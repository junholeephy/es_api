"""설정 로딩과 검증.

설정 파일을 읽는 유일한 지점이다. 다른 모듈은 여기서 만든 객체만 받는다 —
로딩 지점이 흩어지면 접속 정보 마스킹이 한 곳에서 빠진다.

검증은 전부 여기서, 어떤 조회도 하기 전에 끝난다. 30분 돌린 뒤 설정 하나 때문에
죽으면 그 실행을 통째로 버리게 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .schema import parse_path

MAX_CHUNK_HOURS = 24
METADATA_FIELDS = frozenset({"_id", "_index", "_score"})


class ConfigError(Exception):
    """설정이 잘못됐다. 어떤 계산도 시작하기 전에 죽는다."""


@dataclass(frozen=True)
class EsConfig:
    hosts: list[str]
    api_key: str
    request_timeout: float = 60.0
    max_retries: int = 3
    ca_certs: str | None = None
    # 끄면 상대가 누구인지 확인하지 않는다. 기본값은 켠 쪽이다 — 설정 파일에
    # 한 줄을 적어야만 꺼지게 해서, 꺼져 있다는 사실이 어딘가에 남게 한다.
    verify_certs: bool = True

    def __repr__(self) -> str:
        # 예외를 그대로 로깅할 때 이 객체가 딸려 나올 수 있다. 키는 절대 찍지 않는다.
        return (
            f"EsConfig(hosts={self.hosts!r}, api_key='***', "
            f"request_timeout={self.request_timeout!r}, "
            f"max_retries={self.max_retries!r}, ca_certs={self.ca_certs!r}, "
            f"verify_certs={self.verify_certs!r})"
        )


@dataclass(frozen=True)
class QueryConfig:
    index: str
    time_field: str
    batch_size: int = 2000
    scroll_ttl: str = "5m"
    extra_filters: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ChunkConfig:
    timezone: str = "Asia/Seoul"
    anchor_time: time = time(18, 0)
    chunk_hours: int = 24

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass(frozen=True)
class ColumnSpec:
    """CSV 컬럼 하나. source 는 값을 꺼낼 경로, header 는 파일에 쓸 이름이다."""

    source: str
    header: str

    @property
    def is_metadata(self) -> bool:
        return self.source in METADATA_FIELDS


@dataclass(frozen=True)
class OutputConfig:
    directory: Path
    columns: list[ColumnSpec]
    encoding: str = "utf-8-sig"
    write_header: bool = True
    missing_value: str = ""
    null_value: str = "NULL"
    schema_sample: int = 1000
    progress_every: int = 50000


@dataclass(frozen=True)
class Config:
    es: EsConfig
    query: QueryConfig
    chunk: ChunkConfig
    output: OutputConfig


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"{where}.{key} is required")
    return mapping[key]


def _parse_anchor(raw: Any) -> time:
    if isinstance(raw, time):
        return raw
    text = str(raw).strip()
    try:
        return time.fromisoformat(text)
    except ValueError as exc:
        raise ConfigError(f"chunk.anchor_time must be HH:MM (got {text!r})") from exc


def _build_columns(raw: Any) -> list[ColumnSpec]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("output.columns must be a non-empty list")

    columns: list[ColumnSpec] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"output.columns[{i}] must be a mapping")
        source = str(item.get("source", "")).strip()
        header = str(item.get("header", "")).strip()
        if not source:
            raise ConfigError(f"output.columns[{i}].source must not be empty")
        try:
            # 문법이 틀린 경로는 "값이 없다"로 조용히 흘러가 빈 칸으로만 보인다.
            # 30분 받아온 뒤에 알아채는 것보다 시작 전에 죽는 편이 낫다.
            parse_path(source)
        except ValueError as exc:
            raise ConfigError(f"output.columns[{i}].source: {exc}") from exc
        if not header:
            raise ConfigError(f"output.columns[{i}].header must not be empty")
        if header in seen:
            # 헤더가 겹치면 CSV 를 읽는 쪽에서 어느 컬럼인지 가릴 수 없다.
            raise ConfigError(f"duplicate CSV header: {header!r}")
        seen.add(header)
        columns.append(ColumnSpec(source=source, header=header))
    return columns


def _build_es(raw: dict[str, Any]) -> EsConfig:
    hosts = _require(raw, "hosts", "elasticsearch")
    if not isinstance(hosts, list) or not hosts:
        raise ConfigError("elasticsearch.hosts must be a non-empty list")

    api_key = str(raw.get("api_key") or "").strip()
    if not api_key:
        raise ConfigError("elasticsearch.api_key is not set")

    timeout = float(raw.get("request_timeout", 60))
    if timeout <= 0:
        raise ConfigError("elasticsearch.request_timeout must be positive")

    retries = int(raw.get("max_retries", 3))
    if retries < 0:
        raise ConfigError("elasticsearch.max_retries must not be negative")

    ca = raw.get("ca_certs") or None
    verify = bool(raw.get("verify_certs", True))
    if ca and not verify:
        # 둘 다 적혀 있으면 CA 쪽은 아무 일도 하지 않는다. 검증하고 있다고
        # 믿은 채로 도는 것이 가장 나쁘므로, 여기서 멈추고 고르게 한다.
        raise ConfigError(
            "elasticsearch.ca_certs has no effect while verify_certs is false; keep one"
        )

    return EsConfig(
        hosts=[str(h) for h in hosts],
        api_key=api_key,
        request_timeout=timeout,
        max_retries=retries,
        ca_certs=str(ca) if ca else None,
        verify_certs=verify,
    )


def _build_query(raw: dict[str, Any]) -> QueryConfig:
    index = str(_require(raw, "index", "query")).strip()
    if not index:
        raise ConfigError("query.index must not be empty")

    time_field = str(_require(raw, "time_field", "query")).strip()
    if not time_field:
        raise ConfigError("query.time_field must not be empty")

    batch_size = int(raw.get("batch_size", 2000))
    if not 1 <= batch_size <= 10000:
        raise ConfigError(f"query.batch_size must be between 1 and 10000 (got {batch_size})")

    filters = raw.get("extra_filters") or []
    if not isinstance(filters, list):
        raise ConfigError("query.extra_filters must be a list of query clauses")

    return QueryConfig(
        index=index,
        time_field=time_field,
        batch_size=batch_size,
        scroll_ttl=str(raw.get("scroll_ttl", "5m")),
        extra_filters=list(filters),
    )


def _build_chunk(raw: dict[str, Any]) -> ChunkConfig:
    tz_name = str(raw.get("timezone", "Asia/Seoul"))
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"unknown timezone: {tz_name!r}") from exc

    hours = int(raw.get("chunk_hours", 24))
    if not 1 <= hours <= MAX_CHUNK_HOURS:
        # 한 번의 조회가 덮는 시간 폭에 상한이 있다. 넘기면 시작하지 않는다.
        raise ConfigError(
            f"chunk.chunk_hours must be between 1 and {MAX_CHUNK_HOURS} (got {hours})"
        )

    return ChunkConfig(
        timezone=tz_name,
        anchor_time=_parse_anchor(raw.get("anchor_time", "18:00")),
        chunk_hours=hours,
    )


def _build_output(raw: dict[str, Any]) -> OutputConfig:
    directory = Path(str(raw.get("directory", "outputs"))).expanduser()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"cannot create output directory: {directory} ({exc})") from exc

    sample = int(raw.get("schema_sample", 1000))
    if sample < 0:
        raise ConfigError("output.schema_sample must not be negative")

    every = int(raw.get("progress_every", 50000))
    if every < 1:
        raise ConfigError("output.progress_every must be at least 1")

    return OutputConfig(
        directory=directory,
        columns=_build_columns(_require(raw, "columns", "output")),
        encoding=str(raw.get("encoding", "utf-8-sig")),
        write_header=bool(raw.get("write_header", True)),
        missing_value=str(raw.get("missing_value", "")),
        null_value=str(raw.get("null_value", "NULL")),
        schema_sample=sample,
        progress_every=every,
    )


def build_config(raw: dict[str, Any]) -> Config:
    """이미 읽어들인 매핑에서 설정을 만든다. 파일 접근이 없어 테스트하기 쉽다."""
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")

    return Config(
        es=_build_es(dict(_require(raw, "elasticsearch", "config"))),
        query=_build_query(dict(_require(raw, "query", "config"))),
        chunk=_build_chunk(dict(raw.get("chunk") or {})),
        output=_build_output(dict(_require(raw, "output", "config"))),
    )


def load_config(path: str | Path) -> Config:
    """설정 파일을 읽어 검증된 Config 를 돌려준다. 실패하면 ConfigError."""
    path = Path(path).expanduser()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config: {path} ({exc})") from exc

    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"cannot parse config: {path} ({exc})") from exc

    return build_config(raw)
