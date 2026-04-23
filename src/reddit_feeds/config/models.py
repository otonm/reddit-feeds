from pathlib import Path
from pydantic import BaseModel, field_validator


class FeedConfig(BaseModel):
    """Configuration for a single Reddit feed."""

    name: str
    url: str
    fetch_items: int = 20

    @field_validator("fetch_items")
    @classmethod
    def validate_fetch_items(cls, v: int) -> int:
        """Ensure fetch_items is between 1 and 100."""
        if not 1 <= v <= 100:
            msg = f"fetch_items must be between 1 and 100, got {v}"
            raise ValueError(msg)
        return v


class Settings(BaseModel):
    """Top-level application settings."""

    output_dir: Path = Path("output")
    interval: int = 900
    feeds: list[FeedConfig] = []
    log_level: str = "INFO"
