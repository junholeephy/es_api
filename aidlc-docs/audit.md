# AI-DLC 감사 기록 (요약)

**프로젝트**: es_api — Elasticsearch 시간 구간 추출기
**기간**: 2026-09-09
**결과**: 워크플로 완료. 커밋 `920f6e2`, 태그 `v0.1`, preflight 통과

> 원래 이 파일은 사용자 입력 원문과 AI 응답 전문을 담은 44KB 로그였습니다.
> 워크플로 완료 후 **결정과 근거 중심으로 압축**했습니다 (사용자 요청, 2026-09-09).
> 각 단계의 상세 산출물은 `aidlc-docs/` 아래 해당 문서에 있습니다.

---

## 1. 단계 진행

| # | 단계 | 결과 | 산출물 |
|---|---|---|---|
| 1 | Workspace Detection | Greenfield 판정. 소스·빌드 파일 없음 | `aidlc-state.md` |
| 2 | Reverse Engineering | **SKIP** — 기존 코드 없음 | — |
| 3 | Requirements Analysis | 2라운드 질의 (14문항 + 5문항) 후 승인 | `inception/requirements/requirements.md` |
| 4 | User Stories | **SKIP** — 개발자 도구, 단일 사용자 유형 | — |
| 5 | Workflow Planning | 실행 6단계 / 건너뜀 4단계. 리스크 Low | `inception/plans/execution-plan.md` |
| 6 | Application Design | 8문항 후 승인. 9모듈 구조 | `inception/application-design/` 4개 |
| 7 | Units Generation | **SKIP** — 단일 패키지 | — |
| 8 | Functional Design | 9문항 + 2문항 명확화 후 승인 | `construction/es-crawler/functional-design/` 3개 |
| 9 | NFR Requirements | 9문항 + 규약 정합 5문항 후 승인 | `construction/es-crawler/nfr-requirements/` 2개 |
| 10 | NFR Design | 6문항 후 승인. 패턴 13종 | `construction/es-crawler/nfr-design/` 2개 |
| 11 | Infrastructure Design | **SKIP** — 클라우드 리소스 없음 | — |
| 12 | Code Generation | 계획 30단계 승인 후 전체 실행 | `construction/es-crawler/code/code-summary.md` |
| 13 | Build and Test | 지침 5종. 실측 수행 | `construction/build-and-test/` 5개 |
| 14 | Operations | **플레이스홀더** | `operations/operations.md` |

---

## 2. 요구사항 확정 (1~3단계)

사용자의 최초 요청은 "ai-dlc 방법으로 개발 시작하자"뿐이었고, 대상 시스템이 정해지지
않아 질의로 좁혔습니다.

**Round 1 원문 (핵심)**
> "elasticsearch 8.15.3 버전을 사용해서 파이썬으로 데이터를 크롤링하고자 해, REST API를
> 사용해서, 만개가 넘는 데이터를 크롤링 할 때는 scrolling search/scroll api 를 사용해서
> 가져오고자 해. 그리고 제약이 있는데, 한번에 가져오는 데이터 양은 하루에 해당하는
> 24시간 데이터가 최대야. 5일치 데이터를 가져오고 싶다면 최소 5번으로 나눠서 가져와야
> 한다는 거지"

**주요 답변**

| 항목 | 결정 |
|---|---|
| 페이징 | scroll API (ES 8.x deprecated 임을 알리고 사용자가 명시 선택) |
| 24h 제약의 성격 | 클러스터 부하 감소를 위한 자체 규칙 |
| 여러 날 요청 | 자동 분할 (거부 아님) |
| 실행 | 순차. 병렬 없음 |
| 재개 | 필요 — 상태 파일, 실패 청크 자동 재시도 |
| 출력 | JSONL 보존 → 별도 단계에서 CSV. 지정 컬럼만 + 헤더 리네이밍 |
| 인증 | API Key |
| 확장 | Security ❌ / Resiliency ❌ / **PBT ✅ Partial** |

**검토 중 확정 (D-1, D-2)**
- 스케줄러는 매일 **19:00 KST** 실행, 대상은 **전날 18:00 ~ 당일 18:00**
- 타임존 기본값 `Asia/Seoul`, 질의는 절대시각 기준

D-1의 파생 효과로 하루의 경계가 자정이 아니게 되어, 청크 분할이 **설정 가능한 기준
시각(anchor)에 정렬**되고 파일명이 창의 종료 시각을 쓰게 되었습니다.

---

## 3. 규약 우선 지시 (9단계)

**사용자 지시**: "general_implementation의 규약이 다른 모든 규약보다 우선이야"

`/Users/junho/coding_work/general_implementation` 의 규약을 읽고 이 프로젝트의
확정 결정과 대조한 결과 **8건이 충돌**했고, 전부 규약 쪽으로 뒤집었습니다.

| 기존 결정 | 변경 후 | 근거 |
|---|---|---|
| CLI 서브커맨드 2개 | 단일 진입점, 실행 요약 한 장 | 하지 말 것 #12, §3.2 |
| 스케줄러가 두 명령 연결 | 단일 명령 | 동일 |
| 평평한 9모듈 | 공유 모듈 + 프로젝트 모듈 | §1.5, §3.1 |
| Python 3.12 | **Python 3.14** | C7 |
| `pip install -e .` | 설치 없음, `python src/run.py` | C7 |
| `elasticsearch>=8.15,<9` | 완전 고정 | requirements.txt 규칙 |
| 시크릿 `.env` | `configs/env.yaml` | 설정 일원화 |
| (없음) | 실행 요약·스키마 단일 출처·합성 데이터 추가 | §1.1, §1.2, §3.2 |

패키지 이름 `es_crawler` 는 규약이 정하지 않아(개명을 명시 허용) 판단해 결정했습니다.

**적응 1건**: 규약의 `validate(rows)` 는 전체 리스트를 받지만, 예상 규모(10만~100만 건)와
스트리밍 요구가 충돌해 **첫 청크의 표본 1000건**만 검증하도록 바꾸고 그 사실을 화면에
표기하게 했습니다.

---

## 4. 기술 스택 (9단계)

| 항목 | 값 | 확인 |
|---|---|---|
| Python | 3.14.7 | `/opt/homebrew/bin/python3.14` |
| `elasticsearch` | 8.19.3 | 8.15.1(서버 마이너 일치) 대신 선택 — 동일 메이저 호환 보장, 1년치 수정, 3.13 지원 선언 |
| `PyYAML` | 6.0.3 | |
| `pytest` / `hypothesis` | 9.1.1 / 6.168.0 | **PBT-09 충족** |
| `ruff` / `mypy` | 0.16.6 / 2.3.1 | |

---

## 5. 발견하고 고친 결함 (12~13단계)

전부 **속성 기반 테스트**가 찾았습니다. 셋 다 조용히 틀리는 종류 — 프로그램은 정상
종료하고 로그도 깨끗합니다.

### 결함 1 — TW-4 (오프셋 동일 요구)

제가 Functional Design 에 넣은 불변식이 서머타임을 넘는 구간을 통째로 거부했습니다.
구간 길이는 절대 시간으로 재므로 두 끝의 오프셋이 달라도 정상입니다.

→ 불변식 철회. 회귀 테스트 `test_a_window_may_cross_a_daylight_saving_change`.

### 결함 2 — 벽시계 산술

`chunks()` 가 지역 시각에 `timedelta` 를 더했는데 파이썬은 이를 **벽시계 기준**으로
계산합니다. 서머타임이 끝나는 날 01:00 이 두 번 오므로 **한 조각이 두 시간을 덮으면서
`duration` 은 한 시간이라고 답했습니다.** 제약 C-3(조회당 24시간 상한)이 DST 타임존에서
무력화됩니다.

→ `chunks()`·`duration`·불변식을 절대 시간 기준으로 변경. fall-back 하루가 24h + 1h 로
분할됨을 확인. 회귀 테스트 2개.

### 결함 3 — 파일명이 분까지만

`slug` 가 `%H%M` 을 써서 초를 버렸습니다. `05:00:00` 과 `05:00:01` 에 끝나는 두 조각이
같은 파일명을 갖고, **기록에는 둘 다 완료로 남는데 파일은 하나**입니다.
CQ1=A 로 막으려던 바로 그 실패였고 제 수정이 불완전했습니다.

→ `slug` 를 `key.replace(":", "")` 로 파생. 콜론 제거는 되돌릴 수 있으므로 키가 다르면
이름도 반드시 다릅니다. 파일명이 `T1800+0900` → `T180000+0900` 으로 변경.
회귀 테스트 2개.

### 그 외 — 테스트가 틀린 경우 2건

- `test_key_round_trips_to_the_end_boundary` 가 `==` 로 datetime 을 비교. PEP 495 상
  DST fold 안의 시각은 같은 순간이어도 다른 표현과 같지 않다고 판정됩니다 → 순간 비교로 수정
- `_source` 안에 `_score` 필드가 있는 문서. 메타데이터 이름은 언제나 히트 최상위를
  가리키므로 설계대로지만 테스트에 없었습니다 → `test_metadata_names_are_reserved` 추가

---

## 6. 릴리스 (커밋·태그)

**사용자 요청**: "커밋하고 v0.1 태그 내줘"

첫 preflight 가 **실패**하며 제 검사가 놓친 C9 위반을 잡았습니다.

```
[sync] ⚠ 사본에 워크플로 어휘가 남아있음 (C9):
TODO.md:9:| | 무엇 | 왜 여기서 만드나 | 규격 |
```

제 패턴은 `규격 ?§` 처럼 § 기호를 요구했지만 `sync.sh` 는 맨 단어 "규격"을 봅니다.
표 헤더를 "만드는 법"으로 바꾸고 amend 후 재태그 → **preflight OK, 29 files**.

---

## 7. 최종 검증

| 항목 | 결과 |
|---|---|
| 테스트 | **105 passed** — 서로 다른 시드로 8회 연속 |
| `ruff check` / `format --check` | clean |
| `mypy` | Success, 12 source files |
| `--dry-run` | 종료 `0`, `status: OK` |
| `--dry-run --adversarial` | 종료 `1`, `status: SCHEMA MISMATCH` |
| 변환 성능 | 500,000행 / 90MB → 1.9초, 최대 RSS 45.6MB (입력 크기와 무관) |
| 이식 표면 | 29개 파일. 개인 경로·이메일·외부 API·워크플로 어휘 없음 |
| preflight | OK |

---

## 8. 남은 작업

| 항목 | 조건 |
|---|---|
| 통합 테스트 실행 | Elasticsearch 8.15.3 인스턴스 필요. 지침은 `build-and-test/integration-test-instructions.md` 시나리오 7종 |
| `INPUT_SCHEMA` 실제 필드 확정 | 현재 3개는 자리표시. 첫 실행의 `schema` 줄이 알려줌 |
| `batch_size` 기본값 조정 | 하루치 실제 문서 수 확인 후 |

---

## 9. v0.2 이후의 변경

승인된 설계 이후 사용자 요청으로 바뀐 것들. 각 항목은 태그 하나에 대응한다.
v0.5 ~ v0.7 은 다른 세션에서 낸 갱신 스크립트 동기화 커밋이라 여기 적지 않는다.

### v0.3 — 인증서 검증을 설정으로 (2026-09-11)

**사용자 입력**: "load.py/config.py 쪽에 verify_certs=False로 설정해야 할 것 같아"

**결정**: 코드에 박지 않고 `EsConfig.verify_certs` 설정 항목으로 열었다. 코드
기본값은 `true`, `configs/env.example.yaml` 은 `false`.

**근거**: 박아두면 제대로 된 인증서를 받은 뒤에도 되돌릴 수 없고, 어느 환경이
검증 없이 도는지 구분되지 않는다. 끄려면 설정 파일에 한 줄을 적어야 하므로
꺼져 있다는 사실이 어딘가에 남는다. `ca_certs` 와 함께 적으면 `ConfigError` —
검증을 끄면 CA 는 아무 일도 하지 않는데, 적어뒀으니 검증된다고 믿은 채 도는
것이 가장 나쁘다.

### v0.4 — 기본 필터 (2026-09-11)

**사용자 입력**: "extra_filters에 추가해줘" (Kibana KQL
`response_body_content.raw_text: *` 에 대한 질문에 이어서)

**결정**: `query.extra_filters` 에 `exists` 절을 기본으로 넣었다.

**주의로 남김**: `exists` 는 색인 여부를 본다. multi-field 의 하위 필드라면
부모에 값이 있어도 하위 필드가 색인되지 않은 문서는 빠진다.

### v0.8 — 기본 실행을 추출까지로 (2026-09-11)

**사용자 입력**: "지금 코드가 json을 csv로 변환까지 한다면, 이것을 변환까지는
하지말고 json으로 저장하는 것 까지만 기능하게 하자"

**확인 질문**: 변환 코드를 지울지 기본 동작만 바꿀지 물었고, **기본 실행에서만
빼기**를 선택했다.

**결정**: 명령행 기본 실행은 `extract_only`. `converter.py` 와 `output.columns`
는 그대로 두고 `--only convert` 로 접근한다. `--only extract` 는 기본과 같은
뜻이 되었지만 계속 받는다 — 이미 그 인자를 적어둔 실행 스크립트가 있다.

**근거**: CSV 규칙이 아직 정해지지 않았다("json을 csv로 변환하는 로직에 대해
추가사항이 있어"). 지웠다가 다시 만드는 것보다 기본값을 옮기는 편이 되돌리기
쉽다. 받아오는 일과 정리하는 일은 실패 조건이 다르고, 정리 규칙이 바뀌어도
이미 받아둔 문서를 다시 조회할 이유는 없다.

**함께 고친 것**: RUN SUMMARY 가 **돌지 않은 단계의 줄을 내지 않는다.**
`convert : 0 rows -> 0 csv` 는 변환을 시도했다가 한 건도 못 만든 것처럼
읽힌다. `chunks` 블록도 실제로 돌린 단계의 결과를 센다.

### v0.11 — 기능이 받는 모양을 바로잡고 등록부를 규약 자리로 (2026-09-12)

**사용자 입력**: "B로 진행하고, 스캐폴드와 다른 두 가지도 같이 맞춰줘"

**배경**: 다른 세션이 `general_implementation` 의 features 스캐폴드를 옮겨왔는데
(v0.9, v0.10), 옮기는 과정에서 세 가지가 어긋나 있었다.

**1. 기능이 받는 것이 문서가 아니라 히트 봉투였다.** `template` 이
`row.values()` 를 훑는데 거기 담긴 것은 `_index` · `_id` · `_score` · `_source`
넷이다. `sort: ["_doc"]` 라 `_score` 는 언제나 `None` 이어서 예시 판정이 데이터와
무관하게 **항상 100%** 를 냈다 (확인: `generate(200)` → `200 (100.00%)`).
원본 스캐폴드는 납작한 행을 받으므로 원본의 결함이 아니라 이식 과정의 문제다.

선택지 A(등록부가 `_source` 를 벗겨 넘김)와 B(봉투인 것을 드러내고 `resolve` 로
꺼냄)를 비교해 **B** 를 골랐다. 근거: 이 프로그램의 입력은 끝까지 ES 히트이고,
`_id` 로 중복을 세는 기능이 막히지 않으며, 점 경로가 `output.columns` · `schema`
· `converter` 가 이미 쓰는 표기와 같다.

`schema.resolve` 에 `default` 인자를 더해 기능이 모듈 private 인 `_MISSING` 을
import 하지 않게 했다. 기존 호출부는 인자를 주지 않으므로 동작이 그대로다.

**2. `FEATURES` 위치.** 스펙 §1.5 가 "기능 목록이 `pipeline.py` 에 있는 것이
요점"이라고 근거까지 적어둔다 — 그 파일은 프로젝트가 고치는 파일이고 공유 코드와
진입점은 기능이 늘어도 손대지 않는다. `features/__init__.py` 에 있던 등록부를
`pipeline.py` 로 옮겼다.

**3. 기능이 없을 때의 `metrics` 줄.** 스펙 예시는 `{"rows": ...}` 를 언제나
넣는다. 분모가 보이지 않으면 나중에 붙는 비율을 읽을 수 없어서다. 여기서는 입력이
히트라 키 이름을 `hits` 로 맞췄다. 표본이 첫 조각에서 뽑은 것이라 더 필요하다.

**회귀 테스트**: `test_the_template_reads_the_document_not_the_envelope` — 채워진
`_source.user.name` 10건이 `0 (0.00%)` 로, 빈 것 10건이 `100 (100.00%)` 로 나와야
한다. 봉투를 훑는 코드로 돌아가면 앞쪽이 100% 가 되어 깨진다.

**확인**: `template` 을 실제로 등록해 전 구간 실행 — `hits 500` / `template 27
(5.40%)`. 이전 구현이었다면 `500 (100.00%)`.
