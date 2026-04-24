# Env Config & Tailscale Deployment Design

**Date:** 2026-04-24
**Status:** Approved

## Problem

- Minimum refresh interval of 60 s is too aggressive for a polling app with no API key — 5 min is a safer floor.
- Env var overrides already exist in code (`loader.py`) but are undocumented and not surfaced in docker-compose.
- README Tailscale section used nginx as a middleman; Tailscale Serve can serve a directory directly.
- No docker-compose example using a Tailscale sidecar container for fully containerised deployments.

## Changes

### 1 — Minimum interval: 60 s → 300 s

`src/config/models.py`, `_MIN_INTERVAL = 60` → `_MIN_INTERVAL = 300`.
Update the validator error message to match.

### 2 — Env var documentation and docker-compose exposure

`src/config/loader.py` already implements three overrides:

| Env var | Config field | Type |
|---------|-------------|------|
| `REDDIT_FEEDS_INTERVAL` | `interval` | int (seconds) |
| `REDDIT_FEEDS_LOG_LEVEL` | `log_level` | string |
| `REDDIT_FEEDS_OUTPUT_DIR` | `output_dir` | path |

No code change needed. Changes:
- `docker-compose.yml`: add `environment:` block with commented-out defaults for `REDDIT_FEEDS_INTERVAL` and `REDDIT_FEEDS_LOG_LEVEL`.
- `README.md`: add "Environment variables" subsection under Configuration.

### 3 — README Tailscale section: remove nginx, use direct file serving

Replace the nginx + docker-compose approach with:

```bash
docker compose up -d
tailscale serve --https=443 /absolute/path/to/output
tailscale funnel 443 on
```

Tailscale Serve serves a directory natively. Feeds available at `https://<machine>.ts.net/<slug>.xml`.

### 4 — README: new Tailscale container deployment example

A separate named section showing a two-service docker-compose with a `tailscale/tailscale` sidecar:

- `reddit-feeds`: unchanged, uses a named volume for output
- `tailscale`: `tailscale/tailscale` image; shares the output named volume at `/feeds`; auth via `TS_AUTHKEY`; configured via `TS_SERVE_CONFIG` pointing to `ts-serve.json`

Requires a `ts-serve.json` serve config and a `TS_AUTHKEY` in `.env`. Both files are shown in the README.

## Files modified

| Path | Change |
|------|--------|
| `src/config/models.py` | `_MIN_INTERVAL` 60 → 300, update error message |
| `docker-compose.yml` | Add `environment:` block |
| `README.md` | Env var docs, Tailscale section rewrite, new container example |
