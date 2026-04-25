"""Per-feed item store backed by a JSON file."""

import json
import logging
from pathlib import Path

import aiofiles
import aiofiles.os

from store._io import load_json
from store.models import StoredItem

logger = logging.getLogger(__name__)


class FeedStore:
    """Persists a feed's item list to {db_dir}/{slug}.json."""

    def __init__(self, db_dir: Path, feed_slug: str) -> None:
        self._path = db_dir / f"{feed_slug}.json"

    async def load(self) -> list[StoredItem]:
        """Load items from disk. Returns empty list if file does not exist."""
        if not self._path.exists():
            return []
        data = await load_json(self._path)
        if data is None:
            logger.warning("Corrupt feed store at %s, starting fresh", self._path)
            return []
        items = [StoredItem.from_dict(d) for d in data]
        logger.debug("Loaded %d items from %s", len(items), self._path)
        return items

    async def save(self, items: list[StoredItem]) -> None:
        """Persist items to disk, creating the directory if needed."""
        await aiofiles.os.makedirs(self._path.parent, exist_ok=True)
        async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
            await f.write(json.dumps([item.to_dict() for item in items], indent=2))
        logger.debug("Saved %d items to %s", len(items), self._path)
