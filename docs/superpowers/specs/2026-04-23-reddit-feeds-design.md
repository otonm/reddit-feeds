# Reddit Feeds — Design Spec

**Date:** 2026-04-23
**Status:** Approved

## Overview

A Python CLI application that fetches Reddit JSON feeds, extracts direct media URLs from posts using gallery-dl, and republishes them as RSS 2.0 feeds. No Reddit credentials or API keys required. Runs as a one-shot command or a long-running daemon.

---

## 1. Configuration

### Schema (`config.yaml`)

```yaml
output_dir: output/       # default: output/
interval: 900             # seconds, daemon mode only; env: REDDIT_FEEDS_INTERVAL
feeds:
  - name: python
    url: https://reddit.com/r/python/.json
    fetch_items: 25       # default: 20, max: 100
```

### Pydantic-settings models

```
Settings
  output_dir: Path          (default: output/)
  interval: int             (default: 900)
  feeds: list[FeedConfig]

FeedConfig
  name: str
  url: HttpUrl
  fetch_items: int          (default: 20, validated: must be 1–100 — config error if outside range)
```

Top-level fields (`output_dir`, `interval`) are overridable via env vars prefixed `REDDIT_FEEDS_` (e.g., `REDDIT_FEEDS_INTERVAL=300`). Feed-level fields are config-file-only.

Config file path defaults to `config.yaml` in CWD, overridable with `--config PATH` CLI flag.

---

## 2. CLI & Runner

### Entry point (`cli.py`)

Typer-based. Single command:

```
reddit-feeds run [--config PATH] [--daemon]
```

- Without `--daemon`: fetch all feeds once and exit.
- With `--daemon`: loop forever, sleeping `interval` seconds between runs.

### Runner (`runner.py`)

```python
async def run_once(settings: Settings) -> None
```

Processes all feeds concurrently via `asyncio.gather`. Each feed runs through `process_feed`:

```
process_feed(feed, settings)
  1. fetch Reddit JSON          → list[RedditPost]
  2. extract media URLs         → list[MediaPost]  (skip posts with no media)
  3. build RSS XML              → str
  4. write .xml to output_dir
```

One feed failing does not affect others — exceptions are caught per-feed and logged.

Output filename: `{slugify(feed.name)}.xml` inside `output_dir`. Directory is created if missing.

Daemon loop (in `cli.py`):

```python
while True:
    await run_once(settings)
    await asyncio.sleep(settings.interval)
```

---

## 3. Reddit Fetching (`reddit/client.py`)

```python
async def fetch_posts(url: str, limit: int, client: httpx.AsyncClient) -> list[RedditPost]
```

- Appends `?limit={limit}` to the URL.
- Sends `User-Agent: reddit-feeds/0.1` (hardcoded).
- `httpx.AsyncClient` is created once per run and shared across all feeds (connection pooling).
- Timeout: 15 seconds.
- On any `httpx.HTTPError`: log WARNING, raise to let the runner skip this feed.

### `RedditPost` dataclass fields

| Field | Source in Reddit JSON |
|-------|-----------------------|
| `id` | `data.id` |
| `title` | `data.title` |
| `author` | `data.author` |
| `permalink` | `https://reddit.com` + `data.permalink` |
| `url` | `data.url` |
| `post_hint` | `data.post_hint` (optional) |
| `is_gallery` | `data.is_gallery` (optional, default False) |
| `created_utc` | `data.created_utc` |
| `selftext_html` | `data.selftext_html` (optional) |

---

## 4. Media Extraction (`media/extractor.py`)

```python
def extract_media_urls(post: RedditPost) -> list[str]
```

Synchronous. Called via `run_in_executor` so it does not block the event loop.

### Extraction strategy (priority order)

1. **gallery-dl** — `gallery_dl.extractor.find(post.url)`. If an extractor is found, iterate to get all media URLs. Handles imgur, redgifs, gfycat, i.redd.it, v.redd.it, and 1000+ hosts.
2. **Direct image fallback** — if gallery-dl returns nothing and `post_hint == "image"`, use `post.url` directly.
3. **No media** — return `[]`; post is skipped by the runner.

gallery-dl is configured programmatically (no `~/.gallery-dl.conf` dependency) with `write-pages: false` and `download: false` to extract URLs only, without downloading files.

---

## 5. RSS Feed Building (`feed/`)

### `MediaPost` dataclass

Combines `RedditPost` + `media_urls: list[str]`.

### `feed/builder.py`

```python
def build_feed(feed_config: FeedConfig, posts: list[MediaPost]) -> str
```

Returns RSS 2.0 XML string.

#### RSS item structure

| RSS field | Value |
|-----------|-------|
| `title` | post title |
| `link` | `https://reddit.com{permalink}` |
| `pubDate` | from `created_utc` |
| `guid` | `https://reddit.com{permalink}` |
| `description` | All media as `<img src="...">` tags; `.mp4`/`.webm` URLs wrapped in `<video src="...">` instead |
| `enclosure` | First media URL, MIME type inferred from extension |

#### MIME type inference

| Extension | MIME type |
|-----------|-----------|
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.png` | `image/png` |
| `.gif` | `image/gif` |
| `.mp4` | `video/mp4` |
| `.webm` | `video/webm` |
| unknown | `application/octet-stream` |

#### Feed-level metadata

- Title: `r/{name}`
- Link: subreddit URL (sans `.json`)
- Description: `Reddit feed for r/{name}`

### `feed/writer.py`

```python
async def write_feed(xml: str, feed_config: FeedConfig, output_dir: Path) -> None
```

Uses `aiofiles`. Creates `output_dir` if missing.

---

## 6. Error Handling & Logging

**Logging:** Standard `logging`. Level configurable via `REDDIT_FEEDS_LOG_LEVEL` env var (default `INFO`). Log lines include feed name as context prefix: `[python] Skipping post abc123: no media extracted`.

| Failure point | Behaviour |
|---------------|-----------|
| Config file missing/invalid | Fatal — exit with clear error message |
| Reddit HTTP error (per feed) | WARNING log, skip this feed, continue others |
| Reddit JSON parse error | WARNING log, skip feed |
| gallery-dl extraction failure (per post) | WARNING log, skip post |
| RSS write failure (per feed) | ERROR log, skip write, continue |
| Daemon loop unhandled exception | ERROR log, continue to next interval |

No retries in v1. Daemon mode retries naturally on the next interval.

---

## 7. Package Structure

```
src/reddit_feeds/
  __init__.py
  cli.py              # typer entry point
  runner.py           # async orchestration
  config/
    __init__.py
    loader.py         # pydantic-settings, YAML parsing
    models.py         # Settings, FeedConfig dataclasses
  reddit/
    __init__.py
    client.py         # httpx Reddit JSON fetching
    models.py         # RedditPost dataclass
  media/
    __init__.py
    extractor.py      # gallery-dl URL extraction
  feed/
    __init__.py
    builder.py        # feedgenerator RSS construction
    writer.py         # aiofiles RSS file writing
    models.py         # MediaPost dataclass

tests/
  test_config.py
  test_reddit_client.py
  test_media_extractor.py
  test_feed_builder.py
  test_runner.py
```

---

## 8. Testing

pytest + pytest-asyncio + pytest-httpx. No real network calls in tests.

| Module | Test coverage |
|--------|---------------|
| `config/` | Valid load, env var override, missing file, invalid YAML, fetch_items clamping |
| `reddit/client.py` | Mocked HTTP success, HTTP error, malformed JSON |
| `media/extractor.py` | Mocked gallery-dl success (single + multi URL), direct-image fallback, empty list for unsupported |
| `feed/builder.py` | Single image post, gallery post (all imgs in description, first as enclosure), video post, MIME inference |
| `runner.py` | One feed fails while others complete, concurrent execution |

---

## 9. Decisions & Constraints

- **No auth:** Reddit's public JSON API requires no credentials.
- **User-Agent:** Hardcoded to `reddit-feeds/0.1`.
- **gallery-dl as library:** Used via Python API, not subprocess.
- **Async boundary:** gallery-dl is sync; called via `run_in_executor`.
- **No retries in v1:** Daemon's interval provides natural retry.
- **Text/link-only posts:** Skipped entirely (no enclosure, no description media).
- **Gallery posts:** One RSS item, all images as `<img>` tags in description, first image as enclosure.
