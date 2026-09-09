"""Elasticsearch 접근. 입력이 어떤 모양으로 도착하는지 아는 유일한 곳이다.

바깥 시스템에 의존하는 코드를 여기 한 곳에 몰아둔다. 나머지 모듈은 파일과 순수한
데이터만 다루므로 클러스터 없이 테스트할 수 있다.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from elasticsearch import Elasticsearch

from .chunker import TimeWindow
from .config import EsConfig, QueryConfig

log = logging.getLogger(__name__)


def build_client(config: EsConfig) -> Elasticsearch:
    """재시도를 이 한 계층에만 둔다.

    애플리케이션 쪽에 재시도 루프를 겹치면 실제 대기 시간이 곱으로 늘어난다 —
    3회 x 3회 = 9회. 그동안 다음 구간은 시작조차 못 한다. 여기서 회복되지 않은
    실패만 위로 올라가고, 그것은 다음 실행에서 다시 시도된다.
    """
    kwargs: dict[str, Any] = {
        "hosts": config.hosts,
        "api_key": config.api_key,
        "request_timeout": config.request_timeout,
        "max_retries": config.max_retries,
        "retry_on_timeout": True,
        "retry_on_status": (429, 502, 503, 504),
    }
    if config.ca_certs:
        kwargs["ca_certs"] = config.ca_certs
    return Elasticsearch(**kwargs)


class EsExtractor:
    def __init__(self, client: Elasticsearch, config: QueryConfig) -> None:
        self._client = client
        self._config = config

    def build_query(self, window: TimeWindow) -> dict[str, Any]:
        """구간에 해당하는 조회 본문.

        gte / lt 를 쓴다. lte 를 쓰면 경계에 놓인 문서가 이웃한 두 구간에 모두
        걸려 중복된다.

        시각은 오프셋을 붙인 문자열로 그대로 보낸다. Elasticsearch 가 UTC 로
        정규화하므로, 손으로 변환하는 코드를 두지 않는다.
        """
        filters: list[dict[str, Any]] = [
            {
                "range": {
                    self._config.time_field: {
                        "gte": window.start.isoformat(),
                        "lt": window.end.isoformat(),
                    }
                }
            }
        ]
        filters.extend(self._config.extra_filters)
        return {
            "query": {"bool": {"filter": filters}},
            "size": self._config.batch_size,
            # 점수를 매기지 않고 색인 순서대로 훑는다. 이 조회 방식에서 가장 싸다.
            "sort": ["_doc"],
        }

    def count(self, window: TimeWindow) -> int:
        body = self.build_query(window)
        result = self._client.count(index=self._config.index, query=body["query"])
        return int(result["count"])

    def iter_documents(self, window: TimeWindow) -> Generator[dict[str, Any]]:
        """구간 하나의 문서를 순서대로 흘려보낸다.

        받은 것을 모아두지 않고 그때그때 넘긴다. 백만 건을 리스트로 들면 수 GB 다.

        조회 상태는 서버 메모리에 남으므로 반드시 정리해야 한다. finally 에 두어
        정상 종료든 예외든 중간에 멈추든 한 번은 지우게 한다. 다만 호출하는 쪽이
        끝까지 소비하지 않으면 finally 가 바로 돌지 않으므로, 이 제너레이터는
        contextlib.closing 으로 감싸서 써야 한다.
        """
        response = self._client.search(
            index=self._config.index,
            body=self.build_query(window),
            scroll=self._config.scroll_ttl,
        )
        scroll_id = response.get("_scroll_id")
        try:
            while True:
                hits = response["hits"]["hits"]
                if not hits:
                    break
                yield from hits
                response = self._client.scroll(scroll_id=scroll_id, scroll=self._config.scroll_ttl)
                # 응답마다 바뀔 수 있다. 첫 값만 들고 정리하면 실제 상태가 남는다.
                scroll_id = response.get("_scroll_id", scroll_id)
        finally:
            self._release(scroll_id)

    def _release(self, scroll_id: str | None) -> None:
        if not scroll_id:
            return
        try:
            self._client.clear_scroll(scroll_id=scroll_id)
        except Exception as exc:
            # 정리에 실패했다고 해서 이미 받아온 결과를 실패로 바꾸지는 않는다.
            log.warning("could not release search context: %s", exc)
