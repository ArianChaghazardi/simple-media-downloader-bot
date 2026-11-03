"""
Functional update dispatcher and router for Simple Media Downloader.
Maps incoming Telegram updates to functional handlers without custom classes.
"""

from typing import Any, Dict

from src.media_bot.bot_api.client import answer_callback_query, send_message
from src.media_bot.bot_api.updates import (
    is_update_processed,
    mark_update_processed,
    parse_update,
)
from src.media_bot.db.repositories.user_states import get_user_state
from src.media_bot.db.repositories.users import is_user_banned
from src.media_bot.handlers.admin import (
    handle_admin_home,
    handle_admin_limits_menu,
    handle_admin_set_group_limit_prompt,
    handle_admin_set_user_limit_prompt,
    handle_admin_stats,
    handle_admin_text_input,
    handle_admin_toggle_group_limit,
    handle_admin_toggle_user_limit,
    is_authorized_admin,
)
from src.media_bot.handlers.downloads import handle_downloads_prompt, handle_media_url
from src.media_bot.handlers.groups import handle_group_message
from src.media_bot.handlers.large_files import handle_large_file_choice
from src.media_bot.handlers.start import (
    handle_nav_account,
    handle_nav_help,
    handle_nav_home,
    handle_start,
)
from src.media_bot.providers.url_validator import extract_first_url, validate_url


def dispatch_update(
    cfg: Dict[str, Any],
    conn: Any,
    raw_update: Dict[str, Any],
) -> None:
    update = parse_update(raw_update)
    update_id = update["update_id"]
    database_url = cfg["DATABASE_URL"]
    bot_token = cfg["BOT_TOKEN"]

    # Idempotency check
    if is_update_processed(conn, database_url, update_id):
        return
    mark_update_processed(conn, database_url, update_id)

    u_type = update["type"]
    user_id = update.get("user_id")
    chat_id = update.get("chat_id")

    if not user_id or not chat_id:
        return

    # Check ban status
    if is_user_banned(conn, database_url, user_id):
        return

    # 1. Handle Group Messages
    if u_type == "message" and update.get("is_group"):
        handle_group_message(cfg, conn, update)
        return

    # 2. Handle Callback Queries (Inline button clicks)
    if u_type == "callback_query":
        cb_data = update.get("callback_data", "")
        cq_id = update.get("callback_query_id")

        if cb_data == "nav:home":
            handle_nav_home(cfg, conn, update)
        elif cb_data == "nav:account":
            handle_nav_account(cfg, conn, update)
        elif cb_data == "nav:help":
            handle_nav_help(cfg, conn, update)
        elif cb_data == "nav:downloads":
            handle_downloads_prompt(cfg, conn, update)
        elif cb_data == "admin:home":
            handle_admin_home(cfg, conn, update)
        elif cb_data == "admin:stats":
            handle_admin_stats(cfg, conn, update)
        elif cb_data == "admin:limits":
            handle_admin_limits_menu(cfg, conn, update)
        elif cb_data == "admin:toggle_user_limit":
            handle_admin_toggle_user_limit(cfg, conn, update)
        elif cb_data == "admin:toggle_group_limit":
            handle_admin_toggle_group_limit(cfg, conn, update)
        elif cb_data == "admin:set_user_limit":
            handle_admin_set_user_limit_prompt(cfg, conn, update)
        elif cb_data == "admin:set_group_limit":
            handle_admin_set_group_limit_prompt(cfg, conn, update)
        elif cb_data.startswith("large_file:"):
            handle_large_file_choice(cfg, conn, update)
        else:
            if cq_id:
                answer_callback_query(bot_token, cq_id)
        return

    # 3. Handle Private Text Messages
    if u_type == "message":
        text = update.get("text", "").strip()

        # Commands
        if text.startswith("/start"):
            handle_start(cfg, conn, update)
            return

        if text in ("/admin", "/panel", "پنل مدیریت"):
            if is_authorized_admin(cfg, user_id):
                handle_admin_home(cfg, conn, update)
            else:
                send_message(bot_token, chat_id, "❌ شما دسترسی مدیریت به این ربات را ندارید.")
            return

        if text in ("/myaccount", "حساب کاربری"):
            handle_nav_account(cfg, conn, update)
            return

        if text in ("/help", "راهنما"):
            handle_nav_help(cfg, conn, update)
            return

        # Check pending user states (e.g. admin setting daily limits)
        state_info = get_user_state(conn, database_url, user_id)
        if state_info:
            handled = handle_admin_text_input(cfg, conn, update, state_info)
            if handled:
                return

        # Check if message contains a downloadable media URL
        clean_url = extract_first_url(text)
        is_valid, _, _ = validate_url(clean_url)
        if is_valid:
            handle_media_url(cfg, conn, update)
            return

        # Unknown / non-URL messages
        if text.startswith("/"):
            send_message(bot_token, chat_id, "دستور وارد شده نامعتبر است. برای شروع از /start استفاده کنید.")
        else:
            send_message(
                bot_token,
                chat_id,
                "لطفا لینک ویدیو، پست یا ریلز مورد نظر خود را ارسال کنید تا دانلود شود.\n"
                "برای مشاهده لیست سرویس های تحت پوشش از دستور /help استفاده نمایید.",
            )
