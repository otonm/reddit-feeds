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


class TestLoadSettings:
    def test_load_valid_config(self, sample_config_yaml):
        settings = load_settings(sample_config_yaml)
        assert settings.interval == 600
        assert len(settings.feeds) == 1
        assert settings.feeds[0].name == "python"
        assert settings.feeds[0].fetch_items == 10

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

    def test_env_var_overrides_output_dir(self, sample_config_yaml, monkeypatch, tmp_path):
        monkeypatch.setenv("REDDIT_FEEDS_OUTPUT_DIR", str(tmp_path / "feeds"))
        settings = load_settings(sample_config_yaml)
        assert settings.output_dir == tmp_path / "feeds"

    def test_env_var_overrides_log_level(self, sample_config_yaml, monkeypatch):
        monkeypatch.setenv("REDDIT_FEEDS_LOG_LEVEL", "DEBUG")
        settings = load_settings(sample_config_yaml)
        assert settings.log_level == "DEBUG"

    def test_invalid_fetch_items_raises_on_load(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("feeds:\n  - name: test\n    url: https://reddit.com/r/test/.json\n    fetch_items: 200\n")
        with pytest.raises(ValidationError):
            load_settings(config)
