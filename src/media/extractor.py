"""Media URL extraction using gallery-dl and yt-dlp."""

import asyncio
import contextlib
import logging
import tempfile
import threading
from functools import partial
from pathlib import Path, PurePosixPath

import gallery_dl.extractor as gallery_dl_extractor
from gallery_dl import config as gallery_dl_config
from gallery_dl.exception import AbortExtraction

from reddit.models import RedditPost

_MASK_PREFIX_LEN = 4

logger = logging.getLogger(__name__)

_GALLERY_DL_URL_MESSAGE = 3
_GALLERY_DL_CONFIG: dict[str, bool] = {
    "download": False,
    "write-metadata": False,
    "write-pages": False,
}
# gallery-dl's extractor registry initialization is not thread-safe; serialize all find() calls.
_gallery_dl_lock = threading.Lock()

_DIRECT_MEDIA_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".gifv",
        ".webp",
        ".mp4",
        ".webm",
        ".mov",
    }
)


def _is_direct_media_url(url: str) -> bool:
    return PurePosixPath(url.split("?", maxsplit=1)[0]).suffix.lower() in _DIRECT_MEDIA_EXTENSIONS


def extract_media_urls(post: RedditPost, *, cookies: dict[str, str] | None = None) -> list[str]:
    """Extract direct media URLs from a Reddit post using gallery-dl.

    Returns empty list if no media can be extracted. Safe to call from a thread pool.

    For v.redd.it videos and gallery posts, gallery-dl needs the full post
    permalink (not the bare /v.redd.it/xxx or /gallery URL) so it can fetch
    the post page and resolve the real media URLs.

    Args:
        post: The Reddit post to extract media URLs from.
        cookies: Optional dict of cookie name → value to pass to gallery-dl
            (e.g. {"reddit_session": "..."}). Used to authenticate requests
            and bypass Reddit's WAF block on datacenter IPs.

    """
    logger.debug("Extracting media from %s (hint=%s)", post.url, post.post_hint)

    if _is_direct_media_url(post.url):
        logger.debug("Direct media URL, skipping gallery-dl: %s", post.url)
        return [post.url]

    if post.post_hint == "hosted:video":
        urls, _ = _try_yt_dlp(post, cookies=cookies)
        if urls:
            logger.debug("yt-dlp found %d URL(s) for %s", len(urls), post.url)
            return urls
        logger.debug("yt-dlp returned nothing for %s, falling back to gallery-dl", post.url)

    target = post.permalink if post.is_gallery or post.post_hint == "hosted:video" else post.url
    urls, can_fallback = _try_gallery_dl(target, cookies=cookies)

    if not urls and can_fallback and post.post_hint == "image":
        logger.debug("No gallery-dl match; falling back to direct URL for %s", post.url)
        urls = [post.url]

    logger.debug("Extracted %d URL(s) from %s", len(urls), post.url)
    return urls


async def extract_media_urls_async(
    post: RedditPost,
    *,
    cookies: dict[str, str] | None = None,
) -> list[str]:
    """Async wrapper: runs extract_media_urls in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(extract_media_urls, post, cookies=cookies),
    )


def _try_gallery_dl(
    url: str,
    *,
    cookies: dict[str, str] | None = None,
) -> tuple[list[str], bool]:
    """Attempt URL extraction via gallery-dl.

    Returns:
        tuple[urls, can_fallback]: urls is list of extracted URLs,
        can_fallback is True only when gallery-dl.find() returned None
        (indicating this extractor doesn't handle this URL type).
        False when extraction was attempted but failed or returned nothing.

    Args:
        url: The URL (or permalink) to extract from.
        cookies: Optional dict of cookies to set in gallery-dl's
            `extractor.reddit.cookies` config (e.g. for reddit_session).

    """
    with _gallery_dl_lock:
        try:
            for key, value in _GALLERY_DL_CONFIG.items():
                gallery_dl_config.set((), key, value)
            if cookies:
                gallery_dl_config.set(("extractor", "reddit"), "cookies", cookies)

            extractor = gallery_dl_extractor.find(url)
            if extractor is None:
                logger.debug("No gallery-dl extractor found for %s", url)
                return [], True

            urls: list[str] = []
            try:
                urls.extend(message[1] for message in extractor if message[0] == _GALLERY_DL_URL_MESSAGE)
            except AbortExtraction:
                logger.warning(
                    "gallery-dl aborted extraction for %s (likely Reddit WAF block, auth required, "
                    "or HTML response — run with --debug for full details)",
                    url,
                )
                logger.debug("gallery-dl extraction failed for %s", url, exc_info=True)
                return [], False
            except Exception as e:
                logger.warning(
                    "gallery-dl extraction failed for %s: %s: %s",
                    url,
                    type(e).__name__,
                    _truncate(str(e), 200),
                )
                logger.debug("gallery-dl extraction failed for %s", url, exc_info=True)
                return [], False
            else:
                logger.debug("gallery-dl found %d URL(s) for %s", len(urls), url)
                return urls, False
        except Exception as e:
            logger.warning(
                "gallery-dl extraction failed for %s: %s: %s",
                url,
                type(e).__name__,
                _truncate(str(e), 200),
            )
            logger.debug("gallery-dl extraction failed for %s", url, exc_info=True)
            return [], False


def _truncate(s: str, max_len: int) -> str:
    """Truncate a string with an ellipsis if it exceeds max_len characters."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _mask(value: str) -> str:
    """Return a short, safe representation of a secret value for logging.

    Short values are returned unchanged so empty/None-ish inputs are
    still recognisable; longer values show only the first 4 characters.
    """
    if len(value) <= _MASK_PREFIX_LEN:
        return value
    return value[:_MASK_PREFIX_LEN] + "***"


def _try_yt_dlp(
    post: RedditPost,
    *,
    cookies: dict[str, str] | None = None,
) -> tuple[list[str], bool]:
    """Attempt URL extraction for a `hosted:video` (v.redd.it) post via yt-dlp.

    Returns ``(urls, can_fallback)``:
      - ``urls``: a single-element list with the best direct media URL on success,
        or an empty list on failure.
      - ``can_fallback``: always ``False``; the caller is expected to try
        ``_try_gallery_dl`` next if we returned nothing.

    yt-dlp is preferred for hosted:video because it handles DASH/HLS manifest
    selection and format ranking better than gallery-dl. Both extractors are
    subject to Reddit's WAF block on datacenter IPs; passing ``cookies`` (e.g.
    a logged-in ``reddit_session`` value) gets the API call through.
    """
    from yt_dlp import YoutubeDL  # noqa: PLC0415  (lazy import: avoid cost on image-only feeds)

    opts: dict = {"quiet": True, "no_warnings": True, "skip_download": True}
    cookie_path: str | None = None
    if cookies:
        cookie_path = _write_mozilla_cookies_file(cookies)
        opts["cookiefile"] = cookie_path

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(post.permalink or post.url, download=False)
        url = _pick_yt_dlp_url(info)
    except Exception as e:
        logger.warning(
            "yt-dlp extraction failed for %s: %s: %s",
            post.url,
            type(e).__name__,
            _truncate(str(e), 200),
        )
        logger.debug("yt-dlp extraction failed for %s", post.url, exc_info=True)
        return [], False
    else:
        if url:
            return [url], False
        return [], False
    finally:
        if cookie_path:
            with contextlib.suppress(OSError):
                Path(cookie_path).unlink(missing_ok=True)


def _write_mozilla_cookies_file(cookies: dict[str, str]) -> str:
    """Write cookies as a Mozilla/Netscape cookies.txt; return the file path.

    yt-dlp's ``cookiefile`` option expects this format. The file is created
    with ``delete=False`` and is the caller's responsibility to remove
    (we delete it in ``_try_yt_dlp``'s ``finally`` block).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(_mozilla_cookies(cookies))
        f.flush()
        return f.name


def _mozilla_cookies(cookies: dict[str, str]) -> str:
    r"""Format cookies as a Mozilla/Netscape cookies.txt body.

    Each non-comment line is:
        <domain>\t<include_subdomains>\t<path>\t<secure>\t<expiration>\t<name>\t<value>
    """
    lines = ["# Netscape HTTP Cookie File"]
    for name, value in cookies.items():
        lines.append(f".reddit.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    return "\n".join(lines) + "\n"


def _pick_yt_dlp_url(info: object) -> str | None:
    """Return the best direct media URL from a yt-dlp result, or ``None``."""
    if not isinstance(info, dict):
        return None
    url = info.get("url")
    if isinstance(url, str) and url:
        return url
    for fmt in info.get("formats") or ():
        u = fmt.get("url") if isinstance(fmt, dict) else None
        if isinstance(u, str) and u:
            return u
    return None
