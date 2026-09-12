"""형태 대조.

화면에 뜨는 줄을 사람이 그대로 옮겨 적는 것이 전제다. "형식이 틀렸습니다" 같은
요약 메시지는 여기서 결함이다 — 옮겨 적을 것이 없기 때문이다.
"""

from __future__ import annotations

import pytest

from es_crawler import schema as sch
from es_crawler.schema import Field, Report, resolve, validate
from es_crawler.synth import generate


def with_schema(monkeypatch, fields: tuple[Field, ...]) -> None:
    monkeypatch.setattr(sch, "INPUT_SCHEMA", fields)


def test_synthetic_documents_match_the_declared_shape():
    """스키마에서 만든 문서가 스키마를 통과하지 못하면 둘 중 하나가 틀린 것이다."""
    assert validate(generate(200, seed=1)).ok


def test_adversarial_documents_are_caught():
    report = validate(generate(500, seed=1, mode="adversarial"))
    assert not report.ok
    assert report.violations


def test_a_violation_line_names_the_field_and_the_count(monkeypatch):
    with_schema(monkeypatch, (Field("grade", "str", False),))
    report = validate([{"_source": {"grade": 1}} for _ in range(3)])

    assert len(report.violations) == 1
    line = report.violations[0]
    assert "grade" in line
    assert "3" in line


def test_a_field_the_output_ignores_becomes_a_note(monkeypatch):
    """결과에 영향이 없는 어긋남을 위반으로 올리면, 매 실행마다 뜨는 줄이 생긴다."""
    with_schema(monkeypatch, (Field("legacy", "int", True, used=False),))
    report = validate([{"_source": {"legacy": "text"}}])

    assert report.ok
    assert report.notes


def test_the_sample_size_is_recorded(monkeypatch):
    with_schema(monkeypatch, (Field("a", "int", True),))
    assert validate([{"_source": {"a": 1}} for _ in range(7)]).sampled == 7


def test_no_documents_is_reported_but_is_not_a_violation():
    report = validate([])
    assert report.ok
    assert report.notes


def test_a_missing_field_and_a_null_are_reported_separately(monkeypatch):
    with_schema(monkeypatch, (Field("x", "int", False),))
    report = validate([{"_source": {}}, {"_source": {"x": None}}])

    joined = " ".join(report.violations)
    assert "missing" in joined
    assert "nulls" in joined


def test_a_nullable_field_may_be_null(monkeypatch):
    with_schema(monkeypatch, (Field("x", "int", True),))
    assert validate([{"_source": {"x": None}}]).ok


def test_unexpected_category_values_are_listed(monkeypatch):
    with_schema(monkeypatch, (Field("grade", "str", True, allowed=("A", "B")),))
    report = validate([{"_source": {"grade": "Z"}}])
    assert "Z" in report.violations[0]


def test_a_value_outside_the_range_is_counted(monkeypatch):
    with_schema(monkeypatch, (Field("score", "float", True, rng=(0.0, 1.0)),))
    report = validate([{"_source": {"score": 5.0}}])
    assert "outside" in report.violations[0]


def test_booleans_are_not_accepted_as_numbers(monkeypatch):
    with_schema(monkeypatch, (Field("n", "int", True),))
    assert not validate([{"_source": {"n": True}}]).ok


def test_metadata_is_read_from_the_top_level():
    assert resolve({"_id": "abc", "_source": {}}, "_id") == "abc"


def test_a_timestamp_written_with_z_is_accepted(monkeypatch):
    with_schema(monkeypatch, (Field("t", "datetime", False),))
    assert validate([{"_source": {"t": "2026-09-09T10:00:00Z"}}]).ok


def test_report_is_ok_only_when_there_are_no_violations():
    assert Report([], ["note"]).ok
    assert not Report(["violation"], []).ok


# ------------------------------------------------------------------ 경로 해석

MESSAGES = {
    "_source": {
        "request_body_content": {
            "messages": [
                {"role": "system", "content": "지시"},
                {"role": "user", "content": "1턴 질문"},
                {"role": "assistant", "content": "1턴 답변"},
                {"role": "user", "content": "2턴 질문"},
            ]
        },
        "plain": "문자열",
    }
}

SENTINEL = object()


def test_an_index_picks_one_item_out_of_a_list():
    assert resolve(MESSAGES, "request_body_content.messages[0].role") == "system"


def test_a_negative_index_counts_from_the_end():
    """대화 이력은 턴마다 길이가 다르다. 마지막 하나를 길이 없이 집을 수 있어야 한다."""
    assert resolve(MESSAGES, "request_body_content.messages[-1].content") == "2턴 질문"
    assert resolve(MESSAGES, "request_body_content.messages[-1].role") == "user"


def test_an_index_past_the_end_is_missing_not_an_error():
    """30분 받아온 뒤 IndexError 로 죽으면 그 실행을 통째로 버린다."""
    assert resolve(MESSAGES, "request_body_content.messages[99].content", SENTINEL) is SENTINEL


def test_indexing_something_that_is_not_a_list_is_missing():
    """문자열은 인덱스가 먹지만 글자 하나를 돌려준다. 의도한 적이 없다."""
    assert resolve(MESSAGES, "plain[0]", SENTINEL) is SENTINEL


def test_a_malformed_path_reads_as_missing():
    """설정에서 온 경로는 읽을 때 이미 검증했다. 여기서 또 죽일 이유가 없다."""
    for bad in ("plain[", "plain[a]", "..", ""):
        assert resolve(MESSAGES, bad, SENTINEL) is SENTINEL


def test_parse_path_refuses_what_it_cannot_read():
    """설정 단계에서 걸러내려면 여기서 조용히 넘기면 안 된다."""
    for bad in ("plain[", "plain[a]", "a..b", ""):
        with pytest.raises(ValueError):
            sch.parse_path(bad)


def test_parse_path_accepts_the_shapes_we_use():
    assert sch.parse_path("a.b") == (("a", ()), ("b", ()))
    assert sch.parse_path("messages[-1].content") == (("messages", (-1,)), ("content", ()))
