# Architecture

## Pipeline

Each configured feed runs through an async pipeline. Feeds are launched with a configurable gap (`reddit_fetch_gap`, default 2 s) between each Reddit API call to avoid rate-limiting. Once launched, they run concurrently. `SeenStore` is shared across all feeds and loaded/saved once per cycle by `run_once`.

```
Reddit RSS feed
      │
      ▼
 reddit/client.py      — HTTP GET with httpx, parses Atom 1.0 via feedparser
       │
       ▼
 media/extractor.py    — per post:
       │                  1. if URL is direct media (i.redd.it/foo.jpg etc.) → use as-is
       │                  2. if post_hint == "hosted:video" → yt-dlp resolves the
       │                     direct .mp4 from the DASH/HLS manifest
       │                  3. else (galleries, embeds, redirects) → gallery-dl
       │                     resolves media URLs from the post permalink
       │                  All three paths accept an optional cookies dict
       │                  (forwarded from settings.reddit_session) to bypass
       │                  Reddit's WAF block on datacenter IPs.
       ▼
 store/seen_store.py   — two-level dedup: post.url pre-filter + per-media-URL filter
 store/feed_store.py   — load existing items, append new ones, persist to db_dir
       │
       ▼
 feed/builder.py       — builds RSS 2.0 XML with <enclosure> + embedded HTML
       │
       ▼
 feed/writer.py        — writes <slug>.xml to output_dir asynchronously
```

Posts with no resolvable media are silently skipped. Posts whose `post.url` is already in `SeenStore` skip gallery-dl entirely. Posts where all extracted media URLs are already seen are also skipped. Posts where only *some* media URLs are new (partial reposts) are included with only the unseen media URLs. Cross-feed deduplication is best-effort: concurrent coroutines can interleave between a `SeenStore.contains()` check and the subsequent `SeenStore.add()`, allowing rare duplicates across feeds processed in the same cycle. Per-feed errors are caught and logged without stopping other feeds.

## Components

| Module | Role |
|--------|------|
| `src/reddit/client.py` | Fetches posts from Reddit's public `.rss` Atom feed (the JSON endpoint is deprecated — see https://www.reddit.com/r/modnews/comments/1tq9vxo); parses with feedparser; infers `post_hint` and `is_gallery` from URL patterns; retries up to 2× on 429/403, honouring the `Retry-After` header (falls back to 2 s / 4 s exponential backoff) |
| `src/media/extractor.py` | Three-way dispatch per post: (a) direct media URL (`i.redd.it/foo.jpg`) → use as-is, (b) `hosted:video` → `_try_yt_dlp` (yt-dlp resolves the DASH/HLS manifest to a direct `.mp4`; uses `post.permalink` so yt-dlp can authenticate against the post page), (c) everything else (galleries, embeds, redirects) → gallery-dl on the post permalink. All three paths accept an optional `cookies: dict[str, str]`; when `Settings.reddit_session` is set, the runner builds `{"reddit_session": value}` and passes it through (gallery-dl: `extractor.reddit.cookies`; yt-dlp: temp Mozilla cookies.txt via `cookiefile`). The yt-dlp import is lazy so image-only feeds don't pay the import cost. For gallery-dl failures, `AbortExtraction` is special-cased to a one-line WARNING; full payload is at DEBUG. Runs in a thread pool via `run_in_executor` to avoid blocking the event loop. |
| `src/store/models.py` | `StoredItem` dataclass — the persistent feed item representation; serialises to/from JSON |
| `src/store/seen_store.py` | `SeenStore` — global in-memory `set[str]` of seen `post.url` + media URLs; backed by `{db_dir}/seen.json`; shared across all feeds within a cycle |
| `src/store/feed_store.py` | `FeedStore` — per-feed ordered list of `StoredItem` backed by `{db_dir}/{slug}.json`; loaded at the start of each feed cycle and saved after new items are appended |
| `src/feed/builder.py` | Produces RSS 2.0 XML from a `list[StoredItem]`; images use `<img>`, videos use `<video autoplay muted controls>`; sets a first-media `<enclosure>`; no `<link>` — omitting it prevents RSS readers from opening Reddit instead of rendering the embedded media; item identity uses `<guid>` (permalink) |
| `src/feed/writer.py` | Async file write via aiofiles; filename is a URL-safe slug of the feed name (`EarthPorn` → `earthporn.xml`) |
| `src/feed/opml.py` | Builds OPML 2.0 XML index from all configured feeds (`build_opml`) and writes `feeds.opml` to `output_dir` (`write_opml`); only called when `base_url` is set |
| `src/runner.py` | Orchestrates one full cycle: cleans up orphaned files for removed feeds, loads `SeenStore`, launches feeds with `reddit_fetch_gap` stagger between Reddit calls, saves `SeenStore`, touches `/tmp/reddit-feeds.last_run` |
| `src/cli.py` | Typer CLI; one-shot and daemon mode; configures logging |
| `src/config/` | Pydantic models + YAML loader; env var overrides for `interval`, `log_level`, `reddit_fetch_gap`, and `reddit_session`; `output_dir` and `db_dir` are config-file-only (env overrides removed to prevent silently bypassing Docker volume mounts); `FeedConfig.url` validator requires `.rss` |

## Docker image

Multi-stage build to minimise the final image size:

- **Builder**: `ghcr.io/astral-sh/uv:python3.12-alpine` — runs `uv sync --frozen --no-dev` to install dependencies into `.venv`
- **Runtime**: `python:3.12-alpine` — copies only `.venv/` and `src/`; uv is not present at runtime

The final image contains only the Alpine OS, the Python virtualenv, and `src/`. Runs as a non-root user (`appuser`, uid 1000).

### Health check

After each successful `run_once()` cycle, `runner.py` touches `/tmp/reddit-feeds.last_run`. The Dockerfile `HEALTHCHECK` verifies the file is less than 3600 seconds old — a 4× buffer over the default 900 s interval. Uses `stat -c %Y` (busybox-compatible) rather than `date -r` (GNU only).

## CI/CD

`.github/workflows/docker.yml` — two jobs on every push to `main`:

1. **test** — `uv sync` + `uv run pytest` (100% coverage enforced)
2. **build** (needs: test) — builds and pushes `ghcr.io/<owner>/reddit-feeds:latest` to GHCR using GitHub Actions layer cache

## Development

```bash
uv sync                  # install all deps including dev tools
uv run pytest            # test suite (100% coverage required)
uv run ruff check        # lint
uv run ruff format .     # format
```

Tests use pytest-asyncio and pytest-httpx; no external services required. All async tests run automatically via `asyncio_mode = "auto"`.

## Dependencies

| Package | Purpose |
|---------|---------|
| `httpx` | Async HTTP client for Reddit RSS |
| `feedparser` | Atom 1.0 feed parser (Python stdlib `email.utils` handles RFC 2822 dates as a fallback) |
| `gallery-dl` | Media URL extraction (1000+ sites); moved its canonical repo to https://codeberg.org/mikf/gallery-dl but PyPI distribution is unchanged |
| `yt-dlp` | Used directly by `media/extractor.py` for `hosted:video` posts (DASH/HLS manifest → direct `.mp4` URL); also used internally by gallery-dl |
| `feedgen` | RSS 2.0 feed generation |
| `pyyaml` | Config file parsing (`safe_load` only) |
| `pydantic` | Config model validation |
| `aiofiles` | Async RSS file writes |
| `python-slugify` | Feed name → safe filename |
| `typer` | CLI framework |
