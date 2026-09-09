# 비즈니스 규칙 (Business Rules) — `es-crawler`

**단계**: CONSTRUCTION - Functional Design
**단위(Unit)**: `es-crawler`

---

## 1. 설정 검증 규칙 (실행 전 검사)

모두 **실행 시작 전** 검사하며, 위반 시 즉시 중단하고 **종료 코드 `2`** 를 반환합니다.
청크 처리 도중에 발견되면 이미 부분 실행된 상태가 되므로, 반드시 사전에 검사합니다.

| ID | 규칙 | 위반 시 메시지 예 |
|---|---|---|
| BR-C01 | `0 < chunk_hours <= 24` | `chunk_hours must be between 1 and 24 (got 48)` — 제약 C-3 |
| BR-C02 | `timezone`이 유효한 IANA 이름 | `unknown timezone: 'Asia/Seou'` |
| BR-C03 | `index`가 비어 있지 않음 | `index must not be empty` |
| BR-C04 | `time_field`가 비어 있지 않음 | `time_field must not be empty` |
| BR-C05 | `columns`가 최소 1개 | `at least one column must be configured` |
| BR-C06 | `columns`의 `header`가 중복되지 않음 | `duplicate CSV header: '사용자명'` |
| BR-C07 | `source`, `header` 모두 비어 있지 않음 | `column source/header must not be empty` |
| BR-C08 | `1 <= batch_size <= 10000` | `batch_size must be between 1 and 10000` |
| BR-C09 | `hosts`가 최소 1개 | `ES_HOSTS is not set in .env` |
| BR-C10 | `api_key`가 비어 있지 않음 | `ES_API_KEY is not set in .env` |
| BR-C11 | `output.directory` 생성 가능 | `cannot create output directory: <path>` |

**BR-C01이 특히 중요합니다.** 제약 C-3(청크당 최대 24시간)을 코드로 강제하는 지점이며,
FR-2의 "24시간을 초과하도록 설정되면 경고를 출력하고 실행하지 않는다"가 여기서 구현됩니다.

---

## 2. 입력 시각 규칙

| ID | 규칙 | 근거 |
|---|---|---|
| BR-T01 | `--from` / `--to`는 **시각까지 명시**해야 함 (`2026-09-01T18:00`). 날짜만 주면 거부 | Q1=C |
| BR-T02 | 타임존을 생략하면 `config.timezone`(기본 `Asia/Seoul`)으로 해석 | D-2 |
| BR-T03 | 주어진 시각을 **그대로** 사용. anchor로 정렬하지 않음 | Q2=C |
| BR-T04 | `--from`과 `--to`는 **함께** 주거나 **둘 다 생략**해야 함. 하나만 주면 거부 | 모호성 제거 |
| BR-T05 | 둘 다 생략하면 `default_window()` 사용 (전날 anchor ~ 당일 anchor) | D-1 |
| BR-T06 | `from >= to`이면 거부 | TW-1 |

**BR-T01의 거부 메시지**:
```
--from must include a time, e.g. 2026-09-01T18:00 (got '2026-09-01')
```
날짜만 허용하면 하루 경계가 18:00인 상황에서 어느 창을 뜻하는지 알 수 없기 때문입니다.

---

## 3. 경계 규칙

| ID | 규칙 | 근거 |
|---|---|---|
| BR-B01 | 시간 창은 **반개구간 `[start, end)`** | 인접 청크 간 누락·중복 방지 |
| BR-B02 | ES range 쿼리는 `gte` / `lt` 사용. `lte` 금지 | BR-B01과 정확히 일치시키기 위함 |
| BR-B03 | 마지막 청크는 `chunk_hours`보다 짧을 수 있음. 요청 범위를 넘지 않음 | `min(cursor+size, end)` |
| BR-B04 | 모든 청크의 `duration <= 24시간` | 제약 C-3 |
| BR-B05 | 청크 경계는 정확히 이어붙음: `w[i].end == w[i+1].start` | 누락 방지 |

---

## 4. 파일명 규칙

| ID | 규칙 | 근거 |
|---|---|---|
| BR-F01 | JSONL 파일명 = `data-{key without colons}.jsonl` | CQ1=A |
| BR-F02 | CSV 파일명 = `data-{key without colons}.csv` | 동일 규칙 |
| BR-F03 | 콜론(`:`)을 파일명에 쓰지 않음 | 파일시스템 호환 |
| BR-F04 | UTC 오프셋을 파일명에 포함 | 타임존이 다른 창끼리의 충돌 방지 |
| BR-F05 | 쓰기는 항상 `.tmp` -> `os.replace` | 불완전 파일이 완성본으로 오인되는 것 방지 |
| BR-F06 | 실패 시 `.tmp` 파일 삭제 | 쓰레기 누적 방지 |

예: `[2026-09-08T18:00+09:00, 2026-09-09T18:00+09:00)` -> `data-2026-09-09T180000+0900.jsonl`

**서로 다른 창은 반드시 서로 다른 파일명을 갖습니다** (속성 P-10).
이 규칙이 없으면 청크 크기를 6시간으로 줄였을 때 하루에 4번 같은 파일을 덮어쓰게 되고,
체크포인트는 4개 모두 완료로 기록해 **파일과 상태가 조용히 어긋납니다**.

---

## 5. 추출 규칙

| ID | 규칙 | 근거 |
|---|---|---|
| BR-E01 | 청크는 **순차** 처리. 병렬 없음 | NFR-7, 클러스터 부하 |
| BR-E02 | `scroll_id`는 응답마다 갱신해 최신 값으로 정리 | ES가 id를 변경할 수 있음 |
| BR-E03 | `clear_scroll`은 정상·예외·조기 중단 **모두**에서 호출 | 제약 C-2 방어선 |
| BR-E04 | `clear_scroll` 실패는 로그만 남기고 추출 결과를 뒤엎지 않음 | 정리 실패로 성공을 실패로 바꾸지 않음 |
| BR-E05 | 문서를 메모리에 모으지 않고 제너레이터로 흘림 | NFR-5 |
| BR-E06 | JSONL에는 **히트 객체 전체**를 저장 (`_index`, `_id`, `_score`, `_source`) | Q8=A |
| BR-E07 | 문서가 0건이어도 **빈 JSONL 파일을 만들고 `done` 처리** | Q6=A |
| BR-E08 | `mark_done`은 `os.replace` **이후**에만 호출 | 상태와 파일의 일관성 |

**BR-E07의 의미**: 빈 파일이 있으면 "조회했고 데이터가 없었다"이고,
파일이 없으면 "아직 조회하지 않았다"입니다. 이 구분이 없으면 운영 중 판단이 불가능합니다.

---

## 6. 체크포인트 규칙

| ID | 규칙 | 근거 |
|---|---|---|
| BR-K01 | 청크 키 = `TimeWindow.end.isoformat()` (오프셋 포함) | Application Design Q8=A |
| BR-K02 | `done`은 종착 상태. 재추출하지 않음 | FR-6 |
| BR-K03 | `failed`는 다음 실행에서 **자동 재시도** | Q7=A |
| BR-K04 | 상태 파일이 없으면 빈 상태로 시작 (오류 아님) | 최초 실행 |
| BR-K05 | 상태 파일 저장은 `.tmp` -> `os.replace` | 손상 방지 |
| BR-K06 | 상태 파일이 손상되어 파싱 불가하면 **중단**하고 사용자에게 알림 | 조용히 전체 재추출하면 클러스터에 큰 부하 |
| BR-K07 | `convert`는 체크포인트를 읽지도 쓰지도 않음 | 추출만 추적 |

**BR-K06의 근거**: 손상된 체크포인트를 "빈 상태"로 취급하면 이미 받은 수백 일치를
전부 다시 추출하게 됩니다. 부하를 줄이려 하루씩 쪼갠 목적(C-3)과 정반대이므로,
조용히 넘어가지 않고 명시적으로 중단합니다.

---

## 7. CSV 변환 규칙

| ID | 규칙 | 근거 |
|---|---|---|
| BR-V01 | 설정된 컬럼만 추출. 전체 평탄화하지 않음 | CQ5=C |
| BR-V02 | `_id`, `_index`, `_score`는 히트 최상위에서 조회 | Q3=A |
| BR-V03 | 그 외 경로는 `_source` 내부 기준 | Q3=A |
| BR-V04 | 경로가 존재하지 않으면 `missing_value`(기본 `""`) | Q5=B |
| BR-V05 | 값이 `null`이면 `null_value`(기본 `"NULL"`) | Q5=B, CQ2=A |
| BR-V06 | 배열·객체는 JSON 문자열로 직렬화 (`ensure_ascii=False`) | Q4=A |
| BR-V07 | `bool`은 `true` / `false` 소문자 문자열 | JSON 표기와 일치 |
| BR-V08 | `bool` 검사를 `int` 검사보다 **먼저** 수행 | Python에서 `bool`은 `int`의 하위 타입 |
| BR-V09 | 인코딩은 `utf-8-sig`, 헤더 행 포함 | Q9=B |
| BR-V10 | 헤더는 `ColumnSpec.header` 순서 그대로 | 설정이 곧 스키마 |
| BR-V11 | 대상 JSONL이 없으면 경고 후 `skipped`. **오류 아님** | D-3 |
| BR-V12 | 이미 존재하는 CSV는 덮어씀 (변환은 멱등) | 재실행 안전성 |
| BR-V13 | 빈 줄은 건너뜀 | 파일 끝 개행 등 |

### 값 렌더링 판정 순서

```
1. MISSING (필드 없음)  -> missing_value   ""
2. None                 -> null_value      "NULL"
3. bool                 -> "true" / "false"
4. dict 또는 list        -> json.dumps(..., ensure_ascii=False)
5. 그 외                 -> str(value)
```

순서가 규칙입니다. 2번과 3번을 바꾸면 안 되고, 3번과 5번을 바꾸면 `True`가 `1`이 됩니다.

---

## 8. 오류 분류 및 처리 규칙

| ID | 오류 유형 | 처리 | 종료 코드 |
|---|---|---|---|
| BR-X01 | 설정 검증 실패 (BR-C\*) | 실행 전 즉시 중단 | `2` |
| BR-X02 | 입력 시각 오류 (BR-T\*) | 실행 전 즉시 중단 | `2` |
| BR-X03 | ES 연결·인증 실패 | 실행 전 즉시 중단 | `2` |
| BR-X04 | 체크포인트 파일 손상 (BR-K06) | 즉시 중단 | `2` |
| BR-X05 | 일시적 ES 오류 (429, 502, 503, 타임아웃) | `elasticsearch-py` 클라이언트가 재시도로 흡수. 서비스는 인지하지 않음 | — |
| BR-X06 | 재시도 후에도 실패한 청크 | `mark_failed` 기록 후 **다음 청크 계속** | `1` |
| BR-X07 | JSONL 파일 없음 (`convert`) | 경고 로그 + `skipped` | `0` |
| BR-X08 | CSV 변환 중 파싱 실패 | 해당 청크만 `failed`, 다음 청크 계속 | `1` |

### 종료 코드 매핑

| 코드 | 조건 |
|---|---|
| `0` | `Report.failed == 0` — 모든 청크가 `done` 또는 `skipped` |
| `1` | `Report.failed > 0` — 하나 이상 실패했으나 실행은 완주 |
| `2` | 실행 전 중단 (설정·입력·연결·체크포인트 오류) |

**설계 의도**: 스케줄러는 `extract && convert` 로 연결해 실행합니다 (D-4).
`&&`는 종료 코드 `0`일 때만 다음 명령을 실행하므로, 추출이 부분 실패해도(`1`)
그 시점의 불완전한 JSONL로 CSV를 만들지 않습니다.

---

## 9. 보안 규칙

| ID | 규칙 | 근거 |
|---|---|---|
| BR-S01 | `api_key`와 `hosts`는 `.env`에서만 로드. YAML에 두지 않음 | NFR-6 |
| BR-S02 | `api_key`를 로그·오류 메시지·리포트에 출력하지 않음 | NFR-6 |
| BR-S03 | `.env`는 버전 관리에서 제외하고 `.env.example` 템플릿 제공 | NFR-6 |
| BR-S04 | 예외를 그대로 로깅할 때 클라이언트 설정 객체를 함께 덤프하지 않음 | 헤더에 키가 실릴 수 있음 |

Security Baseline 확장은 옵트아웃(Q12=B) 상태이지만, 위 4개 규칙은
NFR-6에서 도출된 **이 프로젝트 자체의 요구사항**이므로 적용합니다.

---

## 10. 로깅 규칙

| ID | 규칙 |
|---|---|
| BR-L01 | 청크 시작 시: 창의 시작·종료 시각 기록 |
| BR-L02 | 청크 완료 시: 문서 수와 소요 시간 기록 |
| BR-L03 | 청크 실패 시: 예외 타입과 메시지 기록 (스택트레이스는 DEBUG 레벨) |
| BR-L04 | 실행 종료 시: 성공/실패/건너뜀 개수와 총 문서 수 요약 |
| BR-L05 | 무인 실행이므로 로그만 보고 무엇이 실패했는지 판단 가능해야 함 (FR-10) |

---

## 11. 확장 규칙 준수 요약 (Extension Compliance)

| 규칙 | 상태 | 근거 |
|---|---|---|
| PBT-01 (설계 시 속성 식별) | **준수** | `business-logic-model.md` L-10에 속성 14개 식별. 속성이 없는 컴포넌트는 사유 명시 (Partial 모드에서는 권고 규칙이나 충족함) |
| PBT-02 (왕복 속성) | 준수 (사전 식별) | P-5 (JSONL 왕복), P-9 (`TimeWindow.key` 왕복). 구현 검증은 Code Generation |
| PBT-03 (불변식 속성) | 준수 (사전 식별) | P-1~P-4, P-6~P-8, P-10 |
| PBT-04 (멱등성) | N/A (권고) | P-13으로 식별. Partial 모드에서 비차단 |
| PBT-05 (오라클) | N/A | 비교 대상 참조 구현이 없음 |
| PBT-06 (상태 기반) | N/A (권고) | P-14로 식별. `CheckpointStore`가 유일한 상태 보유 컴포넌트이며 상태 공간이 단순 |
| PBT-07 (제너레이터 품질) | 준수 (사전 식별) | P-11. 구현은 Code Generation |
| PBT-08 (shrinking·재현성) | 준수 (사전 식별) | P-12. 구현은 Code Generation |
| PBT-09 (프레임워크 선정) | 다음 단계 | NFR Requirements 단계에서 확정 (hypothesis 후보) |
| PBT-10 (상호보완 전략) | 준수 (사전 식별) | L-10에 예제 기반 테스트가 적합한 컴포넌트를 별도 명시 |
| Security Baseline | N/A | 옵트아웃 (Q12=B) |
| Resiliency Baseline | N/A | 옵트아웃 (Q13=B) |

**차단성 발견 사항(Blocking findings): 없음.**
