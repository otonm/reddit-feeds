"""Load application settings from YAML config files with environment variable overrides."""

import os
from pathlib import Path

import yaml

from config.models import Settings


def load_settings(config_path: Path) -> Settings:
    """Load settings from a YAML file, with env-var overrides for top-level scalar fields."""
    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)

    raw: dict = yaml.safe_load(config_path.read_text()) or {}

    _apply_env_overrides(raw)

    return Settings.model_validate(raw)


def _apply_env_overrides(raw: dict) -> None:
    """Override top-level scalar fields from REDDIT_FEEDS_* environment variables."""
    overrides: list[tuple[str, str]] = [
        ("REDDIT_FEEDS_OUTPUT_DIR", "output_dir"),
        ("REDDIT_FEEDS_INTERVAL", "interval"),
        ("REDDIT_FEEDS_LOG_LEVEL", "log_level"),
    ]
    for env_key, field in overrides:
        val = os.getenv(env_key)
        if val is not None:
            raw[field] = val
