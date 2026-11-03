"""
Unit tests for Admin limits configuration and permission enforcement.
Zero custom classes.
"""

from src.media_bot.db.engine import close_connection, create_connection
from src.media_bot.db.migrations import run_migrations
from src.media_bot.handlers.admin import is_authorized_admin
from src.media_bot.services.quota_service import (
    check_download_permission,
    is_group_limit_enabled,
    is_user_limit_enabled,
    record_successful_download,
    set_group_limit_enabled,
    set_user_limit_enabled,
)


def _setup_test_db(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, "migrations")
    conn = create_connection(db_url)
    return conn, db_url


def test_admin_authorization():
    cfg = {"ADMIN_IDS": [123456, 789012]}
    assert is_authorized_admin(cfg, 123456) is True
    assert is_authorized_admin(cfg, "789012") is True
    assert is_authorized_admin(cfg, 999999) is False


def test_user_limit_toggle_and_quota(tmp_path):
    conn, db_url = _setup_test_db(tmp_path)
    try:
        cfg = {"ADMIN_IDS": [123], "DATABASE_URL": db_url, "DAILY_USER_DOWNLOAD_LIMIT": 2}

        # 1. Enabled by default
        assert is_user_limit_enabled(conn, db_url, cfg) is True

        # 2. Permission check: 0 used
        allowed, reason, meta = check_download_permission(conn, db_url, cfg, user_id=10, chat_id=10, is_group=False)
        assert allowed is True
        assert meta["remaining"] == 2

        # 3. Record 2 downloads
        record_successful_download(conn, db_url, user_id=10, chat_id=10, platform="youtube", is_group=False)
        record_successful_download(conn, db_url, user_id=10, chat_id=10, platform="instagram", is_group=False)

        # 4. Quota exceeded
        allowed, reason, meta = check_download_permission(conn, db_url, cfg, user_id=10, chat_id=10, is_group=False)
        assert allowed is False
        assert reason == "quota_exceeded"
        assert meta["remaining"] == 0

        # 5. Disable limit globally
        set_user_limit_enabled(conn, db_url, False)
        assert is_user_limit_enabled(conn, db_url, cfg) is False

        # 6. Now unlimited
        allowed, reason, meta = check_download_permission(conn, db_url, cfg, user_id=10, chat_id=10, is_group=False)
        assert allowed is True
        assert meta["limit_disabled"] is True
    finally:
        close_connection(conn)


def test_group_limit_toggle_and_quota(tmp_path):
    conn, db_url = _setup_test_db(tmp_path)
    try:
        cfg = {"ADMIN_IDS": [123], "DATABASE_URL": db_url, "DAILY_GROUP_DOWNLOAD_LIMIT": 3}

        # 1. Default enabled
        assert is_group_limit_enabled(conn, db_url, cfg) is True

        # 2. Record 3 downloads in group
        for _ in range(3):
            record_successful_download(conn, db_url, user_id=10, chat_id=-100123456, platform="tiktok", is_group=True)

        allowed, reason, meta = check_download_permission(conn, db_url, cfg, user_id=10, chat_id=-100123456, is_group=True)
        assert allowed is False
        assert reason == "quota_exceeded"

        # 3. Disable group limit
        set_group_limit_enabled(conn, db_url, False)
        allowed, reason, meta = check_download_permission(conn, db_url, cfg, user_id=10, chat_id=-100123456, is_group=True)
        assert allowed is True
    finally:
        close_connection(conn)
