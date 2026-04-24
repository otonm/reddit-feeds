# reddit-feeds

Fetches Reddit subreddit JSON feeds, extracts direct media links from posts using gallery-dl, and republishes them as RSS 2.0 feeds containing only embedded images, GIFs, and videos. No Reddit credentials, API keys, or authentication required.

Subscribe to any subreddit as a clean media-only RSS feed in any reader.

---

## How it works

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

All configured feeds run concurrently via `asyncio.gather`. Posts with no resolvable media are silently skipped.

---

## Components

| Module | Role |
|--------|------|
| `src/reddit/client.py` | Fetches posts from Reddit's public `.json` endpoint; no auth needed |
| `src/media/extractor.py` | Uses gallery-dl (1000+ supported sites: imgur, redgifs, i.redd.it, etc.) to resolve direct media URLs; runs in a thread pool via `run_in_executor` to avoid blocking the event loop |
| `src/feed/builder.py` | Produces RSS 2.0 XML; each item embeds `<img>` / `<video>` HTML in `<description>` and sets a first-media `<enclosure>` for podcast-style clients |
| `src/feed/writer.py` | Async file write via aiofiles; filename is a URL-safe slug of the feed name (`EarthPorn` → `earthporn.xml`) |
| `src/runner.py` | Orchestrates one full cycle across all configured feeds; touches `/tmp/reddit-feeds.last_run` on completion (used by Docker health check) |
| `src/cli.py` | Typer CLI; supports one-shot and continuous daemon mode |
| `src/config/` | Pydantic models + YAML loader; validates all settings at startup |

---

## Installation

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/otonm/reddit-feeds.git
cd reddit-feeds
uv sync
cp config.yaml.example config.yaml
# edit config.yaml with your feeds, then:
uv run python src/cli.py --config config.yaml
```

---

## Configuration

Create `config.yaml` (see `config.yaml.example` for a starting point):

```yaml
output_dir: output/
interval: 900
log_level: INFO

feeds:
  - name: EarthPorn
    url: https://www.reddit.com/r/EarthPorn/.json
    fetch_items: 25
  - name: AbandonedPorn
    url: https://www.reddit.com/r/AbandonedPorn/.json
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_dir` | path | `output/` | Directory where RSS `.xml` files are written |
| `interval` | int (seconds) | `900` | Sleep between daemon runs (minimum 300) |
| `log_level` | string | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `feeds[].name` | string | required | Feed name; slugified to produce the output filename |
| `feeds[].url` | string | required | Reddit subreddit `.json` URL |
| `feeds[].fetch_items` | int | `20` | Posts to fetch per run (1–100) |

### Environment variables

All three top-level scalar fields can be overridden at runtime without editing `config.yaml`:

| Variable | Overrides | Example |
|----------|-----------|---------|
| `REDDIT_FEEDS_INTERVAL` | `interval` | `REDDIT_FEEDS_INTERVAL=1800` |
| `REDDIT_FEEDS_LOG_LEVEL` | `log_level` | `REDDIT_FEEDS_LOG_LEVEL=DEBUG` |
| `REDDIT_FEEDS_OUTPUT_DIR` | `output_dir` | `REDDIT_FEEDS_OUTPUT_DIR=/data/feeds` |

Environment variables take precedence over `config.yaml`. Useful for Docker and CI overrides without remounting the config file.

---

## CLI reference

```
uv run python src/cli.py [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config PATH` | `-c` | `config.yaml` | Path to configuration file |
| `--daemon` | `-D` | off | Run continuously, sleeping `interval` seconds between runs |
| `--debug` | `-d` | off | Force DEBUG log level (mutually exclusive with `--quiet`) |
| `--quiet` | `-q` | off | Suppress INFO logs; show warnings and errors only |

**Examples:**

```bash
# One-shot run
uv run python src/cli.py -c config.yaml

# Daemon mode with debug logging
uv run python src/cli.py -c config.yaml --daemon --debug

# Quiet daemon (warnings and errors only)
uv run python src/cli.py -c config.yaml --daemon --quiet
```

---

## Docker deployment

### Pre-built image

GitHub Actions builds and pushes `ghcr.io/otonm/reddit-feeds:latest` on every push to `main`.

```bash
docker pull ghcr.io/otonm/reddit-feeds:latest
```

The image is built from a multi-stage Dockerfile:
- **Builder stage**: `ghcr.io/astral-sh/uv:python3.12-alpine` installs runtime dependencies
- **Runtime stage**: `python:3.12-alpine` — only the virtualenv and `src/` are copied; uv is not present

### Running with Docker

```bash
docker run -d \
  --name reddit-feeds \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v $(pwd)/output:/app/output \
  ghcr.io/otonm/reddit-feeds:latest
```

### Running with Docker Compose

```bash
docker compose up -d
```

`docker-compose.yml` mounts `config.yaml` read-only and `output/` for RSS file output. The health check verifies the daemon completed a cycle within the last hour:

```bash
docker compose ps   # shows health status
```

### Building locally

```bash
docker build -t reddit-feeds:local .
```

---

## Serving feeds with Tailscale Funnel

[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) exposes a local port over HTTPS to the public internet or your tailnet — no reverse proxy config, no certificates to manage.

The simplest setup adds an nginx container that serves the `output/` directory, then funnels it.

### docker-compose.yml

```yaml
services:
  reddit-feeds:
    image: ghcr.io/otonm/reddit-feeds:latest
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./output:/app/output
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "test -f /tmp/reddit-feeds.last_run && [ $$(( $$(date +%s) - $$(stat -c %Y /tmp/reddit-feeds.last_run) )) -lt 3600 ]"]
      interval: 2m
      timeout: 10s
      start_period: 2m
      retries: 3

  server:
    image: nginx:alpine
    ports:
      - "127.0.0.1:8080:80"
    volumes:
      - ./output:/usr/share/nginx/html:ro
    restart: unless-stopped
    depends_on:
      - reddit-feeds
```

### Start and expose

```bash
# Start both containers
docker compose up -d

# Expose port 8080 via Tailscale Funnel (runs in background)
tailscale funnel --bg 8080
```

Tailscale provides HTTPS automatically. Your feeds are available at:

```
https://<machine>.<tailnet>.ts.net/earthporn.xml
https://<machine>.<tailnet>.ts.net/abandonedporn.xml
```

Subscribe to these URLs in any RSS reader (NetNewsWire, Reeder, Miniflux, Feedly, etc.).

### Stop the funnel

```bash
tailscale funnel --bg off
```

---

## Development

```bash
uv sync                  # install all deps including dev tools
uv run pytest            # run test suite (100% coverage enforced)
uv run ruff check        # lint
uv run ruff format .     # format
```

Tests use pytest-asyncio and pytest-httpx; no external services are required.
