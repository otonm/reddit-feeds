"""Media URL extraction using gallery-dl."""

import asyncio
import logging

import gallery_dl.extractor as gallery_dl_extractor
from gallery_dl import config as gallery_dl_config

from reddit_feeds.reddit.models import RedditPost

logger = logging.getLogger(__name__)

_GALLERY_DL_URL_MESSAGE = 3
_GALLERY_DL_CONFIG: dict[str, bool] = {
    "download": False,
    "write-metadata": False,
    "write-pages": False,
}


def extract_media_urls(post: RedditPost) -> list[str]:
    """Extract direct media URLs from a Reddit post using gallery-dl.

    Returns empty list if no media can be extracted. Safe to call from a thread pool.
    """
    urls, can_fallback = _try_gallery_dl(post.url)

    if not urls and can_fallback and post.post_hint == "image":
        urls = [post.url]

    return urls


async def extract_media_urls_async(post: RedditPost) -> list[str]:
    """Async wrapper: runs extract_media_urls in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, extract_media_urls, post)


def _try_gallery_dl(url: str) -> tuple[list[str], bool]:
    """Attempt URL extraction via gallery-dl.

    Returns:
        tuple[urls, can_fallback]: urls is list of extracted URLs,
        can_fallback is True only when gallery-dl.find() returned None
        (indicating this extractor doesn't handle this URL type).
        False when extraction was attempted but failed or returned nothing.

    """
    try:
        for key, value in _GALLERY_DL_CONFIG.items():
            gallery_dl_config.set((), key, value)

        extractor = gallery_dl_extractor.find(url)
        if extractor is None:
            return [], True

        urls: list[str] = []
        try:
            urls.extend(message[1] for message in extractor if message[0] == _GALLERY_DL_URL_MESSAGE)
        except Exception:
            logger.warning("gallery-dl extraction failed for %s", url, exc_info=True)
            return [], False
        else:
            return urls, False
    except Exception:
        logger.warning("gallery-dl extraction failed for %s", url, exc_info=True)
        return [], False
