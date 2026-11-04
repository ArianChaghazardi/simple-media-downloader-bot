"""
Functional job queue service.
Enforces queue limits, generates idempotency keys, and schedules media processing tasks.
Provides dynamic visual progress formatting without exposing queue IDs.
Zero custom classes.
"""

import hashlib
import subprocess
from typing import Any, Dict, Optional

from src.media_bot.db.repositories.jobs import count_pending_jobs, enqueue_job


def _make_idempotency_key(prefix: str, user_id: int, identifier: str) -> str:
    raw = f"{prefix}:{user_id}:{identifier.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def make_progress_bar(percent: int, length: int = 10) -> str:
    filled = max(0, min(length, int(round((percent / 100.0) * length))))
    empty = length - filled
    return "▰" * filled + "▱" * empty


def format_job_status(
    platform: str,
    step: str = "queued",
    percent: int = 20,
    locale: str = "fa",
) -> str:
    bar = make_progress_bar(percent)
    platform_key = (platform or "media").lower()

    if locale == "fa":
        names_fa = {
            "youtube": "یوتیوب (YouTube)",
            "instagram": "اینستاگرام (Instagram)",
            "x": "توییتر / ایکس (Twitter/X)",
            "twitter": "توییتر / ایکس (Twitter/X)",
            "tiktok": "تیک تاک (TikTok)",
            "pinterest": "پینترست (Pinterest)",
            "threads": "تردز (Threads)",
            "reddit": "ردیت (Reddit)",
        }
        plat_name = names_fa.get(platform_key, "مدیا")

        if step == "downloading":
            return (
                f"📥 <b>در حال پردازش و دانلود مدیا...</b>\n\n"
                f"🌐 پلتفرم: <b>{plat_name}</b>\n"
                f"🔄 وضعیت: <b>در حال دریافت بهترین کیفیت از سرور...</b>\n"
                f"📊 پیشرفت: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>لطفا کمی صبور باشید...</i>"
            )
        elif step == "uploading":
            return (
                f"🚀 <b>در حال ارسال فایل...</b>\n\n"
                f"🌐 پلتفرم: <b>{plat_name}</b>\n"
                f"🔄 وضعیت: <b>در حال آپلود و تحویل به تلگرام...</b>\n"
                f"📊 پیشرفت: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>ارسال تا چند لحظه دیگر انجام می شود...</i>"
            )
        else:  # queued
            return (
                f"⚡️ <b>درخواست شما با موفقیت ثبت شد!</b>\n\n"
                f"🌐 پلتفرم: <b>{plat_name}</b>\n"
                f"🔄 وضعیت: <b>در حال بررسی لینک و آماده سازی دانلود...</b>\n"
                f"📊 پیشرفت: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>لطفا چند لحظه صبور باشید...</i>"
            )
    else:
        names_en = {
            "youtube": "YouTube",
            "instagram": "Instagram",
            "x": "Twitter / X",
            "twitter": "Twitter / X",
            "tiktok": "TikTok",
            "pinterest": "Pinterest",
            "threads": "Threads",
            "reddit": "Reddit",
        }
        plat_name = names_en.get(platform_key, "Media")

        if step == "downloading":
            return (
                f"📥 <b>Processing & Downloading Media...</b>\n\n"
                f"🌐 Platform: <b>{plat_name}</b>\n"
                f"🔄 Status: <b>Downloading file from source...</b>\n"
                f"📊 Progress: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>Please wait a moment...</i>"
            )
        elif step == "uploading":
            return (
                f"🚀 <b>Uploading Media...</b>\n\n"
                f"🌐 Platform: <b>{plat_name}</b>\n"
                f"🔄 Status: <b>Uploading file to Telegram...</b>\n"
                f"📊 Progress: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>File will be sent shortly...</i>"
            )
        else:  # queued
            return (
                f"⚡️ <b>Request Received Successfully!</b>\n\n"
                f"🌐 Platform: <b>{plat_name}</b>\n"
                f"🔄 Status: <b>Analyzing link and preparing download...</b>\n"
                f"📊 Progress: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>Please wait a moment...</i>"
            )


def format_large_file_progress(
    title: str,
    action: str,
    percent: int = 50,
    locale: str = "fa",
) -> str:
    bar = make_progress_bar(percent)
    clean_title = title[:45] + "..." if len(title) > 45 else title

    if locale == "fa":
        if action == "audio":
            if percent < 40:
                status_desc = "در حال شروع جداسازی ترک صوتی..."
            elif percent < 80:
                status_desc = "در حال پردازش و استخراج صوت با کیفیت اصلی (M4A)..."
            else:
                status_desc = "استخراج صدا تکمیل شد، در حال نهایی سازی فایل..."
            return (
                f"🎙 <b>در حال آماده سازی و استخراج نسخه صوتی...</b>\n\n"
                f"🎬 عنوان: <b>{clean_title}</b>\n"
                f"🔄 وضعیت: <b>{status_desc}</b>\n"
                f"📊 پیشرفت: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>لطفا کمی صبور باشید...</i>"
            )
        elif action == "compress":
            if percent < 30:
                status_desc = "در حال شروع بهینه سازی و تنظیم ابعاد (480p)..."
            elif percent < 75:
                status_desc = "در حال فشرده سازی سریع و کاهش حجم به زیر 50MB..."
            else:
                status_desc = "فشرده سازی ویدیو رو به اتمام است..."
            return (
                f"🎬 <b>در حال بهینه سازی و فشرده سازی ویدیو...</b>\n\n"
                f"🎬 عنوان: <b>{clean_title}</b>\n"
                f"🔄 وضعیت: <b>{status_desc}</b>\n"
                f"📊 پیشرفت: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>این عملیات ممکن است چند لحظه طول بکشد، لطفا صبور باشید...</i>"
            )
        else:  # upload
            return (
                f"🚀 <b>در حال ارسال فایل به تلگرام...</b>\n\n"
                f"🎬 عنوان: <b>{clean_title}</b>\n"
                f"🔄 وضعیت: <b>در حال آپلود و تحویل مدیا به تلگرام...</b>\n"
                f"📊 پیشرفت: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>ارسال تا چند لحظه دیگر انجام می شود...</i>"
            )
    else:
        if action == "audio":
            status_desc_en = (
                "Starting audio track extraction..."
                if percent < 40
                else "Processing high-quality audio..."
                if percent < 80
                else "Finalizing audio delivery..."
            )
            return (
                f"🎙 <b>Extracting Audio Track...</b>\n\n"
                f"🎬 Title: <b>{clean_title}</b>\n"
                f"🔄 Status: <b>{status_desc_en}</b>\n"
                f"📊 Progress: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>Please wait a moment...</i>"
            )
        elif action == "compress":
            status_desc_en = (
                "Setting 480p resolution..."
                if percent < 30
                else "Compressing video below 50MB..."
                if percent < 75
                else "Finalizing compressed video..."
            )
            return (
                f"🎬 <b>Optimizing & Compressing Video...</b>\n\n"
                f"🎬 Title: <b>{clean_title}</b>\n"
                f"🔄 Status: <b>{status_desc_en}</b>\n"
                f"📊 Progress: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>This may take a few moments, please wait...</i>"
            )
        else:
            return (
                f"🚀 <b>Uploading to Telegram...</b>\n\n"
                f"🎬 Title: <b>{clean_title}</b>\n"
                f"🔄 Status: <b>Delivering media...</b>\n"
                f"📊 Progress: <code>[{bar}] {percent}%</code>\n\n"
                f"<i>Sending shortly...</i>"
            )



def create_download_job(
    conn: Any,
    database_url: str,
    platform: str,
    chat_id: int,
    user_id: int,
    url: str,
    max_queue_size: int = 50,
    status_message_id: Optional[int] = None,
    paid_with_coins: bool = False,
    quality: Optional[str] = None,
    format_spec: Optional[str] = None,
) -> Dict[str, Any]:
    pending = count_pending_jobs(conn, database_url)
    if pending >= max_queue_size:
        return {"ok": False, "error": "queue_full", "pending_jobs": pending}

    idemp_target = f"{url}:{quality}" if quality else url
    idemp_key = _make_idempotency_key(platform, user_id, idemp_target)
    payload: Dict[str, Any] = {
        "platform": platform,
        "url": url,
        "chat_id": chat_id,
        "user_id": user_id,
        "paid_with_coins": paid_with_coins,
    }
    if status_message_id is not None:
        payload["status_message_id"] = status_message_id
    if quality:
        payload["quality"] = quality
    if format_spec:
        payload["format_spec"] = format_spec

    job_id = enqueue_job(
        conn,
        database_url,
        idempotency_key=idemp_key,
        job_type=f"{platform}_download",
        chat_id=chat_id,
        user_id=user_id,
        payload=payload,
    )

    return {"ok": True, "job_id": job_id}


def probe_media_duration(file_path: str) -> float:
    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        val = res.stdout.strip() if res.stdout else ""
        return float(val) if val else 0.0
    except Exception:
        return 0.0


def estimate_compressed_size_mb(
    file_size_bytes: int,
    duration_sec: Optional[float] = None,
) -> float:
    orig_mb = file_size_bytes / (1024 * 1024)
    if duration_sec and duration_sec > 0:
        # At 480p CRF 28 with 64kbps audio, typical bitrate is ~500-600 kbps (~0.065 MB/sec)
        dur_mb = duration_sec * 0.065
        ratio_mb = orig_mb * 0.35
        estimated = max(dur_mb, min(ratio_mb, dur_mb * 1.4))
    else:
        estimated = orig_mb * 0.40

    return round(estimated, 1)


def format_live_download_progress(
    platform: str,
    percent: int,
    downloaded_bytes: int = 0,
    total_bytes: int = 0,
    speed_str: str = "",
    eta_str: str = "",
    locale: str = "fa",
) -> str:
    bar = make_progress_bar(percent)
    platform_key = (platform or "media").lower()

    if locale == "fa":
        names_fa = {
            "youtube": "یوتیوب (YouTube)",
            "instagram": "اینستاگرام (Instagram)",
            "x": "توییتر / ایکس (Twitter/X)",
            "twitter": "توییتر / ایکس (Twitter/X)",
            "tiktok": "تیک تاک (TikTok)",
            "pinterest": "پینترست (Pinterest)",
            "threads": "تردز (Threads)",
            "reddit": "ردیت (Reddit)",
        }
        plat_name = names_fa.get(platform_key, "مدیا")
        details = []

        if downloaded_bytes and total_bytes:
            dl_mb = downloaded_bytes / (1024 * 1024)
            tot_mb = total_bytes / (1024 * 1024)
            details.append(f"📦 حجم: <b>{dl_mb:.1f} از {tot_mb:.1f} مگابایت</b>")
        elif downloaded_bytes:
            dl_mb = downloaded_bytes / (1024 * 1024)
            details.append(f"📦 حجم دریافت شده: <b>{dl_mb:.1f} مگابایت</b>")

        if speed_str:
            spd = speed_str.strip().replace("MiB/s", "MB/s").replace("KiB/s", "KB/s")
            details.append(f"⚡️ سرعت دانلود: <b>{spd}</b>")

        if eta_str and eta_str != "Unknown":
            clean_eta = eta_str.strip()
            details.append(f"⏳ زمان باقیمانده: <b>{clean_eta}</b>")

        extra_info = "\n".join(details)
        if extra_info:
            extra_info = "\n" + extra_info + "\n"

        return (
            f"📥 <b>در حال دانلود از سرور...</b>\n\n"
            f"🌐 پلتفرم: <b>{plat_name}</b>\n"
            f"📊 پیشرفت: <code>[{bar}] {percent}%</code>\n"
            f"{extra_info}\n"
            f"<i>دانلود در جریان است، لطفا شکیبا باشید...</i>"
        )
    else:
        return (
            f"📥 <b>Downloading from server...</b>\n\n"
            f"📊 Progress: <code>[{bar}] {percent}%</code>\n\n"
            f"<i>Please wait a moment...</i>"
        )
