"""RSS 2.0 feed builder."""

import logging
from datetime import UTC, datetime
from urllib.parse import urlparse

from feedgen.feed import FeedGenerator

from reddit_feeds.config.models import FeedConfig
from reddit_feeds.feed.models import MediaPost

logger = logging.getLogger(__name__)

_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
_VIDEO_MIMES = {"video/mp4", "video/webm"}


def _infer_mime(url: str) -> str:
    """Infer MIME type from a URL's file extension."""
    path = urlparse(url).path
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _MIME_MAP.get(ext, "application/octet-stream")


def _is_video(url: str) -> bool:
    return _infer_mime(url) in _VIDEO_MIMES


def _build_description(media_urls: list[str]) -> str:
    """Build an HTML description with all media embedded."""
    parts: list[str] = []
    for url in media_urls:
        if _is_video(url):
            parts.append(f'<video src="{url}" controls style="max-width:100%"></video>')
        else:
            parts.append(f'<img src="{url}" style="max-width:100%">')
    return "".join(parts)


def build_feed(feed_config: FeedConfig, posts: list[MediaPost]) -> str:
    """Build an RSS 2.0 feed string from a list of MediaPost objects."""
    base_url = feed_config.url.removesuffix(".json")

    fg = FeedGenerator()
    fg.id(base_url)
    fg.title(f"r/{feed_config.name}")
    fg.link(href=base_url, rel="alternate")
    fg.description(f"Reddit feed for r/{feed_config.name}")

    for mp in posts:
        fe = fg.add_entry(order="append")
        fe.id(mp.post.permalink)
        fe.title(mp.post.title)
        fe.link(href=mp.post.permalink)
        fe.published(datetime.fromtimestamp(mp.post.created_utc, tz=UTC))
        fe.description(_build_description(mp.media_urls))

        if mp.media_urls:
            first_url = mp.media_urls[0]
            fe.enclosure(url=first_url, length="0", type=_infer_mime(first_url))

    return fg.rss_str(pretty=True).decode()
