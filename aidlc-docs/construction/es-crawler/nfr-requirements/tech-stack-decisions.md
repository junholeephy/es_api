# 기술 스택 결정 (Tech Stack Decisions) — `es-crawler`

**단계**: CONSTRUCTION - NFR Requirements
**단위(Unit)**: `es-crawler`

> **우선순위**: `/Users/junho/coding_work/general_implementation` 규약 > 이 프로젝트의 다른 모든 결정

---

## 1. 언어·런타임

| 항목 | 결정 | 근거 |
|---|---|---|
| 언어 | Python | 사용자 요청 |
| 최소 버전 | **3.14** | 제약 C7 — 운영 환경이 3.14이고, 개발 장비도 같은 버전을 써야 3.14 wheel 이 없는 패키지를 미리 거른다. NFR Q1=B(3.12)를 규약이 덮어씀 |
| venv | 프로젝트 폴더 안에 자체 venv | 사용자 요청 (NFR Q2 부가 답변) |
| 패키지 설치 | **하지 않음** | 제약 C7 — 공용 venv 에 우리 패키지를 남기지 않아야 디렉터리 통째 교체가 무연산이 된다 |
| import 경로 | `python src/run.py` 실행 시 `sys.path[0]` 이 `src/` 가 되어 `es_crawler` 가 그대로 import 됨 | 규약 §3.1. `PYTHONPATH` 도 설치도 불필요 |

**NFR Q2=A(`pyproject.toml` + `pip install -e .`)는 규약에 의해 뒤집혔습니다.**
`pyproject.toml` 은 만들지 않고, `ruff`·`mypy`·`pytest` 설정은 각자의 설정 파일에 둡니다.

---

## 2. 런타임 의존성 (`requirements.txt`)

규약은 **버전 완전 고정**을 요구합니다 — "어디서 돌리든 같은 버전을 쓰기 위한 잠금 파일".

```
elasticsearch==8.15.1
PyYAML==6.0.2
```

| 패키지 | 용도 | 근거 |
|---|---|---|
| `elasticsearch` | ES 8.15.3 서버 접속, scroll 페이징, 재시도, API Key 인증 | CQ1=A (Application Design). 서버 메이저 버전과 정합 |
| `PyYAML` | `configs/env.yaml` 파싱 | NFR Q4=A (설정 파일 YAML) |

**NFR Q3=A(`>=8.15,<9` 범위 핀)는 규약에 의해 뒤집혔습니다.**

**`PyYAML` 추가에 대한 주의**: 규약의 `src/run.py` 는 `paths.venv` 한 키를 읽으려고
PyYAML 을 넣지 않고 **손으로 파싱**합니다. 그 방침을 유지합니다 —
`run.py` 는 venv 를 갈아타기 **전에** 실행되므로, 그 시점에 아직 의존성이 설치되지 않았을 수 있습니다.
본체(`es_crawler/config.py`)는 venv 전환 이후에 돌므로 PyYAML 을 씁니다.

---

## 3. 개발 의존성 (`requirements-dev.txt`)

이식에서 제외됩니다 (`.gitattributes` 의 `export-ignore`).

```
pytest==9.1.1
hypothesis==6.140.2
ruff==0.14.5
mypy==1.19.0
```

| 패키지 | 용도 | 근거 |
|---|---|---|
| `pytest` | 예제 기반 테스트 | Q6=A. 규약 저장소가 이미 이 버전으로 고정 |
| **`hypothesis`** | **속성 기반 테스트 — PBT-09 충족** | Q6=A, Q14=B (Partial 모드) |
| `ruff` | 린트 + 포맷 | Q7=A |
| `mypy` | 정적 타입 검사 | Q7=A |

**버전은 설치 시점의 실제 최신 안정판으로 고정합니다.** 위 숫자는 자리표시이며,
Code Generation 단계에서 `pip index` 로 확인한 실제 버전을 박습니다 —
규약이 요구하는 것은 "고정되어 있을 것"이지 특정 숫자가 아닙니다.

### PBT-09 준수 확인

| 요구 | `hypothesis` |
|---|---|
| 도메인 타입용 커스텀 제너레이터 | ✅ `@st.composite`, `st.builds` |
| 실패 케이스 자동 shrinking | ✅ 기본 활성 |
| 시드 기반 재현성 | ✅ `--hypothesis-seed`, 실패 시 `@reproduce_failure` 출력 |
| 기존 테스트 러너와 통합 | ✅ pytest 플러그인 내장 |

**PBT-09는 Partial 모드에서 차단성 규칙이며, 이 선정으로 충족됩니다.**

---

## 4. 파일 배치

규약 §2.1·§3.1 을 따릅니다. 패키지 이름은 `es_crawler` 입니다
(규약이 `adopt.sh` 둘째 인자로 개명을 명시 허용하며, 기능을 가리키는 평범한 이름이라 C9 에 저촉되지 않음).

```
es_api/
  README.md                     워크플로 설명 (export-ignore)
  TODO.md                       운영 환경에서 만들어야 할 것 (이식됨)
  todo/                         그 규격 (이식됨)
  IMPLEMENTATION_SPEC.md?       규약 원문은 복사하지 않고 참조만
  .gitattributes                이식 제외 목록 (자기 자신도 제외)
  .gitignore                    데이터·산출물·설정 차단
  requirements.txt              elasticsearch, PyYAML (고정)
  requirements-dev.txt          pytest, hypothesis, ruff, mypy (export-ignore)
  configs/
    env.example.yaml            설정 예시. 실값은 운영 환경에만
  scripts/
    sync.sh                     이식 스크립트 (export-ignore)
  src/
    run.py                      진입점. venv 갈아타기 + 위임만
    es_crawler/
      __init__.py
      __main__.py               CLI 인자, 실행 순서, 종료 코드
      schema.py                 ES 문서 스키마 (단일 출처) + validate()
      synth.py                  가짜 ES 히트 생성
      load.py                   Elasticsearch 접근 — 입력 포맷을 아는 유일한 곳
      pipeline.py               오케스트레이션 (추출 -> 변환)
      report.py                 RUN SUMMARY
      config.py                 configs/env.yaml 로딩·검증
      chunker.py                시간 창 분할
      writer.py                 JSONL 쓰기
      converter.py              JSONL -> CSV
      checkpoint.py             청크 상태
  tests/
    conftest.py
    test_chunker.py             속성 기반 (P-1~P-4)
    test_writer.py              속성 기반 왕복 (P-5)
    test_converter.py           속성 기반 (P-6~P-8) + 예제 기반
    test_checkpoint.py
    test_load.py                모킹된 ES 클라이언트로 scroll 정리 검증
    test_run.py                 --dry-run 스모크
  aidlc-docs/                   AI-DLC 문서 (export-ignore)
```

### 규약 모듈과 이 프로젝트 컴포넌트의 대응

| 규약 모듈 | 이 프로젝트에서 | Application Design 대응 |
|---|---|---|
| `schema.py` | ES 문서의 기대 형태 + 위반 검사 | (신규 — 규약이 요구) |
| `synth.py` | 가짜 ES 히트 생성 | (신규 — 규약이 요구) |
| `load.py` | `EsExtractor` — scroll 페이징, 컨텍스트 정리 | `extractor.py` |
| `pipeline.py` | `CrawlService` — 청크 루프, 추출 후 변환 | `pipeline.py` |
| `report.py` | RUN SUMMARY 렌더링 | (신규 — 규약이 요구) |
| `__main__.py` | CLI, 종료 코드 | `cli.py` |
| (프로젝트 고유) | `config` `chunker` `writer` `converter` `checkpoint` | 동일 |

---

## 5. 설정

| 항목 | 결정 |
|---|---|
| 파일 | `configs/env.yaml` **하나** (예시는 `configs/env.example.yaml`) |
| 형식 | YAML |
| 위치 | 운영 환경에서는 `{AA}` 루트의 `configs/env.yaml` (사본 안에 두면 다음 sync 때 지워짐) |
| 시크릿 | 같은 파일. `.gitignore` 가 `configs/*.yaml` 을 통째로 막고 `env.example.yaml` 만 예외 |
| `.env` | **쓰지 않음** — 기존 NFR-6 을 규약이 대체 |

```yaml
paths:
  venv:                      # 이 파이썬으로 갈아타서 실행. 비우면 현재 파이썬

elasticsearch:
  hosts: ["https://es.internal:9200"]
  api_key: ""                # 실값은 운영 환경에서만
  request_timeout: 60
  max_retries: 3

query:
  index: "logs-*"
  time_field: "@timestamp"
  batch_size: 2000
  scroll_ttl: "5m"
  extra_filters: []

chunk:
  timezone: "Asia/Seoul"
  anchor_time: "18:00"
  chunk_hours: 24

output:
  directory: "outputs"
  encoding: "utf-8-sig"
  missing_value: ""
  null_value: "NULL"
  schema_sample: 1000
  columns:
    - source: "_id"
      header: "문서ID"
    - source: "@timestamp"
      header: "시각"
    - source: "user.name"
      header: "사용자명"
```

**바뀔 만한 값 중 CLI 인자로 받는 것** (규약 §1.3):
`--from`, `--to`, `--config`, `--only`, `--dry-run`, `--rows`, `--seed`, `--limit`

---

## 6. 실행 방식

```bash
# 개발 장비 — 클러스터 없이 전 구간 스모크
python src/run.py --dry-run

# 운영 환경 — 인자 없이 실행하면 [전날 18:00, 당일 18:00) KST
python src/run.py --config configs/env.yaml

# 특정 범위 (시각을 반드시 명시. BR-T01)
python src/run.py --config configs/env.yaml --from 2026-09-01T18:00 --to 2026-09-06T18:00

# 개발용 보조 — 한 단계만
python src/run.py --config configs/env.yaml --only convert
```

**스케줄러는 이 명령을 하루 한 번 19:00 KST 에 호출합니다.**
기존 D-4 의 `extract && convert` 두 번 호출은 규약 하지 말 것 #12 에 의해 폐기되었습니다.

---

## 7. 배제한 선택지와 이유

| 선택지 | 배제 이유 |
|---|---|
| `pyproject.toml` + `pip install -e .` | 제약 C7 — 공용 venv 에 패키지를 남기면 디렉터리 교체 때 뒤처리가 생긴다 |
| `elasticsearch>=8.15,<9` 범위 핀 | 규약 `requirements.txt` — "어디서 돌리든 같은 버전" |
| `.env` + `python-dotenv` | 규약이 설정을 `configs/env.yaml` 하나로 모은다. 의존성도 하나 줄어든다 |
| CLI 서브커맨드 2개 | 하지 말 것 #12 — 리포트가 갈라지고 C4 때문에 합칠 수 없다 |
| 구조화 로깅(`structlog`) | Q8=A(stdout만) + 규약의 RUN SUMMARY 가 회수 채널. 의존성을 늘릴 이유가 없다 |
| 파일 로깅 | Q8=A. 규약상 로그도 반출 불가(C4)라 파일로 남길 이득이 없다 |
| 테스트 픽스처 파일 | 규약 §1.2 — 없는 파일은 커밋될 수 없다. `synth.generate()` 로 대체 |
| `pytest-cov` | Q6=A — 커버리지 수치 목표를 두지 않기로 함 |

---

## 8. 확장 규칙 준수 요약 (Extension Compliance)

| 규칙 | 상태 | 근거 |
|---|---|---|
| **PBT-09** | ✅ **준수** | `hypothesis` 를 선정하고 `requirements-dev.txt` 에 고정 버전으로 포함. 커스텀 제너레이터·shrinking·시드 재현성·pytest 통합 모두 충족 (§3 확인표) |
| PBT-01~08, 10 | 해당 없음 (다른 단계) | — |
| Security Baseline | N/A | 옵트아웃 (Q12=B) |
| Resiliency Baseline | N/A | 옵트아웃 (Q13=B) |

**차단성 발견 사항(Blocking findings): 없음.**
