"""공용 픽스처와 도메인 생성기.

데이터는 파일이 아니라 코드에서 나온다. 저장소에 픽스처 파일이 없으면 실수로
커밋될 파일 자체가 없고, 스키마를 고치면 테스트 데이터도 따라 바뀐다.

원시 타입만 흔드는 생성기는 의미 없는 사례만 만들어낸다. 여기 있는 것들은 실제
문서와 같은 모양을 만들며, 여러 테스트가 나눠 쓴다.
"""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from es_crawler.config import ChunkConfig, ColumnSpec, OutputConfig

# 실패한 사례를 최소 형태로 줄여주는 기능은 끄지 않는다. 실패 시 재현용 문구가
# 함께 출력되도록 print_blob 을 켠다.
settings.register_profile(
    "default",
    max_examples=200,
    deadline=None,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("default")

TZ = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")


# --------------------------------------------------------------- 도메인 생성기

timezones = st.sampled_from([TZ, UTC, ZoneInfo("America/New_York")])


@st.composite
def aware_datetimes(draw: Any, tz: ZoneInfo | None = None) -> datetime:
    """타임존이 붙은 시각. 서머타임 경계를 밟도록 여러 존을 섞는다."""
    zone = tz if tz is not None else draw(timezones)
    naive = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
        )
    )
    return naive.replace(tzinfo=zone)


@st.composite
def spans(draw: Any, max_days: int = 12) -> tuple[datetime, datetime]:
    """[start, end) 로 쓸 수 있는 시각 쌍. 항상 start < end 다."""
    zone = draw(timezones)
    start = draw(aware_datetimes(tz=zone))
    seconds = draw(st.integers(min_value=1, max_value=max_days * 24 * 3600))
    return start, start + timedelta(seconds=seconds)


@st.composite
def chunk_configs(draw: Any) -> ChunkConfig:
    return ChunkConfig(
        timezone=str(draw(timezones)),
        anchor_time=time(draw(st.integers(0, 23)), draw(st.sampled_from([0, 30]))),
        chunk_hours=draw(st.integers(min_value=1, max_value=24)),
    )


scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(min_size=0, max_size=40),
)

json_values = st.recursive(
    scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(min_size=1, max_size=8), children, max_size=4),
    ),
    max_leaves=8,
)

field_names = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=10,
)


@st.composite
def sources(draw: Any) -> dict[str, Any]:
    """문서 본문. 중첩과 배열이 실제처럼 섞여 나온다."""
    return draw(st.dictionaries(field_names, json_values, min_size=0, max_size=6))


@st.composite
def hits(draw: Any) -> dict[str, Any]:
    """검색 결과 한 건. 메타데이터와 본문을 모두 갖춘다."""
    return {
        "_index": draw(st.text(min_size=1, max_size=12)),
        "_id": draw(st.text(min_size=1, max_size=16)),
        "_score": draw(st.one_of(st.none(), st.floats(0, 10, allow_nan=False))),
        "_source": draw(sources()),
    }


@st.composite
def column_specs(draw: Any) -> list[ColumnSpec]:
    """서로 다른 헤더를 가진 컬럼 목록."""
    names = draw(st.lists(field_names, min_size=1, max_size=5, unique=True))
    return [ColumnSpec(source=n, header=f"col_{n}") for n in names]


# ------------------------------------------------------------------- 픽스처


@pytest.fixture
def tz() -> ZoneInfo:
    return TZ


@pytest.fixture
def output_config(tmp_path: Path) -> OutputConfig:
    return OutputConfig(
        directory=tmp_path,
        columns=[
            ColumnSpec("_id", "doc_id"),
            ColumnSpec("@timestamp", "timestamp"),
            ColumnSpec("user.name", "user_name"),
        ],
    )
