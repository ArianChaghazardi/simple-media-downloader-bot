"""
Functional downloads statistics and reporting repository.
Zero custom classes: pure functions and plain dictionaries.
"""

import datetime
from typing import Any, Dict

from src.media_bot.db.engine import execute, fetch_all, fetch_one, get_backend_type


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


def record_user_activity(
    conn: Any,
    database_url: str,
    user_id: int,
) -> None:
    if not user_id or user_id <= 0:
        return
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    act_date = now_dt.strftime("%Y-%m-%d")
    now_iso = now_dt.isoformat()
    backend = get_backend_type(database_url)
    try:
        if backend == "mysql":
            execute(
                conn,
                database_url,
                """INSERT INTO user_activity_daily (user_id, activity_date, last_action_at)
                   VALUES (?, ?, ?)
                   ON DUPLICATE KEY UPDATE last_action_at = VALUES(last_action_at)""",
                (user_id, act_date, now_iso),
                commit=True,
            )
        else:
            execute(
                conn,
                database_url,
                """INSERT INTO user_activity_daily (user_id, activity_date, last_action_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, activity_date) DO UPDATE SET last_action_at = excluded.last_action_at""",
                (user_id, act_date, now_iso),
                commit=True,
            )
    except Exception:
        pass


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

    # VIP users count (if column exists)
    vip_cnt_val = 0
    try:
        vip_cnt = fetch_one(
            conn,
            database_url,
            "SELECT COUNT(*) as cnt FROM users WHERE vip_expires_at > ?",
            (now.isoformat(),),
        )
        vip_cnt_val = int(vip_cnt["cnt"]) if vip_cnt else 0
    except Exception:
        pass

    # Active Users Breakdown (DAU / WAU / MAU)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    d3_str = (now - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    d7_str = (now - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    d30_str = (now - datetime.timedelta(days=29)).strftime("%Y-%m-%d")

    act_today_cnt = 0
    act_yesterday_cnt = 0
    act_3d_cnt = 0
    act_7d_cnt = 0
    act_30d_cnt = 0
    try:
        act_today = fetch_one(
            conn,
            database_url,
            "SELECT COUNT(DISTINCT user_id) as cnt FROM user_activity_daily WHERE activity_date = ?",
            (today_str,),
        )
        act_yesterday = fetch_one(
            conn,
            database_url,
            "SELECT COUNT(DISTINCT user_id) as cnt FROM user_activity_daily WHERE activity_date = ?",
            (yesterday_str,),
        )
        act_3d = fetch_one(
            conn,
            database_url,
            "SELECT COUNT(DISTINCT user_id) as cnt FROM user_activity_daily WHERE activity_date >= ?",
            (d3_str,),
        )
        act_7d = fetch_one(
            conn,
            database_url,
            "SELECT COUNT(DISTINCT user_id) as cnt FROM user_activity_daily WHERE activity_date >= ?",
            (d7_str,),
        )
        act_30d = fetch_one(
            conn,
            database_url,
            "SELECT COUNT(DISTINCT user_id) as cnt FROM user_activity_daily WHERE activity_date >= ?",
            (d30_str,),
        )
        act_today_cnt = int(act_today["cnt"]) if act_today else 0
        act_yesterday_cnt = int(act_yesterday["cnt"]) if act_yesterday else 0
        act_3d_cnt = int(act_3d["cnt"]) if act_3d else 0
        act_7d_cnt = int(act_7d["cnt"]) if act_7d else 0
        act_30d_cnt = int(act_30d["cnt"]) if act_30d else 0
    except Exception:
        pass

    return {
        "users_today": int(u_today["cnt"]) if u_today else 0,
        "users_yesterday": int(u_yesterday["cnt"]) if u_yesterday else 0,
        "users_7d": int(u_7d["cnt"]) if u_7d else 0,
        "users_30d": int(u_30d["cnt"]) if u_30d else 0,
        "users_total": int(u_total["cnt"]) if u_total else 0,
        "groups_total": int(g_total["cnt"]) if g_total else 0,
        "vip_users": vip_cnt_val,
        "downloads_total": int(d_total["cnt"]) if d_total else 0,
        "platform_downloads": platform_counts,
        "active_today": act_today_cnt,
        "active_yesterday": act_yesterday_cnt,
        "active_3d": act_3d_cnt,
        "active_7d": act_7d_cnt,
        "active_30d": act_30d_cnt,
    }
