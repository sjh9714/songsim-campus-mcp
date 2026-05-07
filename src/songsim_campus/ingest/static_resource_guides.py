from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote, urljoin

import httpx
from bs4 import BeautifulSoup

WHITESPACE_PATTERN = re.compile(r"\s+")
IGNORED_LINES = {
    "QUICK MENU",
    "콘텐츠 담당부서",
    "맨위로가기",
    "프린트",
    "공유",
}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = clean_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def dedupe_links(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in items:
        key = (item["label"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def extract_links(root, *, base_url: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for anchor in root.select("a[href]"):
        label = clean_text(anchor.get_text(" ", strip=True))
        href = unquote(unescape(str(anchor.get("href") or "")).strip())
        if not label or not href or href.startswith("javascript:") or href.startswith("#"):
            continue
        items.append({"label": label, "url": urljoin(base_url, href)})
    return dedupe_links(items)


def extract_steps(root, *, title: str) -> list[str]:
    clone = BeautifulSoup(str(root), "html.parser")
    for node in clone.select("a, img, script, style, noscript, .link-box, .img-box"):
        node.decompose()

    lines: list[str] = []
    for raw_line in clone.get_text("\n", strip=True).splitlines():
        line = clean_text(raw_line)
        if not line or line == title or line in IGNORED_LINES:
            continue
        if line.startswith("Image:"):
            continue
        lines.append(line)
    return unique(lines)


def resolve_title(soup: BeautifulSoup, *, default_title: str) -> str:
    for selector in (
        ".page-title h3",
        ".sub-title h3",
        ".content-title",
        ".h3-tit",
        "h3",
        "h2",
        "title",
    ):
        node = soup.select_one(selector)
        title = clean_text(node.get_text(" ", strip=True) if node else "")
        if title:
            return title
    return default_title


def resolve_root(soup: BeautifulSoup):
    return (
        soup.select_one("#cms-content")
        or soup.select_one(".content-box")
        or soup.select_one("#contents")
        or soup.select_one("main")
        or soup
    )


class StaticResourceGuideSourceBase:
    source_tag = ""
    topic = ""
    default_title = ""
    default_summary = ""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = resolve_root(soup)
        title = resolve_title(soup, default_title=self.default_title)
        steps = extract_steps(root, title=title)
        summary = self.default_summary or (
            steps[0]
            if steps
            else f"공식 페이지에서 {title} 관련 자료와 링크를 확인할 수 있습니다."
        )
        return [
            {
                "topic": self.topic,
                "title": title,
                "summary": summary,
                "steps": steps,
                "links": extract_links(root, base_url=self.url),
                "source_url": self.url,
                "source_tag": self.source_tag,
                "last_synced_at": fetched_at,
            }
        ]
