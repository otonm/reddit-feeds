# Reddit Feeds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that fetches Reddit JSON feeds, extracts direct media URLs via gallery-dl, and publishes RSS 2.0 files — one per configured subreddit — with media enclosures.

**Architecture:** Layered package under `src/reddit_feeds/` with five responsibilities (config, reddit fetching, media extraction, feed building, file writing) coordinated by an async runner. The CLI wraps the runner in one-shot or looping daemon mode.

**Tech Stack:** Python 3.12, uv, httpx, gallery-dl, feedgen, PyYAML, pydantic, aiofiles, python-slugify, typer, pytest + pytest-asyncio + pytest-httpx

---

## File Map

```
src/reddit_feeds/
  __init__.py
  cli.py                   # typer app, daemon loop
  runner.py                # async orchestration: run_once, process_feed

  config/
    __init__.py
    models.py              # FeedConfig, Settings (pydantic BaseModel)
    loader.py              # YAML load + env-var override → Settings

  reddit/
    __init__.py
    models.py              # RedditPost dataclass
    client.py              # fetch_posts (httpx)

  media/
    __init__.py
    extractor.py           # extract_media_urls (sync, gallery-dl)
                           # extract_media_urls_async (run_in_executor wrapper)

  feed/
    __init__.py
    models.py              # MediaPost dataclass
    builder.py             # build_feed → RSS XML str, _infer_mime
    writer.py              # write_feed (aiofiles)

tests/
  conftest.py
  test_config.py
  test_reddit_client.py
  test_media_extractor.py
  test_feed_builder.py
  test_runner.py
```

---

## Task 1: Fix pyproject.toml and scaffold package structure

**Files:**
- Modify: `pyproject.toml`
- Create: `src/reddit_feeds/__init__.py` and all sub-package `__init__.py` files
- Create: `tests/conftest.py`

- [ ] **Step 1: Fix pyproject.toml**

Replace the entire file with this corrected version (fixes: missing `]` on dependencies, `feedgenerator` → `feedgen>=1.0.0`, adds `[project.scripts]`, adds pytest config, fixes ruff per-file-ignore path):

```toml
[project]
name = "reddit-feeds"
version = "0.1.0"
description = "Reddit gallery to RSS feed generator"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "gallery-dl>=1.31.10",
    "httpx>=0.27.0",
    "pyyaml>=6.0.0",
    "python-slugify>=8.0.0",
    "aiofiles>=25.1.0",
    "pydantic-settings>=2.13.1",
    "feedgen>=1.0.0",
    "typer>=0.24.1",
]

[project.scripts]
reddit-feeds = "reddit_feeds.cli:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["ALL"]
ignore = [
    "D107",
    "D203",
    "D213",
    "TRY003",
    "EM102",
    "G004",
    "PLR0913",
    "ERA001",
    "COM812",
    "D104",
    "T201",
    "TRY400",
]

[tool.ruff.lint.per-file-ignores]
"src/reddit_feeds/config/loader.py" = ["TC003", "TC001"]
"tests/**/*.py" = ["S101", "ANN", "D101", "D102", "D103", "D400", "D403", "D415", "INP001", "SIM117", "S314", "SLF001", "PLR2004", "ARG001", "PLC0415"]

[dependency-groups]
dev = [
    "feedparser>=6.0.12",
    "pytest>=9.0.2",
    "pytest-asyncio>=0.23.0",
    "pytest-httpx>=0.36.0",
    "ruff>=0.15.8",
]
```

- [ ] **Step 2: Create package `__init__.py` files**

Create these empty files (just `""` content is fine — they mark directories as packages):

```
src/reddit_feeds/__init__.py
src/reddit_feeds/config/__init__.py
src/reddit_feeds/reddit/__init__.py
src/reddit_feeds/media/__init__.py
src/reddit_feeds/feed/__init__.py
tests/__init__.py
```

Run:
```bash
mkdir -p src/reddit_feeds/config src/reddit_feeds/reddit src/reddit_feeds/media src/reddit_feeds/feed tests
touch src/reddit_feeds/__init__.py src/reddit_feeds/config/__init__.py \
      src/reddit_feeds/reddit/__init__.py src/reddit_feeds/media/__init__.py \
      src/reddit_feeds/feed/__init__.py tests/__init__.py
```

- [ ] **Step 3: Create tests/conftest.py**

```python
from pathlib import Path
import pytest


@pytest.fixture
def sample_config_yaml(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(
        "output_dir: output/\n"
        "interval: 600\n"
        "feeds:\n"
        "  - name: python\n"
        "    url: https://reddit.com/r/python/.json\n"
        "    fetch_items: 10\n"
    )
    return config


@pytest.fixture
def minimal_reddit_response() -> dict:
    return {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc123",
                        "title": "Test Post",
                        "author": "testuser",
                        "permalink": "/r/python/comments/abc123/test_post/",
                        "url": "https://i.redd.it/abc123.jpg",
                        "created_utc": 1700000000.0,
                        "post_hint": "image",
                        "is_gallery": False,
                        "selftext_html": None,
                    }
                }
            ]
        }
    }
```

- [ ] **Step 4: Install dependencies**

```bash
uv sync
```

Expected: resolves and installs all packages including `feedgen`. No errors.

- [ ] **Step 5: Verify pytest discovers tests**

```bash
uv run pytest --collect-only
```

Expected: `0 tests collected` (no test files yet) — no import errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: scaffold package structure and fix pyproject.toml"
```

---

## Task 2: Config models

**Files:**
- Create: `src/reddit_feeds/config/models.py`
- Create: `tests/test_config.py` (partial — models section)

- [ ] **Step 1: Write failing tests for FeedConfig validation**

Create `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError
from reddit_feeds.config.models import FeedConfig, Settings
from pathlib import Path


class TestFeedConfig:
    def test_valid_feed_config(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json")
        assert fc.name == "python"
        assert fc.fetch_items == 20  # default

    def test_fetch_items_default_is_20(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json")
        assert fc.fetch_items == 20

    def test_fetch_items_too_low_raises(self):
        with pytest.raises(ValidationError):
            FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=0)

    def test_fetch_items_too_high_raises(self):
        with pytest.raises(ValidationError):
            FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=101)

    def test_fetch_items_at_boundary_1(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=1)
        assert fc.fetch_items == 1

    def test_fetch_items_at_boundary_100(self):
        fc = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=100)
        assert fc.fetch_items == 100


class TestSettings:
    def test_settings_defaults(self):
        s = Settings(feeds=[])
        assert s.output_dir == Path("output")
        assert s.interval == 900
        assert s.log_level == "INFO"

    def test_settings_custom_values(self):
        fc = FeedConfig(name="test", url="https://reddit.com/r/test/.json")
        s = Settings(output_dir=Path("/tmp/feeds"), interval=300, feeds=[fc])
        assert s.output_dir == Path("/tmp/feeds")
        assert s.interval == 300
        assert len(s.feeds) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ImportError: No module named 'reddit_feeds.config.models'`

- [ ] **Step 3: Implement config/models.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add src/reddit_feeds/config/models.py tests/test_config.py
git commit -m "feat: add config models with fetch_items validation"
```

---

## Task 3: Config loader

**Files:**
- Create: `src/reddit_feeds/config/loader.py`
- Modify: `tests/test_config.py` (add loader tests)

- [ ] **Step 1: Add failing tests for the loader**

Append to `tests/test_config.py`:

```python
from reddit_feeds.config.loader import load_settings


class TestLoadSettings:
    def test_load_valid_config(self, sample_config_yaml, tmp_path):
        settings = load_settings(sample_config_yaml)
        assert settings.interval == 600
        assert len(settings.feeds) == 1
        assert settings.feeds[0].name == "python"
        assert settings.feeds[0].fetch_items == 10

    def test_load_config_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_settings(tmp_path / "nonexistent.yaml")

    def test_load_config_defaults_when_keys_absent(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("feeds:\n  - name: test\n    url: https://reddit.com/r/test/.json\n")
        settings = load_settings(config)
        assert settings.output_dir == Path("output")
        assert settings.interval == 900
        assert settings.log_level == "INFO"

    def test_env_var_overrides_interval(self, sample_config_yaml, monkeypatch):
        monkeypatch.setenv("REDDIT_FEEDS_INTERVAL", "300")
        settings = load_settings(sample_config_yaml)
        assert settings.interval == 300

    def test_env_var_overrides_output_dir(self, sample_config_yaml, monkeypatch, tmp_path):
        monkeypatch.setenv("REDDIT_FEEDS_OUTPUT_DIR", str(tmp_path / "feeds"))
        settings = load_settings(sample_config_yaml)
        assert settings.output_dir == tmp_path / "feeds"

    def test_env_var_overrides_log_level(self, sample_config_yaml, monkeypatch):
        monkeypatch.setenv("REDDIT_FEEDS_LOG_LEVEL", "DEBUG")
        settings = load_settings(sample_config_yaml)
        assert settings.log_level == "DEBUG"

    def test_invalid_fetch_items_raises_on_load(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "feeds:\n  - name: test\n    url: https://reddit.com/r/test/.json\n    fetch_items: 200\n"
        )
        with pytest.raises(Exception):
            load_settings(config)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py::TestLoadSettings -v
```

Expected: `ImportError: No module named 'reddit_feeds.config.loader'`

- [ ] **Step 3: Implement config/loader.py**

```python
import os
from pathlib import Path

import yaml

from reddit_feeds.config.models import Settings


def load_settings(config_path: Path) -> Settings:
    """Load settings from a YAML file, with env-var overrides for top-level scalar fields."""
    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)

    raw: dict = yaml.safe_load(config_path.read_text()) or {}

    _apply_env_overrides(raw)

    return Settings.model_validate(raw)


def _apply_env_overrides(raw: dict) -> None:
    """Override top-level scalar fields from REDDIT_FEEDS_* environment variables."""
    overrides: list[tuple[str, str]] = [
        ("REDDIT_FEEDS_OUTPUT_DIR", "output_dir"),
        ("REDDIT_FEEDS_INTERVAL", "interval"),
        ("REDDIT_FEEDS_LOG_LEVEL", "log_level"),
    ]
    for env_key, field in overrides:
        val = os.getenv(env_key)
        if val is not None:
            raw[field] = val
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/reddit_feeds/config/loader.py tests/test_config.py
git commit -m "feat: add config loader with YAML parsing and env-var overrides"
```

---

## Task 4: Reddit models

**Files:**
- Create: `src/reddit_feeds/reddit/models.py`
- Create: `tests/test_reddit_client.py` (models section)

- [ ] **Step 1: Write failing tests for RedditPost parsing**

Create `tests/test_reddit_client.py`:

```python
import pytest
import httpx
from pytest_httpx import HTTPXMock

from reddit_feeds.reddit.models import RedditPost
from reddit_feeds.reddit.client import fetch_posts, _parse_post


class TestParsePost:
    def test_parse_full_post(self):
        data = {
            "id": "abc123",
            "title": "Test Post",
            "author": "testuser",
            "permalink": "/r/python/comments/abc123/test/",
            "url": "https://i.redd.it/abc123.jpg",
            "created_utc": 1700000000.0,
            "post_hint": "image",
            "is_gallery": False,
            "selftext_html": None,
        }
        post = _parse_post(data)
        assert post.id == "abc123"
        assert post.permalink == "https://reddit.com/r/python/comments/abc123/test/"
        assert post.post_hint == "image"
        assert post.is_gallery is False

    def test_parse_post_missing_optional_fields(self):
        data = {
            "id": "xyz",
            "title": "Minimal",
            "author": "user",
            "permalink": "/r/test/comments/xyz/",
            "url": "https://example.com",
            "created_utc": 1700000000.0,
        }
        post = _parse_post(data)
        assert post.post_hint is None
        assert post.is_gallery is False
        assert post.selftext_html is None

    def test_parse_post_deleted_author(self):
        data = {
            "id": "del1",
            "title": "Deleted",
            "author": None,
            "permalink": "/r/test/comments/del1/",
            "url": "https://example.com",
            "created_utc": 1700000000.0,
        }
        post = _parse_post(data)
        assert post.author == "[deleted]"

    def test_permalink_prefixed_with_reddit_domain(self):
        data = {
            "id": "p1",
            "title": "Post",
            "author": "u",
            "permalink": "/r/x/comments/p1/post/",
            "url": "https://example.com",
            "created_utc": 1700000000.0,
        }
        post = _parse_post(data)
        assert post.permalink.startswith("https://reddit.com")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_reddit_client.py::TestParsePost -v
```

Expected: `ImportError: No module named 'reddit_feeds.reddit.models'`

- [ ] **Step 3: Implement reddit/models.py**

```python
from dataclasses import dataclass, field


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
```

- [ ] **Step 4: Implement the `_parse_post` function in reddit/client.py (stub only)**

Create `src/reddit_feeds/reddit/client.py` with just enough to make the model tests pass:

```python
import logging

import httpx

from reddit_feeds.reddit.models import RedditPost

USER_AGENT = "reddit-feeds/0.1"
TIMEOUT = 15.0

logger = logging.getLogger(__name__)


def _parse_post(data: dict) -> RedditPost:
    """Parse a Reddit post dict from the JSON API into a RedditPost."""
    return RedditPost(
        id=data["id"],
        title=data["title"],
        author=data.get("author") or "[deleted]",
        permalink=f"https://reddit.com{data['permalink']}",
        url=data["url"],
        created_utc=data["created_utc"],
        post_hint=data.get("post_hint"),
        is_gallery=bool(data.get("is_gallery", False)),
        selftext_html=data.get("selftext_html"),
    )


async def fetch_posts(url: str, limit: int, client: httpx.AsyncClient) -> list[RedditPost]:
    """Fetch posts from a Reddit JSON feed URL."""
    raise NotImplementedError
```

- [ ] **Step 5: Run model tests to verify they pass**

```bash
uv run pytest tests/test_reddit_client.py::TestParsePost -v
```

Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add src/reddit_feeds/reddit/models.py src/reddit_feeds/reddit/client.py tests/test_reddit_client.py
git commit -m "feat: add RedditPost model and _parse_post"
```

---

## Task 5: Reddit client

**Files:**
- Modify: `src/reddit_feeds/reddit/client.py`
- Modify: `tests/test_reddit_client.py`

- [ ] **Step 1: Add failing tests for fetch_posts**

Append to `tests/test_reddit_client.py`:

```python
class TestFetchPosts:
    async def test_fetch_posts_success(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(
            url="https://reddit.com/r/python/.json?limit=10",
            json=minimal_reddit_response,
        )
        async with httpx.AsyncClient() as client:
            posts = await fetch_posts("https://reddit.com/r/python/.json", 10, client)

        assert len(posts) == 1
        assert posts[0].id == "abc123"
        assert posts[0].title == "Test Post"
        assert posts[0].permalink == "https://reddit.com/r/python/comments/abc123/test_post/"

    async def test_fetch_posts_sends_user_agent(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            await fetch_posts("https://reddit.com/r/python/.json", 5, client)

        request = httpx_mock.get_requests()[0]
        assert request.headers["user-agent"] == "reddit-feeds/0.1"

    async def test_fetch_posts_appends_limit_param(self, httpx_mock: HTTPXMock, minimal_reddit_response):
        httpx_mock.add_response(json=minimal_reddit_response)
        async with httpx.AsyncClient() as client:
            await fetch_posts("https://reddit.com/r/python/.json", 25, client)

        request = httpx_mock.get_requests()[0]
        assert "limit=25" in str(request.url)

    async def test_fetch_posts_raises_on_http_error(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(status_code=429)
        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_posts("https://reddit.com/r/python/.json", 10, client)

    async def test_fetch_posts_empty_feed(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"data": {"children": []}})
        async with httpx.AsyncClient() as client:
            posts = await fetch_posts("https://reddit.com/r/python/.json", 10, client)
        assert posts == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_reddit_client.py::TestFetchPosts -v
```

Expected: all fail with `NotImplementedError`

- [ ] **Step 3: Implement fetch_posts**

Replace the `fetch_posts` stub in `src/reddit_feeds/reddit/client.py`:

```python
async def fetch_posts(url: str, limit: int, client: httpx.AsyncClient) -> list[RedditPost]:
    """Fetch posts from a Reddit JSON feed URL."""
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}limit={limit}"
    response = await client.get(
        full_url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    children = response.json()["data"]["children"]
    return [_parse_post(child["data"]) for child in children]
```

- [ ] **Step 4: Run all reddit tests to verify they pass**

```bash
uv run pytest tests/test_reddit_client.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/reddit_feeds/reddit/client.py tests/test_reddit_client.py
git commit -m "feat: implement fetch_posts with httpx"
```

---

## Task 6: Media extractor

**Files:**
- Create: `src/reddit_feeds/media/extractor.py`
- Create: `tests/test_media_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_media_extractor.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from reddit_feeds.media.extractor import extract_media_urls
from reddit_feeds.reddit.models import RedditPost


def make_post(**kwargs) -> RedditPost:
    defaults = {
        "id": "abc123",
        "title": "Test",
        "author": "user",
        "permalink": "https://reddit.com/r/test/comments/abc123/",
        "url": "https://i.redd.it/abc123.jpg",
        "created_utc": 1700000000.0,
        "post_hint": "image",
        "is_gallery": False,
    }
    defaults.update(kwargs)
    return RedditPost(**defaults)


def make_mock_extractor(url_messages: list[str]) -> MagicMock:
    """Build a mock gallery-dl extractor that yields Message.Url tuples."""
    mock = MagicMock()
    mock.__iter__ = MagicMock(
        return_value=iter([(3, url, {}) for url in url_messages])
    )
    return mock


class TestExtractMediaUrls:
    def test_single_image_via_gallery_dl(self):
        post = make_post(url="https://i.redd.it/abc123.jpg", post_hint="image")
        mock_extractor = make_mock_extractor(["https://i.redd.it/abc123.jpg"])

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/abc123.jpg"]

    def test_gallery_multiple_images(self):
        post = make_post(
            url="https://www.reddit.com/gallery/abc123",
            is_gallery=True,
            post_hint=None,
        )
        mock_extractor = make_mock_extractor([
            "https://i.redd.it/img1.jpg",
            "https://i.redd.it/img2.jpg",
        ])

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/img1.jpg", "https://i.redd.it/img2.jpg"]

    def test_fallback_to_direct_url_when_gallery_dl_returns_none(self):
        post = make_post(url="https://i.redd.it/direct.jpg", post_hint="image")

        with patch("gallery_dl.extractor.find", return_value=None):
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/direct.jpg"]

    def test_no_fallback_for_non_image_post_hint(self):
        post = make_post(url="https://example.com/article", post_hint="link")

        with patch("gallery_dl.extractor.find", return_value=None):
            urls = extract_media_urls(post)

        assert urls == []

    def test_text_post_returns_empty(self):
        post = make_post(url="https://self.reddit.com/r/test", post_hint="self")

        with patch("gallery_dl.extractor.find", return_value=None):
            urls = extract_media_urls(post)

        assert urls == []

    def test_gallery_dl_exception_returns_empty_list(self):
        post = make_post(url="https://example.com/video", post_hint=None)

        with patch("gallery_dl.extractor.find", side_effect=Exception("network error")):
            urls = extract_media_urls(post)

        assert urls == []

    def test_gallery_dl_iteration_exception_returns_empty_list(self):
        post = make_post(url="https://example.com/img.jpg", post_hint="image")
        mock_extractor = MagicMock()
        mock_extractor.__iter__ = MagicMock(side_effect=RuntimeError("extraction failed"))

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == []

    def test_non_url_messages_are_ignored(self):
        """Message type 1 (Directory) and 2 (Queue) should not be added to urls."""
        post = make_post(url="https://i.redd.it/abc.jpg", post_hint="image")
        mock_extractor = MagicMock()
        mock_extractor.__iter__ = MagicMock(return_value=iter([
            (1, {"category": "reddit"}, {}),   # Directory message
            (3, "https://i.redd.it/abc.jpg", {}),  # Url message
        ]))

        with patch("gallery_dl.extractor.find", return_value=mock_extractor):
            urls = extract_media_urls(post)

        assert urls == ["https://i.redd.it/abc.jpg"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_media_extractor.py -v
```

Expected: `ImportError: No module named 'reddit_feeds.media.extractor'`

- [ ] **Step 3: Implement media/extractor.py**

```python
import asyncio
import logging
from collections.abc import Callable

from reddit_feeds.reddit.models import RedditPost

logger = logging.getLogger(__name__)

_GALLERY_DL_URL_MESSAGE = 3


def extract_media_urls(post: RedditPost) -> list[str]:
    """Extract direct media URLs from a Reddit post using gallery-dl.

    Returns empty list if no media can be extracted. Safe to call from a thread pool.
    """
    urls = _try_gallery_dl(post.url)

    if not urls and post.post_hint == "image":
        urls = [post.url]

    return urls


async def extract_media_urls_async(post: RedditPost) -> list[str]:
    """Async wrapper: runs extract_media_urls in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, extract_media_urls, post)


def _try_gallery_dl(url: str) -> list[str]:
    """Attempt URL extraction via gallery-dl. Returns [] on any failure."""
    try:
        import gallery_dl.extractor as gallery_dl_extractor
        from gallery_dl import config as gallery_dl_config

        gallery_dl_config.set((), "download", False)
        gallery_dl_config.set((), "write-metadata", False)
        gallery_dl_config.set((), "write-pages", False)

        extractor = gallery_dl_extractor.find(url)
        if extractor is None:
            return []

        urls: list[str] = []
        for message in extractor:
            if message[0] == _GALLERY_DL_URL_MESSAGE:
                urls.append(message[1])
        return urls
    except Exception:
        logger.warning("gallery-dl extraction failed for %s", url, exc_info=True)
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_media_extractor.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/reddit_feeds/media/extractor.py tests/test_media_extractor.py
git commit -m "feat: implement media extractor with gallery-dl"
```

---

## Task 7: Feed models and builder

**Files:**
- Create: `src/reddit_feeds/feed/models.py`
- Create: `src/reddit_feeds/feed/builder.py`
- Create: `tests/test_feed_builder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_feed_builder.py`:

```python
import feedparser
import pytest

from reddit_feeds.config.models import FeedConfig
from reddit_feeds.feed.builder import _infer_mime, build_feed
from reddit_feeds.feed.models import MediaPost
from reddit_feeds.reddit.models import RedditPost


def make_feed_config(name: str = "python") -> FeedConfig:
    return FeedConfig(name=name, url=f"https://reddit.com/r/{name}/.json")


def make_media_post(media_urls: list[str], **overrides) -> MediaPost:
    post = RedditPost(
        id=overrides.get("id", "abc123"),
        title=overrides.get("title", "Test Post"),
        author=overrides.get("author", "user"),
        permalink=overrides.get("permalink", "https://reddit.com/r/python/comments/abc123/test/"),
        url=overrides.get("url", media_urls[0] if media_urls else ""),
        created_utc=overrides.get("created_utc", 1700000000.0),
        post_hint=overrides.get("post_hint", "image"),
    )
    return MediaPost(post=post, media_urls=media_urls)


class TestBuildFeed:
    def test_feed_title_and_link(self):
        xml = build_feed(make_feed_config("python"), [])
        parsed = feedparser.parse(xml)
        assert parsed.feed.title == "r/python"
        assert "reddit.com/r/python" in parsed.feed.link

    def test_single_image_item_has_enclosure(self):
        posts = [make_media_post(["https://i.redd.it/abc123.jpg"])]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)

        assert len(parsed.entries) == 1
        assert len(parsed.entries[0].enclosures) == 1
        assert parsed.entries[0].enclosures[0].url == "https://i.redd.it/abc123.jpg"
        assert parsed.entries[0].enclosures[0].type == "image/jpeg"

    def test_single_image_in_description(self):
        posts = [make_media_post(["https://i.redd.it/abc123.jpg"])]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert 'src="https://i.redd.it/abc123.jpg"' in parsed.entries[0].summary

    def test_gallery_all_images_in_description(self):
        urls = ["https://i.redd.it/img1.jpg", "https://i.redd.it/img2.png", "https://i.redd.it/img3.gif"]
        posts = [make_media_post(urls)]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)

        description = parsed.entries[0].summary
        assert "img1.jpg" in description
        assert "img2.png" in description
        assert "img3.gif" in description
        assert description.count("<img") == 3

    def test_gallery_enclosure_is_first_url(self):
        urls = ["https://i.redd.it/first.jpg", "https://i.redd.it/second.png"]
        posts = [make_media_post(urls)]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert parsed.entries[0].enclosures[0].url == "https://i.redd.it/first.jpg"

    def test_video_url_uses_video_tag_in_description(self):
        posts = [make_media_post(["https://v.redd.it/abc123.mp4"], post_hint=None)]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert "<video" in parsed.entries[0].summary

    def test_video_enclosure_has_video_mime(self):
        posts = [make_media_post(["https://v.redd.it/abc.mp4"], post_hint=None)]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert parsed.entries[0].enclosures[0].type == "video/mp4"

    def test_multiple_posts_all_appear(self):
        posts = [
            make_media_post(["https://i.redd.it/a.jpg"], id="a", title="Post A"),
            make_media_post(["https://i.redd.it/b.png"], id="b", title="Post B"),
        ]
        xml = build_feed(make_feed_config(), posts)
        parsed = feedparser.parse(xml)
        assert len(parsed.entries) == 2

    def test_empty_posts_list_produces_valid_feed(self):
        xml = build_feed(make_feed_config(), [])
        parsed = feedparser.parse(xml)
        assert parsed.feed.title == "r/python"
        assert len(parsed.entries) == 0


class TestInferMime:
    def test_jpeg_extensions(self):
        assert _infer_mime("https://example.com/img.jpg") == "image/jpeg"
        assert _infer_mime("https://example.com/img.jpeg") == "image/jpeg"

    def test_png(self):
        assert _infer_mime("https://example.com/img.png") == "image/png"

    def test_gif(self):
        assert _infer_mime("https://example.com/img.gif") == "image/gif"

    def test_mp4(self):
        assert _infer_mime("https://example.com/vid.mp4") == "video/mp4"

    def test_webm(self):
        assert _infer_mime("https://example.com/vid.webm") == "video/webm"

    def test_unknown_extension(self):
        assert _infer_mime("https://example.com/file.xyz") == "application/octet-stream"

    def test_url_with_query_string(self):
        assert _infer_mime("https://example.com/img.jpg?size=large") == "image/jpeg"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_feed_builder.py -v
```

Expected: `ImportError: No module named 'reddit_feeds.feed.models'`

- [ ] **Step 3: Implement feed/models.py**

```python
from dataclasses import dataclass

from reddit_feeds.reddit.models import RedditPost


@dataclass
class MediaPost:
    """A Reddit post paired with its extracted direct media URLs."""

    post: RedditPost
    media_urls: list[str]
```

- [ ] **Step 4: Implement feed/builder.py**

```python
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from feedgen.feed import FeedGenerator

from reddit_feeds.config.models import FeedConfig
from reddit_feeds.feed.models import MediaPost

logger = logging.getLogger(__name__)

_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
_VIDEO_MIMES = {"video/mp4", "video/webm"}


def _infer_mime(url: str) -> str:
    """Infer MIME type from a URL's file extension."""
    path = urlparse(url).path
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _MIME_MAP.get(ext, "application/octet-stream")


def _is_video(url: str) -> bool:
    return _infer_mime(url) in _VIDEO_MIMES


def _build_description(media_urls: list[str]) -> str:
    """Build an HTML description with all media embedded."""
    parts: list[str] = []
    for url in media_urls:
        if _is_video(url):
            parts.append(f'<video src="{url}" controls style="max-width:100%"></video>')
        else:
            parts.append(f'<img src="{url}" style="max-width:100%">')
    return "".join(parts)


def build_feed(feed_config: FeedConfig, posts: list[MediaPost]) -> str:
    """Build an RSS 2.0 feed string from a list of MediaPost objects."""
    base_url = feed_config.url.removesuffix(".json")

    fg = FeedGenerator()
    fg.id(base_url)
    fg.title(f"r/{feed_config.name}")
    fg.link(href=base_url, rel="alternate")
    fg.description(f"Reddit feed for r/{feed_config.name}")

    for mp in posts:
        fe = fg.add_entry(order="append")
        fe.id(mp.post.permalink)
        fe.title(mp.post.title)
        fe.link(href=mp.post.permalink)
        fe.published(datetime.fromtimestamp(mp.post.created_utc, tz=timezone.utc))
        fe.description(_build_description(mp.media_urls))

        if mp.media_urls:
            first_url = mp.media_urls[0]
            fe.enclosure(url=first_url, length="0", type=_infer_mime(first_url))

    return fg.rss_str(pretty=True).decode()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_feed_builder.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/reddit_feeds/feed/models.py src/reddit_feeds/feed/builder.py tests/test_feed_builder.py
git commit -m "feat: implement feed models and RSS builder"
```

---

## Task 8: Feed writer

**Files:**
- Create: `src/reddit_feeds/feed/writer.py`
- Modify: `tests/test_feed_builder.py` (add writer tests)

- [ ] **Step 1: Add failing tests for write_feed**

Append to `tests/test_feed_builder.py`:

```python
from pathlib import Path
from reddit_feeds.feed.writer import write_feed


class TestWriteFeed:
    async def test_write_feed_creates_file(self, tmp_path):
        config = make_feed_config("python")
        await write_feed("<rss/>", config, tmp_path)
        assert (tmp_path / "python.xml").exists()

    async def test_write_feed_content_matches(self, tmp_path):
        config = make_feed_config("python")
        xml = "<rss><channel><title>r/python</title></channel></rss>"
        await write_feed(xml, config, tmp_path)
        content = (tmp_path / "python.xml").read_text()
        assert content == xml

    async def test_write_feed_slugifies_name(self, tmp_path):
        config = make_feed_config("My Feed Name!")
        await write_feed("<rss/>", config, tmp_path)
        assert (tmp_path / "my-feed-name.xml").exists()

    async def test_write_feed_creates_output_dir_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b" / "feeds"
        config = make_feed_config("python")
        await write_feed("<rss/>", config, nested)
        assert (nested / "python.xml").exists()

    async def test_write_feed_overwrites_existing(self, tmp_path):
        config = make_feed_config("python")
        (tmp_path / "python.xml").write_text("old content")
        await write_feed("new content", config, tmp_path)
        assert (tmp_path / "python.xml").read_text() == "new content"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_feed_builder.py::TestWriteFeed -v
```

Expected: `ImportError: No module named 'reddit_feeds.feed.writer'`

- [ ] **Step 3: Implement feed/writer.py**

```python
import logging
from pathlib import Path

import aiofiles
from slugify import slugify

from reddit_feeds.config.models import FeedConfig

logger = logging.getLogger(__name__)


async def write_feed(xml: str, feed_config: FeedConfig, output_dir: Path) -> None:
    """Write RSS XML to {output_dir}/{slug}.xml, creating the directory if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slugify(feed_config.name)}.xml"
    path = output_dir / filename
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(xml)
    logger.debug("Wrote feed to %s", path)
```

- [ ] **Step 4: Run all feed tests to verify they pass**

```bash
uv run pytest tests/test_feed_builder.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/reddit_feeds/feed/writer.py tests/test_feed_builder.py
git commit -m "feat: implement async feed writer"
```

---

## Task 9: Runner

**Files:**
- Create: `src/reddit_feeds/runner.py`
- Create: `tests/test_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_runner.py`:

```python
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from reddit_feeds.config.models import FeedConfig, Settings
from reddit_feeds.feed.models import MediaPost
from reddit_feeds.reddit.models import RedditPost
from reddit_feeds.runner import process_feed, run_once


def make_settings(tmp_path: Path, feeds: list[FeedConfig] | None = None) -> Settings:
    return Settings(
        output_dir=tmp_path,
        interval=900,
        feeds=feeds or [FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)],
        log_level="INFO",
    )


def make_reddit_post(**overrides) -> RedditPost:
    defaults = {
        "id": "abc",
        "title": "Test",
        "author": "user",
        "permalink": "https://reddit.com/r/python/comments/abc/",
        "url": "https://i.redd.it/abc.jpg",
        "created_utc": 1700000000.0,
        "post_hint": "image",
    }
    defaults.update(overrides)
    return RedditPost(**defaults)


class TestProcessFeed:
    async def test_process_feed_writes_file(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])
        post = make_reddit_post()

        with (
            patch("reddit_feeds.runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("reddit_feeds.runner.extract_media_urls_async", AsyncMock(return_value=["https://i.redd.it/abc.jpg"])),
        ):
            import httpx
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)

        assert (tmp_path / "python.xml").exists()

    async def test_process_feed_skips_posts_with_no_media(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])
        post = make_reddit_post()

        written_posts: list = []

        async def mock_write(xml, fc, od):
            import feedparser
            parsed = feedparser.parse(xml)
            written_posts.extend(parsed.entries)

        with (
            patch("reddit_feeds.runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("reddit_feeds.runner.extract_media_urls_async", AsyncMock(return_value=[])),
            patch("reddit_feeds.runner.write_feed", side_effect=mock_write),
        ):
            import httpx
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)

        assert written_posts == []

    async def test_process_feed_fetch_failure_does_not_raise(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])

        with patch("reddit_feeds.runner.fetch_posts", AsyncMock(side_effect=Exception("network error"))):
            import httpx
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)  # must not raise

    async def test_process_feed_extraction_failure_skips_post(self, tmp_path):
        config = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        settings = make_settings(tmp_path, [config])
        post = make_reddit_post()

        with (
            patch("reddit_feeds.runner.fetch_posts", AsyncMock(return_value=[post])),
            patch("reddit_feeds.runner.extract_media_urls_async", AsyncMock(side_effect=Exception("gallery-dl broke"))),
            patch("reddit_feeds.runner.write_feed", AsyncMock()) as mock_write,
        ):
            import httpx
            async with httpx.AsyncClient() as client:
                await process_feed(config, settings, client)

        xml_arg = mock_write.call_args[0][0]
        import feedparser
        assert len(feedparser.parse(xml_arg).entries) == 0


class TestRunOnce:
    async def test_run_once_processes_all_feeds(self, tmp_path):
        feed1 = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        feed2 = FeedConfig(name="rust", url="https://reddit.com/r/rust/.json", fetch_items=5)
        settings = make_settings(tmp_path, [feed1, feed2])

        processed: list[str] = []

        async def mock_process_feed(feed, s, client):
            processed.append(feed.name)

        with patch("reddit_feeds.runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)

        assert "python" in processed
        assert "rust" in processed

    async def test_run_once_one_feed_fails_others_complete(self, tmp_path):
        feed1 = FeedConfig(name="python", url="https://reddit.com/r/python/.json", fetch_items=5)
        feed2 = FeedConfig(name="rust", url="https://reddit.com/r/rust/.json", fetch_items=5)
        settings = make_settings(tmp_path, [feed1, feed2])

        processed: list[str] = []

        async def mock_process_feed(feed, s, client):
            processed.append(feed.name)
            if feed.name == "python":
                raise RuntimeError("python feed exploded")

        with patch("reddit_feeds.runner.process_feed", side_effect=mock_process_feed):
            await run_once(settings)  # must not raise

        assert "python" in processed
        assert "rust" in processed
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_runner.py -v
```

Expected: `ImportError: No module named 'reddit_feeds.runner'`

- [ ] **Step 3: Implement runner.py**

```python
import asyncio
import logging

import httpx

from reddit_feeds.config.models import FeedConfig, Settings
from reddit_feeds.feed.builder import build_feed
from reddit_feeds.feed.models import MediaPost
from reddit_feeds.feed.writer import write_feed
from reddit_feeds.media.extractor import extract_media_urls_async
from reddit_feeds.reddit.client import fetch_posts

logger = logging.getLogger(__name__)


async def run_once(settings: Settings) -> None:
    """Fetch and publish all configured feeds concurrently."""
    async with httpx.AsyncClient() as client:
        await asyncio.gather(
            *[process_feed(feed, settings, client) for feed in settings.feeds],
            return_exceptions=True,
        )


async def process_feed(feed: FeedConfig, settings: Settings, client: httpx.AsyncClient) -> None:
    """Fetch, extract, build, and write a single feed. Logs and returns on any error."""
    logger.info("[%s] Fetching %d posts from %s", feed.name, feed.fetch_items, feed.url)
    try:
        posts = await fetch_posts(feed.url, feed.fetch_items, client)
    except Exception:
        logger.warning("[%s] Failed to fetch posts", feed.name, exc_info=True)
        return

    media_posts: list[MediaPost] = []
    for post in posts:
        try:
            urls = await extract_media_urls_async(post)
            if urls:
                media_posts.append(MediaPost(post=post, media_urls=urls))
            else:
                logger.debug("[%s] Skipping post %s: no media", feed.name, post.id)
        except Exception:
            logger.warning("[%s] Extraction failed for post %s", feed.name, post.id, exc_info=True)

    logger.info("[%s] %d/%d posts have media", feed.name, len(media_posts), len(posts))

    try:
        xml = build_feed(feed, media_posts)
        await write_feed(xml, feed, settings.output_dir)
        logger.info("[%s] Feed written to %s/%s.xml", feed.name, settings.output_dir, feed.name)
    except Exception:
        logger.error("[%s] Failed to write feed", feed.name, exc_info=True)
```

- [ ] **Step 4: Run all runner tests to verify they pass**

```bash
uv run pytest tests/test_runner.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/reddit_feeds/runner.py tests/test_runner.py
git commit -m "feat: implement async runner with concurrent feed processing"
```

---

## Task 10: CLI entry point

**Files:**
- Create: `src/reddit_feeds/cli.py`

No unit tests for the CLI — it's a thin wrapper. Verified by running it directly.

- [ ] **Step 1: Implement cli.py**

```python
import asyncio
import logging
import sys
from pathlib import Path

import typer

from reddit_feeds.config.loader import load_settings
from reddit_feeds.runner import run_once

app = typer.Typer(help="Fetch Reddit feeds and publish them as RSS files.")


@app.command()
def run(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config.yaml"),
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run continuously, sleeping interval seconds between runs"),
) -> None:
    """Fetch all configured feeds and write RSS files."""
    try:
        settings = load_settings(config)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Invalid config: {e}", err=True)
        raise typer.Exit(code=1) from e

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if daemon:
        asyncio.run(_run_daemon(settings))
    else:
        asyncio.run(run_once(settings))


async def _run_daemon(settings) -> None:
    """Loop forever: run all feeds, sleep interval, repeat."""
    from reddit_feeds.config.models import Settings
    import asyncio as _asyncio

    while True:
        await run_once(settings)
        await _asyncio.sleep(settings.interval)


def main() -> None:
    """Entry point for the `reddit-feeds` CLI command."""
    app()
```

- [ ] **Step 2: Reinstall the package so the entry point is registered**

```bash
uv sync
```

- [ ] **Step 3: Verify the CLI help works**

```bash
uv run reddit-feeds --help
```

Expected output includes:
```
Usage: reddit-feeds [OPTIONS] COMMAND [ARGS]...
  Fetch Reddit feeds and publish them as RSS files.
Commands:
  run  Fetch all configured feeds and write RSS files.
```

- [ ] **Step 4: Smoke test with the example config**

```bash
cp config.yaml.example config.yaml
mkdir -p output
uv run reddit-feeds run --config config.yaml
```

Expected: no Python errors. Log lines appear on stderr. `output/python.xml` and `output/rust.xml` created (or at least attempted — network may limit what's extracted).

- [ ] **Step 5: Run the full test suite one final time**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Run the linter**

```bash
uv run ruff check src/ tests/
```

Fix any reported issues, then:

```bash
uv run ruff format src/ tests/
```

- [ ] **Step 7: Final commit**

```bash
git add src/reddit_feeds/cli.py
git commit -m "feat: add typer CLI with run and --daemon mode"
```

---

## Self-Review Checklist

- [x] **Spec § Config** — covered by Tasks 2 + 3: models, loader, env-var overrides, validation
- [x] **Spec § CLI & Runner** — covered by Tasks 9 + 10: run_once, process_feed, daemon loop
- [x] **Spec § Reddit Fetching** — covered by Tasks 4 + 5: RedditPost, fetch_posts, User-Agent
- [x] **Spec § Media Extraction** — covered by Task 6: gallery-dl, fallback, run_in_executor
- [x] **Spec § RSS Building** — covered by Task 7: build_feed, MIME inference, description HTML
- [x] **Spec § Feed Writer** — covered by Task 8: aiofiles, slugify, mkdir
- [x] **Spec § Error Handling** — each process_feed has try/except per boundary; daemon never crashes
- [x] **Spec § Testing** — all five test modules with the cases listed in the spec
