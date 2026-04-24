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


@app.command()
def run(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to config.yaml"),
    ] = Path("config.yaml"),
    daemon: Annotated[
        bool,
        typer.Option("--daemon", "-d", help="Run continuously, sleeping interval seconds between runs"),
    ] = False,
) -> None:
    """Fetch all configured feeds and write RSS files."""
    try:
        settings = load_settings(config)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Invalid config: {e}", err=True)
        raise typer.Exit(code=1) from e

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if daemon:
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
