from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from reddit.auth import RedditAuthConfig, TokenProvider
from reddit.client import _MAX_RETRIES, _parse_post, _user_agent, fetch_posts


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
        assert request.headers["user-agent"] == _user_agent()

    async def test_fetch_posts_appends_limit_param(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            await fetch_posts("https://reddit.com/r/python/.json", 25, client)

        request = httpx_mock.get_requests()[0]
        assert "limit=25" in str(request.url)

    async def test_fetch_posts_raises_after_retries_exhausted(self, httpx_mock: HTTPXMock):
        for _ in range(_MAX_RETRIES + 1):
            httpx_mock.add_response(status_code=429)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await fetch_posts("https://reddit.com/r/python/.json", 10, client)

    async def test_fetch_posts_retries_on_429_then_succeeds(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(status_code=429)
        httpx_mock.add_response(json=minimal_reddit_response)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            async with httpx.AsyncClient() as client:
                posts = await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        assert len(posts) == 1

    async def test_fetch_posts_respects_retry_after_header(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(status_code=429, headers={"Retry-After": "30"})
        httpx_mock.add_response(json=minimal_reddit_response)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async with httpx.AsyncClient() as client:
                await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        mock_sleep.assert_called_once_with(30.0)

    async def test_fetch_posts_sleep_count_matches_retries(self, httpx_mock: HTTPXMock):
        for _ in range(_MAX_RETRIES + 1):
            httpx_mock.add_response(status_code=429)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        assert mock_sleep.call_count == _MAX_RETRIES

    async def test_fetch_posts_empty_feed(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"data": {"children": []}})
        async with httpx.AsyncClient() as client:
            posts = await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        assert posts == []


class TestUserAgent:
    def test_user_agent_matches_reddit_required_format(self):
        ua = _user_agent()
        # Reddit requires: <platform>:<app-id>:<version> (by /u/<username>)
        assert ":" in ua
        assert ua.startswith("python:")
        assert "(by /u/" in ua


class TestFetchPostsAuth:
    async def test_unauthenticated_uses_www_reddit_com(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            await fetch_posts("https://www.reddit.com/r/python/.json", 10, client)
        request = httpx_mock.get_requests()[0]
        assert "www.reddit.com" in str(request.url)

    async def test_authenticated_rewrites_host_to_oauth_reddit(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)
            with patch.object(provider, "get_token", AsyncMock(return_value="bearer-tok")):
                await fetch_posts("https://www.reddit.com/r/python/.json", 10, client, token_provider=provider)
        request = httpx_mock.get_requests()[0]
        assert "oauth.reddit.com" in str(request.url)
        assert "www.reddit.com" not in str(request.url)

    async def test_authenticated_sends_bearer_header(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)
            with patch.object(provider, "get_token", AsyncMock(return_value="bearer-tok")):
                await fetch_posts("https://www.reddit.com/r/python/.json", 10, client, token_provider=provider)
        request = httpx_mock.get_requests()[0]
        assert request.headers["authorization"] == "Bearer bearer-tok"

    async def test_authenticated_preserves_non_reddit_host(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)
            with patch.object(provider, "get_token", AsyncMock(return_value="bearer-tok")):
                await fetch_posts("https://old.reddit.com/r/python/.json", 10, client, token_provider=provider)
        request = httpx_mock.get_requests()[0]
        assert "old.reddit.com" in str(request.url)
        assert "oauth.reddit.com" not in str(request.url)

    async def test_401_triggers_invalidate_and_retry(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(status_code=401)
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)
            with (
                patch.object(provider, "get_token", AsyncMock(return_value="bearer-tok")) as mock_get,
                patch.object(provider, "invalidate") as mock_invalidate,
            ):
                posts = await fetch_posts("https://www.reddit.com/r/python/.json", 10, client, token_provider=provider)
        assert len(posts) == 1
        mock_invalidate.assert_called_once()
        assert mock_get.call_count == 2  # once for each attempt after invalidate


class TestFetchPosts403Retry:
    async def test_retries_on_403_then_succeeds(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(status_code=403)
        httpx_mock.add_response(json=minimal_reddit_response)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            async with httpx.AsyncClient() as client:
                posts = await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        assert len(posts) == 1

    async def test_403_respects_retry_after_header(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(status_code=403, headers={"Retry-After": "5"})
        httpx_mock.add_response(json=minimal_reddit_response)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async with httpx.AsyncClient() as client:
                await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        mock_sleep.assert_called_once_with(5.0)

    async def test_403_raises_after_retries_exhausted(self, httpx_mock: HTTPXMock):
        for _ in range(_MAX_RETRIES + 1):
            httpx_mock.add_response(status_code=403)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await fetch_posts("https://reddit.com/r/python/.json", 10, client)

    async def test_403_sleep_count_matches_retries(self, httpx_mock: HTTPXMock):
        for _ in range(_MAX_RETRIES + 1):
            httpx_mock.add_response(status_code=403)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        assert mock_sleep.call_count == _MAX_RETRIES
