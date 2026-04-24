# syntax=docker/dockerfile:1

# ── Builder ───────────────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

WORKDIR /app

# Install deps first — cached layer, only re-runs when lockfile changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source after deps to avoid busting the dep cache on source changes
COPY src/ ./src/

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-alpine AS runtime

WORKDIR /app

RUN adduser -D -u 1000 appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"

VOLUME ["/app/output"]

# stat -c %Y is busybox-compatible; sentinel is touched by run_once() after each cycle
HEALTHCHECK --interval=2m --timeout=10s --start-period=2m --retries=3 \
  CMD sh -c 'test -f /tmp/reddit-feeds.last_run && \
    [ $(( $(date +%s) - $(stat -c %Y /tmp/reddit-feeds.last_run) )) -lt 3600 ]'

USER appuser

CMD ["python", "src/cli.py", "--daemon"]
