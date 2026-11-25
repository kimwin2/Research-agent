"""Render data/digests/*.json into a static site in _site/ (for GitHub Pages).

    python -m agent.site
"""

from __future__ import annotations

import calendar
import os
import shutil
from datetime import date, datetime
from email.utils import format_datetime
from html import escape
from itertools import groupby

from . import config
from .digest import load_digests

ASSETS = config.ROOT / "agent" / "assets"
WEEKDAYS = "월화수목금토일"
SOURCE_LABELS = {"hackernews": "Hacker News", "hf_daily": "HF Daily Papers", "arxiv": "arXiv"}
LINK_LABELS = [("arxiv", "arXiv"), ("hf", "HF Papers"), ("hn", "HN 토론"), ("code", "Code")]
HOME_RECENT_DAYS = 7
FEED_DIGESTS = 10


def e(text: object) -> str:
    return escape(str(text), quote=True)


def href(url: str) -> str:
    """Only http(s) links are rendered; anything else collected from the web becomes inert."""
    return e(url) if url.startswith(("https://", "http://")) else "#"


def long_date(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.year}년 {day.month}월 {day.day}일 ({WEEKDAYS[day.weekday()]})"


def source_line(item: dict) -> str:
    signals = item.get("signals", {})
    parts = []
    for source in item["sources"]:
        label = SOURCE_LABELS.get(source, source)
        if source == "hackernews" and signals.get("hn_points"):
            label += f" {signals['hn_points']}pts"
        if source == "hf_daily" and signals.get("hf_upvotes"):
            label += f" ▲{signals['hf_upvotes']}"
        parts.append(label)
    if signals.get("github_stars"):
        parts.append(f"GitHub ★{signals['github_stars']:,}")
    if item.get("published"):
        day = date.fromisoformat(item["published"])
        parts.append(f"{day.month}월 {day.day}일 공개")
    return " · ".join(parts)


def render_media(item: dict) -> str:
    """The item's one picture or video, hot-linked. It removes itself when it fails to load."""
    media = item.get("media")
    if not media or not media["url"].startswith("https://"):
        return ""
    url = e(media["url"])
    gone = "this.closest('figure').remove()"
    if media["type"] == "video":
        # "#t=3" makes browsers show a frame a few seconds in (past any title card) as the poster;
        # nothing plays until clicked.
        return (
            f'<figure class="media"><video src="{url}#t=3" controls muted playsinline '
            f'preload="metadata" onerror="{gone}"></video></figure>'
        )
    return (
        f'<figure class="media"><img src="{url}" alt="" loading="lazy" referrerpolicy="no-referrer" '
        f'onerror="{gone}" onload="if(this.naturalWidth<200){gone}"></figure>'
    )


def render_item(number: int, item: dict) -> str:
    points = "".join(f"<li>{e(point)}</li>" for point in item["key_points"])
    tags = "".join(f"<span>#{e(tag)}</span>" for tag in item["tags"])
    links = "".join(
        f'<a href="{href(item["links"][key])}">{label}</a>'
        for key, label in LINK_LABELS
        if item.get("links", {}).get(key)
    )
    category = item["category"]
    return f"""
<article class="item">
  <div class="meta">
    <span class="num">{number:02d}</span>
    <span class="cat cat-{e(category.lower())}">{e(category)}</span>
    <span class="src">{e(source_line(item))}</span>
  </div>
  <h2><a href="{href(item["url"])}">{e(item["title"])}</a></h2>
  <p class="headline">{e(item["headline"])}</p>
  {render_media(item)}
  <p class="tldr"><b>TL;DR</b> {e(item["tldr"])}</p>
  <ul class="points">{points}</ul>
  <p class="eff"><b>효율 포인트</b> {e(item["efficiency"])}</p>
  <div class="foot"><div class="tags">{tags}</div><div class="links">{links}</div></div>
</article>"""


def page(title: str, body: str, root: str, description: str = "") -> str:
    """Wrap a body in the shared layout. `root` is the relative path back to the site root."""
    feed = (
        f'<link rel="alternate" type="application/rss+xml" title="{e(config.SITE_TITLE)}" '
        f'href="{root}feed.xml">'
        if config.SITE_URL
        else ""
    )
    rss_nav = f'<a href="{root}feed.xml">RSS</a>' if config.SITE_URL else ""
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    source = f' · <a href="https://github.com/{e(repository)}">source</a>' if repository else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description or config.SITE_TAGLINE)}">
<link rel="stylesheet" href="{root}assets/style.css">
{feed}
</head>
<body>
<header class="site">
  <a class="brand" href="{root}">{e(config.SITE_TITLE)}</a>
  <nav><a href="{root}">최신</a><a href="{root}archive/">아카이브</a>{rss_nav}</nav>
</header>
<main>
{body}
</main>
<footer class="site">
  Hacker News · Hugging Face Daily Papers · arXiv에서 수집한 후보를 Claude가 선별·요약합니다.
  자동 생성된 요약이므로 정확한 내용은 원문을 확인하세요.{source}
</footer>
</body>
</html>
"""


def render_digest(digest: dict, newer: dict | None, older: dict | None, root: str) -> str:
    items = "".join(render_item(n, item) for n, item in enumerate(digest["items"], 1))
    previous = f'<a href="{root}{older["date"]}/">← {older["date"]}</a>' if older else "<span></span>"
    following = f'<a href="{root}{newer["date"]}/">{newer["date"]} →</a>' if newer else "<span></span>"
    return f"""<div class="day">
  <p class="tagline">{e(config.SITE_TAGLINE)}</p>
  <h1>{long_date(digest["date"])}</h1>
</div>
{items}
<nav class="pager">{previous}{following}</nav>"""


def render_day_list(digests: list[dict], root: str) -> str:
    rows = []
    for digest in digests:
        titles = "".join(
            f'<li><span class="cat cat-{e(item["category"].lower())}">{e(item["category"])}</span>'
            f"{e(item['headline'])}</li>"
            for item in digest["items"]
        )
        rows.append(
            f'<section class="past"><h3><a href="{root}{digest["date"]}/">'
            f"{long_date(digest['date'])}</a></h3><ul>{titles}</ul></section>"
        )
    return "".join(rows)


def render_calendar(year: int, month: int, digest_dates: set[str], root: str) -> str:
    """A month grid (Monday first) in which every day that has a digest links to it."""
    cells = "".join(f'<span class="dow">{name}</span>' for name in WEEKDAYS)
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        for day in week:
            iso = f"{year:04d}-{month:02d}-{day:02d}"
            if day == 0:
                cells += "<span></span>"
            elif iso in digest_dates:
                cells += f'<a href="{root}{iso}/" title="{long_date(iso)}">{day}</a>'
            else:
                cells += f'<span class="empty">{day}</span>'
    return f'<div class="calendar">{cells}</div>'


def render_feed(digests: list[dict]) -> str:
    entries = []
    for digest in digests[:FEED_DIGESTS]:
        published = format_datetime(datetime.fromisoformat(digest["generated_at"]))
        for item in digest["items"]:
            description = f"{item['headline']}\n\n{item['tldr']}\n\n{item['efficiency']}"
            entries.append(
                f"<item><title>{e('[' + item['category'] + '] ' + item['title'])}</title>"
                f"<link>{href(item['url'])}</link>"
                f'<guid isPermaLink="false">{e(digest["date"] + "/" + item["id"])}</guid>'
                f"<pubDate>{published}</pubDate>"
                f"<description>{e(description)}</description></item>"
            )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{e(config.SITE_TITLE)}</title><link>{e(config.SITE_URL)}/</link>"
        f"<description>{e(config.SITE_TAGLINE)}</description><language>ko</language>"
        f"{''.join(entries)}</channel></rss>\n"
    )


def write(relative_path: str, content: str) -> None:
    path = config.SITE_DIR / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build() -> int:
    digests = [digest for digest in load_digests() if digest["items"]]
    if config.SITE_DIR.exists():
        shutil.rmtree(config.SITE_DIR)
    shutil.copytree(ASSETS, config.SITE_DIR / "assets")

    if not digests:
        body = '<div class="day"><h1>아직 다이제스트가 없습니다</h1><p>첫 실행을 기다리는 중입니다.</p></div>'
        write("index.html", page(config.SITE_TITLE, body, root="./"))
        write("archive/index.html", page(f"아카이브 · {config.SITE_TITLE}", body, root="../"))
        return 0

    for index, digest in enumerate(digests):  # newest first
        newer = digests[index - 1] if index > 0 else None
        older = digests[index + 1] if index + 1 < len(digests) else None
        title = f"{digest['date']} · {config.SITE_TITLE}"
        description = " / ".join(item["headline"] for item in digest["items"])
        write(
            f"{digest['date']}/index.html",
            page(title, render_digest(digest, newer, older, "../"), "../", description),
        )

    latest = digests[0]
    older = digests[1] if len(digests) > 1 else None
    home = render_digest(latest, None, older, "./")
    recent = digests[1 : 1 + HOME_RECENT_DAYS]
    if recent:
        home += f'<h2 class="section">지난 다이제스트</h2>{render_day_list(recent, "./")}'
    write("index.html", page(config.SITE_TITLE, home, root="./"))

    archive = (
        '<div class="day"><p class="tagline">날짜를 누르면 그날 정리한 내용을 볼 수 있습니다.</p>'
        "<h1>아카이브</h1></div>"
    )
    digest_dates = {digest["date"] for digest in digests}
    for month, group in groupby(digests, key=lambda digest: digest["date"][:7]):
        year, month_number = (int(part) for part in month.split("-"))
        archive += f'<h2 class="section">{year}년 {month_number}월</h2>'
        archive += render_calendar(year, month_number, digest_dates, "../")
        archive += render_day_list(list(group), "../")
    write("archive/index.html", page(f"아카이브 · {config.SITE_TITLE}", archive, root="../"))

    if config.SITE_URL:
        write("feed.xml", render_feed(digests))
    print(f"built {len(digests)} digest page(s) in {config.SITE_DIR.relative_to(config.ROOT)}/")
    return len(digests)


if __name__ == "__main__":
    build()
