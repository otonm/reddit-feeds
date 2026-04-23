from dataclasses import dataclass


@dataclass
class RedditPost:
    """A single Reddit post extracted from the JSON feed."""

    id: str
    title: str
    author: str
    permalink: str
    url: str
    created_utc: float
    post_hint: str | None = None
    is_gallery: bool = False
    selftext_html: str | None = None
