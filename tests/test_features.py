"""기능 등록부. 아직 기능이 없어도 자리가 제대로 비어 있는지 본다."""

import pytest

from es_crawler import features
from es_crawler.features import template


def test_no_features_means_no_metrics_line():
    """본업은 뽑아 떨구는 것이다. 판정이 없는 것은 결함이 아니다."""
    assert features.process_data([{"a": 1}]) == {}


def test_a_registered_feature_shows_up():
    original = features.FEATURES
    features.FEATURES = (template,)
    try:
        metrics = features.process_data([{"a": 1, "b": ""}, {"a": 2, "b": "x"}])
        assert any(k.startswith(template.NAME) for k in metrics)
    finally:
        features.FEATURES = original


def test_colliding_metric_names_raise_instead_of_overwriting():
    """조용히 덮어쓰면 화면에 마지막 기능의 숫자만 남고, 덮였다는 사실이 안 뜬다."""

    class Twin:
        NAME = "twin"

        @staticmethod
        def process_data(rows):
            return {template.NAME: "겹친다"}

    original = features.FEATURES
    features.FEATURES = (template, Twin)
    try:
        with pytest.raises(KeyError, match="twin"):
            features.process_data([{"a": 1}])
    finally:
        features.FEATURES = original


def test_template_exposes_the_agreed_shape():
    """복사 원본이 계약을 지켜야 베낀 것도 지킨다."""
    assert isinstance(template.NAME, str) and template.NAME
    assert callable(template.process_data)
    for name in template.process_data([{"a": 1}]):
        assert name.startswith(template.NAME)
