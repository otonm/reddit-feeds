"""Reddit post data model."""

from dataclasses import dataclass


@dataclass
class RedditPost:
    """A single Reddit post extracted from the subreddit RSS feed."""

    id: str
    title: str
    author: str
    permalink: str
    url: str
    created_utc: float
    post_hint: str = "link"
    is_gallery: bool = False
