"""
Unit tests for URL validation across all 7 supported media platforms.
Zero custom classes.
"""

from src.media_bot.providers.url_validator import (
    extract_first_url,
    is_private_or_invalid_host,
    validate_url,
)


def test_extract_first_url():
    text = "Hello check this out: https://instagram.com/reel/C12345678/ it is awesome"
    assert extract_first_url(text) == "https://instagram.com/reel/C12345678/"
    assert extract_first_url("https://youtu.be/dQw4w9WgXcQ.") == "https://youtu.be/dQw4w9WgXcQ"


def test_private_and_ssrf_blocking():
    assert is_private_or_invalid_host("localhost") is True
    assert is_private_or_invalid_host("127.0.0.1") is True
    assert is_private_or_invalid_host("192.168.1.1") is True
    assert is_private_or_invalid_host("10.0.0.1") is True
    assert is_private_or_invalid_host("172.16.0.5") is True
    assert is_private_or_invalid_host("youtube.com") is False
    assert is_private_or_invalid_host("instagram.com") is False


def test_validate_all_platforms():
    test_cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True, "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", True, "youtube"),
        ("https://www.youtube.com/shorts/abcdefghijk", True, "youtube"),
        ("https://www.instagram.com/reel/C12345678/", True, "instagram"),
        ("https://www.instagram.com/p/C12345678/", True, "instagram"),
        ("https://www.tiktok.com/@user/video/1234567890123456789", True, "tiktok"),
        ("https://vm.tiktok.com/ZM1234567/", True, "tiktok"),
        ("https://twitter.com/elonmusk/status/1234567890", True, "x"),
        ("https://x.com/user/status/9876543210", True, "x"),
        ("https://www.pinterest.com/pin/123456789012345678/", True, "pinterest"),
        ("https://pin.it/abcdefg", True, "pinterest"),
        ("https://www.threads.net/@user/post/C12345678", True, "threads"),
        ("https://www.reddit.com/r/funny/comments/123456/title/", True, "reddit"),
    ]

    for url, exp_valid, exp_plat in test_cases:
        valid, plat, err = validate_url(url)
        assert valid == exp_valid, f"Failed validation for {url}: {err}"
        assert plat == exp_plat, f"Expected {exp_plat} for {url}, got {plat}"


def test_reject_unsupported_urls():
    invalid_cases = [
        "https://example.com/video.mp4",
        "https://127.0.0.1:8080/file.mp4",
        "ftp://youtube.com/watch?v=123",
        "invalid_text_without_link",
    ]
    for url in invalid_cases:
        valid, plat, err = validate_url(url)
        assert valid is False, f"Expected failure for {url}"
