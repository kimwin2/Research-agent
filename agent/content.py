"""Get readable text for a selected item, so the summary is grounded in more than a title."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from . import config, fetch
from .sources import Candidate, arxiv_id_from_url, fetch_arxiv_abstract

SKIPPED_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"}
MAIN_TAGS = {"article", "main"}
GITHUB_REPO = re.compile(r"^https?://github\.com/([\w.-]+)/([\w.-]+)/?$")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.main_depth = 0
        self.all_text: list[str] = []
        self.main_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED_TAGS:
            self.skip_depth += 1
        elif tag in MAIN_TAGS:
            self.main_depth += 1

    def handle_endtag(self, tag):
        if tag in SKIPPED_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in MAIN_TAGS:
            self.main_depth = max(0, self.main_depth - 1)

    def handle_data(self, data):
        if self.skip_depth or not data.strip():
            return
        self.all_text.append(data)
        if self.main_depth:
            self.main_text.append(data)


def html_to_text(html: str) -> str:
    """Visible text of a page, preferring the <article>/<main> region when it has real content."""
    parser = _TextExtractor()
    parser.feed(html)
    main = re.sub(r"\s+", " ", " ".join(parser.main_text)).strip()
    if len(main) >= 500:
        return main
    return re.sub(r"\s+", " ", " ".join(parser.all_text)).strip()


def _fetch_page_text(url: str) -> str:
    repo = GITHUB_REPO.match(url)
    if repo:
        owner, name = repo.groups()
        raw = fetch.get(f"https://raw.githubusercontent.com/{owner}/{name}/HEAD/README.md", retries=1)
        return raw.decode("utf-8", errors="replace")
    body = fetch.get(url, timeout=20, retries=1, max_bytes=2_000_000)
    if body.startswith(b"%PDF"):
        return ""
    return html_to_text(body.decode("utf-8", errors="replace"))


def content_for(candidate: Candidate) -> str:
    """Abstract for papers, article text for links. Empty string when nothing could be fetched."""
    if candidate.summary and candidate.id.startswith("arxiv:"):
        return candidate.summary
    try:
        paper_id = arxiv_id_from_url(candidate.url)
        text = fetch_arxiv_abstract(paper_id) if paper_id else _fetch_page_text(candidate.url)
    except Exception as error:  # noqa: BLE001 - arbitrary third-party sites; fall back to what we have
        print(f"::notice::could not fetch {candidate.url}: {error!r}")
        text = ""
    text = "\n\n".join(part for part in (candidate.summary, text) if part)
    return text[: config.ARTICLE_MAX_CHARS]
