"""
Functional Reddit media provider.
Downloads Reddit videos and images using yt-dlp with FFmpeg audio/video muxing,
with fallback to RapidSave info endpoint.
Zero custom classes.
"""

import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yt_dlp

from src.media_bot.providers.url_validator import validate_url


def _download_via_rapidsave(
    url: str,
    output_dir: str,
    unique_token: str,
    max_bytes: int,
) -> Dict[str, Any]:
    api_url = "https://rapidsave.com/info"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(api_url, params={"url": url}, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {
                "success": False,
                "error_code": "rapidsave_error",
                "error_message": f"RapidSave HTTP {resp.status_code}",
            }

        html_text = resp.text
        # Extract title
        title_match = re.search(r"<h2>(.*?)</h2>", html_text, re.DOTALL)
        raw_title = title_match.group(1).strip() if title_match else "Reddit Video"
        clean_title = re.sub(r"<[^>]+>", "", raw_title).strip() or "Reddit Media"

        # Find direct download button href
        dl_matches = re.findall(
            r'href="([^"]+)"[^>]*class="[^"]*downloadbutton[^"]*"', html_text
        )
        if not dl_matches:
            # Fallback search for download links
            dl_matches = re.findall(
                r'href="(https?://[^"]+\.mp4[^"]*)"', html_text
            )

        if not dl_matches:
            return {
                "success": False,
                "error_code": "no_download_link",
                "error_message": "Could not locate video download link",
            }

        download_url = dl_matches[0]
        out_path_obj = Path(output_dir)
        out_path_obj.mkdir(parents=True, exist_ok=True)
        file_path = str(out_path_obj / f"reddit_{unique_token}.mp4")

        with requests.get(download_url, headers=headers, stream=True, timeout=30) as dl_resp:
            dl_resp.raise_for_status()
            downloaded = 0
            with open(file_path, "wb") as f:
                for chunk in dl_resp.iter_content(chunk_size=65536):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > max_bytes:
                            f.close()
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            return {
                                "success": False,
                                "error_code": "too_large",
                                "error_message": f"Media exceeds size limit ({downloaded} > {max_bytes})",
                            }
                        f.write(chunk)

        file_size = os.path.getsize(file_path)
        return {
            "success": True,
            "title": clean_title[:150],
            "file_path": file_path,
            "file_size": file_size,
        }

    except Exception as e:
        return {"success": False, "error_code": "fallback_failed", "error_message": str(e)}


def download_reddit_media(
    url: str,
    output_dir: str,
    max_bytes: int = 104857600,
    ffmpeg_path: Optional[str] = None,
    cookies_path: Optional[str] = None,
    proxy_url: Optional[str] = None,
) -> Dict[str, Any]:
    is_valid, platform, err = validate_url(url)
    if not is_valid or platform != "reddit":
        return {
            "success": False,
            "error_code": "invalid_url",
            "error_message": err or "Invalid Reddit URL",
        }

    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    unique_token = uuid.uuid4().hex[:12]
    out_tmpl = str(out_path_obj / f"reddit_{unique_token}_%(id)s.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        "outtmpl": out_tmpl,
        "format": "bestvideo+bestaudio/best",
        "max_filesize": max_bytes,
        "quiet": True,
        "no_warnings": True,
    }

    if cookies_path and os.path.isfile(cookies_path):
        ydl_opts["cookiefile"] = cookies_path
    elif os.path.isfile("data/cookies.txt"):
        ydl_opts["cookiefile"] = "data/cookies.txt"
    elif os.path.isfile("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    if proxy_url:
        ydl_opts["proxy"] = proxy_url

    if ffmpeg_path and os.path.exists(ffmpeg_path):
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return _download_via_rapidsave(url, output_dir, unique_token, max_bytes)

            file_path = ydl.prepare_filename(info)
            if not os.path.exists(file_path):
                candidates = list(out_path_obj.glob(f"reddit_{unique_token}_*"))
                if candidates:
                    file_path = str(candidates[0])
                else:
                    return _download_via_rapidsave(url, output_dir, unique_token, max_bytes)

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

            title = info.get("description", "") or info.get("title", "Reddit Media")
            clean_title = title[:150] if title else "Reddit Media"

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
        return _download_via_rapidsave(url, output_dir, unique_token, max_bytes)
