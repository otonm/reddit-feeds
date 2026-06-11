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
        "    url: https://reddit.com/r/python/.rss\n"
        "    fetch_count: 10\n"
    )
    return config


@pytest.fixture
def rss_response_xml() -> str:
    """Return a realistic Reddit Atom 1.0 feed as served by `/r/SUB/.rss`."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
<entry>
  <author><name>/u/testuser</name><uri>https://www.reddit.com/user/testuser</uri></author>
  <category term="python" label="r/python"/>
  <content type="html">&lt;table&gt;&lt;tr&gt;&lt;td&gt;&lt;a href="https://www.reddit.com/r/python/comments/abc123/test_post/"&gt;&lt;img src="https://preview.redd.it/x.jpeg?width=640"/&gt;&lt;/a&gt;&lt;/td&gt;&lt;td&gt;&lt;span&gt;&lt;a href="https://i.redd.it/abc123.jpg"&gt;[link]&lt;/a&gt;&lt;/span&gt;&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</content>
  <id>t3_abc123</id>
  <media:thumbnail url="https://preview.redd.it/x.jpeg"/>
  <link href="https://www.reddit.com/r/python/comments/abc123/test_post/"/>
  <updated>2024-11-14T22:13:46+00:00</updated>
  <published>2024-11-14T22:13:46+00:00</published>
  <title>Test Post Title</title>
</entry>
<entry>
  <author><name>/u/videouser</name><uri>https://www.reddit.com/user/videouser</uri></author>
  <content type="html">&lt;table&gt;&lt;tr&gt;&lt;td&gt;&lt;a href="https://www.reddit.com/r/aww/comments/vid001/cute_dog/"&gt;&lt;img src="https://external-preview.redd.it/dog.png"/&gt;&lt;/a&gt;&lt;/td&gt;&lt;td&gt;&lt;span&gt;&lt;a href="https://v.redd.it/vid001"&gt;[link]&lt;/a&gt;&lt;/span&gt;&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</content>
  <id>t3_vid001</id>
  <link href="https://www.reddit.com/r/aww/comments/vid001/cute_dog/"/>
  <updated>2024-11-14T20:00:00+00:00</updated>
  <published>2024-11-14T20:00:00+00:00</published>
  <title>Video Post</title>
</entry>
<entry>
  <author><name>/u/galuser</name><uri>https://www.reddit.com/user/galuser</uri></author>
  <content type="html">&lt;table&gt;&lt;tr&gt;&lt;td&gt;&lt;a href="https://www.reddit.com/r/aww/comments/gal001/kitten_pics/"&gt;&lt;img src="https://preview.redd.it/gal.png"/&gt;&lt;/a&gt;&lt;/td&gt;&lt;td&gt;&lt;span&gt;&lt;a href="https://www.reddit.com/r/aww/comments/gal001/kitten_pics/gallery"&gt;[link]&lt;/a&gt;&lt;/span&gt;&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</content>
  <id>t3_gal001</id>
  <link href="https://www.reddit.com/r/aww/comments/gal001/kitten_pics/"/>
  <updated>2024-11-14T18:00:00+00:00</updated>
  <published>2024-11-14T18:00:00+00:00</published>
  <title>Gallery Post</title>
</entry>
</feed>"""  # noqa: E501
