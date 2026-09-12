"""기능 등록부. 아직 기능이 없어도 자리가 제대로 비어 있는지 본다.

기능이 받는 것은 문서 본문이 아니라 그것을 감싼 **Elasticsearch 히트**다. 여기서
쓰는 표본도 같은 모양이어야 한다 — 납작한 dict 로 시험하면 통과하는데 실제로는
봉투를 훑는 코드가 그대로 지나간다.
"""

from typing import Any

import pytest

from es_crawler import pipeline
from es_crawler.features import template


def hit(**source: Any) -> dict[str, Any]:
    """실제로 오는 모양. _score 는 sort:["_doc"] 라 언제나 None 이다."""
    return {"_index": "logs-000001", "_id": "abc", "_score": None, "_source": source}


def test_no_features_still_reports_the_sample_size():
    """본업은 뽑아 떨구는 것이다. 기능이 없는 것은 결함이 아니다.

    그래도 건수는 찍는다 — 분모가 없으면 나중에 붙는 비율을 읽을 수 없다.
    """
    assert pipeline.process_data([hit(a=1)]) == {"hits": "1"}


def test_a_registered_feature_shows_up():
    original = pipeline.FEATURES
    pipeline.FEATURES = (template,)
    try:
        metrics = pipeline.process_data([hit(user={"name": ""}), hit(user={"name": "x"})])
        assert any(k.startswith(template.NAME) for k in metrics)
    finally:
        pipeline.FEATURES = original


def test_colliding_metric_names_raise_instead_of_overwriting():
    """조용히 덮어쓰면 화면에 마지막 기능의 숫자만 남고, 덮였다는 사실이 안 뜬다."""

    class Twin:
        NAME = "twin"

        @staticmethod
        def process_data(hits: list[dict[str, Any]]) -> dict[str, str]:
            return {template.NAME: "겹친다"}

    original = pipeline.FEATURES
    pipeline.FEATURES = (template, Twin)
    try:
        with pytest.raises(KeyError, match="twin"):
            pipeline.process_data([hit(a=1)])
    finally:
        pipeline.FEATURES = original


def test_template_exposes_the_agreed_shape():
    """복사 원본이 계약을 지켜야 베낀 것도 지킨다."""
    assert isinstance(template.NAME, str) and template.NAME
    assert callable(template.process_data)
    for name in template.process_data([hit(a=1)]):
        assert name.startswith(template.NAME)


def test_the_template_reads_the_document_not_the_envelope():
    """봉투를 훑으면 _score 가 언제나 None 이라 무엇을 넣어도 100% 가 나온다.

    이 원본을 베껴 _hit 안쪽만 고치는 사람이 따라가는 길이므로, 원본이 _source
    안을 보고 있어야 한다.
    """
    filled = [hit(user={"name": "kim"})] * 10
    assert template.process_data(filled) == {"template": "0 (0.00%)"}

    empty = [hit(user={"name": ""})] * 10
    assert template.process_data(empty) == {"template": "10 (100.00%)"}
