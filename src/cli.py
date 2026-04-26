"""Reddit Feeds CLI entry point."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from config.loader import load_settings
from config.models import Settings
from runner import run_once

app = typer.Typer(help="Fetch Reddit feeds and publish them as RSS files.")
logger = logging.getLogger(__name__)


@app.command()
def run(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.yaml"),
    ] = Path("config.yaml"),
    *,
    daemon: Annotated[
        bool,
        typer.Option("--daemon", "-D", help="Run continuously, sleeping interval seconds between runs"),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", "-d", help="Enable debug logging (overrides config log_level)"),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress INFO logs; show warnings and errors only"),
    ] = False,
) -> None:
    """Fetch all configured feeds and write RSS files."""
    if debug and quiet:
        typer.echo("Error: --debug and --quiet are mutually exclusive", err=True)
        raise typer.Exit(code=1)

    try:
        settings = load_settings(config)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Invalid config: {e}", err=True)
        raise typer.Exit(code=1) from e

    if debug:
        log_level = "DEBUG"
    elif quiet:
        log_level = "WARNING"
    else:
        log_level = settings.log_level

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    logger.debug(
        "Config loaded from %s: %d feed(s), interval=%ds, log_level=%s",
        config,
        len(settings.feeds),
        settings.interval,
        log_level,
    )

    if daemon:
        logger.info("Daemon mode: will re-run every %ds", settings.interval)
        asyncio.run(_run_daemon(settings))
    else:
        asyncio.run(run_once(settings))


async def _run_daemon(settings: Settings) -> None:
    """Loop forever: run all feeds, sleep interval, repeat."""
    while True:
        await run_once(settings)
        await asyncio.sleep(settings.interval)


def main() -> None:
    """Entry point for the `reddit-feeds` CLI command."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
