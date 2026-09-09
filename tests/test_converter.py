"""CSV 로 정리하기.

값을 문자열로 만드는 판정 순서가 이 모듈의 규칙이다. 순서가 하나 어긋나면
조용히 틀린 값이 파일에 남는다.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import column_specs, hits
from hypothesis import given
from hypothesis import strategies as st

from es_crawler.config import ColumnSpec, OutputConfig
from es_crawler.converter import MISSING, CsvConverter, extract_value
from es_crawler.schema import METADATA_FIELDS


def make(tmp_path: Path, columns: list[ColumnSpec], **kwargs) -> CsvConverter:
    return CsvConverter(OutputConfig(directory=tmp_path, columns=columns, **kwargs))


# ------------------------------------------------------------------- 성질


@given(documents=st.lists(hits(), max_size=30), columns=column_specs())
def test_every_document_becomes_exactly_one_row(documents, columns, tmp_path_factory):
    directory = tmp_path_factory.mktemp("rows")
    converter = make(directory, columns)

    source = directory / "in.jsonl"
    with open(source, "w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=False) + "\n")

    target = directory / "out.csv"
    assert converter.convert(source, target) == len(documents)

    with open(target, encoding="utf-8-sig", newline="") as handle:
        written = list(csv.reader(handle))
    assert written[0] == converter.headers
    assert len(written) - 1 == len(documents)


@given(document=hits(), columns=column_specs())
def test_every_row_has_one_cell_per_column(document, columns):
    converter = make(Path("."), columns)
    assert len(converter.to_row(document)) == len(converter.headers)


@given(document=hits())
def test_a_path_that_exists_yields_its_value(document):
    """문서에 있는 경로는 언제나 그 값을 돌려준다.

    메타데이터 이름은 예외다 — 아래 test_metadata_names_are_reserved 를 보라.
    """
    for key, value in document["_source"].items():
        if key in METADATA_FIELDS:
            continue
        assert extract_value(document, key) == value
    assert extract_value(document, "_id") == document["_id"]


@given(document=hits(), path=st.text(min_size=1, max_size=6))
def test_an_absent_path_is_reported_as_missing(document, path):
    if path not in document["_source"] and path not in ("_id", "_index", "_score"):
        assert extract_value(document, path) is MISSING


# ------------------------------------------------------------------- 예시


def test_an_absent_field_and_a_null_are_told_apart(tmp_path):
    """필드가 없는 것과 값이 null 인 것은 다른 사실이다."""
    converter = make(
        tmp_path,
        [ColumnSpec("gone", "gone"), ColumnSpec("empty", "empty")],
        missing_value="",
        null_value="NULL",
    )
    assert converter.to_row({"_source": {"empty": None}}) == ["", "NULL"]


def test_true_is_written_as_true_not_one():
    """bool 검사가 숫자 검사보다 뒤로 가면 True 가 1 로 기록된다."""
    converter = CsvConverter(
        OutputConfig(directory=Path("."), columns=[ColumnSpec("flag", "flag")])
    )
    assert converter.render(True) == "true"
    assert converter.render(False) == "false"
    assert converter.render(1) == "1"
    assert converter.render(0) == "0"


def test_arrays_and_objects_keep_their_shape_as_json():
    converter = CsvConverter(OutputConfig(directory=Path("."), columns=[ColumnSpec("x", "x")]))
    assert converter.render(["a", "b"]) == '["a", "b"]'
    assert converter.render({"x": 1}) == '{"x": 1}'
    assert converter.render(["한글"]) == '["한글"]'


def test_a_nested_path_reaches_into_the_document():
    document = {"_source": {"user": {"name": "kim", "tags": ["a"]}}}
    assert extract_value(document, "user.name") == "kim"
    assert extract_value(document, "user.tags") == ["a"]
    assert extract_value(document, "user.missing") is MISSING
    assert extract_value(document, "user.name.deeper") is MISSING


def test_metadata_comes_from_the_top_level_not_the_body():
    document = {"_id": "outer", "_index": "idx", "_source": {"_id": "inner"}}
    assert extract_value(document, "_id") == "outer"


def test_metadata_names_are_reserved():
    """_id / _index / _score 는 언제나 문서 바깥을 가리킨다.

    본문에 같은 이름의 필드가 있으면 그 값은 컬럼으로 꺼낼 수 없다. 이름이 셋뿐이라
    실제로 부딪힐 일은 드물지만, 부딪히면 조용히 바깥 값이 나오므로 여기 적어둔다.
    """
    document = {"_id": "outer", "_score": 1.5, "_source": {"_score": ["inner"]}}
    assert extract_value(document, "_score") == 1.5
    assert extract_value(document, "_score") != ["inner"]


def test_headers_follow_the_configured_order(tmp_path):
    converter = make(tmp_path, [ColumnSpec("b", "second"), ColumnSpec("a", "first")])
    assert converter.headers == ["second", "first"]


def test_the_file_opens_cleanly_in_a_spreadsheet(tmp_path):
    """BOM 이 붙어야 Excel 에서 한글이 깨지지 않는다."""
    converter = make(tmp_path, [ColumnSpec("name", "이름")])
    source = tmp_path / "in.jsonl"
    source.write_text('{"_source": {"name": "김철수"}}\n', encoding="utf-8")

    target = tmp_path / "out.csv"
    converter.convert(source, target)
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "김철수" in target.read_text(encoding="utf-8-sig")


def test_blank_lines_are_skipped(tmp_path):
    converter = make(tmp_path, [ColumnSpec("a", "a")])
    source = tmp_path / "in.jsonl"
    source.write_text('{"_source": {"a": 1}}\n\n{"_source": {"a": 2}}\n\n', encoding="utf-8")
    assert converter.convert(source, tmp_path / "out.csv") == 2


def test_converting_twice_gives_the_same_file(tmp_path):
    """다시 돌려도 결과가 같아야 실패한 실행을 마음 놓고 재시도할 수 있다."""
    converter = make(tmp_path, [ColumnSpec("a", "a")])
    source = tmp_path / "in.jsonl"
    source.write_text('{"_source": {"a": 1}}\n', encoding="utf-8")
    target = tmp_path / "out.csv"

    converter.convert(source, target)
    first = target.read_bytes()
    converter.convert(source, target)
    assert target.read_bytes() == first


def test_a_broken_line_leaves_no_half_written_file(tmp_path):
    converter = make(tmp_path, [ColumnSpec("a", "a")])
    source = tmp_path / "in.jsonl"
    source.write_text('{"_source": {"a": 1}}\nnot json\n', encoding="utf-8")
    target = tmp_path / "out.csv"

    try:
        converter.convert(source, target)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("expected the broken line to raise")

    assert not target.exists()
    assert not (tmp_path / "out.csv.tmp").exists()
