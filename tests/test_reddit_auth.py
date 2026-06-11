"""Tests for Reddit OAuth2 token provider."""

import asyncio
import base64
from unittest.mock import patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from reddit.auth import RedditAuthConfig, TokenProvider

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"


def _bearer(token: str) -> dict[str, str]:
    raw = f"my_client_id:{token}"
    encoded = base64.b64encode(raw.encode("ascii")).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def _token_response(access_token: str = "abc123", expires_in: int = 3600) -> dict:
    return {"access_token": access_token, "token_type": "bearer", "expires_in": expires_in, "scope": ""}


class TestTokenProviderAcquisition:
    async def test_get_token_acquires_and_caches(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_token_response("tok-1"))
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)

            token = await provider.get_token()

        assert token == "tok-1"
        assert httpx_mock.get_requests().__len__() == 1

    async def test_get_token_sends_basic_auth_with_client_credentials(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_token_response("tok"))
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(
                RedditAuthConfig(client_id="my_client_id", client_secret="my_secret"),
                client=client,
            )
            await provider.get_token()

        request = httpx_mock.get_requests()[0]
        assert request.headers["authorization"] == _bearer("my_secret")["Authorization"]
        body = request.read()
        assert b"grant_type=client_credentials" in body
        assert request.url == TOKEN_URL

    async def test_get_token_caches_until_near_expiry(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_token_response("tok-1", expires_in=3600))
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)

            t1 = await provider.get_token()
            t2 = await provider.get_token()
            t3 = await provider.get_token()

        assert t1 == t2 == t3 == "tok-1"
        assert httpx_mock.get_requests().__len__() == 1

    async def test_get_token_refreshes_near_expiry(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_token_response("tok-1", expires_in=600))  # refreshes at 300s
        httpx_mock.add_response(json=_token_response("tok-2", expires_in=3600))
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)

            t1 = await provider.get_token()
            provider._expires_at = provider._expires_at - 400  # force past refresh window
            t2 = await provider.get_token()

        assert t1 == "tok-1"
        assert t2 == "tok-2"

    async def test_concurrent_first_call_makes_single_request(self, httpx_mock: HTTPXMock):
        async def slow_response(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=_token_response("tok"))

        httpx_mock.add_callback(slow_response, is_reusable=True)

        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)
            results = await asyncio.gather(provider.get_token(), provider.get_token(), provider.get_token())

        assert results == ["tok", "tok", "tok"]
        assert httpx_mock.get_requests().__len__() == 1

    async def test_invalidate_forces_reacquisition(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_token_response("tok-1"))
        httpx_mock.add_response(json=_token_response("tok-2"))
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)

            t1 = await provider.get_token()
            provider.invalidate()
            t2 = await provider.get_token()

        assert t1 == "tok-1"
        assert t2 == "tok-2"

    async def test_invalid_credentials_raises_runtime_error(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(status_code=401, json={"error": "invalid_client"})
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="bad", client_secret="bad"), client=client)

            with pytest.raises(RuntimeError, match="OAuth2 token request failed"):
                await provider.get_token()

    async def test_response_missing_access_token_raises(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"expires_in": 3600, "token_type": "bearer"})
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)

            with pytest.raises(RuntimeError, match="missing access_token"):
                await provider.get_token()


class TestTokenProviderDefaults:
    async def test_refresh_skew_used(self, httpx_mock: HTTPXMock):
        """Token is refreshed when within refresh_skew seconds of expiry."""
        httpx_mock.add_response(json=_token_response("tok-1", expires_in=600))
        httpx_mock.add_response(json=_token_response("tok-2", expires_in=3600))
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)

            t1 = await provider.get_token()
            # _expires_at = now + 600 - 300 (default skew) = now + 300
            # Force _now past the refresh boundary
            with patch.object(provider, "_now", return_value=provider._expires_at + 1):
                t2 = await provider.get_token()

        assert t1 == "tok-1"
        assert t2 == "tok-2"

    async def test_token_not_refreshed_before_skew_window(self, httpx_mock: HTTPXMock):
        """Within the validity window, no second request is made."""
        httpx_mock.add_response(json=_token_response("tok", expires_in=3600))
        async with httpx.AsyncClient() as client:
            provider = TokenProvider(RedditAuthConfig(client_id="cid", client_secret="sec"), client=client)

            t1 = await provider.get_token()
            with patch.object(provider, "_now", return_value=provider._expires_at - 1):
                t2 = await provider.get_token()

        assert t1 == t2 == "tok"


class TestMakeTokenProvider:
    async def test_returns_none_when_credentials_absent(self):
        from reddit.auth import make_token_provider

        async with httpx.AsyncClient() as client:
            provider = make_token_provider(None, None, client)
            assert provider is None

    async def test_returns_provider_when_credentials_set(self):
        from reddit.auth import make_token_provider

        async with httpx.AsyncClient() as client:
            provider = make_token_provider("cid", "sec", client)
            assert isinstance(provider, TokenProvider)
