"""Reddit JSON API client."""

import logging

import httpx

from reddit.models import RedditPost

USER_AGENT = "reddit-feeds/0.1"
TIMEOUT = 15.0

logger = logging.getLogger(__name__)


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


async def fetch_posts(url: str, limit: int, client: httpx.AsyncClient) -> list[RedditPost]:
    """Fetch posts from a Reddit JSON feed URL."""
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}limit={limit}"
    logger.debug("GET %s", full_url)
    response = await client.get(
        full_url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    logger.debug(
        "Response %d from %s in %.2fs",
        response.status_code,
        url,
        response.elapsed.total_seconds(),
    )
    response.raise_for_status()
    children = response.json()["data"]["children"]
    posts = [_parse_post(child["data"]) for child in children]
    logger.info("Fetched %d post(s) from %s", len(posts), url)
    return posts
