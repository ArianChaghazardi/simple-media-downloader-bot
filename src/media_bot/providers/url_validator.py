"""
Functional URL validator for media providers.
Enforces SSRF prevention, private network blocking, and platform-specific allowlists.
Zero custom classes.
"""

import ipaddress
import re
from typing import Tuple
from urllib.parse import urlparse

# Regex patterns for supported platforms
YOUTUBE_PATTERN = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|v/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
)
X_PATTERN = re.compile(
    r"^(https?://)?(www\.)?(twitter\.com|x\.com)/([a-zA-Z0-9_]{1,30})/status/([0-9]{1,25})"
)
INSTAGRAM_PATTERN = re.compile(
    r"^(https?://)?(www\.)?instagram\.com/(?:share/)?(p|reel|reels|tv|stories)/([a-zA-Z0-9_-]+)"
)
TIKTOK_PATTERN = re.compile(
    r"^(https?://)?(www\.|vm\.|vt\.|m\.)?tiktok\.com/(?:t/[a-zA-Z0-9_-]+|@[a-zA-Z0-9_.-]+/video/\d+|[a-zA-Z0-9_-]+)",
    re.I,
)
PINTEREST_PATTERN = re.compile(
    r"^(https?://)?([a-zA-Z0-9-]+\.)?(pinterest\.(?:com|[a-z]{2,3}(?:\.[a-z]{2})?)/pin/[a-zA-Z0-9_-]+|pin\.it/[a-zA-Z0-9_-]+)",
    re.I,
)
THREADS_PATTERN = re.compile(
    r"^(https?://)?(www\.)?threads\.net/(?:@[a-zA-Z0-9_.-]+/post/|t/)[a-zA-Z0-9_-]+",
    re.I,
)
REDDIT_PATTERN = re.compile(
    r"^(https?://)?(www\.|old\.|new\.|sh\.)?(reddit\.com/r/[a-zA-Z0-9_]+/comments/[a-zA-Z0-9_]+|redd\.it/[a-zA-Z0-9_]+|v\.redd\.it/[a-zA-Z0-9_]+)",
    re.I,
)

FORBIDDEN_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def extract_first_url(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"https?://[^\s<>\"']+", text)
    if match:
        return match.group(0).rstrip(".,;!?:")
    return text.strip()



def is_private_or_invalid_host(hostname: str) -> bool:
    if not hostname:
        return True
    host_lower = hostname.lower()
    if host_lower in FORBIDDEN_HOSTS:
        return True
    if host_lower.endswith(".local") or host_lower.endswith(".internal"):
        return True

    try:
        ip = ipaddress.ip_address(host_lower)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    except ValueError:
        # Hostname is a domain name, not an IP
        pass

    return False


def validate_url(url: str) -> Tuple[bool, str, str]:
    """
    Validates URL scheme, host, and identifies the platform ('youtube', 'x', 'instagram', or 'unknown').
    Returns: (is_valid, platform, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "unknown", "Empty URL"

    extracted = extract_first_url(url)
    if extracted:
        url = extracted

    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "unknown", "Malformed URL"

    if parsed.scheme not in ("http", "https"):
        return False, "unknown", "Invalid scheme (only http/https allowed)"

    hostname = parsed.hostname or ""
    if is_private_or_invalid_host(hostname):
        return False, "unknown", "Disallowed host target"

    if YOUTUBE_PATTERN.match(url):
        return True, "youtube", ""

    if X_PATTERN.match(url):
        return True, "x", ""

    if INSTAGRAM_PATTERN.match(url):
        return True, "instagram", ""

    if TIKTOK_PATTERN.match(url):
        return True, "tiktok", ""

    if PINTEREST_PATTERN.match(url):
        return True, "pinterest", ""

    if THREADS_PATTERN.match(url):
        return True, "threads", ""

    if REDDIT_PATTERN.match(url):
        return True, "reddit", ""

    return False, "unknown", "Unsupported platform URL"
