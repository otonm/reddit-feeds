from pathlib import Path
from unittest.mock import AsyncMock, patch

import feedparser
import httpx

from reddit_feeds.config.models import FeedConfig, Settings
from reddit_feeds.reddit.models import RedditPost
from reddit_feeds.runner import process_feed, run_once


def make_settings(tmp_path: Path, feeds: list[FeedConfig] | None = None) -> Settings:
    return Settings(
        output_dir=tmp_path,
        interval=900,
        feeds=feeds or [FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)],
        log_level="INFO",
    )


def make_reddit_post(**overrides) -> RedditPost:
    defaults = {
        "id": "abc",
        "title": "Test",
        "author": "user",
        "permalink": "https://reddit.com/r/python/comments/abc/",
        "url": "https://i.redd.it/abc.jpg",
        "created_utc": 1700000000.0,
        "post_hint": "image",
    }
    defaults.update(overrides)
    return RedditPost(**defaults)


class TestProcessFeed:
    async def test_process_feed_writes_file(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])
        post = make_reddit_post()

        with (
            patch("reddit_feeds.runner.fetch_posts", AsyncMock(return_value=[post])),
            patch(
                "reddit_feeds.runner.extract_media_urls_async", AsyncMock(return_value=["https://i.redd.it/abc.jpg"])
            ),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)

        assert (tmp_path / "python.xml").exists()

    async def test_process_feed_skips_posts_with_no_media(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])
        post = make_reddit_post()

        written_posts: list = []

        async def mock_write(xml, fc, od):
            parsed = feedparser.parse(xml)
            written_posts.extend(parsed.entries)

        with (
            patch("reddit_feeds.runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("reddit_feeds.runner.extract_media_urls_async", AsyncMock(return_value=[])),
            patch("reddit_feeds.runner.write_feed", side_effect=mock_write),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)

        assert written_posts == []

    async def test_process_feed_fetch_failure_does_not_raise(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])

        with patch("reddit_feeds.runner.fetch_posts", AsyncMock(side_effect=Exception("network error"))):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)  # must not raise

    async def test_process_feed_extraction_failure_skips_post(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])
        post = make_reddit_post()

        with (
            patch("reddit_feeds.runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("reddit_feeds.runner.extract_media_urls_async", AsyncMock(side_effect=Exception("gallery-dl broke"))),
            patch("reddit_feeds.runner.write_feed", AsyncMock()) as mock_write,
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)

        xml_arg = mock_write.call_args[0][0]
        assert len(feedparser.parse(xml_arg).entries) == 0

    async def test_process_feed_write_failure_does_not_raise(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])
        post = make_reddit_post()

        with (
            patch("reddit_feeds.runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("reddit_feeds.runner.extract_media_urls_async", AsyncMock(return_value=["https://i.redd.it/abc.jpg"])),
            patch("reddit_feeds.runner.write_feed", AsyncMock(side_effect=OSError("disk full"))),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)  # must not raise


class TestRunOnce:
    async def test_run_once_processes_all_feeds(self, tmp_path):
        feed1 = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        feed2 = FeedConfig(name="rust", url="https://reddit.com/r/rust/.json", fetch_items=5)
        settings = make_settings(tmp_path, [feed1, feed2])

        processed: list[str] = []

        async def mock_process_feed(feed, s, client):
            processed.append(feed.name)

        with patch("reddit_feeds.runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)

        assert "python" in processed
        assert "rust" in processed

    async def test_run_once_one_feed_fails_others_complete(self, tmp_path):
        feed1 = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        feed2 = FeedConfig(name="rust", url="https://reddit.com/r/rust/.json", fetch_items=5)
        settings = make_settings(tmp_path, [feed1, feed2])

        processed: list[str] = []

        async def mock_process_feed(feed, s, client):
            processed.append(feed.name)
            if feed.name == "python":
                raise RuntimeError("python feed exploded")

        with patch("reddit_feeds.runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)  # must not raise

        assert "python" in processed
        assert "rust" in processed
