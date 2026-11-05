"""
Functional handler for large file download choices (>50MB).
Fast compression, audio extraction, and dynamic real-time progress bar.
Zero custom classes.
"""

import os
import subprocess
import time
from typing import Any, Callable, Dict, List

from src.media_bot.bot_api.client import (
    answer_callback_query,
    delete_message,
    edit_message_text,
    send_audio,
    send_chat_action,
    send_document,
    send_video,
)
from src.media_bot.bot_api.keyboards import large_file_options_keyboard
from src.media_bot.db.repositories.jobs import complete_job, get_job
from src.media_bot.db.repositories.users import get_and_reset_daily_quota
from src.media_bot.services.ad_service import deliver_post_download_ad
from src.media_bot.services.job_service import (
    estimate_compressed_size_mb,
    format_large_file_progress,
    probe_media_duration,
)
from src.media_bot.services.quota_service import record_successful_download
from src.media_bot.workers.cleanup import safe_delete_file


def run_ffmpeg_monitored(
    cmd: List[str],
    total_duration: float,
    start_pct: int,
    end_pct: int,
    on_progress: Callable[[int], None],
) -> int:
    on_progress(start_pct)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except Exception:
        return 1

    last_call_time = time.time()
    last_pct = start_pct

    if proc.stdout:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                val = line.split("=", 1)[1].strip()
                if val.isdigit() and total_duration > 0:
                    cur_sec = float(val) / 1_000_000.0
                    ratio = min(1.0, max(0.0, cur_sec / total_duration))
                    pct = int(start_pct + ratio * (end_pct - start_pct))
                    now = time.time()
                    if (now - last_call_time >= 2.0) and (pct >= last_pct + 3):
                        last_call_time = now
                        last_pct = pct
                        on_progress(pct)
            elif total_duration <= 0:
                now = time.time()
                if (now - last_call_time >= 2.5) and (last_pct < end_pct):
                    last_call_time = now
                    last_pct = min(end_pct, last_pct + 12)
                    on_progress(last_pct)

    return proc.wait()


def extract_audio_fast(
    file_path: str,
    audio_path: str,
    total_duration: float,
    on_progress: Callable[[int], None],
) -> bool:
    on_progress(25)
    # 1. Try fast direct stream copy first (takes <0.2s for AAC streams)
    res = subprocess.run(
        ["ffmpeg", "-i", file_path, "-vn", "-c:a", "copy", audio_path, "-y"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if res.returncode == 0:
        on_progress(85)
        return True

    # 2. If stream copy fails (e.g. YouTube Opus/WebM audio), transcode to AAC fast
    cmd = [
        "ffmpeg",
        "-i",
        file_path,
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-preset",
        "ultrafast",
        "-threads",
        "0",
        "-progress",
        "pipe:1",
        audio_path,
        "-y",
    ]
    code = run_ffmpeg_monitored(
        cmd,
        total_duration,
        start_pct=30,
        end_pct=85,
        on_progress=on_progress,
    )
    return code == 0


def handle_large_file_choice(
    cfg: Dict[str, Any],
    conn: Any,
    update: Dict[str, Any],
) -> None:
    raw_cq = (update.get("raw") or {}).get("callback_query", {}) if isinstance(update.get("raw"), dict) else {}
    cb_data = update.get("callback_data") or raw_cq.get("data", "")
    cq_id = update.get("callback_query_id") or raw_cq.get("id")
    user_id = update.get("user_id") or (raw_cq.get("from") or {}).get("id")
    chat_id = update.get("chat_id") or ((raw_cq.get("message") or {}).get("chat") or {}).get("id") or user_id
    msg_id = update.get("message_id") or (raw_cq.get("message") or {}).get("message_id")
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    parts = cb_data.split(":")
    if len(parts) < 3:
        answer_callback_query(bot_token, cq_id, "درخواست نامعتبر است.")
        return

    action = parts[1]  # "audio", "compress", "original"
    try:
        job_id = int(parts[2])
    except ValueError:
        answer_callback_query(bot_token, cq_id, "شناسه نامعتبر است.")
        return

    job = get_job(conn, database_url, job_id)
    if not job:
        answer_callback_query(bot_token, cq_id, "تسک یافت نشد یا منقضی شده است.", show_alert=True)
        return

    payload = job.get("payload") or {}
    file_path = payload.get("saved_file_path")
    title = payload.get("title", "Media")
    duration = payload.get("duration")
    width = payload.get("width")
    height = payload.get("height")
    bot_username = cfg.get("BOT_USERNAME", "")
    bot_tag = f"@{bot_username}" if bot_username else ""

    if not file_path or not os.path.exists(file_path):
        answer_callback_query(
            bot_token,
            cq_id,
            "فایل مدیا منقضی یا حذف شده است. لطفا لینک را مجددا ارسال کنید.",
            show_alert=True,
        )
        return

    is_grp = bool(chat_id != user_id)
    target_id = chat_id if is_grp else user_id

    # 1. User wants original file (>50MB) -> Requires VIP
    if action == "original":
        q_status = get_and_reset_daily_quota(conn, database_url, target_id, is_group=is_grp)
        if not q_status.get("is_vip"):
            answer_callback_query(
                bot_token,
                cq_id,
                "این گزینه مخصوص اعضای دارای اشتراک ویژه است! لطفا ابتدا اشتراک ویژه تهیه نمایید.",
                show_alert=True,
            )
            return

        answer_callback_query(bot_token, cq_id, "اشتراک ویژه تایید شد. در حال ارسال فایل اصلی...")
        if msg_id:
            try:
                edit_message_text(
                    bot_token,
                    chat_id,
                    msg_id,
                    format_large_file_progress(title, action="upload", percent=70, locale=locale),
                )
            except Exception:
                pass
        caption = f"<b>{title}</b>\n\n⭐️ نسخه کیفیت اصلی (اشتراک ویژه)\n\n{bot_tag}".strip()
        send_chat_action(bot_token, chat_id, "upload_video")
        res = send_video(
            bot_token,
            chat_id,
            video_path=file_path,
            caption=caption,
            duration=duration,
            width=width,
            height=height,
        )
        if not res.get("ok"):
            send_document(bot_token, chat_id, document_path=file_path, caption=caption)

        if msg_id:
            try:
                delete_message(bot_token, chat_id, msg_id)
            except Exception:
                pass
        safe_delete_file(file_path)
        complete_job(conn, database_url, job_id, {"status": "sent", "mode": "original"})
        try:
            record_successful_download(conn, database_url, user_id, chat_id, payload.get("platform", "media"), is_group=is_grp)
        except Exception:
            pass
        return

    # 2. User chooses audio extraction (Free, Fast)
    elif action == "audio":
        answer_callback_query(bot_token, cq_id, "در حال استخراج و آماده سازی فایل صوتی...")
        total_duration = float(duration) if duration else probe_media_duration(file_path)
        audio_path = os.path.splitext(file_path)[0] + ".m4a"

        def on_audio_progress(pct: int) -> None:
            if msg_id:
                try:
                    edit_message_text(
                        bot_token,
                        chat_id,
                        msg_id,
                        format_large_file_progress(title, action="audio", percent=pct, locale=locale),
                    )
                except Exception:
                    pass

        try:
            success = extract_audio_fast(
                file_path,
                audio_path,
                total_duration,
                on_progress=on_audio_progress,
            )
            if not success:
                if msg_id:
                    try:
                        edit_message_text(
                            bot_token,
                            chat_id,
                            msg_id,
                            "❌ خطا در استخراج صوت. لطفا مجددا تلاش کنید.",
                        )
                    except Exception:
                        pass
                answer_callback_query(bot_token, cq_id, "خطا در استخراج فایل صوتی.", show_alert=True)
                return

            if msg_id:
                try:
                    edit_message_text(
                        bot_token,
                        chat_id,
                        msg_id,
                        format_large_file_progress(title, action="upload", percent=88, locale=locale),
                    )
                except Exception:
                    pass
            caption = f"<b>{title}</b>\n\n🎙 نسخه صوتی با کیفیت اصلی\n\n{bot_tag}".strip()
            send_chat_action(bot_token, chat_id, "upload_document")
            send_audio(
                bot_token,
                chat_id,
                audio_path=audio_path,
                caption=caption,
                title=title,
                duration=int(total_duration) if total_duration else None,
            )
            safe_delete_file(audio_path)
            safe_delete_file(file_path)
            if msg_id:
                try:
                    delete_message(bot_token, chat_id, msg_id)
                except Exception:
                    pass
            complete_job(conn, database_url, job_id, {"status": "sent", "mode": "audio"})
            try:
                record_successful_download(conn, database_url, user_id, chat_id, payload.get("platform", "media"), is_group=is_grp)
                deliver_post_download_ad(cfg, conn, chat_id, user_id, is_vip=False)
            except Exception:
                pass
        except Exception as e:
            if msg_id:
                try:
                    edit_message_text(
                        bot_token,
                        chat_id,
                        msg_id,
                        f"❌ خطا در استخراج فایل صوتی: {e}",
                    )
                except Exception:
                    pass
            answer_callback_query(bot_token, cq_id, f"خطا در استخراج صدا: {e}", show_alert=True)
        return

    # 3. User chooses compressed video (<50MB)
    elif action == "compress":
        total_duration = float(duration) if duration else probe_media_duration(file_path)
        file_size = payload.get("file_size") or (os.path.getsize(file_path) if os.path.exists(file_path) else 0)
        estimated_mb = payload.get("estimated_compressed_mb") or estimate_compressed_size_mb(file_size, total_duration)

        if estimated_mb > 50.0:
            answer_callback_query(
                bot_token,
                cq_id,
                f"حجم این فایل حتی پس از فشرده سازی حدود {estimated_mb} مگابایت خواهد بود و امکان کاهش به زیر 50 مگابایت وجود ندارد. لطفا اشتراک ویژه تهیه نمایید.",
                show_alert=True,
            )
            return

        answer_callback_query(
            bot_token,
            cq_id,
            "در حال فشرده سازی ویدیو به زیر 50 مگابایت... لطفا صبور باشید.",
        )
        compressed_path = os.path.splitext(file_path)[0] + "_compressed.mp4"

        def on_video_progress(pct: int) -> None:
            if msg_id:
                try:
                    edit_message_text(
                        bot_token,
                        chat_id,
                        msg_id,
                        format_large_file_progress(title, action="compress", percent=pct, locale=locale),
                    )
                    send_chat_action(bot_token, chat_id, "upload_video")
                except Exception:
                    pass

        cmd = [
            "ffmpeg",
            "-i",
            file_path,
            "-vcodec",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-tune",
            "fastdecode",
            "-vf",
            "scale=-2:trunc(min(480\\,ih)/2)*2",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "0",
            "-acodec",
            "aac",
            "-b:a",
            "64k",
            "-progress",
            "pipe:1",
            compressed_path,
            "-y",
        ]
        try:
            ret = run_ffmpeg_monitored(
                cmd,
                total_duration,
                start_pct=20,
                end_pct=85,
                on_progress=on_video_progress,
            )
            if ret != 0:
                if msg_id:
                    try:
                        edit_message_text(
                            bot_token,
                            chat_id,
                            msg_id,
                            "❌ خطا در بهینه سازی ویدیو. لطفا مجددا تلاش کنید.",
                        )
                    except Exception:
                        pass
                answer_callback_query(bot_token, cq_id, "خطا در بهینه سازی ویدیو.", show_alert=True)
                return

            compressed_size = os.path.getsize(compressed_path) if os.path.exists(compressed_path) else 0
            if compressed_size > 52428800:
                safe_delete_file(compressed_path)
                c_mb = round(compressed_size / (1024 * 1024), 1)
                kb = large_file_options_keyboard(job_id, locale, allow_compress=False)
                if msg_id:
                    try:
                        edit_message_text(
                            bot_token,
                            chat_id,
                            msg_id,
                            f"⚠️ <b>امکان ارسال نسخه فشرده شده وجود ندارد!</b>\n\n"
                            f"🎬 عنوان: <b>{title}</b>\n"
                            f"📦 حجم پس از بهینه سازی: <b>{c_mb} مگابایت</b> (بیشتر از سقف 50 مگابایت)\n\n"
                            f"👑 به دلیل طولانی بودن یا کیفیت بالای ویدیو، حجم نسخه بهینه شده نیز از سقف 50 مگابایت بیشتر شد.\n\n"
                            f"برای دریافت این فایل، لطفا <b>اشتراک ویژه (VIP)</b> تهیه فرمایید یا از نسخه صوتی استفاده نمایید:",
                            reply_markup=kb,
                        )
                    except Exception:
                        pass
                answer_callback_query(
                    bot_token,
                    cq_id,
                    f"حجم فایل فشرده شده ({c_mb} مگابایت) بیشتر از سقف 50 مگابایت شد. تهیه اشتراک ویژه الزامی است.",
                    show_alert=True,
                )
                return

            if msg_id:
                try:
                    edit_message_text(
                        bot_token,
                        chat_id,
                        msg_id,
                        format_large_file_progress(title, action="upload", percent=88, locale=locale),
                    )
                except Exception:
                    pass
            caption = f"<b>{title}</b>\n\n🎬 نسخه بهینه شده (کم حجم)\n\n{bot_tag}".strip()
            send_chat_action(bot_token, chat_id, "upload_video")
            res = send_video(
                bot_token,
                chat_id,
                video_path=compressed_path,
                caption=caption,
                duration=int(total_duration) if total_duration else None,
            )
            if not res.get("ok"):
                send_document(bot_token, chat_id, document_path=compressed_path, caption=caption)

            safe_delete_file(compressed_path)
            safe_delete_file(file_path)
            if msg_id:
                try:
                    delete_message(bot_token, chat_id, msg_id)
                except Exception:
                    pass
            complete_job(conn, database_url, job_id, {"status": "sent", "mode": "compressed"})
            try:
                record_successful_download(conn, database_url, user_id, chat_id, payload.get("platform", "media"), is_group=is_grp)
                deliver_post_download_ad(cfg, conn, chat_id, user_id, is_vip=False)
            except Exception:
                pass
        except Exception as e:
            if msg_id:
                try:
                    edit_message_text(
                        bot_token,
                        chat_id,
                        msg_id,
                        f"❌ خطا در فشرده سازی ویدیو: {e}",
                    )
                except Exception:
                    pass
            answer_callback_query(bot_token, cq_id, f"خطا در فشرده سازی ویدیو: {e}", show_alert=True)
        return
