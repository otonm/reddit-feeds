"""Tests for media URL extraction."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

from media.extractor import extract_media_urls, extract_media_urls_async
from reddit.models import RedditPost


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
    mock.__iter__ = MagicMock(return_value=iter([(3, url, {}) for url in url_messages]))
    return mock


class TestExtractMediaUrls:
    def test_direct_media_url_skips_gallery_dl(self):
        """URLs with known media extensions bypass gallery-dl and are returned as-is."""
        for url in [
            "https://i.redd.it/abc123.jpg",
            "https://live.staticflickr.com/65535/photo_4k.jpg",
            "https://example.com/clip.mp4",
            "https://example.com/anim.gif",
        ]:
            post = make_post(url=url, post_hint="image")
            with patch("gallery_dl.extractor.find") as mock_find:
                urls = extract_media_urls(post)
            assert urls == [url]
            mock_find.assert_not_called()

    def test_direct_url_with_query_string_recognised(self):
        url = "https://example.com/photo.png?size=large"
        post = make_post(url=url, post_hint="image")
        with patch("gallery_dl.extractor.find") as mock_find:
            urls = extract_media_urls(post)
        assert urls == [url]
        mock_find.assert_not_called()

    def test_single_image_via_gallery_dl(self):
        post = make_post(url="https://imgur.com/abc123", post_hint="image")
        mock_extractor = make_mock_extractor(["https://i.imgur.com/abc123.jpg"])

        with patch("gallery_dl.extractor.find", return_value=mock_extractor) as mock_find:
            urls = extract_media_urls(post)

        assert urls == ["https://i.imgur.com/abc123.jpg"]
        mock_find.assert_called_once_with("https://imgur.com/abc123")

    def test_gallery_multiple_images(self):
        post = make_post(
            url="https://www.reddit.com/r/test/comments/abc123/kitten_pics/gallery",
            permalink="https://www.reddit.com/r/test/comments/abc123/kitten_pics/",
            is_gallery=True,
            post_hint="image",
        )
        mock_extractor = make_mock_extractor(
            [
                "https://i.redd.it/img1.jpg",
                "https://i.redd.it/img2.jpg",
            ]
        )

        with patch("gallery_dl.extractor.find", return_value=mock_extractor) as mock_find:
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/img1.jpg", "https://i.redd.it/img2.jpg"]
        # For a gallery post, gallery-dl is invoked with the post permalink, not the gallery URL,
        # so it can fetch the post page and resolve all gallery image URLs.
        called_with = mock_find.call_args.args[0]
        assert called_with == "https://www.reddit.com/r/test/comments/abc123/kitten_pics/"

    def test_v_redd_it_url_uses_yt_dlp_with_permalink(self):
        """For hosted:video posts, yt-dlp is called with the post permalink and its URL is returned."""
        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )

        with patch("yt_dlp.YoutubeDL") as mock_cls:
            mock_ydl = mock_cls.return_value.__enter__.return_value
            mock_ydl.extract_info.return_value = {
                "url": "https://v.redd.it/vid001/DASH_720.mp4?source=fallback",
            }
            urls = extract_media_urls(post)

        assert urls == ["https://v.redd.it/vid001/DASH_720.mp4?source=fallback"]
        # yt-dlp was called with the permalink (not the bare v.redd.it URL).
        called_url = mock_ydl.extract_info.call_args.args[0]
        assert called_url == "https://www.reddit.com/r/aww/comments/vid001/cute_dog/"

    def test_fallback_to_direct_url_when_gallery_dl_returns_none(self):
        """When gallery-dl has no extractor for a URL and post_hint is 'image', use post.url directly."""
        post = make_post(url="https://imgur.com/xyz", post_hint="image")

        with patch("gallery_dl.extractor.find", return_value=None):
            urls = extract_media_urls(post)

        assert urls == ["https://imgur.com/xyz"]

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
        post = make_post(url="https://example.com/video", post_hint="link")

        with patch("gallery_dl.extractor.find", side_effect=Exception("network error")):
            urls = extract_media_urls(post)

        assert urls == []

    def test_gallery_dl_iteration_exception_returns_empty_list(self):
        post = make_post(url="https://example.com/album", post_hint="image")
        mock_extractor = MagicMock()
        mock_extractor.__iter__ = MagicMock(side_effect=RuntimeError("extraction failed"))

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == []

    def test_non_url_messages_are_ignored(self):
        """Message type 1 (Directory) and 2 (Queue) should not be added to urls."""
        post = make_post(url="https://imgur.com/abc", post_hint="image")
        mock_extractor = MagicMock()
        mock_extractor.__iter__ = MagicMock(
            return_value=iter(
                [
                    (1, {"category": "reddit"}, {}),
                    (3, "https://i.imgur.com/abc.jpg", {}),
                ]
            )
        )

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == ["https://i.imgur.com/abc.jpg"]


class TestCookiesPassthrough:
    def test_cookies_passed_to_gallery_dl_config(self):
        """When cookies are provided, gallery-dl's extractor.reddit.cookies config is set."""
        from gallery_dl import config as gdl_config

        post = make_post(url="https://example.com/post", post_hint="image")
        mock_extractor = make_mock_extractor(["https://example.com/img.jpg"])

        with (
            patch("gallery_dl.config.set") as mock_set,
            patch("gallery_dl.extractor.find", return_value=mock_extractor),
        ):
            urls = extract_media_urls(post, cookies={"reddit_session": "secret-value"})

        assert urls == ["https://example.com/img.jpg"]
        # At least one call to set the cookies config
        cookie_calls = [
            call_args
            for call_args in mock_set.call_args_list
            if len(call_args.args) == 3 and call_args.args[1] == "cookies"
        ]
        assert cookie_calls, f"expected cookies config to be set, got {mock_set.call_args_list}"
        assert cookie_calls[0].args[2] == {"reddit_session": "secret-value"}
        del gdl_config  # silence unused warning

    def test_no_cookies_means_no_cookies_config_set(self):
        from gallery_dl import config as gdl_config

        post = make_post(url="https://example.com/post", post_hint="image")
        mock_extractor = make_mock_extractor(["https://example.com/img.jpg"])

        with (
            patch("gallery_dl.config.set") as mock_set,
            patch("gallery_dl.extractor.find", return_value=mock_extractor),
        ):
            extract_media_urls(post)

        cookie_calls = [
            call_args
            for call_args in mock_set.call_args_list
            if len(call_args.args) == 3 and call_args.args[1] == "cookies"
        ]
        assert not cookie_calls, "cookies config must NOT be set when no cookies are provided"
        del gdl_config  # silence unused warning

    def test_async_wrapper_forwards_cookies(self):
        """The async wrapper passes cookies through to the sync function."""
        from unittest.mock import patch as _patch

        from media import extractor as ext_mod

        post = make_post(url="https://i.redd.it/abc.jpg", post_hint="image")

        async def run():
            with _patch.object(ext_mod, "extract_media_urls", return_value=["x"]) as m:
                await ext_mod.extract_media_urls_async(post, cookies={"reddit_session": "v"})
                m.assert_called_once_with(post, cookies={"reddit_session": "v"})

        import asyncio

        asyncio.run(run())


class TestMaskCookieValue:
    def test_mask_truncates_long_value(self):
        from media.extractor import _mask

        assert _mask("abcdefghij") == "abcd***"

    def test_mask_returns_short_value_unchanged(self):
        from media.extractor import _mask

        assert _mask("abc") == "abc"

    def test_mask_handles_empty(self):
        from media.extractor import _mask

        assert _mask("") == ""


class TestYtDlpForHostedVideo:
    def test_hosted_video_uses_yt_dlp(self):
        """For post_hint=hosted:video, yt-dlp is called and its URL is returned."""
        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )

        with patch("yt_dlp.YoutubeDL") as mock_cls:
            mock_ydl = mock_cls.return_value.__enter__.return_value
            mock_ydl.extract_info.return_value = {
                "url": "https://v.redd.it/vid001/DASH_720.mp4?source=fallback",
                "formats": [
                    {"url": "https://v.redd.it/vid001/DASH_720.mp4", "height": 720},
                    {"url": "https://v.redd.it/vid001/DASH_1080.mp4", "height": 1080},
                ],
            }
            from media.extractor import _try_yt_dlp

            urls, _ = _try_yt_dlp(post)

        # The function should pick one URL (the best/first format).
        assert len(urls) >= 1
        assert all(u.startswith("https://v.redd.it/") for u in urls)

    def test_hosted_video_falls_back_to_gallery_dl_when_yt_dlp_fails(self):
        """If yt-dlp raises, extract_media_urls still tries gallery-dl for hosted:video."""
        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )
        gdl_extractor = make_mock_extractor(["https://v.redd.it/vid001/DASH_720.mp4"])

        with (
            patch("yt_dlp.YoutubeDL", side_effect=RuntimeError("import failed")),
            patch("gallery_dl.extractor.find", return_value=gdl_extractor),
        ):
            urls = extract_media_urls(post)

        # Gallery-dl returned the URL, so we still get something.
        assert urls == ["https://v.redd.it/vid001/DASH_720.mp4"]

    def test_hosted_video_uses_yt_dlp_first(self):
        """When yt-dlp succeeds, gallery-dl is NOT called for hosted:video."""
        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )

        with patch("yt_dlp.YoutubeDL") as mock_cls, patch("gallery_dl.extractor.find") as mock_gdl:
            mock_ydl = mock_cls.return_value.__enter__.return_value
            mock_ydl.extract_info.return_value = {
                "url": "https://v.redd.it/vid001/DASH_720.mp4",
            }
            urls = extract_media_urls(post)

        assert urls == ["https://v.redd.it/vid001/DASH_720.mp4"]
        mock_gdl.assert_not_called()

    def test_yt_dlp_cookiefile_created_when_cookies_provided(self):
        """When cookies are provided, a Mozilla-format cookies.txt is created and passed as cookiefile."""
        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )
        captured: dict = {}

        def fake_ydl(opts):
            if "cookiefile" in opts:
                with Path(opts["cookiefile"]).open() as f:
                    captured["cookies_content"] = f.read()
            m = MagicMock()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=False)
            m.extract_info.return_value = {"url": "https://v.redd.it/x.mp4"}
            return m

        with patch("yt_dlp.YoutubeDL", side_effect=fake_ydl):
            from media.extractor import _try_yt_dlp

            urls, _ = _try_yt_dlp(post, cookies={"reddit_session": "secret"})

        assert len(urls) == 1
        assert "cookies_content" in captured
        content = captured["cookies_content"]
        assert "reddit_session" in content
        assert "secret" in content
        assert ".reddit.com" in content

    def test_yt_dlp_no_cookiefile_when_no_cookies(self):
        """When no cookies are provided, cookiefile is NOT in the yt-dlp options."""
        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )
        captured: dict = {}

        def fake_ydl(opts):
            captured["opts"] = opts
            m = MagicMock()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=False)
            m.extract_info.return_value = {"url": "https://v.redd.it/x.mp4"}
            return m

        with patch("yt_dlp.YoutubeDL", side_effect=fake_ydl):
            from media.extractor import _try_yt_dlp

            _try_yt_dlp(post)

        assert "cookiefile" not in captured["opts"]


class TestTruncate:
    def test_short_string_returned_unchanged(self):
        from media.extractor import _truncate

        assert _truncate("hello", 10) == "hello"

    def test_long_string_truncated_with_ellipsis(self):
        from media.extractor import _truncate

        result = _truncate("X" * 250, 10)
        assert result.startswith("XXXXXXX")
        assert result.endswith("...")
        assert len(result) == 10

    def test_exact_length_returned_unchanged(self):
        from media.extractor import _truncate

        assert _truncate("0123456789", 10) == "0123456789"


class TestPickYtDlpUrl:
    def test_returns_none_for_non_dict(self):
        from media.extractor import _pick_yt_dlp_url

        assert _pick_yt_dlp_url(None) is None
        assert _pick_yt_dlp_url("string") is None
        assert _pick_yt_dlp_url([1, 2, 3]) is None

    def test_prefers_top_level_url(self):
        from media.extractor import _pick_yt_dlp_url

        assert (
            _pick_yt_dlp_url(
                {
                    "url": "https://top-level",
                    "formats": [{"url": "https://from-formats"}],
                }
            )
            == "https://top-level"
        )

    def test_falls_back_to_formats_when_no_top_url(self):
        from media.extractor import _pick_yt_dlp_url

        assert (
            _pick_yt_dlp_url(
                {
                    "formats": [
                        {"url": "https://first"},
                        {"url": "https://second"},
                    ],
                }
            )
            == "https://first"
        )

    def test_returns_none_when_no_url_anywhere(self):
        from media.extractor import _pick_yt_dlp_url

        assert _pick_yt_dlp_url({"formats": [{"height": 720}]}) is None
        assert _pick_yt_dlp_url({}) is None


class TestTryYtDlpExtraBranches:
    def test_yt_dlp_returns_no_url(self):
        """If yt-dlp returns a result with no usable URL, _try_yt_dlp returns ([], False)."""
        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )

        with patch("yt_dlp.YoutubeDL") as mock_cls:
            mock_ydl = mock_cls.return_value.__enter__.return_value
            mock_ydl.extract_info.return_value = {"formats": []}
            from media.extractor import _try_yt_dlp

            urls, _ = _try_yt_dlp(post)

        assert urls == []

    def test_yt_dlp_raises_logs_warning_and_returns_empty(self, caplog):
        """When yt-dlp raises, a WARNING is logged (truncated) and an empty list returned."""
        import logging

        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )

        with patch("yt_dlp.YoutubeDL", side_effect=RuntimeError("boom " * 1000)):
            with caplog.at_level(logging.WARNING, logger="media.extractor"):
                from media.extractor import _try_yt_dlp

                urls, _ = _try_yt_dlp(post)

        assert urls == []
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("yt-dlp extraction failed" in r.getMessage() for r in warnings)
        # The 7 KB message is truncated; warning should be short.
        for w in warnings:
            assert len(w.getMessage()) < 300

    def test_yt_dlp_cleanup_swallows_oserror(self):
        """If unlinking the temp file fails, _try_yt_dlp still returns normally."""
        from pathlib import Path

        post = make_post(
            url="https://v.redd.it/vid001",
            permalink="https://www.reddit.com/r/aww/comments/vid001/cute_dog/",
            post_hint="hosted:video",
        )

        def boom(*_args, **_kwargs):
            raise OSError

        with patch("yt_dlp.YoutubeDL") as mock_cls, patch.object(Path, "unlink", boom):
            mock_ydl = mock_cls.return_value.__enter__.return_value
            mock_ydl.extract_info.return_value = {"url": "https://v.redd.it/x.mp4"}
            from media.extractor import _try_yt_dlp

            urls, _ = _try_yt_dlp(post, cookies={"reddit_session": "v"})

        assert urls == ["https://v.redd.it/x.mp4"]


class TestCleanLogOnAbortExtraction:
    def test_abort_extraction_logs_short_message(self, caplog):
        """When gallery-dl raises AbortExtraction, the WARNING must not contain the full payload."""
        from gallery_dl.exception import AbortExtraction

        post = make_post(url="https://example.com/post", post_hint="link")
        big_payload = "X" * 30_000
        mock_extractor = MagicMock()
        mock_extractor.__iter__ = MagicMock(side_effect=AbortExtraction(big_payload))

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            with caplog.at_level(logging.WARNING, logger="media.extractor"):
                urls = extract_media_urls(post)

        assert urls == []
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        # The full 30 KB payload must NOT appear in the WARNING message.
        assert big_payload not in warnings[0].getMessage()
        assert len(warnings[0].getMessage()) < 300

    def test_abort_extraction_keeps_full_text_at_debug(self, caplog):
        """At DEBUG level the full exception text is preserved (via exc_info)."""
        from gallery_dl.exception import AbortExtraction

        post = make_post(url="https://example.com/post", post_hint="link")
        mock_extractor = MagicMock()
        mock_extractor.__iter__ = MagicMock(side_effect=AbortExtraction("some detail"))

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            with caplog.at_level(logging.DEBUG, logger="media.extractor"):
                extract_media_urls(post)

        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any(r.exc_info for r in debug_records)


class TestExtractMediaUrlsAsync:
    async def test_async_wrapper_delegates_to_sync(self):
        post = make_post(url="https://i.redd.it/abc123.jpg", post_hint="image")

        urls = await extract_media_urls_async(post)

        assert urls == ["https://i.redd.it/abc123.jpg"]
