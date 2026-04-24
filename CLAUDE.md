## Project

**Reddit Feeds**

A Python application that fetches Reddit JSON feeds and republishes them as RSS feeds. It extracts links to media in posts and creates clean RSS feeds with only embedded media. The final feed thus only displays an image, a gallery of images, a gif or 
a video file. No Reddit credentials, API keys or authentication required.

**Core Value:** Users can subscribe to Reddit content via RSS without needing a Reddit account or API access.

### Constraints

- **Tech Stack**: Python 3.12, uv package manager
- **No Auth**: Must work without Reddit credentials or API keys
- **Output Format**: RSS 2.0 compliant feeds
- **CLI Only**: No web interface for v1

## Technology Stack

## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Runtime | Modern async support, native type hints, performance improvements. Required by project constraints. |
| httpx | 0.28.1 | Async HTTP client | Industry standard for async HTTP in Python. Native async/await support, connection pooling, proper timeout handling, and excellent error hierarchy. Replaces requests for async workflows. |
| gallery-dl | 1.31.10 | Media extraction | Battle-tested library supporting 1000+ sites including Reddit. Handles imgur, redgifs, gfycat etc. used in Reddit posts. Can be used as library, not just CLI. |
| feedgen | 1.0.0 | RSS/Atom feed generation | Standard library for generating RSS 2.0 and Atom feeds in Python. Supports enclosures for media, podcast extensions, and produces valid XML. |
| PyYAML | 6.0.3 | Configuration parsing | Standard YAML library for Python. Use `safe_load()` for security. Required for feed configuration. |
| typer | 0.24.1 | CLI framework | Modern CLI builder using Python type hints. Auto-generates help text, supports subcommands, validation. Built on Click but with better DX. |

### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-slugify | 8.0.4 | URL-safe filenames | Converting feed names to valid file names for RSS output. Handles unicode, special characters. |
| aiofiles | 25.1.0 | Async file I/O | Non-blocking file writes for RSS output. Essential for maintaining async context throughout the application. |

### Development Tools
| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| uv | latest | Package manager | Fast Python package installer. Used by project. Replaces pip/pip-tools. |
| ruff | 0.15.8 | Linter + Formatter | Written in Rust, 10-100x faster than flake8/black. Replaces isort, flake8, black, and more. Configure via `pyproject.toml`. |
| mypy | 1.19.1 | Type checker | Static type checking for Python. **Not yet in dev dependencies** but mentioned in PROJECT.md. |

## Installation
Applications runs in a docker container. It is configured through enironmental variables and outputs the feeds in a feeds folder.
The feeds are published using a Tailscale funnel o a similar mechanism.

## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| httpx | requests | Only for purely synchronous scripts. httpx can do sync too and is future-proof. |
| httpx | aiohttp | aiohttp is more complex with manual session management. httpx has better API design. |
| feedgen | django-feedgenerator | Only if already using Django. feedgen is standalone and more feature-rich. |
| feedgen | xml.etree (manual) | Never. Manual XML generation is error-prone and hard to validate. |
| typer | click | If you need Click's lower-level control. Typer is Click with better DX. |
| typer | argparse | Only for simple scripts. argparse requires more boilerplate, no type hints integration. |
| gallery-dl | youtube-dl/yt-dlp | yt-dlp for video-heavy workflows. gallery-dl is better for image/media galleries from Reddit. |

## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| requests | Blocking I/O, no async support. Breaks async event loop. | httpx |
| pickle for config | Security vulnerability, not human-readable. | PyYAML with safe_load() |
| yaml.load() (unsafe) | Arbitrary code execution vulnerability. | yaml.safe_load() |
| print() for CLI output | No formatting, no color support, not testable. | logger.info() |
| time.sleep() in async | Blocks entire event loop. | asyncio.sleep() |
| lxml for RSS generation | Verbose, easy to create invalid feeds. | feedgen |

# Development

This project uses **uv** for Python package management and running commands.

## Quick Start

```bash
# Install dependencies
uv sync

# Run the main application
uv run python main.py

# Run with specific command
uv run python -m <module>
```

## Project Overview

- **Python version**: 3.12
- **Package manager**: uv
- **Dependencies**: gallery-dl, httpx, pyyaml, aiofiles, python-slugify
- **Development tools**: ruff, mypy

## Documentation

When you need to search docs, ALWAYS use `context7` tools.

## Build/Lint Commands

### Using uv

```bash
# Install all dependencies (including dev dependencies)
uv sync

# Install a specific package
uv add <package>
uv add --dev <package>  # dev dependency

# Remove a package
uv remove <package>

# Upgrade dependencies
uv sync --upgrade

# Run Python scripts
uv run python script.py
uv run python -m module

# Lint with ruff
uv run ruff check
uv run ruff check --fix  # auto-fix issues

# Format code with ruff
uv run ruff format .
```

## Code Style Guidelines

### General Principles

- Write clean, readable, and maintainable code
- Keep functions small and focused (single responsibility)
- Use descriptive names for variables, functions, and classes
- Prefer explicit over implicit
- Avoid magic numbers - use constants

### Imports

```python
# Standard library imports first
import os
import sys
from typing import Optional, List, Dict

# Third-party imports
import requests
from gallery_dl import extractor

# Local application imports
from . import module
from .module import something
```

- Use absolute imports within the package
- Sort imports alphabetically within each group
- Use `from` imports for specific items to avoid polluting namespace

### Formatting

- **Line length**: 120 characters (ruff default)
- **Indentation**: 4 spaces
- **Blank lines**: Two between top-level definitions, one between method definitions
- **Trailing whitespace**: Remove

```python
# Good
def function_with_long_name(
    param1: str,
    param2: int,
) -> bool:
    """Docstring here."""
    if condition:
        return True
    return False


# Bad - cramped
def f(p1, p2): return p1 + p2
```

### Types

- Use type hints for all function parameters and return values
- built-in types

```python
# Target Python 3.12+
def process_items(items: list[str]) -> dict[str, int]:
    ...

# Or with typing module
from typing import List, Dict

def process_items(items: List[str]) -> Dict[str, int]:
    ...
```

### Naming Conventions

- **Variables/functions**: `snake_case` (e.g., `my_variable`, `get_data`)
- **Classes**: `PascalCase` (e.g., `RedditExtractor`, `FeedParser`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`, `DEFAULT_TIMEOUT`)
- **Private functions/variables**: `_leading_underscore` (e.g., `_internal_helper`)
- **Module names**: `snake_case` (e.g., `reddit_client.py`)

### Error Handling

- Use specific exception types
- Handle errors at the appropriate level
- Provide meaningful error messages

```python
# Good
def fetch_data(url: str) -> dict:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e

# Bad - bare except
try:
    ...
except:
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def function(param1: str, param2: int) -> bool:
    """Short one-line description.

    Longer description if needed.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param2 is invalid.
    """
```

### Async

- Use `async def` for all I/O-bound functions (network, file, DB, subprocesses).
- Use `asyncio.run()` only at the top-level entry point — never inside an async function.
- Prefer `await asyncio.gather()` for concurrent tasks; avoid sequential awaits when calls are independent.
- Never mix blocking I/O (e.g. `requests`, `open()`, `time.sleep()`) inside async functions — use `httpx`/`aiohttp`, `aiofiles`, `asyncio.sleep()` instead.
- If blocking code is unavoidable, offload it with `asyncio.get_event_loop().run_in_executor()`.
- Do not use `async def` for CPU-bound or purely synchronous functions — it adds overhead with no benefit.
- Avoid `asyncio.create_task()` fire-and-forget patterns unless the task lifecycle is explicitly managed.
- Use `async with` and `async for` for async context managers and iterators.
- Propagate async up the call chain — do not call `asyncio.run()` mid-stack to bridge sync/async boundaries.

## Notes

- Always run linters and type checkers before committing
- Keep changes focused and atomic

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
