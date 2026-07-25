from __future__ import annotations

import pytest

from songsim_campus import sync as sync_module


def _fake_snapshot(summary: dict[str, int], failures: list[str]):
    """sync_official_snapshot 대역. failed_sources 아웃 파라미터를 그대로 흉내낸다."""

    def _run(conn, *, failed_sources=None, **kwargs):
        if failed_sources is not None:
            failed_sources.extend(failures)
        return summary

    return _run


def test_sync_cli_exits_nonzero_when_a_source_fails(app_env, monkeypatch, capsys):
    """정기 동기화가 조용히 실패하면 안 된다.

    sync_official_snapshot 은 source 별로 격리돼 있어 일부가 실패해도 예외를
    올리지 않는다. 그대로 cron 에 걸면 워크플로는 초록불인데 데이터는 낡아가는,
    이 프로젝트를 두 달간 죽여둔 것과 똑같은 상황이 된다.
    """
    monkeypatch.setattr(
        sync_module,
        "sync_official_snapshot",
        _fake_snapshot({"places": 3}, ["registration_guides", "wifi_guides"]),
    )
    monkeypatch.setattr(sync_module, "init_db", lambda: None)
    monkeypatch.setattr("sys.argv", ["songsim-sync"])

    with pytest.raises(SystemExit) as exc:
        sync_module.main()

    assert exc.value.code == 1

    captured = capsys.readouterr()
    # 무엇이 실패했는지 로그만 보고 알 수 있어야 한다.
    assert "registration_guides" in captured.err
    assert "wifi_guides" in captured.err
    # 부분 결과는 그대로 남는다.
    assert '"places": 3' in captured.out


def test_sync_cli_allows_partial_when_asked(app_env, monkeypatch, capsys):
    monkeypatch.setattr(
        sync_module,
        "sync_official_snapshot",
        _fake_snapshot({"places": 3}, ["registration_guides"]),
    )
    monkeypatch.setattr(sync_module, "init_db", lambda: None)
    monkeypatch.setattr("sys.argv", ["songsim-sync", "--allow-partial"])

    sync_module.main()

    assert "registration_guides" in capsys.readouterr().err


def test_sync_cli_succeeds_quietly_when_every_source_works(app_env, monkeypatch, capsys):
    monkeypatch.setattr(
        sync_module, "sync_official_snapshot", _fake_snapshot({"places": 3}, [])
    )
    monkeypatch.setattr(sync_module, "init_db", lambda: None)
    monkeypatch.setattr("sys.argv", ["songsim-sync"])

    sync_module.main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert '"places": 3' in captured.out
