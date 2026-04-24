"""Tests for CLI entry point."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from reddit_feeds.cli import _run_daemon, app, main
from reddit_feeds.config.models import FeedConfig, Settings
from typer.testing import CliRunner

runner = CliRunner()


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        output_dir=tmp_path,
        interval=60,
        feeds=[FeedConfig(name="python", url="https://reddit.com/r/python/.json")],
        log_level="INFO",
    )


class TestRunCommand:
    def test_run_once_success(self, tmp_path):
        settings = make_settings(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("feeds: []")

        with (
            patch("reddit_feeds.cli.load_settings", return_value=settings),
            patch("reddit_feeds.cli.run_once", AsyncMock()) as mock_run,
        ):
            result = runner.invoke(app, ["--config", str(config_file)])

        assert result.exit_code == 0
        mock_run.assert_called_once_with(settings)

    def test_run_daemon_calls_run_daemon(self, tmp_path):
        settings = make_settings(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("feeds: []")

        with (
            patch("reddit_feeds.cli.load_settings", return_value=settings),
            patch("reddit_feeds.cli._run_daemon", AsyncMock()) as mock_daemon,
        ):
            result = runner.invoke(app, ["--config", str(config_file), "--daemon"])

        assert result.exit_code == 0
        mock_daemon.assert_called_once_with(settings)

    def test_run_missing_config_exits_1(self, tmp_path):
        missing = tmp_path / "missing.yaml"
        with patch("reddit_feeds.cli.load_settings", side_effect=FileNotFoundError("Config file not found")):
            result = runner.invoke(app, ["--config", str(missing)])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_run_invalid_config_exits_1(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("bad: yaml")
        with patch("reddit_feeds.cli.load_settings", side_effect=ValueError("bad config")):
            result = runner.invoke(app, ["--config", str(config_file)])

        assert result.exit_code == 1
        assert "Invalid config" in result.output

    def test_main_calls_app(self):
        with patch("reddit_feeds.cli.app") as mock_app:
            main()
        mock_app.assert_called_once()


class TestRunDaemon:
    async def test_run_daemon_calls_run_once_and_sleeps(self, tmp_path):
        settings = make_settings(tmp_path)
        sleep_count = 0

        async def mock_sleep(seconds):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError

        with (
            patch("reddit_feeds.cli.run_once", AsyncMock()) as mock_run,
            patch("asyncio.sleep", side_effect=mock_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _run_daemon(settings)

        assert mock_run.call_count == 2
