"""
Functional media quality selection service.
Zero custom classes.
"""

import os
import shutil
from typing import Any, Dict, List, Optional

import yt_dlp

from src.media_bot.db.repositories.settings import get_setting, set_setting
from src.media_bot.providers.youtube import (
    _detect_pot_provider,
    _detect_warp_proxy,
    _get_isolated_cookie_file,
)
from src.media_bot.providers.youtube_fallback import fetch_youtube_fallback_qualities


def is_quality_selection_supported(platform: str, url: str) -> bool:
    """
    Returns True if the platform supports selectable media qualities.
    Currently YouTube is supported.
    """
    return platform == "youtube"


def get_vip_quality_threshold_mb(
    conn: Any,
    database_url: str,
    default: int = 50,
) -> int:
    """
    Retrieves the configurable VIP size threshold in MB from bot settings.
    Media qualities exceeding this size are marked as VIP.
    """
    val_str = get_setting(conn, database_url, "vip_quality_threshold_mb", str(default))
    try:
        val = int(val_str) if val_str else default
        return val if val > 0 else default
    except (ValueError, TypeError):
        return default


def set_vip_quality_threshold_mb(
    conn: Any,
    database_url: str,
    threshold_mb: int,
) -> None:
    """
    Updates the configurable VIP size threshold in MB.
    """
    if threshold_mb <= 0:
        threshold_mb = 50
    set_setting(conn, database_url, "vip_quality_threshold_mb", str(threshold_mb))


def format_size_label(mb: Optional[float]) -> str:
    """
    Formats a megabyte float value into a human-readable size label.
    """
    if mb is None or mb <= 0:
        return "حجم نامشخص"
    if mb >= 1024:
        return f"{round(mb / 1024, 1)} GB"
    if mb < 1:
        kb = round(mb * 1024)
        return f"{kb} KB"
    return f"{round(mb, 1)} MB"


def extract_quality_options_from_info(
    info: Dict[str, Any],
    threshold_mb: int = 50,
) -> List[Dict[str, Any]]:
    """
    Extracts available video and audio qualities with approximate sizes
    and marks qualities exceeding threshold_mb as VIP.
    """
    formats = info.get("formats") or []
    duration = info.get("duration") or 0

    # Best audio stream extraction
    audio_formats = [
        f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"
    ]
    best_audio = (
        max(audio_formats, key=lambda f: f.get("tbr") or 0)
        if audio_formats
        else None
    )
    best_audio_id = best_audio["format_id"] if best_audio else "bestaudio"
    best_audio_size = (
        (best_audio.get("filesize") or best_audio.get("filesize_approx"))
        if best_audio
        else 0
    )
    if not best_audio_size and best_audio and best_audio.get("tbr") and duration:
        best_audio_size = int((best_audio["tbr"] * 1000 / 8) * duration)
    best_audio_size = best_audio_size or 0

    audio_mb = (
        round(best_audio_size / (1024 * 1024), 1) if best_audio_size > 0 else None
    )
    audio_is_vip = bool(audio_mb and audio_mb > threshold_mb)
    audio_size_str = format_size_label(audio_mb)
    audio_label = (
        f"⭐️ صوتی MP3 (~{audio_size_str}) (اشتراک ویژه)"
        if audio_is_vip
        else f"🎵 صوتی MP3 (~{audio_size_str})"
    )

    # Video stream extraction
    video_formats = [f for f in formats if f.get("vcodec") != "none"]
    options: List[Dict[str, Any]] = []

    target_heights = [1080, 720, 480, 360]
    for th in target_heights:
        matching = [
            f
            for f in video_formats
            if (f.get("height") or 0) == th
            or min(f.get("width") or 99999, f.get("height") or 0) == th
        ]
        if not matching:
            continue

        best_v = max(
            matching,
            key=lambda f: (1 if f.get("ext") == "mp4" else 0, f.get("tbr") or 0),
        )
        v_size = best_v.get("filesize") or best_v.get("filesize_approx")
        if not v_size and best_v.get("tbr") and duration:
            v_size = int((best_v["tbr"] * 1000 / 8) * duration)

        total_size = (v_size or 0) + (
            best_audio_size if best_v.get("acodec") == "none" else 0
        )
        total_mb = (
            round(total_size / (1024 * 1024), 1) if total_size > 0 else None
        )
        is_vip = bool(total_mb and total_mb > threshold_mb)
        size_str = format_size_label(total_mb)
        label = (
            f"⭐️ {th}p (~{size_str}) (اشتراک ویژه)"
            if is_vip
            else f"🎬 {th}p (~{size_str})"
        )

        v_fid = best_v.get("format_id")
        spec = (
            f"{v_fid}+{best_audio_id}/{v_fid}/"
            f"bestvideo[height<={th}]+bestaudio/best[height<={th}]/best"
        )
        options.append(
            {
                "quality_id": f"{th}p",
                "height": th,
                "type": "video",
                "size_mb": total_mb,
                "size_label": size_str,
                "is_vip": is_vip,
                "btn_label": label,
                "format_spec": spec,
            }
        )

    # If no standard target heights matched, pick the best video format available
    if not options and video_formats:
        best_v = max(
            video_formats,
            key=lambda f: (f.get("height") or 0, f.get("tbr") or 0),
        )
        h = best_v.get("height") or 360
        v_size = best_v.get("filesize") or best_v.get("filesize_approx")
        if not v_size and best_v.get("tbr") and duration:
            v_size = int((best_v["tbr"] * 1000 / 8) * duration)
        total_size = (v_size or 0) + (
            best_audio_size if best_v.get("acodec") == "none" else 0
        )
        total_mb = (
            round(total_size / (1024 * 1024), 1) if total_size > 0 else None
        )
        is_vip = bool(total_mb and total_mb > threshold_mb)
        size_str = format_size_label(total_mb)
        label = (
            f"⭐️ {h}p (~{size_str}) (اشتراک ویژه)"
            if is_vip
            else f"🎬 {h}p (~{size_str})"
        )
        v_fid = best_v.get("format_id")
        spec = (
            f"{v_fid}+{best_audio_id}/{v_fid}/"
            f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
        )
        options.append(
            {
                "quality_id": f"{h}p",
                "height": h,
                "type": "video",
                "size_mb": total_mb,
                "size_label": size_str,
                "is_vip": is_vip,
                "btn_label": label,
                "format_spec": spec,
            }
        )

    # Always append the MP3 audio option
    options.append(
        {
            "quality_id": "audio",
            "height": 0,
            "type": "audio",
            "size_mb": audio_mb,
            "size_label": audio_size_str,
            "is_vip": audio_is_vip,
            "btn_label": audio_label,
            "format_spec": "bestaudio/best",
        }
    )

    return options


def fetch_media_qualities(
    url: str,
    cookies_path: Optional[str] = None,
    proxy_url: Optional[str] = None,
    threshold_mb: int = 50,
) -> Dict[str, Any]:
    """
    Extracts video metadata and quality choices from a YouTube URL
    using the multi-tier proxy and cookies fallback strategy.
    """
    dedicated_proxy = os.environ.get("YOUTUBE_PROXY_URL") or os.environ.get("RESIDENTIAL_PROXY_URL") or proxy_url
    warp_proxy = _detect_warp_proxy(proxy_url)
    pot_provider = _detect_pot_provider()
    temp_cookie_path = _get_isolated_cookie_file(cookies_path)
    deno_available = bool(shutil.which("deno"))

    tiers: List[Dict[str, Any]] = []

    # Priority 1: Master Cookies + Direct Connection (highest speed, unthrottled gigabit)
    if temp_cookie_path:
        tiers.append({
            "tier_name": "cookies_direct",
            "cookiefile": temp_cookie_path,
            "proxy": None,
            "player_clients": ["web_embedded", "web", "mweb"],
            "pot_provider": pot_provider,
        })

    # Priority 2: Master Cookies + Dedicated/Residential Proxy
    if temp_cookie_path and dedicated_proxy:
        tiers.append({
            "tier_name": "cookies_dedicated_proxy",
            "cookiefile": temp_cookie_path,
            "proxy": dedicated_proxy,
            "player_clients": ["web_embedded", "web", "mweb"],
            "pot_provider": pot_provider,
        })

    # Priority 3: Master Cookies + WARP Proxy
    if temp_cookie_path and warp_proxy and warp_proxy != dedicated_proxy:
        tiers.append({
            "tier_name": "cookies_warp",
            "cookiefile": temp_cookie_path,
            "proxy": warp_proxy,
            "player_clients": ["web_embedded", "web", "mweb"],
            "pot_provider": pot_provider,
        })

    # Priority 4: POT Provider + Alternative Mobile Clients (no cookies)
    primary_proxy = dedicated_proxy or warp_proxy
    tiers.append({
        "tier_name": "pot_mobile_clients",
        "cookiefile": None,
        "proxy": primary_proxy,
        "player_clients": ["web_embedded", "android", "ios", "mweb"],
        "pot_provider": pot_provider,
    })

    last_error_msg = ""
    try:
        for tier in tiers:
            ext_args: Dict[str, Any] = {
                "youtube": {
                    "player_client": tier["player_clients"],
                }
            }
            if tier.get("pot_provider"):
                ext_args["youtubepot-bgutilhttp"] = {
                    "base_url": [tier["pot_provider"]],
                }

            ydl_opts: Dict[str, Any] = {
                "skip_download": True,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "extractor_args": ext_args,
            }

            if tier.get("cookiefile"):
                ydl_opts["cookiefile"] = tier["cookiefile"]
            if tier.get("proxy"):
                ydl_opts["proxy"] = tier["proxy"]
            if deno_available:
                ydl_opts["js_runtimes"] = {"deno": {}}
                ydl_opts["remote_components"] = ["ejs:github"]

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        continue

                    options = extract_quality_options_from_info(
                        info, threshold_mb=threshold_mb
                    )
                    return {
                        "success": True,
                        "title": info.get("title", "ویدیو یوتیوب"),
                        "duration": info.get("duration", 0),
                        "thumbnail": info.get("thumbnail"),
                        "options": options,
                    }
            except Exception as e:
                last_error_msg = str(e)
                continue

    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            try:
                os.remove(temp_cookie_path)
            except Exception:
                pass

    # Priority 5: Fallback via secondary API service (Cobalt / Web Service)
    fallback_res = fetch_youtube_fallback_qualities(url, threshold_mb=threshold_mb)
    if fallback_res and fallback_res.get("success"):
        return fallback_res

    if not last_error_msg:
        err_msg = "خطا در دریافت مشخصات و کیفیت های ویدیو از یوتیوب."
    elif "bot" in last_error_msg.lower() or "confirm" in last_error_msg.lower():
        err_msg = "خطا در بررسی لینک: یوتیوب این ویدیو را به دلیل محدودیت ضدربات محدود کرده است. لطفا دقایقی دیگر تلاش نمایید."
    else:
        err_msg = f"خطا در بررسی لینک: {last_error_msg[:80]}"

    return {
        "success": False,
        "error_message": err_msg,
    }
