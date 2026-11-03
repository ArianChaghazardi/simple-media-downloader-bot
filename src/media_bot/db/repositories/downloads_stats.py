"""
Functional downloads statistics and reporting repository.
Zero custom classes: pure functions and plain dictionaries.
"""

import datetime
from typing import Any, Dict

from src.media_bot.db.engine import execute, fetch_all, fetch_one


def record_download_stat(
    conn: Any,
    database_url: str,
    user_id: int,
    chat_id: int,
    platform: str,
) -> None:
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    execute(
        conn,
        database_url,
        "INSERT INTO downloads_stats (user_id, chat_id, platform, created_at) VALUES (?, ?, ?, ?)",
        (user_id, chat_id, platform, now_utc),
        commit=True,
    )


def get_detailed_stats(
    conn: Any,
    database_url: str,
) -> Dict[str, Any]:
    now = datetime.datetime.now(datetime.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    yesterday_start = (
        now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=1)
    ).isoformat()
    seven_days_ago = (now - datetime.timedelta(days=7)).isoformat()
    thirty_days_ago = (now - datetime.timedelta(days=30)).isoformat()

    # User signups breakdown
    u_today = fetch_one(
        conn,
        database_url,
        "SELECT COUNT(*) as cnt FROM users WHERE created_at >= ?",
        (today_start,),
    )
    u_yesterday = fetch_one(
        conn,
        database_url,
        "SELECT COUNT(*) as cnt FROM users WHERE created_at >= ? AND created_at < ?",
        (yesterday_start, today_start),
    )
    u_7d = fetch_one(
        conn,
        database_url,
        "SELECT COUNT(*) as cnt FROM users WHERE created_at >= ?",
        (seven_days_ago,),
    )
    u_30d = fetch_one(
        conn,
        database_url,
        "SELECT COUNT(*) as cnt FROM users WHERE created_at >= ?",
        (thirty_days_ago,),
    )
    u_total = fetch_one(conn, database_url, "SELECT COUNT(*) as cnt FROM users")

    # Groups count
    g_total = fetch_one(conn, database_url, "SELECT COUNT(*) as cnt FROM bot_groups")

    # Total downloads
    d_total = fetch_one(conn, database_url, "SELECT COUNT(*) as cnt FROM downloads_stats")

    # Platform breakdown
    platform_rows = fetch_all(
        conn,
        database_url,
        "SELECT platform, COUNT(*) as cnt FROM downloads_stats GROUP BY platform ORDER BY cnt DESC",
    )
    platform_counts: Dict[str, int] = {str(r["platform"]): int(r["cnt"]) for r in platform_rows}

    return {
        "users_today": int(u_today["cnt"]) if u_today else 0,
        "users_yesterday": int(u_yesterday["cnt"]) if u_yesterday else 0,
        "users_7d": int(u_7d["cnt"]) if u_7d else 0,
        "users_30d": int(u_30d["cnt"]) if u_30d else 0,
        "users_total": int(u_total["cnt"]) if u_total else 0,
        "groups_total": int(g_total["cnt"]) if g_total else 0,
        "downloads_total": int(d_total["cnt"]) if d_total else 0,
        "platform_downloads": platform_counts,
    }
