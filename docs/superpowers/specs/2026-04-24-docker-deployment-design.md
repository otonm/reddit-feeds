# Docker Deployment Design

**Date:** 2026-04-24
**Status:** Approved

## Problem

reddit-feeds had no container or CI setup. Deploying required manual steps on the host. The goal is a self-contained Docker image built and published automatically on every `main` push, with the smallest possible footprint.

## Decisions

### Base image: multi-stage Alpine

| Stage | Image | Role |
|-------|-------|------|
| builder | `ghcr.io/astral-sh/uv:python3.12-alpine` | Installs runtime deps into `.venv` |
| runtime | `python:3.12-alpine` | Runs the app; uv is not present |

All dependencies (gallery-dl, httpx, feedgen, pyyaml, etc.) are pure Python — Alpine is safe, no native-extension complications.

### Run mode: daemon

The container uses `--daemon`, so it loops forever and sleeps `interval` seconds between runs. No external scheduler needed.

### CI trigger: push to main → `latest`

Every commit to `main` builds and pushes `ghcr.io/<owner>/reddit-feeds:latest`. Tests must pass before the image is built (`needs: test`).

### Health check: sentinel file

`run_once()` touches `/tmp/reddit-feeds.last_run` after every successful cycle. The Dockerfile `HEALTHCHECK` verifies the file is less than 3600 seconds old — a 4× buffer over the default 900 s interval.

`stat -c %Y` is used instead of `date -r` because Alpine uses busybox (not GNU coreutils).

## Volume contract

| Mount | Container path | Mode |
|-------|---------------|------|
| `config.yaml` | `/app/config.yaml` | read-only |
| `output/` dir | `/app/output` | read-write |

## Files created / modified

| Path | Change |
|------|--------|
| `Dockerfile` | Multi-stage build |
| `.dockerignore` | Excludes tests, docs, output, config.yaml |
| `docker-compose.yml` | Single-service compose for local/prod use |
| `.github/workflows/docker.yml` | Test → build pipeline |
| `src/runner.py` | Added `Path("/tmp/reddit-feeds.last_run").touch()` after run |
