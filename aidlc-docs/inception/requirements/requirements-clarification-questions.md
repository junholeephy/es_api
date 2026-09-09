# 요구사항 명확화 질문 (Clarification)

**단계**: INCEPTION - Requirements Analysis
**사유**: 미답변 1건 + 모순/모호 3건 감지

---

## 📖 Q3 설명 요청에 대한 답변: `elasticsearch-py` vs 직접 HTTP 호출

두 방식 모두 **결국 같은 Elasticsearch REST API를 호출**합니다. 차이는 그 위에 무엇이 얹혀 있느냐입니다.

### A) 공식 `elasticsearch-py` 8.x 클라이언트

```python
from elasticsearch import Elasticsearch

es = Elasticsearch("https://host:9200", api_key=API_KEY)
resp = es.search(index="logs-*", query={...}, size=1000, scroll="5m")
sid = resp["_scroll_id"]
while resp["hits"]["hits"]:
    resp = es.scroll(scroll_id=sid, scroll="5m")
```

**얻는 것**

| 항목 | 내용 |
|---|---|
| 버전 호환성 검사 | 클라이언트 8.15와 서버 8.15.3의 호환을 시작 시 검증하고, 불일치하면 명확한 에러 |
| 스크롤 컨텍스트 정리 | `clear_scroll()` 제공. 안 지우면 서버 메모리에 검색 컨텍스트가 남아 쌓임 |
| 재시도·백오프 | 429(Too Many Requests), 502/503, 커넥션 끊김에 대한 재시도가 내장 (`max_retries`, `retry_on_timeout`) |
| 인증·TLS | `api_key=`, `basic_auth=`, `ca_certs=` 인자로 처리. 헤더를 직접 만들 필요 없음 |
| 커넥션 풀 | 노드 여러 개일 때 라운드로빈, 죽은 노드 감지 |
| 헬퍼 | `helpers.scan()` — scroll을 감싼 제너레이터. 스크롤 반복과 정리를 알아서 해줌 |
| 에러 타입 | `NotFoundError`, `AuthenticationException` 등 예외로 구분되어 처리 코드가 명확 |

**치르는 비용**: 의존성 1개 추가(`elasticsearch>=8.15,<9`), 서버 메이저 버전과 클라이언트 메이저 버전을 맞춰야 함.

### B) `requests` / `httpx` 로 직접 호출

```python
import requests
r = requests.post(f"{HOST}/logs-*/_search?scroll=5m",
                  json={"size": 1000, "query": {...}},
                  headers={"Authorization": f"ApiKey {API_KEY}"})
sid = r.json()["_scroll_id"]
# 이후 POST /_search/scroll 을 직접 반복, 끝나면 DELETE /_search/scroll 로 정리
```

**얻는 것**: 의존성 최소, HTTP 레이어를 완전히 통제, ES 버전 업그레이드와 무관.

**치르는 비용**: 위 표의 항목을 **전부 직접 구현**해야 합니다 — scroll 반복 루프, `clear_scroll` 호출 누락 방지, 429 재시도와 지수 백오프, 인증 헤더 조립, TLS 인증서 처리, HTTP 상태코드별 에러 분기. 이 프로젝트는 **scroll을 쓰고**(Q4=A), **하루 단위로 수십~수백 번 반복 실행**하며, **재개 기능이 필요**하므로(Q7=A) 재시도와 스크롤 컨텍스트 정리가 특히 중요합니다. 직접 구현하면 그 부분이 전부 우리 코드의 버그 표면이 됩니다.

### 이 프로젝트에 대한 권장: **A**

이유는 셋입니다.
1. **scroll 컨텍스트 누수 위험** — 하루 단위로 반복 실행하는 구조라, `clear_scroll` 한 번 빠뜨리면 클러스터에 검색 컨텍스트가 계속 쌓입니다. Q5에서 "부하를 줄이려고 하루씩 쪼갠다"고 하셨는데, 정리를 놓치면 오히려 부하를 만듭니다. `helpers.scan()`은 이걸 컨텍스트 매니저로 보장합니다.
2. **재시도가 재개 기능과 맞물림** — Q7에서 재개를 요청하셨습니다. 일시적 429/503까지 "실패한 날짜"로 기록해 재개 대상으로 만들면 비효율적입니다. 클라이언트 레벨 재시도가 일시적 오류를 먼저 흡수하고, 진짜 실패만 체크포인트에 남는 구조가 낫습니다.
3. **Q11=B(테스트 포함, 반복 사용 수준)** — 직접 구현한 HTTP 레이어는 그만큼 테스트해야 할 코드가 늘어납니다.

**단, B를 고르실 만한 이유도 있습니다**: 사내 정책상 외부 의존성을 최소화해야 하거나, 프록시·인증 방식이 특이해서 HTTP를 직접 통제해야 하는 경우입니다.

---

## Clarification Question 1
위 설명을 바탕으로, Elasticsearch 클라이언트를 무엇으로 할까요?

A) 공식 `elasticsearch-py` 8.x 클라이언트 (권장)

B) `requests` / `httpx` 로 REST 엔드포인트 직접 호출

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## 모순 1: 여러 날짜 요청을 자동 분할하는가, 거부하는가

Round 1에서는 이렇게 말씀하셨습니다:
> "5일치 데이터를 가져오고 싶다면 **최소 5번으로 나눠서** 가져와야 한다는 거지"

그런데 Q2 답변은 이렇습니다:
> "만약 **1일 초과한다면 경고 보이고 실행하지 않음**"

전자는 "5일치 요청을 5개 청크로 **쪼개서 실행**한다"로 읽히고, 후자는 "5일치 요청은 **거부**한다"로 읽힙니다. 이 둘은 다른 동작입니다.

## Clarification Question 2
`--from 2026-09-01 --to 2026-09-05` 처럼 5일 범위를 요청하면 어떻게 동작해야 하나요?

A) **자동 분할 실행** — 도구가 5개의 하루짜리 청크로 나눠 순차 실행. "1일 초과 시 거부"는 *개별 청크 하나*의 크기 제한을 뜻함 (즉, 한 번의 ES 쿼리가 24시간을 넘지 않도록 보장)

B) **거부** — 전체 요청 기간이 1일을 넘으면 경고 후 종료. 사용자가 직접 5번 나눠 호출해야 함

C) **기본은 거부, 옵션으로 자동 분할** — `--auto-split` 같은 플래그를 켰을 때만 분할 실행

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## 모호 2: 실행 인터페이스 (CLI가 있는가)

Q10에서 **B) 재사용 가능한 Python 패키지/모듈 (import해서 사용)** 을 선택하셨습니다.
그런데 Q8에서는 **A) 설정 파일 / CLI 인자로 받기**, Q2에서는 "명시적으로 시간을 **입력**하면"이라고 하셨습니다.
CLI 인자와 "입력"은 명령줄 진입점이 있다는 뜻으로 읽힙니다.

## Clarification Question 3
실행 인터페이스를 어떻게 할까요?

A) **라이브러리만** — `import` 해서 함수/클래스를 호출. 파라미터는 함수 인자와 설정 파일로 전달 (CLI 없음)

B) **라이브러리 + 얇은 CLI** — 핵심 로직은 패키지로 만들고, `python -m es_crawler --from ... --to ...` 형태의 얇은 진입점을 얹음

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: B. 나중에 스케줄링 툴을 써서 오후 8시에 매일 매일 하루치의 데이터를 fetching 하려고 해.

---

## 모호 3: JSONL의 역할과 "processing"의 내용

Q1 답변: "jsonl 형식의 파일을 processing 하여 csv로 저장"

두 가지가 불명확합니다.

**(1) JSONL 파일이 디스크에 남는가?**
ES에서 받은 원본을 `.jsonl`로 저장해 두고 그것을 읽어 CSV로 변환하는지, 아니면 JSONL은 중간 표현일 뿐이고 최종 산출물은 CSV뿐인지.

**(2) "processing"이 구체적으로 무엇인가?**
ES 문서는 중첩 구조(`_source` 안에 객체/배열)인데 CSV는 평평한 표입니다. 이 변환에서 무엇을 하는지에 따라 설계가 달라집니다.

## Clarification Question 4
JSONL 파일을 디스크에 남길까요?

A) **남긴다** — ES 원본을 `.jsonl`로 저장하고, 별도 단계에서 읽어 CSV로 변환. 재추출 없이 변환 로직만 다시 돌릴 수 있음 (재개 기능과도 잘 맞음)

B) **남기지 않는다** — 스트리밍으로 받아 바로 CSV로 씀. 최종 산출물은 CSV뿐

C) **옵션으로 선택** — 기본은 JSONL 보존, 플래그로 끄기

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: A

---

## Clarification Question 5
JSONL → CSV 변환("processing")에서 필요한 작업은 무엇인가요? (해당하는 것을 모두 적어주세요, 예: "A, C")

A) `_source` 안의 필드만 추출 (`_index`, `_id`, `_score` 등 메타데이터 제외)

B) 중첩 객체를 점 표기법으로 평탄화 (`user.name` → `user.name` 컬럼)

C) 미리 정한 컬럼 목록만 뽑기 (설정 파일에 컬럼 지정)

D) 배열 필드는 구분자로 합치기 (`["a","b"]` → `"a|b"`)

E) 타입 변환 / 포맷팅 (예: 타임스탬프를 특정 포맷의 문자열로)

X) Other (아래 [Answer]: 뒤에 직접 설명해 주세요)

[Answer]: C. 다면 컬럼명은 csv에 저장할때 이름을 바꿔서 저장할 수도 잇음 

---
