import feedparser

from reddit_feeds.config.models import FeedConfig
from reddit_feeds.feed.builder import _infer_mime, build_feed
from reddit_feeds.feed.models import MediaPost
from reddit_feeds.feed.writer import write_feed
from reddit_feeds.reddit.models import RedditPost


def make_feed_config(name: str = "python") -> FeedConfig:
    return FeedConfig(name=name, url=f"https://reddit.com/r/{name}/.json")


def make_media_post(media_urls: list[str], **overrides) -> MediaPost:
    post = RedditPost(
        id=overrides.get("id", "abc123"),
        title=overrides.get("title", "Test Post"),
        author=overrides.get("author", "user"),
        permalink=overrides.get("permalink", "https://reddit.com/r/python/comments/abc123/test/"),
        url=overrides.get("url", media_urls[0] if media_urls else ""),
        created_utc=overrides.get("created_utc", 1700000000.0),
        post_hint=overrides.get("post_hint", "image"),
    )
    return MediaPost(post=post, media_urls=media_urls)


class TestBuildFeed:
    def test_feed_title_and_link(self):
        xml = build_feed(make_feed_config("python"), [])
        parsed = feedparser.parse(xml)
        assert parsed.feed.title == "r/python"
        assert "reddit.com/r/python" in parsed.feed.link

    def test_single_image_item_has_enclosure(self):
        posts = [make_media_post(["https://i.redd.it/abc123.jpg"])]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)

        assert len(parsed.entries) == 1
        assert len(parsed.entries[0].enclosures) == 1
        assert parsed.entries[0].enclosures[0].url == "https://i.redd.it/abc123.jpg"
        assert parsed.entries[0].enclosures[0].type == "image/jpeg"

    def test_single_image_in_description(self):
        posts = [make_media_post(["https://i.redd.it/abc123.jpg"])]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert 'src="https://i.redd.it/abc123.jpg"' in parsed.entries[0].summary

    def test_gallery_all_images_in_description(self):
        urls = ["https://i.redd.it/img1.jpg", "https://i.redd.it/img2.png", "https://i.redd.it/img3.gif"]
        posts = [make_media_post(urls)]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)

        description = parsed.entries[0].summary
        assert "img1.jpg" in description
        assert "img2.png" in description
        assert "img3.gif" in description
        assert description.count("<img") == 3

    def test_gallery_enclosure_is_first_url(self):
        urls = ["https://i.redd.it/first.jpg", "https://i.redd.it/second.png"]
        posts = [make_media_post(urls)]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert parsed.entries[0].enclosures[0].url == "https://i.redd.it/first.jpg"

    def test_video_url_uses_video_tag_in_description(self):
        posts = [make_media_post(["https://v.redd.it/abc123.mp4"], post_hint=None)]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert "<video" in parsed.entries[0].summary

    def test_video_enclosure_has_video_mime(self):
        posts = [make_media_post(["https://v.redd.it/abc.mp4"], post_hint=None)]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert parsed.entries[0].enclosures[0].type == "video/mp4"

    def test_multiple_posts_all_appear(self):
        posts = [
            make_media_post(["https://i.redd.it/a.jpg"], id="a", title="Post A"),
            make_media_post(["https://i.redd.it/b.png"], id="b", title="Post B"),
        ]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert len(parsed.entries) == 2

    def test_empty_posts_list_produces_valid_feed(self):
        xml = build_feed(make_feed_config(), [])
        parsed = feedparser.parse(xml)
        assert parsed.feed.title == "r/python"
        assert len(parsed.entries) == 0


class TestInferMime:
    def test_jpeg_extensions(self):
        assert _infer_mime("https://example.com/img.jpg") == "image/jpeg"
        assert _infer_mime("https://example.com/img.jpeg") == "image/jpeg"

    def test_png(self):
        assert _infer_mime("https://example.com/img.png") == "image/png"

    def test_gif(self):
        assert _infer_mime("https://example.com/img.gif") == "image/gif"

    def test_mp4(self):
        assert _infer_mime("https://example.com/vid.mp4") == "video/mp4"

    def test_webm(self):
        assert _infer_mime("https://example.com/vid.webm") == "video/webm"

    def test_unknown_extension(self):
        assert _infer_mime("https://example.com/file.xyz") == "application/octet-stream"

    def test_url_with_query_string(self):
        assert _infer_mime("https://example.com/img.jpg?size=large") == "image/jpeg"


class TestWriteFeed:
    async def test_write_feed_creates_file(self, tmp_path):
        config = make_feed_config("python")
        await write_feed("<rss/>", config, tmp_path)
        assert (tmp_path / "python.xml").exists()

    async def test_write_feed_content_matches(self, tmp_path):
        config = make_feed_config("python")
        xml = "<rss><channel><title>r/python</title></channel></rss>"
        await write_feed(xml, config, tmp_path)
        content = (tmp_path / "python.xml").read_text()
        assert content == xml

    async def test_write_feed_slugifies_name(self, tmp_path):
        config = make_feed_config("My Feed Name!")
        await write_feed("<rss/>", config, tmp_path)
        assert (tmp_path / "my-feed-name.xml").exists()

    async def test_write_feed_creates_output_dir_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b" / "feeds"
        config = make_feed_config("python")
        await write_feed("<rss/>", config, nested)
        assert (nested / "python.xml").exists()

    async def test_write_feed_overwrites_existing(self, tmp_path):
        config = make_feed_config("python")
        (tmp_path / "python.xml").write_text("old content")
        await write_feed("new content", config, tmp_path)
        assert (tmp_path / "python.xml").read_text() == "new content"
