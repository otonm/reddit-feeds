"""Reddit JSON API client."""

import logging

import httpx

from reddit.models import RedditPost

USER_AGENT = "reddit-feeds/0.1"
TIMEOUT = 15.0

logger = logging.getLogger(__name__)


def _parse_post(data: dict) -> RedditPost:
    """Parse a Reddit post dict from the JSON API into a RedditPost."""
    return RedditPost(
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


async def fetch_posts(url: str, limit: int, client: httpx.AsyncClient) -> list[RedditPost]:
    """Fetch posts from a Reddit JSON feed URL."""
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}limit={limit}"
    response = await client.get(
        full_url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    children = response.json()["data"]["children"]
    return [_parse_post(child["data"]) for child in children]
