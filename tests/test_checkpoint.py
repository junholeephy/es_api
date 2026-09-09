"""진행 상태.

중단된 지점부터 이어서 도는 일이 여기에 달려 있다. 완료로 잘못 적으면 그 구간은
영원히 건너뛰어지고, 반대로 상태를 잃으면 이미 받은 것을 전부 다시 조회한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import TZ

from es_crawler.checkpoint import CheckpointError, CheckpointStore
from es_crawler.chunker import TimeWindow

BASE = datetime(2026, 9, 8, 18, 0, tzinfo=TZ)


def window(offset_days: int = 0) -> TimeWindow:
    start = BASE + timedelta(days=offset_days)
    return TimeWindow(start, start + timedelta(hours=24))


def store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(tmp_path / ".checkpoint.json")


def test_a_missing_file_means_nothing_is_done(tmp_path):
    """처음 실행이다. 오류가 아니다."""
    assert store(tmp_path).load() == {}


def test_a_finished_window_is_not_offered_again(tmp_path):
    saved = store(tmp_path)
    saved.mark_done(window(), 100)
    assert saved.is_done(window())
    assert saved.pending([window()]) == []


def test_a_failed_window_comes_back_next_time(tmp_path):
    """실패는 종착이 아니다. 다음 실행에서 다시 시도한다."""
    saved = store(tmp_path)
    saved.mark_failed(window(), "ConnectionTimeout")
    assert not saved.is_done(window())
    assert saved.pending([window()]) == [window()]


def test_a_retry_that_succeeds_clears_the_failure(tmp_path):
    saved = store(tmp_path)
    saved.mark_failed(window(), "ConnectionTimeout")
    saved.mark_done(window(), 42)

    state = saved.load()[window().key]
    assert state.status == "done"
    assert state.doc_count == 42
    assert state.error is None


def test_state_survives_a_restart(tmp_path):
    store(tmp_path).mark_done(window(), 7)
    assert store(tmp_path).is_done(window())


def test_only_unfinished_windows_are_offered(tmp_path):
    saved = store(tmp_path)
    saved.mark_done(window(0), 1)
    saved.mark_failed(window(1), "boom")
    assert saved.pending([window(0), window(1), window(2)]) == [window(1), window(2)]


def test_windows_are_told_apart_by_their_end_boundary(tmp_path):
    """구간이 하루보다 짧아도 키가 겹치지 않는다."""
    saved = store(tmp_path)
    short_a = TimeWindow(BASE, BASE + timedelta(hours=6))
    short_b = TimeWindow(BASE + timedelta(hours=6), BASE + timedelta(hours=12))

    saved.mark_done(short_a, 1)
    assert saved.is_done(short_a)
    assert not saved.is_done(short_b)


def test_an_unreadable_file_stops_the_run(tmp_path):
    """빈 상태로 넘어가면 이미 받은 것을 전부 다시 조회하게 된다."""
    path = tmp_path / ".checkpoint.json"
    path.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(CheckpointError, match="re-fetch"):
        CheckpointStore(path).load()


def test_a_file_missing_its_chunks_key_stops_the_run(tmp_path):
    path = tmp_path / ".checkpoint.json"
    path.write_text('{"version": 1}', encoding="utf-8")

    with pytest.raises(CheckpointError):
        CheckpointStore(path).load()


def test_the_file_stays_readable_by_a_person(tmp_path):
    saved = store(tmp_path)
    saved.mark_done(window(), 5)

    raw = json.loads((tmp_path / ".checkpoint.json").read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["chunks"][window().key]["doc_count"] == 5


def test_no_temp_file_is_left_behind(tmp_path):
    store(tmp_path).mark_done(window(), 1)
    assert not (tmp_path / ".checkpoint.json.tmp").exists()
