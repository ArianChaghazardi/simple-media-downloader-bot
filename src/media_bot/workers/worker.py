"""
Functional background job worker.
Processes media download, recognition, and broadcast jobs with atomic leases.
Zero custom classes.
"""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from src.media_bot.bot_api.client import (
    delete_message,
    edit_message_text,
    send_audio,
    send_chat_action,
    send_document,
    send_media_group,
    send_message,
    send_photo,
    send_video,
)
from src.media_bot.bot_api.keyboards import large_file_options_keyboard
from src.media_bot.db.engine import close_connection, create_connection
from src.media_bot.db.repositories.jobs import (
    claim_next_job,
    complete_job,
    fail_job,
    recover_stale_jobs,
    update_job_status_and_payload,
)
from src.media_bot.db.repositories.users import get_and_reset_daily_quota
from src.media_bot.locales import t
from src.media_bot.logging_setup import get_logger
from src.media_bot.providers.instagram import download_instagram_media
from src.media_bot.providers.pinterest import download_pinterest_media
from src.media_bot.providers.reddit import download_reddit_media
from src.media_bot.providers.threads import download_threads_media
from src.media_bot.providers.tiktok import download_tiktok_media
from src.media_bot.providers.x_media import download_x_media
from src.media_bot.providers.youtube import download_youtube_media
from src.media_bot.services.job_service import (
    estimate_compressed_size_mb,
    format_job_status,
    probe_media_duration,
)
from src.media_bot.services.quota_service import record_successful_download
from src.media_bot.workers.cleanup import clean_expired_files, safe_delete_file

logger = get_logger("worker")


def execute_single_job(
    cfg: Dict[str, Any],
    conn: Any,
    job: Dict[str, Any],
) -> bool:
    job_id = job["id"]
    job_type = job["job_type"]
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    payload = job.get("payload", {})
    bot_token = cfg["BOT_TOKEN"]
    database_url = cfg["DATABASE_URL"]
    temp_dir = cfg["TEMP_DIR"]
    max_bytes = cfg.get("MAX_DOWNLOAD_BYTES", 104857600)
    ffmpeg_path = cfg.get("FFMPEG_PATH") or None
    cookies_path = cfg.get("YOUTUBE_COOKIES_PATH") or None
    proxy_url = cfg.get("PROXY_URL") or None
    locale = cfg.get("DEFAULT_LOCALE", "fa")

    logger.info("Executing job #%d (%s) for user %d", job_id, job_type, user_id)
    downloaded_file: Optional[str] = None
    keep_file: bool = False
    status_msg_id = payload.get("status_message_id")
    platform = payload.get("platform") or job_type.split("_")[0]

    # Provide immediate visual progress feedback (50%)
    if status_msg_id:
        try:
            edit_message_text(
                bot_token,
                chat_id,
                status_msg_id,
                format_job_status(
                    platform=platform,
                    step="downloading",
                    percent=50,
                    locale=locale,
                ),
            )
        except Exception:
            pass

    try:
        result: Dict[str, Any] = {}
        if job_type in ("youtube_download", "youtube_media"):
            url = payload.get("url", "")
            result = download_youtube_media(
                url,
                temp_dir,
                max_bytes,
                ffmpeg_path=ffmpeg_path,
                cookies_path=cookies_path,
                proxy_url=proxy_url,
            )

        elif job_type in ("x_download", "x_media"):
            url = payload.get("url", "")
            result = download_x_media(url, temp_dir, max_bytes)

        elif job_type in ("instagram_download", "instagram_media"):
            url = payload.get("url", "")
            result = download_instagram_media(url, temp_dir, max_bytes)

        elif job_type in ("tiktok_download", "tiktok_media"):
            url = payload.get("url", "")
            result = download_tiktok_media(url, temp_dir, max_bytes)

        elif job_type in ("pinterest_download", "pinterest_media"):
            url = payload.get("url", "")
            result = download_pinterest_media(url, temp_dir, max_bytes)

        elif job_type in ("threads_download", "threads_media"):
            url = payload.get("url", "")
            result = download_threads_media(url, temp_dir, max_bytes)

        elif job_type in ("reddit_download", "reddit_media"):
            url = payload.get("url", "")
            result = download_reddit_media(
                url,
                temp_dir,
                max_bytes,
                ffmpeg_path=ffmpeg_path,
                cookies_path=cookies_path,
                proxy_url=proxy_url,
            )

        else:
            fail_job(conn, database_url, job_id, f"Unknown job type: {job_type}", allow_retry=False)
            return False

        if not result.get("success"):
            err_msg = result.get("error_message", "Download error")
            logger.warning("Job #%d failed: %s", job_id, err_msg)
            fail_job(conn, database_url, job_id, err_msg, allow_retry=False)
            fail_text = t("job_failed", locale, reason=err_msg)
            if status_msg_id:
                try:
                    edit_message_text(bot_token, chat_id, status_msg_id, fail_text)
                except Exception:
                    send_message(bot_token, chat_id, fail_text)
            else:
                send_message(
                    bot_token,
                    chat_id,
                    fail_text,
                )
            return False

        # Visual progress update: Uploading / Delivering (85%)
        if status_msg_id:
            try:
                edit_message_text(
                    bot_token,
                    chat_id,
                    status_msg_id,
                    format_job_status(
                        platform=platform,
                        step="uploading",
                        percent=85,
                        locale=locale,
                    ),
                )
            except Exception:
                pass

        downloaded_file = result.get("file_path")
        file_paths = result.get("file_paths") or ([downloaded_file] if downloaded_file else [])
        title = result.get("title", "")
        bot_username = cfg.get("BOT_USERNAME", "")
        bot_tag = f"@{bot_username}" if bot_username else ""
        caption = f"<b>{title}</b>\n\n{bot_tag}".strip()

        # Send to Telegram based on media format
        ext = os.path.splitext(downloaded_file)[1].lower() if downloaded_file else ""
        file_size = (
            result.get("file_size")
            or (os.path.getsize(downloaded_file) if downloaded_file and os.path.exists(downloaded_file) else 0)
        )

        # Check VIP status for files > 50 MB
        is_grp = bool(chat_id != user_id)
        target_id = chat_id if is_grp else user_id
        q_status = get_and_reset_daily_quota(conn, database_url, target_id, is_group=is_grp)
        is_vip = q_status.get("is_vip", False)

        # 50 MB threshold for non-VIP users (52,428,800 bytes)
        if file_size > 52428800 and not is_vip:
            size_mb = round(file_size / (1024 * 1024), 1)
            duration = result.get("duration")
            if not duration:
                duration = probe_media_duration(downloaded_file)

            estimated_mb = estimate_compressed_size_mb(file_size, duration)
            can_compress = bool(estimated_mb <= 50.0)

            if can_compress:
                prompt_text = (
                    f"⚠️ <b>حجم فایل بیشتر از 50 مگابایت است!</b>\n\n"
                    f"🎬 عنوان: <b>{title}</b>\n"
                    f"📦 حجم مدیا: <b>{size_mb} مگابایت</b>\n"
                    f"📉 حجم تخمینی نسخه کم حجم: <b>{estimated_mb} مگابایت</b>\n\n"
                    f"👑 ارسال فایل های با کیفیت اصلی و بالای 50 مگابایت فقط برای <b>کاربران ویژه (VIP)</b> فعال است.\n\n"
                    f"شما می توانید با تهیه اشتراک ویژه این فایل را با کیفیت اصلی دریافت کنید، "
                    f"یا از گزینه های زیر (نسخه کم حجم یا صوتی) استفاده نمایید:"
                )
            else:
                prompt_text = (
                    f"⚠️ <b>حجم فایل بیشتر از 50 مگابایت است!</b>\n\n"
                    f"🎬 عنوان: <b>{title}</b>\n"
                    f"📦 حجم مدیا: <b>{size_mb} مگابایت</b>\n"
                    f"📉 حجم تخمینی پس از بهینه سازی: <b>{estimated_mb} مگابایت</b>\n\n"
                    f"👑 این فایل حتی پس از بهینه سازی نیز بیشتر از 50 مگابایت خواهد بود و امکان فشرده سازی به زیر 50 مگابایت وجود ندارد.\n\n"
                    f"برای دریافت این فایل با کیفیت اصلی، تهیه <b>اشتراک ویژه (VIP)</b> الزامی است. همچنین می توانید نسخه صوتی این مدیا را دریافت فرمایید:"
                )

            kb = large_file_options_keyboard(job_id, locale, allow_compress=can_compress)

            job_payload = dict(payload)
            job_payload.update(
                {
                    "saved_file_path": downloaded_file,
                    "title": title,
                    "file_size": file_size,
                    "duration": duration,
                    "width": result.get("width"),
                    "height": result.get("height"),
                    "estimated_compressed_mb": estimated_mb,
                    "can_compress": can_compress,
                }
            )
            update_job_status_and_payload(conn, database_url, job_id, "awaiting_choice", job_payload)

            if status_msg_id:
                try:
                    edit_message_text(bot_token, chat_id, status_msg_id, prompt_text, reply_markup=kb)
                except Exception:
                    send_message(bot_token, chat_id, prompt_text, reply_markup=kb)
            else:
                send_message(bot_token, chat_id, prompt_text, reply_markup=kb)

            keep_file = True
            logger.info("Job #%d paused: awaiting large file choice from user %d", job_id, user_id)
            return True

        # Trigger native Telegram uploading status
        if len(file_paths) > 1:
            try:
                send_chat_action(bot_token, chat_id, "upload_photo")
            except Exception:
                pass

            res = send_media_group(
                bot_token,
                chat_id,
                media_paths=file_paths,
                caption=caption,
            )
            if not res.get("ok"):
                logger.warning(
                    "send_media_group failed (%s), falling back to single photo",
                    res.get("description"),
                )
                res = send_photo(
                    bot_token,
                    chat_id,
                    photo_path=downloaded_file,
                    caption=caption,
                )
        else:
            action = "upload_video"
            if ext in (".mp3", ".m4a", ".ogg", ".wav", ".aac", ".flac"):
                action = "upload_voice"
            elif ext in (".jpg", ".jpeg", ".png", ".webp"):
                action = "upload_photo"
            elif ext in (".mp4", ".mov", ".mkv", ".webm"):
                action = "upload_video"
            else:
                action = "upload_document"

            try:
                send_chat_action(bot_token, chat_id, action)
            except Exception:
                pass

            if ext in (
                ".mp3",
                ".m4a",
                ".ogg",
                ".wav",
                ".aac",
                ".flac",
            ):
                res = send_audio(
                    bot_token,
                    chat_id,
                    audio_path=downloaded_file,
                    caption=caption,
                    title=title,
                    performer=result.get("performer"),
                    duration=result.get("duration"),
                )
            elif ext in (".jpg", ".jpeg", ".png", ".webp"):
                res = send_photo(
                    bot_token,
                    chat_id,
                    photo_path=downloaded_file,
                    caption=caption,
                )
            elif ext in (".mp4", ".mov", ".mkv", ".webm"):
                res = send_video(
                    bot_token,
                    chat_id,
                    video_path=downloaded_file,
                    caption=caption,
                    duration=result.get("duration"),
                    width=result.get("width"),
                    height=result.get("height"),
                )
            else:
                res = send_document(
                    bot_token,
                    chat_id,
                    document_path=downloaded_file,
                    caption=caption,
                )

        if not res.get("ok"):
            raw_desc = res.get("description", "Failed to upload media to Telegram")
            if "Request Entity Too Large" in raw_desc or res.get("error_code") == 413:
                size_mb = round(file_size / (1024 * 1024), 1) if file_size else 50
                err_desc = (
                    f"حجم این فایل ({size_mb} مگابایت) بیشتر از سقف مجاز تلگرام (50 مگابایت) است. "
                    f"سرورهای رسمی تلگرام به ربات ها اجازه ارسال فایل های بالاتر از 50 مگابایت را نمی دهند."
                )
            else:
                err_desc = raw_desc
            logger.error("Job #%d upload failed: %s", job_id, err_desc)
            fail_job(conn, database_url, job_id, err_desc, allow_retry=False)
            fail_text = t("job_failed", locale, reason=err_desc)
            if status_msg_id:
                try:
                    edit_message_text(bot_token, chat_id, status_msg_id, fail_text)
                except Exception:
                    send_message(bot_token, chat_id, fail_text)
            else:
                send_message(
                    bot_token,
                    chat_id,
                    fail_text,
                )
            return False

        complete_job(conn, database_url, job_id, {"status": "sent", "title": title})
        logger.info("Job #%d completed successfully", job_id)

        # Cleanly delete the temporary progress status message now that media is delivered
        if status_msg_id:
            try:
                delete_message(bot_token, chat_id, status_msg_id)
            except Exception:
                pass

        try:
            platform_name = job_type.split("_")[0]
            is_grp = bool(chat_id != user_id)
            record_successful_download(
                conn, database_url, user_id, chat_id, platform_name, is_group=is_grp
            )
        except Exception as e:
            logger.error("Error recording download stats: %s", str(e))

        return True

    except Exception as e:
        logger.exception("Unexpected exception in job #%d: %s", job_id, str(e))
        fail_job(conn, database_url, job_id, str(e), allow_retry=False)
        send_message(
            bot_token,
            chat_id,
            t("job_failed", locale, reason="Internal error during processing"),
        )
        return False

    finally:
        if not keep_file:
            if downloaded_file:
                safe_delete_file(downloaded_file)
            for extra_p in (result.get("file_paths") if result else []) or []:
                if extra_p and extra_p != downloaded_file:
                    safe_delete_file(extra_p)


def _run_single_job_task(
    cfg: Dict[str, Any],
    job: Dict[str, Any],
) -> bool:
    """
    Worker task entrypoint executed inside a worker thread.
    Opens its own dedicated DB connection, executes the job, and ensures clean closure.
    """
    database_url = cfg["DATABASE_URL"]
    conn = create_connection(database_url)
    try:
        return execute_single_job(cfg, conn, job)
    finally:
        close_connection(conn)


def run_worker_cycle(
    cfg: Dict[str, Any],
    worker_id: Optional[str] = None,
    max_jobs: int = 5,
) -> int:
    if not worker_id:
        worker_id = f"worker_{os.getpid()}_{uuid.uuid4().hex[:6]}"

    database_url = cfg["DATABASE_URL"]
    conn = create_connection(database_url)
    processed = 0

    try:
        recover_stale_jobs(conn, database_url)
        clean_expired_files(cfg["TEMP_DIR"], cfg.get("FILE_RETENTION_HOURS", 2))

        max_concurrent = max(1, int(cfg.get("MAX_CONCURRENT_JOBS", 5)))
        batch_limit = min(max_jobs, max_concurrent)
        claimed_jobs: List[Dict[str, Any]] = []

        for _ in range(batch_limit):
            job = claim_next_job(
                conn,
                database_url,
                worker_id=worker_id,
                lease_seconds=cfg.get("JOB_TIMEOUT_SECONDS", 300),
            )
            if not job:
                break
            claimed_jobs.append(job)

        if not claimed_jobs:
            return 0

        if len(claimed_jobs) == 1:
            execute_single_job(cfg, conn, claimed_jobs[0])
            processed += 1
        else:
            with ThreadPoolExecutor(max_workers=len(claimed_jobs)) as executor:
                futures = [executor.submit(_run_single_job_task, cfg, j) for j in claimed_jobs]
                for f in futures:
                    try:
                        f.result()
                        processed += 1
                    except Exception as e:
                        logger.error("Error executing job in thread pool: %s", str(e))

    finally:
        close_connection(conn)

    return processed


def run_worker_loop(
    cfg: Dict[str, Any],
    interval_seconds: int = 1,
) -> None:
    max_concurrent = max(1, int(cfg.get("MAX_CONCURRENT_JOBS", 5)))
    worker_id_base = f"worker_{os.getpid()}_{uuid.uuid4().hex[:4]}"
    logger.info(
        "Starting multi-threaded media worker loop %s (concurrency=%d, poll_interval=%ds)",
        worker_id_base,
        max_concurrent,
        interval_seconds,
    )

    database_url = cfg["DATABASE_URL"]
    active_tasks: Dict[Any, Tuple[int, str, str]] = {}
    last_maintenance = 0.0

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        while True:
            try:
                now_ts = time.time()
                if now_ts - last_maintenance >= 30.0:
                    last_maintenance = now_ts
                    m_conn = create_connection(database_url)
                    try:
                        recover_stale_jobs(m_conn, database_url)
                        clean_expired_files(cfg["TEMP_DIR"], cfg.get("FILE_RETENTION_HOURS", 2))
                    finally:
                        close_connection(m_conn)

                done_futures = [f for f in active_tasks if f.done()]
                for f in done_futures:
                    jid, jtype, wid = active_tasks.pop(f)
                    try:
                        f.result()
                    except Exception as e:
                        logger.error("Job #%d (%s) worker thread raised error: %s", jid, jtype, str(e))

                available_slots = max_concurrent - len(active_tasks)
                if available_slots > 0:
                    claim_conn = create_connection(database_url)
                    try:
                        for _ in range(available_slots):
                            sub_wid = f"{worker_id_base}_{uuid.uuid4().hex[:4]}"
                            job = claim_next_job(
                                claim_conn,
                                database_url,
                                worker_id=sub_wid,
                                lease_seconds=cfg.get("JOB_TIMEOUT_SECONDS", 300),
                            )
                            if not job:
                                break

                            job_type = job.get("job_type", "")
                            future = executor.submit(_run_single_job_task, cfg, job)
                            active_tasks[future] = (job["id"], job_type, sub_wid)
                    finally:
                        close_connection(claim_conn)

            except Exception as e:
                logger.error("Error in worker loop iteration: %s", str(e))

            time.sleep(interval_seconds)
