"""Tests for OPML feed index builder and writer."""

import xml.etree.ElementTree as ET
from pathlib import Path

from config.models import FeedConfig
from feed.opml import build_opml, write_opml


def make_feed(name: str = "EarthPorn") -> FeedConfig:
    return FeedConfig(name=name, url=f"https://reddit.com/r/{name}/.json")


def _parse(xml: str) -> ET.Element:
    """Parse OPML XML string, skipping the XML declaration."""
    return ET.fromstring(xml.split("?>", 1)[1].strip())


class TestBuildOpml:
    def test_starts_with_xml_declaration(self):
        xml = build_opml([], "https://example.com")
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_root_element_is_opml_version_2(self):
        root = _parse(build_opml([], "https://example.com"))
        assert root.tag == "opml"
        assert root.attrib["version"] == "2.0"

    def test_head_contains_title_reddit_feeds(self):
        root = _parse(build_opml([], "https://example.com"))
        assert root.find("head/title").text == "Reddit Feeds"

    def test_head_contains_date_created(self):
        root = _parse(build_opml([], "https://example.com"))
        assert root.find("head/dateCreated") is not None
        assert root.find("head/dateCreated").text != ""

    def test_empty_feeds_produces_empty_body(self):
        root = _parse(build_opml([], "https://example.com"))
        assert list(root.find("body")) == []

    def test_feed_produces_one_outline_element(self):
        root = _parse(build_opml([make_feed("EarthPorn")], "https://example.com"))
        assert len(root.findall("body/outline")) == 1

    def test_outline_xml_url_uses_slugified_name(self):
        root = _parse(build_opml([make_feed("EarthPorn")], "https://example.com"))
        outline = root.find("body/outline")
        assert outline.attrib["xmlUrl"] == "https://example.com/earthporn.xml"

    def test_trailing_slash_stripped_from_base_url(self):
        root = _parse(build_opml([make_feed("EarthPorn")], "https://example.com/"))
        outline = root.find("body/outline")
        assert outline.attrib["xmlUrl"] == "https://example.com/earthporn.xml"

    def test_outline_type_is_rss(self):
        root = _parse(build_opml([make_feed()], "https://example.com"))
        assert root.find("body/outline").attrib["type"] == "rss"

    def test_outline_text_is_feed_name(self):
        root = _parse(build_opml([make_feed("EarthPorn")], "https://example.com"))
        assert root.find("body/outline").attrib["text"] == "EarthPorn"

    def test_outline_title_prefixed_with_r_slash(self):
        root = _parse(build_opml([make_feed("EarthPorn")], "https://example.com"))
        assert root.find("body/outline").attrib["title"] == "r/EarthPorn"

    def test_multiple_feeds_produce_multiple_outlines(self):
        feeds = [make_feed("EarthPorn"), make_feed("AbandonedPorn")]
        root = _parse(build_opml(feeds, "https://example.com"))
        assert len(root.findall("body/outline")) == 2

    def test_multiple_feeds_have_correct_urls(self):
        feeds = [make_feed("EarthPorn"), make_feed("AbandonedPorn")]
        root = _parse(build_opml(feeds, "https://example.com"))
        urls = [o.attrib["xmlUrl"] for o in root.findall("body/outline")]
        assert "https://example.com/earthporn.xml" in urls
        assert "https://example.com/abandonedporn.xml" in urls


class TestWriteOpml:
    async def test_creates_feeds_opml_file(self, tmp_path):
        await write_opml("<opml/>", tmp_path)
        assert (tmp_path / "feeds.opml").exists()

    async def test_content_is_written_correctly(self, tmp_path):
        await write_opml("<opml/>", tmp_path)
        assert (tmp_path / "feeds.opml").read_text() == "<opml/>"

    async def test_creates_output_dir_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b"
        await write_opml("<opml/>", nested)
        assert (nested / "feeds.opml").exists()

    async def test_overwrites_existing_file(self, tmp_path):
        (tmp_path / "feeds.opml").write_text("old")
        await write_opml("new", tmp_path)
        assert (tmp_path / "feeds.opml").read_text() == "new"
