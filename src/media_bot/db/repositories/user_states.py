"""
Functional user conversation state repository.
Tracks multi-step conversation states (e.g. awaiting media URL, awaiting support message).
Zero custom classes: pure functions and plain dictionaries.
"""

import datetime
import json
from typing import Any, Dict, Optional

from src.media_bot.db.engine import execute, fetch_one


def get_user_state(
    conn: Any,
    database_url: str,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        conn,
        database_url,
        "SELECT user_id, state, data_json, updated_at FROM user_states WHERE user_id = ?",
        (user_id,),
    )
    if not row:
        return None

    data = None
    if row.get("data_json"):
        try:
            data = json.loads(row["data_json"])
        except Exception:
            data = None

    return {
        "user_id": int(row["user_id"]),
        "state": str(row["state"]),
        "data": data,
        "updated_at": row["updated_at"],
    }


def set_user_state(
    conn: Any,
    database_url: str,
    user_id: int,
    state: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data_str = json.dumps(data) if data is not None else None

    # SQLite and MySQL compatible upsert or replace
    execute(
        conn,
        database_url,
        """INSERT INTO user_states (user_id, state, data_json, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               state = excluded.state,
               data_json = excluded.data_json,
               updated_at = excluded.updated_at""",
        (user_id, state, data_str, now_utc),
        commit=True,
    )


def clear_user_state(
    conn: Any,
    database_url: str,
    user_id: int,
) -> None:
    execute(
        conn,
        database_url,
        "DELETE FROM user_states WHERE user_id = ?",
        (user_id,),
        commit=True,
    )
