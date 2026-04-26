"""Tests for CLI entry point."""

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from cli import _run_daemon, app, main
from config.models import FeedConfig, Settings

runner = CliRunner()


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        output_dir=tmp_path,
        interval=300,
        feeds=[FeedConfig(name="python", url="https://reddit.com/r/python/.json")],
        log_level="INFO",
    )


class TestRunCommand:
    def test_run_once_success(self, tmp_path):
        settings = make_settings(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("feeds: []")

        with (
            patch("cli.load_settings", return_value=settings),
            patch("cli.run_once", AsyncMock()) as mock_run,
        ):
            result = runner.invoke(app, ["--config", str(config_file)])

        assert result.exit_code == 0
        mock_run.assert_called_once_with(settings)

    def test_run_daemon_calls_run_daemon(self, tmp_path):
        settings = make_settings(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("feeds: []")

        with (
            patch("cli.load_settings", return_value=settings),
            patch("cli._run_daemon", AsyncMock()) as mock_daemon,
        ):
            result = runner.invoke(app, ["--config", str(config_file), "--daemon"])

        assert result.exit_code == 0
        mock_daemon.assert_called_once_with(settings)

    def test_run_missing_config_exits_1(self, tmp_path):
        missing = tmp_path / "missing.yaml"
        with patch("cli.load_settings", side_effect=FileNotFoundError("Config file not found")):
            result = runner.invoke(app, ["--config", str(missing)])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_run_invalid_config_exits_1(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("bad: yaml")
        with patch("cli.load_settings", side_effect=ValueError("bad config")):
            result = runner.invoke(app, ["--config", str(config_file)])

        assert result.exit_code == 1
        assert "Invalid config" in result.output

    def test_debug_flag_sets_debug_level(self, tmp_path):
        settings = make_settings(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("feeds: []")

        with (
            patch("cli.load_settings", return_value=settings),
            patch("cli.run_once", AsyncMock()),
            patch("cli.logging.basicConfig") as mock_basicconfig,
        ):
            result = runner.invoke(app, ["--config", str(config_file), "--debug"])

        assert result.exit_code == 0
        mock_basicconfig.assert_called_once()
        assert mock_basicconfig.call_args.kwargs["level"] == logging.DEBUG

    def test_quiet_flag_sets_warning_level(self, tmp_path):
        settings = make_settings(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("feeds: []")

        with (
            patch("cli.load_settings", return_value=settings),
            patch("cli.run_once", AsyncMock()),
            patch("cli.logging.basicConfig") as mock_basicconfig,
        ):
            result = runner.invoke(app, ["--config", str(config_file), "--quiet"])

        assert result.exit_code == 0
        mock_basicconfig.assert_called_once()
        assert mock_basicconfig.call_args.kwargs["level"] == logging.WARNING

    def test_debug_and_quiet_are_mutually_exclusive(self):
        result = runner.invoke(app, ["--debug", "--quiet"])

        assert result.exit_code == 1
        assert "--debug and --quiet are mutually exclusive" in result.output

    def test_main_calls_app(self):
        with patch("cli.app") as mock_app:
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
            patch("cli.run_once", AsyncMock()) as mock_run,
            patch("asyncio.sleep", side_effect=mock_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _run_daemon(settings)

        assert mock_run.call_count == 2

    async def test_run_daemon_logs_next_run(self, tmp_path, caplog):
        settings = make_settings(tmp_path)
        call_count = 0

        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError

        with caplog.at_level(logging.INFO, logger="cli"):
            with (
                patch("cli.run_once", AsyncMock()),
                patch("asyncio.sleep", side_effect=mock_sleep),
            ):
                with pytest.raises(asyncio.CancelledError):
                    await _run_daemon(settings)

        messages = [r.message for r in caplog.records if r.name == "cli"]
        assert any("Next run at" in m and "in 300s" in m for m in messages)
