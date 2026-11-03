"""
Functional start and navigation handler for Simple Media Downloader.
Handles onboarding, help menu, and account quota overview.
Zero custom classes.
"""

from typing import Any, Dict

from src.media_bot.bot_api.client import edit_message_text, send_message
from src.media_bot.bot_api.keyboards import account_menu_keyboard, main_menu_keyboard
from src.media_bot.db.repositories.user_states import clear_user_state
from src.media_bot.db.repositories.users import get_and_reset_daily_quota, upsert_user
from src.media_bot.handlers.admin import is_authorized_admin
from src.media_bot.locales import t
from src.media_bot.services.quota_service import (
    get_configured_daily_limit,
    is_user_limit_enabled,
)


def handle_start(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    bot_username = cfg.get("BOT_USERNAME", "")
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    user_id = update["user_id"]
    chat_id = update["chat_id"]
    clear_user_state(conn, database_url, user_id)
    from_u = update.get("from_user", {})
    first_name = from_u.get("first_name", "کاربر")
    username = from_u.get("username", "")

    user_info = upsert_user(
        conn,
        database_url,
        telegram_id=user_id,
        first_name=first_name,
        username=username,
    )

    is_new = user_info.get("is_new", False)
    welcome_text = t("welcome", locale, name=first_name) if is_new else t("welcome_back", locale, name=first_name)

    is_admin = is_authorized_admin(cfg, user_id)
    kb = main_menu_keyboard(bot_username, locale, is_admin=is_admin)

    send_message(bot_token, chat_id, welcome_text, reply_markup=kb)


def handle_nav_home(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    bot_username = cfg.get("BOT_USERNAME", "")
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    user_id = update["user_id"]
    chat_id = update["chat_id"]
    clear_user_state(conn, database_url, user_id)
    msg_id = update.get("message_id")
    from_u = update.get("from_user", {})
    first_name = from_u.get("first_name", "کاربر")

    is_admin = is_authorized_admin(cfg, user_id)
    kb = main_menu_keyboard(bot_username, locale, is_admin=is_admin)
    text = t("welcome_back", locale, name=first_name)

    if msg_id and update.get("type") == "callback_query":
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)


def handle_nav_account(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    user_id = update["user_id"]
    chat_id = update["chat_id"]
    msg_id = update.get("message_id")

    quota = get_and_reset_daily_quota(conn, database_url, user_id, is_group=False)
    limit_enabled = is_user_limit_enabled(conn, database_url, cfg)
    daily_limit = get_configured_daily_limit(conn, database_url, cfg, is_group=False)
    used = quota.get("daily_downloads_used", 0)

    if limit_enabled:
        remaining = max(0, daily_limit - used)
        quota_text = f"• دانلودهای استفاده شده امروز: <b>{used} از {daily_limit}</b>\n• سهمیه باقی مانده امروز: <b>{remaining}</b> دانلود"
    else:
        quota_text = f"• دانلودهای انجام شده امروز: <b>{used}</b> عدد\n• وضعیت محدودیت: <b>غیرفعال (دانلود نامحدود)</b>"

    text = (
        "👤 <b>اطلاعات حساب کاربری</b>\n\n"
        f"• شناسه عددی شما: <code>{user_id}</code>\n"
        f"{quota_text}\n\n"
        "💡 سهمیه دانلود روزانه هر روز ساعت ۰۰:۰۰ به وقت گرینویچ بازنشانی می شود."
    )
    kb = account_menu_keyboard(locale)

    if msg_id and update.get("type") == "callback_query":
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)


def handle_nav_help(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    bot_token = cfg["BOT_TOKEN"]
    chat_id = update["chat_id"]
    msg_id = update.get("message_id")
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    text = (
        "📖 <b>راهنمای استفاده از ربات مدیا دانلودر</b>\n\n"
        "برای دانلود کافی است لینک پست، ویدیو، ریلز یا استوری مورد نظر خود را در چت ارسال کنید:\n\n"
        "🌐 <b>سرویس های تحت پوشش:</b>\n"
        "• <b>اینستاگرام (Instagram):</b> پست، ریلز، استوری و IGTV\n"
        "• <b>یوتیوب (YouTube):</b> ویدیوهای عادی و شورتز\n"
        "• <b>تیک تاک (TikTok):</b> ویدیو بدون واتر مارک\n"
        "• <b>توییتر / ایکس (Twitter / X):</b> ویدیو و گیف\n"
        "• <b>پینترست (Pinterest):</b> تصاویر و ویدیوهای پین\n"
        "• <b>تردز (Threads):</b> ویدیوها و تصاویر\n"
        "• <b>ردیت (Reddit):</b> ویدیوها به همراه صدا\n\n"
        "👥 <b>استفاده در گروه ها:</b>\n"
        "می توانید ربات را به عنوان ادمین به گروه خود اضافه کنید تا اعضا با ارسال لینک به راحتی مدیا را در گروه دریافت کنند."
    )
    kb = account_menu_keyboard(locale)

    if msg_id and update.get("type") == "callback_query":
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)
