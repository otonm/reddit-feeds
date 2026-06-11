from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from reddit.client import _MAX_RETRIES, _parse_entry, _user_agent, fetch_posts

SAMPLE_ENTRY_IMAGE = {
    "id": "t3_abc123",
    "title": "Test Post Title",
    "author": "/u/testuser",
    "link": "https://www.reddit.com/r/python/comments/abc123/test_post/",
    "published": "2024-11-14T22:13:46+00:00",
    "content": [
        {
            "type": "text/html",
            "value": '<table><tr><td><a href="https://i.redd.it/abc123.jpg">[link]</a></td></tr></table>',
        }
    ],
}


SAMPLE_ENTRY_VIDEO = {
    "id": "t3_vid001",
    "title": "Video Post",
    "author": "/u/videouser",
    "link": "https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
    "published": "2024-11-14T20:00:00+00:00",
    "content": [
        {
            "type": "text/html",
            "value": '<table><tr><td><a href="https://v.redd.it/vid001">[link]</a></td></tr></table>',
        }
    ],
}


SAMPLE_ENTRY_GALLERY = {
    "id": "t3_gal001",
    "title": "Gallery Post",
    "author": "/u/galuser",
    "link": "https://www.reddit.com/r/aww/comments/gal001/kitten_pics/",
    "published": "2024-11-14T18:00:00+00:00",
    "content": [
        {
            "type": "text/html",
            "value": '<table><tr><td><a href="https://www.reddit.com/r/aww/comments/gal001/kitten_pics/gallery">[link]</a></td></tr></table>',
        }
    ],
}


SAMPLE_ENTRY_GIF = {
    "id": "t3_gif001",
    "title": "GIF Post",
    "author": "/u/gifuser",
    "link": "https://www.reddit.com/r/gifs/comments/gif001/fun/",
    "published": "2024-11-14T16:00:00+00:00",
    "content": [
        {
            "type": "text/html",
            "value": '<table><tr><td><a href="https://i.redd.it/fun.gif">[link]</a></td></tr></table>',
        }
    ],
}


class TestParseEntry:
    def test_parses_image_post(self):
        post = _parse_entry(SAMPLE_ENTRY_IMAGE)
        assert post.id == "abc123"
        assert post.title == "Test Post Title"
        assert post.author == "testuser"
        assert post.permalink == "https://www.reddit.com/r/python/comments/abc123/test_post/"
        assert post.url == "https://i.redd.it/abc123.jpg"
        assert post.post_hint == "image"
        assert post.is_gallery is False

    def test_strips_t3_prefix_from_id(self):
        post = _parse_entry(SAMPLE_ENTRY_IMAGE)
        assert not post.id.startswith("t3_")

    def test_strips_leading_slash_u_from_author(self):
        post = _parse_entry(SAMPLE_ENTRY_IMAGE)
        assert not post.author.startswith("/u/")

    def test_parses_video_post(self):
        post = _parse_entry(SAMPLE_ENTRY_VIDEO)
        assert post.url == "https://v.redd.it/vid001"
        assert post.post_hint == "hosted:video"

    def test_parses_gallery_post(self):
        post = _parse_entry(SAMPLE_ENTRY_GALLERY)
        assert post.post_hint == "image"
        assert post.is_gallery is True

    def test_parses_gif_post(self):
        post = _parse_entry(SAMPLE_ENTRY_GIF)
        assert post.url == "https://i.redd.it/fun.gif"
        assert post.post_hint == "image"

    def test_created_utc_is_unix_timestamp(self):
        post = _parse_entry(SAMPLE_ENTRY_IMAGE)
        assert isinstance(post.created_utc, float)
        assert post.created_utc > 1700000000.0  # 2023-11-14

    def test_missing_content_returns_empty_url(self):
        entry = {**SAMPLE_ENTRY_IMAGE, "content": []}
        post = _parse_entry(entry)
        assert post.url == ""

    def test_external_image_url_post_hint(self):
        entry = {**SAMPLE_ENTRY_IMAGE, "content": [{"value": '<a href="https://flickr.com/p.jpg">[link]</a>'}]}
        post = _parse_entry(entry)
        assert post.post_hint == "image"

    def test_external_video_url_post_hint(self):
        entry = {**SAMPLE_ENTRY_IMAGE, "content": [{"value": '<a href="https://example.com/clip.mp4">[link]</a>'}]}
        post = _parse_entry(entry)
        assert post.post_hint == "rich:video"

    def test_reddit_comments_link_post_hint(self):
        entry = {
            **SAMPLE_ENTRY_IMAGE,
            "content": [{"value": '<a href="https://www.reddit.com/r/x/comments/abc/">[link]</a>'}],
        }
        post = _parse_entry(entry)
        assert post.post_hint == "link"

    def test_unknown_external_url_falls_back_to_link(self):
        entry = {**SAMPLE_ENTRY_IMAGE, "content": [{"value": '<a href="https://github.com/foo/bar">[link]</a>'}]}
        post = _parse_entry(entry)
        assert post.post_hint == "link"

    def test_gallery_inferred_from_permalink(self):
        entry = {
            **SAMPLE_ENTRY_IMAGE,
            "link": "https://www.reddit.com/r/x/comments/abc/gallery",
        }
        post = _parse_entry(entry)
        assert post.is_gallery is True

    def test_uses_summary_when_content_absent(self):
        entry = {**SAMPLE_ENTRY_IMAGE, "content": [], "summary": '<a href="https://i.redd.it/x.jpg">[link]</a>'}
        post = _parse_entry(entry)
        assert post.url == "https://i.redd.it/x.jpg"

    def test_falls_back_to_rfc2822_published(self):
        entry = {**SAMPLE_ENTRY_IMAGE, "published": "Thu, 14 Nov 2024 22:13:46 +0000"}
        post = _parse_entry(entry)
        assert post.created_utc > 1700000000.0

    def test_invalid_published_yields_zero(self):
        entry = {**SAMPLE_ENTRY_IMAGE, "published": "not a date"}
        post = _parse_entry(entry)
        assert post.created_utc == 0.0


class TestUserAgent:
    def test_user_agent_matches_reddit_required_format(self):
        ua = _user_agent()
        assert ":" in ua
        assert ua.startswith("python:")
        assert "(by /u/" in ua


class TestFetchPosts:
    async def test_fetch_posts_parses_rss(self, httpx_mock: HTTPXMock, rss_response_xml):
        httpx_mock.add_response(text=rss_response_xml)
        async with httpx.AsyncClient() as client:
            posts = await fetch_posts("https://reddit.com/r/python/.rss", 25, client)
        assert len(posts) == 3
        assert posts[0].id == "abc123"
        assert posts[0].url == "https://i.redd.it/abc123.jpg"
        assert posts[1].post_hint == "hosted:video"
        assert posts[2].is_gallery is True

    async def test_fetch_posts_sends_user_agent(self, httpx_mock: HTTPXMock, rss_response_xml):
        httpx_mock.add_response(text=rss_response_xml)
        async with httpx.AsyncClient() as client:
            await fetch_posts("https://reddit.com/r/python/.rss", 5, client)
        request = httpx_mock.get_requests()[0]
        assert request.headers["user-agent"] == _user_agent()

    async def test_fetch_posts_requests_rss_endpoint(self, httpx_mock: HTTPXMock, rss_response_xml):
        httpx_mock.add_response(text=rss_response_xml)
        async with httpx.AsyncClient() as client:
            await fetch_posts("https://reddit.com/r/python/.rss", 25, client)
        request = httpx_mock.get_requests()[0]
        assert str(request.url).startswith("https://reddit.com/r/python/.rss")

    async def test_fetch_posts_raises_after_retries_exhausted(self, httpx_mock: HTTPXMock):
        for _ in range(_MAX_RETRIES + 1):
            httpx_mock.add_response(status_code=429)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await fetch_posts("https://reddit.com/r/python/.rss", 10, client)

    async def test_fetch_posts_retries_on_429_then_succeeds(self, httpx_mock: HTTPXMock, rss_response_xml):
        httpx_mock.add_response(status_code=429)
        httpx_mock.add_response(text=rss_response_xml)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            async with httpx.AsyncClient() as client:
                posts = await fetch_posts("https://reddit.com/r/python/.rss", 10, client)
        assert len(posts) == 3

    async def test_fetch_posts_respects_retry_after_header(self, httpx_mock: HTTPXMock, rss_response_xml):
        httpx_mock.add_response(status_code=429, headers={"Retry-After": "30"})
        httpx_mock.add_response(text=rss_response_xml)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async with httpx.AsyncClient() as client:
                await fetch_posts("https://reddit.com/r/python/.rss", 10, client)
        mock_sleep.assert_called_once_with(30.0)

    async def test_fetch_posts_sleep_count_matches_retries(self, httpx_mock: HTTPXMock):
        for _ in range(_MAX_RETRIES + 1):
            httpx_mock.add_response(status_code=429)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await fetch_posts("https://reddit.com/r/python/.rss", 10, client)
        assert mock_sleep.call_count == _MAX_RETRIES

    async def test_fetch_posts_empty_feed(self, httpx_mock: HTTPXMock):
        empty_rss = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"/>"""
        httpx_mock.add_response(text=empty_rss)
        async with httpx.AsyncClient() as client:
            posts = await fetch_posts("https://reddit.com/r/python/.rss", 10, client)
        assert posts == []


class TestFetchPosts403Retry:
    async def test_retries_on_403_then_succeeds(self, httpx_mock: HTTPXMock, rss_response_xml):
        httpx_mock.add_response(status_code=403)
        httpx_mock.add_response(text=rss_response_xml)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            async with httpx.AsyncClient() as client:
                posts = await fetch_posts("https://reddit.com/r/python/.rss", 10, client)
        assert len(posts) == 3

    async def test_403_respects_retry_after_header(self, httpx_mock: HTTPXMock, rss_response_xml):
        httpx_mock.add_response(status_code=403, headers={"Retry-After": "5"})
        httpx_mock.add_response(text=rss_response_xml)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async with httpx.AsyncClient() as client:
                await fetch_posts("https://reddit.com/r/python/.rss", 10, client)
        mock_sleep.assert_called_once_with(5.0)

    async def test_403_raises_after_retries_exhausted(self, httpx_mock: HTTPXMock):
        for _ in range(_MAX_RETRIES + 1):
            httpx_mock.add_response(status_code=403)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await fetch_posts("https://reddit.com/r/python/.rss", 10, client)

    async def test_403_sleep_count_matches_retries(self, httpx_mock: HTTPXMock):
        for _ in range(_MAX_RETRIES + 1):
            httpx_mock.add_response(status_code=403)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await fetch_posts("https://reddit.com/r/python/.rss", 10, client)
        assert mock_sleep.call_count == _MAX_RETRIES
