# Application Design Plan

**프로젝트**: Elasticsearch 데이터 추출 도구 (es_api)
**단계**: INCEPTION - Application Design (Part 1: 계획 + 질문)
**작성일**: 2026-09-09

---

## 1. 실행 계획 체크리스트

- [x] 1. 요구사항 컨텍스트 분석 (requirements.md, execution-plan.md 로드)
- [x] 2. 컴포넌트 식별 및 책임 정의
  - [x] 2.1 각 컴포넌트의 단일 책임 확정
  - [x] 2.2 컴포넌트 경계 및 인터페이스 정의
- [x] 3. 컴포넌트 메서드 시그니처 정의 (입출력 타입 포함, 상세 비즈니스 규칙은 Functional Design에서)
- [x] 4. 서비스 계층(오케스트레이션) 설계
- [x] 5. 컴포넌트 의존 관계 및 데이터 흐름 정의
- [x] 6. 설계 산출물 생성
  - [x] 6.1 `components.md` — 컴포넌트 정의와 책임
  - [x] 6.2 `component-methods.md` — 메서드 시그니처
  - [x] 6.3 `services.md` — 서비스 정의와 오케스트레이션
  - [x] 6.4 `component-dependency.md` — 의존 매트릭스, 통신 패턴, 데이터 흐름
  - [x] 6.5 `application-design.md` — 위 문서 통합본
- [x] 7. 설계 완결성·일관성 검증
- [x] 8. 사용자 승인 (승인 완료)

---

## 2. 제안 컴포넌트 구조 (질문의 배경)

아래는 요구사항에서 도출한 **초안**입니다. 질문에 답해주시면 이를 확정합니다.

```
es_crawler/
  __init__.py      공개 API (라이브러리 진입점)
  config.py        Config        - 설정 파일 + .env 로딩, 검증
  chunker.py       DateChunker   - 기간 -> anchor 정렬 24h 청크 목록
  extractor.py     EsExtractor   - elasticsearch-py + scroll 페이징
  writer.py        JsonlWriter   - 청크 -> JSONL 파일
  converter.py     CsvConverter  - JSONL -> CSV (컬럼 선택/리네임)
  checkpoint.py    CheckpointStore - 청크 상태 기록/조회
  pipeline.py      CrawlService  - 위 컴포넌트 오케스트레이션
  cli.py           CLI 진입점
```

**데이터 흐름**
```
Config --> CrawlService
              |
              +--> DateChunker      기간 -> [chunk1, chunk2, ...]
              |
              +--> CheckpointStore  완료된 청크 제외
              |
              +--> EsExtractor      청크 -> 문서 스트림 (scroll)
              |         |
              |         v
              +--> JsonlWriter      문서 스트림 -> data-YYYY-MM-DD.jsonl
              |
              +--> CsvConverter     jsonl -> data-YYYY-MM-DD.csv
              |
              +--> CheckpointStore  청크 완료/실패 기록
```

---

## 3. 설계 확인 질문

**답변 방법**: 각 질문의 `[Answer]:` 태그 뒤에 알파벳을 적어주세요.
보기에 맞는 것이 없으면 `X) Other`를 고르고 직접 설명해 주세요.
전부 작성 후 "완료"라고 알려주세요.

---

## Question 1 — 컴포넌트 구성
위 2절의 컴포넌트 분리(9개 모듈)를 어떻게 보시나요?

A) 그대로 진행 — 각 모듈이 단일 책임을 갖고, 테스트하기 좋음

B) 더 단순하게 통합 — `writer.py`를 `extractor.py`에 흡수하고, `checkpoint.py`를 `pipeline.py`에 흡수해 6개 모듈로 축소 (YAGNI 관점)

C) 더 세분화 — 각 컴포넌트를 서브패키지로 분리 (`es_crawler/extract/`, `es_crawler/transform/` 등)

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 2 — 추출과 변환의 실행 결합
FR-5에서 "CSV 변환은 추출과 분리된 별도 단계로 실행 가능해야 한다"고 정했습니다.
CLI에서 이를 어떻게 노출할까요?

A) **서브커맨드 3개** — `extract` (ES→JSONL), `convert` (JSONL→CSV), `run` (둘 다 순차 실행).
   스케줄러는 `run`을 호출, 변환 로직만 고칠 때는 `convert`만 재실행

B) **서브커맨드 2개** — `extract`, `convert`. 둘 다 하려면 스케줄러가 두 번 호출

C) **기본은 통합 실행**, `--skip-convert` / `--convert-only` 플래그로 분리

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: B

---

## Question 3 — CSV 변환 시점
여러 날짜를 추출할 때, CSV 변환을 언제 수행할까요?

A) **청크마다 즉시** — 하루치 JSONL을 다 쓰면 곧바로 그 날의 CSV를 생성.
   중간에 중단돼도 이미 처리한 날짜는 CSV까지 완성되어 있음

B) **전체 추출 후 일괄** — 모든 JSONL을 만든 뒤 한 번에 변환.
   변환 단계가 명확히 분리되지만, 중단 시 CSV가 하나도 없을 수 있음

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: B

---

## Question 4 — 설정 파일 형식
인덱스명, 시간 필드, 컬럼 매핑 등을 담을 설정 파일 형식은?

A) **YAML** — 중첩 구조와 컬럼 매핑을 사람이 읽고 쓰기 편함 (의존성 `PyYAML` 추가)

B) **TOML** — Python 표준 라이브러리 `tomllib`로 읽기 가능 (3.11+), 의존성 없음

C) **JSON** — 표준 라이브러리, 의존성 없음. 다만 주석을 달 수 없음

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 5 — 라이브러리 공개 API 형태
`import` 해서 쓸 때 어떤 형태를 노출할까요?

A) **고수준 함수 하나** — `crawl(config, start, end)` 만 공개. 내부 컴포넌트는 비공개
   (단순하지만 부분 사용이 어려움)

B) **컴포넌트도 함께 공개** — `DateChunker`, `EsExtractor`, `CsvConverter` 등을 개별로도
   import 가능. 예: "이미 있는 JSONL만 CSV로 바꾸고 싶다"를 코드에서 직접 수행

C) **서비스 클래스 하나** — `CrawlService(config)` 를 공개하고 `.extract()`, `.convert()`,
   `.run()` 메서드 제공

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: C

---

## Question 6 — Elasticsearch 클라이언트 추상화 수준
테스트에서 실제 ES 없이 검증하려면 추상화가 필요합니다. 어느 수준으로 할까요?

A) **`elasticsearch-py`를 직접 사용** — `EsExtractor`가 `Elasticsearch` 객체를 생성자로 받고,
   테스트에서는 이 객체를 모킹. 추가 레이어 없음 (YAGNI, 권장)

B) **얇은 인터페이스(Protocol) 도입** — `SearchClient` 프로토콜을 정의하고 `EsExtractor`가
   그것에 의존. 테스트용 가짜 구현을 쉽게 만들 수 있으나 레이어가 하나 늘어남

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 7 — 체크포인트 저장 형식과 위치
청크 진행 상태를 어디에 어떤 형식으로 저장할까요?

A) **출력 디렉터리 안의 JSON 파일 하나** (예: `output/.checkpoint.json`) — 단순, 사람이 읽을 수 있음.
   원자적 쓰기(임시 파일 + rename)로 손상 방지

B) **출력 파일의 존재 여부로 판단** — 별도 상태 파일 없이 `data-YYYY-MM-DD.jsonl`이 있으면 완료로 간주.
   가장 단순하지만, **쓰다가 중단된 불완전한 파일을 완료로 오인**할 위험이 있음
   (완료 표시 파일 `.done`을 함께 쓰면 완화 가능)

C) **SQLite** — 상태 조회·갱신이 견고하지만 이 규모에는 과함

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Question 8 — 실행 범위 기록의 단위
체크포인트가 청크를 식별하는 키를 무엇으로 할까요?
(D-1에 따라 하루의 경계가 18:00이므로 "날짜"만으로는 애매할 수 있습니다)

A) **창의 종료 시각(ISO 8601, 타임존 포함)** — 예: `2026-09-09T18:00:00+09:00`.
   청크 크기를 6시간 등으로 바꿔도 그대로 동작

B) **창의 종료 날짜** — 예: `2026-09-09`. 단순하지만 하루보다 작은 청크를 쓰면 키가 충돌

C) **시작·종료 시각 쌍** — 가장 명시적이지만 키가 길어짐

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---
