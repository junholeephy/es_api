# 비기능 요구사항 (NFR Requirements) — `es-crawler`

**단계**: CONSTRUCTION - NFR Requirements
**단위(Unit)**: `es-crawler`
**작성일**: 2026-09-09

> **우선순위 규칙 (사용자 지시, 2026-09-09)**
> `/Users/junho/coding_work/general_implementation` 의 규약이 **다른 모든 규약보다 우선**한다.
> 이 프로젝트의 이전 결정과 충돌하면 규약이 이긴다. 아래 요구사항은 그 결과를 반영한 것이다.

---

## 1. 성능·처리량 (Performance)

| ID | 요구사항 | 값 | 근거 |
|---|---|---|---|
| NFR-P01 | 하루치 예상 문서 수 | **10만 ~ 100만 건** (추정) | Q4=C |
| NFR-P02 | scroll 배치 크기 기본값 | **2000** | 100만 건 기준 scroll 500회. 1000이면 1000회 — 왕복 횟수를 절반으로 줄임 |
| NFR-P03 | scroll TTL 기본값 | **5m** | 한 배치 처리 시간의 수십 배 여유 |
| NFR-P04 | 메모리 상한 | 결과 전체를 적재하지 않음. **스트리밍 처리** | 100만 건을 리스트로 들면 수 GB |
| NFR-P05 | 성능 목표(SLA) | **없음** | 무인 배치 실행. 19:00 시작해 다음 날까지 여유 |

**NFR-P02의 근거**: Q4=C(10만~100만 건)에서 배치 크기가 실질적 의미를 갖습니다.
다만 배치가 크면 한 응답의 메모리와 scroll 컨텍스트 유지 비용이 함께 커지므로,
2000을 기본값으로 두고 설정으로 조정 가능하게 합니다.

**주의 — 추정값이다**: Q4 답변이 "잘 모르지만 C 정도 될 거라 예상"이었습니다.
실제 규모는 운영 환경 첫 실행의 RUN SUMMARY 에서 확인하고, 그 수치를 인사이트로 가지고 나와
`configs/env.example.yaml` 의 기본값에 반영합니다 (규약 §4).

---

## 2. 신뢰성 (Reliability)

| ID | 요구사항 | 값 | 근거 |
|---|---|---|---|
| NFR-R01 | 일시적 오류 재시도 | **3회** (`max_retries=3`, `retry_on_timeout=True`) | Q5=A |
| NFR-R02 | 요청 타임아웃 | **60초** | Q5=A |
| NFR-R03 | 재시도 대상 | 429, 502, 503, 504, 연결 타임아웃 | `elasticsearch-py` 기본 + 명시 설정 |
| NFR-R04 | 청크 실패 격리 | 한 청크 실패가 나머지를 막지 않음 | BR-X06 |
| NFR-R05 | 재개 | 체크포인트 기반. `failed`는 자동 재시도 | FR-6, BR-K03 |
| NFR-R06 | 원자적 쓰기 | JSONL·CSV·체크포인트 모두 `.tmp` -> `os.replace` | BR-F05, BR-K05 |
| NFR-R07 | scroll 컨텍스트 정리 | 정상·예외·조기 중단 모두에서 보장 | BR-E03, 제약 C-2 |

---

## 3. 관측성 (Observability)

| ID | 요구사항 | 근거 |
|---|---|---|
| NFR-O01 | **RUN SUMMARY 블록**을 성공·실패 무관하게 마지막에 출력 | 규약 §3.2 |
| NFR-O02 | RUN SUMMARY 는 **stdout**, 진행 상황은 **stderr** | 규약 §3.2 — 요약이 stderr로 새면 `> log.txt` 가 빈다 |
| NFR-O03 | 실행 인자를 RUN SUMMARY 에 그대로 한 줄 기록 | 반출 불가(C4)이므로 이 한 줄이 재현 수단 |
| NFR-O04 | `version` 은 빈칸 금지. 모르면 `unversioned` | 규약 §3.2 |
| NFR-O05 | 한 줄에 한 항목, **표시 폭** 80칸 이내 (한글 2칸 계산) | 규약 §3.2 |
| NFR-O06 | 스키마 위반은 사람이 그대로 옮겨 적을 수 있는 형태로 | 규약 §3.2 — 포맷 회수의 주 채널 |
| NFR-O07 | 실데이터의 개별 값·식별자를 화면에 찍지 않음 | 제약 C3 |
| NFR-O08 | 로그 출력은 **stdout/stderr만**. 파일 로깅 없음 | Q8=A + 규약 |
| NFR-O09 | 한 번 실행에 RUN SUMMARY 는 **한 장** | 규약 §3.2, 하지 말 것 #12 |

### RUN SUMMARY 에 담을 지표

```
================ RUN SUMMARY ================
version   : v0.1.0 (a1b2c3d)
args      : --from 2026-09-08T18:00 --to 2026-09-09T18:00
window    : 2026-09-08T18:00+09:00 .. 2026-09-09T18:00+09:00 (1 chunk)
schema    : 6 ok / 1 MISMATCH
  - user.grade  : unexpected values {'Z'}
chunks    :
  done                 1
  failed               0
  skipped              0
extract   : 152,431 docs -> 1 jsonl
convert   : 152,431 rows -> 1 csv
runtime   : 412.3s, peak 0.31GB
status    : OK
=============================================
```

---

## 4. 보안 (Security)

| ID | 요구사항 | 근거 |
|---|---|---|
| NFR-S01 | ES 접속 정보·API Key 는 **`configs/env.yaml`** 에 둔다 | CQ4=A (기존 NFR-6의 `.env` 방식을 규약이 대체) |
| NFR-S02 | `configs/*.yaml` 은 `.gitignore` 로 통째 차단. `env.example.yaml` 만 예외 | 규약 §2.3 — 이름을 하나씩 적으면 오타 한 번에 무시가 풀린다 |
| NFR-S03 | API Key 를 로그·오류 메시지·RUN SUMMARY 에 출력하지 않음 | NFR-6 |
| NFR-S04 | 예외 로깅 시 클라이언트 설정 객체를 덤프하지 않음 | 헤더에 키가 실릴 수 있음 |
| NFR-S05 | `src/` 안에서 LLM·외부 API 호출 금지 | 제약 C8. 이 프로젝트에는 해당 사항 없음 |
| NFR-S06 | 개인 머신 절대 경로(`/Users/…`, `/home/…`)를 코드·설정에 두지 않음 | `sync.sh` 가 기계적으로 검사 |
| NFR-S07 | 이메일·커밋 트레일러가 이식 표면에 남지 않음 | `sync.sh` 가 기계적으로 검사 |

Security Baseline 확장은 옵트아웃(Q12=B)이지만, 위 규칙은 규약과 NFR-6에서 나온
**이 프로젝트 자체의 요구사항**이므로 적용합니다.

---

## 5. 유지보수성 (Maintainability)

| ID | 요구사항 | 근거 |
|---|---|---|
| NFR-M01 | 공개 함수·클래스에 타입 힌트 | Q11=B |
| NFR-M02 | `ruff` 린트 + 포맷, `mypy` 타입 검사 | Q7=A |
| NFR-M03 | 개발 도구는 `requirements-dev.txt` 에 두고 `export-ignore` | 규약 §1.4 |
| NFR-M04 | `src/` 는 `tools/` 를 import 하지 않음 (단방향) | 규약 §1.4 |
| NFR-M05 | 바뀔 만한 값은 코드에 박지 않음 — CLI 인자 또는 설정 | 규약 §1.3 |
| NFR-M06 | 인덱스명·시간 필드명·컬럼 매핑은 설정으로 | 규약 §1.3, FR-7 |
| NFR-M07 | 스키마는 `schema.py` **단일 출처** | 규약 §1.1 |

---

## 6. 테스트 (Testability)

| ID | 요구사항 | 근거 |
|---|---|---|
| NFR-T01 | `pytest` + `hypothesis` | Q6=A, **PBT-09 충족** |
| NFR-T02 | 커버리지 수치 목표 **없음** | Q6=A |
| NFR-T03 | **테스트 픽스처 파일 금지.** `synth.generate()` 로 런타임 생성 | 규약 §1.2 — 없는 파일은 커밋될 수 없다 |
| NFR-T04 | `generate(n, seed)` 는 결정론적 | 규약 §1.2 |
| NFR-T05 | 외부 API 키 없이 전체 테스트 통과 | 규약 §1.4 |
| NFR-T06 | 속성 기반 테스트는 shrinking 활성, 실패 시 시드 로깅 | PBT-08 |
| NFR-T07 | ES 접속 없이 전체 테스트 통과 | 규약 §1.2의 확장 — 개발 장비에 클러스터가 없다 |

**NFR-T07이 규약 적용의 실질적 이득입니다.** `synth.py` 가 가짜 ES 히트를 만들어주므로
개발 장비에서 클러스터 없이 전 구간을 돌려볼 수 있습니다 (`--dry-run`).

---

## 7. 운영 (Operations)

| ID | 요구사항 | 근거 |
|---|---|---|
| NFR-X01 | 출력 파일 보관 정책 **없음** (범위 밖) | Q9=A |
| NFR-X02 | 종료 코드 `0` 정상 / `1` 돌았지만 온전치 않음 / `2` 시작도 못 함 | 규약 §3.2 = 기존 BR-X01~08 |
| NFR-X03 | 스케줄러는 **한 번만** 호출 (추출+변환 통합) | CQ3=A |
| NFR-X04 | 필수 인자 누락은 **어떤 계산도 하기 전에** 죽는다 | 규약 §1.3 |
| NFR-X05 | 설정의 `paths.venv` 가 있으면 진입점이 그 파이썬으로 갈아탄다 | 규약 §3.1 |

---

## 8. 기존 결정 수정 사항 (Amendments)

규약 우선 지시에 따라 **이미 승인된 결정 중 아래가 뒤집힙니다.**

| 문서 | 기존 결정 | 수정 후 | 근거 |
|---|---|---|---|
| Application Design Q2=B | CLI 서브커맨드 2개 (`extract`, `convert`) | **단일 진입점.** 한 번 실행에 추출+변환, RUN SUMMARY 한 장. `--only extract` / `--only convert` 는 개발용 보조 인자 | 하지 말 것 #12, §3.2 |
| D-3 | `convert` 가 `extract` 와 같은 날짜 인자를 받음 | **소멸** — 한 실행 안에서 같은 창을 공유 | CQ3=A |
| D-4 | 스케줄러가 `extract && convert` 를 이어 실행 | **단일 명령** `python src/run.py --from ... --to ...` | CQ3=A |
| Application Design Q1=A | 평평한 9개 모듈 | 규약의 공유 모듈 + 프로젝트 고유 모듈 | 규약 §1.5, §3.1 |
| NFR Q1=B | Python 3.12 | **Python 3.14** | 제약 C7 |
| NFR Q2=A | `pyproject.toml` + `pip install -e .` | **설치 없음.** `python src/run.py` | 제약 C7, 규약 §3.1 |
| NFR Q3=A | `elasticsearch>=8.15,<9` | **완전 고정** `elasticsearch==8.15.1` | 규약 `requirements.txt` |
| NFR-6 | 시크릿은 `.env` 에만 | **`configs/env.yaml`** | CQ4=A |

**유지되는 결정**
- Application Design Q3=B (변환은 전체 추출 후 일괄) — 단일 실행 **안에서** 그대로 성립
- Application Design Q7=A, Q8=A (체크포인트 JSON + 원자적 쓰기, 키는 ISO 종료 시각)
- Functional Design 전체 (청크 분할, 경계, 파일명, CSV 렌더링 규칙) — 규약과 충돌 없음
- 종료 코드 0/1/2 — 규약과 **정확히 일치**

---

## 9. 규약 적용에 따른 설계 적응 1건

**스키마 검증의 범위**

규약의 `validate(rows)` 는 행 **리스트 전체**를 받습니다. 그런데 NFR-P01(10만~100만 건)과
NFR-P04(스트리밍)에서는 전체를 메모리에 들 수 없습니다.

**적응**: 청크마다 **앞부분 N건(기본 1000)을 표본으로 모아** 스키마를 검증합니다.
전수 검사가 아니므로 표본에 없는 위반은 놓칠 수 있으나,
스키마 회수 채널(C5)의 목적은 "포맷이 내 가정과 다른가"를 알아내는 것이고
그 목적에는 표본으로 충분합니다. RUN SUMMARY 에 표본 크기를 함께 찍어
전수 검사가 아님이 드러나게 합니다.

```
schema    : 6 ok / 1 MISMATCH   (sampled 1,000 of 152,431)
```

---

## 10. 확장 규칙 준수 요약 (Extension Compliance)

| 규칙 | 상태 | 근거 |
|---|---|---|
| **PBT-09 (프레임워크 선정)** | ✅ **준수** | `hypothesis` 선정. `requirements-dev.txt` 에 고정 버전으로 포함. 커스텀 제너레이터·shrinking·시드 재현성 모두 지원하며 pytest 와 통합됨 |
| PBT-01~08, 10 | 해당 없음 (다른 단계) | Functional Design 및 Code Generation 단계에서 강제 |
| Security Baseline | N/A | 옵트아웃 (Q12=B) |
| Resiliency Baseline | N/A | 옵트아웃 (Q13=B) |

**차단성 발견 사항(Blocking findings): 없음.**
