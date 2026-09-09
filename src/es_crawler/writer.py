"""받아온 문서를 구간마다 JSONL 파일 하나로 남긴다.

받은 그대로 저장한다. 나중에 CSV 규칙을 고쳐도 다시 조회할 필요가 없도록,
메타데이터를 포함한 히트 객체 전체를 한 줄에 하나씩 쓴다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .chunker import TimeWindow


class JsonlWriter:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, window: TimeWindow) -> Path:
        return self._directory / f"data-{window.slug}.jsonl"

    def csv_path_for(self, window: TimeWindow) -> Path:
        return self._directory / f"data-{window.slug}.csv"

    def exists(self, window: TimeWindow) -> bool:
        """완성된 파일이 있는가.

        임시 파일(.tmp)은 여기에 걸리지 않는다. 쓰다 만 것을 결과로 오해하지
        않으려면 최종 이름만 봐야 한다.
        """
        return self.path_for(window).is_file()

    def write(self, window: TimeWindow, documents: Iterable[dict[str, Any]]) -> int:
        """구간 하나를 파일로 남기고 쓴 문서 수를 돌려준다.

        임시 파일에 전부 쓰고 마지막에 이름을 바꾼다. 그래서 최종 이름을 가진
        파일은 언제나 완성본이다 — 도중에 죽으면 임시 파일만 남고, 그 이름은
        어디에서도 조회되지 않는다.

        문서가 없어도 빈 파일을 만든다. "조회했더니 없었다"와 "아직 조회하지
        않았다"는 다른 상태이고, 파일이 없으면 그 둘을 구별할 수 없다.
        """
        self._directory.mkdir(parents=True, exist_ok=True)
        final = self.path_for(window)
        tmp = final.with_name(final.name + ".tmp")

        count = 0
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                for document in documents:
                    handle.write(json.dumps(document, ensure_ascii=False))
                    handle.write("\n")
                    count += 1
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, final)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return count


def count_lines(path: Path) -> int:
    """이미 있는 파일의 문서 수를 센다. 진행 상태를 메울 때 쓴다."""
    total = 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                total += 1
    return total
