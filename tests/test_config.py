"""Tests for config module (models and loader)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from config.loader import load_settings
from config.models import FeedConfig, Settings


class TestFeedConfig:
    def test_valid_feed_config(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json")
        assert fc.name == "python"
        assert fc.fetch_count == 20  # default

    def test_fetch_count_default_is_20(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json")
        assert fc.fetch_count == 20

    def test_fetch_count_too_low_raises(self):
        with pytest.raises(ValidationError):
            FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=0)

    def test_fetch_count_too_high_raises(self):
        with pytest.raises(ValidationError):
            FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=101)

    def test_fetch_count_at_boundary_1(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=1)
        assert fc.fetch_count == 1

    def test_fetch_count_at_boundary_100(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_count=100)
        assert fc.fetch_count == 100


class TestSettings:
    def test_settings_defaults(self):
        s = Settings(feeds=[])
        assert s.output_dir == Path("output")
        assert s.db_dir == Path("db")
        assert s.interval == 900
        assert s.log_level == "INFO"

    def test_settings_custom_values(self, tmp_path):
        fc = FeedConfig(name="test", url="https://reddit.com/r/test/.json")
        feeds_dir = tmp_path / "feeds"
        s = Settings(output_dir=feeds_dir, interval=300, feeds=[fc])
        assert s.output_dir == feeds_dir
        assert s.interval == 300
        assert len(s.feeds) == 1

    def test_interval_too_low_raises(self):
        with pytest.raises(ValidationError):
            Settings(feeds=[], interval=0)

    def test_interval_at_boundary_300(self):
        s = Settings(feeds=[], interval=300)
        assert s.interval == 300

    def test_interval_at_299_raises(self):
        with pytest.raises(ValidationError):
            Settings(feeds=[], interval=299)

    def test_settings_db_dir_default(self):
        s = Settings()
        assert s.db_dir == Path("db")

    def test_settings_custom_db_dir(self):
        s = Settings(db_dir=Path("/data/db"))
        assert s.db_dir == Path("/data/db")

    def test_base_url_default_is_none(self):
        s = Settings()
        assert s.base_url is None

    def test_base_url_accepts_string(self):
        s = Settings(base_url="https://example.com")
        assert s.base_url == "https://example.com"

    def test_duplicate_feed_names_raises(self):
        feeds = [
            FeedConfig(name="python", url="https://reddit.com/r/python/.json"),
            FeedConfig(name="python", url="https://reddit.com/r/rust/.json"),
        ]
        with pytest.raises(ValidationError, match="duplicate feed names: python"):
            Settings(feeds=feeds)

    def test_duplicate_feed_urls_raises(self):
        feeds = [
            FeedConfig(name="python", url="https://reddit.com/r/python/.json"),
            FeedConfig(name="python2", url="https://reddit.com/r/python/.json"),
        ]
        with pytest.raises(ValidationError, match="duplicate feed URLs"):
            Settings(feeds=feeds)

    def test_duplicate_name_and_url_both_reported(self):
        feeds = [
            FeedConfig(name="python", url="https://reddit.com/r/python/.json"),
            FeedConfig(name="python", url="https://reddit.com/r/python/.json"),
        ]
        with pytest.raises(ValidationError, match="duplicate feed names"):
            Settings(feeds=feeds)

    def test_unique_feeds_accepted(self):
        feeds = [
            FeedConfig(name="python", url="https://reddit.com/r/python/.json"),
            FeedConfig(name="rust", url="https://reddit.com/r/rust/.json"),
        ]
        s = Settings(feeds=feeds)
        assert len(s.feeds) == 2


class TestLoadSettings:
    def test_load_valid_config(self, sample_config_yaml):
        settings = load_settings(sample_config_yaml)
        assert settings.interval == 600
        assert len(settings.feeds) == 1
        assert settings.feeds[0].name == "python"
        assert settings.feeds[0].fetch_count == 10

    def test_load_config_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_settings(tmp_path / "nonexistent.yaml")

    def test_load_config_defaults_when_keys_absent(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("feeds:\n  - name: test\n    url: https://reddit.com/r/test/.json\n")
        settings = load_settings(config)
        assert settings.output_dir == Path("output")
        assert settings.interval == 900
        assert settings.log_level == "INFO"

    def test_env_var_overrides_interval(self, sample_config_yaml, monkeypatch):
        monkeypatch.setenv("REDDIT_FEEDS_INTERVAL", "300")
        settings = load_settings(sample_config_yaml)
        assert settings.interval == 300

    def test_env_var_overrides_log_level(self, sample_config_yaml, monkeypatch):
        monkeypatch.setenv("REDDIT_FEEDS_LOG_LEVEL", "DEBUG")
        settings = load_settings(sample_config_yaml)
        assert settings.log_level == "DEBUG"

    def test_invalid_fetch_count_raises_on_load(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("feeds:\n  - name: test\n    url: https://reddit.com/r/test/.json\n    fetch_count: 200\n")
        with pytest.raises(ValidationError):
            load_settings(config)

    def test_base_url_loaded_from_yaml(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("base_url: https://example.ts.net\nfeeds: []\n")
        settings = load_settings(config)
        assert settings.base_url == "https://example.ts.net"

    def test_base_url_defaults_to_none_when_absent(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("feeds: []\n")
        settings = load_settings(config)
        assert settings.base_url is None
