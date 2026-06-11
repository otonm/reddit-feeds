"""Reddit JSON API client."""

import asyncio
import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser
import httpx

from reddit.models import RedditPost

USER_AGENT = "python:reddit-feeds:0.1.0 (by /u/reddit-feeds-bot)"
TIMEOUT = 15.0
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 2.0
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_FORBIDDEN = 403

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
_VIDEO_EXTS = (".mp4", ".webm", ".mov")

_LINK_HREF_RE = re.compile(r'href="([^"]+)"\s*>\s*\[link\]')


def _user_agent() -> str:
    """Return the User-Agent string sent on every Reddit request.

    Reddit's API policy requires the format `<platform>:<app-id>:<version> (by /u/<username>)`;
    a missing or generic User-Agent causes requests from datacenter IPs to be blocked.
    """
    return USER_AGENT


def _parse_post_hint(url: str) -> str:
    """Infer post_hint from the post's direct media URL (since RSS omits this field)."""
    if not url:
        return "link"
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path
    if host == "v.redd.it":
        return "hosted:video"
    if host == "i.redd.it":
        return "image"
    if "/gallery" in path:
        return "image"
    if host.endswith("reddit.com") and "/comments/" in path:
        return "link"
    return _hint_by_extension(path)


_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
_VIDEO_EXTS = (".mp4", ".webm", ".mov")


def _hint_by_extension(path: str) -> str:
    """Return post_hint inferred from a URL's file extension."""
    lowered = path.lower()
    if lowered.endswith(_IMAGE_EXTS):
        return "image"
    if lowered.endswith(_VIDEO_EXTS):
        return "rich:video"
    return "link"


def _is_gallery_url(permalink: str, content_url: str) -> bool:
    """Infer whether a post is a gallery (Reddit's multi-image posts)."""
    return "/gallery" in permalink or "/gallery" in content_url


def _extract_link_url(content_value: str) -> str:
    """Extract the [link] href from a Reddit RSS entry's HTML content.

    The RSS content has the form:
        <a href="https://i.redd.it/foo.jpg">[link]</a>
    or for videos:
        <a href="https://v.redd.it/xxx">[link]</a>
    or for galleries:
        <a href="https://www.reddit.com/r/X/comments/yyy/gallery">[link]</a>
    """
    if not content_value:
        return ""
    unescaped = content_value.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')
    match = _LINK_HREF_RE.search(unescaped)
    return match.group(1) if match else ""


def _parse_entry(entry: dict) -> RedditPost:
    """Parse a single feedparser entry into a RedditPost.

    Mirrors the contract of the old JSON-based _parse_post, but the inputs are
    Atom 1.0 fields (id, title, author, link, published, content) instead of
    Reddit's JSON shape.
    """
    entry_id = entry.get("id", "").removeprefix("t3_")
    author = entry.get("author", "").removeprefix("/u/")
    permalink = entry.get("link", "")
    published = entry.get("published", "")
    try:
        # Reddit RSS serves ISO 8601 (e.g. "2024-11-14T22:13:46+00:00"); feedparser
        # also normalizes some entries to RFC 2822. Try ISO first, fall back.
        try:
            created_utc = datetime.fromisoformat(published).astimezone(UTC).timestamp()
        except ValueError:
            created_utc = parsedate_to_datetime(published).astimezone(UTC).timestamp()
    except (TypeError, ValueError):
        created_utc = 0.0
    content_value = ""
    if entry.get("content"):
        content_value = entry["content"][0].get("value", "")
    elif entry.get("summary"):
        content_value = entry["summary"]
    url = _extract_link_url(content_value)
    return RedditPost(
        id=entry_id,
        title=entry.get("title", ""),
        author=author or "[deleted]",
        permalink=permalink,
        url=url,
        created_utc=created_utc,
        post_hint=_parse_post_hint(url),
        is_gallery=_is_gallery_url(permalink, url),
    )


async def fetch_posts(
    url: str,
    limit: int,
    client: httpx.AsyncClient,
) -> list[RedditPost]:
    """Fetch posts from a Reddit subreddit RSS feed, retrying on 429/403.

    The `limit` parameter is accepted for API compatibility but Reddit's RSS
    endpoint doesn't honour it — it returns the most recent ~25 entries.
    Callers that need fewer entries slice the result themselves.
    """
    del limit  # Reddit's RSS endpoint ignores count; see docstring.

    for attempt in range(_MAX_RETRIES + 1):
        logger.debug("GET %s (attempt %d/%d)", url, attempt + 1, _MAX_RETRIES + 1)
        headers: dict[str, str] = {"User-Agent": _user_agent()}

        response = await client.get(url, headers=headers, timeout=TIMEOUT)
        logger.debug(
            "Response %d from %s in %.2fs",
            response.status_code,
            url,
            response.elapsed.total_seconds(),
        )

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
        parsed = feedparser.parse(response.text)
        posts = [_parse_entry(entry) for entry in parsed.entries]
        logger.info("Fetched %d post(s) from %s", len(posts), url)
        return posts

    msg = "fetch_posts: unreachable"  # pragma: no cover
    raise RuntimeError(msg)  # pragma: no cover


logger = logging.getLogger(__name__)
