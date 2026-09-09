"""구간별 진행 상태.

중단된 지점부터 이어서 돌 수 있게 하는 유일한 장치다. 상태 파일이 없으면 처음부터,
있으면 남은 구간부터 시작한다.

기록 시점이 규칙이다. 파일을 확정한 **뒤에** 완료로 남긴다. 순서가 뒤집히면
"완료라고 적혀 있는데 파일은 없는" 상태가 생기고, 그 구간은 영원히 건너뛰어진다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .chunker import TimeWindow

VERSION = 1


class CheckpointError(Exception):
    """상태 파일을 읽을 수 없다.

    빈 상태로 넘어가지 않는다 — 그러면 이미 받은 구간을 전부 다시 조회하게 되고,
    구간을 잘게 나눈 목적과 정반대의 부하가 걸린다.
    """


@dataclass(frozen=True)
class ChunkState:
    key: str
    status: str
    doc_count: int
    updated_at: str
    error: str | None = None

    @property
    def done(self) -> bool:
        return self.status == "done"


class CheckpointStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._states: dict[str, ChunkState] | None = None

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, ChunkState]:
        if self._states is not None:
            return self._states
        if not self._path.is_file():
            self._states = {}
            return self._states

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            chunks = raw["chunks"]
            self._states = {
                key: ChunkState(
                    key=key,
                    status=value["status"],
                    doc_count=int(value.get("doc_count", 0)),
                    updated_at=str(value.get("updated_at", "")),
                    error=value.get("error"),
                )
                for key, value in chunks.items()
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CheckpointError(
                f"cannot read checkpoint {self._path}: {exc}\n"
                "  Fix or remove the file. Continuing would re-fetch every window."
            ) from exc
        return self._states

    def is_done(self, window: TimeWindow) -> bool:
        state = self.load().get(window.key)
        return state is not None and state.done

    def pending(self, windows: list[TimeWindow]) -> list[TimeWindow]:
        """아직 끝나지 않은 구간만. 실패한 구간은 다시 시도 대상이다."""
        states = self.load()
        return [w for w in windows if not (w.key in states and states[w.key].done)]

    def mark_done(self, window: TimeWindow, doc_count: int) -> None:
        self._put(ChunkState(window.key, "done", doc_count, _now(), None))

    def mark_failed(self, window: TimeWindow, error: str) -> None:
        self._put(ChunkState(window.key, "failed", 0, _now(), error[:500]))

    def _put(self, state: ChunkState) -> None:
        states = self.load()
        states[state.key] = state
        self._save(states)

    def _save(self, states: dict[str, ChunkState]) -> None:
        payload: dict[str, Any] = {
            "version": VERSION,
            "chunks": {
                key: {
                    "status": s.status,
                    "doc_count": s.doc_count,
                    "updated_at": s.updated_at,
                    "error": s.error,
                }
                for key, s in sorted(states.items())
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")
