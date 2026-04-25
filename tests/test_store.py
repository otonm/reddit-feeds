"""Tests for the store module (StoredItem, SeenStore, FeedStore)."""



from store.feed_store import FeedStore
from store.models import StoredItem
from store.seen_store import SeenStore


def make_stored_item(**kwargs) -> StoredItem:
    defaults = {
        "id": "abc123",
        "title": "Test Post",
        "permalink": "https://reddit.com/r/test/comments/abc123/test/",
        "created_utc": 1700000000.0,
        "media_urls": ["https://i.redd.it/test.jpg"],
    }
    return StoredItem(**{**defaults, **kwargs})


class TestStoredItem:
    def test_to_dict_round_trip(self):
        item = make_stored_item()
        assert StoredItem.from_dict(item.to_dict()) == item

    def test_to_dict_has_expected_keys(self):
        d = make_stored_item().to_dict()
        assert set(d.keys()) == {"id", "title", "permalink", "created_utc", "media_urls"}

    def test_multiple_media_urls_preserved(self):
        item = make_stored_item(media_urls=["https://a.com/1.jpg", "https://a.com/2.jpg"])
        assert StoredItem.from_dict(item.to_dict()).media_urls == item.media_urls


class TestSeenStore:
    async def test_empty_when_file_missing(self, tmp_path):
        store = SeenStore(tmp_path)
        await store.load()
        assert not store.contains("https://example.com/image.jpg")

    async def test_add_and_contains(self, tmp_path):
        store = SeenStore(tmp_path)
        await store.load()
        store.add("https://example.com/image.jpg")
        assert store.contains("https://example.com/image.jpg")
        assert not store.contains("https://other.com/image.jpg")

    async def test_add_many(self, tmp_path):
        store = SeenStore(tmp_path)
        await store.load()
        store.add_many(["https://a.com/1.jpg", "https://b.com/2.jpg"])
        assert store.contains("https://a.com/1.jpg")
        assert store.contains("https://b.com/2.jpg")

    async def test_save_and_reload_persists_entries(self, tmp_path):
        store = SeenStore(tmp_path)
        await store.load()
        store.add("https://example.com/image.jpg")
        await store.save()

        store2 = SeenStore(tmp_path)
        await store2.load()
        assert store2.contains("https://example.com/image.jpg")

    async def test_saves_to_seen_json(self, tmp_path):
        store = SeenStore(tmp_path)
        await store.load()
        store.add("https://example.com/img.jpg")
        await store.save()
        assert (tmp_path / "seen.json").exists()

    async def test_creates_db_dir_if_missing(self, tmp_path):
        db_dir = tmp_path / "newdir"
        store = SeenStore(db_dir)
        await store.load()
        store.add("https://example.com/img.jpg")
        await store.save()
        assert (db_dir / "seen.json").exists()

    async def test_corrupt_file_starts_fresh(self, tmp_path):
        corrupt = tmp_path / "seen.json"
        corrupt.write_text("not valid json{{{")
        store = SeenStore(tmp_path)
        await store.load()
        assert not store.contains("https://example.com/img.jpg")


class TestFeedStore:
    async def test_empty_when_file_missing(self, tmp_path):
        store = FeedStore(tmp_path, "my-feed")
        assert await store.load() == []

    async def test_save_and_load_round_trip(self, tmp_path):
        store = FeedStore(tmp_path, "my-feed")
        item = make_stored_item()
        await store.save([item])

        store2 = FeedStore(tmp_path, "my-feed")
        loaded = await store2.load()
        assert loaded == [item]

    async def test_saves_to_slug_json(self, tmp_path):
        store = FeedStore(tmp_path, "my-feed")
        await store.save([make_stored_item()])
        assert (tmp_path / "my-feed.json").exists()

    async def test_creates_db_dir_if_missing(self, tmp_path):
        db_dir = tmp_path / "newdir"
        store = FeedStore(db_dir, "my-feed")
        await store.save([make_stored_item()])
        assert (db_dir / "my-feed.json").exists()

    async def test_multiple_items_with_multiple_media_urls(self, tmp_path):
        store = FeedStore(tmp_path, "my-feed")
        items = [
            make_stored_item(id="post1"),
            make_stored_item(id="post2", media_urls=["https://a.com/1.mp4", "https://a.com/2.jpg"]),
        ]
        await store.save(items)
        assert await store.load() == items

    async def test_corrupt_file_returns_empty(self, tmp_path):
        corrupt = tmp_path / "my-feed.json"
        corrupt.write_text("not valid json{{{")
        store = FeedStore(tmp_path, "my-feed")
        items = await store.load()
        assert items == []
