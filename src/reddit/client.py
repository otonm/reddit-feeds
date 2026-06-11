"""Reddit JSON API client."""

import asyncio
import logging
from urllib.parse import urlparse, urlunparse

import httpx

from reddit.auth import TokenProvider
from reddit.models import RedditPost

USER_AGENT = "python:reddit-feeds:0.1.0 (by /u/reddit-feeds-bot)"
TIMEOUT = 15.0
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 2.0
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_FORBIDDEN = 403
_HTTP_UNAUTHORIZED = 401
_REDDIT_HOST = "www.reddit.com"
_OAUTH_REDDIT_HOST = "oauth.reddit.com"


def _user_agent() -> str:
    """Return the User-Agent string sent on every Reddit request.

    Reddit's API policy requires the format `<platform>:<app-id>:<version> (by /u/<username>)`;
    a missing or generic User-Agent causes requests from datacenter IPs to be blocked.
    """
    return USER_AGENT


def _parse_post(data: dict) -> RedditPost:
    """Parse a Reddit post dict from the JSON API into a RedditPost."""
    post = RedditPost(
        id=data["id"],
        title=data["title"],
        author=data.get("author") or "[deleted]",
        permalink=f"https://reddit.com{data['permalink']}",
        url=data["url"],
        created_utc=data["created_utc"],
        post_hint=data.get("post_hint"),
        is_gallery=bool(data.get("is_gallery", False)),
        selftext_html=data.get("selftext_html"),
    )
    logger.debug("Parsed post %s: %r (hint=%s)", post.id, post.title[:60], post.post_hint)
    return post


def _to_oauth_url(url: str) -> str:
    """Rewrite www.reddit.com -> oauth.reddit.com for authenticated requests.

    Authenticated Reddit requests must hit oauth.reddit.com per the OAuth2 spec.
    Other hosts (e.g. old.reddit.com) are passed through unchanged.
    """
    parsed = urlparse(url)
    if parsed.netloc == _REDDIT_HOST:
        return urlunparse(parsed._replace(netloc=_OAUTH_REDDIT_HOST))
    return url


async def fetch_posts(
    url: str,
    limit: int,
    client: httpx.AsyncClient,
    token_provider: TokenProvider | None = None,
) -> list[RedditPost]:
    """Fetch posts from a Reddit JSON feed URL, retrying on 429/403/401."""
    sep = "&" if "?" in url else "?"
    request_url = f"{url}{sep}limit={limit}"
    if token_provider is not None:
        request_url = _to_oauth_url(request_url)

    for attempt in range(_MAX_RETRIES + 1):
        logger.debug("GET %s (attempt %d/%d)", request_url, attempt + 1, _MAX_RETRIES + 1)
        headers: dict[str, str] = {"User-Agent": _user_agent()}
        if token_provider is not None:
            headers["Authorization"] = f"Bearer {await token_provider.get_token()}"

        response = await client.get(request_url, headers=headers, timeout=TIMEOUT)
        logger.debug(
            "Response %d from %s in %.2fs",
            response.status_code,
            url,
            response.elapsed.total_seconds(),
        )

        if response.status_code == _HTTP_UNAUTHORIZED and token_provider is not None and attempt < _MAX_RETRIES:
            logger.warning("Reddit returned 401 (stale token?), invalidating and retrying")
            token_provider.invalidate()
            continue

        if response.status_code in (_HTTP_TOO_MANY_REQUESTS, _HTTP_FORBIDDEN) and attempt < _MAX_RETRIES:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else _RETRY_BASE_DELAY * (2**attempt)
            logger.warning(
                "Reddit returned %d (attempt %d/%d), retrying in %.0fs",
                response.status_code,
                attempt + 1,
                _MAX_RETRIES + 1,
                delay,
            )
            await asyncio.sleep(delay)
            continue

        response.raise_for_status()
        children = response.json()["data"]["children"]
        posts = [_parse_post(child["data"]) for child in children]
        logger.info("Fetched %d post(s) from %s", len(posts), url)
        return posts

    msg = "fetch_posts: unreachable"  # pragma: no cover
    raise RuntimeError(msg)  # pragma: no cover


logger = logging.getLogger(__name__)
