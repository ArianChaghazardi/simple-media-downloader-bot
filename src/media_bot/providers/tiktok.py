"""
Functional TikTok media provider.
Downloads TikTok videos using yt-dlp with Chrome impersonation,
with automatic fallback to TikWM API for watermark-free videos.
Zero custom classes.
"""

import os
import uuid
from pathlib import Path
from typing import Any, Dict

import requests
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

from src.media_bot.providers.url_validator import validate_url


def _download_via_tikwm(
    url: str,
    output_dir: str,
    unique_token: str,
    max_bytes: int,
) -> Dict[str, Any]:
    api_url = f"https://www.tikwm.com/api/?url={url}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {
                "success": False,
                "error_code": "api_error",
                "error_message": f"TikWM HTTP {resp.status_code}",
            }

        res_data = resp.json()
        if res_data.get("code") != 0 or not res_data.get("data"):
            msg = res_data.get("msg", "Failed to parse TikTok video")
            return {"success": False, "error_code": "parse_failed", "error_message": msg}

        item = res_data["data"]
        play_url = item.get("play") or item.get("hdplay") or item.get("wmplay")
        if not play_url:
            return {
                "success": False,
                "error_code": "no_media_url",
                "error_message": "No direct video URL returned",
            }

        title = item.get("title") or "TikTok Video"
        clean_title = title[:150].strip()
        duration = int(item.get("duration") or 0)

        out_path_obj = Path(output_dir)
        out_path_obj.mkdir(parents=True, exist_ok=True)
        file_path = str(out_path_obj / f"tt_{unique_token}_{item.get('id', 'video')}.mp4")

        with requests.get(play_url, headers=headers, stream=True, timeout=30) as dl_resp:
            dl_resp.raise_for_status()
            downloaded_bytes = 0
            with open(file_path, "wb") as f:
                for chunk in dl_resp.iter_content(chunk_size=65536):
                    if chunk:
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > max_bytes:
                            f.close()
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            return {
                                "success": False,
                                "error_code": "too_large",
                                "error_message": f"Media exceeds size limit ({downloaded_bytes} > {max_bytes})",
                            }
                        f.write(chunk)

        file_size = os.path.getsize(file_path)
        return {
            "success": True,
            "title": clean_title,
            "file_path": file_path,
            "duration": duration,
            "file_size": file_size,
        }
    except Exception as e:
        return {"success": False, "error_code": "fallback_failed", "error_message": str(e)}


def download_tiktok_media(
    url: str,
    output_dir: str,
    max_bytes: int = 104857600,
) -> Dict[str, Any]:
    is_valid, platform, err = validate_url(url)
    if not is_valid or platform != "tiktok":
        return {
            "success": False,
            "error_code": "invalid_url",
            "error_message": err or "Invalid TikTok URL",
        }

    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    unique_token = uuid.uuid4().hex[:12]
    out_tmpl = str(out_path_obj / f"tt_{unique_token}_%(id)s.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        "outtmpl": out_tmpl,
        "format": "best[ext=mp4]/best",
        "max_filesize": max_bytes,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
    except Exception:
        pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return _download_via_tikwm(url, output_dir, unique_token, max_bytes)

            file_path = ydl.prepare_filename(info)
            if not os.path.exists(file_path):
                candidates = list(out_path_obj.glob(f"tt_{unique_token}_*"))
                if candidates:
                    file_path = str(candidates[0])
                else:
                    return _download_via_tikwm(url, output_dir, unique_token, max_bytes)

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

            title = info.get("description", "") or info.get("title", "TikTok Video")
            clean_title = title[:150] if title else "TikTok Video"

            return {
                "success": True,
                "title": clean_title,
                "file_path": file_path,
                "duration": info.get("duration", 0),
                "width": info.get("width"),
                "height": info.get("height"),
                "file_size": file_size,
            }

    except Exception:
        # On yt-dlp download/bot error, fallback to TikWM API
        return _download_via_tikwm(url, output_dir, unique_token, max_bytes)
