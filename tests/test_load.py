"""바깥 시스템에 붙는 부분.

여기가 조용히 깨지면 프로그램은 정상 종료하고 로그도 깨끗하다. 남은 조회 상태는
서버 쪽에서만 보인다. 그래서 정리 호출이 실제로 일어나는지를 세 경우 모두에서 본다.

클러스터에 접속하지 않는다.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta

import pytest
from conftest import TZ

from es_crawler.chunker import TimeWindow
from es_crawler.config import ConfigError, EsConfig, QueryConfig, build_config
from es_crawler.load import EsExtractor, build_client
from es_crawler.synth import FakeSearchClient, dry_run_config, generate

WINDOW = TimeWindow(datetime(2026, 9, 8, 18, 0, tzinfo=TZ), datetime(2026, 9, 9, 18, 0, tzinfo=TZ))
QUERY = QueryConfig(index="logs-*", time_field="@timestamp", batch_size=100)


def extractor(n: int = 250) -> tuple[EsExtractor, FakeSearchClient]:
    client = FakeSearchClient(generate(n), page=100)
    return EsExtractor(client, QUERY), client


# ------------------------------------------------------- 조회 상태 정리


def test_the_search_context_is_released_after_a_full_read():
    reader, client = extractor()
    with closing(reader.iter_documents(WINDOW)) as documents:
        assert len(list(documents)) == 250
    assert client.released
    assert client.open_contexts == 0


def test_the_search_context_is_released_when_the_reader_stops_early():
    """다 읽지 않고 멈춰도 정리된다. closing 이 없으면 이 정리가 뒤로 밀린다."""
    reader, client = extractor()
    with closing(reader.iter_documents(WINDOW)) as documents:
        next(documents)
    assert client.released
    assert client.open_contexts == 0


def test_the_search_context_is_released_when_the_consumer_raises():
    reader, client = extractor()
    with pytest.raises(RuntimeError), closing(reader.iter_documents(WINDOW)) as documents:
        for _ in documents:
            raise RuntimeError("writer died")
    assert client.released
    assert client.open_contexts == 0


def test_a_failure_while_releasing_does_not_lose_the_result():
    """정리에 실패했다고 이미 받아온 결과를 실패로 바꾸지는 않는다."""

    class Grumpy(FakeSearchClient):
        def clear_scroll(self, *, scroll_id):
            raise RuntimeError("already expired")

    reader = EsExtractor(Grumpy(generate(10), page=5), QUERY)
    with closing(reader.iter_documents(WINDOW)) as documents:
        assert len(list(documents)) == 10


def test_the_latest_scroll_id_is_the_one_released():
    """서버가 식별자를 바꿔 돌려줄 수 있다. 첫 값만 들고 있으면 엉뚱한 것을 지운다."""

    class Rotating(FakeSearchClient):
        def scroll(self, *, scroll_id, scroll):
            page = super().scroll(scroll_id=scroll_id, scroll=scroll)
            renamed = scroll_id + "+"
            self._cursors[renamed] = self._cursors.pop(scroll_id, 0)
            page["_scroll_id"] = renamed
            return page

    client = Rotating(generate(250), page=100)
    reader = EsExtractor(client, QUERY)
    with closing(reader.iter_documents(WINDOW)) as documents:
        list(documents)

    assert client.released
    assert client.released[-1].endswith("+")


# ------------------------------------------------------------- 조회 본문


def test_the_range_excludes_the_upper_boundary():
    """lte 를 쓰면 경계에 놓인 문서가 이웃한 두 구간에 모두 걸린다."""
    reader, _ = extractor()
    body = reader.build_query(WINDOW)
    bounds = body["query"]["bool"]["filter"][0]["range"]["@timestamp"]

    assert set(bounds) == {"gte", "lt"}
    assert bounds["gte"] == WINDOW.start.isoformat()
    assert bounds["lt"] == WINDOW.end.isoformat()


def test_the_range_carries_its_offset():
    """오프셋이 붙은 문자열을 그대로 보낸다. 손으로 UTC 로 바꾸지 않는다."""
    reader, _ = extractor()
    bounds = reader.build_query(WINDOW)["query"]["bool"]["filter"][0]["range"]["@timestamp"]
    assert bounds["gte"].endswith("+09:00")


def test_extra_filters_are_added_after_the_range():
    reader = EsExtractor(
        FakeSearchClient([]),
        QueryConfig(
            index="logs-*",
            time_field="@timestamp",
            extra_filters=[{"term": {"level": "ERROR"}}],
        ),
    )
    filters = reader.build_query(WINDOW)["query"]["bool"]["filter"]
    assert len(filters) == 2
    assert filters[1] == {"term": {"level": "ERROR"}}


def test_the_scan_does_not_score_documents():
    reader, _ = extractor()
    assert reader.build_query(WINDOW)["sort"] == ["_doc"]


def test_the_batch_size_reaches_the_request():
    reader, _ = extractor()
    assert reader.build_query(WINDOW)["size"] == 100


def test_an_empty_window_yields_nothing_and_still_releases():
    reader = EsExtractor(FakeSearchClient([]), QUERY)
    client = reader._client
    with closing(reader.iter_documents(WINDOW)) as documents:
        assert list(documents) == []
    assert client.open_contexts == 0


def test_windows_that_touch_do_not_double_count():
    """두 구간의 경계가 맞닿아도 같은 문서를 두 번 세지 않는다."""
    first = TimeWindow(WINDOW.start, WINDOW.start + timedelta(hours=12))
    second = TimeWindow(first.end, WINDOW.end)
    assert first.end == second.start

    reader, _ = extractor()
    a = reader.build_query(first)["query"]["bool"]["filter"][0]["range"]["@timestamp"]
    b = reader.build_query(second)["query"]["bool"]["filter"][0]["range"]["@timestamp"]
    assert a["lt"] == b["gte"]


# ------------------------------------------------------- 접속 설정


def es_section(tmp_path, **overrides) -> EsConfig:
    raw = dry_run_config(tmp_path)
    raw["elasticsearch"] = {**raw["elasticsearch"], **overrides}
    return build_config(raw).es


def captured_kwargs(monkeypatch, config: EsConfig) -> dict:
    seen: dict = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr("es_crawler.load.Elasticsearch", fake)
    build_client(config)
    return seen


def test_certificates_are_verified_unless_the_config_says_otherwise(tmp_path):
    """켠 쪽이 기본이다. 끄려면 설정 파일에 한 줄을 적어야 한다."""
    assert es_section(tmp_path).verify_certs is True


def test_turning_verification_off_reaches_the_client(monkeypatch, tmp_path):
    config = es_section(tmp_path, verify_certs=False)
    assert captured_kwargs(monkeypatch, config)["verify_certs"] is False


def test_turning_verification_off_is_logged(monkeypatch, tmp_path, caplog):
    """검증이 꺼진 채로 도는 실행은 로그만 봐도 알 수 있어야 한다."""
    config = es_section(tmp_path, verify_certs=False)
    with caplog.at_level("WARNING"):
        captured_kwargs(monkeypatch, config)
    assert "verification is OFF" in caplog.text


def test_a_verified_run_says_nothing_about_certificates(monkeypatch, tmp_path, caplog):
    with caplog.at_level("WARNING"):
        captured_kwargs(monkeypatch, es_section(tmp_path))
    assert "verification is OFF" not in caplog.text


def test_a_ca_bundle_with_verification_off_does_not_start(tmp_path):
    """CA 를 적어두고 검증을 끄면 CA 는 아무 일도 하지 않는다. 고르게 한다."""
    with pytest.raises(ConfigError, match="verify_certs"):
        es_section(tmp_path, ca_certs="/etc/ssl/internal.pem", verify_certs=False)


def test_the_masked_repr_still_hides_the_key_with_the_new_field(tmp_path):
    text = repr(es_section(tmp_path, verify_certs=False))
    assert "verify_certs=False" in text
    assert "dry-run" not in text
