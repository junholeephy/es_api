"""구간 자르기.

여기가 조용히 틀리면 문서가 빠지거나 겹치는데 로그에는 아무것도 남지 않는다.
그래서 예시 몇 개가 아니라 성질로 확인한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest
from conftest import TZ, chunk_configs, spans
from hypothesis import given
from hypothesis import strategies as st

from es_crawler.chunker import MAX_DURATION, DateChunker, TimeWindow, parse_boundary
from es_crawler.config import ChunkConfig

# ------------------------------------------------------------------- 성질


@given(span=spans(), config=chunk_configs())
def test_chunks_cover_the_request_exactly(span, config):
    """구간들의 합집합은 요청한 범위와 정확히 같다. 앞뒤로 넘치지 않는다."""
    start, end = span
    windows = DateChunker(config).chunks(start, end)
    assert windows
    assert windows[0].start.astimezone(UTC) == start.astimezone(UTC)
    assert windows[-1].end.astimezone(UTC) == end.astimezone(UTC)


@given(span=spans(), config=chunk_configs())
def test_chunks_do_not_overlap_or_leave_gaps(span, config):
    """이웃한 구간은 정확히 맞닿는다. 겹치면 문서가 두 번, 벌어지면 아예 빠진다."""
    start, end = span
    windows = DateChunker(config).chunks(start, end)
    for earlier, later in pairwise(windows):
        assert earlier.end.astimezone(UTC) == later.start.astimezone(UTC)


@given(span=spans(), config=chunk_configs())
def test_every_chunk_stays_within_the_limit(span, config):
    """어떤 구간도 상한을 넘지 않고, 빈 구간도 없다."""
    start, end = span
    limit = timedelta(hours=config.chunk_hours)
    for window in DateChunker(config).chunks(start, end):
        assert timedelta(0) < window.duration <= limit
        assert window.duration <= MAX_DURATION


@given(span=spans(), config=chunk_configs())
def test_chunks_come_out_in_order(span, config):
    start, end = span
    windows = DateChunker(config).chunks(start, end)
    instants = [w.start.astimezone(UTC) for w in windows]
    assert instants == sorted(instants)


@given(span=spans(), config=chunk_configs())
def test_key_round_trips_to_the_end_boundary(span, config):
    """기록에 쓰는 키를 되읽으면 원래 종료 시각과 같은 순간이 나온다.

    같은 순간인지를 본다. 객체 비교(==)로는 안 된다 — 서머타임이 끝나는 날의
    애매한 한 시간에 놓인 시각은, 같은 순간을 가리켜도 다른 타임존 표현끼리는
    같지 않다고 판정된다 (PEP 495).
    """
    start, end = span
    for window in DateChunker(config).chunks(start, end):
        assert datetime.fromisoformat(window.key).astimezone(UTC) == window.end.astimezone(UTC)


@given(span=spans(), config=chunk_configs())
def test_distinct_windows_get_distinct_file_names(span, config):
    """서로 다른 구간은 서로 다른 파일 이름을 갖는다.

    날짜만 쓰면 하루보다 짧은 구간이 같은 이름을 갖고, 조용히 덮어쓴다.
    """
    start, end = span
    windows = DateChunker(config).chunks(start, end)
    slugs = [w.slug for w in windows]
    assert len(set(slugs)) == len(slugs)


@given(config=chunk_configs(), when=st.datetimes(datetime(2021, 1, 1), datetime(2029, 12, 31)))
def test_default_window_is_always_one_finished_day(config, when):
    """기본 구간은 언제 실행하든 24시간이고, 아직 오지 않은 시각을 넘지 않는다."""
    chunker = DateChunker(config)
    start, end = chunker.default_window(when.replace(tzinfo=config.tz))
    assert end - start == timedelta(hours=24)
    assert end <= when.replace(tzinfo=config.tz)


# ------------------------------------------------------------------- 예시


def test_default_window_after_the_anchor_takes_today():
    """19:00 에 돌면 전날 18:00 부터 당일 18:00 까지."""
    chunker = DateChunker(ChunkConfig(anchor_time=time(18, 0)))
    start, end = chunker.default_window(datetime(2026, 9, 9, 19, 0, tzinfo=TZ))
    assert start == datetime(2026, 9, 8, 18, 0, tzinfo=TZ)
    assert end == datetime(2026, 9, 9, 18, 0, tzinfo=TZ)


def test_default_window_before_the_anchor_steps_back_a_day():
    """17:00 에 돌면 아직 오늘 18:00 이 오지 않았으므로 직전 하루를 본다."""
    chunker = DateChunker(ChunkConfig(anchor_time=time(18, 0)))
    _, end = chunker.default_window(datetime(2026, 9, 9, 17, 0, tzinfo=TZ))
    assert end == datetime(2026, 9, 8, 18, 0, tzinfo=TZ)


def test_default_window_includes_the_anchor_moment_itself():
    chunker = DateChunker(ChunkConfig(anchor_time=time(18, 0)))
    _, end = chunker.default_window(datetime(2026, 9, 9, 18, 0, tzinfo=TZ))
    assert end == datetime(2026, 9, 9, 18, 0, tzinfo=TZ)


def test_five_days_becomes_five_chunks():
    chunker = DateChunker(ChunkConfig())
    windows = chunker.chunks(
        datetime(2026, 9, 1, 18, 0, tzinfo=TZ), datetime(2026, 9, 6, 18, 0, tzinfo=TZ)
    )
    assert len(windows) == 5
    assert all(w.duration == timedelta(hours=24) for w in windows)


def test_a_partial_tail_stays_inside_the_request():
    """마지막 구간은 짧아도 되지만 요청 범위를 넘어서는 안 된다."""
    chunker = DateChunker(ChunkConfig())
    end = datetime(2026, 9, 3, 6, 0, tzinfo=TZ)
    windows = chunker.chunks(datetime(2026, 9, 1, 18, 0, tzinfo=TZ), end)
    assert len(windows) == 2
    assert windows[-1].duration == timedelta(hours=12)
    assert windows[-1].end == end


def test_slug_keeps_the_offset_and_drops_the_colon():
    window = TimeWindow(
        datetime(2026, 9, 8, 18, 0, tzinfo=TZ), datetime(2026, 9, 9, 18, 0, tzinfo=TZ)
    )
    assert window.slug == "2026-09-09T180000+0900"
    assert ":" not in window.slug


def test_window_rejects_a_span_over_the_limit():
    with pytest.raises(ValueError, match="24h"):
        TimeWindow(datetime(2026, 9, 1, 0, 0, tzinfo=TZ), datetime(2026, 9, 2, 1, 0, tzinfo=TZ))


def test_window_rejects_naive_bounds():
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeWindow(datetime(2026, 9, 1), datetime(2026, 9, 2))


def test_window_rejects_an_empty_span():
    moment = datetime(2026, 9, 1, tzinfo=TZ)
    with pytest.raises(ValueError, match="precede"):
        TimeWindow(moment, moment)


def test_a_date_without_a_time_is_rejected():
    """하루의 경계가 자정이 아닐 수 있으므로 날짜만으로는 구간이 정해지지 않는다."""
    with pytest.raises(ValueError, match="no time component"):
        parse_boundary("2026-09-01", TZ)


def test_a_bare_time_takes_the_configured_zone():
    parsed = parse_boundary("2026-09-01T18:00", TZ)
    assert parsed == datetime(2026, 9, 1, 18, 0, tzinfo=TZ)


def test_an_explicit_offset_wins_over_the_configured_zone():
    parsed = parse_boundary("2026-09-01T18:00+00:00", TZ)
    assert parsed.utcoffset().total_seconds() == 0


def test_midnight_is_accepted_when_written_out():
    """자정을 쓰고 싶으면 시각을 적으면 된다. 거부되는 것은 날짜만 준 경우다."""
    assert parse_boundary("2026-09-01T00:00", TZ) == datetime(2026, 9, 1, 0, 0, tzinfo=TZ)


def test_chunker_rejects_a_backwards_span():
    chunker = DateChunker(ChunkConfig())
    later = datetime(2026, 9, 2, tzinfo=TZ)
    with pytest.raises(ValueError, match="precede"):
        chunker.chunks(later, datetime(2026, 9, 1, tzinfo=TZ))


def test_six_hour_chunks_split_a_day_into_four():
    chunker = DateChunker(ChunkConfig(chunk_hours=6))
    windows = chunker.chunks(
        datetime(2026, 9, 1, 18, 0, tzinfo=TZ), datetime(2026, 9, 2, 18, 0, tzinfo=TZ)
    )
    assert len(windows) == 4
    assert len({w.slug for w in windows}) == 4


def test_a_window_may_cross_a_daylight_saving_change():
    """서머타임을 넘는 구간도 정상이다.

    두 끝의 UTC 오프셋이 달라지지만 길이는 절대 시간으로 재므로 문제가 없다.
    오프셋이 같아야 한다고 두면 이런 구간이 통째로 거부된다.
    """
    ny = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 7, 18, 0, tzinfo=ny)
    end = start + timedelta(days=3)
    assert start.utcoffset() != end.utcoffset()

    windows = DateChunker(ChunkConfig(timezone="America/New_York")).chunks(start, end)
    assert windows[0].start.astimezone(UTC) == start.astimezone(UTC)
    assert windows[-1].end.astimezone(UTC) == end.astimezone(UTC)
    assert all(w.duration <= MAX_DURATION for w in windows)
    # 봄에는 한 시간이 사라진다. 벽시계로는 25시간처럼 보이지만 실제로는 24시간이다.
    assert windows[0].duration == timedelta(hours=24)


def test_a_chunk_never_covers_more_real_time_than_configured():
    """서머타임이 끝나는 날, 벽시계 한 시간이 실제로는 두 시간이다.

    지역 시각에 timedelta 를 더하는 방식으로 자르면 그 조각이 두 시간을 덮는데,
    duration 은 벽시계 차이라 한 시간이라고 답한다. 한 번의 조회가 덮는 양에 상한을
    두는 것이 목적이므로 그러면 상한이 의미를 잃는다.
    """
    ny = ZoneInfo("America/New_York")
    limit = timedelta(hours=1)
    windows = DateChunker(ChunkConfig(timezone="America/New_York", chunk_hours=1)).chunks(
        datetime(2020, 11, 1, 0, 0, tzinfo=ny), datetime(2020, 11, 1, 4, 0, tzinfo=ny)
    )

    for window in windows:
        elapsed = window.end.astimezone(UTC) - window.start.astimezone(UTC)
        assert elapsed <= limit
        assert window.duration == elapsed

    total = windows[-1].end.astimezone(UTC) - windows[0].start.astimezone(UTC)
    assert total == timedelta(hours=5)
    assert len(windows) == 5


def test_a_fall_back_day_is_split_rather_than_stretched():
    """서머타임이 끝나는 하루는 25시간이다. 한 조각에 담을 수 없다."""
    ny = ZoneInfo("America/New_York")
    windows = DateChunker(ChunkConfig(timezone="America/New_York", chunk_hours=24)).chunks(
        datetime(2020, 10, 31, 18, 0, tzinfo=ny), datetime(2020, 11, 1, 18, 0, tzinfo=ny)
    )
    assert len(windows) == 2
    assert windows[0].duration == timedelta(hours=24)
    assert windows[1].duration == timedelta(hours=1)


def test_a_sub_minute_tail_gets_its_own_file_name():
    """마지막 조각이 1초짜리여도 앞 조각과 이름이 겹치지 않는다.

    이름을 분까지만 쓰면 05:00 에 끝나는 조각과 05:00:01 에 끝나는 조각이 같은
    파일이 된다. 기록에는 둘 다 끝났다고 남고 파일은 하나뿐인 상태가 되는데,
    로그에는 아무것도 나오지 않는다.
    """
    chunker = DateChunker(ChunkConfig(chunk_hours=1))
    windows = chunker.chunks(
        datetime(2020, 1, 1, 0, 0, tzinfo=TZ),
        datetime(2020, 1, 1, 5, 0, 1, tzinfo=TZ),
    )
    assert len(windows) == 6
    assert windows[-1].duration == timedelta(seconds=1)
    assert len({w.slug for w in windows}) == 6


@given(span=spans(), config=chunk_configs())
def test_the_file_name_is_derived_from_the_record_key(span, config):
    """이름은 키에서 콜론만 뺀 것이다. 키가 다르면 이름도 반드시 다르다."""
    start, end = span
    for window in DateChunker(config).chunks(start, end):
        assert window.slug == window.key.replace(":", "")
        assert ":" not in window.slug
