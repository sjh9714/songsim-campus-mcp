from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Literal, TypedDict

from . import clock, repo
from .db import DBConnection
from .schemas import (
    AutomationJobObservability,
    AutomationObservability,
    CacheObservability,
    ObservabilitySnapshot,
    SyncObservability,
)
from .settings import get_settings

OBSERVABILITY_EVENT_LIMIT = 10
READINESS_CACHE_TTL_SECONDS = 30
READINESS_CACHE_MAX_STALE_SECONDS = 600

DatasetPolicy = Literal["core", "best_effort", "optional"]


class DatasetSyncState(TypedDict, total=False):
    name: str
    row_count: int
    last_synced_at: str | None
    ok: bool
    policy: DatasetPolicy
    reason: str
    error: str


def _default_now() -> datetime:
    return clock.now()


def _default_now_iso() -> str:
    return _default_now().isoformat(timespec="seconds")


def _new_observability_state(process_started_at: str | None = None) -> dict[str, Any]:
    return {
        "process_started_at": process_started_at or _default_now_iso(),
        "cache": {
            "fresh_hit": 0,
            "stale_hit": 0,
            "live_fetch_success": 0,
            "live_fetch_error": 0,
            "local_fallback": 0,
            "restaurant_hours_fresh_hit": 0,
            "restaurant_hours_stale_hit": 0,
            "restaurant_hours_live_fetch_success": 0,
            "restaurant_hours_live_fetch_error": 0,
            "recent_events": [],
        },
        "sync": {
            "recent_events": [],
            "last_failure_at": None,
            "last_failure_message": None,
        },
        "automation": {
            "leader": False,
        },
    }


_OBSERVABILITY_STATE = _new_observability_state()
_READINESS_CACHE_LOCK = threading.Lock()
_READINESS_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_READINESS_REFRESH_IN_PROGRESS: set[tuple[str, str]] = set()


def reset_observability_state(
    *,
    process_started_at: str | None = None,
) -> None:
    _OBSERVABILITY_STATE.clear()
    _OBSERVABILITY_STATE.update(_new_observability_state(process_started_at))


def reset_readiness_cache() -> None:
    with _READINESS_CACHE_LOCK:
        _READINESS_CACHE.clear()
        _READINESS_REFRESH_IN_PROGRESS.clear()


def set_automation_leader(is_leader: bool) -> None:
    _OBSERVABILITY_STATE["automation"]["leader"] = is_leader


def prepend_observability_event(items: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    items.insert(0, payload)
    del items[OBSERVABILITY_EVENT_LIMIT:]


def record_cache_decision(
    *,
    decision: str,
    origin_slug: str,
    kakao_query: str,
    radius_meters: int,
    occurred_at: str,
    logger: logging.Logger,
    error_text: str | None = None,
) -> None:
    cache_state = _OBSERVABILITY_STATE["cache"]
    if decision in {
        "fresh_hit",
        "stale_hit",
        "live_fetch_success",
        "live_fetch_error",
        "local_fallback",
    }:
        cache_state[decision] += 1
    event = {
        "decision": decision,
        "origin_slug": origin_slug,
        "kakao_query": kakao_query,
        "radius_meters": radius_meters,
        "occurred_at": occurred_at,
        "error_text": error_text,
    }
    prepend_observability_event(cache_state["recent_events"], event)
    logger.info(
        "event=restaurant_cache_decision decision=%s origin_slug=%s kakao_query=%s "
        "radius_meters=%s error_text=%s",
        decision,
        origin_slug,
        kakao_query,
        radius_meters,
        error_text or "",
    )


def record_hours_cache_decision(
    *,
    decision: str,
    kakao_place_id: str,
    source_url: str | None,
    occurred_at: str,
    logger: logging.Logger,
    error_text: str | None = None,
) -> None:
    cache_state = _OBSERVABILITY_STATE["cache"]
    if decision in {
        "restaurant_hours_fresh_hit",
        "restaurant_hours_stale_hit",
        "restaurant_hours_live_fetch_success",
        "restaurant_hours_live_fetch_error",
    }:
        cache_state[decision] += 1
    event = {
        "decision": decision,
        "origin_slug": "-",
        "kakao_query": source_url or "-",
        "radius_meters": kakao_place_id,
        "occurred_at": occurred_at,
        "error_text": error_text,
    }
    prepend_observability_event(cache_state["recent_events"], event)
    logger.info(
        "event=restaurant_hours_cache_decision decision=%s kakao_place_id=%s "
        "source_url=%s error_text=%s",
        decision,
        kakao_place_id,
        source_url or "",
        error_text or "",
    )


def record_sync_result(
    *,
    target: str,
    trigger: str,
    status: str,
    started_at: str,
    finished_at: str,
    logger: logging.Logger,
    summary: dict[str, int] | None = None,
    error_text: str | None = None,
) -> None:
    sync_state = _OBSERVABILITY_STATE["sync"]
    started = datetime.fromisoformat(started_at)
    finished = datetime.fromisoformat(finished_at)
    event = {
        "target": target,
        "trigger": trigger,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": max(0, int((finished - started).total_seconds() * 1000)),
        "summary": summary or {},
        "error_text": error_text,
    }
    prepend_observability_event(sync_state["recent_events"], event)
    failed_event_name = "automation_job_failed" if trigger == "automation" else "admin_sync_failed"
    completed_event_name = (
        "automation_job_completed" if trigger == "automation" else "admin_sync_completed"
    )
    if status == "failed":
        sync_state["last_failure_at"] = finished_at
        sync_state["last_failure_message"] = error_text
        logger.error(
            "event=%s target=%s trigger=%s duration_ms=%s error_text=%s",
            failed_event_name,
            target,
            trigger,
            event["duration_ms"],
            error_text or "",
        )
        return
    logger.info(
        "event=%s target=%s trigger=%s duration_ms=%s summary=%s",
        completed_event_name,
        target,
        trigger,
        event["duration_ms"],
        json.dumps(summary or {}, ensure_ascii=False),
    )


def readiness_cache_key(settings: Any) -> tuple[str, str]:
    return (settings.app_mode, settings.database_url)


def cache_readiness_snapshot(
    cache_key: tuple[str, str],
    *,
    fetched_at: datetime,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    cached_snapshot = deepcopy(snapshot)
    entry = {
        "fetched_at": fetched_at,
        "snapshot": cached_snapshot,
    }
    _READINESS_CACHE[cache_key] = entry
    return entry


def readiness_snapshot_has_runtime_errors(snapshot: dict[str, Any]) -> bool:
    database = snapshot.get("database", {})
    if isinstance(database, dict) and database.get("error"):
        return True
    tables = snapshot.get("tables", {})
    if not isinstance(tables, dict):
        return False
    return any(isinstance(item, dict) and bool(item.get("error")) for item in tables.values())


def readiness_failure_reason(snapshot: dict[str, Any]) -> str:
    database = snapshot.get("database", {})
    if isinstance(database, dict) and database.get("error"):
        return str(database["error"])
    tables = snapshot.get("tables", {})
    if isinstance(tables, dict):
        for name, item in tables.items():
            if isinstance(item, dict) and item.get("error"):
                return f"{name}: {item['error']}"
    return "unknown"


def get_cached_readiness_snapshot(
    cache_key: tuple[str, str],
    *,
    current: datetime,
    is_snapshot_error: Callable[[dict[str, Any]], bool],
) -> tuple[dict[str, Any] | None, bool]:
    ttl = timedelta(seconds=READINESS_CACHE_TTL_SECONDS)
    max_stale = timedelta(seconds=READINESS_CACHE_MAX_STALE_SECONDS)
    start_background_refresh = False
    with _READINESS_CACHE_LOCK:
        cached = _READINESS_CACHE.get(cache_key)
        if cached is not None and current - cached["fetched_at"] < ttl:
            return deepcopy(cached["snapshot"]), False
        if (
            cached is not None
            and current - cached["fetched_at"] <= max_stale
            and not is_snapshot_error(cached["snapshot"])
        ):
            if cache_key not in _READINESS_REFRESH_IN_PROGRESS:
                _READINESS_REFRESH_IN_PROGRESS.add(cache_key)
                start_background_refresh = True
            return deepcopy(cached["snapshot"]), start_background_refresh
    return None, False


def clear_readiness_refresh_flag(cache_key: tuple[str, str]) -> None:
    with _READINESS_CACHE_LOCK:
        _READINESS_REFRESH_IN_PROGRESS.discard(cache_key)


def store_readiness_snapshot(
    cache_key: tuple[str, str],
    *,
    fetched_at: datetime,
    snapshot: dict[str, Any],
    clear_refresh_flag: bool = True,
) -> None:
    with _READINESS_CACHE_LOCK:
        cache_readiness_snapshot(cache_key, fetched_at=fetched_at, snapshot=snapshot)
        if clear_refresh_flag:
            _READINESS_REFRESH_IN_PROGRESS.discard(cache_key)


def start_background_readiness_refresh(
    *,
    target: Any,
    args: tuple[Any, ...],
) -> None:
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()


def collect_dataset_sync_states(
    conn: DBConnection,
    *,
    tables: tuple[str, ...] | list[str],
    public_readonly: bool,
    dataset_policies: dict[str, DatasetPolicy],
    capture_errors: bool,
    rollback_connection: Any | None = None,
    logger: logging.Logger | None = None,
    error_event_name: str | None = None,
) -> tuple[dict[str, DatasetSyncState], bool]:
    table_states: dict[str, DatasetSyncState] = {}
    overall_ok = True
    for table in tables:
        policy = dataset_policies.get(table, "optional")
        try:
            item = repo.get_dataset_sync_state(conn, table)
        except Exception as exc:
            if not capture_errors:
                raise
            overall_ok = False
            table_states[table] = {
                "name": table,
                "ok": False,
                "policy": policy,
                "error": str(exc),
            }
            if logger is not None and error_event_name:
                logger.warning("event=%s check=%s error=%s", error_event_name, table, exc)
            if rollback_connection is not None:
                rollback_connection(conn)
            continue

        table_state: DatasetSyncState = {"ok": True, "policy": policy, **item}
        if public_readonly and policy == "core" and (
            not item.get("row_count") or item.get("last_synced_at") is None
        ):
            overall_ok = False
            table_state["ok"] = False
            table_state["reason"] = "empty_or_unsynced"
        table_states[table] = table_state
    return table_states, overall_ok


def collect_sync_runs_table_state(
    conn: DBConnection,
    *,
    capture_errors: bool,
    rollback_connection: Any | None = None,
    logger: logging.Logger | None = None,
    error_event_name: str | None = None,
) -> tuple[DatasetSyncState, bool]:
    try:
        repo.list_sync_runs(conn, limit=1)
        return {"name": "sync_runs", "ok": True}, True
    except Exception as exc:
        if not capture_errors:
            raise
        if logger is not None and error_event_name:
            logger.warning("event=%s check=sync_runs error=%s", error_event_name, exc)
        if rollback_connection is not None:
            rollback_connection(conn)
        return {"name": "sync_runs", "ok": False, "error": str(exc)}, False


def observability_dataset_payloads(
    table_states: dict[str, DatasetSyncState],
) -> list[dict[str, Any]]:
    datasets: list[dict[str, Any]] = []
    for state in table_states.values():
        datasets.append(
            {
                "name": state["name"],
                "row_count": state.get("row_count", 0),
                "last_synced_at": state.get("last_synced_at"),
            }
        )
    return datasets


def sync_run_completed_at(run: dict[str, Any] | None) -> str | None:
    if run is None:
        return None
    finished_at = run.get("finished_at")
    started_at = run.get("started_at")
    return finished_at or started_at


def automation_interval_minutes(target: str) -> int:
    settings = get_settings()
    if target == "snapshot":
        return settings.automation_snapshot_interval_minutes
    if target == "library_seat_prewarm":
        return settings.library_seat_prewarm_interval_minutes
    if target == "cache_cleanup":
        return settings.automation_cache_cleanup_interval_minutes
    raise ValueError(f"Unsupported automation target: {target}")


def automation_job_snapshot(
    conn: DBConnection,
    *,
    target: str,
    now: datetime,
) -> AutomationJobObservability:
    latest = repo.get_latest_sync_run(conn, target=target, trigger="automation")
    latest_success = repo.get_latest_sync_run(
        conn,
        target=target,
        trigger="automation",
        status="success",
    )
    interval_minutes = automation_interval_minutes(target)
    latest_success_at = sync_run_completed_at(latest_success)
    if latest_success_at:
        next_due = datetime.fromisoformat(latest_success_at) + timedelta(minutes=interval_minutes)
        next_due_at = next_due.isoformat(timespec="seconds")
    else:
        next_due_at = now.isoformat(timespec="seconds")
    return AutomationJobObservability(
        name=target,
        interval_minutes=interval_minutes,
        last_run_at=sync_run_completed_at(latest),
        last_status=(latest or {}).get("status") if latest else None,
        next_due_at=next_due_at,
    )


def get_automation_status(
    conn: DBConnection,
    *,
    now: datetime,
) -> AutomationObservability:
    settings = get_settings()
    return AutomationObservability(
        enabled=settings.automation_runtime_enabled,
        leader=bool(_OBSERVABILITY_STATE["automation"]["leader"]),
        jobs=[
            automation_job_snapshot(conn, target=target, now=now)
            for target in ("snapshot", "library_seat_prewarm", "cache_cleanup")
        ],
    )


def try_acquire_automation_leader(conn: DBConnection, *, lock_key: int) -> bool:
    locked = repo.try_advisory_lock(conn, lock_key)
    set_automation_leader(locked)
    return locked


def release_automation_leader(conn: DBConnection, *, lock_key: int) -> bool:
    unlocked = repo.release_advisory_lock(conn, lock_key)
    set_automation_leader(False)
    return unlocked


def is_automation_job_due(
    conn: DBConnection,
    *,
    target: str,
    now: datetime,
) -> bool:
    snapshot = automation_job_snapshot(conn, target=target, now=now)
    return now >= datetime.fromisoformat(snapshot.next_due_at or now.isoformat(timespec="seconds"))


def build_observability_snapshot(
    conn: DBConnection,
    *,
    runs_limit: int,
    now: datetime,
    public_readonly: bool,
    tables: tuple[str, ...] | list[str],
    dataset_policies: dict[str, DatasetPolicy],
    list_sync_runs_fn: Any,
) -> ObservabilitySnapshot:
    state = deepcopy(_OBSERVABILITY_STATE)
    table_states, _ = collect_dataset_sync_states(
        conn,
        tables=tables,
        public_readonly=public_readonly,
        dataset_policies=dataset_policies,
        capture_errors=False,
    )
    return ObservabilitySnapshot(
        process_started_at=state["process_started_at"],
        cache=CacheObservability.model_validate(state["cache"]),
        sync=SyncObservability.model_validate(state["sync"]),
        automation=get_automation_status(conn, now=now),
        datasets=observability_dataset_payloads(table_states),
        recent_sync_runs=list_sync_runs_fn(conn, limit=runs_limit),
    )
