"""
Functional settings and cooldown repository.
Zero custom classes.
"""

import datetime
from typing import Any, Optional, Tuple

from src.media_bot.db.engine import execute, fetch_one


def get_setting(
    conn: Any,
    database_url: str,
    key: str,
    default: Optional[str] = None,
) -> Optional[str]:
    row = fetch_one(
        conn,
        database_url,
        "SELECT setting_value FROM bot_settings WHERE setting_key = ?",
        (key,),
    )
    if row:
        return str(row["setting_value"])
    return default


def set_setting(
    conn: Any,
    database_url: str,
    key: str,
    value: str,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    existing = get_setting(conn, database_url, key)
    if existing is not None:
        execute(
            conn,
            database_url,
            "UPDATE bot_settings SET setting_value = ?, updated_at = ? WHERE setting_key = ?",
            (value, now, key),
            commit=True,
        )
    else:
        execute(
            conn,
            database_url,
            "INSERT INTO bot_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
            commit=True,
        )


def set_cooldown(
    conn: Any,
    database_url: str,
    key: str,
    seconds: int,
) -> None:
    if seconds <= 0:
        return
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    expires_dt = now_dt + datetime.timedelta(seconds=seconds)
    expires_str = expires_dt.isoformat()

    execute(
        conn,
        database_url,
        "INSERT OR REPLACE INTO cooldowns (cooldown_key, expires_at) VALUES (?, ?)",
        (key, expires_str),
        commit=True,
    )


def check_cooldown(
    conn: Any,
    database_url: str,
    key: str,
) -> Tuple[bool, int]:
    row = fetch_one(
        conn,
        database_url,
        "SELECT expires_at FROM cooldowns WHERE cooldown_key = ?",
        (key,),
    )
    if not row:
        return False, 0

    try:
        expires_str = str(row["expires_at"])
        expires_dt = datetime.datetime.fromisoformat(expires_str)
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        remaining = (expires_dt - now_dt).total_seconds()
        if remaining > 0:
            return True, int(remaining) + 1
    except Exception:
        pass

    return False, 0
