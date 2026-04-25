"""Shared async JSON file I/O for store modules."""

import json
from pathlib import Path

import aiofiles


async def load_json(path: Path) -> list | None:
    """Read and parse a JSON file. Returns None if content is corrupt."""
    async with aiofiles.open(path, encoding="utf-8") as f:
        content = await f.read()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None
