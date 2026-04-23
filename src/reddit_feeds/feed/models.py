"""Feed data models."""

from dataclasses import dataclass

from reddit_feeds.reddit.models import RedditPost


@dataclass
class MediaPost:
    """A Reddit post paired with its extracted direct media URLs."""

    post: RedditPost
    media_urls: list[str]
