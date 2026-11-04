"""
Functional X (Twitter) media provider using yt-dlp and direct CDN syndication.
Downloads single/multiple high-resolution photos and native videos.
Zero custom classes.
"""

import json
import os
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import yt_dlp

from src.media_bot.providers.url_validator import validate_url


def extract_tweet_id(url: str) -> Optional[str]:
    match = re.search(r"(?:twitter\.com|x\.com)/(?:[^/]+/status(?:es)?|i/status)/(\d+)", url)
    return match.group(1) if match else None


def fetch_tweet_syndication(twid: str) -> Optional[Dict[str, Any]]:
    url = f"https://cdn.syndication.twimg.com/tweet-result?id={twid}&token=x"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def _download_x_photos(
    data: Dict[str, Any],
    twid: str,
    output_dir: str,
    max_bytes: int,
    unique_token: str,
) -> Optional[Dict[str, Any]]:
    photos = data.get("photos", [])
    if not photos:
        for item in data.get("mediaDetails", []):
            if item.get("type") == "photo" and item.get("media_url_https"):
                photos.append({"url": item.get("media_url_https")})

    if not photos:
        return None

    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)

    downloaded_paths = []
    total_bytes = 0
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    for idx, p in enumerate(photos):
        p_url = p.get("url")
        if not p_url:
            continue
        orig_url = f"{p_url}?name=orig"
        out_file = out_path_obj / f"x_{unique_token}_{twid}_{idx}.jpg"
        try:
            img_req = urllib.request.Request(orig_url, headers=headers)
            with urllib.request.urlopen(img_req, timeout=20) as img_resp:
                img_data = img_resp.read()
                total_bytes += len(img_data)
                if total_bytes > max_bytes:
                    for path_to_del in downloaded_paths:
                        try:
                            os.remove(path_to_del)
                        except Exception:
                            pass
                    return {
                        "success": False,
                        "error_code": "too_large",
                        "error_message": f"Media exceeds size limit ({total_bytes} > {max_bytes})",
                    }
                with open(out_file, "wb") as f:
                    f.write(img_data)
                downloaded_paths.append(str(out_file))
        except Exception:
            continue

    if not downloaded_paths:
        return None

    raw_text = data.get("text", "")
    clean_title = re.sub(r"https?://\S+", "", raw_text).strip()
    user_name = data.get("user", {}).get("name", "")
    if not clean_title and user_name:
        clean_title = f"Post by {user_name}"
    elif not clean_title:
        clean_title = "X Photo"
    clean_title = clean_title[:150]

    return {
        "success": True,
        "title": clean_title,
        "file_path": downloaded_paths[0],
        "file_paths": downloaded_paths,
        "file_size": total_bytes,
        "media_type": "photo" if len(downloaded_paths) == 1 else "photos",
    }


def _download_x_video_from_syndication(
    data: Dict[str, Any],
    twid: str,
    output_dir: str,
    max_bytes: int,
    unique_token: str,
) -> Optional[Dict[str, Any]]:
    vid_info = data.get("video")
    if not vid_info:
        return None

    variants = vid_info.get("variants", [])
    mp4_variants = [v for v in variants if v.get("type") == "video/mp4" and v.get("src")]
    if not mp4_variants:
        return None

    def _variant_score(v: Dict[str, Any]) -> int:
        src = v.get("src", "")
        match = re.search(r"/(\d+)x(\d+)/", src)
        if match:
            return int(match.group(1)) * int(match.group(2))
        return 0

    best_variant = max(mp4_variants, key=_variant_score)
    video_url = best_variant.get("src")
    if not video_url:
        return None

    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    out_file = out_path_obj / f"x_{unique_token}_{twid}.mp4"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        v_req = urllib.request.Request(video_url, headers=headers)
        with urllib.request.urlopen(v_req, timeout=30) as v_resp:
            v_data = v_resp.read()
            file_size = len(v_data)
            if file_size > max_bytes:
                return {
                    "success": False,
                    "error_code": "too_large",
                    "error_message": f"Media exceeds size limit ({file_size} > {max_bytes})",
                }
            with open(out_file, "wb") as f:
                f.write(v_data)

        raw_text = data.get("text", "")
        clean_title = re.sub(r"https?://\S+", "", raw_text).strip()
        user_name = data.get("user", {}).get("name", "")
        if not clean_title and user_name:
            clean_title = f"Video by {user_name}"
        elif not clean_title:
            clean_title = "X Video"
        clean_title = clean_title[:150]

        return {
            "success": True,
            "title": clean_title,
            "file_path": str(out_file),
            "file_paths": [str(out_file)],
            "file_size": file_size,
            "duration": int(vid_info.get("durationMs", 0) / 1000),
            "media_type": "video",
        }
    except Exception:
        if out_file.exists():
            try:
                os.remove(out_file)
            except Exception:
                pass
        return None


def download_x_media(
    url: str,
    output_dir: str,
    max_bytes: int = 104857600,
) -> Dict[str, Any]:
    is_valid, platform, err = validate_url(url)
    if not is_valid or platform != "x":
        return {
            "success": False,
            "error_code": "invalid_url",
            "error_message": err or "Invalid X/Twitter URL",
        }

    twid = extract_tweet_id(url)
    unique_token = uuid.uuid4().hex[:12]
    tweet_data = fetch_tweet_syndication(twid) if twid else None

    # Check if tweet contains photos without video
    if tweet_data:
        has_video = bool(
            "video" in tweet_data
            or any(
                m.get("type") in ("video", "animated_gif")
                for m in tweet_data.get("mediaDetails", [])
            )
        )
        has_photos = bool(
            tweet_data.get("photos")
            or any(m.get("type") == "photo" for m in tweet_data.get("mediaDetails", []))
        )

        if has_photos and not has_video:
            photo_res = _download_x_photos(
                tweet_data,
                twid or "media",
                output_dir,
                max_bytes,
                unique_token,
            )
            if photo_res:
                return photo_res

    # Try yt-dlp for video extraction
    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(out_path_obj / f"x_{unique_token}_%(id)s.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        "outtmpl": out_tmpl,
        "format": "best[ext=mp4]/best",
        "max_filesize": max_bytes,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First extract flat to prevent yt-dlp from recursing to external URLs in tweet text
            info_flat = ydl.extract_info(url, download=False)
            if not info_flat:
                if tweet_data:
                    photo_res = _download_x_photos(
                        tweet_data, twid or "media", output_dir, max_bytes, unique_token
                    )
                    if photo_res:
                        return photo_res
                return {
                    "success": False,
                    "error_code": "no_media",
                    "error_message": "این توییت حاوی هیچ فایل ویدیو یا تصویری برای دانلود نمی باشد.",
                }

            # If yt-dlp returns an external URL, the tweet itself has no video formats
            if info_flat.get("_type") == "url":
                if tweet_data:
                    photo_res = _download_x_photos(
                        tweet_data, twid or "media", output_dir, max_bytes, unique_token
                    )
                    if photo_res:
                        return photo_res
                return {
                    "success": False,
                    "error_code": "no_media",
                    "error_message": "این توییت حاوی هیچ فایل ویدیو یا تصویری برای دانلود نمی باشد.",
                }

            file_path = ydl.prepare_filename(info_flat)
            info = ydl.process_ie_result(info_flat, download=True)
            if not info:
                return {
                    "success": False,
                    "error_code": "no_media",
                    "error_message": "این توییت حاوی هیچ فایل ویدیو یا تصویری برای دانلود نمی باشد.",
                }

            if not os.path.exists(file_path):
                candidates = list(out_path_obj.glob(f"x_{unique_token}_*"))
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

            title = info.get("description", "") or info.get("title", "X Video")
            clean_title = re.sub(r"https?://\S+", "", title).strip()
            clean_title = clean_title[:150] if clean_title else "X Video"

            return {
                "success": True,
                "title": clean_title,
                "file_path": file_path,
                "file_paths": [file_path],
                "duration": info.get("duration", 0),
                "width": info.get("width"),
                "height": info.get("height"),
                "file_size": file_size,
                "media_type": "video",
            }

    except yt_dlp.utils.DownloadError as e:
        # Check if direct syndication video download works
        if tweet_data:
            vid_res = _download_x_video_from_syndication(
                tweet_data, twid or "media", output_dir, max_bytes, unique_token
            )
            if vid_res:
                return vid_res

            photo_res = _download_x_photos(
                tweet_data, twid or "media", output_dir, max_bytes, unique_token
            )
            if photo_res:
                return photo_res

        msg = str(e)
        if (
            "No video formats found" in msg
            or "There's no video in this tweet" in msg
            or "Unsupported URL" in msg
            or "No video could be found" in msg
        ):
            code = "no_media"
            msg = "این توییت حاوی هیچ فایل ویدیو یا تصویری برای دانلود نمی باشد."
        else:
            code = "download_error"
        return {"success": False, "error_code": code, "error_message": msg}
    except Exception as e:
        if tweet_data:
            vid_res = _download_x_video_from_syndication(
                tweet_data, twid or "media", output_dir, max_bytes, unique_token
            )
            if vid_res:
                return vid_res
            photo_res = _download_x_photos(
                tweet_data, twid or "media", output_dir, max_bytes, unique_token
            )
            if photo_res:
                return photo_res
        return {"success": False, "error_code": "unknown_error", "error_message": str(e)}
