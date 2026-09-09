# Application Design (통합본)

**프로젝트**: Elasticsearch 데이터 추출 도구 (es_api)
**단위(Unit)**: `es-crawler`
**단계**: INCEPTION - Application Design
**작성일**: 2026-09-09

이 문서는 아래 4개 설계 문서를 하나로 모은 통합본입니다.
- `components.md` — 컴포넌트 정의와 책임
- `component-methods.md` — 메서드 시그니처
- `services.md` — 서비스 계층과 오케스트레이션
- `component-dependency.md` — 의존 관계와 데이터 흐름

---

## 개요

Elasticsearch 8.15.3에서 지정 기간의 문서를 **anchor(기본 18:00 KST)에 정렬된 24시간 청크**로 나누어
scroll API로 순차 추출하고, 청크마다 JSONL 파일로 보존한 뒤, 별도 명령으로 설정된 컬럼만 CSV로 변환하는
Python 패키지입니다. 체크포인트를 통해 중단 지점부터 재개할 수 있습니다.

**설계의 중심 아이디어 세 가지**

1. **추출과 변환의 완전한 분리** — JSONL을 디스크에 보존하므로(CQ4=A), 변환 로직을 고쳐도
   Elasticsearch에 다시 질의하지 않습니다. `convert` 흐름에는 ES 의존이 아예 등장하지 않습니다.
2. **외부 의존의 격리** — `elasticsearch-py`에 의존하는 컴포넌트는 `EsExtractor` 하나뿐입니다.
   나머지 컴포넌트는 파일과 순수 데이터만 다루므로 ES 없이 테스트할 수 있습니다.
3. **조합 책임의 집중** — 컴포넌트끼리는 서로를 참조하지 않고, 조합은 `CrawlService`가 전담합니다.
   의존 그래프가 단방향 비순환(DAG)이 됩니다.

---

# 제1부: 컴포넌트 정의

**단위(Unit)**: `es-crawler`
**패키지**: `es_crawler/`

---

### 설계 결정 요약 (Application Design Plan 답변 반영)

| # | 결정 | 근거 |
|---|---|---|
| Q1=A | 9개 모듈로 분리 유지 | 각 모듈 단일 책임, 테스트 용이 |
| Q2=B | CLI 서브커맨드 **2개**: `extract`, `convert` (`run` 없음) | 단계 분리를 CLI에서도 명확히 강제 |
| Q3=B | CSV 변환은 **전체 추출 후 일괄** | 추출/변환 단계가 완전히 분리됨 |
| Q4=A | 설정 파일 **YAML** (`PyYAML`) | 컬럼 매핑의 가독성 |
| Q5=C | 라이브러리는 **`CrawlService` 클래스** 공개, `.extract()` / `.convert()` / `.run()` | 서비스 하나로 진입 |
| Q6=A | `elasticsearch-py` **직접 사용** (추가 추상화 없음) | YAGNI, 테스트는 클라이언트 모킹 |
| Q7=A | 체크포인트는 **출력 디렉터리 내 JSON 파일**, 원자적 쓰기 | 단순 + 손상 방지 |
| Q8=A | 청크 키는 **창의 종료 시각 ISO 8601 (타임존 포함)** | 청크 크기를 바꿔도 키가 충돌하지 않음 |

#### 파생 결정 (D-3): `convert`의 대상 범위
Q2=B로 `run` 서브커맨드가 없으므로, `convert`가 어떤 JSONL을 변환할지 정해야 합니다.
**결정**: `convert`는 `extract`와 **동일한 날짜 범위 인자**를 받고, 그 범위의 청크에 대응하는
JSONL 파일만 변환합니다. 인자가 없으면 `extract`와 같은 기본 창(전날 18:00 ~ 당일 18:00)을 씁니다.
대상 JSONL이 없으면 경고 후 건너뜁니다(오류 아님).

#### 파생 결정 (D-4): 스케줄러 호출 방식
Q2=B이므로 매일 19:00 KST에 두 명령을 이어서 실행합니다.

```
python -m es_crawler extract && python -m es_crawler convert
```

`&&` 로 연결해 추출이 실패하면 변환을 시도하지 않습니다 (FR-9의 종료 코드 요구와 맞물림).

---

### 공통 값 객체 (Value Objects)

#### `TimeWindow`
청크 하나를 나타내는 불변 값 객체. **반개구간 `[start, end)`** 입니다.

| 항목 | 내용 |
|---|---|
| 책임 | 추출 대상 시간 창을 표현하고, 체크포인트 키와 파일명을 파생시킨다 |
| 불변식 | `start < end`, 두 값 모두 타임존 인식(aware), `end - start <= 24h` |
| 파생값 | `key` = `end`의 ISO 8601 문자열 (Q8=A), `label` = `end`의 로컬 날짜 (파일명용) |

#### `ColumnSpec`
CSV 컬럼 하나의 매핑. `source`(점 표기법 경로) → `header`(CSV 헤더명).

#### `ChunkState`
체크포인트에 기록되는 청크 상태. `status`(`done` / `failed`), `doc_count`, `updated_at`, `error`.

---

### 컴포넌트 목록

#### 1. `Config` (`config.py`)

| 항목 | 내용 |
|---|---|
| 목적 | 설정 파일(YAML)과 `.env`를 읽어 검증된 설정 객체를 만든다 |
| 책임 | YAML 파싱 / `.env`에서 시크릿 로딩 / 값 검증 / 기본값 적용 |
| 책임 아님 | 설정 값을 사용하는 로직 (각 컴포넌트가 담당) |
| 인터페이스 | 중첩 dataclass: `Config(es, query, chunk, output)` |
| 검증 항목 | `chunk_hours <= 24` (초과 시 오류로 실행 중단, FR-2) / 필수 시크릿 존재 / 타임존 문자열 유효성 / 컬럼 목록 비어있지 않음 |
| 시크릿 | ES 호스트와 API Key는 **`.env`에서만** 읽는다. YAML에 두지 않는다 (NFR-6) |

#### 2. `DateChunker` (`chunker.py`)

| 항목 | 내용 |
|---|---|
| 목적 | 요청 기간을 anchor에 정렬된 `TimeWindow` 목록으로 나눈다 |
| 책임 | 기준 시각(anchor, 기본 18:00 KST) 정렬 / 반개구간 경계 계산 / 기본 창 계산 / 타임존 처리 |
| 책임 아님 | Elasticsearch 쿼리 생성, 실행 순서 결정 |
| 순수성 | **부수효과 없는 순수 로직** — 속성 기반 테스트의 주 대상 (PBT-03) |
| 핵심 불변식 | 청크들의 합집합 = 요청 기간 / 인접 청크가 겹치지 않음 / 모든 청크 폭 <= 24h / 청크가 시간순 정렬 |

#### 3. `EsExtractor` (`extractor.py`)

| 항목 | 내용 |
|---|---|
| 목적 | 하나의 `TimeWindow`에 대해 Elasticsearch에서 문서를 스트리밍으로 가져온다 |
| 책임 | range 쿼리 생성(로컬 시각 → UTC 변환) / scroll 페이징 / **scroll 컨텍스트 정리 보장** |
| 책임 아님 | 파일 쓰기, 청크 분할, 재시도 정책(클라이언트가 담당) |
| 인터페이스 | `Elasticsearch` 객체를 **생성자 주입**으로 받는다 (Q6=A, 테스트는 이 객체를 모킹) |
| 반환 | `Iterator[dict]` — 전체를 메모리에 올리지 않음 (NFR-5) |
| 중요 제약 | 정상 종료·예외 발생 **양쪽 모두** `clear_scroll` 호출 (C-2 리스크의 방어선) |

#### 4. `JsonlWriter` (`writer.py`)

| 항목 | 내용 |
|---|---|
| 목적 | 문서 스트림을 청크별 JSONL 파일로 저장한다 |
| 책임 | 파일 경로 결정 / 스트리밍 쓰기 / 원자적 완료(임시 파일 → rename) / 쓴 문서 수 반환 |
| 책임 아님 | 문서 변형 — **ES 원본(`_source` 포함 전체 히트)을 그대로 보존** (FR-4) |
| 파일명 | `data-{window.label}.jsonl` — `label`은 창의 **종료 날짜** (예: `data-2026-09-09.jsonl`) |
| 원자성 | `.jsonl.tmp`에 쓰고 완료 시 `os.replace` — 중단된 파일이 완성본으로 오인되지 않음 |

#### 5. `CsvConverter` (`converter.py`)

| 항목 | 내용 |
|---|---|
| 목적 | JSONL 파일을 설정된 컬럼만 담은 CSV로 변환한다 |
| 책임 | 점 표기법 경로로 값 추출 / 헤더명 리네이밍 / 누락 필드 치환 / CSV 쓰기 |
| 책임 아님 | 전체 필드 평탄화 (CQ5=C — **지정한 컬럼만**) |
| 순수 로직 | 값 추출(`extract_value`)과 행 생성(`to_row`)은 부수효과 없는 순수 함수 — PBT 대상 |
| 파일명 | `data-{window.label}.csv` |

#### 6. `CheckpointStore` (`checkpoint.py`)

| 항목 | 내용 |
|---|---|
| 목적 | 청크별 진행 상태를 영속화해 재개를 가능하게 한다 (FR-6) |
| 책임 | 상태 로드/조회/갱신 / 원자적 파일 쓰기 |
| 저장 위치 | `{output_dir}/.checkpoint.json` (Q7=A) |
| 키 | `TimeWindow.key` = 창 종료 시각 ISO 8601 (Q8=A) |
| 원자성 | 임시 파일 → `os.replace`. 중단 시 이전 상태가 온전히 남음 |
| 갱신 시점 | 청크 처리 **완료 직후** 기록 (JSONL rename 이후) — 순서가 바뀌면 "완료로 기록됐지만 파일은 없음" 상태가 생김 |

#### 7. `CrawlService` (`pipeline.py`)

| 항목 | 내용 |
|---|---|
| 목적 | 컴포넌트를 조립해 추출/변환 흐름을 실행한다. **라이브러리 공개 진입점** (Q5=C) |
| 책임 | 청크 목록 확보 / 완료 청크 건너뛰기 / 순차 실행 / 오류 격리 / 리포트 집계 |
| 책임 아님 | 인자 파싱, 로깅 포맷, 종료 코드 (CLI가 담당) |
| 오류 정책 | 청크 하나의 실패가 나머지를 막지 않는다. 실패를 기록하고 계속 진행, 끝에 요약 (NFR-4) |
| 메서드 | `extract()`, `convert()`, `run()` — `run()`은 라이브러리 편의용이며 CLI에는 노출하지 않음 (Q2=B) |

#### 8. `CLI` (`cli.py`)

| 항목 | 내용 |
|---|---|
| 목적 | 스케줄러와 사람이 쓰는 얇은 진입점 |
| 책임 | 인자 파싱 / 설정 로드 / `CrawlService` 호출 / 로깅 설정 / **종료 코드 결정** |
| 책임 아님 | 비즈니스 로직 일체 |
| 서브커맨드 | `extract`, `convert` (Q2=B) |
| 종료 코드 | `0` 전체 성공 / `1` 하나 이상 청크 실패 / `2` 설정·연결 오류 (FR-9) |

#### 9. 패키지 공개 API (`__init__.py`)

| 항목 | 내용 |
|---|---|
| 공개 | `CrawlService`, `Config`, `load_config`, `TimeWindow` |
| 비공개 | 나머지 컴포넌트는 내부 구현 — 필요해지면 그때 공개 (YAGNI) |

---

# 제2부: 컴포넌트 메서드

**단위(Unit)**: `es-crawler`

> **범위 참고**: 이 문서는 **시그니처와 입출력 타입**만 정의합니다.
> 상세 비즈니스 규칙(경계 계산 규칙, 상태 전이 규칙, 누락 필드 처리 규칙 등)은
> CONSTRUCTION 단계의 **Functional Design**에서 정의합니다.

---

### 값 객체 (Value Objects)

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

### `Config` (`config.py`)

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

### `DateChunker` (`chunker.py`)

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

### `EsExtractor` (`extractor.py`)

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

### `JsonlWriter` (`writer.py`)

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

### `CsvConverter` (`converter.py`)

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

### `CheckpointStore` (`checkpoint.py`)

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

### `CrawlService` (`pipeline.py`)

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

### `CLI` (`cli.py`)

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

---

# 제3부: 서비스 계층

**단위(Unit)**: `es-crawler`

---

### 서비스 정의

이 시스템의 서비스 계층은 **`CrawlService` 하나**입니다.
분산 서비스나 마이크로서비스가 아니라, **컴포넌트를 조립해 흐름을 실행하는 오케스트레이션 계층**을 뜻합니다.

| 항목 | 내용 |
|---|---|
| 서비스명 | `CrawlService` |
| 위치 | `es_crawler/pipeline.py` |
| 역할 | 컴포넌트 조립 + 실행 순서 결정 + 오류 격리 + 결과 집계 |
| 공개 여부 | **라이브러리 공개 진입점** (Q5=C) |
| 상태 | 스스로 가변 상태를 갖지 않음. 영속 상태는 `CheckpointStore`가 소유 |

#### 서비스가 하지 않는 것
- 인자 파싱, 로깅 설정, 종료 코드 결정 → `CLI`의 책임
- Elasticsearch 쿼리 생성 → `EsExtractor`의 책임
- 경계 계산 → `DateChunker`의 책임

---

### 오케스트레이션 1: `extract()`

```
  +---------------------------------+
  | 1. Build chunk list             |
  |    DateChunker.chunks()         |
  +---------------------------------+
                  |
                  v
  +---------------------------------+
  | 2. Drop finished chunks         |
  |    CheckpointStore.pending()    |
  +---------------------------------+
                  |
                  v
  +---------------------------------+
  | 3. Loop chunks SEQUENTIALLY     |
  +---------------------------------+
                  |
                  v
  +---------------------------------+
  | 3a. EsExtractor                 |
  |     .iter_documents()  (scroll) |
  +---------------------------------+
                  |
                  v
  +---------------------------------+
  | 3b. JsonlWriter.write()         |
  |     tmp file -> os.replace      |
  +---------------------------------+
                  |
                  v
  +---------------------------------+
  | 3c. CheckpointStore             |
  |     .mark_done()                |
  +---------------------------------+
                  |
                  v
  +---------------------------------+
  | 4. Aggregate Report, return     |
  +---------------------------------+
```

#### 단계별 규칙

| 단계 | 규칙 |
|---|---|
| 1 | `start`/`end`가 `None`이면 `default_window()` 사용 (D-1) |
| 2 | 이미 `done`인 청크는 `skipped`로 리포트에 기록하고 건너뜀 (FR-6) |
| 3 | **순차 실행**. 청크 하나가 실패해도 다음 청크로 계속 진행 (NFR-4) |
| 3a | 스트리밍 — 문서 전체를 메모리에 모으지 않음 (NFR-5) |
| 3b | 임시 파일에 쓰고 완료 후 `os.replace` |
| 3c | **반드시 3b 이후**에 실행. 순서가 뒤집히면 "완료 기록은 있는데 파일은 없는" 상태가 생김 |
| 실패 시 | `CheckpointStore.mark_failed()` 기록 후 다음 청크로 진행 |

---

### 오케스트레이션 2: `convert()`

```
  +--------------------------------+
  | 1. Build chunk list            |
  |    DateChunker.chunks()        |
  +--------------------------------+
                  |
                  v
  +--------------------------------+
  | 2. Resolve JSONL path          |
  |    JsonlWriter.path_for()      |
  +--------------------------------+
                  |
                  v
  +--------------------------------+
  | 3. Missing file -> skip + warn |
  +--------------------------------+
                  |
                  v
  +--------------------------------+
  | 4. CsvConverter.convert()      |
  +--------------------------------+
                  |
                  v
  +--------------------------------+
  | 5. Aggregate Report, return    |
  +--------------------------------+
```

#### 단계별 규칙

| 단계 | 규칙 |
|---|---|
| 1 | `extract`와 **동일한 날짜 범위 인자**를 받는다 (D-3) |
| 3 | 대상 JSONL이 없으면 `skipped`로 기록하고 경고 로그. **오류가 아님** |
| 4 | CSV 변환은 체크포인트를 갱신하지 않는다 — 체크포인트는 추출 단계만 추적 |
| 재실행 | 이미 있는 CSV는 덮어쓴다 (변환은 멱등, 재실행이 안전) |

**설계 근거 (Q3=B)**: 변환은 추출이 모두 끝난 뒤 별도 명령으로 일괄 수행합니다.
덕분에 변환 로직을 고쳤을 때 **ES에 다시 질의하지 않고** `convert`만 재실행할 수 있습니다.
JSONL을 디스크에 보존하기로 한 결정(CQ4=A)이 이를 가능하게 합니다.

---

### 오케스트레이션 3: `run()`

`extract()` 실행 후 성공 시 `convert()` 를 이어서 실행합니다.
**라이브러리 사용자를 위한 편의 메서드이며, CLI에는 노출하지 않습니다** (Q2=B).

---

### 스케줄러 연동 (D-4)

CLI에 `run`이 없으므로, 매일 19:00 KST에 두 명령을 이어서 실행합니다.

```
python -m es_crawler extract && python -m es_crawler convert
```

| 항목 | 내용 |
|---|---|
| 실행 시각 | 매일 19:00 KST |
| 추출 대상 | 인자 없음 -> 전날 18:00 ~ 당일 18:00 KST (D-1) |
| 연결자 | `&&` — 추출이 실패(종료 코드 0이 아님)하면 변환하지 않음 |
| 실패 감지 | 스케줄러가 종료 코드로 판단 (FR-9) |
| 재시도 | 다음 날 실행 시 체크포인트에 남은 실패 청크를 자동으로 다시 시도 |

---

### 오류 처리 정책

| 오류 유형 | 처리 |
|---|---|
| 설정 오류 (`chunk_hours > 24` 등) | 실행 전 즉시 중단, 종료 코드 `2` |
| ES 연결·인증 실패 | 실행 전 즉시 중단, 종료 코드 `2` |
| 일시적 오류 (429, 502, 503, 타임아웃) | `elasticsearch-py` 클라이언트가 재시도로 흡수. 서비스는 인지하지 않음 (NFR-4) |
| 재시도 후에도 실패한 청크 | `mark_failed` 기록 후 **다음 청크 계속 진행**. 종료 코드 `1` |
| JSONL 파일 없음 (`convert`) | `skipped` 기록 + 경고. 오류 아님 |

---

# 제4부: 의존 관계

**단위(Unit)**: `es-crawler`

---

### 1. 계층 구조

```
+------------------------------------------+
| Entry Layer                              |
| cli.py                __init__.py        |
+------------------------------------------+
                     |
                     v
+------------------------------------------+
| Orchestration Layer                      |
| pipeline.py : CrawlService               |
+------------------------------------------+
                     |
                     v
+------------------------------------------+
| Component Layer                          |
| chunker.py   extractor.py   writer.py    |
| converter.py checkpoint.py               |
+------------------------------------------+
                     |
                     v
+------------------------------------------+
| Foundation Layer                         |
| config.py    elasticsearch-py (external) |
+------------------------------------------+
```

**규칙**: 의존은 **위에서 아래로만** 흐릅니다. 아래 계층이 위 계층을 참조하지 않습니다.
컴포넌트끼리도 서로 참조하지 않으며, 조합은 `CrawlService`가 전담합니다.

---

### 2. 의존 매트릭스

행이 열에 의존합니다. `X` = 직접 의존.

| 의존 주체 \ 대상 | Config | DateChunker | EsExtractor | JsonlWriter | CsvConverter | CheckpointStore | CrawlService | es-py |
|---|---|---|---|---|---|---|---|---|
| **CLI**             | X |   |   |   |   |   | X |   |
| **CrawlService**    | X | X | X | X | X | X |   | X |
| **DateChunker**     | X |   |   |   |   |   |   |   |
| **EsExtractor**     | X |   |   |   |   |   |   | X |
| **JsonlWriter**     |   |   |   |   |   |   |   |   |
| **CsvConverter**    |   |   |   |   |   |   |   |   |
| **CheckpointStore** |   |   |   |   |   |   |   |   |
| **Config**          |   |   |   |   |   |   |   |   |

#### 관찰

- **`JsonlWriter`, `CsvConverter`, `CheckpointStore`는 의존이 전혀 없습니다.**
  생성자로 필요한 값(경로, 컬럼 목록)만 받으므로 ES나 설정 없이 단독 테스트가 가능합니다.
- **`DateChunker`는 `ChunkConfig`만 의존**하고 부수효과가 없어, 속성 기반 테스트의 주 대상입니다.
- **`EsExtractor`만 `elasticsearch-py`에 직접 의존**합니다. 외부 시스템 의존이 한 곳에 격리되어,
  테스트에서 이 컴포넌트에 주입되는 클라이언트만 모킹하면 됩니다 (Q6=A).
- **`CrawlService`가 유일하게 여러 컴포넌트에 의존**합니다. 결합의 복잡도가 여기 한 곳에 모입니다.

---

### 3. 통신 패턴

| 관계 | 패턴 | 비고 |
|---|---|---|
| CLI -> CrawlService | 직접 메서드 호출 | 동기 |
| CrawlService -> 컴포넌트 | 직접 메서드 호출 | 동기, 순차 |
| CrawlService -> EsExtractor | **이터레이터(제너레이터) 반환** | 스트리밍, 지연 평가 (NFR-5) |
| EsExtractor -> Elasticsearch | HTTP (elasticsearch-py) | scroll 페이징, 클라이언트가 재시도 |
| CheckpointStore -> 파일시스템 | 원자적 쓰기 (tmp + `os.replace`) | 손상 방지 |
| JsonlWriter -> 파일시스템 | 원자적 쓰기 (tmp + `os.replace`) | 불완전 파일 방지 |

**의존성 주입**: `Elasticsearch` 클라이언트는 `CrawlService` 생성자에서 선택적으로 주입받아
`EsExtractor`에 전달합니다. 이것이 테스트에서 ES를 대체하는 유일한 지점입니다.

---

### 4. 데이터 흐름: `extract`

```
+----------+     +--------------+     +------------------+
|  Config  | --> | CrawlService | --> |   DateChunker    |
+----------+     +--------------+     +------------------+
                        |
                        | list[TimeWindow]
                        v
                 +------------------+
                 | CheckpointStore  |
                 |   pending()      |
                 +------------------+
                        |
                        | unfinished chunks
                        v
                 +------------------+
                 |   EsExtractor    |
                 |   scroll paging  |
                 +------------------+
                        |
                        | Iterator[dict]
                        v
                 +------------------+
                 |   JsonlWriter    |
                 +------------------+
                        |
                        | data-YYYY-MM-DD.jsonl
                        v
                 +------------------+
                 | CheckpointStore  |
                 |   mark_done()    |
                 +------------------+
```

### 5. 데이터 흐름: `convert`

```
+----------+     +--------------+     +------------------+
|  Config  | --> | CrawlService | --> |   DateChunker    |
+----------+     +--------------+     +------------------+
                        |
                        | list[TimeWindow]
                        v
                 +------------------+
                 |   JsonlWriter    |
                 |   path_for()     |
                 +------------------+
                        |
                        | data-YYYY-MM-DD.jsonl
                        v
                 +------------------+
                 |   CsvConverter   |
                 +------------------+
                        |
                        | data-YYYY-MM-DD.csv
                        v
                 +------------------+
                 |      Report      |
                 +------------------+
```

**주목**: `convert` 흐름에는 `EsExtractor`도 `CheckpointStore`도 등장하지 않습니다.
Elasticsearch에 접속하지 않고 동작하므로, 변환 로직만 고쳐 재실행할 때 클러스터에 부하를 주지 않습니다.

---

### 6. 출력 디렉터리 구조

```
output/
  .checkpoint.json          체크포인트 상태 (CheckpointStore)
  data-2026-09-08.jsonl     추출 원본 (JsonlWriter)
  data-2026-09-09.jsonl
  data-2026-09-08.csv       변환 결과 (CsvConverter)
  data-2026-09-09.csv
```

파일명의 날짜는 창의 **종료 날짜**입니다.
`data-2026-09-09.jsonl` = `[2026-09-08 18:00 KST, 2026-09-09 18:00 KST)` (D-1).

---

### 7. 결합도 평가

| 컴포넌트 | 팬인(누가 의존) | 팬아웃(무엇에 의존) | 평가 |
|---|---|---|---|
| Config | 4 | 0 | 안정적 기반. 변경 시 파급이 크므로 필드 추가는 신중히 |
| DateChunker | 1 | 1 | 낮은 결합. 순수 로직 |
| EsExtractor | 1 | 2 | 외부 의존을 여기 한 곳으로 격리 |
| JsonlWriter | 1 | 0 | 독립적 |
| CsvConverter | 1 | 0 | 독립적 |
| CheckpointStore | 1 | 0 | 독립적 |
| CrawlService | 1 | 6 | 팬아웃이 높지만 의도된 것 — 조합 책임이 한 곳에 모임 |
| CLI | 0 | 2 | 얇은 껍데기 |

**순환 의존 없음.** 의존 그래프는 단방향 비순환(DAG)입니다.

---

# 확장 규칙 준수 요약 (Extension Compliance)

| 확장 | 상태 | 이 단계 적용 |
|---|---|---|
| Security Baseline | 비활성 (옵트아웃) | N/A — 규칙 파일 미로드 |
| Resiliency Baseline | 비활성 (옵트아웃) | N/A — 규칙 파일 미로드 |
| Property-Based Testing | 활성 (Partial) | Application Design은 PBT 강제 대상 단계가 아님 (N/A). 다만 PBT-01(Functional Design)을 대비해 순수 로직 컴포넌트(`DateChunker`, `CsvConverter.to_row` / `extract_value`)와 왕복 대상(`JsonlWriter`)을 이미 식별해 두었음 |

**차단성 발견 사항(Blocking findings): 없음.**
