"""입력 문서의 형태에 대해 아는 것의 유일한 출처.

받아온 문서가 여기 적은 형태와 다르면 그 사실이 실행 요약에 뜬다. 화면에 뜨는 줄을
사람이 그대로 옮겨 적을 수 있어야 하므로, "형식이 틀렸습니다" 같은 요약 메시지는
여기서 결함이다 — 옮겨 적을 것이 없기 때문이다.

적는 것은 구조뿐이다: 경로 / 타입 / 널 허용 / 허용값 / 범위.
실제 값·분포·식별 가능한 코드값은 적지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

METADATA_FIELDS = frozenset({"_id", "_index", "_score"})


@dataclass(frozen=True)
class Field:
    path: str
    dtype: str
    nullable: bool
    allowed: tuple[Any, ...] | None = None
    rng: tuple[float, float] | None = None
    note: str = ""
    used: bool = True


################################################################################
# TODO: INPUT_SCHEMA 를 실제 인덱스의 문서 형태에 맞게 고친다.
#
#   path      _source 안의 경로를 점으로 잇는다. _id / _index / _score 는
#             히트 최상위 메타데이터에서 읽는다
#   dtype     "int" | "float" | "str" | "bool" | "datetime"
#   nullable  False = 값이 반드시 있어야 한다
#   allowed   허용값 튜플 (선택)
#   rng       (min, max) 범위 (선택, int/float)
#   note      실제 문서에서 확인한 사실을 적는 자리
#   used      False = 형태가 어긋나도 CSV 결과에는 영향이 없다
################################################################################
INPUT_SCHEMA: tuple[Field, ...] = (
    Field("_id", "str", False, note="Elasticsearch 문서 id"),
    Field("@timestamp", "datetime", False, note="시간 범위 필터가 이 필드를 쓴다"),
    Field("user.name", "str", True),
)
################################################################################


@dataclass(frozen=True)
class Report:
    """대조 결과.

    위반은 "CSV 결과가 틀렸을 수 있다"는 뜻이고, 노트는 "어긋났지만 결과에는
    영향이 없다"는 뜻이다. 둘을 섞으면 매 실행마다 뜨는 줄이 생기고, 사람은 곧
    그 줄 자체를 안 보게 된다.
    """

    violations: list[str]
    notes: list[str]
    sampled: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations


_MISSING = object()


_SEGMENT = re.compile(r"^(?P<name>[^\[\]]*)(?P<idx>(?:\[-?\d+\])*)$")
_INDEX = re.compile(r"\[(-?\d+)\]")


@lru_cache(maxsize=256)
def parse_path(path: str) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """점 경로를 (이름, 인덱스들) 단계로 쪼갠다. 문법이 틀리면 ValueError.

    `a.b` 는 물론 `messages[-1].content` 처럼 리스트에서 하나를 고르는 것도 된다.
    음수는 뒤에서 센다 — 대화 이력처럼 길이가 매번 다른 리스트에서 마지막 하나를
    집을 때 쓴다.

    설정을 읽을 때 여기서 한 번 검증한다. 문법이 틀린 경로를 그냥 두면 "값이
    없다"로 조용히 흘러가고, 그건 빈 칸으로만 보여서 알아채기 어렵다.

    1행마다 컬럼 수만큼 불리므로 결과를 캐시한다. 경로는 설정에서 오는 몇 개뿐이다.
    """
    if not path:
        raise ValueError("path must not be empty")
    steps: list[tuple[str, tuple[int, ...]]] = []
    for part in path.split("."):
        matched = _SEGMENT.match(part)
        if matched is None:
            raise ValueError(f"bad path segment {part!r} in {path!r}")
        name = matched.group("name")
        indices = tuple(int(n) for n in _INDEX.findall(matched.group("idx")))
        if not name and not indices:
            raise ValueError(f"empty path segment in {path!r}")
        steps.append((name, indices))
    return tuple(steps)


def resolve(hit: dict[str, Any], path: str, default: Any = _MISSING) -> Any:
    """히트에서 경로에 해당하는 값을 꺼낸다. 없으면 default.

    기본값을 주지 않으면 _MISSING 을 돌려준다 — 대조하는 쪽은 "필드가 없음"과
    "값이 null" 을 갈라야 하기 때문이다. 기능(features/)처럼 그 구분이 필요 없는
    쪽은 default 를 주면 모듈 private 인 _MISSING 을 알 필요가 없다.
    """
    if path in METADATA_FIELDS:
        return hit.get(path, default)

    node: Any = hit.get("_source")
    if not isinstance(node, dict):
        return default
    try:
        steps = parse_path(path)
    except ValueError:
        # 문법이 틀린 경로는 여기서 죽이지 않는다. 설정에서 온 경로는 읽을 때
        # 이미 검증했고(config), 30분 받아온 뒤에 터지면 그 실행을 통째로 버린다.
        return default
    for name, indices in steps:
        if name:
            if not isinstance(node, dict) or name not in node:
                return default
            node = node[name]
        for i in indices:
            # 문자열은 인덱스가 먹지만 글자 하나를 돌려준다. 의도한 적이 없다.
            if not isinstance(node, (list, tuple)):
                return default
            try:
                node = node[i]
            except IndexError:
                return default
    return node


def _matches(value: Any, dtype: str) -> bool:
    if dtype == "bool":
        return isinstance(value, bool)
    if dtype == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if dtype == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if dtype == "str":
        return isinstance(value, str)
    if dtype == "datetime":
        if isinstance(value, datetime):
            return True
        if not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True
    return True


def _field_messages(f: Field, hits: list[dict[str, Any]]) -> list[str]:
    """한 필드의 어긋남을 사람이 그대로 옮겨 적을 수 있는 한 줄씩으로."""
    missing = nulls = bad_type = out_of_range = 0
    unexpected: set[Any] = set()

    for hit in hits:
        value = resolve(hit, f.path)
        if value is _MISSING:
            missing += 1
            continue
        if value is None:
            nulls += 1
            continue
        if not _matches(value, f.dtype):
            bad_type += 1
            continue
        if f.allowed is not None and value not in f.allowed:
            unexpected.add(value)
        if (
            f.rng is not None
            and isinstance(value, (int, float))
            and not f.rng[0] <= value <= f.rng[1]
        ):
            out_of_range += 1

    label = f.path[:20]
    out: list[str] = []
    if missing:
        out.append(f"{label:<20}: {missing:,} docs missing this field")
    if nulls and not f.nullable:
        out.append(f"{label:<20}: {nulls:,} nulls but nullable=False")
    if bad_type:
        out.append(f"{label:<20}: dtype {f.dtype} expected, {bad_type:,} docs did not match")
    if unexpected:
        shown = sorted(str(v) for v in unexpected)[:5]
        more = "" if len(unexpected) <= 5 else f" (+{len(unexpected) - 5} more)"
        out.append(f"{label:<20}: unexpected values {set(shown)}{more}")
    if out_of_range:
        out.append(f"{label:<20}: {out_of_range:,} docs outside {f.rng}")
    return out


def validate(hits: list[dict[str, Any]]) -> Report:
    """표본을 스키마와 대조한다.

    전수 검사가 아니다. 목적은 품질 보증이 아니라 "받아온 문서가 내 가정과
    다른가"를 알아내는 것이고, 그 목적에는 표본으로 충분하다. 표본이었다는 사실은
    실행 요약에 함께 찍는다 — 표기가 없으면 "한 건도 안 틀렸다"로 읽힌다.
    """
    if not hits:
        return Report([], ["(schema)          : no documents sampled"], 0)

    violations: list[str] = []
    notes: list[str] = []
    for f in INPUT_SCHEMA:
        (violations if f.used else notes).extend(_field_messages(f, hits))
    return Report(violations, notes, len(hits))
