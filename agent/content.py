"""Read a selected item's source: text to ground the summary in, and one image to show with it."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import config, fetch
from .sources import VIDEO_EXTENSIONS, Candidate, arxiv_id_from_url, fetch_arxiv_abstract

SKIPPED_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"}
MAIN_TAGS = {"article", "main"}
GITHUB_REPO = re.compile(r"^https?://github\.com/([\w.-]+)/([\w.-]+)/?$")
PAGE_IMAGE_META = ("og:image", "og:image:url", "og:image:secure_url", "twitter:image")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.main_depth = 0
        self.all_text: list[str] = []
        self.main_text: list[str] = []
        self.image = ""

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED_TAGS:
            self.skip_depth += 1
        elif tag in MAIN_TAGS:
            self.main_depth += 1
        elif tag == "meta" and not self.image:
            attributes = dict(attrs)
            key = (attributes.get("property") or attributes.get("name") or "").lower()
            if key in PAGE_IMAGE_META:
                self.image = (attributes.get("content") or "").strip()

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


def parse_page(html: str, page_url: str = "") -> tuple[str, str]:
    """(visible text, representative image URL) of a page.

    The text prefers the <article>/<main> region when it has real content; the image is the one
    the page itself declares for link previews (og:image / twitter:image), or "".
    """
    parser = _PageParser()
    parser.feed(html)
    main = re.sub(r"\s+", " ", " ".join(parser.main_text)).strip()
    text = main if len(main) >= 500 else re.sub(r"\s+", " ", " ".join(parser.all_text)).strip()
    image = urljoin(page_url, parser.image) if parser.image else ""
    return text, image


def media(url: str) -> dict | None:
    """Describe an image or video URL for the site, or None when it cannot be embedded safely."""
    if not url.startswith("https://"):  # the site is served over https
        return None
    path = urlparse(url).path.lower()
    if path.endswith(VIDEO_EXTENSIONS):
        return {"type": "video", "url": url}
    # Page preview images often have no file extension, so anything that is not a video is an image.
    return {"type": "image", "url": url}


def _fetch_page(url: str) -> tuple[str, str]:
    repo = GITHUB_REPO.match(url)
    if repo:  # README instead of the repository page; GitHub's preview image is only a title card
        owner, name = repo.groups()
        raw = fetch.get(f"https://raw.githubusercontent.com/{owner}/{name}/HEAD/README.md", retries=1)
        return raw.decode("utf-8", errors="replace"), ""
    body = fetch.get(url, timeout=20, retries=1, max_bytes=2_000_000)
    if body.startswith(b"%PDF"):
        return "", ""
    return parse_page(body.decode("utf-8", errors="replace"), url)


def read_source(candidate: Candidate) -> tuple[str, dict | None]:
    """(source text, media) for an item: abstract + uploaded figure for papers, article text +
    preview image for links. Missing parts come back as "" / None."""
    if candidate.summary and candidate.id.startswith("arxiv:"):
        return candidate.summary, media(candidate.media)
    image = ""
    try:
        paper_id = arxiv_id_from_url(candidate.url)
        if paper_id:
            text = fetch_arxiv_abstract(paper_id)
        else:
            text, image = _fetch_page(candidate.url)
    except Exception as error:  # noqa: BLE001 - arbitrary third-party sites; fall back to what we have
        print(f"::notice::could not fetch {candidate.url}: {error!r}")
        text = ""
    text = "\n\n".join(part for part in (candidate.summary, text) if part)
    return text[: config.ARTICLE_MAX_CHARS], media(candidate.media or image)
