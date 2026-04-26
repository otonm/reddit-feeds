"""Async runner: orchestrates fetching, extraction, building, and writing for all feeds."""

import asyncio
import logging
import time
from pathlib import Path

import aiofiles.os
import httpx
from slugify import slugify

from config.models import FeedConfig, Settings
from feed.builder import build_feed
from feed.opml import build_opml, write_opml
from feed.writer import write_feed
from media.extractor import extract_media_urls_async
from reddit.client import fetch_posts
from store.feed_store import FeedStore
from store.models import StoredItem
from store.seen_store import SeenStore

logger = logging.getLogger(__name__)


async def run_once(settings: Settings) -> None:
    """Fetch and publish all configured feeds concurrently."""
    await _cleanup_removed_feeds(settings)

    seen = SeenStore(settings.db_dir)
    await seen.load()

    feed_names = [f.name for f in settings.feeds]
    logger.info("Starting run: %d feed(s): %s", len(settings.feeds), ", ".join(feed_names))
    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        tasks = []
        for i, feed in enumerate(settings.feeds):
            if i > 0 and settings.reddit_fetch_gap > 0:
                await asyncio.sleep(settings.reddit_fetch_gap)
            tasks.append(asyncio.create_task(process_feed(feed, settings, client, seen)))
        await asyncio.gather(*tasks, return_exceptions=True)

    await seen.save()

    if settings.base_url:
        try:
            await write_opml(build_opml(settings.feeds, settings.base_url), settings.output_dir)
        except Exception:
            logger.exception("Failed to write feeds.opml")

    logger.info("Run complete in %.1fs", time.monotonic() - t0)
    Path("/tmp/reddit-feeds.last_run").touch()  # noqa: S108, ASYNC240


async def process_feed(feed: FeedConfig, settings: Settings, client: httpx.AsyncClient, seen: SeenStore) -> None:
    """Fetch, deduplicate, merge, and write a single feed incrementally."""
    logger.info("[%s] Fetching %d posts from %s", feed.name, feed.fetch_count, feed.url)
    try:
        posts = await fetch_posts(feed.url, feed.fetch_count, client)
        logger.debug("[%s] Received %d posts from Reddit", feed.name, len(posts))
    except Exception:
        logger.warning("[%s] Failed to fetch posts", feed.name, exc_info=True)
        return

    feed_slug = slugify(feed.name)
    feed_store = FeedStore(settings.db_dir, feed_slug)
    existing_items = await feed_store.load()

    new_items: list[StoredItem] = []
    for post in posts:
        if seen.contains(post.url):
            logger.debug("[%s] Skipping post %s: post.url already seen", feed.name, post.id)
            continue

        try:
            urls = await extract_media_urls_async(post)
        except Exception:
            logger.warning("[%s] Extraction failed for post %s", feed.name, post.id, exc_info=True)
            continue

        if not urls:
            logger.debug("[%s] Skipping post %s: no media", feed.name, post.id)
            continue

        # Cross-feed dedup is best-effort: concurrent coroutines can interleave between
        # contains() and add(), so rare duplicates across feeds are possible.
        new_urls = [u for u in urls if not seen.contains(u)]
        if not new_urls:
            logger.debug("[%s] Skipping post %s: all media URLs already seen", feed.name, post.id)
            seen.add(post.url)
            continue

        new_items.append(
            StoredItem(
                id=post.id,
                title=post.title,
                permalink=post.permalink,
                created_utc=post.created_utc,
                media_urls=new_urls,
            )
        )
        seen.add(post.url)
        seen.add_many(new_urls)
        logger.debug("[%s] Post %s: %d new media URL(s)", feed.name, post.id, len(new_urls))

    logger.info("[%s] %d new post(s) with media (of %d fetched)", feed.name, len(new_items), len(posts))

    all_items = existing_items + new_items
    all_items.sort(key=lambda x: x.created_utc, reverse=True)

    try:
        await feed_store.save(all_items)
        xml = build_feed(feed, all_items)
        await write_feed(xml, feed, settings.output_dir)
        logger.info("[%s] Feed written: %d total items", feed.name, len(all_items))
    except Exception:
        logger.exception("[%s] Failed to write feed", feed.name)


async def _cleanup_removed_feeds(settings: Settings) -> None:
    """Delete XML and DB files for feeds no longer present in the config."""
    expected_slugs = {slugify(f.name) for f in settings.feeds}

    if settings.output_dir.exists():
        for xml_file in settings.output_dir.glob("*.xml"):
            if xml_file.stem not in expected_slugs:
                logger.info("Removing orphaned feed file: %s", xml_file)
                await aiofiles.os.remove(xml_file)

    if settings.db_dir.exists():
        for json_file in settings.db_dir.glob("*.json"):
            if json_file.stem == "seen":
                continue
            if json_file.stem not in expected_slugs:
                logger.info("Removing orphaned feed DB: %s", json_file)
                await aiofiles.os.remove(json_file)
