# Architecture

## Pipeline

Each configured feed runs through a four-stage async pipeline. All feeds execute concurrently via `asyncio.gather`.

```
Reddit JSON API
      │
      ▼
 reddit/client.py      — HTTP GET with httpx, parses post list
      │
      ▼
 media/extractor.py    — gallery-dl resolves direct media URLs per post
      │
      ▼
 feed/builder.py       — builds RSS 2.0 XML with <enclosure> + embedded HTML
      │
      ▼
 feed/writer.py        — writes <slug>.xml to output_dir asynchronously
```

Posts with no resolvable media are silently skipped. Per-feed errors are caught and logged without stopping other feeds.

## Components

| Module | Role |
|--------|------|
| `src/reddit/client.py` | Fetches posts from Reddit's public `.json` endpoint using httpx; no auth |
| `src/media/extractor.py` | Uses gallery-dl (1000+ supported sites) to resolve direct media URLs; runs in a thread pool via `run_in_executor` to avoid blocking the event loop |
| `src/feed/builder.py` | Produces RSS 2.0 XML; each item embeds `<img>` / `<video>` HTML in `<description>` and sets a first-media `<enclosure>` for podcast-style clients |
| `src/feed/writer.py` | Async file write via aiofiles; filename is a URL-safe slug of the feed name (`EarthPorn` → `earthporn.xml`) |
| `src/runner.py` | Orchestrates one full cycle across all configured feeds; touches `/tmp/reddit-feeds.last_run` on completion (used by Docker health check) |
| `src/cli.py` | Typer CLI; one-shot and daemon mode; configures logging |
| `src/config/` | Pydantic models + YAML loader; env var overrides applied in `loader.py` |

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
| `httpx` | Async HTTP client for Reddit JSON API |
| `gallery-dl` | Media URL extraction (1000+ sites) |
| `feedgen` | RSS 2.0 feed generation |
| `pyyaml` | Config file parsing (`safe_load` only) |
| `pydantic` | Config model validation |
| `aiofiles` | Async RSS file writes |
| `python-slugify` | Feed name → safe filename |
| `typer` | CLI framework |
