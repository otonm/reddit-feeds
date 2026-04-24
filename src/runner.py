"""Async runner: orchestrates fetching, extraction, building, and writing for all feeds."""

import asyncio
import logging
import time
from pathlib import Path

import httpx

from config.models import FeedConfig, Settings
from feed.builder import build_feed
from feed.models import MediaPost
from feed.writer import write_feed
from media.extractor import extract_media_urls_async
from reddit.client import fetch_posts

logger = logging.getLogger(__name__)


async def run_once(settings: Settings) -> None:
    """Fetch and publish all configured feeds concurrently."""
    feed_names = [f.name for f in settings.feeds]
    logger.info("Starting run: %d feed(s): %s", len(settings.feeds), ", ".join(feed_names))
    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        await asyncio.gather(
            *[process_feed(feed, settings, client) for feed in settings.feeds],
            return_exceptions=True,
        )
    logger.info("Run complete in %.1fs", time.monotonic() - t0)
    Path("/tmp/reddit-feeds.last_run").touch()  # noqa: S108, ASYNC240


async def process_feed(feed: FeedConfig, settings: Settings, client: httpx.AsyncClient) -> None:
    """Fetch, extract, build, and write a single feed. Logs and returns on any error."""
    logger.debug("[%s] Starting pipeline (url=%s)", feed.name, feed.url)
    logger.info("[%s] Fetching %d posts from %s", feed.name, feed.fetch_items, feed.url)
    try:
        posts = await fetch_posts(feed.url, feed.fetch_items, client)
        logger.debug("[%s] Received %d posts from Reddit", feed.name, len(posts))
    except Exception:
        logger.warning("[%s] Failed to fetch posts", feed.name, exc_info=True)
        return

    media_posts: list[MediaPost] = []
    for post in posts:
        try:
            urls = await extract_media_urls_async(post)
            if urls:
                media_posts.append(MediaPost(post=post, media_urls=urls))
                logger.debug("[%s] Post %s: %d media URL(s)", feed.name, post.id, len(urls))
            else:
                logger.debug("[%s] Skipping post %s: no media", feed.name, post.id)
        except Exception:
            logger.warning("[%s] Extraction failed for post %s", feed.name, post.id, exc_info=True)

    logger.info("[%s] %d/%d posts have media", feed.name, len(media_posts), len(posts))

    try:
        xml = build_feed(feed, media_posts)
        await write_feed(xml, feed, settings.output_dir)
        logger.info("[%s] Feed written to %s", feed.name, settings.output_dir)
    except Exception:
        logger.exception("[%s] Failed to write feed", feed.name)
