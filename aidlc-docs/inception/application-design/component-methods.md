# 컴포넌트 메서드 (Component Methods)

**단위(Unit)**: `es-crawler`

> **범위 참고**: 이 문서는 **시그니처와 입출력 타입**만 정의합니다.
> 상세 비즈니스 규칙(경계 계산 규칙, 상태 전이 규칙, 누락 필드 처리 규칙 등)은
> CONSTRUCTION 단계의 **Functional Design**에서 정의합니다.

---

## 값 객체 (Value Objects)

```python
@dataclass(frozen=True)
class TimeWindow:
    start: datetime          # tz-aware, 포함(inclusive)
    end: datetime            # tz-aware, 제외(exclusive)

    @property
    def key(self) -> str: ...        # 체크포인트 키: end.isoformat()
    @property
    def label(self) -> str: ...      # 파일명용: end의 로컬 날짜 'YYYY-MM-DD'
    @property
    def duration(self) -> timedelta: ...


@dataclass(frozen=True)
class ColumnSpec:
    source: str              # 점 표기법 경로, 예: '_source.user.name'
    header: str              # CSV 헤더명


@dataclass(frozen=True)
class ChunkState:
    key: str
    status: Literal['done', 'failed']
    doc_count: int
    updated_at: datetime
    error: str | None = None
```

---

## `Config` (`config.py`)

```python
@dataclass(frozen=True)
class EsConfig:
    hosts: list[str]                 # .env
    api_key: str                     # .env
    request_timeout: float = 60.0
    max_retries: int = 3

@dataclass(frozen=True)
class QueryConfig:
    index: str
    time_field: str
    extra_filters: list[dict] = field(default_factory=list)
    batch_size: int = 1000           # scroll size
    scroll_ttl: str = '5m'

@dataclass(frozen=True)
class ChunkConfig:
    timezone: str = 'Asia/Seoul'     # D-2
    anchor_time: time = time(18, 0)  # D-1
    chunk_hours: int = 24            # <= 24 강제

@dataclass(frozen=True)
class OutputConfig:
    directory: Path
    columns: list[ColumnSpec]
    missing_value: str = ''

@dataclass(frozen=True)
class Config:
    es: EsConfig
    query: QueryConfig
    chunk: ChunkConfig
    output: OutputConfig


def load_config(config_path: Path, env_path: Path | None = None) -> Config: ...
    # YAML + .env 로드, 검증 수행. 검증 실패 시 ConfigError 발생
```

| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `load_config` | 설정 파일과 `.env`를 읽어 검증된 `Config` 생성 | YAML 경로, `.env` 경로(선택) | `Config` |

---

## `DateChunker` (`chunker.py`)

```python
class DateChunker:
    def __init__(self, config: ChunkConfig) -> None: ...

    def chunks(self, start: date | datetime, end: date | datetime) -> list[TimeWindow]: ...
    def default_window(self, now: datetime) -> TimeWindow: ...
    def window_for(self, target: date) -> TimeWindow: ...
```

| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `chunks` | 기간을 anchor 정렬 청크 목록으로 분할 | 시작·종료 | `list[TimeWindow]` (시간순) |
| `default_window` | 인자 없이 실행할 때의 기본 창 (D-1) | 현재 시각 | `TimeWindow` |
| `window_for` | 특정 날짜 하나에 대응하는 창 | 날짜 | `TimeWindow` |

**속성 테스트 대상 (PBT-03)**: `chunks` 결과의 합집합 = 요청 기간, 인접 청크 무겹침,
모든 청크 `duration <= 24h`, 시간순 정렬.

---

## `EsExtractor` (`extractor.py`)

```python
class EsExtractor:
    def __init__(self, client: Elasticsearch, config: QueryConfig) -> None: ...

    def build_query(self, window: TimeWindow) -> dict: ...
    def iter_documents(self, window: TimeWindow) -> Iterator[dict]: ...
    def count(self, window: TimeWindow) -> int: ...
```

| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `build_query` | 창 + 추가 필터로 ES 쿼리 본문 생성 (UTC 변환 포함) | `TimeWindow` | `dict` (ES query DSL) |
| `iter_documents` | scroll로 전체 히트를 스트리밍. 종료 시 컨텍스트 정리 보장 | `TimeWindow` | `Iterator[dict]` (히트 원본) |
| `count` | 창에 해당하는 문서 수 조회 (로깅·검증용) | `TimeWindow` | `int` |

**중요**: `iter_documents`는 `try/finally` 또는 컨텍스트 매니저로 `clear_scroll`을 보장합니다.
소비자가 중간에 순회를 멈춰도(예: 예외) 정리되어야 합니다.

---

## `JsonlWriter` (`writer.py`)

```python
class JsonlWriter:
    def __init__(self, directory: Path) -> None: ...

    def path_for(self, window: TimeWindow) -> Path: ...
    def write(self, window: TimeWindow, documents: Iterable[dict]) -> int: ...
    def exists(self, window: TimeWindow) -> bool: ...
```

| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `path_for` | 창에 대응하는 JSONL 경로 | `TimeWindow` | `Path` |
| `write` | 스트림을 임시 파일에 쓰고 완료 시 rename | 창, 문서 이터러블 | 쓴 문서 수 `int` |
| `exists` | 완성된 JSONL 존재 여부 | `TimeWindow` | `bool` |

**속성 테스트 대상 (PBT-02)**: 문서 리스트 → JSONL 쓰기 → 읽기 = 원본 (왕복).

---

## `CsvConverter` (`converter.py`)

```python
class CsvConverter:
    def __init__(self, columns: list[ColumnSpec], missing_value: str = '') -> None: ...

    def convert(self, jsonl_path: Path, csv_path: Path) -> int: ...
    def to_row(self, document: dict) -> list[str]: ...

    @staticmethod
    def extract_value(document: dict, path: str) -> Any | None: ...

    @property
    def headers(self) -> list[str]: ...
```

| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `convert` | JSONL 파일 전체를 CSV로 변환 | 입력·출력 경로 | 쓴 행 수 `int` |
| `to_row` | 문서 하나를 CSV 행으로 (순수 함수) | `dict` | `list[str]` |
| `extract_value` | 점 표기법 경로로 값 추출 (순수 함수) | 문서, 경로 | 값 또는 `None` |
| `headers` | 설정된 헤더명 목록 | - | `list[str]` |

**속성 테스트 대상 (PBT-03)**: 출력 행 수 = 입력 문서 수, 출력 컬럼 = `headers`,
모든 행의 길이 = `len(headers)`.

---

## `CheckpointStore` (`checkpoint.py`)

```python
class CheckpointStore:
    def __init__(self, path: Path) -> None: ...

    def load(self) -> dict[str, ChunkState]: ...
    def is_done(self, window: TimeWindow) -> bool: ...
    def mark_done(self, window: TimeWindow, doc_count: int) -> None: ...
    def mark_failed(self, window: TimeWindow, error: str) -> None: ...
    def pending(self, windows: list[TimeWindow]) -> list[TimeWindow]: ...
```

| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `load` | 상태 파일 로드 (없으면 빈 상태) | - | `dict[str, ChunkState]` |
| `is_done` | 해당 창이 완료되었는지 | `TimeWindow` | `bool` |
| `mark_done` | 완료 기록 후 원자적 저장 | 창, 문서 수 | - |
| `mark_failed` | 실패 기록 후 원자적 저장 | 창, 오류 메시지 | - |
| `pending` | 완료된 창을 제외한 목록 반환 | 창 목록 | `list[TimeWindow]` |

---

## `CrawlService` (`pipeline.py`)

```python
@dataclass
class ChunkResult:
    window: TimeWindow
    status: Literal['done', 'failed', 'skipped']
    doc_count: int = 0
    error: str | None = None

@dataclass
class Report:
    results: list[ChunkResult]

    @property
    def succeeded(self) -> int: ...
    @property
    def failed(self) -> int: ...
    @property
    def skipped(self) -> int: ...
    @property
    def total_documents(self) -> int: ...
    @property
    def ok(self) -> bool: ...      # failed == 0


class CrawlService:
    def __init__(self, config: Config, client: Elasticsearch | None = None) -> None: ...

    def extract(self, start: date | None = None, end: date | None = None) -> Report: ...
    def convert(self, start: date | None = None, end: date | None = None) -> Report: ...
    def run(self, start: date | None = None, end: date | None = None) -> Report: ...
```

| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `extract` | 청크 분할 → 완료분 제외 → 순차 추출 → JSONL 저장 → 체크포인트 기록 | 시작·종료(선택) | `Report` |
| `convert` | 해당 범위의 JSONL을 CSV로 일괄 변환 (Q3=B) | 시작·종료(선택) | `Report` |
| `run` | `extract` 후 `convert` (라이브러리 편의용, CLI 미노출) | 시작·종료(선택) | `Report` |

`start`/`end`가 `None`이면 `DateChunker.default_window()` 를 사용합니다 (D-1).
`client`가 `None`이면 `config.es`로 생성하고, 테스트에서는 가짜 클라이언트를 주입합니다 (Q6=A).

---

## `CLI` (`cli.py`)

```python
def main(argv: list[str] | None = None) -> int: ...
```

| 서브커맨드 | 인자 | 동작 |
|---|---|---|
| `extract` | `--from`, `--to`, `--config`, `--log-level` | `CrawlService.extract()` 호출 |
| `convert` | `--from`, `--to`, `--config`, `--log-level` | `CrawlService.convert()` 호출 |

| 종료 코드 | 의미 |
|---|---|
| `0` | 모든 청크 성공 (또는 이미 완료되어 건너뜀) |
| `1` | 하나 이상의 청크 실패 |
| `2` | 설정 오류, 연결 실패 등 실행 전 오류 |
