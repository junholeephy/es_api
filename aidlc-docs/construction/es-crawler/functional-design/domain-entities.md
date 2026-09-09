# 도메인 엔티티 (Domain Entities) — `es-crawler`

**단계**: CONSTRUCTION - Functional Design
**단위(Unit)**: `es-crawler`

> 이 문서는 기술 중립적인 도메인 개념을 정의합니다.
> Python 타입 표기는 이해를 돕기 위한 것이며, 구현 세부는 Code Generation 단계에서 확정됩니다.

---

## 엔티티 관계

```
+---------------------+
|      Config         |
|  (aggregate root)   |
+---------------------+
          |
          | 1..1
          v
+---------------------+      1..*       +---------------------+
|    ChunkConfig      | --------------> |     TimeWindow      |
|  anchor / tz / size |     creates     |    [start, end)     |
+---------------------+                 +---------------------+
                                                  |
                                                  | 1..1  (key)
                                                  v
                                        +---------------------+
                                        |     ChunkState      |
                                        |   done / failed     |
                                        +---------------------+

+---------------------+      1..*       +---------------------+
|    OutputConfig     | --------------> |     ColumnSpec      |
|  dir / columns      |    contains     |  source -> header   |
+---------------------+                 +---------------------+

+---------------------+
|    HitDocument      |   raw Elasticsearch hit (read only)
|  _id / _index /     |
|  _score / _source   |
+---------------------+
```

---

## E-1. `TimeWindow` — 시간 창

추출 대상 구간 하나. **반개구간 `[start, end)`** 입니다.

| 속성 | 타입 | 설명 |
|---|---|---|
| `start` | tz-aware datetime | 시작 시각 (포함) |
| `end` | tz-aware datetime | 종료 시각 (**제외**) |

### 불변식 (Invariants)

| ID | 불변식 | 위반 시 |
|---|---|---|
| TW-1 | `start < end` | 생성 실패 (`ValueError`) |
| TW-2 | `start`, `end` 모두 타임존 인식(aware) | 생성 실패 |
| TW-3 | `end - start <= 24시간` — **절대 시간 기준** | 생성 실패 (제약 C-3) |
| TW-4 | ~~`start`, `end`의 타임존이 동일~~ **철회** | — |

> **TW-4 철회 (Code Generation, 2026-09-09)**: 처음에는 두 끝의 UTC 오프셋이 같아야 한다고
> 적었으나, 이는 **서머타임을 넘는 구간을 통째로 거부**합니다.
> 예: `America/New_York` 의 `2026-03-07T18:00-05:00 ~ 2026-03-10T18:00-04:00`.
> 구간의 길이는 벽시계가 아니라 절대 시간으로 재므로 오프셋이 달라도 정상입니다.
> 구현에서 이 불변식을 제거하고 회귀 테스트를 추가했습니다
> (`tests/test_chunker.py::test_a_window_may_cross_a_daylight_saving_change`).
> 기본 타임존 `Asia/Seoul` 에는 서머타임이 없어 주 사용 경로에는 영향이 없었습니다.

### 파생값 (Derived Values)

| 이름 | 정의 | 예시 |
|---|---|---|
| `key` | `end.isoformat()` — 체크포인트 키 | `2026-09-02T18:00:00+09:00` |
| `slug` | `end` 를 `key` 에서 콜론 제거 로 포맷 — 파일명 조각 | `2026-09-02T1800+0900` |
| `duration` | `end - start` | `24:00:00` |

**`slug` 설계 근거 (CQ1=A)**: 파일명에 종료 **시각 전체**를 넣어 서로 다른 창이 같은 파일명을
갖는 일을 원천 차단합니다. 콜론(`:`)은 파일시스템 호환을 위해 제외하고,
UTC 오프셋(`+0900`)은 포함해 타임존이 다른 창끼리도 충돌하지 않게 합니다.

### 동등성
`start`와 `end`가 모두 같으면 같은 창입니다. 불변(frozen) 값 객체이며 해시 가능합니다.

---

## E-2. `ChunkState` — 청크 진행 상태

체크포인트에 영속화되는 청크 하나의 상태입니다.

| 속성 | 타입 | 설명 |
|---|---|---|
| `key` | str | 대응하는 `TimeWindow.key` |
| `status` | `done` \| `failed` | 처리 결과 |
| `doc_count` | int | 추출된 문서 수 (`failed`면 의미 없음, 0) |
| `updated_at` | tz-aware datetime | 마지막 기록 시각 |
| `error` | str \| None | 실패 사유 (`done`이면 `None`) |

### 상태 전이

```
                 +-------------+
                 |  (absent)   |
                 +-------------+
                   |         |
        success    |         |    failure
                   v         v
            +----------+  +----------+
            |   done   |  |  failed  |
            +----------+  +----------+
                 ^             |
                 |             | auto retry on next run (Q7=A)
                 +-------------+
                     success
```

| 전이 | 조건 | 비고 |
|---|---|---|
| (없음) -> `done` | 추출 성공 | JSONL 파일 확정 **이후** 기록 |
| (없음) -> `failed` | 추출 실패 | 오류 메시지 기록, 다음 청크로 진행 |
| `failed` -> `done` | 재실행 성공 | Q7=A: 자동 재시도 |
| `failed` -> `failed` | 재실행도 실패 | `updated_at`, `error` 갱신 |
| `done` -> (없음) | **없음** | `done`은 종착 상태. 재추출하지 않음 |

**중요**: `done` 기록은 반드시 JSONL 파일의 `os.replace` **이후**에 수행합니다.
순서가 뒤집히면 "완료로 기록됐지만 파일은 없는" 상태가 되고, 재개가 그 청크를 영원히 건너뜁니다.

---

## E-3. `ColumnSpec` — CSV 컬럼 매핑

| 속성 | 타입 | 설명 |
|---|---|---|
| `source` | str | 값을 꺼낼 경로 (점 표기법) |
| `header` | str | CSV 헤더에 쓸 이름 |

### 경로 해석 규칙 (Q3=A)

| `source` 값 | 해석 |
|---|---|
| `_id`, `_index`, `_score` | **히트 최상위 메타데이터**에서 조회 |
| 그 외 모든 이름 | **`_source` 내부** 기준 경로. 예: `user.name` -> `hit['_source']['user']['name']` |

메타데이터 이름 집합은 `{_id, _index, _score}` 로 **고정**합니다.
`_source` 안에 밑줄로 시작하는 필드가 있어도 이 세 이름과 겹치지 않는 한 정상 조회됩니다.

### 불변식

| ID | 불변식 |
|---|---|
| CS-1 | `source`가 빈 문자열이 아님 |
| CS-2 | `header`가 빈 문자열이 아님 |
| CS-3 | 한 `OutputConfig` 안에서 `header`가 중복되지 않음 |

---

## E-4. `HitDocument` — Elasticsearch 히트 (읽기 전용)

Elasticsearch가 돌려주는 히트 객체입니다. **변형 없이 그대로** JSONL에 저장합니다 (Q8=A).

```json
{
  "_index": "logs-2026.09.02",
  "_id": "abc123",
  "_score": null,
  "_source": { "@timestamp": "2026-09-02T10:00:00Z", "user": {"name": "kim"} }
}
```

| 특성 | 내용 |
|---|---|
| 소유 | Elasticsearch. 이 시스템은 읽기만 함 |
| 저장 | JSONL 한 줄 = 히트 객체 하나 (`ensure_ascii=False`) |
| 보존 이유 | `_id`로 중복 판별·추적이 가능하고, 변환 로직을 바꿔도 재추출이 불필요 |

---

## E-5. 설정 엔티티 (Configuration Entities)

### `ChunkConfig`

| 속성 | 기본값 | 제약 |
|---|---|---|
| `timezone` | `Asia/Seoul` | 유효한 IANA 타임존 이름 (D-2) |
| `anchor_time` | `18:00` | `default_window()` 계산에만 사용 (D-1) |
| `chunk_hours` | `24` | `0 < chunk_hours <= 24` (C-3). 초과 시 실행 거부 |

**`anchor_time`의 적용 범위**: Q1=C(명시적 시각만 허용) + Q2=C(준 시각 그대로 사용)의 결과로,
CLI에서 시각을 명시하면 anchor는 **쓰이지 않습니다**. `anchor_time`은 인자 없이 실행할 때의
기본 창을 만드는 데만 관여합니다.

### `QueryConfig`

| 속성 | 기본값 | 제약 |
|---|---|---|
| `index` | (필수) | 빈 문자열 불가. 와일드카드 허용 (`logs-*`) |
| `time_field` | (필수) | 빈 문자열 불가 |
| `extra_filters` | `[]` | ES query DSL 절의 리스트 |
| `batch_size` | `1000` | `1 <= batch_size <= 10000` |
| `scroll_ttl` | `5m` | ES 기간 표기 문자열 |

### `OutputConfig`

| 속성 | 기본값 | 제약 |
|---|---|---|
| `directory` | (필수) | 없으면 생성 |
| `columns` | (필수) | 최소 1개. `header` 중복 불가 |
| `missing_value` | `""` | 필드가 **없을 때** 쓰는 값 |
| `null_value` | `"NULL"` | 값이 **`null`일 때** 쓰는 값 (CQ2=A) |
| `encoding` | `utf-8-sig` | Q9=B |
| `write_header` | `true` | Q9=B |

### `EsConfig` (시크릿 — `.env`에서만 로드)

| 속성 | 출처 | 제약 |
|---|---|---|
| `hosts` | `.env` | 최소 1개 |
| `api_key` | `.env` | 빈 문자열 불가. **로그에 절대 출력 금지** |
| `request_timeout` | 설정 파일 (기본 60초) | > 0 |
| `max_retries` | 설정 파일 (기본 3) | >= 0 |

---

## E-6. `ChunkResult` / `Report` — 실행 결과 (비영속)

| `ChunkResult` 속성 | 설명 |
|---|---|
| `window` | 대상 창 |
| `status` | `done` \| `failed` \| `skipped` |
| `doc_count` | 처리한 문서 수 |
| `error` | 실패 사유 |

`skipped`의 의미는 단계에 따라 다릅니다.
- `extract`: 체크포인트에 이미 `done`으로 기록되어 건너뜀
- `convert`: 대상 JSONL 파일이 없어 건너뜀 (D-3, 오류 아님)

| `Report` 파생값 | 정의 |
|---|---|
| `succeeded` / `failed` / `skipped` | 각 상태의 개수 |
| `total_documents` | `doc_count` 합계 |
| `ok` | `failed == 0` — CLI 종료 코드 결정에 사용 |


---

## 부록: Code Generation·Build and Test 단계에서 고친 것

속성 기반 테스트가 찾아낸 정확성 결함 세 건입니다. 셋 다 서머타임이나 초 단위 경계처럼
예시 테스트로는 떠올리기 어려운 입력에서 나왔습니다.

### 1. TW-4 (오프셋 동일) 철회

서머타임을 넘는 구간을 통째로 거부했습니다. 구간의 길이는 절대 시간으로 재므로
두 끝의 오프셋이 달라도 정상입니다.

### 2. 구간 분할이 벽시계 산술이었다

지역 시각에 `timedelta` 를 더하면 파이썬은 **벽시계** 기준으로 더합니다.
서머타임이 끝나는 날 01:00 은 두 번 오므로, 벽시계로 한 시간인 조각이 실제로는
**두 시간**을 덮었습니다. `duration` 역시 벽시계 차이라 "한 시간"이라고 답해
상한(제약 C-3)이 의미를 잃었습니다.

- `chunks()` 를 UTC 기준으로 자르도록 변경
- `duration` 과 TW-1·TW-3 검사를 절대 시간 기준으로 변경
- 회귀 테스트: `test_a_chunk_never_covers_more_real_time_than_configured`,
  `test_a_fall_back_day_is_split_rather_than_stretched`

기본 타임존 `Asia/Seoul` 에는 서머타임이 없어 주 사용 경로는 영향받지 않았습니다.

### 3. `slug` 가 분까지만 담아 파일명이 충돌했다

`%Y-%m-%dT%H%M%z` 는 초를 버립니다. `05:00:00` 에 끝나는 조각과 `05:00:01` 에
끝나는 조각이 **같은 파일 이름**을 갖게 되어, 기록에는 둘 다 끝났다고 남고
파일은 하나만 남는 상태가 됩니다. 이것은 CQ1=A 로 막으려 했던 바로 그 실패입니다.

- `slug` 를 `key.replace(":", "")` 로 변경 — 콜론 제거는 되돌릴 수 있는 변환이므로
  **키가 다르면 이름도 반드시 다릅니다**
- 파일명 형식이 `data-2026-09-09T1800+0900` 에서 `data-2026-09-09T180000+0900` 으로 바뀜
- 회귀 테스트: `test_a_sub_minute_tail_gets_its_own_file_name`,
  `test_the_file_name_is_derived_from_the_record_key`
