import unittest
from datetime import datetime, timezone

from agent import sources

NOW = datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)

ARXIV_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2611.32064v2</id>
    <title>Fast  Tokens:
      A Study</title>
    <published>2026-11-24T06:51:43Z</published>
    <summary>  We prune
      tokens. </summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2611.00001v1</id>
    <title>Too old</title>
    <published>2026-11-01T00:00:00Z</published>
    <summary>Old.</summary>
  </entry>
</feed>"""


class ParseTests(unittest.TestCase):
    def test_hn_story_linking_to_arxiv_becomes_a_paper(self):
        hits = [
            {"objectID": "1", "title": "A paper", "url": "https://arxiv.org/pdf/2611.12345v2", "points": 72},
            {"objectID": "2", "title": "Show HN: thing", "url": None, "story_text": "<p>Hi &amp; bye</p>"},
        ]
        paper, show = sources.parse_hn(hits)
        self.assertEqual(paper.id, "arxiv:2611.12345")
        self.assertEqual(paper.url, "https://arxiv.org/abs/2611.12345")
        self.assertEqual(paper.signals["hn_points"], 72)
        self.assertEqual(show.id, "hn:2")
        self.assertEqual(show.url, "https://news.ycombinator.com/item?id=2")
        self.assertEqual(show.summary, "Hi & bye")

    def test_hf_keeps_recent_papers_most_upvoted_first(self):
        def entry(paper_id, day, upvotes):
            return {"paper": {"id": paper_id, "title": paper_id, "summary": "s", "upvotes": upvotes,
                              "submittedOnDailyAt": f"2026-11-{day}T00:00:00.000Z"}}

        payload = [entry("b", "25", 1), entry("a", "14", 90), entry("c", "25", 7), entry("c", "25", 7),
                   entry("old", "02", 500)]
        self.assertEqual([c.id for c in sources.parse_hf(payload, NOW)], ["arxiv:a", "arxiv:c", "arxiv:b"])

    def test_hf_takes_a_picture_over_a_video(self):
        entry = {"paper": {"id": "m", "title": "m", "summary": "s", "submittedOnDailyAt": "2026-11-25T00:00:00.000Z"},
                 "mediaUrls": ["https://cdn/a.mp4", "https://cdn/b.png"]}
        (paper,) = sources.parse_hf([entry], NOW)
        self.assertEqual(paper.media, "https://cdn/b.png")

    def test_arxiv_strips_version_and_whitespace_and_drops_old(self):
        (paper,) = sources.parse_arxiv(ARXIV_XML, NOW)
        self.assertEqual(paper.id, "arxiv:2611.32064")
        self.assertEqual(paper.title, "Fast Tokens: A Study")
        self.assertEqual(paper.summary, "We prune tokens.")

    def test_merge_combines_the_same_paper_from_two_sources(self):
        from_hn = sources.parse_hn(
            [{"objectID": "9", "title": "Wow, tokens", "url": "https://arxiv.org/abs/2611.32064", "points": 50}]
        )
        from_arxiv = sources.parse_arxiv(ARXIV_XML, NOW)
        (merged,) = sources.merge(from_hn + from_arxiv)
        self.assertEqual(merged.title, "Fast Tokens: A Study")
        self.assertEqual(merged.sources, ["hackernews", "arxiv"])
        self.assertEqual(merged.summary, "We prune tokens.")
        self.assertEqual(merged.signals["hn_points"], 50)
        self.assertIn("hn", merged.links)


if __name__ == "__main__":
    unittest.main()
