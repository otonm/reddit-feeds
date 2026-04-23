import pytest
from pydantic import ValidationError
from reddit_feeds.config.models import FeedConfig, Settings
from pathlib import Path


class TestFeedConfig:
    def test_valid_feed_config(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json")
        assert fc.name == "python"
        assert fc.fetch_items == 20  # default

    def test_fetch_items_default_is_20(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json")
        assert fc.fetch_items == 20

    def test_fetch_items_too_low_raises(self):
        with pytest.raises(ValidationError):
            FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=0)

    def test_fetch_items_too_high_raises(self):
        with pytest.raises(ValidationError):
            FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=101)

    def test_fetch_items_at_boundary_1(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=1)
        assert fc.fetch_items == 1

    def test_fetch_items_at_boundary_100(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=100)
        assert fc.fetch_items == 100


class TestSettings:
    def test_settings_defaults(self):
        s = Settings(feeds=[])
        assert s.output_dir == Path("output")
        assert s.interval == 900
        assert s.log_level == "INFO"

    def test_settings_custom_values(self):
        fc = FeedConfig(name="test", url="https://reddit.com/r/test/.json")
        s = Settings(output_dir=Path("/tmp/feeds"), interval=300, feeds=[fc])
        assert s.output_dir == Path("/tmp/feeds")
        assert s.interval == 300
        assert len(s.feeds) == 1
