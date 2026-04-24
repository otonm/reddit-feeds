# reddit-feeds

Fetches Reddit subreddit JSON feeds, extracts direct media links from posts, and republishes them as RSS 2.0 feeds containing only embedded images, GIFs, and videos. No Reddit credentials, API keys, or authentication required.

Subscribe to any subreddit as a clean media-only RSS feed in any reader.

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

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_dir` | path | `output/` | Directory where RSS `.xml` files are written |
| `interval` | int (seconds) | `900` | Sleep between daemon runs (minimum 300) |
| `log_level` | string | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `feeds[].name` | string | required | Feed name; slugified to produce the output filename |
| `feeds[].url` | string | required | Reddit subreddit `.json` URL |
| `feeds[].fetch_items` | int | `20` | Posts to fetch per run (1–100) |

### Environment variables

Top-level scalar fields can be overridden without editing `config.yaml`:

| Variable | Overrides |
|----------|-----------|
| `REDDIT_FEEDS_INTERVAL` | `interval` |
| `REDDIT_FEEDS_LOG_LEVEL` | `log_level` |
| `REDDIT_FEEDS_OUTPUT_DIR` | `output_dir` |

Environment variables take precedence over `config.yaml`.

---

## CLI

```bash
uv run python src/cli.py [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config PATH` | `-c` | `config.yaml` | Path to configuration file |
| `--daemon` | `-D` | off | Run continuously, sleeping `interval` seconds between runs |
| `--debug` | `-d` | off | Force DEBUG log level |
| `--quiet` | `-q` | off | Warnings and errors only |

---

## Docker

Pull the latest image built by GitHub Actions on every push to `main`:

```bash
docker pull ghcr.io/otonm/reddit-feeds:latest
```

**Run with Docker:**

```bash
docker run -d \
  --name reddit-feeds \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v $(pwd)/output:/app/output \
  ghcr.io/otonm/reddit-feeds:latest
```

**Run with Docker Compose:**

```bash
docker compose up -d
docker compose ps   # shows health status
```

**Build locally:**

```bash
docker build -t reddit-feeds:local .
```

---

## Serving feeds with Tailscale Funnel

[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) exposes the output directory over HTTPS — no certificates or reverse proxy required.

### Direct serving

```bash
docker compose up -d
tailscale funnel /absolute/path/to/output
```

Feeds available at:

```
https://<machine>.ts.net/earthporn.xml
https://<machine>.ts.net/abandonedporn.xml
```

To stop: `tailscale funnel off`

### Fully containerised: Tailscale sidecar

For servers where Tailscale runs in Docker alongside the app.

**1. Create `ts-serve.json`:**

```json
{
  "TCP": {
    "443": {
      "HTTPS": true
    }
  },
  "Web": {
    "${TS_CERT_DOMAIN}:443": {
      "Handlers": {
        "/": {
          "Path": "/feeds/"
        }
      }
    }
  },
  "AllowFunnel": {
    "${TS_CERT_DOMAIN}:443": true
  }
}
```

**2. Create `.env`:**

```
TS_AUTHKEY=tskey-auth-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Get an auth key from [Tailscale admin → Settings → Keys](https://login.tailscale.com/admin/settings/keys). Use a reusable, pre-authenticated key.

**3. `docker-compose.yml`:**

```yaml
services:
  reddit-feeds:
    image: ghcr.io/otonm/reddit-feeds:latest
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - feeds-output:/app/output
    restart: unless-stopped
    environment:
      - REDDIT_FEEDS_INTERVAL
      - REDDIT_FEEDS_LOG_LEVEL
    healthcheck:
      test: ["CMD-SHELL", "test -f /tmp/reddit-feeds.last_run && [ $$(( $$(date +%s) - $$(stat -c %Y /tmp/reddit-feeds.last_run) )) -lt 3600 ]"]
      interval: 2m
      timeout: 10s
      start_period: 2m
      retries: 3

  tailscale:
    image: tailscale/tailscale
    hostname: reddit-feeds
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
      - TS_STATE_DIR=/var/lib/tailscale
      - TS_SERVE_CONFIG=/config/ts-serve.json
    volumes:
      - tailscale-state:/var/lib/tailscale
      - ./ts-serve.json:/config/ts-serve.json:ro
      - feeds-output:/feeds:ro
    cap_add:
      - NET_ADMIN
    restart: unless-stopped

volumes:
  tailscale-state:
  feeds-output:
```

**4. Start:**

```bash
docker compose up -d
```

Feeds available at `https://reddit-feeds.<tailnet>.ts.net/earthporn.xml`.
