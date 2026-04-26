from pathlib import Path
from unittest.mock import AsyncMock, patch

import feedparser
import httpx
from slugify import slugify

from config.models import FeedConfig, Settings
from reddit.models import RedditPost
from runner import process_feed, run_once
from store.feed_store import FeedStore
from store.models import StoredItem
from store.seen_store import SeenStore


def make_settings(tmp_path: Path, feeds: list[FeedConfig] | None = None) -> Settings:
    return Settings(
        output_dir=tmp_path / "output",
        db_dir=tmp_path / "db",
        interval=900,
        feeds=feeds or [FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)],
        log_level="INFO",
        reddit_fetch_gap=0.0,
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


def make_seen_store(tmp_path: Path) -> SeenStore:
    return SeenStore(tmp_path / "db")


class TestProcessFeed:
    async def test_process_feed_writes_file(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])
        seen = make_seen_store(tmp_path)
        post = make_reddit_post()

        with (
            patch("runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("runner.extract_media_urls_async", AsyncMock(return_value=["https://i.redd.it/abc.jpg"])),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client, seen)

        assert (settings.output_dir / "python.xml").exists()

    async def test_process_feed_skips_posts_with_no_media(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])
        seen = make_seen_store(tmp_path)
        post = make_reddit_post()

        written_posts: list = []

        async def mock_write(xml, fc, od):
            written_posts.extend(feedparser.parse(xml).entries)

        with (
            patch("runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("runner.extract_media_urls_async", AsyncMock(return_value=[])),
            patch("runner.write_feed", side_effect=mock_write),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client, seen)

        assert written_posts == []

    async def test_process_feed_skips_post_whose_url_is_already_seen(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])
        seen = make_seen_store(tmp_path)
        post = make_reddit_post(url="https://i.redd.it/abc.jpg")
        seen.add("https://i.redd.it/abc.jpg")  # mark post.url as seen

        mock_extract = AsyncMock(return_value=["https://i.redd.it/abc.jpg"])
        with (
            patch("runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("runner.extract_media_urls_async", mock_extract),
            patch("runner.write_feed", AsyncMock()),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client, seen)

        mock_extract.assert_not_called()  # fast pre-filter: no extraction for seen posts

    async def test_process_feed_skips_when_all_media_urls_already_seen(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])
        seen = make_seen_store(tmp_path)
        post = make_reddit_post(url="https://i.redd.it/abc.jpg")
        # post.url not seen, but its media URLs are
        seen.add("https://i.redd.it/media1.jpg")
        seen.add("https://i.redd.it/media2.jpg")

        written_posts: list = []

        async def mock_write(xml, fc, od):
            written_posts.extend(feedparser.parse(xml).entries)

        with (
            patch("runner.fetch_posts", AsyncMock(return_value=[post])),
            patch(
                "runner.extract_media_urls_async",
                AsyncMock(return_value=["https://i.redd.it/media1.jpg", "https://i.redd.it/media2.jpg"]),
            ),
            patch("runner.write_feed", side_effect=mock_write),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client, seen)

        assert written_posts == []

    async def test_process_feed_partial_repost_shows_only_new_media(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])
        seen = make_seen_store(tmp_path)
        post = make_reddit_post(url="https://i.redd.it/new_gallery.jpg")
        seen.add("https://i.redd.it/media1.jpg")  # one of the gallery images is already seen

        captured_items: list = []

        async def mock_write(xml, fc, od):
            captured_items.extend(feedparser.parse(xml).entries)

        with (
            patch("runner.fetch_posts", AsyncMock(return_value=[post])),
            patch(
                "runner.extract_media_urls_async",
                AsyncMock(return_value=["https://i.redd.it/media1.jpg", "https://i.redd.it/media2.jpg"]),
            ),
            patch("runner.write_feed", side_effect=mock_write),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client, seen)

        # Post is included, but only with the new media URL
        assert len(captured_items) == 1
        assert "media2.jpg" in captured_items[0].get("summary", "")
        assert "media1.jpg" not in captured_items[0].get("summary", "")

    async def test_process_feed_appends_to_existing_items(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])
        seen = make_seen_store(tmp_path)

        # Seed the feed store with a prior item
        prior_item = StoredItem(
            id="prior",
            title="Prior Post",
            permalink="https://reddit.com/r/python/comments/prior/",
            created_utc=1699000000.0,
            media_urls=["https://i.redd.it/prior.jpg"],
        )
        store = FeedStore(settings.db_dir, slugify(config.name))
        await store.save([prior_item])

        new_post = make_reddit_post(id="new", url="https://i.redd.it/new.jpg", created_utc=1700000000.0)
        written_entries: list = []

        async def mock_write(xml, fc, od):
            written_entries.extend(feedparser.parse(xml).entries)

        with (
            patch("runner.fetch_posts", AsyncMock(return_value=[new_post])),
            patch("runner.extract_media_urls_async", AsyncMock(return_value=["https://i.redd.it/new.jpg"])),
            patch("runner.write_feed", side_effect=mock_write),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client, seen)

        assert len(written_entries) == 2  # prior + new

    async def test_process_feed_fetch_failure_does_not_raise(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])
        seen = make_seen_store(tmp_path)

        with patch("runner.fetch_posts", AsyncMock(side_effect=httpx.HTTPError("network error"))):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client, seen)  # must not raise

    async def test_process_feed_write_failure_does_not_raise(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])
        seen = make_seen_store(tmp_path)
        post = make_reddit_post()

        with (
            patch("runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("runner.extract_media_urls_async", AsyncMock(return_value=["https://i.redd.it/abc.jpg"])),
            patch("runner.write_feed", AsyncMock(side_effect=OSError("disk full"))),
        ):
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client, seen)  # must not raise


class TestCleanupRemovedFeeds:
    async def test_cleanup_removes_orphaned_xml_and_json(self, tmp_path):
        """Files for feeds no longer in config are deleted on run_once."""
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])

        # Create orphaned output and db files for a feed that is no longer configured
        output_dir = settings.output_dir
        db_dir = settings.db_dir
        output_dir.mkdir(parents=True)
        db_dir.mkdir(parents=True)
        orphan_xml = output_dir / "rust.xml"
        orphan_json = db_dir / "rust.json"
        orphan_xml.write_text("<rss/>")
        orphan_json.write_text("[]")
        # seen.json must be preserved
        seen_json = db_dir / "seen.json"
        seen_json.write_text("[]")

        async def mock_process_feed(feed, s, client, seen):
            pass

        with patch("runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)

        assert not orphan_xml.exists(), "orphaned XML should have been removed"
        assert not orphan_json.exists(), "orphaned JSON store should have been removed"
        assert seen_json.exists(), "seen.json must not be removed"

    async def test_cleanup_keeps_configured_feed_files(self, tmp_path):
        """Files for feeds still in config are not deleted."""
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        settings = make_settings(tmp_path, [config])

        output_dir = settings.output_dir
        db_dir = settings.db_dir
        output_dir.mkdir(parents=True)
        db_dir.mkdir(parents=True)
        kept_xml = output_dir / "python.xml"
        kept_json = db_dir / "python.json"
        kept_xml.write_text("<rss/>")
        kept_json.write_text("[]")

        async def mock_process_feed(feed, s, client, seen):
            pass

        with patch("runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)

        assert kept_xml.exists(), "configured feed XML should not be removed"
        assert kept_json.exists(), "configured feed JSON store should not be removed"


class TestRunOnce:
    async def test_run_once_processes_all_feeds(self, tmp_path):
        feed1 = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        feed2 = FeedConfig(name="rust", url="https://reddit.com/r/rust/.json", fetch_count=5)
        settings = make_settings(tmp_path, [feed1, feed2])

        processed: list[str] = []

        async def mock_process_feed(feed, s, client, seen):
            processed.append(feed.name)

        with patch("runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)

        assert "python" in processed
        assert "rust" in processed

    async def test_run_once_one_feed_fails_others_complete(self, tmp_path):
        feed1 = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        feed2 = FeedConfig(name="rust", url="https://reddit.com/r/rust/.json", fetch_count=5)
        settings = make_settings(tmp_path, [feed1, feed2])

        processed: list[str] = []

        async def mock_process_feed(feed, s, client, seen):
            processed.append(feed.name)
            if feed.name == "python":
                msg = "python feed exploded"
                raise RuntimeError(msg)

        with patch("runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)  # must not raise

        assert "python" in processed
        assert "rust" in processed

    async def test_run_once_saves_seen_store(self, tmp_path):
        settings = make_settings(tmp_path)

        async def mock_process_feed(feed, s, client, seen):
            seen.add("https://i.redd.it/tracked.jpg")

        with patch("runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)

        # seen.json must exist and contain the URL added during processing
        seen2 = SeenStore(settings.db_dir)
        await seen2.load()
        assert seen2.contains("https://i.redd.it/tracked.jpg")

    async def test_run_once_staggers_feed_fetches(self, tmp_path):
        feed1 = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=5)
        feed2 = FeedConfig(name="rust", url="https://reddit.com/r/rust/.json", fetch_count=5)
        feed3 = FeedConfig(name="go", url="https://reddit.com/r/golang/.json", fetch_count=5)
        settings = make_settings(tmp_path, [feed1, feed2, feed3])
        settings = settings.model_copy(update={"reddit_fetch_gap": 0.1})

        sleep_calls: list[float] = []

        async def tracking_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with (
            patch("runner.asyncio.sleep", side_effect=tracking_sleep),
            patch("runner.process_feed", new_callable=AsyncMock),
        ):
            await run_once(settings)

        assert len(sleep_calls) == 2  # one gap between each of the 3 feeds
        assert all(d == 0.1 for d in sleep_calls)

    async def test_run_once_writes_opml_when_base_url_set(self, tmp_path):
        settings = make_settings(tmp_path)
        settings = settings.model_copy(update={"base_url": "https://example.com"})

        with patch("runner.process_feed", new_callable=AsyncMock):
            await run_once(settings)

        assert (settings.output_dir / "feeds.opml").exists()

    async def test_run_once_skips_opml_when_base_url_is_none(self, tmp_path):
        settings = make_settings(tmp_path)  # base_url=None by default

        with patch("runner.process_feed", new_callable=AsyncMock):
            await run_once(settings)

        assert not (settings.output_dir / "feeds.opml").exists()

    async def test_run_once_opml_failure_does_not_raise(self, tmp_path):
        settings = make_settings(tmp_path)
        settings = settings.model_copy(update={"base_url": "https://example.com"})

        with (
            patch("runner.process_feed", new_callable=AsyncMock),
            patch("runner.write_opml", AsyncMock(side_effect=OSError("disk full"))),
        ):
            await run_once(settings)  # must not raise
