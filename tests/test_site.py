import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent import config, content, digest, site


def make_digest(day: str, title: str = "Paper") -> dict:
    return {
        "date": day,
        "generated_at": f"{day}T22:20:00+00:00",
        "candidates": {},
        "usage": {},
        "items": [
            {
                "id": "arxiv:2611.00001",
                "title": title,
                "url": "https://arxiv.org/abs/2611.00001",
                "category": "VLM",
                "sources": ["hf_daily", "hackernews"],
                "signals": {"hf_upvotes": 12, "hn_points": 80},
                "links": {"arxiv": "https://arxiv.org/abs/2611.00001", "code": "javascript:alert(1)"},
                "headline": "핵심 한 줄",
                "tldr": "요약",
                "key_points": ["a", "b", "c"],
                "efficiency": "2x 빠름",
                "tags": ["quantization"],
            }
        ],
    }


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        patches = [
            mock.patch.object(config, "DIGEST_DIR", root / "digests"),
            mock.patch.object(config, "SITE_DIR", root / "_site"),
            mock.patch.object(config, "ROOT", root),
            mock.patch.object(config, "SITE_URL", "https://example.github.io/repo"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        config.DIGEST_DIR.mkdir()

    def save(self, data: dict) -> None:
        (config.DIGEST_DIR / f"{data['date']}.json").write_text(json.dumps(data), encoding="utf-8")

    def test_builds_home_day_archive_and_feed(self):
        self.save(make_digest("2026-11-24"))
        self.save(make_digest("2026-11-25", title="<script>x</script>"))
        self.assertEqual(site.build(), 2)

        home = (config.SITE_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("2026년 11월 25일 (수)", home)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", home)  # titles from the web are escaped
        self.assertNotIn("javascript:", home)  # and non-http links are dropped
        self.assertIn("HF Daily Papers ▲12 · Hacker News 80pts", home)
        self.assertIn('href="./2026-11-24/"', home)
        for path in ("2026-11-24/index.html", "2026-11-25/index.html", "archive/index.html", "feed.xml", "assets/style.css"):
            self.assertTrue((config.SITE_DIR / path).exists(), path)

    def test_builds_placeholder_without_digests(self):
        self.assertEqual(site.build(), 0)
        self.assertIn("아직 다이제스트가 없습니다", (config.SITE_DIR / "index.html").read_text(encoding="utf-8"))

    def test_featured_items_are_not_repeated(self):
        self.save(make_digest("2026-11-24"))
        seen = digest.seen_keys(digest.load_digests(), exclude_date="2026-11-25")
        self.assertIn("arxiv:2611.00001", seen)
        self.assertEqual(digest.seen_keys(digest.load_digests(), exclude_date="2026-11-24"), set())


class ContentTests(unittest.TestCase):
    def test_html_to_text_prefers_article_and_skips_scripts(self):
        body = "word " * 150
        html = f"<html><nav>Menu</nav><script>var x=1</script><article><p>{body}</p></article><p>Sidebar</p></html>"
        text = content.html_to_text(html)
        self.assertTrue(text.startswith("word word"))
        self.assertNotIn("Menu", text)
        self.assertNotIn("var x", text)
        self.assertNotIn("Sidebar", text)


if __name__ == "__main__":
    unittest.main()
