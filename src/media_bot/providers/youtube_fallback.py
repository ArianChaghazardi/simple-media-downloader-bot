import json
import logging
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("media_bot.youtube_fallback")


def get_fallback_api_urls() -> List[str]:
    """
    Returns configured fallback API URLs in order of priority.
    """
    urls: List[str] = []
    custom_url = os.environ.get("COBALT_API_URL") or os.environ.get("YOUTUBE_FALLBACK_API_URL")
    if custom_url:
        urls.append(custom_url.rstrip("/"))
    return urls


def is_fallback_available() -> bool:
    """
    Checks if a fallback API is configured.
    """
    return len(get_fallback_api_urls()) > 0


def fetch_youtube_oembed(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetches basic YouTube metadata using the official public oEmbed API.
    This endpoint never requires cookies or bot verification.
    """
    try:
        encoded_url = urllib.parse.quote(url)
        oembed_url = f"https://www.youtube.com/oembed?url={encoded_url}&format=json"
        req = urllib.request.Request(
            oembed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug("oEmbed metadata fetch failed for %s: %s", url, e)
    return None


def fetch_qualities_from_cobalt(
    url: str,
    api_url: str,
    threshold_mb: int = 50,
) -> Optional[Dict[str, Any]]:
    """
    Queries a Cobalt instance to check available qualities.
    """
    try:
        payload = json.dumps({
            "url": url,
            "videoQuality": "1080",
            "downloadMode": "auto",
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{api_url}/",
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "AhaMediaBot/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") in ("tunnel", "redirect", "picker", "success"):
                oembed = fetch_youtube_oembed(url) or {}
                title = oembed.get("title") or data.get("filename") or "ویدیو یوتیوب"
                thumbnail = oembed.get("thumbnail_url")

                options = [
                    {
                        "quality_id": "1080p",
                        "height": 1080,
                        "type": "video",
                        "size_mb": 150.0,
                        "size_label": "~150 MB",
                        "is_vip": 150.0 >= threshold_mb,
                        "btn_label": f"{'⭐️ ' if 150.0 >= threshold_mb else ''}1080p (~150 MB){' (اشتراک ویژه)' if 150.0 >= threshold_mb else ''}",
                        "format_spec": "cobalt:1080",
                    },
                    {
                        "quality_id": "720p",
                        "height": 720,
                        "type": "video",
                        "size_mb": 80.0,
                        "size_label": "~80 MB",
                        "is_vip": 80.0 >= threshold_mb,
                        "btn_label": f"{'⭐️ ' if 80.0 >= threshold_mb else ''}720p (~80 MB){' (اشتراک ویژه)' if 80.0 >= threshold_mb else ''}",
                        "format_spec": "cobalt:720",
                    },
                    {
                        "quality_id": "480p",
                        "height": 480,
                        "type": "video",
                        "size_mb": 45.0,
                        "size_label": "~45 MB",
                        "is_vip": 45.0 >= threshold_mb,
                        "btn_label": f"{'⭐️ ' if 45.0 >= threshold_mb else ''}480p (~45 MB){' (اشتراک ویژه)' if 45.0 >= threshold_mb else ''}",
                        "format_spec": "cobalt:480",
                    },
                    {
                        "quality_id": "audio",
                        "height": 0,
                        "type": "audio",
                        "size_mb": 15.0,
                        "size_label": "~15 MB",
                        "is_vip": False,
                        "btn_label": "🎵 صوتی MP3 (~15 MB)",
                        "format_spec": "cobalt:audio",
                    },
                ]

                return {
                    "success": True,
                    "title": title,
                    "duration": 0,
                    "thumbnail": thumbnail,
                    "options": options,
                    "is_fallback": True,
                }
    except Exception as e:
        logger.debug("Cobalt query failed for %s: %s", url, e)
    return None


def fetch_youtube_fallback_qualities(
    url: str,
    threshold_mb: int = 50,
) -> Optional[Dict[str, Any]]:
    """
    Attempts to fetch YouTube quality choices via configured fallback APIs.
    """
    for api_url in get_fallback_api_urls():
        res = fetch_qualities_from_cobalt(url, api_url, threshold_mb=threshold_mb)
        if res and res.get("success"):
            return res
    return None


def download_via_cobalt(
    url: str,
    output_dir: str,
    api_url: str,
    quality: Optional[str] = None,
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Downloads media using a Cobalt API instance.
    """
    is_audio = quality == "audio"
    quality_param = "1080"
    if quality in ("720p", "720"):
        quality_param = "720"
    elif quality in ("480p", "480"):
        quality_param = "480"
    elif quality in ("360p", "360"):
        quality_param = "360"

    payload_dict: Dict[str, Any] = {
        "url": url,
        "videoQuality": quality_param,
        "downloadMode": "audio" if is_audio else "auto",
    }
    if is_audio:
        payload_dict["audioFormat"] = "mp3"

    try:
        req = urllib.request.Request(
            f"{api_url}/",
            data=json.dumps(payload_dict).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "AhaMediaBot/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        stream_url = data.get("url")
        if not stream_url:
            return {
                "success": False,
                "error_code": "fallback_no_stream",
                "error_message": "سرویس جایگزین لینک دانلود معتبر بازنگرداند.",
            }

        os.makedirs(output_dir, exist_ok=True)
        token = uuid.uuid4().hex[:10]
        ext = "mp3" if is_audio else "mp4"
        out_path = os.path.join(output_dir, f"yt_fb_{token}.{ext}")

        # Download stream to file
        stream_req = urllib.request.Request(
            stream_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(stream_req, timeout=60) as s_resp, open(out_path, "wb") as f_out:
            total_size = int(s_resp.headers.get("content-length") or 0)
            downloaded = 0
            chunk_size = 1048576  # 1MB
            while True:
                chunk = s_resp.read(chunk_size)
                if not chunk:
                    break
                f_out.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total_size > 0:
                    try:
                        progress_callback({
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total_size,
                        })
                    except Exception:
                        pass

        file_size = os.path.getsize(out_path)
        oembed = fetch_youtube_oembed(url) or {}
        title = oembed.get("title") or "ویدیو یوتیوب"

        return {
            "success": True,
            "file_path": out_path,
            "file_size": file_size,
            "title": title,
            "duration": 0,
            "thumbnail": oembed.get("thumbnail_url"),
            "is_fallback": True,
        }
    except Exception as e:
        logger.error("Download via Cobalt failed: %s", e)
        return {
            "success": False,
            "error_code": "fallback_download_error",
            "error_message": f"خطا در دانلود از طریق سرویس جایگزین: {str(e)[:80]}",
        }


def download_youtube_fallback(
    url: str,
    output_dir: str,
    quality: Optional[str] = None,
    progress_callback: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Attempts to download media using any available fallback API.
    """
    for api_url in get_fallback_api_urls():
        res = download_via_cobalt(
            url=url,
            output_dir=output_dir,
            api_url=api_url,
            quality=quality,
            progress_callback=progress_callback,
        )
        if res and res.get("success"):
            return res
    return None
