"""
Functional daily download quota service for Simple Media Downloader.
Zero custom classes: pure functions and plain dictionaries.
"""

from typing import Any, Dict, Optional, Tuple

from src.media_bot.db.repositories.downloads_stats import record_download_stat
from src.media_bot.db.repositories.settings import get_setting, set_setting
from src.media_bot.db.repositories.users import (
    get_and_reset_daily_quota,
    increment_daily_downloads,
)


def is_user_limit_enabled(
    conn: Any,
    database_url: str,
    cfg: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Checks if daily download limit for private users is enabled.
    """
    val = get_setting(conn, database_url, "USER_LIMIT_ENABLED")
    if val is not None:
        return val.strip().lower() in ("true", "1", "yes", "on")
    if cfg and "USER_LIMIT_ENABLED" in cfg:
        return bool(cfg["USER_LIMIT_ENABLED"])
    return True


def set_user_limit_enabled(
    conn: Any,
    database_url: str,
    enabled: bool,
) -> None:
    """
    Enables or disables daily download limit for private users.
    """
    set_setting(conn, database_url, "USER_LIMIT_ENABLED", "true" if enabled else "false")


def is_group_limit_enabled(
    conn: Any,
    database_url: str,
    cfg: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Checks if daily download limit for groups is enabled.
    """
    val = get_setting(conn, database_url, "GROUP_LIMIT_ENABLED")
    if val is not None:
        return val.strip().lower() in ("true", "1", "yes", "on")
    if cfg and "GROUP_LIMIT_ENABLED" in cfg:
        return bool(cfg["GROUP_LIMIT_ENABLED"])
    return True


def set_group_limit_enabled(
    conn: Any,
    database_url: str,
    enabled: bool,
) -> None:
    """
    Enables or disables daily download limit for groups.
    """
    set_setting(conn, database_url, "GROUP_LIMIT_ENABLED", "true" if enabled else "false")


def get_configured_daily_limit(
    conn: Any,
    database_url: str,
    cfg: Dict[str, Any],
    is_group: bool = False,
) -> int:
    key = "DAILY_GROUP_DOWNLOAD_LIMIT" if is_group else "DAILY_USER_DOWNLOAD_LIMIT"
    db_val = get_setting(conn, database_url, key)
    if db_val and db_val.isdigit():
        return int(db_val)
    default = 50 if is_group else 10
    return int(cfg.get(key, default))


def check_download_permission(
    conn: Any,
    database_url: str,
    cfg: Dict[str, Any],
    user_id: int,
    chat_id: int,
    is_group: bool = False,
) -> Tuple[bool, str, Dict[str, Any]]:
    target_id = chat_id if is_group else user_id
    quota = get_and_reset_daily_quota(conn, database_url, target_id, is_group=is_group)

    limit_active = (
        is_group_limit_enabled(conn, database_url, cfg)
        if is_group
        else is_user_limit_enabled(conn, database_url, cfg)
    )

    if not limit_active:
        return True, "unlimited_active", {
            "used": quota.get("daily_downloads_used", 0),
            "daily_base": 999999,
            "remaining": 999999,
            "limit_disabled": True,
        }

    daily_base = get_configured_daily_limit(conn, database_url, cfg, is_group=is_group)
    used = quota.get("daily_downloads_used", 0)
    remaining = max(0, daily_base - used)

    if used >= daily_base:
        return False, "quota_exceeded", {
            "used": used,
            "daily_base": daily_base,
            "remaining": 0,
        }

    return True, "quota_ok", {
        "used": used,
        "daily_base": daily_base,
        "remaining": remaining,
    }


def record_successful_download(
    conn: Any,
    database_url: str,
    user_id: int,
    chat_id: int,
    platform: str,
    is_group: bool = False,
    permission_meta: Optional[Dict[str, Any]] = None,
) -> None:
    target_id = chat_id if is_group else user_id
    increment_daily_downloads(conn, database_url, target_id, is_group=is_group)
    record_download_stat(conn, database_url, user_id, chat_id, platform)
