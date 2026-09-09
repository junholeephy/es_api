# Code Generation Plan — `es-crawler`

**단계**: CONSTRUCTION - Code Generation (Part 1: 계획)
**단위(Unit)**: `es-crawler`
**작성일**: 2026-09-09

> **이 문서가 Code Generation 의 단일 진실 원본입니다.**
> Part 2 는 아래 단계를 순서대로만 실행하며, 여기 없는 것은 만들지 않습니다.

> **우선순위**: `general_implementation` 규약 > 다른 모든 규약 (사용자 지시)

---

## 1. 단위 컨텍스트

| 항목 | 내용 |
|---|---|
| 단위 | `es-crawler` (유일한 단위) |
| 의존 단위 | 없음 |
| 워크스페이스 루트 | `/Users/junho/coding_work/es_api` |
| 코드 위치 | 워크스페이스 루트의 `src/`, `tests/`, `configs/`, `scripts/` |
| 문서 위치 | `aidlc-docs/construction/es-crawler/code/` (마크다운 요약만) |
| User Stories | **없음** (Workflow Planning 에서 SKIP). 추적성은 FR/NFR/BR/P ID 로 대신함 |

### 규약 템플릿과의 차이 (근거 명시)

Code Generation 규칙의 기본 단계 목록에는 API Layer, Repository Layer, Frontend,
Database Migration 이 있으나 이 단위에는 해당하지 않습니다.

| 기본 단계 | 판정 | 근거 |
|---|---|---|
| API Layer | **N/A** | HTTP 서버가 없습니다. 외부 인터페이스는 CLI 하나뿐 |
| Repository Layer | **N/A** | 데이터베이스가 없습니다. 영속화는 파일(JSONL·CSV·체크포인트)뿐이며 `writer`·`checkpoint` 가 담당 |
| Frontend Components | **N/A** | UI 가 없습니다. `data-testid` 규칙도 해당 없음 |
| Database Migration | **N/A** | 스키마를 가진 DB 가 없습니다 |
| Deployment Artifacts | **적용** | 규약의 이식 장치(`scripts/sync.sh`, `.gitattributes`, `TODO.md`)가 이 자리를 대신함 |

---

## 2. 확정된 의존성 버전

PyPI 조회 결과(2026-09-09)로 실제 존재하는 버전을 고정합니다. 규약은 **완전 고정**을 요구합니다.

### `requirements.txt` (운영 의존성)
```
elasticsearch==8.19.3
PyYAML==6.0.3
```

**`elasticsearch` 버전 선택 근거**: 서버는 8.15.3 이고, 후보는 `8.15.1`(서버 마이너 일치)과
`8.19.3`(8.x 최신) 둘이었습니다. **`8.19.3` 을 선택**합니다.
- `elasticsearch-py` 는 **동일 메이저 버전 내 호환**을 보장하므로 와이어 프로토콜상 차이가 없습니다
- `8.15.1`(2024-09 릴리스) 대비 1년치 버그 수정이 들어 있습니다
- 분류자에 Python 3.13 을 선언한 것은 둘 중 `8.19.3` 뿐입니다 — 3.14(제약 C7)에서 돌 가능성이 더 높습니다

서버 마이너와 정확히 맞추길 원하시면 `8.15.1` 로 바꿉니다. 검토 시 알려주세요.

### `requirements-dev.txt` (개발 전용, `export-ignore`)
```
pytest==9.1.1
hypothesis==6.168.0
ruff==0.16.6
mypy==2.3.1
```

`pytest==9.1.1` 은 규약 저장소가 고정한 버전과 동일합니다.

### Python
`python3.14` 확인됨 — `/opt/homebrew/bin/python3.14` (제약 C7 충족)

---

## 3. 생성 단계

### A. 프로젝트 골격과 규약 장치

- [x] **Step 1** — git 저장소 초기화
  - 워크스페이스 **루트**에 `git init` (문서 하위 디렉터리가 아님)
  - 규약의 이식 장치(태그, `git archive`, `export-ignore`)가 git 을 전제함
  - *근거*: 규약 §2.2, §2.3

- [x] **Step 2** — venv 생성 및 의존성 설치
  - `python3.14 -m venv .venv`
  - `requirements.txt` + `requirements-dev.txt` 설치
  - **설치된 실제 버전을 `pip freeze` 로 확인**하고 §2 의 핀과 다르면 핀을 실제 값으로 정정
  - 3.14 에서 설치 실패하는 패키지가 있으면 **즉시 보고하고 중단** (규약 §3.1 의 조기 발견 목적)
  - *근거*: NFR Q2 부가 답변(자체 venv), 제약 C7

- [x] **Step 3** — `.gitignore` 생성
  - 규약 파일을 기반으로 하되 이 프로젝트에 맞게 조정
  - 데이터·산출물 차단: `*.csv` `*.jsonl` `outputs/` `logs/`
  - 설정 차단(allowlist): `configs/*.yaml` + `!configs/env.example.yaml`
  - `.venv/` `__pycache__/` `.pytest_cache/` `.omc/`
  - *근거*: 규약 §2.3, 하지 말 것 #11 (이름 나열 금지, allowlist 로)

- [x] **Step 4** — `.gitattributes` 생성 (`export-ignore` 목록)
  - `aidlc-docs/` `requirements-dev.txt` `README.md` `scripts/sync.sh` `.gitattributes` 등
  - **줄 끝 주석 금지** — git 이 그 줄을 조용히 무시함
  - *근거*: 규약 §2.3, 하지 말 것 #10

- [x] **Step 5** — `requirements.txt` / `requirements-dev.txt` 생성
  - §2 의 고정 버전
  - *근거*: 규약 §1.4, tech-stack-decisions §2·§3

- [x] **Step 6** — `configs/env.example.yaml` 생성
  - `paths.venv`, `elasticsearch`, `query`, `chunk`, `output` 전 항목
  - 실값 없음. 시크릿 자리는 빈 문자열
  - *근거*: NFR-S01, NFR-S02, tech-stack-decisions §5

- [x] **Step 7** — `scripts/sync.sh` 배치
  - 규약 저장소의 `scripts/sync.sh` 를 그대로 가져옴 (반드시 `scripts/` 안)
  - *근거*: 규약 §2.2 — 스크립트가 자기 위치에서 저장소 이름을 유도함

### B. 기반 모듈

- [x] **Step 8** — `src/run.py`
  - venv 갈아타기(`paths.venv` 훔쳐보기 → `os.execv`) + `es_crawler.__main__` 위임
  - PyYAML 미사용(손 파싱) — 이 시점엔 의존성이 없을 수 있음
  - *구현*: P-13 / *근거*: NFR-X05, 규약 §3.1

- [x] **Step 9** — `src/es_crawler/__init__.py`
  - 공개 API: `CrawlService`, `Config`, `load_config`, `TimeWindow`
  - *근거*: Application Design 컴포넌트 9

- [x] **Step 10** — `src/es_crawler/config.py`
  - `EsConfig` `QueryConfig` `ChunkConfig` `OutputConfig` `ColumnSpec` `Config` dataclass
  - `load_config()` — YAML 로드 + 검증
  - 검증 규칙 **BR-C01 ~ BR-C11** 전부 구현 (특히 BR-C01 `chunk_hours <= 24`)
  - `__repr__` 마스킹으로 `api_key` 노출 차단
  - *구현*: P-11, P-12 / *근거*: FR-7, NFR-S01~S04, BR-C01~C11

### C. 순수 로직 모듈 (속성 테스트 대상)

- [x] **Step 11** — `src/es_crawler/chunker.py`
  - `TimeWindow` (불변식 TW-1~TW-4, 파생값 `key`/`slug`/`duration`)
  - `DateChunker.chunks()` — L-1
  - `DateChunker.default_window()` — L-2 (D-1: anchor 18:00 KST)
  - 입력 시각 파싱 규칙 BR-T01~T06
  - *근거*: FR-2, D-1, D-2, BR-B01~B05, BR-F01~F04

- [x] **Step 12** — `src/es_crawler/schema.py`
  - `Field` dataclass + `INPUT_SCHEMA` (ES 문서의 기대 형태)
  - `validate(hits) -> Report` — 위반/노트 구분
  - 구조만 기술. 실제 값·분포는 적지 않음 (제약 C3)
  - *근거*: 규약 §1.1, NFR-O06, P-10

- [x] **Step 13** — `src/es_crawler/synth.py`
  - `generate(n, seed, mode)` — `INPUT_SCHEMA` 를 읽어 가짜 **ES 히트**(`_id`/`_index`/`_source`) 생성
  - 결정론적. `mode="adversarial"` 로 사고 유형 주입
  - *근거*: 규약 §1.2, NFR-T03, NFR-T04, NFR-T07

- [x] **Step 14** — `src/es_crawler/converter.py`
  - `extract_value()` — 점 표기법, `MISSING` 표식, 메타데이터 특별 취급 (BR-V02, BR-V03)
  - `to_row()` — 렌더링 판정 순서 (BR-V04~V08)
  - `convert()` — 스트리밍 + 원자적 쓰기, `utf-8-sig` + 헤더 (BR-V09, BR-V10)
  - *구현*: L-7, P-3 / *근거*: FR-5, BR-V01~V13

### D. I/O 모듈

- [x] **Step 15** — `src/es_crawler/writer.py`
  - `path_for()` `write()` `exists()`
  - 원자적 쓰기 + `fsync` (P-3), `ensure_ascii=False`
  - 히트 객체 전체 저장 (BR-E06), 0건이어도 파일 생성 (BR-E07)
  - *구현*: L-5, P-3 / *근거*: FR-4, BR-F01~F06

- [x] **Step 16** — `src/es_crawler/checkpoint.py`
  - `ChunkState`, `load()` `is_done()` `mark_done()` `mark_failed()` `pending()`
  - `reconcile()` — P-6 (파일 있으면 보정, `.tmp` 무시)
  - 원자적 쓰기 + `fsync`, 손상 시 중단 (BR-K06)
  - *구현*: L-6, P-3, P-6 / *근거*: FR-6, BR-K01~K07

- [x] **Step 17** — `src/es_crawler/load.py`
  - `build_client()` — 재시도 3회·타임아웃 60초 (P-1)
  - `EsExtractor.build_query()` — `gte`/`lt`, `sort:["_doc"]` (L-3, BR-B02)
  - `EsExtractor.iter_documents()` — scroll + `try/finally` 정리, `scroll_id` 매번 갱신 (P-4)
  - *구현*: L-3, L-4, P-1, P-4 / *근거*: FR-1, FR-3, BR-E01~E05

### E. 오케스트레이션과 표현

- [x] **Step 18** — `src/es_crawler/report.py`
  - RUN SUMMARY 렌더링. 표시 폭 계산(한글 2칸), 80칸 제한
  - `status` 어휘 4종 (P-8, Q4=A)
  - *구현*: P-8 / *근거*: NFR-O01~O09, 규약 §3.2

- [x] **Step 19** — `src/es_crawler/pipeline.py`
  - `CrawlService.extract()` — L-8, 실패 격리(P-2), 표본 수집(P-10), 진행 로깅(P-9)
  - `CrawlService.convert()` — L-9
  - `CrawlService.run()` — 추출 후 성공분만 변환 (P-7)
  - `closing()` 으로 제너레이터 정리 보장 (P-4 계약)
  - *구현*: L-8, L-9, P-2, P-5, P-6, P-7, P-9, P-10 / *근거*: FR-8, NFR-R04

- [x] **Step 20** — `src/es_crawler/__main__.py`
  - argparse: `--from` `--to` `--config` `--only` `--dry-run` `--rows` `--seed` `--limit` `--log-level`
  - 조기 실패 검사 순서 (P-12)
  - 종료 코드 0/1/2 (BR-X01~X08, NFR-X02)
  - RUN SUMMARY 는 stdout, 진행은 stderr (NFR-O02)
  - *구현*: P-8, P-12 / *근거*: FR-9, FR-10

### F. 테스트

- [x] **Step 21** — `tests/conftest.py`
  - 공용 픽스처, hypothesis 프로파일(shrinking 활성, 시드 로깅 — PBT-08)
  - **픽스처 파일 금지.** 데이터는 `synth.generate()` 로 (규약 §1.2)

- [x] **Step 22** — `tests/test_chunker.py`
  - 속성: **P-1** 합집합, **P-2** 무겹침, **P-3** 24h 이하, **P-4** 정렬·양끝
  - 속성: **P-9** `key` 왕복, **P-10** `slug` 유일성
  - 예제: `default_window()` 의 19:00/17:00/18:00 경계 (L-2 표)
  - *PBT 규칙*: PBT-02, PBT-03, PBT-07

- [x] **Step 23** — `tests/test_writer.py`
  - 속성: **P-5** JSONL 왕복 (쓰기→읽기 == 원본)
  - 예제: 0건이면 빈 파일 생성, 예외 시 `.tmp` 삭제, `.tmp` 는 최종 이름이 아님
  - *PBT 규칙*: PBT-02

- [x] **Step 24** — `tests/test_converter.py`
  - 속성: **P-6** 행 수 일치, **P-7** 행 길이 == 헤더 수, **P-8** 존재하는 경로는 그 값 반환
  - 예제: 렌더링 판정 순서 전수 — `MISSING`→`""`, `None`→`"NULL"`, `True`→`"true"`(not `1`), 배열/객체→JSON
  - *PBT 규칙*: PBT-03, PBT-07

- [x] **Step 25** — `tests/test_checkpoint.py`
  - 예제: 상태 전이 (없음→done/failed, failed→done), `pending()` 이 failed 를 포함
  - 예제: `reconcile()` 이 파일 있는 창을 보정하고 `.tmp` 는 무시
  - 예제: 손상된 JSON 이면 중단 (BR-K06)

- [x] **Step 26** — `tests/test_load.py`
  - 가짜 ES 클라이언트로 검증: scroll 반복, `scroll_id` 갱신 추적
  - **정상 종료·예외·조기 중단 세 경우 모두에서 `clear_scroll` 호출됨** (P-4)
  - `build_query()` 가 `gte`/`lt` 를 쓰고 `lte` 를 쓰지 않음
  - *ES 접속 없이 통과해야 함* (NFR-T07)

- [x] **Step 27** — `tests/test_schema.py` · `tests/test_run.py`
  - `validate()` 가 위반과 노트를 가름
  - `--dry-run` 스모크: 합성 데이터로 전 구간이 도는지, RUN SUMMARY 가 stdout 으로 나오는지
  - *근거*: NFR-T05, NFR-T07

### G. 문서와 운영 산출물

- [x] **Step 28** — `TODO.md` + `todo/`
  - 운영 환경에서 만들어야 하는 것: `configs/env.yaml` 채우기, 실행 스크립트, `{AA}/.gitignore`
  - 항목마다 "이 프로젝트의 사정인가 / 어느 프로젝트나 해당하는가" 구분
  - *근거*: 규약 §3.0, 하지 말 것 #9

- [x] **Step 29** — `README.md`
  - 실행 방법, 설정 항목, 출력물 설명
  - `export-ignore` 대상 (워크플로를 드러내므로)
  - *근거*: 규약 §2.3

- [x] **Step 30** — 코드 요약 문서
  - `aidlc-docs/construction/es-crawler/code/code-summary.md`
  - 생성된 파일 목록, 요구사항 추적, 미구현/보류 항목
  - *근거*: Code Generation 규칙 Step 11

---

## 4. 요구사항 추적 (Traceability)

User Stories 가 SKIP 되었으므로 요구사항 ID 로 추적합니다.

| 요구사항 | 구현 단계 | 검증 단계 |
|---|---|---|
| FR-1 ES 연결 | Step 17 | Step 26 |
| FR-2 날짜 분할 | Step 11 | Step 22 |
| FR-3 scroll 추출 | Step 17 | Step 26 |
| FR-4 JSONL 저장 | Step 15 | Step 23 |
| FR-5 CSV 변환 | Step 14 | Step 24 |
| FR-6 체크포인트·재개 | Step 16 | Step 25 |
| FR-7 설정 | Step 10 | (Step 27 간접) |
| FR-8 실행 인터페이스 | Step 8, 20 | Step 27 |
| FR-9 스케줄 실행 | Step 11, 20 | Step 22, 27 |
| FR-10 로깅 | Step 19, 20 | Step 27 |
| NFR-P01~P05 | Step 17, 19 | — (운영 환경 실측) |
| NFR-R01~R07 | Step 15, 16, 17, 19 | Step 23, 25, 26 |
| NFR-O01~O09 | Step 18, 20 | Step 27 |
| NFR-S01~S07 | Step 3, 6, 10 | (검토) |
| NFR-T01~T07 | Step 13, 21~27 | Step 21~27 |
| P-1 ~ P-13 | Step 8, 10, 14~20 | Step 22~27 |

---

## 5. 규모

| 항목 | 값 |
|---|---|
| 총 단계 | **30** |
| 애플리케이션 모듈 | 12개 (`run.py` + `es_crawler/` 11개) |
| 테스트 파일 | 8개 |
| 설정·규약 파일 | 6개 |
| 속성 기반 테스트 | 10개 속성 (P-1~P-10) |

---

## 6. 확장 규칙 준수 계획 (Extension Compliance)

| 규칙 | 강제 | 계획 |
|---|---|---|
| **PBT-02** (왕복) | 차단성 | Step 23 (JSONL 왕복), Step 22 (`key` 왕복) |
| **PBT-03** (불변식) | 차단성 | Step 22 (청크 4속성), Step 24 (변환 3속성) |
| **PBT-07** (제너레이터 품질) | 차단성 | Step 21 에 도메인 제너레이터를 재사용 가능하게 정의 — ES 히트, 시간 창, 컬럼 명세 |
| **PBT-08** (shrinking·재현성) | 차단성 | Step 21 의 hypothesis 프로파일. shrinking 비활성화 금지, 실패 시 시드 출력 |
| **PBT-09** (프레임워크) | 차단성 | ✅ 이전 단계 충족 — `hypothesis==6.168.0` 을 Step 5 에 고정 |
| PBT-01, 04~06, 10 | 권고 | Functional Design L-10 에 식별 완료. P-13(멱등성), P-14(상태 기반)은 여력이 되면 추가 |
| Security Baseline | N/A | 옵트아웃 |
| Resiliency Baseline | N/A | 옵트아웃 |
