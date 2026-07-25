from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

WHITESPACE_PATTERN = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def clean_board_title(value: str | None) -> str:
    text = clean_text(value)
    return re.sub(r"\s*바로가기$", "", text).strip()


def extract_article_no(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"articleNo=([^&]+)", value)
    return match.group(1) if match else None


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4})[./-]\s*(\d{2})[./-]\s*(\d{2})", value)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def extract_meta_value(soup: BeautifulSoup, *, label: str) -> str | None:
    for item in soup.select(".b-etc-box li"):
        title = item.select_one(".title")
        spans = item.find_all("span")
        if not title or len(spans) < 2:
            continue
        if label in title.get_text():
            return spans[-1].get_text(strip=True)
    return None


def detail_source_url(base_url: str, article_no: str, *, limit: int = 16) -> str:
    return f"{base_url}?mode=view&articleNo={article_no}&article.offset=0&articleLimit={limit}"


class OfficialBoardPostSourceBase:
    source_tag = ""
    topic = ""
    article_limit = 16

    def __init__(self, url: str):
        self.url = url

    def fetch_list(self, *, offset: int = 0, limit: int = 16) -> str:
        response = httpx.get(
            self.url,
            params={"mode": "list", "article.offset": offset, "articleLimit": limit},
            timeout=20,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 16) -> str:
        response = httpx.get(
            self.url,
            params={
                "mode": "view",
                "articleNo": article_no,
                "article.offset": offset,
                "articleLimit": limit,
            },
            timeout=20,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    def parse_list(self, html: str) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")
        rows = self._parse_table_rows(soup)
        if rows:
            return rows
        return self._parse_list_items(soup)

    def _parse_table_rows(self, soup: BeautifulSoup) -> list[dict[str, str | None]]:
        rows: list[dict[str, str | None]] = []
        for item in soup.select("tbody tr"):
            anchor = (
                item.select_one("a.b-title")
                or item.select_one("a[data-article-no]")
                or item.select_one("a[href*='articleNo=']")
            )
            if anchor is None:
                continue
            row = self._row_from_anchor(anchor, date_text=item.get_text(" ", strip=True))
            if row:
                rows.append(row)
        return rows

    def _parse_list_items(self, soup: BeautifulSoup) -> list[dict[str, str | None]]:
        rows: list[dict[str, str | None]] = []
        for item in soup.select("li"):
            anchor = item.select_one("a[href*='articleNo=']")
            if anchor is None:
                continue
            date_node = item.select_one(".b-date")
            row = self._row_from_anchor(
                anchor,
                date_text=date_node.get_text(" ", strip=True) if date_node else item.get_text(" "),
            )
            if row:
                rows.append(row)
        return rows

    def _row_from_anchor(self, anchor, *, date_text: str) -> dict[str, str | None] | None:
        href = unescape(str(anchor.get("href") or ""))
        article_no = str(anchor.get("data-article-no") or "") or extract_article_no(href)
        title_node = anchor.select_one(".b-title, .b-img-title")
        title = clean_board_title(
            title_node.get_text(" ", strip=True)
            if title_node is not None
            else str(anchor.get("title") or anchor.get_text(" ", strip=True))
        )
        if not article_no or not title:
            return None
        return {
            "topic": self.topic,
            "article_no": article_no,
            "title": title,
            "published_at": normalize_date(date_text),
            "source_url": (
                urljoin(self.url, href) if href else detail_source_url(self.url, article_no)
            ),
            "source_tag": self.source_tag,
        }

    def parse_detail(
        self,
        html: str,
        *,
        default_title: str = "",
        default_summary: str = "",
        default_published_at: str | None = None,
    ) -> dict[str, str | None]:
        soup = BeautifulSoup(html, "html.parser")
        title_node = soup.select_one(".b-title-box .b-title") or soup.select_one("h3")
        title = clean_text(title_node.get_text(" ", strip=True) if title_node else default_title)
        published_at = normalize_date(extract_meta_value(soup, label="등록일"))
        body_root = (
            soup.select_one(".b-content-box .b-con-box")
            or soup.select_one(".b-content-box")
            or soup.select_one("#cms-content")
            or soup.select_one("main")
        )
        body_text = clean_text(body_root.get_text(" ", strip=True) if body_root else "")
        return {
            "title": title or default_title,
            "published_at": published_at or default_published_at,
            "summary": body_text[:220].strip() or default_summary,
            "body_text": body_text,
        }
