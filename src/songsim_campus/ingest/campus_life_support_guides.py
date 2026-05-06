from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote, urljoin

import httpx
from bs4 import BeautifulSoup

WHITESPACE_PATTERN = re.compile(r"\s+")


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


def _collect_text_lines(root, *, skip_exact: set[str] | None = None) -> list[str]:
    skip_exact = skip_exact or set()
    text = root.get_text("\n", strip=True)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _clean_text(raw_line)
        if not line:
            continue
        if line in skip_exact:
            continue
        if line.startswith("Image:"):
            continue
        lines.append(line)
    return lines


def _pair_label_value_lines(lines: list[str]) -> list[str]:
    paired: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.rstrip(":").strip()
        if line.endswith(":") and index + 1 < len(lines):
            value = lines[index + 1]
            if value and not value.endswith(":"):
                paired.append(f"{stripped}: {value}")
                index += 2
                continue
        paired.append(line)
        index += 1
    return _unique(paired)


def _extract_links(
    root,
    *,
    base_url: str,
    skip_fragment_links: bool = False,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for anchor in root.select("a[href]"):
        label = _clean_text(anchor.get_text(" ", strip=True))
        href = unquote(unescape(str(anchor.get("href") or "")).strip())
        if not label or not href or href.startswith("javascript:"):
            continue
        if skip_fragment_links and href.startswith("#"):
            continue
        items.append({"label": label, "url": urljoin(base_url, href)})
    return _dedupe_link_items(items)


def _dedupe_link_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in items:
        key = (item["label"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _extract_table_rows(table) -> list[str]:
    rows: list[str] = []
    header_cells = [
        _clean_text(cell.get_text(" ", strip=True))
        for cell in table.select_one("thead tr").find_all(["th", "td"], recursive=False)
    ] if table.select_one("thead tr") else []

    for tr in table.select("tbody tr"):
        cells = [
            _clean_text(cell.get_text(" ", strip=True))
            for cell in tr.find_all(["th", "td"], recursive=False)
        ]
        if not cells:
            continue
        if header_cells and len(header_cells) == len(cells):
            parts = [
                f"{header}: {cell}"
                for header, cell in zip(header_cells, cells, strict=False)
                if header and cell
            ]
            if parts:
                rows.append(" / ".join(parts))
                continue
        rows.append(" / ".join(cell for cell in cells if cell))
    return _unique(rows)


def _extract_section_steps(
    section,
    *,
    title: str | None = None,
    extra_skip: set[str] | None = None,
) -> list[str]:
    skip_exact = set(extra_skip or set())
    if title:
        skip_exact.add(title)
    lines = _collect_text_lines(section, skip_exact=skip_exact)
    steps = _pair_label_value_lines(lines)
    for table in section.select("table"):
        steps.extend(_extract_table_rows(table))
    return _unique(steps)


def _find_con_box_by_h4_title(root, title: str):
    target = _clean_text(title)
    for section in root.find_all("div", class_="con-box", recursive=False):
        heading = section.select_one(".h4-tit01")
        if heading and _clean_text(heading.get_text(" ", strip=True)) == target:
            return section
    return None


def _extract_hospital_links(root, *, base_url: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for anchor in root.select("a[href]"):
        label = _clean_text(anchor.get_text(" ", strip=True))
        href = unquote(unescape(str(anchor.get("href") or "")).strip())
        if not label or not href:
            continue
        if not re.search(r"/hospital[2-9]\.do$", href):
            continue
        items.append({"label": label, "url": urljoin(base_url, href)})
    return _dedupe_link_items(items)


class CampusLifeSupportGuideSourceBase:
    source_tag = "cuk_campus_life_support_guides"
    topic = ""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text


class StudentCounselingGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "student_counseling"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/counsel.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box") or soup
        rows: list[dict] = []
        for thumb in root.select(".thumb-box"):
            title_node = thumb.select_one(".box-tit")
            title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
            if not title:
                continue
            steps = _extract_section_steps(thumb, title=title, extra_skip={"홈페이지 바로가기"})
            rows.append(
                {
                    "topic": self.topic,
                    "title": title,
                    "summary": steps[0] if steps else title,
                    "steps": steps,
                    "links": _extract_links(thumb, base_url=self.url),
                    "source_url": self.url,
                    "source_tag": self.source_tag,
                    "last_synced_at": fetched_at,
                }
            )
        return rows


class CareerCounselingGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "career_counseling"

    def __init__(
        self,
        url: str = "https://career.catholic.ac.kr/career/job/job_counseling.do",
    ):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one("#cms-content") or soup.select_one(".content-box") or soup
        title_node = root.select_one("h3") or soup.select_one("title")
        title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "") or (
            "진로/취업 상담"
        )
        if "|" in title:
            title = _clean_text(title.split("|", 1)[0])

        steps: list[str] = []
        for section in root.find_all("div", class_="con-box", recursive=False) or [root]:
            section_title_node = (
                section.select_one(".h4-tit02")
                or section.select_one(".h4-tit01")
                or section.select_one(".box-tit")
            )
            section_title = _clean_text(
                section_title_node.get_text(" ", strip=True) if section_title_node else ""
            )
            if section_title:
                steps.append(section_title)
            if section_title == "상담 신청 방법":
                application_step = _clean_text(section.get_text(" ", strip=True))
                application_step = application_step.removeprefix(section_title).strip()
                application_step = application_step.replace("( ", "(").replace(" )", ")")
                if application_step:
                    steps.append(application_step)
                continue
            steps.extend(_extract_section_steps(section, title=section_title or None))

        steps = _unique(steps)
        summary = next(
            (step for step in steps if "가톨릭대학교 학부생 및 졸업생" in step),
            next(
                (step for step in steps if "1:1 개인별 맞춤 상담" in step),
                steps[0] if steps else title,
            ),
        )
        return [
            {
                "topic": self.topic,
                "title": title,
                "summary": summary,
                "steps": steps,
                "links": _extract_links(root, base_url=self.url),
                "source_url": self.url,
                "source_tag": self.source_tag,
                "last_synced_at": fetched_at,
            }
        ]


class DisabilitySupportGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "disability_support"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/disability_service.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box") or soup
        rows: list[dict] = []
        title = "장애학생지원센터"
        steps: list[str] = []
        links: list[dict[str, str]] = []
        for index, box in enumerate(root.find_all("div", class_="con-box", recursive=False)):
            section_title_node = box.select_one(".h4-tit01") or box.select_one(".box-tit")
            section_title = _clean_text(
                section_title_node.get_text(" ", strip=True) if section_title_node else ""
            )
            if not section_title:
                continue
            if index == 0:
                title = section_title
                links = _extract_links(box, base_url=self.url)
            elif section_title != title:
                steps.append(section_title)
            steps.extend(
                _extract_section_steps(
                    box,
                    title=section_title,
                    extra_skip={"홈페이지 바로가기"},
                )
            )
        steps = _unique(steps)
        summary = next(
            (step for step in steps if step.startswith("장애학생지원센터에서는")),
            steps[0] if steps else title,
        )
        rows.append(
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
        )
        return rows


class StudentReservistGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "student_reservist"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/student_reservist.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box") or soup
        rows: list[dict] = []
        title = "직장예비군 가톨릭대학교 대대"
        steps: list[str] = []
        links: list[dict[str, str]] = []
        for index, box in enumerate(root.find_all("div", class_="con-box", recursive=False)):
            section_title_node = box.select_one(".h4-tit01") or box.select_one(".box-tit")
            section_title = _clean_text(
                section_title_node.get_text(" ", strip=True) if section_title_node else ""
            )
            if not section_title:
                continue
            if index == 0:
                title = section_title
                links = _extract_links(box, base_url=self.url)
            elif section_title != title:
                steps.append(section_title)
            steps.extend(
                _extract_section_steps(
                    box,
                    title=section_title,
                    extra_skip={"예비군대대 홈페이지 바로가기", "홈페이지 바로가기"},
                )
            )
        steps = _unique(steps)
        rows.append(
            {
                "topic": self.topic,
                "title": "직장예비군 가톨릭대학교 대대",
                "summary": title,
                "steps": steps,
                "links": links,
                "source_url": self.url,
                "source_tag": self.source_tag,
                "last_synced_at": fetched_at,
            }
        )
        return rows


class HospitalUseGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "hospital_use"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/hospital1.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box") or soup
        thumb = root.select_one(".thumb-box") or root
        steps = _extract_section_steps(
            thumb,
            title="가톨릭중앙의료원",
            extra_skip={"병원아이콘", "홈페이지 바로가기"},
        )
        steps = [
            step.replace("병원아이콘 ", "", 1) if step.startswith("병원아이콘 ") else step
            for step in steps
        ]
        rows = [
            {
                "topic": self.topic,
                "title": "부속병원이용",
                "summary": steps[0] if steps else "부속병원이용",
                "steps": steps,
                "links": _extract_hospital_links(root, base_url=self.url),
                "source_url": self.url,
                "source_tag": self.source_tag,
                "last_synced_at": fetched_at,
            }
        ]
        return rows


class HealthCenterGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "health_center"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/health.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = (
            soup.select_one(".content-box.conv.health")
            or soup.select_one(".content-box")
            or soup
        )
        sections = root.find_all("div", class_="con-box", recursive=False) or [root]

        steps: list[str] = []
        links: list[dict[str, str]] = []
        title = "보건실"

        for index, section in enumerate(sections):
            section_title_node = section.select_one(".box-tit") or section.select_one(".h4-tit01")
            section_title = _clean_text(
                section_title_node.get_text(" ", strip=True) if section_title_node else ""
            )
            if index == 0 and section_title:
                title = section_title
            section_steps = _extract_section_steps(section, title=section_title or None)
            if section_title and section_title != title:
                steps.append(section_title)
            steps.extend(section_steps)
            links.extend(_extract_links(section, base_url=self.url))

        steps = _unique(steps)
        summary = next(
            (step for step in steps if "학생과 교직원의 건강" in step),
            steps[0] if steps else title,
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


class LostFoundGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "lost_found"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/find.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = (
            soup.select_one(".sub-content.cms-sub-content .border-box.mg-b40")
            or soup.select_one(".border-box.mg-b40")
            or soup
        )
        title = "유실물 찾기"
        steps = _extract_section_steps(root, title=title, extra_skip={"NOTICE"})
        summary = steps[0] if steps else title
        return [
            {
                "topic": self.topic,
                "title": title,
                "summary": summary,
                "steps": steps,
                "links": _extract_links(root, base_url=self.url),
                "source_url": self.url,
                "source_tag": self.source_tag,
                "last_synced_at": fetched_at,
            }
        ]


class ParkingGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "parking"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/about/location_songsim.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box") or soup
        section = _find_con_box_by_h4_title(root, "주차요금안내") or root

        steps: list[str] = []
        title = "주차요금안내"

        section_title_node = section.select_one(".h4-tit01") or section.select_one(".box-tit")
        section_title = _clean_text(
            section_title_node.get_text(" ", strip=True) if section_title_node else ""
        )
        if section_title:
            title = section_title

        for sub_section in section.select(".con-box02"):
            sub_title_node = (
                sub_section.select_one(".h5-tit01")
                or sub_section.select_one(".h6-tit01")
                or sub_section.select_one(".box-tit")
            )
            sub_title = _clean_text(
                sub_title_node.get_text(" ", strip=True) if sub_title_node else ""
            )
            section_steps = _extract_section_steps(
                sub_section,
                title=sub_title or None,
            )
            if sub_title:
                steps.append(sub_title)
            steps.extend(section_steps)

        for alert in section.select(".alert-txt"):
            steps.append(_clean_text(alert.get_text(" ", strip=True)))

        steps = _unique(steps)
        summary = next(
            (step for step in steps if "교직원, 학생(학부, 대학원생)" in step),
            steps[0] if steps else title,
        )
        return [
            {
                "topic": self.topic,
                "title": title,
                "summary": summary,
                "steps": steps,
                "links": _extract_links(section, base_url=self.url),
                "source_url": self.url,
                "source_tag": self.source_tag,
                "last_synced_at": fetched_at,
            }
        ]


class MobilitySafetyGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "mobility_safety"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/service/safety.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content") or soup.select_one(".content-box") or soup
        sections = root.find_all("div", class_="con-box", recursive=False)

        title = "개인형 이동장치 안전관리교육"
        steps: list[str] = []
        links: list[dict[str, str]] = []

        def add_link(label: str, url: str) -> None:
            item = {"label": label, "url": url}
            if item not in links:
                links.append(item)

        if sections:
            education_section = sections[0]
            education_title_node = (
                education_section.select_one(".h4-tit01")
                or education_section.select_one(".box-tit")
            )
            education_title = _clean_text(
                education_title_node.get_text(" ", strip=True) if education_title_node else ""
            )
            if education_title:
                title = education_title
            steps.extend(
                _extract_section_steps(
                    education_section,
                    title=education_title or None,
                    extra_skip={"개인형 이동장치 안전관리 교육영상 시청하기"},
                )
            )
            for link in _extract_links(education_section, base_url=self.url):
                if "교육영상" in link["label"]:
                    add_link("교육영상", link["url"])

        if len(sections) > 1:
            rules_section = sections[1]
            rules_title_node = rules_section.select_one(".h4-tit01") or rules_section.select_one(
                ".box-tit"
            )
            rules_title = _clean_text(
                rules_title_node.get_text(" ", strip=True) if rules_title_node else ""
            )
            steps.extend(
                _extract_section_steps(
                    rules_section,
                    title=rules_title or None,
                )
            )

        if len(sections) > 2:
            regulation_section = sections[2]
            regulation_title_node = (
                regulation_section.select_one(".h4-tit01")
                or regulation_section.select_one(".box-tit")
            )
            regulation_title = _clean_text(
                regulation_title_node.get_text(" ", strip=True) if regulation_title_node else ""
            )
            steps.extend(
                _extract_section_steps(
                    regulation_section,
                    title=regulation_title or None,
                    extra_skip={"「가톨릭대학교 개인형 이동장치 안전관리 규정」 바로가기"},
                )
            )
            for link in _extract_links(regulation_section, base_url=self.url):
                if "규정" in link["label"] or "바로가기" in link["label"]:
                    add_link("규정 바로가기", link["url"])

        steps = _unique(steps)
        summary = steps[0] if steps else title
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


class FacilityRentalGuideSource(CampusLifeSupportGuideSourceBase):
    topic = "facility_rental"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/rent_songsim.do"):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box.rt_sim") or soup.select_one(".content-box") or soup

        rows: list[dict[str, object]] = []
        row_index_by_title: dict[str, int] = {}

        for border_box in root.select(".box-wrap.card.col3 .border-box"):
            title_node = border_box.select_one(".box-tit")
            title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
            if not title:
                continue

            steps: list[str] = []
            for dl in border_box.select(".dl-box dl"):
                dt_node = dl.find("dt")
                dd_node = dl.find("dd")
                dt = _clean_text(dt_node.get_text(" ", strip=True) if dt_node else "")
                dd = _clean_text(dd_node.get_text(" ", strip=True) if dd_node else "")
                if dt and dd:
                    steps.append(f"{dt}: {dd}")
            for alert in border_box.select(".alert-txt"):
                alert_text = _clean_text(alert.get_text(" ", strip=True))
                if alert_text:
                    steps.append(alert_text)

            links = _extract_links(
                border_box,
                base_url=self.url,
                skip_fragment_links=True,
            )
            if title in row_index_by_title:
                row = rows[row_index_by_title[title]]
                row["steps"] = _unique([*(row["steps"] or []), *steps])  # type: ignore[index]
                row["links"] = _dedupe_link_items([*(row["links"] or []), *links])  # type: ignore[index]
                continue

            row_index_by_title[title] = len(rows)
            rows.append(
                {
                    "topic": self.topic,
                    "title": title,
                    "summary": steps[0] if steps else title,
                    "steps": _unique(steps),
                    "links": links,
                    "source_url": self.url,
                    "source_tag": self.source_tag,
                    "last_synced_at": fetched_at,
                }
            )

        rental_section = (
            root.select_one(".con-box.no-pd")
            or root.select_one(".con-box:last-of-type")
            or root
        )
        rental_title_node = rental_section.select_one(".h4-tit01")
        rental_title = _clean_text(
            rental_title_node.get_text(" ", strip=True) if rental_title_node else ""
        ) or "강의실 대관료"
        rental_steps = _collect_text_lines(
            rental_section,
            skip_exact={rental_title},
        )
        rental_steps.extend(_extract_table_rows(rental_section.select_one("table")))
        rental_steps = _unique(rental_steps)
        rows.append(
            {
                "topic": self.topic,
                "title": rental_title,
                "summary": rental_steps[0] if rental_steps else rental_title,
                "steps": rental_steps,
                "links": _extract_links(
                    rental_section,
                    base_url=self.url,
                    skip_fragment_links=True,
                ),
                "source_url": self.url,
                "source_tag": self.source_tag,
                "last_synced_at": fetched_at,
            }
        )
        return rows
