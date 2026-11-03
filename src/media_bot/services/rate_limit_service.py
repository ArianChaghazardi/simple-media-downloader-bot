"""
Functional rate limit and cooldown service.
Zero custom classes: pure functions and plain dictionaries.
"""

from typing import Any, Tuple

from src.media_bot.db.repositories.settings import check_cooldown, set_cooldown


def check_user_cooldown(
    conn: Any,
    database_url: str,
    user_id: int,
    action: str = "download",
) -> Tuple[bool, int]:
    key = f"user:{user_id}:{action}"
    return check_cooldown(conn, database_url, key)


def apply_user_cooldown(
    conn: Any,
    database_url: str,
    user_id: int,
    cooldown_seconds: int,
    action: str = "download",
) -> None:
    key = f"user:{user_id}:{action}"
    set_cooldown(conn, database_url, key, cooldown_seconds)


def check_group_cooldown(
    conn: Any,
    database_url: str,
    chat_id: int,
    action: str = "download",
) -> Tuple[bool, int]:
    key = f"group:{chat_id}:{action}"
    return check_cooldown(conn, database_url, key)


def apply_group_cooldown(
    conn: Any,
    database_url: str,
    chat_id: int,
    cooldown_seconds: int,
    action: str = "download",
) -> None:
    key = f"group:{chat_id}:{action}"
    set_cooldown(conn, database_url, key, cooldown_seconds)
