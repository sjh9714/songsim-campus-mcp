from __future__ import annotations

import argparse
import json
import sys

from .db import connection, init_db
from .services import sync_official_snapshot
from .settings import get_settings


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Sync official Songsim campus data into PostgreSQL/PostGIS"
    )
    parser.add_argument("--campus", default=settings.official_campus_id, help="Official campus id")
    parser.add_argument("--year", type=int, default=settings.official_course_year)
    parser.add_argument(
        "--semester",
        type=int,
        choices=[1, 2],
        default=settings.official_course_semester,
    )
    parser.add_argument(
        "--notice-pages",
        type=int,
        default=settings.official_notice_pages,
        help="How many notice list pages to ingest",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="일부 source 가 실패해도 성공으로 끝낸다. 기본값은 하나라도 실패하면 exit 1 이다.",
    )
    args = parser.parse_args()

    init_db()
    # 동기화는 source 별로 격리돼 있어 일부가 실패해도 예외가 올라오지 않는다.
    # 정기 실행에서는 "조용히 안 들어오는 것"이 곧 사고이므로 종료 코드로 드러낸다.
    failed_sources: list[str] = []
    with connection() as conn:
        summary = sync_official_snapshot(
            conn,
            campus=args.campus,
            year=args.year,
            semester=args.semester,
            notice_pages=args.notice_pages,
            failed_sources=failed_sources,
        )
    print(json.dumps(summary, ensure_ascii=False))

    if not failed_sources:
        return

    print(
        f"failed sources ({len(failed_sources)}): {', '.join(failed_sources)}",
        file=sys.stderr,
    )
    if not args.allow_partial:
        raise SystemExit(1)
