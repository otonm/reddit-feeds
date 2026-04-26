"""Async runner: orchestrates fetching, extraction, building, and writing for all feeds."""

import asyncio
import logging
import tempfile
import time
from dataclasses import dataclass
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


@dataclass
class FeedResult:
    """Result of processing a single feed in one run."""

    name: str
    new_item_count: int = 0
    failure: str | None = None


async def run_once(settings: Settings) -> list[FeedResult]:
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
        gather_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[FeedResult] = []
    for feed, outcome in zip(settings.feeds, gather_results, strict=True):
        if isinstance(outcome, FeedResult):
            results.append(outcome)
        else:
            results.append(FeedResult(name=feed.name, failure="internal error"))

    await seen.save()

    if settings.base_url:
        try:
            await write_opml(build_opml(settings.feeds, settings.base_url), settings.output_dir)
        except Exception:
            logger.exception("Failed to write feeds.opml")

    elapsed = time.monotonic() - t0
    new_count = sum(1 for r in results if r.new_item_count > 0)
    fail_count = sum(1 for r in results if r.failure)

    for r in results:
        if r.failure:
            logger.info("[%s] FAILED (%s)", r.name, r.failure)
        else:
            logger.info("[%s] %d new item(s)", r.name, r.new_item_count)

    logger.info(
        "Run complete: %d feed(s) in %.1fs — %d with new items, %d failed",
        len(results),
        elapsed,
        new_count,
        fail_count,
    )
    sentinel = Path(tempfile.gettempdir()) / "reddit-feeds.last_run"
    await asyncio.get_event_loop().run_in_executor(None, sentinel.touch)
    return results


async def process_feed(feed: FeedConfig, settings: Settings, client: httpx.AsyncClient, seen: SeenStore) -> FeedResult:
    """Fetch, deduplicate, merge, and write a single feed incrementally."""
    logger.info("[%s] Fetching %d posts from %s", feed.name, feed.fetch_count, feed.url)
    try:
        posts = await fetch_posts(feed.url, feed.fetch_count, client)
        logger.debug("[%s] Received %d posts from Reddit", feed.name, len(posts))
    except (httpx.HTTPError, KeyError, ValueError):
        logger.warning("[%s] Failed to fetch posts", feed.name, exc_info=True)
        return FeedResult(name=feed.name, failure="fetch error")

    feed_slug = slugify(feed.name)
    feed_store = FeedStore(settings.db_dir, feed_slug)
    existing_items = await feed_store.load()

    new_items: list[StoredItem] = []
    for post in posts:
        if seen.contains(post.url):
            logger.debug("[%s] Skipping post %s: post.url already seen", feed.name, post.id)
            continue

        urls = await extract_media_urls_async(post)

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
        return FeedResult(name=feed.name, new_item_count=len(new_items), failure="write error")

    return FeedResult(name=feed.name, new_item_count=len(new_items))


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
