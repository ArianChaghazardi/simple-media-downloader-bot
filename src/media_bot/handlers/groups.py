"""
Functional group chat handler for Simple Media Downloader.
Registers groups and handles group media download requests safely.
Zero custom classes.
"""

from typing import Any, Dict

from src.media_bot.bot_api.client import send_message
from src.media_bot.db.repositories.groups import upsert_group
from src.media_bot.locales import t
from src.media_bot.providers.url_validator import extract_first_url, validate_url
from src.media_bot.services.job_service import create_download_job, format_job_status
from src.media_bot.services.quota_service import check_download_permission
from src.media_bot.services.rate_limit_service import (
    apply_group_cooldown,
    check_group_cooldown,
)


def handle_group_message(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")
    cooldown_sec = cfg.get("GROUP_COOLDOWN_SECONDS", 20)
    max_queue = cfg.get("MAX_QUEUE_SIZE", 50)

    chat_id = update["chat_id"]
    user_id = update["user_id"]
    msg_id = update.get("message_id")
    raw_chat = update.get("raw", {}).get("message", {}).get("chat", {})
    chat_title = raw_chat.get("title", f"Group {chat_id}")

    # Register or update group
    upsert_group(conn, database_url, chat_id, chat_title)

    text = update.get("text", "").strip()
    clean_url = extract_first_url(text)
    is_valid, platform, _ = validate_url(clean_url)
    if not is_valid:
        return

    # Check group cooldown
    in_cd, remaining = check_group_cooldown(conn, database_url, chat_id, "download")
    if in_cd:
        send_message(
            bot_token,
            chat_id,
            f"⏳ محدودیت ارسال در گروه فعال است. لطفا {remaining} ثانیه دیگر تلاش کنید.",
            reply_to_message_id=msg_id,
        )
        return

    # Check group daily quota
    allowed, reason, quota_info = check_download_permission(
        conn, database_url, cfg, user_id, chat_id, is_group=True
    )
    if not allowed:
        send_message(
            bot_token,
            chat_id,
            t("group_quota_exceeded", locale, used=quota_info.get("used", 0)),
            reply_to_message_id=msg_id,
        )
        return

    # Send initial progress feedback & enqueue download job
    status_text = format_job_status(
        platform=platform, step="queued", percent=20, locale=locale
    )
    msg_res = send_message(bot_token, chat_id, status_text, reply_to_message_id=msg_id)
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
        return

    apply_group_cooldown(conn, database_url, chat_id, cooldown_sec, "download")
