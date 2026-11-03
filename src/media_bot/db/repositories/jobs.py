"""
Functional jobs repository for media processing queue.
Provides atomic leases, idempotency, retry tracking, and stale recovery.
Zero custom classes.
"""

import datetime
import json
from typing import Any, Dict, Optional

from src.media_bot.db.engine import db_transaction, execute, fetch_all, fetch_one


def enqueue_job(
    conn: Any,
    database_url: str,
    idempotency_key: str,
    job_type: str,
    chat_id: int,
    user_id: int,
    payload: Dict[str, Any],
    max_retries: int = 3,
) -> Optional[int]:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload_str = json.dumps(payload)

    # Check if job with this idempotency key already exists
    existing = fetch_one(
        conn,
        database_url,
        "SELECT id, status FROM jobs WHERE idempotency_key = ?",
        (idempotency_key,),
    )
    if existing:
        job_id = int(existing["id"])
        st = existing.get("status")
        # If the job is active (pending or running), don't create duplicate
        if st in ("pending", "running"):
            return job_id
        # If previously completed, failed, or cancelled, reset it to pending so it runs again!
        execute(
            conn,
            database_url,
            """UPDATE jobs
               SET status = 'pending', retry_count = 0, error_message = NULL,
                   worker_id = NULL, lease_expires_at = NULL, payload_json = ?, updated_at = ?
               WHERE id = ?""",
            (payload_str, now, job_id),
            commit=True,
        )
        return job_id

    job_id = execute(
        conn,
        database_url,
        """INSERT INTO jobs (idempotency_key, job_type, chat_id, user_id, status, payload_json, retry_count, max_retries, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'pending', ?, 0, ?, ?, ?)""",
        (idempotency_key, job_type, chat_id, user_id, payload_str, max_retries, now, now),
        commit=True,
    )
    return job_id


def claim_next_job(
    conn: Any,
    database_url: str,
    worker_id: str,
    lease_seconds: int = 120,
) -> Optional[Dict[str, Any]]:
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now_str = now_dt.isoformat()
    lease_expires = (now_dt + datetime.timedelta(seconds=lease_seconds)).isoformat()

    with db_transaction(conn):
        # Select pending job or stale running job
        candidate = fetch_one(
            conn,
            database_url,
            """SELECT * FROM jobs
               WHERE status = 'pending'
                  OR (status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)
               ORDER BY created_at ASC LIMIT 1""",
            (now_str,),
        )
        if not candidate:
            return None

        job_id = candidate["id"]
        execute(
            conn,
            database_url,
            """UPDATE jobs
               SET status = 'running', worker_id = ?, lease_expires_at = ?, updated_at = ?
               WHERE id = ?""",
            (worker_id, lease_expires, now_str, job_id),
        )

        candidate["status"] = "running"
        candidate["worker_id"] = worker_id
        candidate["lease_expires_at"] = lease_expires
        if isinstance(candidate.get("payload_json"), str):
            try:
                candidate["payload"] = json.loads(candidate["payload_json"])
            except Exception:
                candidate["payload"] = {}
        else:
            candidate["payload"] = {}

        return candidate


def complete_job(
    conn: Any,
    database_url: str,
    job_id: int,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    res_str = json.dumps(result or {})
    execute(
        conn,
        database_url,
        """UPDATE jobs
           SET status = 'completed', result_json = ?, updated_at = ?
           WHERE id = ?""",
        (res_str, now, job_id),
        commit=True,
    )


def update_job_status_and_payload(
    conn: Any,
    database_url: str,
    job_id: int,
    status: str,
    payload: Dict[str, Any],
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload_str = json.dumps(payload)
    execute(
        conn,
        database_url,
        """UPDATE jobs
           SET status = ?, payload_json = ?, updated_at = ?
           WHERE id = ?""",
        (status, payload_str, now, job_id),
        commit=True,
    )



def fail_job(
    conn: Any,
    database_url: str,
    job_id: int,
    error_message: str,
    allow_retry: bool = True,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    job = get_job(conn, database_url, job_id)
    if not job:
        return

    retry_count = int(job.get("retry_count", 0))
    max_retries = int(job.get("max_retries", 3))

    if allow_retry and retry_count + 1 < max_retries:
        execute(
            conn,
            database_url,
            """UPDATE jobs
               SET status = 'pending', retry_count = retry_count + 1, error_message = ?, updated_at = ?
               WHERE id = ?""",
            (error_message[:500], now, job_id),
            commit=True,
        )
    else:
        execute(
            conn,
            database_url,
            """UPDATE jobs
               SET status = 'failed', retry_count = retry_count + 1, error_message = ?, updated_at = ?
               WHERE id = ?""",
            (error_message[:500], now, job_id),
            commit=True,
        )


def get_job(conn: Any, database_url: str, job_id: int) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        conn,
        database_url,
        "SELECT * FROM jobs WHERE id = ?",
        (job_id,),
    )
    if row and isinstance(row.get("payload_json"), str):
        try:
            row["payload"] = json.loads(row["payload_json"])
        except Exception:
            row["payload"] = {}
    return row


def count_pending_jobs(conn: Any, database_url: str) -> int:
    row = fetch_one(
        conn,
        database_url,
        "SELECT COUNT(*) as cnt FROM jobs WHERE status IN ('pending', 'running')",
    )
    return int(row["cnt"]) if row else 0


def count_jobs_by_status(conn: Any, database_url: str) -> Dict[str, int]:
    rows = fetch_all(
        conn,
        database_url,
        "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status",
    )
    result = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
    for r in rows:
        st = r.get("status")
        if st in result:
            result[st] = int(r["cnt"])
    return result


def recover_stale_jobs(conn: Any, database_url: str) -> int:
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return execute(
        conn,
        database_url,
        """UPDATE jobs
           SET status = 'pending', lease_expires_at = NULL, updated_at = ?
           WHERE status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?""",
        (now_str, now_str),
        commit=True,
    )
