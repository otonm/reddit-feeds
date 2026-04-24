"""Media URL extraction using gallery-dl."""

import asyncio
import logging
import threading
from pathlib import PurePosixPath

import gallery_dl.extractor as gallery_dl_extractor
from gallery_dl import config as gallery_dl_config

from reddit.models import RedditPost

logger = logging.getLogger(__name__)

_GALLERY_DL_URL_MESSAGE = 3
_GALLERY_DL_CONFIG: dict[str, bool] = {
    "download": False,
    "write-metadata": False,
    "write-pages": False,
}
# gallery-dl's extractor registry initialization is not thread-safe; serialize all find() calls.
_gallery_dl_lock = threading.Lock()

_DIRECT_MEDIA_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".gifv", ".webp",
    ".mp4", ".webm", ".mov",
})


def _is_direct_media_url(url: str) -> bool:
    return PurePosixPath(url.split("?", maxsplit=1)[0]).suffix.lower() in _DIRECT_MEDIA_EXTENSIONS


def extract_media_urls(post: RedditPost) -> list[str]:
    """Extract direct media URLs from a Reddit post using gallery-dl.

    Returns empty list if no media can be extracted. Safe to call from a thread pool.
    """
    logger.debug("Extracting media from %s (hint=%s)", post.url, post.post_hint)

    if _is_direct_media_url(post.url):
        logger.debug("Direct media URL, skipping gallery-dl: %s", post.url)
        return [post.url]

    urls, can_fallback = _try_gallery_dl(post.url)

    if not urls and can_fallback and post.post_hint == "image":
        logger.debug("No gallery-dl match; falling back to direct URL for %s", post.url)
        urls = [post.url]

    logger.debug("Extracted %d URL(s) from %s", len(urls), post.url)
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
    with _gallery_dl_lock:
        try:
            for key, value in _GALLERY_DL_CONFIG.items():
                gallery_dl_config.set((), key, value)

            extractor = gallery_dl_extractor.find(url)
            if extractor is None:
                logger.debug("No gallery-dl extractor found for %s", url)
                return [], True

            urls: list[str] = []
            try:
                urls.extend(message[1] for message in extractor if message[0] == _GALLERY_DL_URL_MESSAGE)
            except Exception as e:
                logger.warning("gallery-dl extraction failed for %s: %s: %s", url, type(e).__name__, e)
                logger.debug("gallery-dl extraction failed for %s", url, exc_info=True)
                return [], False
            else:
                logger.debug("gallery-dl found %d URL(s) for %s", len(urls), url)
                return urls, False
        except Exception as e:
            logger.warning("gallery-dl extraction failed for %s: %s: %s", url, type(e).__name__, e)
            logger.debug("gallery-dl extraction failed for %s", url, exc_info=True)
            return [], False
