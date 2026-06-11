"""Reddit OAuth2 token provider for app-only authentication.

Implements the OAuth2 client_credentials grant documented at
https://github.com/reddit-archive/reddit/wiki/OAuth2#application-only-oauth.
No Reddit user account is required — only a client_id and client_secret
obtained by registering a "script" or "web" app at
https://www.reddit.com/prefs/apps.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"  # noqa: S105
_DEFAULT_REFRESH_SKEW = 300  # seconds before expiry to refresh
_HTTP_OK = 200


@dataclass(frozen=True)
class RedditAuthConfig:
    """OAuth2 client credentials for app-only Reddit access."""

    client_id: str
    client_secret: str


class TokenProvider:
    """Manages a bearer token for Reddit's app-only OAuth2 flow.

    Tokens are cached in memory for the lifetime of the process and refreshed
    automatically. Concurrent callers awaiting an uninitialised token share a
    single in-flight request (asyncio.Lock).
    """

    def __init__(
        self,
        config: RedditAuthConfig,
        client: httpx.AsyncClient,
        refresh_skew: int = _DEFAULT_REFRESH_SKEW,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._client = client
        self._refresh_skew = refresh_skew
        self._now = clock
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def get_token(self) -> str:
        """Return a valid bearer token, refreshing if near expiry."""
        if self._token is not None and self._now() < self._expires_at:
            return self._token

        async with self._lock:
            if self._token is not None and self._now() < self._expires_at:
                return self._token
            await self._fetch()
            return self._token  # type: ignore[return-value]

    def invalidate(self) -> None:
        """Force the next call to re-fetch a token (e.g. after a 401)."""
        self._token = None
        self._expires_at = 0.0

    async def _fetch(self) -> None:
        response = await self._client.post(
            _TOKEN_URL,
            auth=(self._config.client_id, self._config.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": "python:reddit-feeds:0.1 (by /u/reddit-feeds-bot)"},
        )
        if response.status_code != _HTTP_OK:
            msg = f"OAuth2 token request failed: HTTP {response.status_code}: {response.text[:200]}"
            raise RuntimeError(msg)

        body = response.json()
        token = body.get("access_token")
        expires_in = int(body.get("expires_in", 3600))
        if not token:
            msg = f"OAuth2 token response missing access_token: {body}"
            raise RuntimeError(msg)

        self._token = token
        # Refresh slightly before the server-reported expiry to avoid races.
        self._expires_at = self._now() + max(0, expires_in - self._refresh_skew)
        logger.info("Acquired Reddit OAuth2 token (expires in %ds)", expires_in)


def make_token_provider(
    client_id: str | None,
    client_secret: str | None,
    client: httpx.AsyncClient,
) -> TokenProvider | None:
    """Return a TokenProvider when both credentials are present, else None."""
    if not client_id or not client_secret:
        return None
    return TokenProvider(RedditAuthConfig(client_id=client_id, client_secret=client_secret), client=client)
