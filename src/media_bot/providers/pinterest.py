"""
Functional Pinterest media provider.
Downloads Pinterest videos using yt-dlp, and Pinterest high-resolution photos
via oEmbed and direct CDN original image extraction.
Zero custom classes.
"""

import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict

import requests
import yt_dlp

from src.media_bot.providers.url_validator import validate_url


def _unshorten_pinterest_url(url: str) -> str:
    if "pin.it" in url:
        try:
            resp = requests.head(
                url,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.url and "pinterest.com/pin/" in resp.url:
                return resp.url
        except Exception:
            pass
    return url


def _download_pinterest_photo_via_oembed(
    url: str,
    output_dir: str,
    unique_token: str,
    max_bytes: int,
) -> Dict[str, Any]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    oembed_url = f"https://www.pinterest.com/oembed.json?url={url}"
    try:
        resp = requests.get(oembed_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {
                "success": False,
                "error_code": "oembed_error",
                "error_message": f"Pinterest oEmbed HTTP {resp.status_code}",
            }

        data = resp.json()
        thumb = data.get("thumbnail_url")
        if not thumb:
            return {
                "success": False,
                "error_code": "no_image_found",
                "error_message": "No image URL returned by Pinterest",
            }

        title = data.get("title") or "Pinterest Image"
        if not title.strip():
            author = data.get("author_name") or ""
            title = f"Pinterest Pin by {author}".strip() if author else "Pinterest Pin"
        clean_title = title[:150].strip()

        # Try original resolution first, then 736x, then original thumb
        candidate_urls = [
            thumb.replace("/236x/", "/originals/"),
            thumb.replace("/236x/", "/736x/"),
            thumb,
        ]

        target_img_url = None
        for cand in candidate_urls:
            try:
                head_resp = requests.head(cand, headers=headers, timeout=8)
                if head_resp.status_code == 200:
                    target_img_url = cand
                    break
            except Exception:
                continue

        if not target_img_url:
            target_img_url = thumb

        out_path_obj = Path(output_dir)
        out_path_obj.mkdir(parents=True, exist_ok=True)

        ext = ".jpg"
        if ".png" in target_img_url.lower():
            ext = ".png"
        elif ".webp" in target_img_url.lower():
            ext = ".webp"

        pin_id_match = re.search(r"/pin/(\d+)", url)
        pin_id = pin_id_match.group(1) if pin_id_match else "pin"
        file_path = str(out_path_obj / f"pin_{unique_token}_{pin_id}{ext}")

        with requests.get(target_img_url, headers=headers, stream=True, timeout=25) as dl_resp:
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
                                "error_message": f"Image exceeds size limit ({downloaded} > {max_bytes})",
                            }
                        f.write(chunk)

        file_size = os.path.getsize(file_path)
        return {
            "success": True,
            "title": clean_title,
            "file_path": file_path,
            "file_size": file_size,
        }

    except Exception as e:
        return {"success": False, "error_code": "download_failed", "error_message": str(e)}


def download_pinterest_media(
    url: str,
    output_dir: str,
    max_bytes: int = 104857600,
) -> Dict[str, Any]:
    is_valid, platform, err = validate_url(url)
    if not is_valid or platform != "pinterest":
        return {
            "success": False,
            "error_code": "invalid_url",
            "error_message": err or "Invalid Pinterest URL",
        }

    canonical_url = _unshorten_pinterest_url(url)
    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    unique_token = uuid.uuid4().hex[:12]
    out_tmpl = str(out_path_obj / f"pin_{unique_token}_%(id)s.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        "outtmpl": out_tmpl,
        "format": "best[ext=mp4]/best",
        "max_filesize": max_bytes,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical_url, download=True)
            if not info:
                return _download_pinterest_photo_via_oembed(
                    canonical_url, output_dir, unique_token, max_bytes
                )

            file_path = ydl.prepare_filename(info)
            if not os.path.exists(file_path):
                candidates = list(out_path_obj.glob(f"pin_{unique_token}_*"))
                if candidates:
                    file_path = str(candidates[0])
                else:
                    return _download_pinterest_photo_via_oembed(
                        canonical_url, output_dir, unique_token, max_bytes
                    )

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

            title = info.get("description", "") or info.get("title", "Pinterest Video")
            clean_title = title[:150] if title else "Pinterest Video"

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
        # Fallback to photo extraction via oEmbed and direct CDN original
        return _download_pinterest_photo_via_oembed(
            canonical_url, output_dir, unique_token, max_bytes
        )
