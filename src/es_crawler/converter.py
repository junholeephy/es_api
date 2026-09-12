"""JSONL 을 설정한 컬럼만 담은 CSV 로 바꾼다.

문서 전체를 펼치지 않는다. 설정에 적은 컬럼만 꺼내고, 헤더 이름도 설정이 정한다 —
설정이 곧 출력 스키마다.

값을 문자열로 만드는 판정 순서가 이 모듈의 규칙이다. 순서를 바꾸면 조용히 틀린
값이 나온다.
"""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import ColumnSpec, OutputConfig
from .schema import resolve

MISSING = object()
"""필드가 아예 없음. None(값이 null)과 구별해야 하므로 별도 표식을 쓴다."""


def extract_value(hit: dict[str, Any], path: str) -> Any:
    """히트에서 경로에 해당하는 값을 꺼낸다. 없으면 MISSING.

    경로 해석은 schema 에 한 벌만 둔다. 여기 따로 두면 한쪽만 고쳐지고, 그때부터
    스키마 선언에 쓸 수 있는 경로와 CSV 컬럼에 쓸 수 있는 경로가 달라진다.
    """
    return resolve(hit, path, MISSING)


class CsvConverter:
    def __init__(self, config: OutputConfig) -> None:
        self._config = config
        self._columns: list[ColumnSpec] = list(config.columns)

    @property
    def headers(self) -> list[str]:
        return [c.header for c in self._columns]

    def render(self, value: Any) -> str:
        """값 하나를 CSV 셀 문자열로.

        판정 순서가 규칙이다. bool 검사가 숫자 검사보다 뒤로 가면 True 가 1 로
        기록된다 — 파이썬에서 bool 이 int 의 하위 타입이기 때문이다.
        """
        if value is MISSING:
            return self._config.missing_value
        if value is None:
            return self._config.null_value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def to_row(self, hit: dict[str, Any]) -> list[str]:
        return [self.render(extract_value(hit, c.source)) for c in self._columns]

    def rows(self, hits: Iterable[dict[str, Any]]) -> Iterable[list[str]]:
        for hit in hits:
            yield self.to_row(hit)

    def convert(self, jsonl_path: Path, csv_path: Path) -> int:
        """JSONL 파일 하나를 CSV 로 바꾼다. 쓴 행 수를 돌려준다.

        한 줄씩 읽고 한 줄씩 쓴다. 파일 전체를 메모리에 올리지 않는다.
        임시 파일에 쓰고 마지막에 바꿔치기하므로 중간에 끊겨도 반쪽짜리 CSV 가
        남지 않는다.
        """
        tmp = csv_path.with_name(csv_path.name + ".tmp")
        rows = 0
        try:
            with (
                open(jsonl_path, encoding="utf-8") as src,
                open(tmp, "w", encoding=self._config.encoding, newline="") as dst,
            ):
                writer = csv.writer(dst)
                if self._config.write_header:
                    writer.writerow(self.headers)
                for line in src:
                    line = line.strip()
                    if not line:
                        continue
                    writer.writerow(self.to_row(json.loads(line)))
                    rows += 1
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(tmp, csv_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return rows
