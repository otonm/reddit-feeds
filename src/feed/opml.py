"""OPML 2.0 feed index builder and writer."""

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

import aiofiles
import aiofiles.os
from slugify import slugify

from config.models import FeedConfig

logger = logging.getLogger(__name__)


def build_opml(feeds: list[FeedConfig], base_url: str) -> str:
    """Build an OPML 2.0 XML string listing all configured feeds."""
    clean_base = base_url.rstrip("/")

    root = ET.Element("opml", version="2.0")

    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = "Reddit Feeds"
    ET.SubElement(head, "dateCreated").text = format_datetime(datetime.now(tz=UTC))

    body = ET.SubElement(root, "body")
    for feed in feeds:
        ET.SubElement(body, "outline",
            type="rss",
            text=feed.name,
            title=f"r/{feed.name}",
            xmlUrl=f"{clean_base}/{slugify(feed.name)}.xml",
        )

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


async def write_opml(xml: str, output_dir: Path) -> None:
    """Write OPML XML to {output_dir}/feeds.opml, creating the directory if needed."""
    await aiofiles.os.makedirs(output_dir, exist_ok=True)
    path = output_dir / "feeds.opml"
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(xml)
    logger.info("Wrote %s", path)
