"""Tests for media URL extraction."""

from unittest.mock import MagicMock, patch

from reddit_feeds.media.extractor import extract_media_urls
from reddit_feeds.reddit.models import RedditPost


def make_post(**kwargs) -> RedditPost:
    defaults = {
        "id": "abc123",
        "title": "Test",
        "author": "user",
        "permalink": "https://reddit.com/r/test/comments/abc123/",
        "url": "https://i.redd.it/abc123.jpg",
        "created_utc": 1700000000.0,
        "post_hint": "image",
        "is_gallery": False,
    }
    defaults.update(kwargs)
    return RedditPost(**defaults)


def make_mock_extractor(url_messages: list[str]) -> MagicMock:
    """Build a mock gallery-dl extractor that yields Message.Url tuples."""
    mock = MagicMock()
    mock.__iter__ = MagicMock(
        return_value=iter([(3, url, {}) for url in url_messages])
    )
    return mock


class TestExtractMediaUrls:
    def test_single_image_via_gallery_dl(self):
        post = make_post(url="https://i.redd.it/abc123.jpg", post_hint="image")
        mock_extractor = make_mock_extractor(["https://i.redd.it/abc123.jpg"])

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/abc123.jpg"]

    def test_gallery_multiple_images(self):
        post = make_post(
            url="https://www.reddit.com/gallery/abc123",
            is_gallery=True,
            post_hint=None,
        )
        mock_extractor = make_mock_extractor([
            "https://i.redd.it/img1.jpg",
            "https://i.redd.it/img2.jpg",
        ])

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/img1.jpg", "https://i.redd.it/img2.jpg"]

    def test_fallback_to_direct_url_when_gallery_dl_returns_none(self):
        post = make_post(url="https://i.redd.it/direct.jpg", post_hint="image")

        with patch("gallery_dl.extractor.find", return_value=None):
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/direct.jpg"]

    def test_no_fallback_for_non_image_post_hint(self):
        post = make_post(url="https://example.com/article", post_hint="link")

        with patch("gallery_dl.extractor.find", return_value=None):
            urls = extract_media_urls(post)

        assert urls == []

    def test_text_post_returns_empty(self):
        post = make_post(url="https://self.reddit.com/r/test", post_hint="self")

        with patch("gallery_dl.extractor.find", return_value=None):
            urls = extract_media_urls(post)

        assert urls == []

    def test_gallery_dl_exception_returns_empty_list(self):
        post = make_post(url="https://example.com/video", post_hint=None)

        with patch("gallery_dl.extractor.find", side_effect=Exception("network error")):
            urls = extract_media_urls(post)

        assert urls == []

    def test_gallery_dl_iteration_exception_returns_empty_list(self):
        post = make_post(url="https://example.com/img.jpg", post_hint="image")
        mock_extractor = MagicMock()
        mock_extractor.__iter__ = MagicMock(side_effect=RuntimeError("extraction failed"))

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == []

    def test_non_url_messages_are_ignored(self):
        """Message type 1 (Directory) and 2 (Queue) should not be added to urls."""
        post = make_post(url="https://i.redd.it/abc.jpg", post_hint="image")
        mock_extractor = MagicMock()
        mock_extractor.__iter__ = MagicMock(return_value=iter([
            (1, {"category": "reddit"}, {}),
            (3, "https://i.redd.it/abc.jpg", {}),
        ]))

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/abc.jpg"]
