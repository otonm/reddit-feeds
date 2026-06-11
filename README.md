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
| `output_dir` | path | `output/` | Directory where RSS `.xml` files are written |
| `db_dir` | path | `db/` | Directory for internal state: global seen-URL set and per-feed item stores. |
| `interval` | int (seconds) | `900` | Sleep between daemon runs (minimum 300) |
| `log_level` | string | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `reddit_fetch_gap` | float (seconds) | `2.0` | Minimum delay between Reddit API calls across feeds to reduce rate-limit errors |
| `base_url` | string | `null` | Public base URL used to construct a `feeds.opml` file to help with importing a lot of feeds at once |
| `feeds[].name` | string | required | Feed name; slugified to produce the output filename |
| `feeds[].url` | string | required | Reddit subreddit `.json` URL |
| `feeds[].fetch_count` | int | `20` | Posts to fetch per run (1–100) |

### Environment variables

Top-level scalar fields can be overridden without editing `config.yaml`:

| Variable | Overrides |
|----------|-----------|
| `REDDIT_FEEDS_INTERVAL` | `interval` |
| `REDDIT_FEEDS_LOG_LEVEL` | `log_level` |
| `REDDIT_FEEDS_FETCH_GAP` | `reddit_fetch_gap` |
| `REDDIT_CLIENT_ID` | `reddit_client_id` |
| `REDDIT_CLIENT_SECRET` | `reddit_client_secret` |

Environment variables take precedence over `config.yaml`.

### Optional: Reddit API credentials (recommended for cloud deployments)

Reddit's public `www.reddit.com/.json` endpoint returns `403 Blocked` to requests from datacenter IPs, which means feeds running on VPS, Docker hosts, and most cloud providers will fail without authentication. The app works without credentials on residential networks, but is not reliable elsewhere.

To fix this, register an app at <https://www.reddit.com/prefs/apps> and use the `client_credentials` OAuth2 grant (no Reddit user account required):

1. Go to <https://www.reddit.com/prefs/apps> and click **create another app**.
2. Choose **script** (personal/headless use) or **web app** (server with a redirect URL).
3. Note the `client_id` (the string under the app name) and `client_secret`.
4. Set both as environment variables — `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` — in your deployment. Never commit them.

When both variables are set, the app acquires a bearer token, sends it on every request, and refreshes it automatically (tokens last 1 hour, refreshed 5 minutes before expiry). Authenticated requests go to `oauth.reddit.com` and have a higher rate limit (100 req/min per OAuth client vs ~10 req/min for unauthenticated).

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

## Feed format

Each RSS item contains:

- **`<description>`** — embedded HTML for direct in-reader media display: `<img>` for images/GIFs, `<video autoplay muted controls>` for video (clients that render HTML will autoplay silently)
- **`<enclosure>`** — first media URL as a typed enclosure for podcast-style clients
- **`<guid>`** — permalink to the Reddit post (used by readers for deduplication, not for navigation)
- No `<link>` — omitted intentionally so readers render the embedded media rather than opening Reddit

When `base_url` is configured, a `feeds.opml` file is also written to `output_dir` on every run, allowing one-click import of all feeds into any RSS client.

Feeds are updated incrementally: posts and media URLs that have already been seen are not re-added. A post whose media was partially seen (e.g. a reposted gallery) will appear with only the new media items.

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
      # base_url: https://reddit-feeds.<tailnet>.ts.net  # enables feeds.opml generation
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
