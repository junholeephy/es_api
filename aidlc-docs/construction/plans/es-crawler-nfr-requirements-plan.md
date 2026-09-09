# NFR Requirements Plan — `es-crawler`

**단계**: CONSTRUCTION - NFR Requirements (Part 1: 계획 + 질문)
**단위(Unit)**: `es-crawler`
**작성일**: 2026-09-09

---

## 1. 실행 계획 체크리스트

- [x] 1. Functional Design 산출물 분석 (domain-entities, business-logic-model, business-rules)
- [x] 2. NFR 영역별 요구사항 도출
  - [x] 2.1 성능·처리량 (배치 크기, scroll TTL, 예상 소요 시간)
  - [x] 2.2 신뢰성 (재시도, 타임아웃, 실패 격리)
  - [x] 2.3 관측성 (로깅, 실행 결과 보고)
  - [x] 2.4 보안 (시크릿 관리, 로그 마스킹)
  - [x] 2.5 유지보수성 (타입 힌트, 테스트, 코드 품질 도구)
  - [x] 2.6 운영 (디스크 사용, 보관 정책)
- [x] 3. 기술 스택 결정
  - [x] 3.1 Python 버전 및 언어 기능 범위
  - [x] 3.2 런타임 의존성 확정 및 버전 핀 정책
  - [x] 3.3 개발·테스트 의존성 확정
  - [x] 3.4 **PBT 프레임워크 선정 (PBT-09 — 차단성 규칙)**
  - [x] 3.5 패키징·의존성 관리 방식
- [x] 4. 산출물 생성
  - [x] 4.1 `nfr-requirements.md`
  - [x] 4.2 `tech-stack-decisions.md`
- [x] 5. PBT-09 준수 검증
- [x] 6. 사용자 승인 (승인 완료)

---

## 2. 확인 질문

**답변 방법**: 각 질문의 `[Answer]:` 태그 뒤에 알파벳을 적어주세요.
보기에 맞는 것이 없으면 `X) Other`를 고르고 직접 설명해 주세요.
전부 작성 후 "완료"라고 알려주세요.

---

## Question 1 — Python 최소 버전
사용할 Python 최소 버전은 무엇인가요? (문법과 표준 라이브러리 사용 범위가 달라집니다)

A) **3.11 이상** — `datetime.UTC`, `tomllib`, 향상된 예외 그룹 사용 가능. 현재 널리 쓰이는 안정 버전

B) **3.12 이상** — 최신 문법과 성능 개선. 일부 환경에서는 아직 설치가 번거로울 수 있음

C) **3.10 이상** — `X | None` 문법과 `match` 사용 가능. 호환 범위가 가장 넓음

D) **3.9 이상** — `ZoneInfo`가 표준에 들어온 최소 버전. `X | None` 대신 `Optional[X]` 사용 필요

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: B

---

## Question 2 — 의존성 관리 및 패키징 방식
`python -m es_crawler` 로 실행하려면 패키지가 import 경로에 있어야 합니다. 어떻게 관리할까요?

A) **`pyproject.toml` + `pip install -e .`** — 표준 방식. 개발 중 편집이 바로 반영되고,
   의존성·엔트리포인트·도구 설정(ruff, mypy, pytest)을 한 파일에 모을 수 있음

B) **`requirements.txt` + venv, 패키징 없음** — 프로젝트 루트에서 직접 실행.
   가장 단순하지만 도구 설정 파일이 흩어지고 `pip install -e .` 를 쓸 수 없음

C) **`pyproject.toml` + `requirements.txt` 병행** — 의존성 핀은 `requirements.txt`,
   메타데이터·도구 설정은 `pyproject.toml`

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A. 해당 폴더안에 venv를 자체 마련하고 싶어.

---

## Question 3 — `elasticsearch` 클라이언트 버전 핀 정책
서버는 8.15.3 고정입니다 (제약 C-1). 클라이언트 버전을 어떻게 고정할까요?

A) **`elasticsearch>=8.15,<9`** — 8.x 안에서 패치·마이너 업데이트 허용.
   서버 메이저와 맞고, 버그 수정을 자동으로 받음

B) **`elasticsearch==8.15.1`** 처럼 완전 고정 — 재현성이 가장 높음.
   업데이트는 수동으로만

C) **`elasticsearch~=8.15.0`** — 8.15.x 패치만 허용

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 4 — 하루치 데이터 규모 ⚠️ 성능 설계에 직접 영향
하루(24시간) 분량이 대략 몇 건, 어느 정도 크기인가요?
정확하지 않아도 자릿수만 맞으면 됩니다. `batch_size` 기본값과 예상 소요 시간 산정에 씁니다.

A) **1만 건 미만** — scroll이 거의 필요 없는 수준

B) **1만 ~ 10만 건** — scroll 수십 회

C) **10만 ~ 100만 건** — scroll 수백 회. 배치 크기 조정이 의미 있어짐

D) **100만 건 이상** — 실행 시간과 디스크 사용이 본격적인 고려 대상

E) **아직 모름** — 실제로 돌려보고 조정하고 싶음

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: 잘 모르지만 C 정도 될 거라 예상

---

## Question 5 — 재시도 및 타임아웃 정책
일시적 ES 오류(429, 502, 503, 타임아웃)에 대한 클라이언트 설정입니다.

A) **재시도 3회 + 요청 타임아웃 60초** — 일반적인 기본값

B) **재시도 5회 + 요청 타임아웃 120초** — 클러스터가 바쁘거나 청크가 클 때 여유 있게

C) **재시도 없음 + 타임아웃 30초** — 실패를 빨리 드러내고 다음 날 재시도에 맡김
   (Q7=A 자동 재시도가 있으므로 가능한 선택)

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 6 — 테스트 도구 및 기준
PBT 확장이 Partial 모드로 활성화되어 있어 **속성 기반 테스트 프레임워크 선정이 필수**입니다 (PBT-09).

A) **pytest + hypothesis, 커버리지 기준 없음** — 테스트는 작성하되 수치 목표는 두지 않음

B) **pytest + hypothesis + pytest-cov, 커버리지 80% 목표** — 수치 기준을 둠

C) **pytest + hypothesis + pytest-cov, 순수 로직 모듈만 90% 목표**
   (`chunker`, `converter`, `checkpoint` — I/O가 없는 모듈에 집중)

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 7 — 코드 품질 도구
린터·포매터·타입 체커를 어디까지 도입할까요?

A) **ruff (린트 + 포맷) + mypy** — 현재 가장 일반적인 조합. ruff가 빠르고 설정이 단순

B) **ruff만** — 린트와 포맷만. 타입 힌트는 작성하되 체커로 강제하지는 않음

C) **도구 없음** — 테스트만으로 충분

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 8 — 로깅 출력 방식
스케줄러가 매일 19:00에 무인 실행합니다. 로그를 어디에 남길까요?

A) **표준 출력(stdout)만** — 스케줄러(cron 등)가 리다이렉션으로 파일에 남기도록 위임.
   가장 단순하고 컨테이너 환경과도 잘 맞음

B) **stdout + 회전 로그 파일** — 애플리케이션이 직접 `logs/` 에 날짜별 파일을 남김.
   스케줄러 설정과 무관하게 항상 기록됨

C) **JSON 구조화 로그(stdout)** — 로그 수집 시스템에 넣을 계획이 있다면

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 9 — 출력 파일 보관 정책
매일 JSONL + CSV가 쌓입니다. 오래된 파일을 어떻게 할까요?

A) **관리하지 않음 (범위 밖)** — 필요하면 별도 스크립트나 OS 도구로 정리

B) **보관 기간 설정 추가** — 설정에 `retention_days`를 두고, 실행 시 그보다 오래된
   출력 파일을 자동 삭제

C) **JSONL만 정리, CSV는 보존** — 원본은 용량이 크므로 N일 후 삭제, 변환 결과는 유지

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---
