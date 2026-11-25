"""Candidate collection: Hacker News, Hugging Face Daily Papers, arXiv.

Each source has a pure ``parse_*`` function (unit-tested) and a ``fetch_*`` function that does the
network calls. ``collect`` merges everything into one de-duplicated candidate list.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from . import config, fetch

ARXIV_ID = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html)|huggingface\.co/papers)/(\d{4}\.\d{4,5})")
PAPER_SOURCES = ("hf_daily", "arxiv")
ATOM = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass
class Candidate:
    id: str  # "arxiv:2611.01234" for papers, "hn:123456" for other HN stories
    title: str
    url: str
    sources: list[str] = field(default_factory=list)
    summary: str = ""  # abstract, or the text of a Show/Ask HN post
    short: str = ""  # one-sentence summary when the source provides one
    published: str = ""  # ISO timestamp
    signals: dict[str, int] = field(default_factory=dict)  # hn_points, hn_comments, hf_upvotes,
    # github_stars
    links: dict[str, str] = field(default_factory=dict)  # hn, hf, arxiv, code

    def to_dict(self) -> dict:
        return asdict(self)


def arxiv_id_from_url(url: str) -> str | None:
    match = ARXIV_ID.search(url or "")
    return match.group(1) if match else None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _strip_html(text: str) -> str:
    return _squash(html.unescape(re.sub(r"<[^>]+>", " ", text or "")))


# --- Hacker News -------------------------------------------------------------


def parse_hn(hits: list[dict]) -> list[Candidate]:
    candidates = []
    for hit in hits:
        title = _squash(hit.get("title") or "")
        if not title:
            continue
        discussion = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        url = hit.get("url") or discussion
        paper_id = arxiv_id_from_url(url)
        links = {"hn": discussion}
        if paper_id:
            url = f"https://arxiv.org/abs/{paper_id}"
            links["arxiv"] = url
        candidates.append(
            Candidate(
                id=f"arxiv:{paper_id}" if paper_id else f"hn:{hit['objectID']}",
                title=title,
                url=url,
                sources=["hackernews"],
                summary=_strip_html(hit.get("story_text") or ""),
                published=hit.get("created_at") or "",
                signals={
                    "hn_points": int(hit.get("points") or 0),
                    "hn_comments": int(hit.get("num_comments") or 0),
                },
                links=links,
            )
        )
    return candidates


def _hn_search(query: str, since: int, min_points: int, per_page: int) -> list[dict]:
    params = {
        "tags": "story",
        "hitsPerPage": per_page,
        "numericFilters": f"created_at_i>{since},points>={min_points}",
    }
    if query:
        params["query"] = query
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(params)
    return json.loads(fetch.get(url))["hits"]


def fetch_hn(now: datetime) -> list[Candidate]:
    since = int((now - timedelta(days=config.HN_WINDOW_DAYS)).timestamp())
    title_pattern = re.compile(config.HN_TITLE_PATTERN, re.IGNORECASE)

    found = _hn_search("", since, config.HN_FRONT_PAGE_MIN_POINTS, 100)
    for query in config.HN_QUERIES:
        found += _hn_search(query, since, config.HN_TOPIC_MIN_POINTS, 20)
    hits = {hit["objectID"]: hit for hit in found if title_pattern.search(hit.get("title") or "")}

    candidates = parse_hn(list(hits.values()))
    candidates.sort(key=lambda c: c.signals["hn_points"], reverse=True)
    return candidates[: config.HN_MAX_CANDIDATES]


# --- Hugging Face Daily Papers -------------------------------------------------


def parse_hf(payload: list[dict], now: datetime) -> list[Candidate]:
    cutoff = (now - timedelta(days=config.HF_MAX_AGE_DAYS)).isoformat()
    candidates: dict[str, Candidate] = {}
    for entry in payload:
        paper = entry.get("paper") or {}
        paper_id = paper.get("id")
        submitted = paper.get("submittedOnDailyAt") or entry.get("publishedAt") or ""
        if not paper_id or not submitted or submitted < cutoff:
            continue
        url = f"https://arxiv.org/abs/{paper_id}"
        links = {"arxiv": url, "hf": f"https://huggingface.co/papers/{paper_id}"}
        if paper.get("githubRepo"):
            links["code"] = paper["githubRepo"]
        signals = {"hf_upvotes": int(paper.get("upvotes") or 0)}
        if paper.get("githubStars"):
            signals["github_stars"] = int(paper["githubStars"])
        candidates[f"arxiv:{paper_id}"] = Candidate(
            id=f"arxiv:{paper_id}",
            title=_squash(paper.get("title") or entry.get("title") or ""),
            url=url,
            sources=["hf_daily"],
            summary=_squash(paper.get("summary") or entry.get("summary") or ""),
            short=_squash(paper.get("ai_summary") or ""),
            published=submitted,
            signals=signals,
            links=links,
        )
    ranked = sorted(candidates.values(), key=lambda c: c.signals["hf_upvotes"], reverse=True)
    return ranked[: config.HF_MAX_CANDIDATES]


def fetch_hf(now: datetime) -> list[Candidate]:
    """Page back through the daily papers (newest first) until the window is covered."""
    cutoff = (now - timedelta(days=config.HF_MAX_AGE_DAYS)).isoformat()
    payload: list[dict] = []
    for page in range(config.HF_MAX_PAGES):
        batch = json.loads(fetch.get(f"https://huggingface.co/api/daily_papers?limit=100&p={page}"))
        payload += batch
        oldest = min(((e.get("paper") or {}).get("submittedOnDailyAt") or "" for e in batch), default="")
        if len(batch) < 100 or oldest < cutoff:
            break
    return parse_hf(payload, now)


# --- arXiv -----------------------------------------------------------------------


def arxiv_query() -> str:
    categories = " OR ".join(f"cat:{c}" for c in config.ARXIV_CATEGORIES)
    topics = " OR ".join(f"abs:{t}" for t in config.ARXIV_TOPIC_TERMS)
    efficiency = " OR ".join(
        [f"ti:{t}" for t in config.ARXIV_TITLE_TERMS]
        + [f"abs:{p}" for p in config.ARXIV_ABSTRACT_PHRASES]
    )
    return f"({categories}) AND ({topics}) AND ({efficiency})"


def parse_arxiv(xml: bytes, now: datetime) -> list[Candidate]:
    cutoff = (now - timedelta(days=config.ARXIV_MAX_AGE_DAYS)).isoformat()
    candidates = []
    for entry in ET.fromstring(xml).findall("atom:entry", ATOM):
        paper_id = arxiv_id_from_url(entry.findtext("atom:id", "", ATOM))
        published = entry.findtext("atom:published", "", ATOM)
        if not paper_id or published < cutoff:
            continue
        url = f"https://arxiv.org/abs/{paper_id}"
        candidates.append(
            Candidate(
                id=f"arxiv:{paper_id}",
                title=_squash(entry.findtext("atom:title", "", ATOM)),
                url=url,
                sources=["arxiv"],
                summary=_squash(entry.findtext("atom:summary", "", ATOM)),
                published=published,
                links={"arxiv": url},
            )
        )
    return candidates


def fetch_arxiv(now: datetime) -> list[Candidate]:
    params = {
        "search_query": arxiv_query(),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": config.ARXIV_MAX_CANDIDATES,
    }
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    return parse_arxiv(fetch.get(url, timeout=60), now)


def fetch_arxiv_abstract(paper_id: str) -> str:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": paper_id})
    entry = ET.fromstring(fetch.get(url, timeout=60)).find("atom:entry", ATOM)
    return _squash(entry.findtext("atom:summary", "", ATOM)) if entry is not None else ""


# --- Merge -----------------------------------------------------------------------


def merge(candidates: list[Candidate]) -> list[Candidate]:
    """Collapse the same paper/story seen through several sources into one candidate."""
    merged: dict[str, Candidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.id)
        if existing is None:
            merged[candidate.id] = candidate
            continue
        # A paper source knows the real title; an HN submission title may be editorialised.
        if candidate.sources[0] in PAPER_SOURCES and existing.sources[0] not in PAPER_SOURCES:
            existing.title = candidate.title
        existing.sources += [s for s in candidate.sources if s not in existing.sources]
        existing.summary = max(existing.summary, candidate.summary, key=len)
        existing.short = existing.short or candidate.short
        existing.published = existing.published or candidate.published
        existing.signals.update(candidate.signals)
        existing.links.update(candidate.links)
    return list(merged.values())


def collect(now: datetime | None = None) -> tuple[list[Candidate], dict[str, int | str]]:
    """Fetch every source. A failing source is reported and skipped; all failing is an error."""
    now = now or datetime.now(timezone.utc)
    fetchers = {"hackernews": fetch_hn, "hf_daily": fetch_hf, "arxiv": fetch_arxiv}
    candidates: list[Candidate] = []
    stats: dict[str, int | str] = {}
    for name, fetcher in fetchers.items():
        try:
            found = fetcher(now)
        except Exception as error:  # noqa: BLE001 - one source being down must not stop the digest
            print(f"::warning::source {name} failed: {error!r}")
            stats[name] = f"failed: {type(error).__name__}"
            continue
        stats[name] = len(found)
        candidates += found
    if all(isinstance(value, str) for value in stats.values()):
        raise RuntimeError(f"every source failed: {stats}")
    return merge(candidates), stats
