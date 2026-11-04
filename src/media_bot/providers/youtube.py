"""
Functional YouTube media provider using yt-dlp.
Zero custom classes.
"""

import os
import shutil
import socket
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yt_dlp

from src.media_bot.providers.url_validator import validate_url


def _detect_pot_provider() -> Optional[str]:
    """
    Detects if local bgutil PO Token provider is running on 127.0.0.1:4416.
    """
    pot_url = os.environ.get("POT_PROVIDER_URL", "http://127.0.0.1:4416")
    try:
        host = "127.0.0.1"
        port = 4416
        if "://" in pot_url:
            parts = pot_url.split("://", 1)[1].split("/", 1)[0]
            if ":" in parts:
                h, p = parts.split(":", 1)
                host = h
                port = int(p)
            else:
                host = parts
                port = 80
        with socket.create_connection((host, port), timeout=0.2):
            return pot_url
    except Exception:
        return None


def _detect_warp_proxy(explicit_proxy: Optional[str] = None) -> Optional[str]:
    """
    Detects active proxy: explicit -> env -> local WARP socks5 on 127.0.0.1:1080.
    """
    if explicit_proxy:
        return explicit_proxy
    env_proxy = os.environ.get("PROXY_URL")
    if env_proxy:
        return env_proxy
    try:
        with socket.create_connection(("127.0.0.1", 1080), timeout=0.4):
            return "socks5://127.0.0.1:1080"
    except Exception:
        return None


def _get_isolated_cookie_file(cookies_path: Optional[str] = None) -> Optional[str]:
    """
    Creates an isolated temporary copy of the master cookie file.
    This prevents yt-dlp from overwriting or corrupting master cookies on exit.
    """
    master_source = None
    if cookies_path and os.path.isfile(cookies_path):
        master_source = cookies_path
    elif os.path.isfile("data/cookies.txt"):
        master_source = "data/cookies.txt"
    elif os.path.isfile("cookies.txt"):
        master_source = "cookies.txt"

    # Self-heal from master backup if current file is missing or truncated
    if master_source and os.path.isfile(master_source):
        if os.path.getsize(master_source) < 100 and os.path.isfile(f"{master_source}.master"):
            try:
                shutil.copyfile(f"{master_source}.master", master_source)
            except Exception:
                pass
    elif os.path.isfile("data/cookies.txt.master"):
        master_source = "data/cookies.txt.master"

    if not master_source or not os.path.isfile(master_source) or os.path.getsize(master_source) < 50:
        return None

    try:
        temp_dir = tempfile.gettempdir()
        temp_cookie_path = os.path.join(temp_dir, f"ytdlp_media_ck_{uuid.uuid4().hex}.txt")
        shutil.copyfile(master_source, temp_cookie_path)
        return temp_cookie_path
    except Exception:
        return None


def download_youtube_media(
    url: str,
    output_dir: str,
    max_bytes: int = 104857600,
    ffmpeg_path: Optional[str] = None,
    cookies_path: Optional[str] = None,
    proxy_url: Optional[str] = None,
) -> Dict[str, Any]:
    is_valid, platform, err = validate_url(url)
    if not is_valid or platform != "youtube":
        return {
            "success": False,
            "error_code": "invalid_url",
            "error_message": err or "Invalid YouTube URL",
        }

    out_path_obj = Path(output_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    unique_token = uuid.uuid4().hex[:12]
    out_tmpl = str(out_path_obj / f"yt_{unique_token}_%(id)s.%(ext)s")

    warp_proxy = _detect_warp_proxy(proxy_url)
    pot_provider = _detect_pot_provider()
    temp_cookie_path = _get_isolated_cookie_file(cookies_path)
    deno_available = bool(shutil.which("deno"))

    # Multi-tier fallback pipeline:
    # Tier 1: POT Provider via WARP / direct (mints valid GVS PO Token)
    # Tier 2: Master Cookies + Deno JS challenges (Direct or explicit proxy)
    # Tier 3: Master Cookies + Deno JS challenges via WARP Proxy (127.0.0.1:1080)
    # Tier 4: Alternative Player Clients via WARP Proxy
    tiers: List[Dict[str, Any]] = []

    # Priority 1: POT provider active
    if pot_provider:
        primary_proxy = warp_proxy or proxy_url or os.environ.get("PROXY_URL")
        tiers.append({
            "tier_name": "pot_warp",
            "cookiefile": temp_cookie_path,
            "proxy": primary_proxy,
            "player_clients": ["web_embedded", "web", "mweb"],
            "pot_provider": pot_provider,
        })
        if proxy_url and proxy_url != primary_proxy:
            tiers.append({
                "tier_name": "pot_proxy",
                "cookiefile": temp_cookie_path,
                "proxy": proxy_url,
                "player_clients": ["web_embedded", "web", "mweb"],
                "pot_provider": pot_provider,
            })

    # Priority 2: Cookies + direct/explicit proxy
    tier_direct: Dict[str, Any] = {
        "tier_name": "cookies_direct",
        "cookiefile": temp_cookie_path,
        "proxy": proxy_url or os.environ.get("PROXY_URL"),
        "player_clients": ["web_embedded", "web", "mweb"],
        "pot_provider": pot_provider,
    }
    tiers.append(tier_direct)

    # Priority 3: Cookies + WARP proxy
    if warp_proxy and warp_proxy != tier_direct.get("proxy"):
        tiers.append({
            "tier_name": "cookies_warp",
            "cookiefile": temp_cookie_path,
            "proxy": warp_proxy,
            "player_clients": ["web_embedded", "web", "mweb"],
            "pot_provider": pot_provider,
        })

    # Priority 4: No cookies + WARP proxy + alternative clients
    tiers.append({
        "tier_name": "nocookies_warp",
        "cookiefile": None,
        "proxy": warp_proxy,
        "player_clients": ["web_embedded", "android", "ios", "mweb"],
        "pot_provider": pot_provider,
    })

    last_error_msg = ""
    last_error_code = "download_error"

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
                "outtmpl": out_tmpl,
                "format": "best[filesize<=52428800]/best[filesize_approx<=52428800]/bestvideo[height<=720]+bestaudio/best[height<=720]/18/best",
                "concurrent_fragment_downloads": 4,
                "max_filesize": max_bytes,
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

            if ffmpeg_path and os.path.exists(ffmpeg_path):
                ydl_opts["ffmpeg_location"] = ffmpeg_path

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        continue

                    file_path = ydl.prepare_filename(info)
                    if not os.path.exists(file_path):
                        candidates = list(out_path_obj.glob(f"yt_{unique_token}_*"))
                        if candidates:
                            file_path = str(candidates[0])
                        else:
                            last_error_code = "file_missing"
                            last_error_msg = "Downloaded file not found on disk"
                            continue

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

                    title = info.get("title", "YouTube Video")
                    duration = info.get("duration", 0)
                    width = info.get("width")
                    height = info.get("height")

                    return {
                        "success": True,
                        "title": title,
                        "file_path": file_path,
                        "duration": duration,
                        "width": width,
                        "height": height,
                        "file_size": file_size,
                        "metadata": {
                            "id": info.get("id"),
                            "uploader": info.get("uploader"),
                            "view_count": info.get("view_count"),
                            "tier_used": tier["tier_name"],
                        },
                    }

            except yt_dlp.utils.DownloadError as e:
                msg = str(e)
                last_error_msg = msg
                if "File is larger than max-filesize" in msg:
                    return {
                        "success": False,
                        "error_code": "too_large",
                        "error_message": "حجم ویدیو بیشتر از حد مجاز تنظیم شده برای ربات است.",
                        "raw_error": msg,
                    }
                elif "Private video" in msg:
                    last_error_code = "private_video"
                    continue
                elif "Video unavailable" in msg or "not available" in msg:
                    last_error_code = "unavailable"
                    continue
                elif (
                    "confirm you’re not a bot" in msg
                    or "confirm you're not a bot" in msg
                    or "Sign in to confirm" in msg
                    or "no longer valid" in msg
                ):
                    last_error_code = "bot_check_required"
                    # Try next tier
                    continue
                else:
                    # General network or yt-dlp error; proceed to next tier
                    continue
            except Exception as e:
                last_error_msg = str(e)
                continue

    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            try:
                os.remove(temp_cookie_path)
            except Exception:
                pass

    if last_error_code == "bot_check_required":
        user_msg = "خطا در دانلود از یوتیوب: به دلیل محدودیت ضدربات یوتیوب امکان پردازش این لینک در حال حاضر وجود ندارد. لطفا چند دقیقه بعد مجددا تلاش کنید."
    elif last_error_code == "too_large":
        user_msg = "حجم ویدیو بیشتر از حد مجاز تنظیم شده برای ربات است."
    elif last_error_code == "private_video":
        user_msg = "این ویدیو خصوصی است و امکان دسترسی به آن وجود ندارد."
    elif last_error_code == "unavailable":
        user_msg = "این ویدیو در دسترس نیست یا توسط سازنده حذف شده است."
    elif last_error_code == "file_missing":
        user_msg = "خطا در یافتن فایل دانلود شده در سیستم."
    else:
        user_msg = "خطا در دریافت ویدیوی یوتیوب. لطفا مجددا تلاش کنید."

    return {
        "success": False,
        "error_code": last_error_code,
        "error_message": user_msg,
        "raw_error": last_error_msg,
    }
