"""
Unit tests for X (Twitter) media provider in simple media downloader bot.
Tests photos, multi-photo albums, and external URLs.
Zero custom classes.
"""

from unittest.mock import MagicMock
from src.media_bot.providers.x_media import (
    download_x_media,
    extract_tweet_id,
)


def test_extract_tweet_id():
    url1 = "https://x.com/terryturtle2554/status/2109794504731513110"
    url2 = "https://twitter.com/user/status/123456789?s=20"
    url3 = "https://x.com/i/status/987654321"
    assert extract_tweet_id(url1) == "2109794504731513110"
    assert extract_tweet_id(url2) == "123456789"
    assert extract_tweet_id(url3) == "987654321"
    assert extract_tweet_id("https://youtube.com/watch?v=123") is None


def test_x_media_invalid_url():
    res = download_x_media("https://youtube.com/watch?v=123", "/tmp")
    assert res["success"] is False
    assert res["error_code"] == "invalid_url"


def test_x_media_photos_multi_carousel(tmp_path, mocker):
    fake_data = {
        "text": "Check this out! https://t.co/abc https://t.co/def",
        "user": {"name": "Test User"},
        "photos": [
            {"url": "https://pbs.twimg.com/media/photo1.jpg"},
            {"url": "https://pbs.twimg.com/media/photo2.jpg"},
        ],
    }

    mock_urlopen = mocker.patch("urllib.request.urlopen")
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"\xff\xd8\xff\xe0" + b"\x00" * 500
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    mocker.patch("src.media_bot.providers.x_media.fetch_tweet_syndication", return_value=fake_data)

    res = download_x_media("https://x.com/user/status/11223344", str(tmp_path))
    assert res["success"] is True
    assert res["title"] == "Check this out!"
    assert len(res["file_paths"]) == 2
    assert res["media_type"] == "photos"
    assert res["file_size"] > 0


def test_x_media_tweet_with_external_link_no_media(tmp_path, mocker):
    fake_data = {
        "text": "Check my repo: https://github.com/some/repo",
        "user": {"name": "Developer"},
        "photos": [],
        "mediaDetails": [],
    }
    mocker.patch("src.media_bot.providers.x_media.fetch_tweet_syndication", return_value=fake_data)

    mock_ydl = MagicMock()
    mock_ydl_ctx = MagicMock()
    mock_ydl.return_value.__enter__.return_value = mock_ydl_ctx
    mock_ydl_ctx.extract_info.return_value = {
        "_type": "url",
        "url": "https://github.com/some/repo",
    }
    mocker.patch("yt_dlp.YoutubeDL", mock_ydl)

    res = download_x_media("https://x.com/dev/status/998877", str(tmp_path))
    assert res["success"] is False
    assert res["error_code"] == "no_media"
    assert "Unsupported URL" not in res["error_message"]
    assert "توییت" in res["error_message"]
