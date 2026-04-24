"""Async RSS feed file writer."""

import logging
from pathlib import Path

import aiofiles
import aiofiles.os
from slugify import slugify

from config.models import FeedConfig

logger = logging.getLogger(__name__)


async def write_feed(xml: str, feed_config: FeedConfig, output_dir: Path) -> None:
    """Write RSS XML to {output_dir}/{slug}.xml, creating the directory if needed."""
    await aiofiles.os.makedirs(output_dir, exist_ok=True)
    filename = f"{slugify(feed_config.name)}.xml"
    path = output_dir / filename
    byte_count = len(xml.encode("utf-8"))
    logger.debug("Writing %d bytes to %s", byte_count, path)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(xml)
    logger.info("Wrote %s (%d bytes)", path, byte_count)
