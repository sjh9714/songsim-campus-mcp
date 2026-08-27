from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class KakaoPlace:
    name: str
    category: str
    address: str
    latitude: float
    longitude: float
    place_url: str
    place_id: str | None = None


class KakaoLocalClient:
    BASE_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"KakaoAK {self.api_key}"}

    @staticmethod
    def _params(
        query: str,
        *,
        x: float | None = None,
        y: float | None = None,
        radius: int = 1000,
    ) -> dict[str, str | int | float]:
        params: dict[str, str | int | float] = {"query": query, "radius": radius}
        if x is not None and y is not None:
            params.update({"x": x, "y": y})
        return params

    @staticmethod
    def _parse_places(data: dict) -> list[KakaoPlace]:
        places: list[KakaoPlace] = []
        for item in data.get("documents", []):
            places.append(
                KakaoPlace(
                    name=item.get("place_name", ""),
                    category=item.get("category_name", ""),
                    address=item.get("road_address_name") or item.get("address_name", ""),
                    latitude=float(item["y"]),
                    longitude=float(item["x"]),
                    place_id=str(item.get("id") or "") or None,
                    place_url=item.get("place_url", ""),
                )
            )
        return places

    async def search(
        self,
        query: str,
        *,
        x: float | None = None,
        y: float | None = None,
        radius: int = 1000,
    ) -> list[KakaoPlace]:
        params = self._params(query, x=x, y=y, radius=radius)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(self.BASE_URL, headers=self._headers(), params=params)
            response.raise_for_status()
            data = response.json()
        return self._parse_places(data)

    def search_sync(
        self,
        query: str,
        *,
        x: float | None = None,
        y: float | None = None,
        radius: int = 1000,
    ) -> list[KakaoPlace]:
        params = self._params(query, x=x, y=y, radius=radius)
        with httpx.Client(timeout=20) as client:
            response = client.get(self.BASE_URL, headers=self._headers(), params=params)
            response.raise_for_status()
            data = response.json()
        return self._parse_places(data)


def extract_kakao_place_id(place_url: str) -> str | None:
    match = re.search(r"/(\d+)(?:[/?#]|$)", place_url.strip())
    return match.group(1) if match else None


def parse_place_detail_opening_hours(payload: dict[str, Any]) -> dict[str, str]:
    open_hours = payload.get("open_hours")
    if not isinstance(open_hours, dict):
        return {}

    all_hours = open_hours.get("all")
    periods = all_hours.get("periods") if isinstance(all_hours, dict) else None
    if not isinstance(periods, list):
        week_from_today = open_hours.get("week_from_today")
        periods = (
            week_from_today.get("week_periods")
            if isinstance(week_from_today, dict)
            else None
        )
    if not isinstance(periods, list):
        return {}

    day_keys = {
        "월": "mon",
        "화": "tue",
        "수": "wed",
        "목": "thu",
        "금": "fri",
        "토": "sat",
        "일": "sun",
    }
    normalized: dict[str, str] = {}
    for period in periods:
        if not isinstance(period, dict):
            continue
        title = str(period.get("period_title") or "").replace(" ", "")
        suffix = ""
        if "브레이크" in title:
            suffix = "_break"
        elif "라스트오더" in title or "마감주문" in title:
            suffix = "_last_order"
        days = period.get("days")
        if not isinstance(days, list):
            continue
        for day in days:
            if not isinstance(day, dict):
                continue
            day_label = str(
                day.get("day_of_the_week") or day.get("day_of_the_week_desc") or ""
            ).strip()
            day_match = re.match(r"([월화수목금토일])", day_label)
            day_key = day_keys.get(day_match.group(1) if day_match else "")
            if not day_key:
                continue
            on_days = day.get("on_days")
            if isinstance(on_days, dict):
                text = str(on_days.get("start_end_time_desc") or "").strip()
                if text:
                    normalized[f"{day_key}{suffix}"] = text
                    continue
            off_desc = str(day.get("off_days_desc") or "").strip()
            if off_desc:
                normalized[f"{day_key}{suffix}"] = "휴무"

    holiday_notice = (
        str(all_hours.get("all_days_off_info") or "").strip()
        if isinstance(all_hours, dict)
        else ""
    )
    if holiday_notice:
        normalized["holiday_notice"] = holiday_notice
    return normalized


class KakaoPlaceDetailClient:
    BASE_URL = "https://place-api.map.kakao.com/places/panel3/{place_id}"

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://place.map.kakao.com/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
            "appversion": "6.6.0",
            "pf": "PC",
        }

    def fetch_sync(self, place_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=20) as client:
            response = client.get(
                self.BASE_URL.format(place_id=place_id),
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()
