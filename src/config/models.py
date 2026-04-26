"""Pydantic models for application configuration."""

from pathlib import Path

from pydantic import BaseModel, field_validator

_MAX_FETCH_COUNT = 100
_MIN_INTERVAL = 300


class FeedConfig(BaseModel):
    """Configuration for a single Reddit feed."""

    name: str
    url: str
    fetch_count: int = 20

    @field_validator("fetch_count")
    @classmethod
    def validate_fetch_count(cls, v: int) -> int:
        """Ensure fetch_count is between 1 and 100."""
        if not 1 <= v <= _MAX_FETCH_COUNT:
            msg = f"fetch_count must be between 1 and 100, got {v}"
            raise ValueError(msg)
        return v


class Settings(BaseModel):
    """Top-level application settings."""

    output_dir: Path = Path("output")
    db_dir: Path = Path("db")
    interval: int = 900
    feeds: list[FeedConfig] = []
    log_level: str = "INFO"
    reddit_fetch_gap: float = 2.0

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        """Ensure interval is at least 300 seconds."""
        if v < _MIN_INTERVAL:
            msg = f"interval must be at least 300 seconds, got {v}"
            raise ValueError(msg)
        return v
