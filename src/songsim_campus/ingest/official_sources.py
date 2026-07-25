from __future__ import annotations

import json
import re
from datetime import datetime
from html import unescape
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

PLACE_LIST_PATTERN = re.compile(r"\?mode=getPlaceListByCondition&campus=\$\{campus\}")
SCHEDULE_PATTERN = re.compile(
    r"^(?P<day>[월화수목금토일])\s*(?P<start>\d+)(?:\s*[~-]\s*(?P<end>\d+))?(?:\((?P<room>[^)]+)\))?$"
)
WHITESPACE_PATTERN = re.compile(r"\s+")
SEAT_STATUS_INTEGER_PATTERN = re.compile(r"(\d[\d,]*)")
KST = ZoneInfo("Asia/Seoul")


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(unescape(value), "html.parser").get_text(" ", strip=True)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def _compact_text(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "place"


def _split_parenthetical(value: str) -> tuple[str, list[str]]:
    matches = re.findall(r"\(([^)]+)\)", value)
    outer = re.sub(r"\([^)]*\)", "", value).strip()
    aliases = [item.strip() for item in matches if item.strip()]
    return outer, aliases


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _date_from_epoch_millis(value: int | str | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        timestamp_millis = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp_millis / 1000, tz=KST).date().isoformat()


def _academic_year_from_date_string(value: str) -> int:
    year = int(value[:4])
    month = int(value[5:7])
    return year if month >= 3 else year - 1


def _extract_table_grid(table) -> list[list[str]]:
    rows: list[list[str]] = []
    active_rowspans: list[tuple[int, str] | None] = []

    for tr in table.select("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        row: list[str] = []
        col_idx = 0
        while col_idx < len(active_rowspans) and active_rowspans[col_idx] is not None:
            remaining, value = active_rowspans[col_idx]
            row.append(value)
            remaining -= 1
            active_rowspans[col_idx] = (remaining, value) if remaining > 0 else None
            col_idx += 1
        for cell in cells:
            while col_idx < len(active_rowspans) and active_rowspans[col_idx] is not None:
                remaining, value = active_rowspans[col_idx]
                row.append(value)
                remaining -= 1
                active_rowspans[col_idx] = (remaining, value) if remaining > 0 else None
                col_idx += 1
            text = _clean_text(cell.get_text(" ", strip=True))
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))
            while len(active_rowspans) < col_idx + colspan:
                active_rowspans.append(None)
            for offset in range(colspan):
                row.append(text)
                if rowspan > 1:
                    active_rowspans[col_idx + offset] = (rowspan - 1, text)
            col_idx += colspan
        while col_idx < len(active_rowspans) and active_rowspans[col_idx] is not None:
            remaining, value = active_rowspans[col_idx]
            row.append(value)
            remaining -= 1
            active_rowspans[col_idx] = (remaining, value) if remaining > 0 else None
            col_idx += 1
        if row:
            rows.append(row)
    return rows


def _collect_dl_fields(root) -> dict[str, str]:
    fields: dict[str, str] = {}
    for dl in root.select("dl"):
        label = dl.find("dt")
        value = dl.find("dd")
        if not label or not value:
            continue
        key = _clean_text(label.get_text()).replace(":", "").strip()
        fields[key] = _clean_text(value.get_text(" ", strip=True))
    return fields


def _collect_dl_pairs(root) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for dl in root.select("dl"):
        label = dl.find("dt")
        value = dl.find("dd")
        if not label or not value:
            continue
        key = _clean_text(label.get_text()).replace(":", "").strip()
        normalized = _clean_text(value.get_text(" ", strip=True))
        if key and normalized:
            rows.append((key, normalized))
    return rows


def _normalize_note_text(value: str | None) -> str:
    return _clean_text(value).lstrip("*※ ").strip()


def _extract_table_steps(table) -> list[str]:
    grid = _extract_table_grid(table)
    if len(grid) < 2:
        return []
    headers = [_clean_text(cell) for cell in grid[0]]
    steps: list[str] = []
    for row in grid[1:]:
        normalized_row = [_clean_text(cell) for cell in row]
        nonempty = [cell for cell in normalized_row if cell]
        if not nonempty:
            continue
        unique_nonempty = _unique(nonempty)
        if len(unique_nonempty) == 1:
            note = _normalize_note_text(unique_nonempty[0])
            if note:
                steps.append(note)
            continue
        pairs: list[str] = []
        for idx, header in enumerate(headers[: len(normalized_row)]):
            value = normalized_row[idx]
            if not header or not value:
                continue
            pairs.append(f"{header}: {value}")
        if pairs:
            steps.append(" / ".join(pairs))
    return _unique(steps)


def _extract_link_items(root, *, base_url: str) -> list[dict[str, str]]:
    if root is None:
        return []
    items: list[dict[str, str]] = []
    for anchor in root.select("a[href]"):
        label = _clean_text(anchor.get_text(" ", strip=True))
        href = unescape(str(anchor.get("href") or "")).strip()
        if not label or not href:
            continue
        items.append({"label": label, "url": urljoin(base_url, href)})
    return items


def _split_csv_items(value: str | None) -> list[str]:
    if not value:
        return []
    return _unique([_clean_text(item) for item in value.split(",")])


def _flatten_transport_steps(container) -> list[str]:
    steps: list[str] = []
    for item in container.select(".ul-type-dot li"):
        detail = item.select_one(".dl_desc")
        if detail:
            dt = _clean_text(detail.select_one("dt").get_text() if detail.select_one("dt") else "")
            dd = _clean_text(detail.select_one("dd").get_text() if detail.select_one("dd") else "")
            text = " ".join(part for part in [dt, dd] if part)
        else:
            text = _clean_text(item.get_text(" ", strip=True))
        if text:
            steps.append(text)
    return steps


def _normalize_place_slug(name: str, english_name: str, place_id: int) -> str:
    english_base, english_aliases = _split_parenthetical(english_name)
    if any("library" in alias.lower() for alias in english_aliases):
        return _slugify(next(alias for alias in english_aliases if "library" in alias.lower()))
    if english_base:
        return _slugify(english_base)
    return f"place-{place_id}"


def _infer_place_category(name: str, english_name: str, description: str) -> str:
    combined = " ".join([name, english_name, description]).lower()
    if "도서관" in combined or "library" in combined:
        return "library"
    if "정문" in combined or "gate" in combined:
        return "gate"
    if "기숙사" in combined or "dormitory" in combined:
        return "dormitory"
    if "성당" in combined or "chapel" in combined:
        return "chapel"
    if "운동장" in combined or "trail" in combined or "산책로" in combined:
        return "outdoor"
    if "관" in name or "hall" in combined or "center" in combined or "센터" in combined:
        return "building"
    return "facility"


def _normalize_schedule(
    raw_schedule: str | None,
) -> tuple[str | None, int | None, int | None, str | None]:
    if not raw_schedule:
        return None, None, None, None

    normalized = WHITESPACE_PATTERN.sub("", raw_schedule)
    if "," in normalized or "/" in normalized:
        return None, None, None, None

    match = SCHEDULE_PATTERN.match(normalized)
    if not match:
        return None, None, None, None

    start = int(match.group("start"))
    end = int(match.group("end") or start)
    room = match.group("room")
    return match.group("day"), start, end, room


def classify_notice_category(title: str, body: str, board_category: str | None = None) -> str:
    normalized_board_category = _clean_text(board_category or "")
    explicit_category_map = {
        "학사": "academic",
        "장학": "scholarship",
        "취창업": "employment",
    }
    if normalized_board_category in explicit_category_map:
        return explicit_category_map[normalized_board_category]

    text = " ".join(filter(None, [title, body, normalized_board_category])).lower()
    if any(keyword in text for keyword in ["긴급", "중요", "마감", "휴강", "정전", "중단", "폐쇄"]):
        return "urgent"
    if "장학" in text:
        return "scholarship"
    if any(
        keyword in text
        for keyword in ["식당", "학식", "아침밥", "조식", "중식", "석식", "cafeteria"]
    ):
        return "cafeteria"
    if any(keyword in text for keyword in ["도서관", "library"]):
        return "library"
    if any(keyword in text for keyword in ["취업", "진로", "커리어", "자기소개서", "채용"]):
        return "employment"
    if any(keyword in text for keyword in ["행사", "특강", "설명회", "공모전", "축제", "세미나"]):
        return "event"
    if any(
        keyword in text
        for keyword in ["수강", "학사", "성적", "등록", "학기", "시험", "졸업", "강의"]
    ):
        return "academic"
    if board_category:
        return _slugify(board_category).replace("-", "_")
    return "general"


GENERIC_NOTICE_DETAIL_LABELS = {"공지"}


class CampusMapSource:
    """Official Songsim campus map source backed by the public JSON mode."""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def discover_place_list_url(self, html: str, *, campus: str = "1") -> str:
        if (
            not PLACE_LIST_PATTERN.search(html)
            and "campus-map" not in html
            and "캠퍼스 안내" not in html
        ):
            raise ValueError("Campus map page no longer exposes the place list endpoint.")
        query = urlencode({"mode": "getPlaceListByCondition", "campus": campus})
        return f"{self.url}?{query}"

    def fetch_place_list(self, *, campus: str = "1") -> str:
        response = httpx.get(self.discover_place_list_url(self.fetch(), campus=campus), timeout=20)
        response.raise_for_status()
        return response.text

    def parse_place_list(self, payload: str, *, fetched_at: str) -> list[dict]:
        data = json.loads(payload)
        rows: list[dict] = []
        seen_slugs: set[str] = set()
        for item in data.get("items", []):
            name = _clean_text(item.get("placeName"))
            english_name = _clean_text(item.get("placeNameEn"))
            description = _clean_text(item.get("description"))
            abbreviation = _clean_text(item.get("abbreviation"))
            name_base, name_aliases = _split_parenthetical(name)
            slug = _normalize_place_slug(name_base or name, english_name, int(item.get("id") or 0))
            if slug in seen_slugs:
                slug = f"{slug}-{item.get('id')}"
            seen_slugs.add(slug)
            aliases = _unique(
                ([name_base] if name_base and name_base != name else [])
                + name_aliases
                + ([abbreviation] if abbreviation else [])
            )
            latitude = item.get("latitude")
            longitude = item.get("longitude")
            rows.append(
                {
                    "slug": slug,
                    "name": name_base or name,
                    "category": _infer_place_category(name, english_name, description),
                    "aliases": aliases,
                    "description": description,
                    "latitude": latitude if latitude not in (0, 0.0, "0", None) else None,
                    "longitude": longitude if longitude not in (0, 0.0, "0", None) else None,
                    "opening_hours": {},
                    "source_tag": "cuk_campus_map",
                    "last_synced_at": fetched_at,
                }
            )
        return rows


class CourseCatalogSource:
    """Official open-course HTML parser."""

    def __init__(self, url: str):
        self.url = url

    def fetch(
        self,
        *,
        year: int,
        semester: int,
        department: str = "ALL",
        completion_type: str = "ALL",
        query: str = "",
        offset: int = 0,
    ) -> str:
        params = {
            "mode": "list",
            "sust": department,
            "pobtFg": completion_type,
            "year": year,
            "openShtm": "10" if semester == 1 else "20",
            "srSearchVal": query,
            "isEngCourses": "N",
            "alignKey": "sbjtNm",
            "article.offset": offset,
        }
        response = httpx.get(self.url, params=params, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        year = self._parse_year(soup)
        semester = self._parse_semester(soup)
        rows: list[dict] = []
        for tr in soup.select(".b-courses-offered-table tbody tr"):
            cells = tr.find_all("td", recursive=False)
            if len(cells) < 5 or "b-no-post" in cells[0].get("class", []):
                continue
            details = self._parse_detail_fields(cells[4])
            raw_schedule = details.get("시간표") or None
            day_of_week, period_start, period_end, room = _normalize_schedule(raw_schedule)
            rows.append(
                {
                    "year": year,
                    "semester": semester,
                    "code": _clean_text(cells[0].get_text()),
                    "title": _clean_text(cells[1].get_text()),
                    "professor": details.get("담당교수") or None,
                    "department": details.get("개설학과") or None,
                    "section": _clean_text(cells[3].get_text()) or None,
                    "day_of_week": day_of_week,
                    "period_start": period_start,
                    "period_end": period_end,
                    "room": room,
                    "raw_schedule": raw_schedule,
                    "source_tag": "cuk_subject_search",
                    "last_synced_at": fetched_at,
                }
            )
        return rows

    @staticmethod
    def _parse_year(soup: BeautifulSoup) -> int:
        selected = soup.select_one(
            "#year_key option[selected], select[name='year'] option[selected]"
        )
        if selected and selected.get("value", "").isdigit():
            return int(selected["value"])
        current = soup.select_one("#year_key option, select[name='year'] option")
        if current and current.get("value", "").isdigit():
            return int(current["value"])
        raise ValueError("Unable to determine course year from the page.")

    @staticmethod
    def _parse_semester(soup: BeautifulSoup) -> int:
        selected = soup.select_one(
            "#semester_key option[selected], select[name='openShtm'] option[selected]"
        )
        value = selected.get("value") if selected else None
        if value == "10":
            return 1
        if value == "20":
            return 2
        first_option = soup.select_one(
            "#semester_key option[selected], select[name='openShtm'] option"
        )
        value = first_option.get("value") if first_option else None
        if value == "10":
            return 1
        if value == "20":
            return 2
        raise ValueError("Unable to determine course semester from the page.")

    @staticmethod
    def _parse_detail_fields(cell) -> dict[str, str]:
        fields: dict[str, str] = {}
        for item in cell.select(".b-con-list li"):
            label = item.find("p")
            value = item.find("span")
            if not label or not value:
                continue
            key = label.get_text(strip=True).replace(":", "")
            fields[key] = _clean_text(value.get_text())
        return fields


class LibraryHoursSource:
    """Official central-library opening-hours parser."""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        opening_hours: dict[str, str] = {}
        for section in soup.select(".guideContent"):
            title_node = section.select_one(".guideTit1")
            title = _clean_text(title_node.get_text() if title_node else "")
            if title not in {"자료실 이용시간", "열람실 이용시간", "커뮤니티공간 이용시간"}:
                continue
            table = next(
                (
                    candidate
                    for candidate in section.select("table")
                    if candidate.select("tbody tr")
                ),
                None,
            )
            if table is None:
                continue
            grid = _extract_table_grid(table)
            for row in grid[2:]:
                if len(row) < 7:
                    continue
                name = row[0]
                if not name:
                    continue
                time_cells = row[2:6]
                if len(set(time_cells)) == 1:
                    summary = time_cells[0]
                else:
                    summary = (
                        f"학기중 평일 {row[2]} / 토요일 {row[3]} | "
                        f"방학중 평일 {row[4]} / 토요일 {row[5]}"
                    )
                note = row[6]
                if note and note not in {"-", ""}:
                    summary = f"{summary} | {note}"
                opening_hours[name] = summary
        return [
            {
                "place_name": "중앙도서관",
                "opening_hours": opening_hours,
                "source_tag": "cuk_library_hours",
                "last_synced_at": fetched_at,
            }
        ]


class LibrarySeatStatusSource:
    """Best-effort central-library reading-room seat-status parser."""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=8)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict] = []
        seen_rooms: set[str] = set()

        for table in soup.select("table"):
            grid = _extract_table_grid(table)
            if not grid:
                continue
            header_map = self._detect_header_map(grid)
            if header_map is None:
                continue
            header_row_index = int(header_map["_row_index"])
            room_index = int(header_map["room_name"])
            remaining_index = header_map.get("remaining_seats")
            occupied_index = header_map.get("occupied_seats")
            total_index = header_map.get("total_seats")

            for row in grid[header_row_index + 1 :]:
                if len(row) <= room_index:
                    continue
                room_name = _clean_text(row[room_index])
                if not room_name or room_name in seen_rooms or "합계" in room_name:
                    continue
                remaining_seats = self._parse_int_cell(row, remaining_index)
                occupied_seats = self._parse_int_cell(row, occupied_index)
                total_seats = self._parse_int_cell(row, total_index)
                if (
                    remaining_seats is None
                    and occupied_seats is None
                    and total_seats is None
                ):
                    continue
                rows.append(
                    {
                        "room_name": room_name,
                        "remaining_seats": remaining_seats,
                        "occupied_seats": occupied_seats,
                        "total_seats": total_seats,
                        "source_url": self.url,
                        "source_tag": "cuk_library_seat_status",
                        "last_synced_at": fetched_at,
                    }
                )
                seen_rooms.add(room_name)
        return rows

    @staticmethod
    def _parse_int_cell(row: list[str], index: int | None) -> int | None:
        if index is None or index >= len(row):
            return None
        match = SEAT_STATUS_INTEGER_PATTERN.search(row[index] or "")
        if match is None:
            return None
        return int(match.group(1).replace(",", ""))

    @staticmethod
    def _detect_header_map(grid: list[list[str]]) -> dict[str, int] | None:
        for row_index, row in enumerate(grid[:5]):
            normalized = [_compact_text(_clean_text(cell)).lower() for cell in row]
            room_index = next(
                (
                    index
                    for index, cell in enumerate(normalized)
                    if any(keyword in cell for keyword in ("열람실", "실명", "room"))
                ),
                None,
            )
            total_index = next(
                (
                    index
                    for index, cell in enumerate(normalized)
                    if any(keyword in cell for keyword in ("전체", "총", "합계"))
                    and "잔여" not in cell
                    and "사용" not in cell
                ),
                None,
            )
            occupied_index = next(
                (
                    index
                    for index, cell in enumerate(normalized)
                    if any(keyword in cell for keyword in ("사용", "이용", "점유"))
                ),
                None,
            )
            remaining_index = next(
                (
                    index
                    for index, cell in enumerate(normalized)
                    if any(keyword in cell for keyword in ("잔여", "여석", "남은", "빈"))
                ),
                None,
            )
            if room_index is None:
                continue
            if total_index is None and occupied_index is None and remaining_index is None:
                continue
            return {
                "_row_index": row_index,
                "room_name": room_index,
                "total_seats": total_index,
                "occupied_seats": occupied_index,
                "remaining_seats": remaining_index,
            }
        return None


class CampusFacilitiesSource:
    """Official campus restaurants and facilities opening-hours parser."""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def fetch_menu_document(self, source_url: str) -> bytes:
        response = httpx.get(source_url, timeout=20)
        response.raise_for_status()
        return response.content

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict] = []

        for card in soup.select(".content-box.restaurant .box-wrap.card .border-box"):
            title_node = card.select_one(".box-tit span")
            details = _collect_dl_fields(card)
            facility_name = _clean_text(title_node.get_text() if title_node else "")
            location = details.get("위치", "")
            hours_text = details.get("운영시간", "")
            menu_anchor = next(
                (
                    anchor
                    for anchor in card.select("a[href]")
                    if "메뉴" in _clean_text(anchor.get_text())
                ),
                None,
            )
            contact_value = _normalize_phone(details.get("전화번호"))
            if not facility_name or not location or not hours_text:
                continue
            rows.append(
                {
                    "facility_name": facility_name,
                    "location": location,
                    "hours_text": hours_text,
                    "phone": contact_value,
                    "menu_week_label": (
                        _clean_text(menu_anchor.get_text()) if menu_anchor else None
                    ),
                    "menu_source_url": (
                        urljoin(self.url, unescape(menu_anchor.get("href", "")))
                        if menu_anchor and menu_anchor.get("href")
                        else None
                    ),
                    "category": "식당안내",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": fetched_at,
                }
            )

        table = soup.select_one(".content-box.restaurant .table-wrap table")
        if table is None:
            return rows

        grid = _extract_table_grid(table)
        if not grid:
            return rows

        header = grid[0]
        category_index = _column_index_for_header(header, ["업종"], 0)
        name_index = _column_index_for_header(header, ["매장명", "시설명"], 1)
        phone_index = _column_index_for_header(header, ["전화번호", "연락처"], 2)
        location_index = _column_index_for_header(header, ["위치"], 3)
        hours_index = _column_index_for_header(header, ["운영시간", "운영"], 4)
        min_cells = max(category_index, name_index, phone_index, location_index, hours_index) + 1

        for row in grid[1:]:
            if len(row) < min_cells:
                continue
            category = _clean_text(row[category_index]) if category_index < len(row) else ""
            facility_name = _clean_text(row[name_index]) if name_index < len(row) else ""
            phone = _normalize_phone(row[phone_index]) if phone_index < len(row) else None
            location = _clean_text(row[location_index]) if location_index < len(row) else ""
            hours_text = _clean_text(row[hours_index]) if hours_index < len(row) else ""
            if not facility_name:
                continue
            rows.append(
                {
                    "facility_name": facility_name,
                    "location": location,
                    "hours_text": hours_text,
                    "phone": phone,
                    "category": category,
                    "source_tag": "cuk_facilities",
                    "last_synced_at": fetched_at,
                }
            )
        return rows


class TransportGuideSource:
    """Official static transport-guide parser for Songsim campus."""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict] = []

        address = _clean_text(
            soup.select_one(".map-address .addr span").get_text()
            if soup.select_one(".map-address .addr span")
            else ""
        )
        phone = _clean_text(
            soup.select_one(".map-address .tel span").get_text()
            if soup.select_one(".map-address .tel span")
            else ""
        )
        title = _clean_text(
            soup.select_one(".map-title").get_text() if soup.select_one(".map-title") else ""
        )
        if title:
            rows.append(
                {
                    "mode": "campus",
                    "title": title.replace("가톨릭대학교 ", ""),
                    "summary": " / ".join(part for part in [address, phone] if part),
                    "steps": [part for part in [address, phone] if part],
                    "source_url": self.url,
                    "source_tag": "cuk_transport",
                    "last_synced_at": fetched_at,
                }
            )

        for section in soup.select(".con-box02"):
            heading_node = section.select_one(".h5-tit01")
            heading = _clean_text(heading_node.get_text() if heading_node else "")
            mode = "subway" if "지하철" in heading else "bus"
            for box in section.select(".border-box"):
                title_box = box.find("p")
                title_span = title_box.find("span") if title_box else None
                route_title = _clean_text(title_span.get_text() if title_span else "")
                summaries = [
                    _clean_text(item.get_text(" ", strip=True))
                    for item in box.select(".box-tit")
                ]
                if not route_title:
                    continue
                rows.append(
                    {
                        "mode": mode,
                        "title": route_title,
                        "summary": " / ".join(item for item in summaries if item),
                        "steps": _flatten_transport_steps(box),
                        "source_url": self.url,
                        "source_tag": "cuk_transport",
                        "last_synced_at": fetched_at,
                    }
                )
        return rows


class CertificateGuideSource:
    """Official static certificate-guide parser for Songsim campus."""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box.cert") or soup
        rows: list[dict] = []

        title_node = next(
            (
                node
                for node in root.select(".con-box .h4-tit01")
                if _clean_text(node.get_text()) == "발급증명"
            ),
            None,
        )
        if title_node:
            summary_node = title_node.find_next_sibling("div")
            summary = _clean_text(summary_node.get_text(" ", strip=True) if summary_node else "")
            if summary:
                rows.append(
                    {
                        "title": "발급증명",
                        "summary": summary,
                        "steps": [],
                        "source_url": self.url,
                        "source_tag": "cuk_certificate_guides",
                        "last_synced_at": fetched_at,
                    }
                )

        for box in root.select(".box-wrap .border-box"):
            row = self._parse_simple_box(box, fetched_at=fetched_at)
            if row is not None:
                rows.append(row)

        internet_box = root.select_one(".border-box.box4")
        if internet_box is not None:
            internet_row = self._parse_internet_box(internet_box, fetched_at=fetched_at)
            if internet_row is not None:
                rows.append(internet_row)

            bg_boxes = internet_box.select(".bg-box")
            if len(bg_boxes) > 1:
                stopped_row = self._parse_mail_stop_box(bg_boxes[1], fetched_at=fetched_at)
                if stopped_row is not None:
                    rows.append(stopped_row)
        return rows

    def _parse_simple_box(self, box, *, fetched_at: str) -> dict | None:
        title = _clean_text(
            box.select_one(".box-tit").get_text() if box.select_one(".box-tit") else ""
        )
        if not title:
            return None
        pairs = _collect_dl_pairs(box)
        if not pairs:
            return None
        summary = self._build_summary(title, pairs)
        steps = [f"{label}: {value}" for label, value in pairs]
        steps.extend(
            self._normalize_note(_clean_text(node.get_text(" ", strip=True)))
            for node in box.select(".alert-txt")
            if _clean_text(node.get_text(" ", strip=True))
        )
        return {
            "title": title,
            "summary": summary,
            "steps": steps,
            "source_url": self.url,
            "source_tag": "cuk_certificate_guides",
            "last_synced_at": fetched_at,
        }

    def _parse_internet_box(self, box, *, fetched_at: str) -> dict | None:
        title_wrap = box.find("div", class_="box-tit-wrap")
        title = _clean_text(title_wrap.get_text(" ", strip=True) if title_wrap else "")
        info_box = box.select_one(".bg-box .info-box")
        if not title or info_box is None:
            return None
        pairs = _collect_dl_pairs(info_box)
        summary = next((value for label, value in pairs if label == "신청방법"), "")
        steps = [f"{label}: {value}" for label, value in pairs if label != "신청방법"]
        steps.extend(
            self._normalize_note(_clean_text(node.get_text(" ", strip=True)))
            for node in info_box.select(".alert-txt")
            if _clean_text(node.get_text(" ", strip=True))
        )
        link = info_box.select_one("a[href]")
        source_url = urljoin(self.url, unescape(link.get("href", ""))) if link else self.url
        return {
            "title": title,
            "summary": summary,
            "steps": steps,
            "source_url": source_url,
            "source_tag": "cuk_certificate_guides",
            "last_synced_at": fetched_at,
        }

    def _parse_mail_stop_box(self, box, *, fetched_at: str) -> dict | None:
        title = _clean_text(
            box.select_one(".box-tit").get_text() if box.select_one(".box-tit") else ""
        )
        info_box = box.select_one(".info-box")
        if not title or info_box is None:
            return None
        summary_node = info_box.find("dd")
        summary = _clean_text(summary_node.get_text(" ", strip=True) if summary_node else "")
        pairs = _collect_dl_pairs(info_box)
        steps = [f"{label}: {value}" for label, value in pairs]
        for note in info_box.select(".alert-txt"):
            text = _clean_text(note.get_text(" ", strip=True))
            if not text:
                continue
            if "관련 문의" in text:
                text = text.replace("※ 관련 문의 :", "문의:").replace("※ 관련 문의:", "문의:")
            steps.append(text)
        link = info_box.select_one("a[href]")
        source_url = urljoin(self.url, unescape(link.get("href", ""))) if link else self.url
        return {
            "title": title,
            "summary": summary,
            "steps": steps,
            "source_url": source_url,
            "source_tag": "cuk_certificate_guides",
            "last_synced_at": fetched_at,
        }

    @staticmethod
    def _build_summary(title: str, pairs: list[tuple[str, str]]) -> str:
        field_map = {label: value for label, value in pairs}
        if "발급장소" in field_map and "이용시간" in field_map:
            return f"{field_map['발급장소']} / {field_map['이용시간']}"
        if "신청방법" in field_map:
            return field_map["신청방법"]
        return pairs[0][1] if pairs else title

    @staticmethod
    def _normalize_note(text: str) -> str:
        return text.lstrip("*※ ").strip()


class LeaveOfAbsenceGuideSource:
    """Official static leave-of-absence guide parser for Songsim campus."""

    SECTION_TITLES = (
        "신청방법",
        "휴학상담 안내",
        "다음의 경우 학사지원팀에 직접 방문 제출",
        "휴학 시기에 따른 등록금 반환 기준",
    )

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box.leaveAb") or soup.select_one(".content-box") or soup
        boxes = root.find_all("div", class_="con-box", recursive=False)
        rows_by_title: dict[str, dict] = {}

        for box in boxes:
            title_node = box.select_one(".h4-tit01")
            title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
            if not title:
                continue
            if title == "신청방법":
                rows_by_title[title] = self._parse_application_box(box, fetched_at=fetched_at)
            elif title == "휴학상담 안내":
                rows_by_title[title] = self._parse_consultation_box(box, fetched_at=fetched_at)
            elif title == "다음의 경우 학사지원팀에 직접 방문 제출":
                rows_by_title[title] = self._parse_direct_visit_box(box, fetched_at=fetched_at)
            elif title == "휴학 시기에 따른 등록금 반환 기준":
                rows_by_title[title] = self._parse_refund_box(box, fetched_at=fetched_at)

        return [rows_by_title[title] for title in self.SECTION_TITLES if title in rows_by_title]

    def _parse_application_box(self, box, *, fetched_at: str) -> dict:
        step_infos: list[str] = []
        steps: list[str] = []
        for item in box.select(".step-wrap .step-box"):
            step_num = _clean_text(item.select_one(".step-num").get_text(" ", strip=True))
            step_info = _clean_text(item.select_one(".step-info").get_text(" ", strip=True))
            actor_nodes = item.find_all("p", recursive=False)
            actor = _clean_text(actor_nodes[-1].get_text(" ", strip=True) if actor_nodes else "")
            if step_info:
                step_infos.append(step_info)
            if step_num and step_info:
                detail = f"{step_num}: {step_info}"
                if actor:
                    detail += f" ({actor})"
                steps.append(detail)
        return {
            "title": "신청방법",
            "summary": " → ".join(step_infos),
            "steps": steps,
            "links": _extract_link_items(box.select_one(".link-box") or box, base_url=self.url),
            "source_url": self.url,
            "source_tag": "cuk_leave_of_absence_guides",
            "last_synced_at": fetched_at,
        }

    def _parse_consultation_box(self, box, *, fetched_at: str) -> dict:
        steps = self._extract_nested_list_steps(box.select_one(".ul-type-dot"))
        return {
            "title": "휴학상담 안내",
            "summary": (
                "상담을 위한 지도교수 확인과 상담일정 조율 후 휴학관련 문의처를 확인합니다."
            ),
            "steps": steps,
            "links": [],
            "source_url": self.url,
            "source_tag": "cuk_leave_of_absence_guides",
            "last_synced_at": fetched_at,
        }

    def _parse_direct_visit_box(self, box, *, fetched_at: str) -> dict:
        subsection_titles: list[str] = []
        steps: list[str] = []
        for section in box.select(".con-box02"):
            subtitle_node = section.select_one(".h5-tit01")
            subtitle = _clean_text(subtitle_node.get_text(" ", strip=True) if subtitle_node else "")
            if subtitle:
                subsection_titles.append(subtitle)
            for item in self._extract_nested_list_steps(section.select_one(".ul-type-dot")):
                if subtitle:
                    steps.append(f"{subtitle}: {item}")
                else:
                    steps.append(item)
        for note in box.select(".alert-txt li, .alert-txt p"):
            text = _normalize_note_text(note.get_text(" ", strip=True))
            if text and text not in steps:
                steps.append(text)
        title_preview = ", ".join(subsection_titles[:2])
        summary = (
            f"{title_preview} 등 예외적인 경우에는 학사지원팀 방문 제출이 필요합니다."
            if title_preview
            else "예외적인 경우에는 학사지원팀 방문 제출이 필요합니다."
        )
        return {
            "title": "다음의 경우 학사지원팀에 직접 방문 제출",
            "summary": summary,
            "steps": _unique(steps),
            "links": _extract_link_items(box.select_one(".link-box") or box, base_url=self.url),
            "source_url": self.url,
            "source_tag": "cuk_leave_of_absence_guides",
            "last_synced_at": fetched_at,
        }

    def _parse_refund_box(self, box, *, fetched_at: str) -> dict:
        table = box.select_one("table")
        steps = _extract_table_steps(table) if table is not None else []
        return {
            "title": "휴학 시기에 따른 등록금 반환 기준",
            "summary": "휴학 시점에 따라 수업료 전액, 5/6, 2/3 또는 미반환 기준이 적용됩니다.",
            "steps": steps,
            "links": [],
            "source_url": self.url,
            "source_tag": "cuk_leave_of_absence_guides",
            "last_synced_at": fetched_at,
        }

    @staticmethod
    def _extract_nested_list_steps(list_node) -> list[str]:
        if list_node is None:
            return []
        steps: list[str] = []
        for item in list_node.find_all("li", recursive=False):
            main_text = LeaveOfAbsenceGuideSource._direct_list_text(item)
            if main_text:
                steps.append(main_text)
            for nested_list in item.find_all("ul", recursive=False):
                for nested_item in nested_list.find_all("li", recursive=False):
                    nested_text = _normalize_note_text(nested_item.get_text(" ", strip=True))
                    if not nested_text:
                        continue
                    if main_text:
                        steps.append(f"{main_text.rstrip(':')}: {nested_text}")
                    else:
                        steps.append(nested_text)
        return _unique(steps)

    @staticmethod
    def _direct_list_text(item) -> str:
        parts: list[str] = []
        for child in item.contents:
            if getattr(child, "name", None) == "ul":
                continue
            text = _clean_text(
                str(child)
                if isinstance(child, str)
                else child.get_text(" ", strip=True)
            )
            if text:
                parts.append(text)
        return _normalize_note_text(" ".join(parts))


def _extract_alert_steps(box) -> list[str]:
    steps: list[str] = []
    for node in box.select(".alert-txt li, .alert-txt p, p.alert-txt"):
        text = _normalize_note_text(node.get_text(" ", strip=True))
        if text:
            steps.append(text)
    return _unique(steps)


def _extract_con_box_paragraph_steps(box) -> list[str]:
    steps: list[str] = []
    for node in box.find_all(["p", "div"], recursive=False):
        classes = set(node.get("class", []))
        if {"h4-tit01", "h3-tit01"} & classes:
            continue
        if {"alert-txt", "link-box", "table-wrap"} & classes:
            continue
        if node.find("table", recursive=False):
            continue
        text = _normalize_note_text(node.get_text(" ", strip=True))
        if text:
            steps.append(text)
    return _unique(steps)


def _extract_guide_box_steps(box) -> list[str]:
    steps = _extract_con_box_paragraph_steps(box)
    steps.extend(LeaveOfAbsenceGuideSource._extract_nested_list_steps(box.select_one("ul")))
    table = box.select_one("table")
    if table is not None:
        steps.extend(_extract_table_steps(table))
    steps.extend(_extract_alert_steps(box))
    return _unique(steps)


def _normalize_academic_status_title(title: str) -> str:
    normalized = _clean_text(title)
    if normalized.startswith("자퇴 신청 방법"):
        return "자퇴 신청 방법"
    return normalized


def _parse_academic_status_sections(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    status: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".content-box") or soup
    boxes = root.find_all("div", class_="con-box", recursive=False)
    rows: list[dict] = []
    for box in boxes:
        title_node = box.select_one(".h4-tit01") or box.select_one(".h3-tit01")
        title = _normalize_academic_status_title(
            title_node.get_text(" ", strip=True) if title_node else ""
        )
        if not title:
            continue
        steps = _extract_guide_box_steps(box)
        summary = steps[0] if steps else ""
        rows.append(
            {
                "status": status,
                "title": title,
                "summary": summary,
                "steps": steps,
                "links": _extract_link_items(box.select_one(".link-box") or box, base_url=base_url),
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )
    return rows


class AcademicStatusGuideSourceBase:
    """Shared parser for the academic-status guide family."""

    source_tag = "cuk_academic_status_guides"
    status = ""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_academic_status_sections(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            status=self.status,
            fetched_at=fetched_at,
        )


class ReturnFromLeaveOfAbsenceGuideSource(AcademicStatusGuideSourceBase):
    """Parser for the 복학 안내 page."""

    status = "return_from_leave"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/support/return_from_leave_of_absence.do"):
        super().__init__(url)


class DropoutGuideSource(AcademicStatusGuideSourceBase):
    """Parser for the 자퇴 안내 page."""

    status = "dropout"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/support/dropout.do"):
        super().__init__(url)


class ReAdmissionGuideSource(AcademicStatusGuideSourceBase):
    """Parser for the 재입학 안내 page."""

    status = "re_admission"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/support/re_admission.do"):
        super().__init__(url)


class RegistrationGuideSourceBase:
    """Shared parser for the registration-guide family."""

    source_tag = "cuk_registration_guides"
    topic = ""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box") or soup
        boxes = root.find_all("div", class_="con-box", recursive=False)
        rows: list[dict] = []
        for box in boxes:
            title_node = box.select_one(".h4-tit01") or box.select_one(".h3-tit01")
            title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
            if not title:
                continue
            steps = _extract_guide_box_steps(box)
            summary = steps[0] if steps else ""
            rows.append(
                {
                    "topic": self.topic,
                    "title": title,
                    "summary": summary,
                    "steps": steps,
                    "links": _extract_link_items(
                        box.select_one(".link-box") or box,
                        base_url=self.url,
                    ),
                    "source_url": self.url,
                    "source_tag": self.source_tag,
                    "last_synced_at": fetched_at,
                }
            )
        return rows


class RegistrationBillLookupGuideSource(RegistrationGuideSourceBase):
    """Parser for the 재학생 고지서 조회 · 출력 방법 page."""

    topic = "bill_lookup"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/tuition_fee_payment_schedule.do",
    ):
        super().__init__(url)


class RegistrationPaymentAndReturnGuideSource(RegistrationGuideSourceBase):
    """Parser for the 등록금 납부/반환 page."""

    topic = "payment_and_return"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/tuition_payment_and_returning.do",
    ):
        super().__init__(url)


class RegistrationPaymentByStudentGuideSource(RegistrationGuideSourceBase):
    """Parser for the 대상별 등록금 납부 page."""

    topic = "payment_by_student"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/tuition_payment_by_student.do",
    ):
        super().__init__(url)


class ClassGuideSourceBase:
    """Shared parser for the class-guide family."""

    source_tag = "cuk_class_guides"
    topic = ""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_class_guide_sections(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            topic=self.topic,
            fetched_at=fetched_at,
        )


class ClassRegistrationChangeGuideSource(ClassGuideSourceBase):
    """Parser for the 수강신청·변경 page."""

    topic = "registration_change"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/support/register_for_class.do"):
        super().__init__(url)


class ClassRetakeGuideSource(ClassGuideSourceBase):
    """Parser for the 재수강 page."""

    topic = "retake"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/support/re-register_for_class.do"):
        super().__init__(url)


class ClassCourseCancellationGuideSource(ClassGuideSourceBase):
    """Parser for the 수강과목취소 page."""

    topic = "course_cancellation"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/support/cancellation_of_class.do"):
        super().__init__(url)


class ClassCourseEvaluationGuideSource(ClassGuideSourceBase):
    """Parser for the 수업평가 page."""

    topic = "course_evaluation"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/support/course_evaluation.do"):
        super().__init__(url)


class ClassExcusedAbsenceGuideSource(ClassGuideSourceBase):
    """Parser for the 공결 page."""

    topic = "excused_absence"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/support/absence_notification.do"):
        super().__init__(url)


class ClassForeignLanguageRequirementGuideSource(ClassGuideSourceBase):
    """Parser for the 학번별 외국어강의 의무이수 요건 page."""

    topic = "foreign_language_requirement"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/completion_requirements_for_foreign_language_2024.do",
    ):
        super().__init__(url)


class StudentExchangeGuideSourceBase:
    """Shared parser for the student exchange guide family."""

    source_tag = "cuk_student_exchange_guides"
    topic = ""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text


class StudentExchangeDomesticCreditExchangeGuideSource(StudentExchangeGuideSourceBase):
    """Parser for the 국내 학점교류 안내 page."""

    topic = "domestic_credit_exchange"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/exchange_domestic1.do",
    ):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_student_exchange_con_box_guides(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            topic=self.topic,
            fetched_at=fetched_at,
        )


class StudentExchangeDomesticPartnerUniversitiesGuideSource(StudentExchangeGuideSourceBase):
    """Parser for the 국내 교류대학 현황 page."""

    topic = "domestic_partner_universities"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/exchange_domestic2.do",
    ):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_student_exchange_domestic_partner_universities(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            topic=self.topic,
            fetched_at=fetched_at,
        )


class StudentExchangeExchangeStudentGuideSource(StudentExchangeGuideSourceBase):
    """Parser for the 해외 교환학생 page."""

    topic = "exchange_student"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/exchange_oversea2.do",
    ):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        return _parse_student_exchange_con_box_guides(
            soup,
            base_url=self.url,
            source_tag=self.source_tag,
            topic=self.topic,
            fetched_at=fetched_at,
            shared_links=_extract_link_items(
                soup.select_one(".content-box .link-box"),
                base_url=self.url,
            ),
        )


class StudentExchangeExchangeProgramsGuideSource(StudentExchangeGuideSourceBase):
    """Parser for the 해외 교류프로그램 page."""

    topic = "exchange_programs"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/exchange_oversea3.do",
    ):
        super().__init__(url)

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_student_exchange_thumb_guides(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            topic=self.topic,
            fetched_at=fetched_at,
        )


class StudentExchangePartnerSource:
    """Parser for the overseas partner university APP-backed directory."""

    source_tag = "cuk_student_exchange_partners"
    landing_url = "https://www.catholic.ac.kr/ko/support/exchange_oversea1.do"
    list_url = "https://www.catholic.ac.kr/exchangeOverseaVue/getList.do"

    def __init__(
        self,
        landing_url: str = "https://www.catholic.ac.kr/ko/support/exchange_oversea1.do",
        list_url: str = "https://www.catholic.ac.kr/exchangeOverseaVue/getList.do",
    ):
        self.landing_url = landing_url
        self.list_url = list_url

    def fetch(self) -> str:
        landing_response = httpx.get(self.landing_url, timeout=20, follow_redirects=True)
        landing_response.raise_for_status()
        self._validate_landing_page(landing_response.text)

        response = httpx.get(self.list_url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def parse(self, payload: str, *, fetched_at: str) -> list[dict]:
        data = json.loads(payload)
        rows: list[dict] = []
        for item in data.get("list", []):
            university_name = _clean_text(item.get("schNm"))
            if not university_name:
                continue

            homepage_url = unescape(str(item.get("homePageAddr") or "")).strip()
            if homepage_url and not homepage_url.startswith("http"):
                homepage_url = f"http://{homepage_url}"

            rows.append(
                {
                    "partner_code": _clean_text(item.get("agrtSchCd")),
                    "university_name": university_name,
                    "country_ko": _clean_text(item.get("counNmKor")) or None,
                    "country_en": _clean_text(item.get("counNmEng")) or None,
                    "continent": _clean_text(item.get("conti")) or None,
                    "location": _clean_text(item.get("loca")) or None,
                    "agreement_date": _clean_text(item.get("concDt")) or None,
                    "homepage_url": homepage_url or None,
                    "source_url": self.landing_url,
                    "source_tag": self.source_tag,
                    "last_synced_at": fetched_at,
                }
            )
        return rows

    @staticmethod
    def _validate_landing_page(html: str) -> None:
        if 'appKey":"exchange-oversea-vue"' not in html or 'pageKind":"APP"' not in html:
            raise ValueError(
                "exchange_oversea1.do no longer exposes exchange-oversea-vue APP metadata."
            )


class SeasonalSemesterGuideSource:
    """Parser for the 계절학기 guide page."""

    source_tag = "cuk_seasonal_semester_guides"
    topic = "seasonal_semester"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
    ):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_seasonal_semester_guide_sections(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            topic=self.topic,
            fetched_at=fetched_at,
        )


class AcademicMilestoneGuideSourceBase:
    """Shared parser for the academic-milestone guide family."""

    source_tag = "cuk_academic_milestone_guides"
    topic = ""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_academic_milestone_guide_sections(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            topic=self.topic,
            fetched_at=fetched_at,
        )


class GradeEvaluationGuideSource(AcademicMilestoneGuideSourceBase):
    """Parser for the 성적평가 page."""

    topic = "grade_evaluation"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/grade_evaluation_system.do",
    ):
        super().__init__(url)


class GraduationRequirementGuideSource(AcademicMilestoneGuideSourceBase):
    """Parser for the 졸업요건 page."""

    topic = "graduation_requirement"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/support/graduation_requirement.do",
    ):
        super().__init__(url)


class PhoneBookSource:
    """Parser for the 주요전화번호 page."""

    source_tag = "cuk_phone_book"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/about/phone_book.do"):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_phone_book_entries(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            fetched_at=fetched_at,
        )


class DormitorySongsimGuideSource:
    """Parser for the 성심교정 기숙사 소개 page."""

    source_tag = "cuk_dormitory_guides"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do"):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_dormitory_songsim_guides(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            fetched_at=fetched_at,
        )


class DormitoryHomepageGuideSource:
    """Parser for the dormitory homepage quick links and notice cards."""

    source_tag = "cuk_dormitory_guides"

    def __init__(self, url: str = "https://dorm.catholic.ac.kr/"):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_dormitory_home_guides(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            fetched_at=fetched_at,
        )


class DormitoryFeeGuideSource:
    """Parser for the K/A hall dormitory fee and refund guide."""

    source_tag = "cuk_dormitory_guides"

    def __init__(
        self,
        url: str = "https://dorm.catholic.ac.kr/dormitory/life-guide/stefano-andrea.do",
    ):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        return _parse_dormitory_fee_guides(
            html,
            base_url=self.url,
            source_tag=self.source_tag,
            fetched_at=fetched_at,
        )


def _parse_dormitory_songsim_guides(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []

    for box in soup.select(".box-wrap.card .border-box"):
        title_node = box.select_one(".box-tit")
        title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        if not title:
            continue
        steps = _unique(
            [
                _clean_text(node.get_text(" ", strip=True))
                for node in box.select(".info-box > .con-p")
                if _clean_text(node.get_text(" ", strip=True))
            ]
        )
        rows.append(
            {
                "topic": "hall_info",
                "title": title,
                "summary": steps[0] if steps else title,
                "steps": steps,
                "links": [],
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )

    contact_box = soup.select_one(".sub-info-box .info-con-box")
    if contact_box is not None:
        name_node = contact_box.select_one(".name")
        department = _clean_text(name_node.get_text(" ", strip=True) if name_node else "")
        if department:
            title = department.removeprefix("성심교정 ")
            contact_steps: list[str] = []
            contact_steps.append(f"담당부서: {department}")
            phone_anchor = contact_box.select_one('.info-con a[href^="tel:"]')
            if phone_anchor is not None:
                phone_text = _clean_text(phone_anchor.get_text(" ", strip=True))
                if phone_text:
                    contact_steps.append(f"전화: {phone_text}")
            mail_anchor = contact_box.select_one('.info-con a[href^="mailto:"]')
            if mail_anchor is not None:
                mail_text = _clean_text(mail_anchor.get_text(" ", strip=True))
                if mail_text:
                    contact_steps.append(f"메일: {mail_text}")
            rows.append(
                {
                    "topic": "hall_info",
                    "title": title,
                    "summary": contact_steps[0] if contact_steps else title,
                    "steps": contact_steps,
                    "links": _extract_link_items(
                        contact_box.select_one(".info-con") or contact_box,
                        base_url=base_url,
                    ),
                    "source_url": base_url,
                    "source_tag": source_tag,
                    "last_synced_at": fetched_at,
                }
            )

    return rows


def _parse_dormitory_home_guides(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []

    quick_link_labels = [
        "입사안내",
        "퇴사안내",
        "생활안내",
        "기숙사비",
        "FAQ",
        "기숙사비 환불신청서",
        "신입생 입사신청",
    ]
    quick_link_root = soup.select_one(".main_cont.sec1 .cont_top") or soup
    quick_links = _dormitory_links_by_labels(
        quick_link_root,
        labels=quick_link_labels,
        base_url=base_url,
    )
    if quick_links:
        quick_steps = [item["label"] for item in quick_links]
        rows.append(
            {
                "topic": "quick_links",
                "title": " / ".join(quick_steps[:5]),
                "summary": quick_steps[0],
                "steps": quick_steps,
                "links": quick_links,
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )

    tab_title_map = {
        _clean_text(anchor.get("href", "").lstrip("#")): _clean_text(
            anchor.get("title") or anchor.get_text(" ", strip=True)
        )
        for anchor in soup.select(".title_box .tab a[href^='#']")
    }
    for tab in soup.select(".tab_cont"):
        tab_id = _clean_text(tab.get("id"))
        title = tab_title_map.get(tab_id, "")
        if not title:
            continue
        card_anchors = tab.select("ul > li > a[href]")
        titles: list[str] = []
        links: list[dict[str, str]] = []
        for anchor in card_anchors:
            card_title_node = anchor.select_one(".el")
            card_title = _clean_text(
                card_title_node.get_text(" ", strip=True)
                if card_title_node
                else anchor.get_text(" ", strip=True)
            )
            if not card_title:
                continue
            titles.append(card_title)
            links.append(
                {
                    "label": card_title,
                    "url": urljoin(base_url, str(anchor.get("href") or "")),
                }
            )
        if not titles:
            continue
        rows.append(
            {
                "topic": "latest_notices",
                "title": title,
                "summary": titles[0],
                "steps": titles,
                "links": links,
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )

    return rows


def _parse_dormitory_fee_guides(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("#cms-content") or soup
    steps: list[str] = []

    for table in root.select("table"):
        caption_node = table.select_one("caption")
        caption = _clean_text(
            caption_node.get_text(" ", strip=True) if caption_node else ""
        )
        for step in _dormitory_fee_table_steps(table):
            steps.append(f"{caption}: {step}" if caption else step)

    for item in root.select(".refund_step_box li"):
        text = _clean_text(item.get_text(" ", strip=True))
        if text:
            steps.append(f"환불절차: {text}")

    for note in root.select(".mark-p"):
        text = _normalize_note_text(note.get_text(" ", strip=True))
        if text:
            steps.append(text)

    steps = _unique(steps)
    return [
        {
            "topic": "fees",
            "title": "스테파노관 / 안드레아관 기숙사비",
            "summary": (
                "정규학기와 방학 기숙사비, 추가 선발 납부금액, 환불절차와 "
                "환불기준을 공식 페이지에서 확인할 수 있습니다."
            ),
            "steps": steps,
            "links": _extract_link_items(root, base_url=base_url),
            "source_url": base_url,
            "source_tag": source_tag,
            "last_synced_at": fetched_at,
        }
    ]


def _dormitory_fee_table_steps(table) -> list[str]:
    steps = _extract_table_steps(table)
    if steps:
        return steps

    rows = _extract_table_grid(table)
    fallback_steps: list[str] = []
    for row in rows:
        nonempty = _unique([_clean_text(cell) for cell in row if _clean_text(cell)])
        if len(nonempty) >= 2:
            fallback_steps.append(f"{nonempty[0]}: {' / '.join(nonempty[1:])}")
        elif nonempty:
            fallback_steps.append(_normalize_note_text(nonempty[0]))
    return _unique(fallback_steps)


def _dormitory_links_by_labels(
    root,
    *,
    labels: list[str],
    base_url: str,
) -> list[dict[str, str]]:
    wanted = {label: None for label in labels}
    for anchor in root.select("a[href]"):
        label = _clean_text(anchor.get_text(" ", strip=True))
        if label not in wanted or wanted[label] is not None:
            continue
        href = unescape(str(anchor.get("href") or "")).strip()
        if not href:
            continue
        wanted[label] = {"label": label, "url": urljoin(base_url, href)}
    return [item for item in (wanted[label] for label in labels) if item is not None]


def _parse_class_guide_sections(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    topic: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    roots = soup.select(".content-box") or [soup]
    rows_by_title: dict[str, dict] = {}

    for root in roots:
        for node in _iter_class_guide_section_nodes(root):
            title = _class_guide_section_title(node)
            if not title:
                continue
            steps = _class_guide_section_steps(node)
            summary = _class_guide_section_summary(node, title=title, steps=steps)
            rows_by_title[title] = {
                "topic": topic,
                "title": title,
                "summary": summary,
                "steps": steps,
                "links": _extract_link_items(
                    node.select_one(".link-box") or node,
                    base_url=base_url,
                ),
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }

    return list(rows_by_title.values())


def _parse_academic_milestone_guide_sections(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    topic: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".content-box") or soup
    rows: list[dict] = []
    current_title = ""
    current_fragments: list[str] = []

    def flush() -> None:
        nonlocal current_fragments
        if not current_title:
            current_fragments = []
            return
        wrapper = BeautifulSoup(f"<div>{''.join(current_fragments)}</div>", "html.parser").div
        if wrapper is None:
            current_fragments = []
            return
        steps = _extract_academic_milestone_steps(wrapper)
        rows.append(
            {
                "topic": topic,
                "title": current_title,
                "summary": _academic_milestone_summary(wrapper, title=current_title, steps=steps),
                "steps": steps,
                "links": _extract_link_items(wrapper, base_url=base_url),
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )
        current_fragments = []

    def walk(container) -> None:
        nonlocal current_title, current_fragments
        for child in list(getattr(container, "children", [])):
            if getattr(child, "name", None) is None:
                continue
            if _is_academic_milestone_title_node(child):
                flush()
                current_title = _clean_text(child.get_text(" ", strip=True))
                current_fragments = []
                continue
            if _has_academic_milestone_direct_titles(child):
                walk(child)
                continue
            if current_title:
                current_fragments.append(str(child))

    walk(root)
    flush()
    return rows


def _is_academic_milestone_title_node(node) -> bool:
    if getattr(node, "name", None) not in {"p", "div"}:
        return False
    classes = set(node.get("class", []))
    return bool({"h4-tit01", "h3-tit01"} & classes)


def _has_academic_milestone_direct_titles(node) -> bool:
    return any(
        _is_academic_milestone_title_node(child)
        for child in node.find_all(["p", "div"], recursive=False)
    )


def _academic_milestone_summary(node, *, title: str, steps: list[str]) -> str:
    direct_steps = _academic_milestone_direct_text_steps(node)
    if direct_steps:
        return direct_steps[0]
    return steps[0] if steps else title


def _extract_academic_milestone_steps(node) -> list[str]:
    steps: list[str] = []

    def visit(section) -> None:
        classes = set(section.get("class", []))
        if _is_academic_milestone_title_node(section):
            return
        if "alert-box" in classes:
            alert_title_node = section.select_one(".alert-tit")
            alert_title = _clean_text(
                alert_title_node.get_text(" ", strip=True) if alert_title_node else ""
            )
            alert_items = LeaveOfAbsenceGuideSource._extract_nested_list_steps(
                section.select_one("ul")
            )
            if alert_title and alert_items:
                steps.extend(f"{alert_title}: {item}" for item in alert_items)
            else:
                steps.extend(alert_items)
            steps.extend(_extract_alert_steps(section))
            return
        if getattr(section, "name", None) == "table":
            steps.extend(_extract_table_steps(section))
            return
        if getattr(section, "name", None) in {"ul", "ol"}:
            steps.extend(LeaveOfAbsenceGuideSource._extract_nested_list_steps(section))
            steps.extend(_extract_alert_steps(section))
            return
        if "alert-txt" in classes:
            text = _normalize_note_text(section.get_text(" ", strip=True))
            if text:
                steps.append(text)
            return
        if "link-box" not in classes and "table-wrap" not in classes:
            text = _extract_academic_milestone_direct_text(section)
            if text:
                steps.append(text)
        for child in section.find_all(recursive=False):
            visit(child)

    for child in node.find_all(recursive=False):
        visit(child)
    return _unique(steps)


def _academic_milestone_direct_text_steps(node) -> list[str]:
    steps: list[str] = []
    for child in node.find_all(recursive=False):
        if _is_academic_milestone_title_node(child):
            continue
        if getattr(child, "name", None) in {"ul", "ol", "table", "br"}:
            continue
        classes = set(child.get("class", []))
        if {
            "h5-tit01",
            "alert-tit",
            "box-tit",
            "alert-box",
            "alert-txt",
            "link-box",
            "table-wrap",
        } & classes:
            continue
        text = _extract_academic_milestone_direct_text(child)
        if text:
            steps.append(text)
    return _unique(steps)


def _parse_phone_book_entries(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    target_box = next(
        (
            box
            for box in soup.select(".con-box")
            if _clean_text(
                box.select_one(".h4-tit01").get_text(" ", strip=True)
                if box.select_one(".h4-tit01")
                else ""
            ).startswith("주요연락처")
            and "주요연락처 안내표"
            in _clean_text(
                box.select_one("table caption").get_text(" ", strip=True)
                if box.select_one("table caption")
                else ""
            )
        ),
        None,
    )
    if target_box is None:
        return []

    table = target_box.select_one(".table-wrap table")
    if table is None:
        return []

    rows: list[dict] = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) != 3:
            continue
        department = _clean_text(cells[0].get_text(" ", strip=True))
        tasks = _clean_text(cells[1].get_text(" ", strip=True))
        phone = _normalize_phone(cells[2].get_text(" ", strip=True))
        if not department or not tasks or phone is None:
            continue
        rows.append(
            {
                "department": department,
                "tasks": tasks,
                "phone": phone,
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )
    return rows


def _extract_academic_milestone_direct_text(node) -> str:
    classes = set(node.get("class", []))
    if getattr(node, "name", None) in {"ul", "ol", "table", "br"}:
        return ""
    if {
        "h4-tit01",
        "h5-tit01",
        "h3-tit01",
        "alert-tit",
        "box-tit",
        "alert-box",
        "alert-txt",
        "link-box",
        "table-wrap",
    } & classes:
        return ""
    parts: list[str] = []
    for child in node.contents:
        if isinstance(child, str):
            text = _clean_text(child)
            if text:
                parts.append(text)
            continue
        classes = set(child.get("class", []))
        if getattr(child, "name", None) in {"ul", "ol", "table", "br"}:
            continue
        if {
            "h4-tit01",
            "h5-tit01",
            "h3-tit01",
            "alert-tit",
            "box-tit",
            "alert-box",
            "alert-txt",
            "link-box",
            "table-wrap",
        } & classes:
            continue
        if child.find("table", recursive=False) is not None:
            continue
        text = _clean_text(child.get_text(" ", strip=True))
        if text:
            parts.append(text)
    return _normalize_note_text(" ".join(parts))


def _iter_class_guide_section_nodes(root):
    candidates = root.select(".con-box02, .alert-box, .con-box")
    seen: set[int] = set()
    nodes: list = []
    for node in candidates:
        node_id = id(node)
        if node_id in seen:
            continue
        seen.add(node_id)
        if _should_skip_class_guide_node(node):
            continue
        nodes.append(node)
    return nodes


def _should_skip_class_guide_node(node) -> bool:
    classes = set(node.get("class", []))
    if "con-box" in classes and node.find("div", class_="con-box02") is not None:
        return not _class_guide_section_title(node) and node.select_one(".qna-wrap") is None
    return False


def _class_guide_section_title(node) -> str:
    for selector in (".h4-tit01", ".h5-tit01", ".h3-tit01", ".alert-tit", ".box-tit"):
        title_node = node.select_one(selector)
        if title_node is not None:
            title = _normalize_class_guide_title(title_node.get_text(" ", strip=True))
            if title:
                return title
    return ""


def _class_guide_section_summary(node, *, title: str, steps: list[str]) -> str:
    if title == "FAQ":
        question = node.select_one(".qna-wrap li a div")
        if question is not None:
            summary = _clean_text(question.get_text(" ", strip=True))
            if summary:
                return summary
    summary_node = node.select_one(".con-p")
    if summary_node is not None:
        summary = _clean_text(summary_node.get_text(" ", strip=True))
        if summary:
            return summary
    return steps[0] if steps else title


def _class_guide_section_steps(node) -> list[str]:
    if node.select_one(".qna-wrap") is not None:
        return _unique(_extract_qna_steps(node) + _extract_alert_steps(node))
    steps: list[str] = []
    steps.extend(_class_guide_direct_text_steps(node))
    list_node = node.find("ul")
    if list_node is not None:
        steps.extend(LeaveOfAbsenceGuideSource._extract_nested_list_steps(list_node))
    for table in node.find_all("table"):
        steps.extend(_extract_table_steps(table))
    steps.extend(_extract_alert_steps(node))
    return _unique(steps)


def _class_guide_direct_text_steps(node) -> list[str]:
    steps: list[str] = []
    for child in node.find_all(["p", "div"], recursive=False):
        classes = set(child.get("class", []))
        if {"h4-tit01", "h5-tit01", "h3-tit01", "alert-tit", "box-tit", "con-tit"} & classes:
            continue
        if {"alert-txt", "link-box", "table-wrap", "qna-wrap", "bg-box"} & classes:
            continue
        if child.find("table", recursive=False) is not None:
            continue
        text = _normalize_note_text(child.get_text(" ", strip=True))
        if text:
            steps.append(text)
    return _unique(steps)


def _extract_qna_steps(node) -> list[str]:
    steps: list[str] = []
    for item in node.select(".qna-wrap > ul > li"):
        question_node = item.select_one("a div")
        answer_node = item.select_one(".ans-box")
        question = _clean_text(question_node.get_text(" ", strip=True) if question_node else "")
        answer = _clean_text(answer_node.get_text(" ", strip=True) if answer_node else "")
        if question and answer:
            steps.append(f"Q: {question} / A: {answer}")
        elif question:
            steps.append(f"Q: {question}")
        elif answer:
            steps.append(f"A: {answer}")
    return _unique(steps)


def _normalize_class_guide_title(title: str) -> str:
    normalized = _clean_text(title)
    normalized = re.sub(r"^\d+\.\s*", "", normalized)
    normalized = normalized.replace("(표)", "").strip()
    return normalized


def _parse_seasonal_semester_guide_sections(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    topic: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".content-box .con-box") or soup.select_one(".content-box") or soup
    rows: list[dict] = []
    current_title = ""
    current_nodes: list = []

    def flush() -> None:
        nonlocal current_nodes
        if not current_title:
            current_nodes = []
            return
        wrapper = soup.new_tag("div")
        for node in current_nodes:
            wrapper.append(node)
        steps = _extract_seasonal_semester_steps(wrapper)
        rows.append(
            {
                "topic": topic,
                "title": current_title,
                "summary": steps[0] if steps else current_title,
                "steps": steps,
                "links": _extract_link_items(wrapper, base_url=base_url),
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )
        current_nodes = []

    for child in root.find_all("div", class_="con-box02", recursive=False):
        title_node = child.select_one(".h4-tit01")
        if title_node is not None:
            flush()
            current_title = _clean_text(title_node.get_text(" ", strip=True))
            current_nodes = [child]
            continue
        if child.select_one(".alert-tit") is not None and current_title:
            current_nodes.append(child)

    flush()
    return rows


def _extract_seasonal_semester_steps(node) -> list[str]:
    steps: list[str] = []
    sections = node.find_all("div", class_="con-box02", recursive=False) or [node]
    for section in sections:
        title_node = section.select_one(".h4-tit01")
        if title_node is not None:
            steps.extend(_extract_seasonal_semester_direct_steps(section))
            list_node = section.find("ul", recursive=False)
            if list_node is not None:
                steps.extend(LeaveOfAbsenceGuideSource._extract_nested_list_steps(list_node))
            steps.extend(_extract_alert_steps(section))
            continue
        for alert_box in section.select(".alert-box"):
            alert_title_node = alert_box.select_one(".alert-tit")
            alert_title = _clean_text(
                alert_title_node.get_text(" ", strip=True) if alert_title_node else ""
            )
            alert_items = LeaveOfAbsenceGuideSource._extract_nested_list_steps(
                alert_box.select_one("ul")
            )
            if alert_title and alert_items:
                steps.extend(f"{alert_title}: {item}" for item in alert_items)
            else:
                steps.extend(alert_items)
    return _unique(steps)


def _extract_seasonal_semester_direct_steps(section) -> list[str]:
    steps: list[str] = []
    for child in section.find_all(["p", "div"], recursive=False):
        classes = set(child.get("class", []))
        if {"h4-tit01", "h5-tit01", "h3-tit01", "alert-tit"} & classes:
            continue
        if {"alert-txt", "link-box", "table-wrap", "alert-box"} & classes:
            continue
        if child.find("table", recursive=False) is not None:
            continue
        text = _extract_seasonal_semester_direct_text(child)
        if text:
            steps.append(text)
    return _unique(steps)


def _extract_seasonal_semester_direct_text(node) -> str:
    parts: list[str] = []
    for child in node.contents:
        if isinstance(child, str):
            text = _clean_text(child)
            if text:
                parts.append(text)
            continue
        classes = set(child.get("class", []))
        if getattr(child, "name", None) in {"ul", "table"}:
            continue
        if {"alert-txt", "alert-box", "h4-tit01", "h5-tit01", "h3-tit01", "alert-tit"} & classes:
            continue
        text = _clean_text(child.get_text(" ", strip=True))
        if text:
            parts.append(text)
    return _normalize_note_text(" ".join(parts))


def _parse_student_exchange_con_box_guides(
    html: str | BeautifulSoup,
    *,
    base_url: str,
    source_tag: str,
    topic: str,
    fetched_at: str,
    shared_links: list[dict[str, str]] | None = None,
) -> list[dict]:
    soup = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "html.parser")
    root = soup.select_one(".content-box") or soup
    rows: list[dict] = []
    shared_links = shared_links or []
    for box in root.find_all("div", class_="con-box", recursive=False):
        title_node = box.select_one(".h4-tit01")
        title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        if not title:
            continue
        steps = _extract_student_exchange_con_box_steps(box)
        rows.append(
            {
                "topic": topic,
                "title": title,
                "summary": steps[0] if steps else title,
                "steps": steps,
                "links": _extract_link_items(box.select_one(".link-box"), base_url=base_url)
                or shared_links,
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )
    return rows


def _extract_student_exchange_con_box_steps(box) -> list[str]:
    steps: list[str] = []
    for child in box.find_all(["p", "div"], recursive=False):
        classes = set(child.get("class", []))
        if {"h4-tit01", "h3-tit01", "h5-tit01"} & classes:
            continue
        if "link-box" in classes:
            continue
        if "table-wrap" in classes:
            table = child.select_one("table")
            if table is not None:
                steps.extend(_extract_table_steps(table))
            continue
        if "alert-txt" in classes:
            text = _normalize_note_text(child.get_text(" ", strip=True))
            if text:
                steps.append(text)
            continue
        text = _extract_student_exchange_direct_text(child)
        if text:
            steps.append(text)
        for alert in child.select(".alert-txt"):
            alert_text = _normalize_note_text(alert.get_text(" ", strip=True))
            if alert_text:
                steps.append(alert_text)
    return _unique(steps)


def _extract_student_exchange_direct_text(node) -> str:
    parts: list[str] = []
    for child in node.contents:
        if isinstance(child, str):
            text = _clean_text(child)
            if text:
                parts.append(text)
            continue
        classes = set(child.get("class", []))
        if getattr(child, "name", None) in {"ul", "table"}:
            continue
        if {"alert-txt", "link-box", "table-wrap"} & classes:
            continue
        if child.find("table", recursive=False) is not None:
            continue
        text = _clean_text(child.get_text(" ", strip=True))
        if text:
            parts.append(text)
    return _normalize_note_text(" ".join(parts))


def _parse_student_exchange_domestic_partner_universities(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    topic: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one(".content-box .con-box") or soup.select_one(".content-box") or soup
    title = "교류대학 현황"
    summary_node = box.select_one(".con-tit")
    summary = _clean_text(summary_node.get_text(" ", strip=True) if summary_node else "")
    steps = _extract_guide_box_steps(box)
    return [
        {
            "topic": topic,
            "title": title,
            "summary": summary or (steps[0] if steps else title),
            "steps": steps,
            "links": [],
            "source_url": base_url,
            "source_tag": source_tag,
            "last_synced_at": fetched_at,
        }
    ]


def _parse_student_exchange_thumb_guides(
    html: str,
    *,
    base_url: str,
    source_tag: str,
    topic: str,
    fetched_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".content-box") or soup
    rows: list[dict] = []
    for thumb in root.select(".thumb-box"):
        info_box = thumb.select_one(".info-box") or thumb
        title_node = info_box.select_one(".h4-tit01")
        title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        if not title:
            continue
        steps = _extract_con_box_paragraph_steps(info_box)
        rows.append(
            {
                "topic": topic,
                "title": title,
                "summary": steps[0] if steps else title,
                "steps": _unique(steps),
                "links": _extract_link_items(info_box.select_one(".link-box"), base_url=base_url),
                "source_url": base_url,
                "source_tag": source_tag,
                "last_synced_at": fetched_at,
            }
        )
    return rows


class ScholarshipGuideSource:
    """Official static scholarship-guide parser for Songsim campus."""

    SECTION_TITLES = (
        "장학생 자격",
        "장학생 종류",
        "장학금 신청",
        "장학금 지급",
    )

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box") or soup
        boxes = root.find_all("div", class_="con-box", recursive=False)
        rows_by_title: dict[str, dict] = {}

        for box in boxes:
            title_node = box.select_one(".h4-tit01")
            title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
            if title in self.SECTION_TITLES:
                row = self._parse_section_box(box, title=title, fetched_at=fetched_at)
                if row is not None:
                    rows_by_title[row["title"]] = row
            elif title == "장학금 제도보기":
                row = self._parse_document_box(box, fetched_at=fetched_at)
                if row is not None:
                    rows_by_title[row["title"]] = row

        ordered_titles = [*self.SECTION_TITLES, "공식 장학 문서"]
        return [rows_by_title[title] for title in ordered_titles if title in rows_by_title]

    def _parse_section_box(self, box, *, title: str, fetched_at: str) -> dict | None:
        summary = self._section_summary(box, title=title)
        if not summary:
            return None

        steps: list[str] = []
        for table in box.select("table"):
            steps.extend(_extract_table_steps(table))
        for note in box.select(".ul-type-dot li, .ul-type-normal li, .alert-txt"):
            normalized = _normalize_note_text(note.get_text(" ", strip=True))
            if normalized and normalized not in steps and normalized not in summary:
                steps.append(normalized)

        return {
            "title": title,
            "summary": summary,
            "steps": _unique(steps),
            "links": [],
            "source_url": self.url,
            "source_tag": "cuk_scholarship_guides",
            "last_synced_at": fetched_at,
        }

    def _parse_document_box(self, box, *, fetched_at: str) -> dict | None:
        links = _extract_link_items(box, base_url=self.url)
        if not links:
            return None
        return {
            "title": "공식 장학 문서",
            "summary": "장학금 지급 규정과 신입생/재학생 장학제도 공식 문서 링크",
            "steps": [],
            "links": links,
            "source_url": self.url,
            "source_tag": "cuk_scholarship_guides",
            "last_synced_at": fetched_at,
        }

    @staticmethod
    def _section_summary(box, *, title: str) -> str:
        if title == "장학생 종류":
            caption = box.select_one("table caption span")
            return _clean_text(caption.get_text(" ", strip=True) if caption else "")

        summary_node = box.select_one(".con-p")
        if summary_node is None:
            return ""
        if title == "장학금 신청":
            return _clean_text(summary_node.get_text(" ", strip=True))
        return _clean_text(summary_node.get_text(" ", strip=True))


class WifiGuideSource:
    """Official static wifi-guide parser for Songsim campus."""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=20)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one(".content-box") or soup
        table = root.select_one("table")
        if table is None:
            return []

        rows: list[dict] = []
        shared_steps: list[str] = []
        for tr in table.select("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if len(cells) < 2:
                continue

            building_name = _clean_text(cells[0].get_text(" ", strip=True))
            if not building_name or building_name == "건물명":
                continue

            ssids = _split_csv_items(cells[1].get_text(" ", strip=True))
            if not ssids:
                continue

            steps = self._extract_steps(cells[2]) if len(cells) > 2 else []
            if steps:
                shared_steps = steps
            elif shared_steps:
                steps = list(shared_steps)

            rows.append(
                {
                    "building_name": building_name,
                    "ssids": ssids,
                    "steps": steps,
                    "source_url": self.url,
                    "source_tag": "cuk_wifi_guides",
                    "last_synced_at": fetched_at,
                }
            )
        return rows

    @staticmethod
    def _extract_steps(cell) -> list[str]:
        steps = [
            _normalize_note_text(item.get_text(" ", strip=True))
            for item in cell.select("li")
            if _normalize_note_text(item.get_text(" ", strip=True))
        ]
        if steps:
            return _unique(steps)
        fallback = _normalize_note_text(cell.get_text(" ", strip=True))
        return [fallback] if fallback else []


class AcademicSupportGuideSource:
    """Normalize the 학사지원 업무안내 table into guide rows."""

    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> str:
        response = httpx.get(self.url, timeout=10)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, *, fetched_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        table = next(
            (
                candidate
                for candidate in soup.select("table")
                if candidate.select_one("caption strong")
                and "업무안내표" in candidate.select_one("caption strong").get_text()
            ),
            None,
        )
        if table is None:
            return []

        rows: list[dict] = []
        parent_title = ""
        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            if len(cells) >= 4:
                parent_title = _clean_text(cells[0].get_text(" ", strip=True))
                primary = parent_title
                secondary = _clean_text(cells[1].get_text(" ", strip=True))
                task_cell = cells[2]
                contact_cell = cells[3]
            else:
                primary = _clean_text(cells[0].get_text(" ", strip=True))
                secondary = ""
                if cells[0].get("colspan") == "2":
                    parent_title = ""
                elif parent_title:
                    secondary = primary
                    primary = parent_title
                task_cell = cells[-2]
                contact_cell = cells[-1]

            title = " / ".join(part for part in (primary, secondary) if part)
            if not title:
                continue

            steps = _extract_list_or_text(task_cell)
            rows.append(
                {
                    "title": title,
                    "summary": steps[0] if steps else "",
                    "steps": steps,
                    "contacts": _clean_contact_cell(contact_cell),
                    "source_url": self.url,
                    "source_tag": "cuk_academic_support_guides",
                    "last_synced_at": fetched_at,
                }
            )
        return rows


def _clean_contact_cell(cell) -> list[str]:
    parts: list[str] = []
    for line in cell.get_text("\n", strip=True).splitlines():
        cleaned = _clean_text(line)
        if cleaned:
            parts.append(cleaned)
    return parts


def _column_index_for_header(header: list[str], keywords: list[str], default: int) -> int:
    normalized_keywords = [keyword.strip().lower() for keyword in keywords]
    for index, value in enumerate(header):
        text = (value or "").lower()
        if any(keyword in text for keyword in normalized_keywords):
            return index
    return default


def _normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _clean_text(value)
    if normalized in {"-", ""}:
        return None
    return normalized


def _extract_list_or_text(cell) -> list[str]:
    items = [
        _clean_text(li.get_text(" ", strip=True))
        for li in cell.select("li")
        if _clean_text(li.get_text(" ", strip=True))
    ]
    if items:
        return items
    fallback = _clean_text(cell.get_text(" ", strip=True))
    return [fallback] if fallback else []


class AcademicCalendarSource:
    """Official academic calendar parser backed by the public JSON feed."""

    def __init__(self, url: str, site_id: str = "ko"):
        self.url = url
        self.site_id = site_id

    def fetch_range(self, *, start_date: str, end_date: str) -> str:
        response = httpx.get(
            self.url,
            params={
                "mode": "getCalendarData",
                "siteId": self.site_id,
                "start": start_date,
                "end": end_date,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.text

    def parse(self, payload: str, *, fetched_at: str) -> list[dict]:
        data = json.loads(payload)
        rows: list[dict] = []
        for item in data.get("data", []):
            title = _clean_text(item.get("content"))
            start_date = _date_from_epoch_millis(item.get("beginDt"))
            end_date = _date_from_epoch_millis(item.get("endDt")) or start_date
            if not title or start_date is None or end_date is None:
                continue
            campuses = _unique(
                [_clean_text(part) for part in str(item.get("campus") or "").split(",")]
            )
            rows.append(
                {
                    "academic_year": _academic_year_from_date_string(start_date),
                    "title": title,
                    "start_date": start_date,
                    "end_date": end_date,
                    "campuses": campuses,
                    "source_url": self.url,
                    "source_tag": "cuk_academic_calendar",
                    "last_synced_at": fetched_at,
                }
            )
        return rows


class NoticeSource:
    """Official notice board list/detail parser."""

    def __init__(self, url: str):
        self.url = url

    def fetch_list(self, *, offset: int = 0, limit: int = 10) -> str:
        response = httpx.get(
            self.url,
            params={"mode": "list", "article.offset": offset, "articleLimit": limit},
            timeout=20,
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
        )
        response.raise_for_status()
        return response.text

    def parse_list(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict] = []
        for row in soup.select("tbody tr"):
            anchor = row.select_one("a.b-title")
            if not anchor:
                continue
            columns = row.find_all("td", recursive=False)
            fallback_category = row.select_one(".b-cate")
            board_category = (
                _clean_text(columns[1].get_text())
                if len(columns) > 1
                else _clean_text(fallback_category.get_text() if fallback_category else "")
            )
            published_at = None
            if len(columns) >= 4:
                published_at = self._normalize_date(columns[-3].get_text())
            if not published_at:
                date_node = row.select_one(".b-date")
                published_at = self._normalize_date(date_node.get_text() if date_node else "")
            href = anchor.get("href", "")
            items.append(
                {
                    "article_no": anchor.get("data-article-no") or self._extract_article_no(href),
                    "title": _clean_text(anchor.get_text()),
                    "board_category": board_category,
                    "published_at": published_at,
                    "source_url": urljoin(self.url, unescape(href)),
                }
            )
        return items

    def parse_detail(
        self,
        html: str,
        *,
        default_title: str = "",
        default_category: str = "",
    ) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        title = _clean_text(
            soup.select_one(".b-title-box .b-title").get_text()
            if soup.select_one(".b-title-box .b-title")
            else default_title
        )
        detail_board_category = _clean_text(
            soup.select_one(".b-title-box .b-cate").get_text()
            if soup.select_one(".b-title-box .b-cate")
            else default_category
        )
        board_category = (
            default_category
            if default_category and detail_board_category in GENERIC_NOTICE_DETAIL_LABELS
            else detail_board_category or default_category
        )
        published_at = self._normalize_date(
            self._extract_meta_value(soup, label="등록일") or ""
        )
        body_root = soup.select_one(".b-content-box .b-con-box")
        body_text = _clean_text(body_root.get_text(" ", strip=True) if body_root else "")
        summary = body_text[:180].strip()
        return {
            "title": title or default_title,
            "published_at": published_at,
            "summary": summary,
            "labels": _unique([board_category] if board_category else []),
            "category": classify_notice_category(
                title or default_title,
                body_text,
                board_category or default_category,
            ),
        }

    @staticmethod
    def _extract_meta_value(soup: BeautifulSoup, *, label: str) -> str | None:
        for item in soup.select(".b-etc-box li"):
            title = item.select_one(".title")
            value = item.find_all("span")
            if not title or len(value) < 2:
                continue
            if label in title.get_text():
                return value[-1].get_text(strip=True)
        return None

    @staticmethod
    def _extract_article_no(href: str) -> str | None:
        match = re.search(r"articleNo=([^&]+)", href)
        return match.group(1) if match else None

    @staticmethod
    def _normalize_date(value: str) -> str | None:
        match = re.search(r"(\d{4})[./-]\s*(\d{2})[./-]\s*(\d{2})", value)
        if not match:
            return None
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


class AffiliatedNoticeBoardSourceBase(NoticeSource):
    """Shared parser for affiliated academic/dormitory notice boards."""

    source_tag = "cuk_affiliated_notice_boards"
    topic = ""

    def parse_list(self, html: str) -> list[dict]:
        rows = []
        for item in super().parse_list(html):
            article_no = item.get("article_no")
            title = _clean_text(str(item.get("title") or ""))
            if not article_no or not title:
                continue
            rows.append(
                {
                    "topic": self.topic,
                    "article_no": article_no,
                    "title": title,
                    "published_at": item.get("published_at"),
                    "source_url": item.get("source_url"),
                    "source_tag": self.source_tag,
                }
            )
        return rows

    def parse_detail(
        self,
        html: str,
        *,
        default_title: str = "",
        default_category: str = "",
        default_summary: str = "",
        default_published_at: str = "",
        default_source_url: str | None = None,
    ) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        title = _clean_text(
            soup.select_one(".b-title-box .b-title").get_text()
            if soup.select_one(".b-title-box .b-title")
            else default_title
        )
        published_at = self._normalize_date(
            self._extract_meta_value(soup, label="등록일") or ""
        )
        body_root = soup.select_one(".b-content-box .b-con-box")
        body_text = _clean_text(body_root.get_text(" ", strip=True) if body_root else "")
        row = {
            "topic": self.topic,
            "title": title or default_title,
            "published_at": published_at or default_published_at,
            "summary": body_text[:180].strip() or default_summary,
            "source_url": default_source_url or self.url,
            "source_tag": self.source_tag,
        }
        if self.source_tag == "cuk_affiliated_notice_boards":
            row["body_text"] = body_text
        return row


class InternationalStudiesAffiliatedNoticeBoardSource(AffiliatedNoticeBoardSourceBase):
    """Parser for the 국제학부 학과공지 board."""

    topic = "international_studies"

    def __init__(self, url: str = "https://is.catholic.ac.kr/is/community/notice.do"):
        super().__init__(url)


class DormKAGeneralAffiliatedNoticeBoardSource(AffiliatedNoticeBoardSourceBase):
    """Parser for the 스테파노관, 안드레아관 일반 공지 board."""

    topic = "dorm_k_a_general"

    def __init__(
        self,
        url: str = "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do",
    ):
        super().__init__(url)


class DormKACheckinOutAffiliatedNoticeBoardSource(AffiliatedNoticeBoardSourceBase):
    """Parser for the 스테파노관, 안드레아관 입퇴사공지 board."""

    topic = "dorm_k_a_checkin_out"

    def __init__(
        self,
        url: str = "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice1.do",
    ):
        super().__init__(url)


class DormFrancisGeneralAffiliatedNoticeBoardSource(AffiliatedNoticeBoardSourceBase):
    """Parser for the 프란치스코관 일반 공지 board."""

    topic = "dorm_francis_general"

    def __init__(
        self,
        url: str = "https://dorm.catholic.ac.kr/dormitory/board/comm_notice3.do",
    ):
        super().__init__(url)


class DormFrancisCheckinOutAffiliatedNoticeBoardSource(AffiliatedNoticeBoardSourceBase):
    """Parser for the 프란치스코관 입퇴사공지 board."""

    topic = "dorm_francis_checkin_out"

    def __init__(
        self,
        url: str = "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice.do",
    ):
        super().__init__(url)


class CampusLifeOutsideAgenciesNoticeBoardSource(AffiliatedNoticeBoardSourceBase):
    """Parser for the 외부기관공지 board on the campus life site."""

    source_tag = "cuk_campus_life_notices"
    topic = "outside_agencies"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/campuslife/notice_outside.do",
    ):
        super().__init__(url)


class CampusLifeEventsNoticeBoardSource(AffiliatedNoticeBoardSourceBase):
    """Parser for the 행사안내 board on the campus life site."""

    source_tag = "cuk_campus_life_notices"
    topic = "events"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/campuslife/notice_event.do",
    ):
        super().__init__(url)

    def parse_list(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict] = []
        for item in soup.select("li.b-img-con-box"):
            anchor = item.select_one("a[href*='articleNo=']")
            if anchor is None:
                continue
            title_node = item.select_one(".b-img-title")
            date_node = item.select_one(".b-date")
            title_text = (
                title_node.get_text(" ", strip=True)
                if title_node
                else anchor.get_text(" ", strip=True)
            )
            title = _clean_text(title_text)
            article_no = self._extract_article_no(anchor.get("href", ""))
            published_at = self._normalize_date(date_node.get_text() if date_node else "")
            if not article_no or not title:
                continue
            rows.append(
                {
                    "topic": self.topic,
                    "article_no": article_no,
                    "title": title,
                    "published_at": published_at,
                    "source_url": urljoin(self.url, unescape(anchor.get("href", ""))),
                    "source_tag": self.source_tag,
                }
            )
        return rows
