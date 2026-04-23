"""Async runner: orchestrates fetching, extraction, building, and writing for all feeds."""

import asyncio
import logging

import httpx

from reddit_feeds.config.models import FeedConfig, Settings
from reddit_feeds.feed.builder import build_feed
from reddit_feeds.feed.models import MediaPost
from reddit_feeds.feed.writer import write_feed
from reddit_feeds.media.extractor import extract_media_urls_async
from reddit_feeds.reddit.client import fetch_posts

logger = logging.getLogger(__name__)


async def run_once(settings: Settings) -> None:
    """Fetch and publish all configured feeds concurrently."""
    async with httpx.AsyncClient() as client:
        await asyncio.gather(
            *[process_feed(feed, settings, client) for feed in settings.feeds],
            return_exceptions=True,
        )


async def process_feed(feed: FeedConfig, settings: Settings, client: httpx.AsyncClient) -> None:
    """Fetch, extract, build, and write a single feed. Logs and returns on any error."""
    logger.info("[%s] Fetching %d posts from %s", feed.name, feed.fetch_items, feed.url)
    try:
        posts = await fetch_posts(feed.url, feed.fetch_items, client)
    except Exception:  # noqa: BLE001
        logger.warning("[%s] Failed to fetch posts", feed.name, exc_info=True)
        return

    media_posts: list[MediaPost] = []
    for post in posts:
        try:
            urls = await extract_media_urls_async(post)
            if urls:
                media_posts.append(MediaPost(post=post, media_urls=urls))
            else:
                logger.debug("[%s] Skipping post %s: no media", feed.name, post.id)
        except Exception:  # noqa: BLE001
            logger.warning("[%s] Extraction failed for post %s", feed.name, post.id, exc_info=True)

    logger.info("[%s] %d/%d posts have media", feed.name, len(media_posts), len(posts))

    try:
        xml = build_feed(feed, media_posts)
        await write_feed(xml, feed, settings.output_dir)
        logger.info("[%s] Feed written to %s/%s.xml", feed.name, settings.output_dir, feed.name)
    except Exception:
        logger.exception("[%s] Failed to write feed", feed.name)
