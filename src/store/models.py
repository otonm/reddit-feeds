"""Persistent feed item model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StoredItem:
    """A feed item persisted to the JSON store."""

    id: str
    title: str
    permalink: str
    created_utc: float
    media_urls: list[str]

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary suitable for JSON encoding."""
        return {
            "id": self.id,
            "title": self.title,
            "permalink": self.permalink,
            "created_utc": self.created_utc,
            "media_urls": self.media_urls,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StoredItem:
        """Deserialize from a plain dictionary produced by :meth:`to_dict`."""
        return cls(
            id=data["id"],
            title=data["title"],
            permalink=data["permalink"],
            created_utc=data["created_utc"],
            media_urls=data["media_urls"],
        )
