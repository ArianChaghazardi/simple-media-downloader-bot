"""
Functional Admin Panel for Simple Media Downloader.
Zero custom classes: pure functions handling admin stats and limit configurations.
"""

from typing import Any, Dict

from src.media_bot.bot_api.client import edit_message_text, send_message
from src.media_bot.bot_api.keyboards import (
    admin_limits_keyboard,
    admin_main_keyboard,
    back_cancel_keyboard,
)
from src.media_bot.db.repositories.downloads_stats import get_detailed_stats
from src.media_bot.db.repositories.jobs import count_jobs_by_status
from src.media_bot.db.repositories.settings import set_setting
from src.media_bot.db.repositories.user_states import (
    clear_user_state,
    set_user_state,
)
from src.media_bot.services.quota_service import (
    get_configured_daily_limit,
    is_group_limit_enabled,
    is_user_limit_enabled,
    set_group_limit_enabled,
    set_user_limit_enabled,
)


def is_authorized_admin(
    cfg: Dict[str, Any],
    user_id: int,
    **kwargs: Any,
) -> bool:
    """
    Checks if a telegram user is in the configured ADMIN_IDS list.
    """
    admin_ids = cfg.get("ADMIN_IDS", [])
    try:
        u_int = int(user_id)
    except (ValueError, TypeError):
        return False
    return any(int(a) == u_int for a in admin_ids)


def handle_admin_home(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    user_id = update["user_id"]
    chat_id = update["chat_id"]
    msg_id = update.get("message_id")
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    if not is_authorized_admin(cfg, user_id):
        send_message(bot_token, chat_id, "❌ شما دسترسی مدیریت به این ربات را ندارید.")
        return

    clear_user_state(conn, database_url, user_id)
    text = (
        "👑 <b>پنل مدیریت ربات مدیا دانلودر</b>\n\n"
        "به بخش مدیریت ربات خوش آمدید. لطفا یک بخش را انتخاب نمایید:"
    )
    kb = admin_main_keyboard(locale)

    if msg_id and update.get("type") == "callback_query":
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)


def handle_admin_stats(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    user_id = update["user_id"]
    chat_id = update["chat_id"]
    msg_id = update.get("message_id")
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    if not is_authorized_admin(cfg, user_id):
        return

    st = get_detailed_stats(conn, database_url)
    job_stats = count_jobs_by_status(conn, database_url)
    platforms = st.get("platform_downloads", {})

    platform_lines = [
        f"• اینستاگرام (Instagram): <b>{platforms.get('instagram', 0)}</b> دانلود",
        f"• یوتیوب (YouTube): <b>{platforms.get('youtube', 0)}</b> دانلود",
        f"• تیک تاک (TikTok): <b>{platforms.get('tiktok', 0)}</b> دانلود",
        f"• پینترست (Pinterest): <b>{platforms.get('pinterest', 0)}</b> دانلود",
        f"• توییتر / ایکس (Twitter/X): <b>{platforms.get('x', 0)}</b> دانلود",
        f"• تردز (Threads): <b>{platforms.get('threads', 0)}</b> دانلود",
        f"• ردیت (Reddit): <b>{platforms.get('reddit', 0)}</b> دانلود",
    ]

    lines = [
        "📊 <b>گزارش و آمار پیشرفته سیستم</b>\n",
        "👥 <b>آمار ثبت نام کاربران:</b>",
        f"• امروز: <b>{st['users_today']}</b> کاربر جدید",
        f"• دیروز: <b>{st['users_yesterday']}</b> کاربر",
        f"• 7 روز گذشته: <b>{st['users_7d']}</b> کاربر",
        f"• 30 روز گذشته: <b>{st['users_30d']}</b> کاربر",
        f"• کل کاربران ثبت شده: <b>{st['users_total']}</b> کاربر",
        f"• گروه های فعال: <b>{st['groups_total']}</b> گروه\n",
        "⚡️ <b>آمار فعالیت کاربران (کاربران فعال):</b>",
        f"• امروز: <b>{st.get('active_today', 0)}</b> کاربر فعال",
        f"• دیروز: <b>{st.get('active_yesterday', 0)}</b> کاربر فعال",
        f"• 3 روز گذشته: <b>{st.get('active_3d', 0)}</b> کاربر فعال",
        f"• 7 روز گذشته: <b>{st.get('active_7d', 0)}</b> کاربر فعال",
        f"• 30 روز گذشته: <b>{st.get('active_30d', 0)}</b> کاربر فعال\n",
        "📥 <b>تفکیک کل دانلودها بر اساس شبکه:</b>",
        f"• کل دانلود ها: <b>{st['downloads_total']}</b> فایل",
        *platform_lines,
        "",
        "⚙️ <b>وضعیت صف پردازش:</b>",
        f"• در صف انتظار: {job_stats.get('pending', 0)}",
        f"• در حال پردازش: {job_stats.get('running', 0)}",
        f"• دانلود موفق: {job_stats.get('completed', 0)}",
        f"• دانلود ناموفق: {job_stats.get('failed', 0)}",
    ]
    text = "\n".join(lines)
    kb = back_cancel_keyboard("admin:home", locale)
    if msg_id:
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)


def handle_admin_limits_menu(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    user_id = update["user_id"]
    chat_id = update["chat_id"]
    msg_id = update.get("message_id")
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    if not is_authorized_admin(cfg, user_id):
        return

    clear_user_state(conn, database_url, user_id)

    u_enabled = is_user_limit_enabled(conn, database_url, cfg)
    u_limit = get_configured_daily_limit(conn, database_url, cfg, is_group=False)
    g_enabled = is_group_limit_enabled(conn, database_url, cfg)
    g_limit = get_configured_daily_limit(conn, database_url, cfg, is_group=True)

    u_status_str = f"فعال (سقف: {u_limit} دانلود در روز)" if u_enabled else "غیرفعال (نامحدود)"
    g_status_str = f"فعال (سقف: {g_limit} دانلود در روز)" if g_enabled else "غیرفعال (نامحدود)"

    text = (
        "⚙️ <b>تنظیمات محدودیت دانلود روزانه</b>\n\n"
        f"👤 <b>محدودیت کاربران عادی:</b> {u_status_str}\n"
        f"👥 <b>محدودیت گروه ها:</b> {g_status_str}\n\n"
        "برای تغییر وضعیت فعال بودن یا ویرایش سقف مجاز دانلود از دکمه های زیر استفاده کنید:"
    )
    kb = admin_limits_keyboard(u_enabled, g_enabled, locale)

    if msg_id and update.get("type") == "callback_query":
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)


def handle_admin_toggle_user_limit(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    user_id = update["user_id"]
    database_url = cfg["DATABASE_URL"]
    if not is_authorized_admin(cfg, user_id):
        return
    cur = is_user_limit_enabled(conn, database_url, cfg)
    set_user_limit_enabled(conn, database_url, not cur)
    handle_admin_limits_menu(cfg, conn, update)


def handle_admin_toggle_group_limit(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    user_id = update["user_id"]
    database_url = cfg["DATABASE_URL"]
    if not is_authorized_admin(cfg, user_id):
        return
    cur = is_group_limit_enabled(conn, database_url, cfg)
    set_group_limit_enabled(conn, database_url, not cur)
    handle_admin_limits_menu(cfg, conn, update)


def handle_admin_set_user_limit_prompt(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    user_id = update["user_id"]
    chat_id = update["chat_id"]
    msg_id = update.get("message_id")
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    if not is_authorized_admin(cfg, user_id):
        return

    set_user_state(conn, database_url, user_id, "awaiting_user_daily_limit", {})
    text = (
        "✏️ <b>تنظیم سقف دانلود روزانه کاربران عادی:</b>\n\n"
        "لطفا عدد سقف دانلود روزانه برای هر کاربر را ارسال نمایید (مثلا: 10):"
    )
    kb = back_cancel_keyboard("admin:limits", locale)
    if msg_id:
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)


def handle_admin_set_group_limit_prompt(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    user_id = update["user_id"]
    chat_id = update["chat_id"]
    msg_id = update.get("message_id")
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    if not is_authorized_admin(cfg, user_id):
        return

    set_user_state(conn, database_url, user_id, "awaiting_group_daily_limit", {})
    text = (
        "✏️ <b>تنظیم سقف دانلود روزانه گروه ها:</b>\n\n"
        "لطفا عدد سقف دانلود روزانه برای هر گروه را ارسال نمایید (مثلا: 50):"
    )
    kb = back_cancel_keyboard("admin:limits", locale)
    if msg_id:
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)


def handle_admin_text_input(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
    state_info: Dict[str, Any],
) -> bool:
    user_id = update["user_id"]
    chat_id = update["chat_id"]
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    state = state_info.get("state", "")
    text = update.get("text", "").strip()

    if not is_authorized_admin(cfg, user_id):
        return False

    if state == "awaiting_user_daily_limit":
        if not text.isdigit() or int(text) < 1:
            send_message(bot_token, chat_id, "❌ لطفا یک عدد معتبر بزرگتر از صفر وارد کنید.")
            return True
        set_setting(conn, database_url, "DAILY_USER_DOWNLOAD_LIMIT", text)
        clear_user_state(conn, database_url, user_id)
        send_message(bot_token, chat_id, f"✅ سقف دانلود روزانه کاربران به <b>{text}</b> عدد تغییر یافت.")
        handle_admin_limits_menu(cfg, conn, update)
        return True

    elif state == "awaiting_group_daily_limit":
        if not text.isdigit() or int(text) < 1:
            send_message(bot_token, chat_id, "❌ لطفا یک عدد معتبر بزرگتر از صفر وارد کنید.")
            return True
        set_setting(conn, database_url, "DAILY_GROUP_DOWNLOAD_LIMIT", text)
        clear_user_state(conn, database_url, user_id)
        send_message(bot_token, chat_id, f"✅ سقف دانلود روزانه گروه ها به <b>{text}</b> عدد تغییر یافت.")
        handle_admin_limits_menu(cfg, conn, update)
        return True

    return False
