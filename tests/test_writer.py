"""파일로 남기기.

받은 것을 그대로 되읽을 수 있어야 하고, 도중에 죽어도 반쪽짜리가 결과로 보이면 안 된다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import TZ, hits
from hypothesis import given
from hypothesis import strategies as st

from es_crawler.chunker import TimeWindow
from es_crawler.writer import JsonlWriter, count_lines

WINDOW = TimeWindow(datetime(2026, 9, 8, 18, 0, tzinfo=TZ), datetime(2026, 9, 9, 18, 0, tzinfo=TZ))


def read_back(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@given(documents=st.lists(hits(), max_size=40))
def test_written_documents_read_back_unchanged(documents, tmp_path_factory):
    """쓰고 읽으면 원래 문서가 그대로 나온다. 저장 과정에서 잃는 것이 없다."""
    directory = tmp_path_factory.mktemp("roundtrip")
    writer = JsonlWriter(directory)
    count = writer.write(WINDOW, documents)

    assert count == len(documents)
    assert read_back(writer.path_for(WINDOW)) == documents


@given(documents=st.lists(hits(), max_size=20))
def test_line_count_matches_document_count(documents, tmp_path_factory):
    directory = tmp_path_factory.mktemp("count")
    writer = JsonlWriter(directory)
    writer.write(WINDOW, documents)
    assert count_lines(writer.path_for(WINDOW)) == len(documents)


def test_an_empty_result_still_leaves_a_file(tmp_path: Path):
    """조회했더니 없었다와 아직 조회하지 않았다는 다른 상태다."""
    writer = JsonlWriter(tmp_path)
    assert writer.write(WINDOW, []) == 0
    assert writer.exists(WINDOW)
    assert writer.path_for(WINDOW).read_text() == ""


def test_the_file_name_carries_the_end_boundary(tmp_path: Path):
    writer = JsonlWriter(tmp_path)
    assert writer.path_for(WINDOW).name == "data-2026-09-09T180000+0900.jsonl"
    assert writer.csv_path_for(WINDOW).name == "data-2026-09-09T180000+0900.csv"


def test_a_failure_midway_leaves_no_output(tmp_path: Path):
    """도중에 터지면 최종 이름의 파일이 생기지 않고 임시 파일도 남지 않는다."""

    def exploding() -> Iterator[dict[str, Any]]:
        yield {"_id": "1", "_source": {}}
        raise RuntimeError("connection lost")

    writer = JsonlWriter(tmp_path)
    with pytest.raises(RuntimeError):
        writer.write(WINDOW, exploding())

    assert not writer.exists(WINDOW)
    assert list(tmp_path.iterdir()) == []


def test_a_leftover_temp_file_is_not_mistaken_for_output(tmp_path: Path):
    """하드 크래시가 남긴 임시 파일은 결과로 보이지 않는다."""
    writer = JsonlWriter(tmp_path)
    stale = writer.path_for(WINDOW).with_name(writer.path_for(WINDOW).name + ".tmp")
    stale.write_text('{"_id": "half-written"', encoding="utf-8")

    assert not writer.exists(WINDOW)


def test_korean_text_is_stored_readable(tmp_path: Path):
    """한글이 \\uXXXX 로 도망가지 않아야 파일을 눈으로 확인할 수 있다."""
    writer = JsonlWriter(tmp_path)
    writer.write(WINDOW, [{"_id": "1", "_source": {"name": "김철수"}}])
    assert "김철수" in writer.path_for(WINDOW).read_text(encoding="utf-8")


def test_two_windows_never_share_a_file(tmp_path: Path):
    """구간이 하루보다 짧아도 이름이 겹치지 않는다."""
    writer = JsonlWriter(tmp_path)
    base = datetime(2026, 9, 9, 0, 0, tzinfo=TZ)
    names = {
        writer.path_for(TimeWindow(base + timedelta(hours=h), base + timedelta(hours=h + 6))).name
        for h in (0, 6, 12, 18)
    }
    assert len(names) == 4
