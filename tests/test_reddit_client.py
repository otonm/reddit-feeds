import httpx
import pytest
from pytest_httpx import HTTPXMock

from reddit.client import _parse_post, fetch_posts


class TestParsePost:
    def test_parse_full_post(self):
        data = {
            "id": "abc123",
            "title": "Test Post",
            "author": "testuser",
            "permalink": "/r/python/comments/abc123/test/",
            "url": "https://i.redd.it/abc123.jpg",
            "created_utc": 1700000000.0,
            "post_hint": "image",
            "is_gallery": False,
            "selftext_html": None,
        }
        post = _parse_post(data)
        assert post.id == "abc123"
        assert post.permalink == "https://reddit.com/r/python/comments/abc123/test/"
        assert post.post_hint == "image"
        assert post.is_gallery is False

    def test_parse_post_missing_optional_fields(self):
        data = {
            "id": "xyz",
            "title": "Minimal",
            "author": "user",
            "permalink": "/r/test/comments/xyz/",
            "url": "https://example.com",
            "created_utc": 1700000000.0,
        }
        post = _parse_post(data)
        assert post.post_hint is None
        assert post.is_gallery is False
        assert post.selftext_html is None

    def test_parse_post_deleted_author(self):
        data = {
            "id": "del1",
            "title": "Deleted",
            "author": None,
            "permalink": "/r/test/comments/del1/",
            "url": "https://example.com",
            "created_utc": 1700000000.0,
        }
        post = _parse_post(data)
        assert post.author == "[deleted]"

    def test_permalink_prefixed_with_reddit_domain(self):
        data = {
            "id": "p1",
            "title": "Post",
            "author": "u",
            "permalink": "/r/x/comments/p1/post/",
            "url": "https://example.com",
            "created_utc": 1700000000.0,
        }
        post = _parse_post(data)
        assert post.permalink.startswith("https://reddit.com")


class TestFetchPosts:
    async def test_fetch_posts_success(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(
            url="https://reddit.com/r/python/.json?limit=10",
            json=minimal_reddit_response,
        )
        async with httpx.AsyncClient() as client:
            posts = await fetch_posts("https://reddit.com/r/python/.json", 10, client)

        assert len(posts) == 1
        assert posts[0].id == "abc123"
        assert posts[0].title == "Test Post"
        assert posts[0].permalink == "https://reddit.com/r/python/comments/abc123/test_post/"

    async def test_fetch_posts_sends_user_agent(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            await fetch_posts("https://reddit.com/r/python/.json", 5, client)

        request = httpx_mock.get_requests()[0]
        assert request.headers["user-agent"] == "reddit-feeds/0.1"

    async def test_fetch_posts_appends_limit_param(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            await fetch_posts("https://reddit.com/r/python/.json", 25, client)

        request = httpx_mock.get_requests()[0]
        assert "limit=25" in str(request.url)

    async def test_fetch_posts_raises_on_http_error(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(status_code=429)
        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_posts("https://reddit.com/r/python/.json", 10, client)

    async def test_fetch_posts_empty_feed(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"data": {"children": []}})
        async with httpx.AsyncClient() as client:
            posts = await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        assert posts == []
