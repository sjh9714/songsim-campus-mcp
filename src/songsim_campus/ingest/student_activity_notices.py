from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

WHITESPACE_PATTERN = re.compile(r"\s+")

TOPIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rotc", ("rotc", "ROTC", "학생군사교육단", "학군단")),
    ("student_government", ("총학생회", "학생자치", "중앙운영위원회")),
    (
        "club_recruitment",
        ("동아리", "동아리연합회", "중앙동아리", "기관동아리", "신입부원", "동아리원"),
    ),
    ("volunteering", ("봉사단", "사회봉사", "봉사활동", "자원봉사")),
    ("campus_event", ("축제", "아우름제", "다맛제", "학생행사")),
)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def _extract_article_no(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"articleNo=([^&]+)", value)
    return match.group(1) if match else None


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4})[./-]\s*(\d{2})[./-]\s*(\d{2})", value)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _extract_meta_value(soup: BeautifulSoup, *, label: str) -> str | None:
    for item in soup.select(".b-etc-box li"):
        title = item.select_one(".title")
        spans = item.find_all("span")
        if not title or len(spans) < 2:
            continue
        if label in title.get_text():
            return spans[-1].get_text(strip=True)
    return None


class StudentActivityNoticeSource:
    source_tag = "cuk_student_activity_notices"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/notice.do"):
        self.url = url

    def fetch_list(self, *, offset: int = 0, limit: int = 10) -> str:
        response = httpx.get(
            self.url,
            params={"mode": "list", "article.offset": offset, "articleLimit": limit},
            timeout=20,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 10) -> str:
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
        rows: list[dict[str, str | None]] = []
        for item in soup.select("tbody tr"):
            anchor = item.select_one("a.b-title") or item.select_one("a[data-article-no]")
            if anchor is None:
                continue
            columns = item.find_all("td", recursive=False)
            date_text = columns[-2].get_text() if len(columns) >= 2 else ""
            href = unescape(str(anchor.get("href") or ""))
            article_no = str(anchor.get("data-article-no") or "") or _extract_article_no(href)
            title = _clean_text(anchor.get_text(" ", strip=True))
            if not article_no or not title:
                continue
            rows.append(
                {
                    "article_no": article_no,
                    "title": title,
                    "published_at": _normalize_date(date_text),
                    "source_url": urljoin(self.url, href),
                    "source_tag": self.source_tag,
                }
            )
        return rows

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
        title = _clean_text(title_node.get_text(" ", strip=True) if title_node else default_title)
        published_at = _normalize_date(_extract_meta_value(soup, label="등록일"))
        body_root = soup.select_one(".b-content-box .b-con-box") or soup.select_one("#cms-content")
        body_text = _clean_text(body_root.get_text(" ", strip=True) if body_root else "")
        summary = body_text[:220].strip() or default_summary
        return {
            "topic": self.classify_topic(title=title or default_title, body_text=body_text),
            "title": title or default_title,
            "published_at": published_at or default_published_at,
            "summary": summary,
            "body_text": body_text,
        }

    @staticmethod
    def classify_topic(*, title: str, body_text: str) -> str | None:
        haystack = f"{title} {body_text}".lower()
        for topic, keywords in TOPIC_KEYWORDS:
            if any(keyword.lower() in haystack for keyword in keywords):
                return topic
        return None
