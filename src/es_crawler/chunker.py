"""시간 구간을 자르는 순수 로직.

여기에는 입출력이 없다. 그래서 이 모듈이 이 프로그램에서 가장 조용히 틀릴 수 있는
곳이기도 하다 — 경계가 하나 어긋나면 문서가 빠지거나 겹치는데, 둘 다 로그에는
아무것도 남지 않는다. 구간은 전부 반개구간 [start, end) 로 다룬다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import MAX_CHUNK_HOURS, ChunkConfig

MAX_DURATION = timedelta(hours=MAX_CHUNK_HOURS)


@dataclass(frozen=True)
class TimeWindow:
    """조회 한 번이 덮는 구간. start 는 포함, end 는 제외한다."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("TimeWindow bounds must be timezone-aware")
        # 두 끝의 UTC 오프셋이 달라도 된다. 서머타임을 넘는 구간이 그렇고, 그런 구간도
        # 정상이다 — 길이는 벽시계가 아니라 절대 시간으로 잰다.
        #
        # 비교도 절대 시간으로 한다. 같은 타임존의 두 시각을 그냥 비교하면 파이썬은
        # 벽시계로 판단하므로, 서머타임이 끝나는 날 두 번 오는 01:00 이 서로 같다고
        # 나온다 — 실제로는 한 시간 떨어진 서로 다른 순간이다.
        if self.start.astimezone(UTC) >= self.end.astimezone(UTC):
            raise ValueError(f"TimeWindow start must precede end: {self.start} >= {self.end}")
        elapsed = self.end.astimezone(UTC) - self.start.astimezone(UTC)
        if elapsed > MAX_DURATION:
            raise ValueError(
                f"TimeWindow may not span more than {MAX_CHUNK_HOURS}h (got {elapsed})"
            )

    @property
    def key(self) -> str:
        """진행 상태를 기록할 때 쓰는 키. 구간마다 유일하다."""
        return self.end.isoformat()

    @property
    def slug(self) -> str:
        """파일명 조각. key 에서 콜론만 뺀 것이다.

        날짜만 쓰면 서로 다른 구간이 같은 이름을 갖는다 — 구간이 하루보다 짧거나
        경계 시각이 다르면 조용히 덮어쓴다. 그러면 기록에는 둘 다 끝났다고 남는데
        파일은 하나뿐인 상태가 되고, 로그에는 아무것도 나오지 않는다.

        key 에서 파생시키는 이유는 그 성질을 공짜로 얻기 위해서다 — 콜론을 빼는 것은
        되돌릴 수 있는 변환이므로, 키가 다르면 이름도 반드시 다르다. 시각을 잘라
        쓰면(예: 분까지만) 그 보장이 사라진다.
        """
        return self.key.replace(":", "")

    @property
    def duration(self) -> timedelta:
        """실제로 흐른 시간.

        같은 타임존의 두 시각을 그냥 빼면 파이썬은 **벽시계 차이**를 준다. 서머타임이
        끝나는 날 01:00 은 두 번 오므로, 벽시계로 한 시간인 구간이 실제로는 두 시간을
        덮는다. 한 번의 조회가 덮는 양에 상한을 두는 것이 목적이므로 절대 시간으로 잰다.
        """
        return self.end.astimezone(UTC) - self.start.astimezone(UTC)

    def __str__(self) -> str:
        return f"{self.start.isoformat()} .. {self.end.isoformat()}"


def parse_boundary(text: str, tz: ZoneInfo) -> datetime:
    """명령줄에서 받은 시각을 해석한다.

    날짜만으로는 어느 구간인지 정해지지 않는다 — 하루의 경계가 자정이 아닐 수 있기
    때문이다. 그래서 시각까지 요구한다. 타임존을 생략하면 설정의 것을 붙인다.
    """
    raw = text.strip()
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"cannot parse datetime {raw!r}; expected e.g. 2026-09-01T18:00") from exc

    if parsed.time() == time(0, 0) and "T" not in raw and " " not in raw:
        raise ValueError(
            f"{raw!r} has no time component; write e.g. {raw}T18:00 "
            "(a date alone does not identify a window)"
        )

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)


class DateChunker:
    """요청 구간을 chunk_hours 단위로 자른다."""

    def __init__(self, config: ChunkConfig) -> None:
        self._config = config
        self._tz = config.tz
        self._size = timedelta(hours=config.chunk_hours)

    @property
    def tz(self) -> ZoneInfo:
        return self._tz

    def chunks(self, start: datetime, end: datetime) -> list[TimeWindow]:
        """[start, end) 를 이어붙은 구간 목록으로 나눈다.

        구간들의 합집합은 정확히 [start, end) 이고 서로 겹치지 않는다.
        마지막 구간은 chunk_hours 보다 짧을 수 있다 — 요청 범위를 넘지 않기 위해서다.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("chunk bounds must be timezone-aware")
        if start >= end:
            raise ValueError(f"start must precede end: {start} >= {end}")

        # 절대 시간으로 자른다. 지역 시각에 timedelta 를 더하면 벽시계 산술이 되어,
        # 서머타임이 끝나는 날 한 조각이 두 시간을 덮게 된다 — 상한을 두는 의미가 없어진다.
        zone = start.tzinfo
        cursor_utc = start.astimezone(UTC)
        end_utc = end.astimezone(UTC)

        windows: list[TimeWindow] = []
        while cursor_utc < end_utc:
            edge_utc = min(cursor_utc + self._size, end_utc)
            windows.append(TimeWindow(cursor_utc.astimezone(zone), edge_utc.astimezone(zone)))
            cursor_utc = edge_utc
        return windows

    def default_window(self, now: datetime) -> tuple[datetime, datetime]:
        """인자 없이 실행할 때 쓸 구간.

        기준 시각(anchor)이 오늘 이미 지났으면 그 시각까지의 24시간을, 아직이면
        어제 기준 시각까지의 24시간을 돌려준다. 아직 끝나지 않은 하루를 반쯤
        잘라오는 일이 없다.
        """
        local = now.astimezone(self._tz)
        today_edge = datetime.combine(local.date(), self._config.anchor_time, tzinfo=self._tz)
        edge = today_edge if local >= today_edge else today_edge - timedelta(days=1)
        return edge - timedelta(hours=24), edge

    def window_for(self, day: datetime) -> TimeWindow:
        """어떤 날짜의 기준 시각으로 끝나는 24시간 구간."""
        edge = datetime.combine(
            day.astimezone(self._tz).date(), self._config.anchor_time, tzinfo=self._tz
        )
        return TimeWindow(edge - timedelta(hours=24), edge)
