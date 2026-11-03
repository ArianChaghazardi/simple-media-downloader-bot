"""
Functional repository for Telegram users and daily quota tracking.
Zero custom classes: parameterized queries, plain dict outputs.
"""

import datetime
from typing import Any, Dict, List, Optional

from src.media_bot.db.engine import execute, fetch_all, fetch_one


def get_user(conn: Any, database_url: str, telegram_id: int) -> Optional[Dict[str, Any]]:
    return fetch_one(
        conn,
        database_url,
        "SELECT * FROM users WHERE telegram_id = ?",
        (telegram_id,),
    )


def upsert_user(
    conn: Any,
    database_url: str,
    telegram_id: int,
    first_name: Optional[str] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    existing = get_user(conn, database_url, telegram_id)

    if existing:
        execute(
            conn,
            database_url,
            "UPDATE users SET first_name = ?, username = ?, updated_at = ? WHERE telegram_id = ?",
            (
                first_name or existing.get("first_name"),
                username or existing.get("username"),
                now,
                telegram_id,
            ),
            commit=True,
        )
        return {
            "telegram_id": telegram_id,
            "first_name": first_name or existing.get("first_name"),
            "username": username or existing.get("username"),
            "is_new": False,
        }
    else:
        execute(
            conn,
            database_url,
            """INSERT INTO users (telegram_id, first_name, username, is_banned, daily_downloads_used, created_at, updated_at)
               VALUES (?, ?, ?, 0, 0, ?, ?)""",
            (telegram_id, first_name, username, now, now),
            commit=True,
        )
        return {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "username": username,
            "is_new": True,
        }


def set_user_ban(conn: Any, database_url: str, telegram_id: int, is_banned: bool = True) -> None:
    user = get_user(conn, database_url, telegram_id)
    if not user:
        upsert_user(conn, database_url, telegram_id)
    execute(
        conn,
        database_url,
        "UPDATE users SET is_banned = ? WHERE telegram_id = ?",
        (1 if is_banned else 0, telegram_id),
        commit=True,
    )


def is_user_banned(conn: Any, database_url: str, telegram_id: int) -> bool:
    user = get_user(conn, database_url, telegram_id)
    if user:
        return bool(user.get("is_banned", 0))
    return False


def count_users(conn: Any, database_url: str) -> int:
    row = fetch_one(conn, database_url, "SELECT COUNT(*) as cnt FROM users")
    return int(row["cnt"]) if row else 0


def list_users(
    conn: Any,
    database_url: str,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    return fetch_all(
        conn,
        database_url,
        "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )


def get_and_reset_daily_quota(
    conn: Any,
    database_url: str,
    target_id: int,
    is_group: bool = False,
) -> Dict[str, Any]:
    table = "bot_groups" if is_group else "users"
    id_col = "chat_id" if is_group else "telegram_id"
    row = fetch_one(
        conn,
        database_url,
        f"SELECT {id_col}, daily_downloads_used, last_download_date FROM {table} WHERE {id_col} = ?",
        (target_id,),
    )
    if not row:
        return {
            "daily_downloads_used": 0,
            "last_download_date": "",
        }

    now_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    last_date = row.get("last_download_date")
    used = int(row.get("daily_downloads_used") or 0)

    # Reset if new day
    if last_date != now_date:
        used = 0
        execute(
            conn,
            database_url,
            f"UPDATE {table} SET daily_downloads_used = 0, last_download_date = ? WHERE {id_col} = ?",
            (now_date, target_id),
            commit=True,
        )

    return {
        "daily_downloads_used": used,
        "last_download_date": now_date,
    }


def increment_daily_downloads(
    conn: Any,
    database_url: str,
    target_id: int,
    is_group: bool = False,
) -> None:
    table = "bot_groups" if is_group else "users"
    id_col = "chat_id" if is_group else "telegram_id"
    now_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    row = fetch_one(
        conn, database_url, f"SELECT {id_col} FROM {table} WHERE {id_col} = ?", (target_id,)
    )
    if not row:
        if is_group:
            execute(
                conn,
                database_url,
                """INSERT INTO bot_groups (chat_id, is_active, daily_downloads_used, last_download_date, created_at, updated_at)
                   VALUES (?, 1, 1, ?, ?, ?)""",
                (target_id, now_date, now_iso, now_iso),
                commit=True,
            )
        else:
            execute(
                conn,
                database_url,
                """INSERT INTO users (telegram_id, is_banned, daily_downloads_used, last_download_date, created_at, updated_at)
                   VALUES (?, 0, 1, ?, ?, ?)""",
                (target_id, now_date, now_iso, now_iso),
                commit=True,
            )
        return

    execute(
        conn,
        database_url,
        f"""UPDATE {table}
           SET daily_downloads_used = COALESCE(daily_downloads_used, 0) + 1,
               last_download_date = ?
           WHERE {id_col} = ?""",
        (now_date, target_id),
        commit=True,
    )
