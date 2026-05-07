from __future__ import annotations

from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

JSON_COLUMNS = {
    "places": {"aliases_json": "aliases", "opening_hours_json": "opening_hours"},
    "restaurants": {"tags_json": "tags"},
    "restaurant_cache_items": {"tags_json": "tags"},
    "restaurant_hours_cache": {
        "raw_payload_json": "raw_payload",
        "opening_hours_json": "opening_hours",
    },
    "notices": {"labels_json": "labels"},
    "affiliated_notices": {},
    "campus_life_notices": {},
    "transport_guides": {"steps_json": "steps"},
    "certificate_guides": {"steps_json": "steps"},
    "leave_of_absence_guides": {"steps_json": "steps", "links_json": "links"},
    "scholarship_guides": {"steps_json": "steps", "links_json": "links"},
    "wifi_guides": {"ssids_json": "ssids", "steps_json": "steps"},
    "academic_support_guides": {"steps_json": "steps", "contacts_json": "contacts"},
    "academic_status_guides": {"steps_json": "steps", "links_json": "links"},
    "registration_guides": {"steps_json": "steps", "links_json": "links"},
    "class_guides": {"steps_json": "steps", "links_json": "links"},
    "seasonal_semester_guides": {"steps_json": "steps", "links_json": "links"},
    "academic_milestone_guides": {"steps_json": "steps", "links_json": "links"},
    "student_exchange_guides": {"steps_json": "steps", "links_json": "links"},
    "student_exchange_partners": {},
    "dormitory_guides": {"steps_json": "steps", "links_json": "links"},
    "campus_life_support_guides": {"steps_json": "steps", "links_json": "links"},
    "about_resource_guides": {"steps_json": "steps", "links_json": "links"},
    "service_policy_guides": {"steps_json": "steps", "links_json": "links"},
    "pc_software_entries": {"software_list_json": "software_list"},
    "academic_calendar": {"campuses_json": "campuses"},
    "profile_notice_preferences": {
        "categories_json": "categories",
        "keywords_json": "keywords",
    },
    "profile_interests": {"tags_json": "tags"},
    "sync_runs": {
        "params_json": "params",
        "summary_json": "summary",
    },
}

JSON_DEFAULTS = {
    "aliases_json": [],
    "opening_hours_json": {},
    "tags_json": [],
    "raw_payload_json": {},
    "labels_json": [],
    "steps_json": [],
    "links_json": [],
    "contacts_json": [],
    "software_list_json": [],
    "ssids_json": [],
    "campuses_json": [],
    "categories_json": [],
    "keywords_json": [],
    "params_json": {},
    "summary_json": {},
}


def _executemany(
    conn: psycopg.Connection,
    query: str,
    params_seq: list[tuple[Any, ...]],
) -> None:
    if not params_seq:
        return
    with conn.cursor() as cursor:
        cursor.executemany(query, params_seq)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _normalize_record(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalize_value(value) for key, value in data.items()}


def _row_to_dict(table: str, row: dict[str, Any]) -> dict[str, Any]:
    data = _normalize_record(dict(row))
    for db_key, public_key in JSON_COLUMNS.get(table, {}).items():
        data[public_key] = data.pop(db_key, JSON_DEFAULTS[db_key]) or JSON_DEFAULTS[db_key]
    return data


def count_rows(conn: psycopg.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS value FROM {table}").fetchone()
    return int(row["value"] or 0)


def replace_places(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE places RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO places (
            slug, name, category, aliases_json, description,
            latitude, longitude, opening_hours_json, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["slug"],
                row["name"],
                row["category"],
                Jsonb(row.get("aliases", [])),
                row.get("description", ""),
                row.get("latitude"),
                row.get("longitude"),
                Jsonb(row.get("opening_hours", {})),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_courses(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE courses RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO courses (
            year, semester, code, title, professor, department, section,
            day_of_week, period_start, period_end, room, raw_schedule,
            source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["year"],
                row["semester"],
                row["code"],
                row["title"],
                row.get("professor"),
                row.get("department"),
                row.get("section"),
                row.get("day_of_week"),
                row.get("period_start"),
                row.get("period_end"),
                row.get("room"),
                row.get("raw_schedule"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_restaurants(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE restaurants RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO restaurants (
            slug, name, category, min_price, max_price, latitude,
            longitude, tags_json, description, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["slug"],
                row["name"],
                row["category"],
                row.get("min_price"),
                row.get("max_price"),
                row.get("latitude"),
                row.get("longitude"),
                Jsonb(row.get("tags", [])),
                row.get("description", ""),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_notices(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE notices RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO notices (
            title, category, published_at, summary, labels_json,
            source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["title"],
                row["category"],
                row["published_at"],
                row.get("summary", ""),
                Jsonb(row.get("labels", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_affiliated_notices(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE affiliated_notices RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO affiliated_notices (
            topic, title, published_at, summary, body_text, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row["published_at"],
                row.get("summary", ""),
                row.get("body_text", ""),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def search_places(
    conn: psycopg.Connection,
    query: str = "",
    category: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    normalized = f"%{query.strip()}%"
    sql = """
        SELECT * FROM places
        WHERE (
            %s = '%%'
            OR name ILIKE %s
            OR aliases_json::text ILIKE %s
            OR description ILIKE %s
        )
    """
    params: list[Any] = [normalized, normalized, normalized, normalized]
    if category:
        sql += " AND category = %s"
        params.append(category)
    sql += " ORDER BY name LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("places", row) for row in rows]


def list_places(conn: psycopg.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM places ORDER BY name").fetchall()
    return [_row_to_dict("places", row) for row in rows]


def get_place_by_slug_or_name(
    conn: psycopg.Connection,
    identifier: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM places WHERE slug = %s OR name = %s",
        (identifier, identifier),
    ).fetchone()
    return _row_to_dict("places", row) if row else None


def get_place_by_slug(conn: psycopg.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM places WHERE slug = %s",
        (slug,),
    ).fetchone()
    return _row_to_dict("places", row) if row else None


def list_places_by_exact_name(conn: psycopg.Connection, name: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM places WHERE name = %s ORDER BY name",
        (name,),
    ).fetchall()
    return [_row_to_dict("places", row) for row in rows]


def list_places_by_exact_alias(conn: psycopg.Connection, alias: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM places
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(aliases_json) AS alias_item(value)
            WHERE alias_item.value = %s
        )
        ORDER BY name
        """,
        (alias,),
    ).fetchall()
    return [_row_to_dict("places", row) for row in rows]


def update_place_opening_hours(
    conn: psycopg.Connection,
    slug: str,
    opening_hours: dict[str, str],
    *,
    last_synced_at: str,
) -> None:
    row = conn.execute(
        "SELECT opening_hours_json FROM places WHERE slug = %s",
        (slug,),
    ).fetchone()
    if not row:
        return
    merged = dict(row["opening_hours_json"] or {})
    merged.update(opening_hours)
    conn.execute(
        """
        UPDATE places
        SET opening_hours_json = %s, last_synced_at = %s
        WHERE slug = %s
        """,
        (Jsonb(merged), last_synced_at, slug),
    )


def search_courses(
    conn: psycopg.Connection,
    query: str = "",
    *,
    year: int | None = None,
    semester: int | None = None,
    period_start: int | None = None,
    limit: int | None = 20,
) -> list[dict[str, Any]]:
    normalized = f"%{query.strip()}%"
    sql = """
        SELECT * FROM courses
        WHERE (
            %s = '%%'
            OR title ILIKE %s
            OR code ILIKE %s
            OR COALESCE(professor, '') ILIKE %s
        )
    """
    params: list[Any] = [normalized, normalized, normalized, normalized]
    if year is not None:
        sql += " AND year = %s"
        params.append(year)
    if semester is not None:
        sql += " AND semester = %s"
        params.append(semester)
    if period_start is not None:
        sql += " AND period_start = %s"
        params.append(period_start)
    sql += " ORDER BY year DESC, semester DESC, title, code, section"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_normalize_record(dict(row)) for row in rows]


def list_courses_snapshot(
    conn: psycopg.Connection,
    *,
    year: int | None = None,
    semester: int | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM courses WHERE 1=1"
    params: list[Any] = []
    if year is not None:
        sql += " AND year = %s"
        params.append(year)
    if semester is not None:
        sql += " AND semester = %s"
        params.append(semester)
    sql += " ORDER BY year DESC, semester DESC, title, code, section"
    rows = conn.execute(sql, params).fetchall()
    return [_normalize_record(dict(row)) for row in rows]


def list_courses_with_rooms(
    conn: psycopg.Connection,
    *,
    year: int,
    semester: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM courses
        WHERE year = %s
          AND semester = %s
          AND room IS NOT NULL
          AND BTRIM(room) <> ''
        ORDER BY room, day_of_week, period_start, title, code, section
        """,
        (year, semester),
    ).fetchall()
    return [_normalize_record(dict(row)) for row in rows]


def list_restaurants(conn: psycopg.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM restaurants ORDER BY name").fetchall()
    return [_row_to_dict("restaurants", row) for row in rows]


def list_restaurants_nearby(
    conn: psycopg.Connection,
    *,
    latitude: float,
    longitude: float,
    radius_meters: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            *,
            CAST(
                ST_Distance(
                    geom,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) AS INTEGER
            ) AS distance_meters
        FROM restaurants
        WHERE geom IS NOT NULL
          AND ST_DWithin(
                geom,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
            )
        ORDER BY distance_meters, name
        """,
        (longitude, latitude, longitude, latitude, radius_meters),
    ).fetchall()
    return [_row_to_dict("restaurants", row) for row in rows]


def replace_restaurant_cache_snapshot(
    conn: psycopg.Connection,
    *,
    origin_slug: str,
    kakao_query: str,
    radius_meters: int,
    fetched_at: str,
    rows: list[dict[str, Any]],
) -> int:
    snapshot_rows = conn.execute(
        """
        SELECT id FROM restaurant_cache_snapshots
        WHERE origin_slug = %s AND kakao_query = %s AND radius_meters = %s
        """,
        (origin_slug, kakao_query, radius_meters),
    ).fetchall()
    snapshot_ids = [row["id"] for row in snapshot_rows]
    if snapshot_ids:
        conn.execute(
            "DELETE FROM restaurant_cache_items WHERE snapshot_id = ANY(%s)",
            (snapshot_ids,),
        )
        conn.execute(
            "DELETE FROM restaurant_cache_snapshots WHERE id = ANY(%s)",
            (snapshot_ids,),
        )

    snapshot_row = conn.execute(
        """
        INSERT INTO restaurant_cache_snapshots (
            origin_slug, kakao_query, radius_meters, fetched_at, source_tag
        ) VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (origin_slug, kakao_query, radius_meters, fetched_at, "kakao_local_cache"),
    ).fetchone()
    snapshot_id = int(snapshot_row["id"])
    _executemany(
        conn,
        """
        INSERT INTO restaurant_cache_items (
            snapshot_id, item_order, restaurant_id, slug, name, category,
            min_price, max_price, latitude, longitude, kakao_place_id,
            source_url, tags_json, description, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                snapshot_id,
                index,
                row["id"],
                row["slug"],
                row["name"],
                row["category"],
                row.get("min_price"),
                row.get("max_price"),
                row.get("latitude"),
                row.get("longitude"),
                row.get("kakao_place_id"),
                row.get("source_url"),
                Jsonb(row.get("tags", [])),
                row.get("description", ""),
                row.get("source_tag", "kakao_local_cache"),
                row["last_synced_at"],
            )
            for index, row in enumerate(rows, start=1)
        ],
    )
    return snapshot_id


def get_restaurant_cache_snapshot(
    conn: psycopg.Connection,
    *,
    origin_slug: str,
    kakao_query: str,
    radius_meters: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM restaurant_cache_snapshots
        WHERE origin_slug = %s AND kakao_query = %s AND radius_meters = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (origin_slug, kakao_query, radius_meters),
    ).fetchone()
    return _normalize_record(dict(row)) if row else None


def list_restaurant_cache_items(
    conn: psycopg.Connection,
    snapshot_id: int,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: int | None = None,
) -> list[dict[str, Any]]:
    if latitude is not None and longitude is not None and radius_meters is not None:
        rows = conn.execute(
            """
            SELECT
                restaurant_id AS id,
                slug,
                name,
                category,
                min_price,
                max_price,
                latitude,
                longitude,
                kakao_place_id,
                source_url,
                tags_json,
                description,
                source_tag,
                last_synced_at,
                CAST(
                    ST_Distance(
                        geom,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) AS INTEGER
                ) AS distance_meters
            FROM restaurant_cache_items
            WHERE snapshot_id = %s
              AND geom IS NOT NULL
              AND ST_DWithin(
                    geom,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
            ORDER BY item_order
            """,
            (longitude, latitude, snapshot_id, longitude, latitude, radius_meters),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                restaurant_id AS id,
                slug,
                name,
                category,
                min_price,
                max_price,
                latitude,
                longitude,
                kakao_place_id,
                source_url,
                tags_json,
                description,
                source_tag,
                last_synced_at
            FROM restaurant_cache_items
            WHERE snapshot_id = %s
            ORDER BY item_order
            """,
            (snapshot_id,),
        ).fetchall()
    return [_row_to_dict("restaurant_cache_items", row) for row in rows]


def get_restaurant_hours_cache(
    conn: psycopg.Connection,
    *,
    kakao_place_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM restaurant_hours_cache
        WHERE kakao_place_id = %s
        LIMIT 1
        """,
        (kakao_place_id,),
    ).fetchone()
    return _row_to_dict("restaurant_hours_cache", row) if row else None


def upsert_restaurant_hours_cache(
    conn: psycopg.Connection,
    *,
    kakao_place_id: str,
    source_url: str | None,
    raw_payload: dict[str, Any],
    opening_hours: dict[str, str],
    fetched_at: str,
    source_tag: str = "kakao_place_detail_cache",
) -> None:
    conn.execute(
        """
        INSERT INTO restaurant_hours_cache (
            kakao_place_id, source_url, raw_payload_json,
            opening_hours_json, fetched_at, source_tag
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (kakao_place_id) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            raw_payload_json = EXCLUDED.raw_payload_json,
            opening_hours_json = EXCLUDED.opening_hours_json,
            fetched_at = EXCLUDED.fetched_at,
            source_tag = EXCLUDED.source_tag
        """,
        (
            kakao_place_id,
            source_url,
            Jsonb(raw_payload),
            Jsonb(opening_hours),
            fetched_at,
            source_tag,
        ),
    )


def list_notices(
    conn: psycopg.Connection,
    category: str | list[str] | tuple[str, ...] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM notices"
    params: list[Any] = []
    if category:
        if isinstance(category, (list, tuple)):
            sql += " WHERE category = ANY(%s)"
            params.append(list(category))
        else:
            sql += " WHERE category = %s"
            params.append(category)
    sql += " ORDER BY published_at DESC, id DESC LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("notices", row) for row in rows]


def list_affiliated_notices(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM affiliated_notices"
    params: list[Any] = []
    clauses: list[str] = []
    if topic:
        clauses.append("topic = %s")
        params.append(topic)

    normalized_query = (query or "").strip()
    query_like = f"%{normalized_query}%"
    if normalized_query:
        clauses.append("(title ILIKE %s OR summary ILIKE %s OR body_text ILIKE %s)")
        params.extend([query_like, query_like, query_like])

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    if normalized_query:
        sql += """
            ORDER BY
                CASE
                    WHEN title ILIKE %s THEN 0
                    WHEN summary ILIKE %s THEN 1
                    WHEN body_text ILIKE %s THEN 2
                    ELSE 3
                END,
                published_at DESC,
                id DESC
            LIMIT %s
        """
        params.extend([query_like, query_like, query_like, limit])
    else:
        sql += " ORDER BY published_at DESC, id DESC LIMIT %s"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("affiliated_notices", row) for row in rows]


def replace_campus_life_notices(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE campus_life_notices RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO campus_life_notices (
            topic, title, published_at, summary, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row["published_at"],
                row.get("summary", ""),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def list_campus_life_notices(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM campus_life_notices"
    params: list[Any] = []
    clauses: list[str] = []
    if topic:
        clauses.append("topic = %s")
        params.append(topic)

    normalized_query = (query or "").strip()
    query_like = f"%{normalized_query}%"
    if normalized_query:
        clauses.append("(title ILIKE %s OR summary ILIKE %s)")
        params.extend([query_like, query_like])

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    if normalized_query:
        sql += """
            ORDER BY
                CASE
                    WHEN title ILIKE %s THEN 0
                    WHEN summary ILIKE %s THEN 1
                    ELSE 2
                END,
                published_at DESC,
                id DESC
            LIMIT %s
        """
        params.extend([query_like, query_like, limit])
    else:
        sql += " ORDER BY published_at DESC, id DESC LIMIT %s"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("campus_life_notices", row) for row in rows]


def replace_transport_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE transport_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO transport_guides (
            mode, title, summary, steps_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["mode"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_certificate_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE certificate_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO certificate_guides (
            title, summary, steps_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_leave_of_absence_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE leave_of_absence_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO leave_of_absence_guides (
            title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_scholarship_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE scholarship_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO scholarship_guides (
            title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_wifi_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE wifi_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO wifi_guides (
            building_name, ssids_json, steps_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["building_name"],
                Jsonb(row.get("ssids", [])),
                Jsonb(row.get("steps", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_academic_support_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE academic_support_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO academic_support_guides (
            title, summary, steps_json, contacts_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("contacts", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_academic_status_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE academic_status_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO academic_status_guides (
            status, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["status"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_registration_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE registration_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO registration_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_class_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE class_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO class_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_seasonal_semester_guides(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE seasonal_semester_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO seasonal_semester_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_academic_milestone_guides(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE academic_milestone_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO academic_milestone_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_student_exchange_guides(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE student_exchange_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO student_exchange_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_student_activity_guides(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE student_activity_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO student_activity_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_student_activity_notices(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE student_activity_notices RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO student_activity_notices (
            topic, article_no, title, published_at, summary, body_text,
            source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row.get("article_no"),
                row["title"],
                row.get("published_at"),
                row.get("summary", ""),
                row.get("body_text", ""),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_about_resource_guides(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE about_resource_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO about_resource_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_service_policy_guides(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE service_policy_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO service_policy_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_newsroom_posts(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE newsroom_posts RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO newsroom_posts (
            topic, article_no, title, published_at, summary, thumbnail_url,
            external_url, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row.get("article_no"),
                row["title"],
                row.get("published_at"),
                row.get("summary", ""),
                row.get("thumbnail_url"),
                row.get("external_url"),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_student_exchange_partners(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE student_exchange_partners RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO student_exchange_partners (
            partner_code, university_name, country_ko, country_en, continent,
            location, agreement_date, homepage_url, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["partner_code"],
                row["university_name"],
                row.get("country_ko"),
                row.get("country_en"),
                row.get("continent"),
                row.get("location"),
                row.get("agreement_date"),
                row.get("homepage_url"),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_dormitory_guides(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE dormitory_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO dormitory_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_phone_book_entries(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE phone_book_entries RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO phone_book_entries (
            department, tasks, phone, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["department"],
                row["tasks"],
                row["phone"],
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_campus_life_support_guides(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE campus_life_support_guides RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO campus_life_support_guides (
            topic, title, summary, steps_json, links_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["topic"],
                row["title"],
                row.get("summary", ""),
                Jsonb(row.get("steps", [])),
                Jsonb(row.get("links", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_pc_software_entries(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE pc_software_entries RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO pc_software_entries (
            room, pc_count, software_list_json, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["room"],
                row.get("pc_count"),
                Jsonb(row.get("software_list", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_academic_calendar(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE academic_calendar RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO academic_calendar (
            academic_year, title, start_date, end_date, campuses_json,
            source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["academic_year"],
                row["title"],
                row["start_date"],
                row["end_date"],
                Jsonb(row.get("campuses", [])),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_campus_dining_menus(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE campus_dining_menus")
    _executemany(
        conn,
        """
        INSERT INTO campus_dining_menus (
            venue_slug, venue_name, place_slug, place_name, week_label,
            week_start, week_end, menu_text, source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["venue_slug"],
                row["venue_name"],
                row.get("place_slug"),
                row.get("place_name"),
                row.get("week_label"),
                row.get("week_start"),
                row.get("week_end"),
                row.get("menu_text"),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def replace_campus_facilities(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute("TRUNCATE TABLE campus_facilities RESTART IDENTITY CASCADE")
    _executemany(
        conn,
        """
        INSERT INTO campus_facilities (
            facility_name, category, phone, location_text, hours_text, place_slug,
            source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["facility_name"],
                row.get("category"),
                row.get("phone"),
                row.get("location_text"),
                row.get("hours_text"),
                row.get("place_slug"),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def list_campus_dining_menus(
    conn: psycopg.Connection,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM campus_dining_menus
        ORDER BY venue_name, venue_slug
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_normalize_record(dict(row)) for row in rows]


def replace_library_seat_status_cache(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    conn.execute("TRUNCATE TABLE library_seat_status_cache")
    _executemany(
        conn,
        """
        INSERT INTO library_seat_status_cache (
            room_name, remaining_seats, occupied_seats, total_seats,
            source_url, source_tag, last_synced_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                row["room_name"],
                row.get("remaining_seats"),
                row.get("occupied_seats"),
                row.get("total_seats"),
                row.get("source_url"),
                row.get("source_tag", "demo"),
                row["last_synced_at"],
            )
            for row in rows
        ],
    )


def list_library_seat_status_cache(conn: psycopg.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM library_seat_status_cache
        ORDER BY room_name
        """
    ).fetchall()
    return [_normalize_record(dict(row)) for row in rows]


def list_transport_guides(
    conn: psycopg.Connection,
    mode: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM transport_guides"
    params: list[Any] = []
    if mode:
        sql += " WHERE mode = %s"
        params.append(mode)
    sql += " ORDER BY mode, title LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("transport_guides", row) for row in rows]


def list_certificate_guides(
    conn: psycopg.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM certificate_guides
        ORDER BY id, title
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("certificate_guides", row) for row in rows]


def list_leave_of_absence_guides(
    conn: psycopg.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM leave_of_absence_guides
        ORDER BY id, title
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("leave_of_absence_guides", row) for row in rows]


def list_academic_calendar(
    conn: psycopg.Connection,
    *,
    academic_year: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    query: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM academic_calendar
    """
    clauses: list[str] = []
    params: list[Any] = []
    if academic_year is not None:
        clauses.append("academic_year = %s")
        params.append(academic_year)
    if start_date is not None:
        clauses.append("end_date >= %s")
        params.append(start_date)
    if end_date is not None:
        clauses.append("start_date <= %s")
        params.append(end_date)
    if query:
        clauses.append("title ILIKE %s")
        params.append(f"%{query}%")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY start_date, end_date, title, id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("academic_calendar", row) for row in rows]


def list_scholarship_guides(
    conn: psycopg.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM scholarship_guides
        ORDER BY id, title
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("scholarship_guides", row) for row in rows]


def list_wifi_guides(
    conn: psycopg.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM wifi_guides
        ORDER BY id, building_name
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("wifi_guides", row) for row in rows]


def list_academic_support_guides(
    conn: psycopg.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM academic_support_guides
        ORDER BY id, title
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("academic_support_guides", row) for row in rows]


def list_academic_status_guides(
    conn: psycopg.Connection,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM academic_status_guides
    """
    params: list[Any] = []
    if status:
        sql += " WHERE status = %s"
        params.append(status)
    sql += " ORDER BY id, title LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("academic_status_guides", row) for row in rows]


def list_registration_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM registration_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY id, title LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("registration_guides", row) for row in rows]


def list_class_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM class_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY id, title LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("class_guides", row) for row in rows]


def list_seasonal_semester_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM seasonal_semester_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY id, title LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("seasonal_semester_guides", row) for row in rows]


def list_academic_milestone_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM academic_milestone_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY id, title LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("academic_milestone_guides", row) for row in rows]


def list_student_exchange_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM student_exchange_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY id, title LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("student_exchange_guides", row) for row in rows]


def list_student_activity_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM student_activity_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY topic, title, id LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("student_activity_guides", row) for row in rows]


def list_student_activity_notices(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM student_activity_notices
    """
    clauses: list[str] = []
    params: list[Any] = []
    if topic:
        clauses.append("topic = %s")
        params.append(topic)
    if query:
        clauses.append("(title ILIKE %s OR summary ILIKE %s OR body_text ILIKE %s)")
        pattern = f"%{query}%"
        params.extend([pattern, pattern, pattern])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY published_at DESC NULLS LAST, id DESC LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("student_activity_notices", row) for row in rows]


def list_about_resource_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM about_resource_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY topic, title, id LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("about_resource_guides", row) for row in rows]


def list_service_policy_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM service_policy_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY topic, title, id LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("service_policy_guides", row) for row in rows]


def list_newsroom_posts(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM newsroom_posts
    """
    clauses: list[str] = []
    params: list[Any] = []
    if topic:
        clauses.append("topic = %s")
        params.append(topic)
    if query:
        clauses.append("(title ILIKE %s OR summary ILIKE %s)")
        pattern = f"%{query}%"
        params.extend([pattern, pattern])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY published_at DESC NULLS LAST, id LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("newsroom_posts", row) for row in rows]


def list_student_exchange_partners(
    conn: psycopg.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM student_exchange_partners
        ORDER BY
            country_ko IS NULL,
            convert_to(COALESCE(country_ko, ''), 'UTF8'),
            convert_to(university_name, 'UTF8'),
            partner_code,
            id
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("student_exchange_partners", row) for row in rows]


def list_dormitory_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM dormitory_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY id, title LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("dormitory_guides", row) for row in rows]


def list_phone_book_entries(
    conn: psycopg.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM phone_book_entries
        ORDER BY convert_to(department, 'UTF8'), id
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("phone_book_entries", row) for row in rows]


def list_campus_life_support_guides(
    conn: psycopg.Connection,
    *,
    topic: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM campus_life_support_guides
    """
    params: list[Any] = []
    if topic:
        sql += " WHERE topic = %s"
        params.append(topic)
    sql += " ORDER BY topic, title, id LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("campus_life_support_guides", row) for row in rows]


def list_pc_software_entries(
    conn: psycopg.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM pc_software_entries
        ORDER BY room, id
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("pc_software_entries", row) for row in rows]


def list_campus_facilities(
    conn: psycopg.Connection,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM campus_facilities
        ORDER BY id, facility_name
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("campus_facilities", row) for row in rows]


def create_sync_run(
    conn: psycopg.Connection,
    *,
    target: str,
    status: str,
    trigger: str = "manual",
    params: dict[str, Any],
    summary: dict[str, Any],
    error_text: str | None,
    started_at: str,
    finished_at: str | None = None,
) -> int:
    row = conn.execute(
        """
        INSERT INTO sync_runs (
            target, trigger, status, params_json, summary_json, error_text, started_at, finished_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            target,
            trigger,
            status,
            Jsonb(params),
            Jsonb(summary),
            error_text,
            started_at,
            finished_at,
        ),
    ).fetchone()
    return int(row["id"])


def update_sync_run(
    conn: psycopg.Connection,
    run_id: int,
    *,
    status: str,
    summary: dict[str, Any],
    error_text: str | None,
    finished_at: str | None,
) -> None:
    conn.execute(
        """
        UPDATE sync_runs
        SET status = %s, summary_json = %s, error_text = %s, finished_at = %s
        WHERE id = %s
        """,
        (status, Jsonb(summary), error_text, finished_at, run_id),
    )


def get_sync_run(conn: psycopg.Connection, run_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM sync_runs WHERE id = %s", (run_id,)).fetchone()
    return _row_to_dict("sync_runs", row) if row else None


def list_sync_runs(conn: psycopg.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM sync_runs
        ORDER BY started_at DESC, id DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_to_dict("sync_runs", row) for row in rows]


def find_sync_runs(
    conn: psycopg.Connection,
    *,
    target: str | None = None,
    trigger: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM sync_runs"
    params: list[Any] = []
    clauses: list[str] = []
    if target is not None:
        clauses.append("target = %s")
        params.append(target)
    if trigger is not None:
        clauses.append("trigger = %s")
        params.append(trigger)
    if status is not None:
        clauses.append("status = %s")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY started_at DESC, id DESC LIMIT %s"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict("sync_runs", row) for row in rows]


def get_latest_sync_run(
    conn: psycopg.Connection,
    *,
    target: str,
    trigger: str,
    status: str | None = None,
) -> dict[str, Any] | None:
    rows = find_sync_runs(conn, target=target, trigger=trigger, status=status, limit=1)
    return rows[0] if rows else None


def get_dataset_sync_state(conn: psycopg.Connection, table: str) -> dict[str, Any]:
    allowed = {
        "places",
        "courses",
        "notices",
        "transport_guides",
        "certificate_guides",
        "leave_of_absence_guides",
        "scholarship_guides",
        "wifi_guides",
        "academic_support_guides",
        "academic_status_guides",
        "registration_guides",
        "class_guides",
        "seasonal_semester_guides",
        "academic_milestone_guides",
        "campus_life_support_guides",
        "student_activity_guides",
        "student_activity_notices",
        "about_resource_guides",
        "service_policy_guides",
        "newsroom_posts",
        "pc_software_entries",
        "student_exchange_guides",
        "student_exchange_partners",
        "dormitory_guides",
        "phone_book_entries",
        "affiliated_notices",
        "campus_life_notices",
        "academic_calendar",
        "campus_dining_menus",
        "campus_facilities",
    }
    if table not in allowed:
        raise ValueError(f"Unsupported dataset table: {table}")
    row = conn.execute(
        f"SELECT COUNT(*) AS row_count, MAX(last_synced_at) AS last_synced_at FROM {table}"
    ).fetchone()
    data = _normalize_record(dict(row))
    return {
        "name": table,
        "row_count": int(data["row_count"] or 0),
        "last_synced_at": data["last_synced_at"],
    }


def try_advisory_lock(conn: psycopg.Connection, key: int) -> bool:
    row = conn.execute("SELECT pg_try_advisory_lock(%s) AS locked", (key,)).fetchone()
    return bool(row["locked"])


def release_advisory_lock(conn: psycopg.Connection, key: int) -> bool:
    row = conn.execute("SELECT pg_advisory_unlock(%s) AS unlocked", (key,)).fetchone()
    return bool(row["unlocked"])


def delete_stale_restaurant_cache_snapshots(
    conn: psycopg.Connection,
    *,
    older_than: str,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT id FROM restaurant_cache_snapshots
        WHERE fetched_at < %s
        """,
        (older_than,),
    ).fetchall()
    snapshot_ids = [int(row["id"]) for row in rows]
    if not snapshot_ids:
        return {
            "restaurant_cache_snapshots_deleted": 0,
            "restaurant_cache_items_deleted": 0,
        }
    item_row = conn.execute(
        """
        SELECT COUNT(*) AS value
        FROM restaurant_cache_items
        WHERE snapshot_id = ANY(%s)
        """,
        (snapshot_ids,),
    ).fetchone()
    conn.execute(
        "DELETE FROM restaurant_cache_snapshots WHERE id = ANY(%s)",
        (snapshot_ids,),
    )
    return {
        "restaurant_cache_snapshots_deleted": len(snapshot_ids),
        "restaurant_cache_items_deleted": int(item_row["value"] or 0),
    }


def delete_stale_restaurant_hours_cache(
    conn: psycopg.Connection,
    *,
    older_than: str,
) -> int:
    row = conn.execute(
        """
        WITH deleted AS (
            DELETE FROM restaurant_hours_cache
            WHERE fetched_at < %s
            RETURNING 1
        )
        SELECT COUNT(*) AS value FROM deleted
        """,
        (older_than,),
    ).fetchone()
    return int(row["value"] or 0)


def create_profile(
    conn: psycopg.Connection,
    *,
    profile_id: str,
    display_name: str,
    created_at: str,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO profiles (id, display_name, created_at, updated_at)
        VALUES (%s, %s, %s, %s)
        """,
        (profile_id, display_name, created_at, updated_at),
    )


def get_profile(conn: psycopg.Connection, profile_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM profiles WHERE id = %s", (profile_id,)).fetchone()
    return _normalize_record(dict(row)) if row else None


def update_profile(
    conn: psycopg.Connection,
    profile_id: str,
    *,
    display_name: str | None = None,
    department: str | None = None,
    student_year: int | None = None,
    admission_type: str | None = None,
    updated_at: str,
    fields: set[str],
) -> None:
    assignments: list[str] = []
    params: list[Any] = []
    values = {
        "display_name": display_name,
        "department": department,
        "student_year": student_year,
        "admission_type": admission_type,
    }
    for field in ("display_name", "department", "student_year", "admission_type"):
        if field not in fields:
            continue
        assignments.append(f"{field} = %s")
        params.append(values[field])
    if not assignments:
        return
    assignments.append("updated_at = %s")
    params.extend([updated_at, profile_id])
    conn.execute(
        f"UPDATE profiles SET {', '.join(assignments)} WHERE id = %s",
        params,
    )


def replace_profile_courses(
    conn: psycopg.Connection,
    profile_id: str,
    rows: list[dict[str, Any]],
    *,
    updated_at: str,
) -> None:
    conn.execute("DELETE FROM profile_courses WHERE profile_id = %s", (profile_id,))
    _executemany(
        conn,
        """
        INSERT INTO profile_courses (
            profile_id, year, semester, code, section, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [
            (
                profile_id,
                row["year"],
                row["semester"],
                row["code"],
                row["section"],
                row.get("created_at", updated_at),
            )
            for row in rows
        ],
    )
    conn.execute(
        "UPDATE profiles SET updated_at = %s WHERE id = %s",
        (updated_at, profile_id),
    )


def list_profile_courses(
    conn: psycopg.Connection,
    profile_id: str,
    *,
    year: int | None = None,
    semester: int | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM profile_courses WHERE profile_id = %s"
    params: list[Any] = [profile_id]
    if year is not None:
        sql += " AND year = %s"
        params.append(year)
    if semester is not None:
        sql += " AND semester = %s"
        params.append(semester)
    sql += " ORDER BY year DESC, semester DESC, code, section"
    rows = conn.execute(sql, params).fetchall()
    return [_normalize_record(dict(row)) for row in rows]


def get_course_by_key(
    conn: psycopg.Connection,
    *,
    year: int,
    semester: int,
    code: str,
    section: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM courses
        WHERE year = %s AND semester = %s AND code = %s AND COALESCE(section, '') = %s
        """,
        (year, semester, code, section),
    ).fetchone()
    return _normalize_record(dict(row)) if row else None


def save_profile_notice_preferences(
    conn: psycopg.Connection,
    profile_id: str,
    *,
    categories: list[str],
    keywords: list[str],
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO profile_notice_preferences (
            profile_id, categories_json, keywords_json, updated_at
        ) VALUES (%s, %s, %s, %s)
        ON CONFLICT(profile_id) DO UPDATE SET
            categories_json = EXCLUDED.categories_json,
            keywords_json = EXCLUDED.keywords_json,
            updated_at = EXCLUDED.updated_at
        """,
        (profile_id, Jsonb(categories), Jsonb(keywords), updated_at),
    )
    conn.execute(
        "UPDATE profiles SET updated_at = %s WHERE id = %s",
        (updated_at, profile_id),
    )


def get_profile_notice_preferences(
    conn: psycopg.Connection,
    profile_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM profile_notice_preferences WHERE profile_id = %s",
        (profile_id,),
    ).fetchone()
    return _row_to_dict("profile_notice_preferences", row) if row else None


def save_profile_interests(
    conn: psycopg.Connection,
    profile_id: str,
    *,
    tags: list[str],
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO profile_interests (profile_id, tags_json, updated_at)
        VALUES (%s, %s, %s)
        ON CONFLICT(profile_id) DO UPDATE SET
            tags_json = EXCLUDED.tags_json,
            updated_at = EXCLUDED.updated_at
        """,
        (profile_id, Jsonb(tags), updated_at),
    )
    conn.execute(
        "UPDATE profiles SET updated_at = %s WHERE id = %s",
        (updated_at, profile_id),
    )


def get_profile_interests(
    conn: psycopg.Connection,
    profile_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM profile_interests WHERE profile_id = %s",
        (profile_id,),
    ).fetchone()
    return _row_to_dict("profile_interests", row) if row else None
