from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

WHITESPACE_PATTERN = re.compile(r"\s+")


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def _clean_board_title(value: str | None) -> str:
    text = _clean_text(value)
    return re.sub(r"\s*바로가기$", "", text).strip()


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


def _detail_source_url(base_url: str, article_no: str, *, limit: int = 16) -> str:
    return f"{base_url}?mode=view&articleNo={article_no}&article.offset=0&articleLimit={limit}"


class NewsroomPostSourceBase:
    source_tag = "cuk_newsroom_posts"
    topic = ""
    default_category = ""
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
        return {
            "title": title or default_title,
            "published_at": published_at or default_published_at,
            "summary": body_text[:220].strip() or default_summary,
        }

    def _base_row(
        self,
        *,
        article_no: str,
        title: str,
        published_at: str | None,
        source_url: str | None = None,
        summary: str = "",
        thumbnail_url: str | None = None,
        external_url: str | None = None,
    ) -> dict[str, str | None]:
        return {
            "topic": self.topic,
            "article_no": article_no,
            "title": title,
            "published_at": published_at,
            "summary": summary,
            "thumbnail_url": thumbnail_url,
            "external_url": external_url,
            "source_url": source_url or _detail_source_url(self.url, article_no),
            "source_tag": self.source_tag,
        }


class PhotoNewsSource(NewsroomPostSourceBase):
    topic = "photo_news"
    default_category = "포토뉴스"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/newsroom/photonews.do"):
        super().__init__(url)

    def parse_list(self, html: str) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict[str, str | None]] = []
        for item in soup.select("li.b-img-con-box"):
            anchor = item.select_one("a[href*='articleNo=']")
            if anchor is None:
                continue
            article_no = _extract_article_no(anchor.get("href"))
            title_node = item.select_one(".b-img-title") or item.select_one(".b-title")
            if title_node is not None:
                for category_node in title_node.select(".b-cate"):
                    category_node.decompose()
            title = _clean_board_title(
                title_node.get_text(" ", strip=True)
                if title_node
                else str(anchor.get("title") or anchor.get_text(" ", strip=True))
            )
            date_node = item.select_one(".b-date")
            image_node = item.select_one("img[src]")
            thumbnail_url = (
                urljoin(self.url, unescape(str(image_node.get("src"))))
                if image_node is not None
                else None
            )
            if not article_no or not title:
                continue
            rows.append(
                self._base_row(
                    article_no=article_no,
                    title=title,
                    published_at=_normalize_date(date_node.get_text() if date_node else ""),
                    source_url=urljoin(self.url, unescape(str(anchor.get("href") or ""))),
                    thumbnail_url=thumbnail_url,
                )
            )
        return rows


class AlumniInterviewSource(PhotoNewsSource):
    topic = "alumni_interview"
    default_category = "동문 인터뷰"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/newsroom/interview.do"):
        super().__init__(url)


class PromoVideoSource(PhotoNewsSource):
    topic = "promo_video"
    default_category = "홍보영상"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/newsroom/media.do"):
        super().__init__(url)


class PressSource(NewsroomPostSourceBase):
    topic = "press"
    default_category = "보도자료"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/newsroom/press.do"):
        super().__init__(url)

    def parse_list(self, html: str) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict[str, str | None]] = []
        for item in soup.select("tbody tr"):
            anchor = item.select_one("a.b-title") or item.select_one("a[data-article-no]")
            if anchor is None:
                continue
            href = unescape(str(anchor.get("href") or ""))
            article_no = str(anchor.get("data-article-no") or "") or _extract_article_no(href)
            title = _clean_text(anchor.get_text(" ", strip=True))
            media_node = item.select_one(".b-con.b-writer")
            date_node = item.select_one(".b-con.b-date")
            external_url = (
                urljoin(self.url, href) if href.startswith(("http://", "https://")) else None
            )
            source_url = (
                _detail_source_url(self.url, article_no) if article_no else urljoin(self.url, href)
            )
            summary = _clean_text(media_node.get_text(" ", strip=True) if media_node else "")
            if not article_no or not title:
                continue
            rows.append(
                self._base_row(
                    article_no=article_no,
                    title=title,
                    published_at=_normalize_date(date_node.get_text() if date_node else ""),
                    source_url=source_url,
                    summary=summary,
                    external_url=external_url,
                )
            )
        return rows
