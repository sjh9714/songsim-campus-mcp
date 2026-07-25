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


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = _clean_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _dedupe_links(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in items:
        key = (item["label"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _extract_links(root, *, base_url: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for anchor in root.select("a[href]"):
        label = _clean_text(anchor.get_text(" ", strip=True))
        href = unquote(unescape(str(anchor.get("href") or "")).strip())
        if not label or not href or href.startswith("javascript:") or href.startswith("#"):
            continue
        items.append({"label": label, "url": urljoin(base_url, href)})
    return _dedupe_links(items)


def _extract_steps(root, *, title: str) -> list[str]:
    clone = BeautifulSoup(str(root), "html.parser")
    for node in clone.select("a, img, script, style, noscript, .link-box, .img-box"):
        node.decompose()

    lines: list[str] = []
    for raw_line in clone.get_text("\n", strip=True).splitlines():
        line = _clean_text(raw_line)
        if not line or line == title or line in IGNORED_LINES:
            continue
        if line.startswith("Image:"):
            continue
        lines.append(line)
    return _unique(lines)


def _resolve_title(soup: BeautifulSoup, *, default_title: str) -> str:
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
        title = _clean_text(node.get_text(" ", strip=True) if node else "")
        if title:
            return title
    return default_title


def _resolve_root(soup: BeautifulSoup):
    return (
        soup.select_one("#cms-content")
        or soup.select_one(".content-box")
        or soup.select_one("#contents")
        or soup.select_one("main")
        or soup
    )


class ServicePolicyGuideSourceBase:
    source_tag = "cuk_service_policy_guides"
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
        title = _resolve_title(soup, default_title=self.default_title)
        root = _resolve_root(soup)
        steps = _extract_steps(root, title=title)
        links = _extract_links(root, base_url=self.url)
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
                "links": links,
                "source_url": self.url,
                "source_tag": self.source_tag,
                "last_synced_at": fetched_at,
            }
        ]


class BiddingGuideSource(ServicePolicyGuideSourceBase):
    topic = "bidding"
    default_title = "입찰공고"
    default_summary = "가톨릭대학교 공식 입찰공고 게시판에서 최신 입찰 안내를 확인합니다."

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/service/Bidding.do"):
        super().__init__(url)


class JobPostingGuideSource(ServicePolicyGuideSourceBase):
    topic = "job_posting"
    default_title = "채용공고"
    default_summary = "가톨릭대학교 공식 채용공고 게시판에서 최신 채용 안내를 확인합니다."

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/service/Job-posting.do"):
        super().__init__(url)


class PrivacyPolicyGuideSource(ServicePolicyGuideSourceBase):
    topic = "privacy_policy"
    default_title = "개인정보처리방침"
    default_summary = "가톨릭대학교 개인정보처리방침의 공개 적용본과 열람 안내를 제공합니다."

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/service/privacy.do"):
        super().__init__(url)


class CctvPolicyGuideSource(ServicePolicyGuideSourceBase):
    topic = "cctv_policy"
    default_title = "영상정보처리기기 운영 및 관리 방침"
    default_summary = "영상정보처리기기 운영 및 관리 방침의 공개 적용본과 문의 안내를 제공합니다."

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/service/notice_cctv_regulation.do",
    ):
        super().__init__(url)


class AntiGraftGuideSource(ServicePolicyGuideSourceBase):
    topic = "anti_graft"
    default_title = "청탁금지법 안내"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/service/anti_graft_law1.do",
    ):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        rows = super().parse(html, fetched_at=fetched_at)
        rows[0]["title"] = "청탁금지법 안내"
        rows[0]["summary"] = (
            "청탁금지법 주요내용, 적용대상, 교육자료, 문의처를 공식 페이지에서 확인합니다."
        )
        rows[0]["links"] = [
            {
                "label": "청탁금지법 주요내용",
                "url": "https://www.catholic.ac.kr/ko/service/anti_graft_law1.do",
            },
            {
                "label": "청탁금지법 법적용대상",
                "url": "https://www.catholic.ac.kr/ko/service/anti_graft_law2.do",
            },
            {
                "label": "청탁금지법 교육/설명자료",
                "url": "https://www.catholic.ac.kr/ko/service/anti_graft_law3.do",
            },
            {
                "label": "청탁방지담당관 및 관련문의",
                "url": "https://www.catholic.ac.kr/ko/service/anti_graft_law4.do",
            },
        ]
        return rows
