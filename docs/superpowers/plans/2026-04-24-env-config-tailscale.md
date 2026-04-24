# Env Config, Interval Floor & Tailscale Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the minimum refresh interval to 5 minutes, document existing env var overrides in docker-compose and README, and rewrite the Tailscale deployment section with correct commands and a fully-containerised sidecar example.

**Architecture:** One-constant code change to `models.py`; two config file edits (`docker-compose.yml`, existing `docker-compose.yml` update); one doc file rewrite (`README.md`). No new modules. No new dependencies.

**Tech Stack:** Python 3.12, Pydantic v2, Docker Compose, Tailscale Funnel / `tailscale/tailscale` container.

---

### Task 1: Raise minimum interval — tests first

**Files:**
- Modify: `tests/test_config.py` (lines 54–60)
- Modify: `src/config/models.py` (lines 7, 39)

- [ ] **Step 1: Update `test_interval_at_boundary_60` to assert the new boundary and add a below-boundary test**

In `tests/test_config.py`, replace lines 58–60:

```python
def test_interval_at_boundary_60(self):
    s = Settings(feeds=[], interval=60)
    assert s.interval == 60
```

with:

```python
def test_interval_at_boundary_300(self):
    s = Settings(feeds=[], interval=300)
    assert s.interval == 300

def test_interval_at_299_raises(self):
    with pytest.raises(ValidationError):
        Settings(feeds=[], interval=299)
```

- [ ] **Step 2: Run tests to confirm the two new tests fail**

```bash
uv run pytest tests/test_config.py::TestSettings::test_interval_at_boundary_300 tests/test_config.py::TestSettings::test_interval_at_299_raises -v
```

Expected: `test_interval_at_boundary_300` PASSES (300 ≥ 60 already), `test_interval_at_299_raises` FAILS (299 currently accepted).

- [ ] **Step 3: Update `_MIN_INTERVAL` and its error message in `src/config/models.py`**

Change line 7:
```python
_MIN_INTERVAL = 300
```

Change the validator error message at the `raise ValueError` line inside `validate_interval`:
```python
msg = f"interval must be at least 300 seconds, got {v}"
```

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest
```

Expected: all 73 tests pass, 100% coverage.

- [ ] **Step 5: Commit**

```bash
git add src/config/models.py tests/test_config.py
git commit -m "feat: raise minimum interval from 60s to 300s (5 minutes)"
```

---

### Task 2: Expose env vars in docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add `environment:` block to the `reddit-feeds` service**

The current `docker-compose.yml` has no `environment:` section. Add it after `restart: unless-stopped`, before `healthcheck:`:

```yaml
services:
  reddit-feeds:
    image: ghcr.io/otonm/reddit-feeds:latest
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./output:/app/output
    restart: unless-stopped
    environment:
      - REDDIT_FEEDS_INTERVAL=900       # optional: overrides config.yaml interval
      - REDDIT_FEEDS_LOG_LEVEL=INFO     # optional: overrides config.yaml log_level
    healthcheck:
      test: ["CMD-SHELL", "test -f /tmp/reddit-feeds.last_run && [ $$(( $$(date +%s) - $$(stat -c %Y /tmp/reddit-feeds.last_run) )) -lt 3600 ]"]
      interval: 2m
      timeout: 10s
      start_period: 2m
      retries: 3
```

- [ ] **Step 2: Lint**

```bash
uv run ruff check
```

Expected: `All checks passed!` (no Python changes, just YAML).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: expose REDDIT_FEEDS_INTERVAL and REDDIT_FEEDS_LOG_LEVEL in docker-compose"
```

---

### Task 3: README — environment variables subsection

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add an "Environment variables" subsection under the Configuration section**

After the Fields table and before the closing `---` of the Configuration section, insert:

```markdown
### Environment variables

All three top-level scalar fields can be overridden at runtime without editing `config.yaml`:

| Variable | Overrides | Example |
|----------|-----------|---------|
| `REDDIT_FEEDS_INTERVAL` | `interval` | `REDDIT_FEEDS_INTERVAL=1800` |
| `REDDIT_FEEDS_LOG_LEVEL` | `log_level` | `REDDIT_FEEDS_LOG_LEVEL=DEBUG` |
| `REDDIT_FEEDS_OUTPUT_DIR` | `output_dir` | `REDDIT_FEEDS_OUTPUT_DIR=/data/feeds` |

Environment variables take precedence over `config.yaml`. Useful for Docker and CI overrides without remounting the config file.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document REDDIT_FEEDS_* environment variable overrides"
```

---

### Task 4: README — Tailscale direct funnel (replace nginx)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the entire "Serving with Tailscale Funnel" section**

Find the section starting with `## Serving with Tailscale Funnel` and replace it entirely with:

```markdown
## Serving with Tailscale Funnel

[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) exposes the output directory over HTTPS to the public internet — no certificates, no reverse proxy, no extra containers required.

### Direct serving

```bash
# Start the feeds app
docker compose up -d

# Serve the output directory publicly via Tailscale Funnel
tailscale funnel /absolute/path/to/output
```

Tailscale handles TLS automatically. Your feeds are available at:

```
https://<machine>.ts.net/earthporn.xml
https://<machine>.ts.net/abandonedporn.xml
```

Subscribe to these URLs in any RSS reader (NetNewsWire, Reeder, Miniflux, Feedly, etc.).

To stop:

```bash
tailscale funnel off
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: replace nginx Tailscale example with direct tailscale funnel command"
```

---

### Task 5: README — Tailscale container sidecar deployment

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append a new "Fully containerised: Tailscale sidecar" subsection after Task 4's section**

Add immediately after the `tailscale funnel off` block:

````markdown
### Fully containerised: Tailscale sidecar

For deployments where Tailscale must also run inside Docker (e.g. a remote server with no Tailscale installed), use a `tailscale/tailscale` sidecar. It shares the output volume with the feeds container and serves it as a Funnel.

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

`${TS_CERT_DOMAIN}` is resolved automatically by the Tailscale container at runtime.

**2. Create `.env`:**

```
TS_AUTHKEY=tskey-auth-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Generate an auth key at [Tailscale admin → Settings → Keys](https://login.tailscale.com/admin/settings/keys). Use a reusable, pre-authenticated key for server deployments.

**3. Use this `docker-compose.yml`:**

```yaml
services:
  reddit-feeds:
    image: ghcr.io/otonm/reddit-feeds:latest
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - feeds-output:/app/output
    restart: unless-stopped
    environment:
      - REDDIT_FEEDS_INTERVAL=900
      - REDDIT_FEEDS_LOG_LEVEL=INFO
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
      - SYS_MODULE
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
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add Tailscale container sidecar deployment example"
```

---

### Task 6: Push and verify

- [ ] **Step 1: Run full test suite one final time**

```bash
uv run pytest && uv run ruff check
```

Expected: all tests pass, 100% coverage, no lint errors.

- [ ] **Step 2: Push**

```bash
git push origin main
```
