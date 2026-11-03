"""
Functional download intake handler for Simple Media Downloader.
Zero custom classes.
"""

from typing import Any, Dict

from src.media_bot.bot_api.client import edit_message_text, send_message
from src.media_bot.bot_api.keyboards import (
    back_cancel_keyboard,
    quota_exhausted_keyboard,
)
from src.media_bot.db.repositories.user_states import clear_user_state, set_user_state
from src.media_bot.locales import t
from src.media_bot.providers.url_validator import extract_first_url, validate_url
from src.media_bot.services.job_service import create_download_job, format_job_status
from src.media_bot.services.quota_service import check_download_permission
from src.media_bot.services.rate_limit_service import (
    apply_user_cooldown,
    check_user_cooldown,
)


def handle_downloads_prompt(
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

    set_user_state(conn, database_url, user_id, "awaiting_downloads", {})
    text = t("download_prompt", locale)
    kb = back_cancel_keyboard("nav:home", locale)
    if msg_id:
        edit_message_text(bot_token, chat_id, msg_id, text, reply_markup=kb)
    else:
        send_message(bot_token, chat_id, text, reply_markup=kb)


def handle_media_url(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")
    cooldown_sec = cfg.get("USER_COOLDOWN_SECONDS", 10)
    max_queue = cfg.get("MAX_QUEUE_SIZE", 50)

    user_id = update["user_id"]
    chat_id = update["chat_id"]
    clear_user_state(conn, database_url, user_id)
    text = update.get("text", "").strip()

    clean_url = extract_first_url(text)
    is_valid, platform, err = validate_url(clean_url)
    if not is_valid:
        return

    # 1. Check cooldown
    in_cooldown, remaining = check_user_cooldown(conn, database_url, user_id, "download")
    if in_cooldown:
        send_message(bot_token, chat_id, t("cooldown_wait", locale, seconds=remaining))
        return

    # 2. Check daily download quota
    allowed, reason, quota_info = check_download_permission(
        conn, database_url, cfg, user_id, chat_id, is_group=False
    )
    if not allowed:
        used_cnt = quota_info.get("used", 0)
        daily_base = quota_info.get("daily_base", 0)
        text_quota = (
            "⚠️ <b>سهمیه دانلود امروز شما به پایان رسیده است!</b>\n\n"
            f"📊 دانلودهای استفاده شده امروز: <b>{used_cnt} از {daily_base}</b> مدیا\n\n"
            "سهمیه دانلود شما فردا ساعت ۰۰:۰۰ به وقت گرینویچ مجددا تمدید خواهد شد."
        )
        send_message(
            bot_token,
            chat_id,
            text_quota,
            reply_markup=quota_exhausted_keyboard(locale),
        )
        return

    # 3. Send initial progress feedback & enqueue download job
    status_text = format_job_status(
        platform=platform, step="queued", percent=20, locale=locale
    )
    msg_res = send_message(bot_token, chat_id, status_text)
    status_msg_id = (msg_res.get("result") or {}).get("message_id")

    job_res = create_download_job(
        conn,
        database_url,
        platform=platform,
        chat_id=chat_id,
        user_id=user_id,
        url=clean_url,
        max_queue_size=max_queue,
        status_message_id=status_msg_id,
    )

    if not job_res.get("ok"):
        err_msg = t("job_failed", locale, reason="Queue is currently full. Please try again soon.")
        if status_msg_id:
            edit_message_text(bot_token, chat_id, status_msg_id, err_msg)
        else:
            send_message(bot_token, chat_id, err_msg)
        return

    # Apply cooldown
    apply_user_cooldown(conn, database_url, user_id, cooldown_sec, "download")
