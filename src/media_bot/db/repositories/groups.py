"""
Functional groups repository.
Zero custom classes.
"""

import datetime
from typing import Any, Dict, List, Optional

from src.media_bot.db.engine import execute, fetch_all, fetch_one


def get_group(conn: Any, database_url: str, chat_id: int) -> Optional[Dict[str, Any]]:
    return fetch_one(
        conn,
        database_url,
        "SELECT * FROM bot_groups WHERE chat_id = ?",
        (chat_id,),
    )


def upsert_group(
    conn: Any,
    database_url: str,
    chat_id: int,
    title: Optional[str] = None,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    existing = get_group(conn, database_url, chat_id)
    if existing:
        execute(
            conn,
            database_url,
            "UPDATE bot_groups SET title = ?, updated_at = ? WHERE chat_id = ?",
            (title or existing.get("title"), now, chat_id),
            commit=True,
        )
    else:
        execute(
            conn,
            database_url,
            "INSERT INTO bot_groups (chat_id, title, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
            (chat_id, title, now, now),
            commit=True,
        )


def count_groups(conn: Any, database_url: str) -> int:
    row = fetch_one(
        conn, database_url, "SELECT COUNT(*) as cnt FROM bot_groups WHERE is_active = 1"
    )
    return int(row["cnt"]) if row else 0


def list_groups(
    conn: Any,
    database_url: str,
    active_only: bool = True,
    limit: int = 50000,
) -> List[Dict[str, Any]]:
    if active_only:
        sql = "SELECT * FROM bot_groups WHERE is_active = 1 LIMIT ?"
    else:
        sql = "SELECT * FROM bot_groups LIMIT ?"
    return fetch_all(conn, database_url, sql, (limit,))
