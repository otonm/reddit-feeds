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
output_dir: output/   # web-served RSS files
db_dir: db/           # internal state — keep off the web server
interval: 900
log_level: INFO

feeds:
  - name: EarthPorn
    url: https://www.reddit.com/r/EarthPorn/.json
    fetch_count: 25
  - name: AbandonedPorn
    url: https://www.reddit.com/r/AbandonedPorn/.json
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_dir` | path | `output/` | Directory where RSS `.xml` files are written (web-served) |
| `db_dir` | path | `db/` | Directory for internal state: global seen-URL set and per-feed item stores. Keep this off the web server. |
| `interval` | int (seconds) | `900` | Sleep between daemon runs (minimum 300) |
| `log_level` | string | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `feeds[].name` | string | required | Feed name; slugified to produce the output filename |
| `feeds[].url` | string | required | Reddit subreddit `.json` URL |
| `feeds[].fetch_count` | int | `20` | Posts to fetch per run (1–100) |

### Environment variables

Top-level scalar fields can be overridden without editing `config.yaml`:

| Variable | Overrides |
|----------|-----------|
| `REDDIT_FEEDS_INTERVAL` | `interval` |
| `REDDIT_FEEDS_LOG_LEVEL` | `log_level` |
| `REDDIT_FEEDS_OUTPUT_DIR` | `output_dir` |
| `REDDIT_FEEDS_DB_DIR` | `db_dir` |

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
  -v $(pwd)/db:/app/db \
  ghcr.io/otonm/reddit-feeds:latest
```

`output/` holds the web-served RSS files. `db/` holds internal state (seen-URL index and per-feed item stores) — keep it off the web server.

**Run with Docker Compose:**

Edit the `configs.feeds-config.content` block in `docker-compose.yml` to add your feeds, then:

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
tailscale funnel --bg /path/to/output
```

Feeds available at:

```
https://<machine>.ts.net/earthporn.xml
https://<machine>.ts.net/abandonedporn.xml
```

To stop: `tailscale funnel off`

### Fully containerised: Tailscale sidecar

Use `docker-compose.tsfunnel.yml` (included in the repo). It runs the feeds app and a Tailscale sidecar together — feeds and Tailscale serve config are both embedded inline; no external config files needed.

**1. Create `.env`:**

```
TS_AUTHKEY=tskey-auth-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Generate an auth key at [Tailscale admin → Settings → Keys](https://login.tailscale.com/admin/settings/keys). Use a reusable, pre-authenticated key for server deployments.

**2. Edit feeds in `docker-compose.tsfunnel.yml`:**

Find the `configs.feeds-config.content` block and replace the example feeds with your own:

```yaml
configs:
  feeds-config:
    content: |
      feeds:
        - name: EarthPorn
          url: https://www.reddit.com/r/EarthPorn/.json
        - name: AbandonedPorn
          url: https://www.reddit.com/r/AbandonedPorn/.json
          fetch_count: 25
```

**3. Start:**

```bash
docker compose -f docker-compose.tsfunnel.yml up -d
```

Feeds available at `https://reddit-feeds.<tailnet>.ts.net/earthporn.xml`.

`$${TS_CERT_DOMAIN}` in the Tailscale serve config is a Docker Compose escape that writes `${TS_CERT_DOMAIN}` literally into the mounted file; Tailscale resolves it to your machine's cert domain at runtime.
