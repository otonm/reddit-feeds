"""Global seen-URL store backed by a JSON file."""

import json
import logging
from pathlib import Path

import aiofiles
import aiofiles.os

from store._io import load_json

logger = logging.getLogger(__name__)


class SeenStore:
    """Tracks all seen post.url and media URLs globally across all feeds."""

    def __init__(self, db_dir: Path) -> None:
        self._path = db_dir / "seen.json"
        self._seen: set[str] = set()

    async def load(self) -> None:
        """Load seen URLs from disk. No-op if file does not exist."""
        if not self._path.exists():
            self._seen = set()
            return
        data = await load_json(self._path)
        if data is None:
            logger.warning("Corrupt seen store at %s, starting fresh", self._path)
            self._seen = set()
            return
        self._seen = set(data)
        logger.debug("Loaded %d seen URLs from %s", len(self._seen), self._path)

    async def save(self) -> None:
        """Persist the seen set to disk, creating the directory if needed."""
        await aiofiles.os.makedirs(self._path.parent, exist_ok=True)
        async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(sorted(self._seen), indent=2))
        logger.debug("Saved %d seen URLs to %s", len(self._seen), self._path)

    def contains(self, url: str) -> bool:
        """Return True if *url* is in the seen set."""
        return url in self._seen

    def add(self, url: str) -> None:
        """Add a single URL to the seen set."""
        self._seen.add(url)

    def add_many(self, urls: list[str]) -> None:
        """Add multiple URLs to the seen set."""
        self._seen.update(urls)
