"""
Unit tests for Admin stats and breakdown across all 7 media platforms.
Zero custom classes.
"""

from src.media_bot.db.engine import close_connection, create_connection
from src.media_bot.db.migrations import run_migrations
from src.media_bot.db.repositories.downloads_stats import (
    get_detailed_stats,
    record_download_stat,
)
from src.media_bot.db.repositories.users import upsert_user
from src.media_bot.handlers.admin import handle_admin_stats


def _setup_test_db(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, "migrations")
    conn = create_connection(db_url)
    return conn, db_url


def test_detailed_stats_counting(tmp_path, mocker):
    conn, db_url = _setup_test_db(tmp_path)
    try:
        cfg = {"ADMIN_IDS": [1001], "DATABASE_URL": db_url, "BOT_TOKEN": "123:token"}

        upsert_user(conn, db_url, 1001, first_name="Admin")
        upsert_user(conn, db_url, 1002, first_name="User1")

        platforms = ["instagram", "youtube", "tiktok", "pinterest", "x", "threads", "reddit"]
        for p in platforms:
            record_download_stat(conn, db_url, 1002, 1002, p)
            record_download_stat(conn, db_url, 1002, 1002, p)

        stats = get_detailed_stats(conn, db_url)
        assert stats["users_total"] == 2
        assert stats["downloads_total"] == len(platforms) * 2

        mock_edit = mocker.patch("src.media_bot.handlers.admin.edit_message_text")
        update = {"user_id": 1001, "chat_id": 1001, "message_id": 99}
        handle_admin_stats(cfg, conn, update)

        assert mock_edit.call_count == 1
        text = mock_edit.call_args[0][3]

        for p_name in ["Instagram", "YouTube", "TikTok", "Pinterest", "Twitter/X", "Threads", "Reddit"]:
            assert p_name in text
    finally:
        close_connection(conn)
