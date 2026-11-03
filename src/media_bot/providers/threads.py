"""
Functional Threads (threads.net) media provider.
Downloads video and photo posts using curl-cffi with Chrome impersonation.
Zero custom classes.
"""

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict

from curl_cffi import requests

from src.media_bot.providers.url_validator import validate_url


def _find_key_in_obj(obj: Any, target_key: str):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == target_key:
                yield v
            yield from _find_key_in_obj(v, target_key)
    elif isinstance(obj, list):
        for item in obj:
            yield from _find_key_in_obj(item, target_key)


def download_threads_media(
    url: str,
    output_dir: str,
    max_bytes: int = 104857600,
) -> Dict[str, Any]:
    is_valid, platform, err = validate_url(url)
    if not is_valid or platform != "threads":
        return {
            "success": False,
            "error_code": "invalid_url",
            "error_message": err or "Invalid Threads URL",
        }

    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    unique_token = uuid.uuid4().hex[:12]

    try:
        resp = requests.get(url, impersonate="chrome", timeout=15)
        if resp.status_code != 200:
            return {
                "success": False,
                "error_code": "fetch_failed",
                "error_message": f"Threads HTTP {resp.status_code}",
            }

        html_text = resp.text
        media_url = None
        is_video = False

        # Look for video_versions in embedded JSON scripts
        script_matches = re.findall(
            r'<script type="application/json"[^>]*>(.*?)</script>', html_text
        )
        for s in script_matches:
            if "video_versions" in s:
                try:
                    data = json.loads(s)
                    for vv in _find_key_in_obj(data, "video_versions"):
                        if vv and isinstance(vv, list):
                            candidate_url = vv[0].get("url")
                            if candidate_url:
                                media_url = candidate_url
                                is_video = True
                                break
                    if media_url:
                        break
                except Exception:
                    continue

        # If no video found, search for og:video
        if not media_url:
            og_v = re.findall(r'<meta property="og:video" content="([^"]+)"', html_text)
            if og_v:
                media_url = og_v[0].replace("&amp;", "&")
                is_video = True

        # If still no video, look for photo (og:image)
        if not media_url:
            og_i = re.findall(r'<meta property="og:image" content="([^"]+)"', html_text)
            if og_i:
                media_url = og_i[0].replace("&amp;", "&")
                is_video = False

        if not media_url:
            return {
                "success": False,
                "error_code": "no_media_found",
                "error_message": "Could not find media in this Threads post",
            }

        title = "Threads Post"
        desc_matches = re.findall(
            r'<meta property="og:description" content="([^"]+)"', html_text
        )
        if desc_matches:
            title = desc_matches[0].strip()
        clean_title = title[:150].strip() or "Threads Media"

        ext = ".mp4" if is_video else ".jpg"
        file_path = str(out_path_obj / f"threads_{unique_token}{ext}")

        dl_resp = requests.get(media_url, impersonate="chrome", timeout=30)
        if dl_resp.status_code != 200:
            return {
                "success": False,
                "error_code": "media_download_error",
                "error_message": f"Media download HTTP {dl_resp.status_code}",
            }

        content_bytes = dl_resp.content
        if len(content_bytes) > max_bytes:
            return {
                "success": False,
                "error_code": "too_large",
                "error_message": f"Media exceeds size limit ({len(content_bytes)} > {max_bytes})",
            }

        with open(file_path, "wb") as f:
            f.write(content_bytes)

        file_size = len(content_bytes)
        return {
            "success": True,
            "title": clean_title,
            "file_path": file_path,
            "file_size": file_size,
        }

    except Exception as e:
        return {"success": False, "error_code": "download_failed", "error_message": str(e)}
