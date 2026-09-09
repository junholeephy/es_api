# 코드 생성 요약 — `es-crawler`

**단계**: CONSTRUCTION - Code Generation (Part 2 완료)
**단위(Unit)**: `es-crawler`
**작성일**: 2026-09-09

> **우선순위**: `general_implementation` 규약 > 다른 모든 규약 (사용자 지시)

---

## 1. 생성된 파일

### 애플리케이션 코드 (이식됨)

| 파일 | 역할 | 구현한 설계 |
|---|---|---|
| `src/run.py` | 진입점. venv 갈아타기 + 위임 | P-13 |
| `src/es_crawler/__init__.py` | 공개 API 4종 | Application Design 컴포넌트 9 |
| `src/es_crawler/__main__.py` | CLI, 조기 실패, 종료 코드 | P-8, P-12, FR-9, FR-10 |
| `src/es_crawler/config.py` | 설정 로딩·검증, 시크릿 마스킹 | BR-C01~C11, P-11, P-12 |
| `src/es_crawler/chunker.py` | `TimeWindow`, 구간 분할, 기본 창, 시각 파싱 | L-1, L-2, BR-B01~B05, BR-T01~T06, BR-F01~F04 |
| `src/es_crawler/schema.py` | 문서 형태 단일 출처 + 대조 | 규약 §1.1, P-10, NFR-O06 |
| `src/es_crawler/synth.py` | 합성 히트 생성 + `FakeSearchClient` | 규약 §1.2, NFR-T03, NFR-T07 |
| `src/es_crawler/load.py` | ES 접근, scroll, 컨텍스트 정리 | L-3, L-4, P-1, P-4, BR-E01~E05 |
| `src/es_crawler/writer.py` | JSONL 원자적 쓰기 | L-5, P-3, BR-E06~E07, BR-F05~F06 |
| `src/es_crawler/converter.py` | JSONL → CSV | L-7, P-3, BR-V01~V13 |
| `src/es_crawler/checkpoint.py` | 구간별 진행 상태 | L-6, P-3, BR-K01~K07 |
| `src/es_crawler/pipeline.py` | 조립, 실패 격리, 부분 변환 | L-8, L-9, P-2, P-5, P-6, P-7, P-9, P-10 |
| `src/es_crawler/report.py` | RUN SUMMARY | P-8, NFR-O01~O09 |

### 테스트 (이식됨)

| 파일 | 테스트 수 | 내용 |
|---|---|---|
| `tests/conftest.py` | — | hypothesis 프로파일 + 도메인 생성기 6종 (PBT-07, PBT-08) |
| `tests/test_chunker.py` | 23 | 속성 7 + 예시 16 |
| `tests/test_writer.py` | 8 | 속성 2 + 예시 6 |
| `tests/test_converter.py` | 15 | 속성 4 + 예시 11 |
| `tests/test_checkpoint.py` | 11 | 예시 11 |
| `tests/test_load.py` | 12 | 예시 12 (가짜 클라이언트) |
| `tests/test_schema.py` | 14 | 예시 14 |
| `tests/test_run.py` | 18 | 전 구간 스모크 18 |
| **합계** | **101** | |

### 설정·규약 파일

| 파일 | 이식 | 내용 |
|---|---|---|
| `requirements.txt` | O | `elasticsearch==8.19.3`, `PyYAML==6.0.3` |
| `requirements-dev.txt` | X | `pytest`, `hypothesis`, `ruff`, `mypy`, `types-PyYAML` |
| `configs/env.example.yaml` | O | 전 설정 항목. 실값 없음 |
| `.gitignore` | O | 데이터·산출물·설정 차단 (allowlist) |
| `.gitattributes` | X | 이식 제외 목록. 자기 자신도 제외 |
| `ruff.toml` · `mypy.ini` | X | 개발 도구 설정 |
| `scripts/sync.sh` | X | 이식 스크립트 |
| `README.md` | X | 개발자용. 워크플로를 드러내므로 제외 |
| `TODO.md` · `todo/` (3개) | O | 대상 환경에서 만들어야 하는 것과 규격 |
| `docs/usage.md` | O | 프로그램 동작 설명 |

---

## 2. 검증 결과

| 검사 | 결과 |
|---|---|
| `pytest` | **101 passed** (서로 다른 시드로 3회 반복 통과) |
| `ruff check` | **All checks passed** |
| `ruff format --check` | **clean** |
| `mypy` | **Success: no issues found in 12 source files** |
| `--dry-run` 스모크 | 종료 코드 `0`, RUN SUMMARY 정상 |
| `--dry-run --adversarial` | 종료 코드 `1`, `status: SCHEMA MISMATCH` |
| Python 3.14.7 에서 전 의존성 설치 | 성공 |
| ES 접속 없이 전체 테스트 통과 | 성공 (NFR-T07) |

### 이식 표면 검사

`git archive` 로 실제 결과를 확인했습니다 (커밋은 만들지 않고 트리만 생성).

| 항목 | 결과 |
|---|---|
| 이식되는 파일 수 | **29개** |
| 제외 확인 | `aidlc-docs/`, `.aidlc-rule-details/`, `README.md`, `requirements-dev.txt`, `ruff.toml`, `mypy.ini`, `CLAUDE.md`, `.gitattributes`, `scripts/sync.sh` 모두 archive 에 없음 |
| 개인 머신 절대 경로 | 없음 |
| 이메일 | 없음 |
| `src/` 안의 외부 API 호출 | 없음 |
| 워크플로 어휘 (C9) | **1건 발견 후 수정** — `configs/env.example.yaml` 의 "운영 환경" 표현을 중립 문구로 교체 |

---

## 3. 계획과 달라진 점

### 3.1 발견하여 고친 설계 결함 1건

**TW-4 (두 끝의 UTC 오프셋이 같아야 한다) 철회**

Functional Design 에서 제가 넣은 불변식이 **서머타임을 넘는 구간을 통째로 거부**했습니다.
`America/New_York` 의 `2026-03-07T18:00-05:00 ~ 2026-03-10T18:00-04:00` 이 그 예입니다.
구간의 길이는 벽시계가 아니라 절대 시간으로 재므로 오프셋이 달라도 정상입니다.

- 구현에서 해당 검사 제거
- 회귀 테스트 추가: `test_a_window_may_cross_a_daylight_saving_change`
- `domain-entities.md` 의 TW-4 를 철회 표시와 근거로 갱신

기본 타임존 `Asia/Seoul` 에는 서머타임이 없어 주 사용 경로는 영향받지 않았습니다.
속성 테스트가 200 예제 안에서는 잡지 못했고, 직접 탐침해서 찾았습니다.

### 3.2 속성 테스트가 찾아낸 미문서화 동작 1건

`hypothesis` 가 `_source` 안에 `_score` 라는 이름의 필드가 있는 문서를 만들어냈습니다.
BR-V02 에 따라 메타데이터 이름은 **언제나 히트 최상위**를 가리키므로, 본문의 같은
이름 필드는 컬럼으로 꺼낼 수 없습니다 — 설계대로의 동작이지만 테스트에 적혀 있지
않았습니다.

`test_metadata_names_are_reserved` 를 추가해 이 제약을 고정했습니다.

### 3.3 계획에 없던 추가 2건

| 추가 | 이유 |
|---|---|
| `synth.FakeSearchClient` · `dry_run_config()` | `--dry-run` (Step 20 의 인자) 과 `test_load.py` (Step 26) 를 구현하려면 필요. 새 모듈을 만들지 않고 Step 13 의 `synth.py` 안에 두었습니다 |
| `docs/usage.md` | `README.md` 는 워크플로를 드러내 이식에서 빠집니다. 그러면 사본을 받는 쪽에 동작 설명이 하나도 없게 되므로, 중립 어휘로 된 문서를 따로 두었습니다 |

### 3.4 도구 설정 파일 위치

NFR Q2=A(`pyproject.toml`)가 규약에 의해 뒤집혔으므로 `ruff.toml` 과 `mypy.ini` 를
별도 파일로 두고 `export-ignore` 했습니다.

---

## 4. 요구사항 이행 현황

| 요구사항 | 구현 | 검증 |
|---|---|---|
| FR-1 ES 연결 (API Key, 재시도) | `load.build_client` | `test_load.py` |
| FR-2 날짜 분할 (24h 상한, anchor) | `chunker.DateChunker` | `test_chunker.py` 속성 4종 |
| FR-3 scroll 추출 (>10k, 정리 보장) | `load.EsExtractor` | `test_load.py` 정리 3경우 |
| FR-4 JSONL 저장 (원본 보존, 0건도 파일) | `writer.JsonlWriter` | `test_writer.py` |
| FR-5 CSV 변환 (컬럼 선택·리네임) | `converter.CsvConverter` | `test_converter.py` |
| FR-6 체크포인트·재개 | `checkpoint.CheckpointStore` | `test_checkpoint.py`, `test_run.py` |
| FR-7 설정 | `config.load_config` | `test_run.py` |
| FR-8 라이브러리 + CLI | `__init__.py`, `__main__.py` | `test_run.py` |
| FR-9 스케줄 실행 (기본 창) | `chunker.default_window` | `test_chunker.py` 예시 3종 |
| FR-10 로깅 | `pipeline`, `__main__` | `test_run.py` stdout/stderr 분리 |
| NFR-P02 배치 크기 2000 | `configs/env.example.yaml` | — (운영 실측 대기) |
| NFR-R01~R07 | 각 모듈 | 25개 테스트 |
| NFR-O01~O09 RUN SUMMARY | `report.py` | `test_run.py` 6종 |
| NFR-S01~S07 시크릿 | `config.EsConfig.__repr__` | 이식 표면 검사 |
| NFR-T01~T07 | `conftest.py`, `synth.py` | 101 테스트 전부 |

**미이행 요구사항: 없음.**

---

## 5. 확장 규칙 준수 (Extension Compliance)

| 규칙 | 강제 | 상태 | 근거 |
|---|---|---|---|
| **PBT-02** 왕복 | 차단성 | ✅ | `test_written_documents_read_back_unchanged` (JSONL 왕복), `test_key_round_trips_to_the_end_boundary` |
| **PBT-03** 불변식 | 차단성 | ✅ | 청크 합집합·무겹침·상한·정렬, CSV 행 수·셀 수, 경로 조회, `slug` 유일성 — 속성 10종 |
| **PBT-07** 생성기 품질 | 차단성 | ✅ | `conftest.py` 에 `aware_datetimes` `spans` `chunk_configs` `sources` `hits` `column_specs` — 원시 타입이 아니라 실제 문서 모양을 만들며 여러 테스트가 공유 |
| **PBT-08** shrinking·재현성 | 차단성 | ✅ | shrinking 비활성화 없음. `print_blob=True` 로 실패 시 `@reproduce_failure` 문구 출력 (실제로 DST·`_score` 사례에서 작동 확인) |
| **PBT-09** 프레임워크 | 차단성 | ✅ | `hypothesis==6.168.0` 고정 |
| PBT-01 속성 식별 | 권고 | ✅ | Functional Design L-10 |
| PBT-04 멱등성 | 권고 | ✅ | `test_converting_twice_gives_the_same_file` |
| PBT-05 오라클 | 권고 | N/A | 비교할 참조 구현이 없음 |
| PBT-06 상태 기반 | 권고 | 부분 | 상태 전이를 예시 테스트로 덮음 (`test_checkpoint.py`). 상태 공간이 단순해 명령열 생성까지는 두지 않음 |
| PBT-10 상호보완 | 권고 | ✅ | 속성 13 + 예시 88. 핵심 경로는 양쪽 모두 존재 |
| Security Baseline | — | N/A | 옵트아웃 (Q12=B) |
| Resiliency Baseline | — | N/A | 옵트아웃 (Q13=B) |

**차단성 발견 사항(Blocking findings): 없음.**

---

## 6. 남은 작업

| 항목 | 단계 |
|---|---|
| 커밋 및 태그 생성 | 사용자 요청 시 |
| `sync.sh` preflight 실행 | 태그 생성 후 |
| `schema.py` 의 `INPUT_SCHEMA` 를 실제 인덱스 형태로 | 첫 실행 후 회수한 정보로 |
| `batch_size` 기본값 실측 조정 | 첫 실행 후 |

`INPUT_SCHEMA` 는 현재 `_id` / `@timestamp` / `user.name` 세 필드의 자리표시입니다.
실제 형태는 첫 실행의 RUN SUMMARY `schema` 줄에서 나옵니다.
