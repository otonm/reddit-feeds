from pathlib import Path

import pytest


@pytest.fixture
def sample_config_yaml(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(
        "output_dir: output/\n"
        "interval: 600\n"
        "feeds:\n"
        "  - name: python\n"
        "    url: https://reddit.com/r/python/.json\n"
        "    fetch_count: 10\n"
    )
    return config


@pytest.fixture
def minimal_reddit_response() -> dict:
    return {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc123",
                        "title": "Test Post",
                        "author": "testuser",
                        "permalink": "/r/python/comments/abc123/test_post/",
                        "url": "https://i.redd.it/abc123.jpg",
                        "created_utc": 1700000000.0,
                        "post_hint": "image",
                        "is_gallery": False,
                        "selftext_html": None,
                    }
                }
            ]
        }
    }
