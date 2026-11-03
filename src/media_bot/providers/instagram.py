"""
Functional Instagram media provider using yt-dlp.
Zero custom classes.
"""

import os
import uuid
from pathlib import Path
from typing import Any, Dict

import yt_dlp

from src.media_bot.providers.url_validator import validate_url


def download_instagram_media(
    url: str,
    output_dir: str,
    max_bytes: int = 104857600,
) -> Dict[str, Any]:
    is_valid, platform, err = validate_url(url)
    if not is_valid or platform != "instagram":
        return {
            "success": False,
            "error_code": "invalid_url",
            "error_message": err or "Invalid Instagram URL",
        }

    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    unique_token = uuid.uuid4().hex[:12]
    out_tmpl = str(out_path_obj / f"ig_{unique_token}_%(id)s.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        "outtmpl": out_tmpl,
        "format": "best[ext=mp4]/best",
        "max_filesize": max_bytes,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return {
                    "success": False,
                    "error_code": "no_media",
                    "error_message": "Could not access Instagram media",
                }

            file_path = ydl.prepare_filename(info)
            if not os.path.exists(file_path):
                candidates = list(out_path_obj.glob(f"ig_{unique_token}_*"))
                if candidates:
                    file_path = str(candidates[0])
                else:
                    return {
                        "success": False,
                        "error_code": "file_missing",
                        "error_message": "Downloaded file not found on disk",
                    }

            file_size = os.path.getsize(file_path)
            if file_size > max_bytes:
                try:
                    os.remove(file_path)
                except Exception:
                    pass
                return {
                    "success": False,
                    "error_code": "too_large",
                    "error_message": f"Media exceeds size limit ({file_size} > {max_bytes})",
                }

            title = info.get("description", "") or info.get("title", "Instagram Post")
            clean_title = title[:150] if title else "Instagram Reel/Post"

            return {
                "success": True,
                "title": clean_title,
                "file_path": file_path,
                "duration": info.get("duration", 0),
                "width": info.get("width"),
                "height": info.get("height"),
                "file_size": file_size,
            }

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "login" in msg.lower() or "private" in msg.lower():
            code = "private_account"
            msg = "This post is from a private account or requires login."
        else:
            code = "download_error"
        return {"success": False, "error_code": code, "error_message": msg}
    except Exception as e:
        return {"success": False, "error_code": "unknown_error", "error_message": str(e)}
