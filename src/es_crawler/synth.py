"""스키마에서 파생된 합성 문서 생성기.

가짜 데이터는 파일이 아니라 코드로 존재한다. 저장소에 데이터 파일이 없으면
실수로 커밋될 파일 자체가 없다. 테스트도 픽스처 파일 대신 이 함수를 부른다.

덤으로, 클러스터에 붙지 않고도 전 구간을 한 번 돌려볼 수 있다.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from typing import Any

from .schema import INPUT_SCHEMA, METADATA_FIELDS, Field


def _scalar(field: Field, rng: random.Random, when: datetime) -> Any:
    if field.allowed:
        return rng.choice(list(field.allowed))
    if field.dtype == "datetime":
        return when.isoformat()
    if field.dtype == "bool":
        return rng.choice([True, False])
    if field.dtype == "int":
        lo, hi = field.rng or (0, 1000)
        return rng.randint(int(lo), int(hi))
    if field.dtype == "float":
        lo, hi = field.rng or (0.0, 1000.0)
        return round(rng.uniform(lo, min(hi, lo + 1e6)), 4)
    return "".join(rng.choices(string.ascii_lowercase + string.digits, k=10))


def _assign(source: dict[str, Any], path: str, value: Any) -> None:
    """점 경로를 따라 중첩 매핑에 값을 넣는다."""
    parts = path.split(".")
    node = source
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value


def _corrupt(hit: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """실제 문서에서 나타나는 사고 유형을 주입한다.

    새 유형을 만나면 여기에 추가한다. 그러면 다음부터는 합성 데이터에서 미리 터진다.
    """
    field = rng.choice(INPUT_SCHEMA)
    if field.path in METADATA_FIELDS:
        return hit

    source = hit["_source"]
    kind = rng.randrange(5)
    if kind == 0:
        _assign(source, field.path, "1,234")
    elif kind == 1:
        _assign(source, field.path, None)
    elif kind == 2:
        parts = field.path.split(".")
        node = source
        for part in parts[:-1]:
            node = node.get(part) if isinstance(node.get(part), dict) else {}
        node.pop(parts[-1], None)
    elif kind == 3:
        _assign(source, field.path, {"unexpected": "object"})
    else:
        _assign(source, field.path, ["a", "b"])
    return hit


def generate(
    n: int = 1000,
    seed: int = 0,
    mode: str = "normal",
    index: str = "synthetic-000001",
    start: datetime | None = None,
) -> list[dict[str, Any]]:
    """스키마를 읽어 합성 히트를 만든다. 같은 seed 는 같은 결과를 준다."""
    rng = random.Random(seed)
    base = start or datetime(2026, 1, 1)

    hits: list[dict[str, Any]] = []
    for i in range(n):
        when = base + timedelta(seconds=i)
        source: dict[str, Any] = {}
        hit: dict[str, Any] = {
            "_index": index,
            "_id": f"{seed:04d}-{i:08d}",
            "_score": None,
            "_source": source,
        }
        for field in INPUT_SCHEMA:
            if field.path in METADATA_FIELDS:
                continue
            if field.nullable and rng.random() < 0.05:
                _assign(source, field.path, None)
                continue
            _assign(source, field.path, _scalar(field, rng, when))

        if mode == "adversarial" and rng.random() < 0.1:
            hit = _corrupt(hit, rng)
        hits.append(hit)
    return hits


class FakeSearchClient:
    """합성 문서를 돌려주는 대역.

    클러스터에 붙지 않고 전 구간을 돌려보기 위한 것이다. 실제 클라이언트와 같은
    세 메서드만 흉내내며, 조회 상태를 실제로 붙잡았다가 놓는 것까지 따라 한다 —
    그래야 정리 호출이 빠졌는지를 여기서 확인할 수 있다.
    """

    def __init__(self, hits: list[dict[str, Any]], page: int = 500) -> None:
        self._hits = hits
        self._page = max(1, page)
        self._cursors: dict[str, int] = {}
        self.released: list[str] = []
        self._next_id = 0

    def search(self, *, index: str, body: dict[str, Any], scroll: str) -> dict[str, Any]:
        self._next_id += 1
        scroll_id = f"fake-scroll-{self._next_id}"
        self._cursors[scroll_id] = 0
        return self._page_for(scroll_id, int(body.get("size", self._page)))

    def scroll(self, *, scroll_id: str, scroll: str) -> dict[str, Any]:
        return self._page_for(scroll_id, self._page)

    def clear_scroll(self, *, scroll_id: str) -> dict[str, Any]:
        self.released.append(scroll_id)
        self._cursors.pop(scroll_id, None)
        return {"succeeded": True}

    def count(self, *, index: str, query: dict[str, Any]) -> dict[str, Any]:
        return {"count": len(self._hits)}

    @property
    def open_contexts(self) -> int:
        return len(self._cursors)

    def _page_for(self, scroll_id: str, size: int) -> dict[str, Any]:
        start = self._cursors.get(scroll_id, len(self._hits))
        stop = min(start + size, len(self._hits))
        self._cursors[scroll_id] = stop
        return {"_scroll_id": scroll_id, "hits": {"hits": self._hits[start:stop]}}


def dry_run_config(directory: Any, sample: int = 1000) -> dict[str, Any]:
    """합성 실행에 쓸 설정 매핑. 스키마에서 컬럼을 그대로 뽑아 만든다."""
    return {
        "elasticsearch": {"hosts": ["http://localhost:9200"], "api_key": "dry-run"},
        "query": {"index": "synthetic-*", "time_field": "@timestamp", "batch_size": 500},
        "chunk": {"timezone": "Asia/Seoul", "anchor_time": "18:00", "chunk_hours": 24},
        "output": {
            "directory": str(directory),
            "schema_sample": sample,
            "progress_every": 50000,
            "columns": [
                {"source": f.path, "header": f.path.replace(".", "_")} for f in INPUT_SCHEMA
            ],
        },
    }
