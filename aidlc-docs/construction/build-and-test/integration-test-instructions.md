# 통합 테스트 지침

**단위(Unit)**: `es-crawler`
**작성일**: 2026-09-09

---

## 1. 무엇을 통합 테스트로 볼 것인가

작업 단위가 하나뿐이라 **단위 간 통합은 없습니다.** 대신 이 프로젝트에서 단위
테스트로 덮이지 않는 것은 **실제 Elasticsearch 와의 상호작용** 하나입니다.

단위 테스트는 `FakeSearchClient` 로 scroll 을 흉내냅니다. 그것이 확인하는 것은
"우리 코드가 프로토콜을 올바르게 따르는가"까지이고, 아래는 확인하지 못합니다.

| 확인되지 않는 것 | 왜 |
|---|---|
| 실제 서버가 scroll 을 우리 기대대로 다루는가 | 가짜 클라이언트는 우리가 만든 것이다 |
| `clear_scroll` 이 실제로 컨텍스트를 지우는가 | 서버 통계를 봐야 한다 |
| API Key 인증이 통하는가 | 인증 경로가 가짜에는 없다 |
| 실제 인덱스 매핑에서 range 쿼리가 도는가 | 시간 필드 타입이 다를 수 있다 |
| 만 건을 넘는 결과가 실제로 전부 나오는가 | `max_result_window` 는 서버 설정이다 |

---

## 2. 테스트 환경 준비

### 2.1 로컬 Elasticsearch 8.15.3 띄우기

```bash
cat > /tmp/es-test.yml <<'YAML'
services:
  es:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.3
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=true
      - ELASTIC_PASSWORD=testonly
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
    ports:
      - "9200:9200"
YAML

docker compose -f /tmp/es-test.yml up -d
```

**서버 버전이 8.15.3 이어야 합니다.** 클라이언트는 8.19.3 이며 같은 메이저 안에서
호환됩니다. 이 조합이 실제로 도는지 확인하는 것이 이 테스트의 목적 중 하나입니다.

### 2.2 준비 확인

```bash
until curl -s -u elastic:testonly http://localhost:9200 >/dev/null; do sleep 2; done
curl -s -u elastic:testonly http://localhost:9200 | grep number
```

**기대**: `"number" : "8.15.3"`

### 2.3 API Key 발급

```bash
curl -s -u elastic:testonly -X POST http://localhost:9200/_security/api_key \
  -H 'Content-Type: application/json' \
  -d '{"name":"es-crawler-test"}'
```

응답의 `encoded` 값을 설정 파일에 넣습니다.

### 2.4 테스트 데이터 색인

**`max_result_window` 기본값(10,000)을 넘겨야** scroll 경로가 실제로 돕니다.

```bash
.venv/bin/python - <<'PY'
import json, urllib.request, base64
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
base = datetime(2026, 9, 8, 18, 0, tzinfo=KST)
auth = base64.b64encode(b"elastic:testonly").decode()

lines = []
for i in range(25_000):
    when = base + timedelta(seconds=i * 3)
    lines.append(json.dumps({"index": {"_index": "crawler-test"}}))
    lines.append(json.dumps({
        "@timestamp": when.isoformat(),
        "user": {"name": f"user{i % 100}"},
        "level": "ERROR" if i % 7 == 0 else "INFO",
    }))
body = ("\n".join(lines) + "\n").encode()

req = urllib.request.Request(
    "http://localhost:9200/_bulk", data=body, method="POST",
    headers={"Content-Type": "application/x-ndjson", "Authorization": f"Basic {auth}"},
)
resp = json.load(urllib.request.urlopen(req))
print("errors:", resp["errors"], "items:", len(resp["items"]))
PY

curl -s -u elastic:testonly -X POST http://localhost:9200/crawler-test/_refresh
```

**기대**: `errors: False`, 25,000건. 문서는 `2026-09-08T18:00 ~ 2026-09-09T00:50 KST` 에 걸쳐 있습니다.

### 2.5 설정 파일

```bash
mkdir -p /tmp/crawler-it
cat > /tmp/crawler-it/env.yaml <<YAML
paths:
  venv:
elasticsearch:
  hosts: ["http://localhost:9200"]
  api_key: "<2.3 의 encoded 값>"
  request_timeout: 60
  max_retries: 3
query:
  index: "crawler-test"
  time_field: "@timestamp"
  batch_size: 2000
  scroll_ttl: "5m"
  extra_filters: []
chunk:
  timezone: "Asia/Seoul"
  anchor_time: "18:00"
  chunk_hours: 24
output:
  directory: "/tmp/crawler-it/outputs"
  schema_sample: 1000
  columns:
    - {source: "_id", header: "doc_id"}
    - {source: "@timestamp", header: "timestamp"}
    - {source: "user.name", header: "user_name"}
YAML
```

---

## 3. 시나리오

### 시나리오 1 — 만 건을 넘는 결과가 전부 나오는가

이 프로젝트가 scroll 을 쓰는 이유 자체입니다.

```bash
.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00
```

**기대**
```
extract   : 25,000 docs -> 1 jsonl
convert   : 25,000 rows -> 1 csv
status    : OK
```
25,000 < 10,000 이면 scroll 이 첫 페이지에서 멈춘 것입니다.

```bash
wc -l /tmp/crawler-it/outputs/*.jsonl     # 25000
wc -l /tmp/crawler-it/outputs/*.csv       # 25001 (헤더 포함)
```

### 시나리오 2 — 검색 컨텍스트가 실제로 정리되는가

**이 프로젝트에서 가장 조용히 깨질 수 있는 부분입니다.** 정리를 놓쳐도 프로그램은
정상 종료하고 로그도 깨끗합니다.

```bash
# 실행 전
curl -s -u elastic:testonly "http://localhost:9200/_nodes/stats/indices/search" \
  | grep -o '"open_contexts":[0-9]*'

.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00 --only extract

# 실행 직후
curl -s -u elastic:testonly "http://localhost:9200/_nodes/stats/indices/search" \
  | grep -o '"open_contexts":[0-9]*'
```

**기대**: 실행 전후의 `open_contexts` 가 **같아야** 합니다.
늘어나 있으면 `scroll_ttl`(5분)이 지날 때까지 서버 메모리를 붙잡고 있는 것입니다.

### 시나리오 3 — 여러 구간을 돌 때 누락도 중복도 없는가

```bash
rm -rf /tmp/crawler-it/outputs

# 6시간 단위로 쪼갠다
sed -i.bak 's/chunk_hours: 24/chunk_hours: 6/' /tmp/crawler-it/env.yaml

.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00

cat /tmp/crawler-it/outputs/*.jsonl | .venv/bin/python -c "
import sys, json
ids = [json.loads(l)['_id'] for l in sys.stdin if l.strip()]
print('총', len(ids), '고유', len(set(ids)))
"
```

**기대**: `총 25000 고유 25000` — 합계가 맞고 중복이 없습니다.
구간 경계가 `gte`/`lt` 가 아니라 `lte` 였다면 여기서 중복이 나옵니다.
파일도 4개가 아니라 **구간마다 하나씩** 생겨야 합니다.

```bash
ls /tmp/crawler-it/outputs/*.jsonl | wc -l    # 4
```

### 시나리오 4 — 재개가 실제로 작동하는가

```bash
rm -rf /tmp/crawler-it/outputs
sed -i.bak 's/chunk_hours: 6/chunk_hours: 24/' /tmp/crawler-it/env.yaml

# 1회차
.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00

# 2회차 — 같은 범위
.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00
```

**기대 (2회차)**
```
chunks    :
  done             0
  failed           0
  skipped          1
extract   : 0 docs -> 0 jsonl
```
클러스터에 다시 조회하지 않아야 합니다.

### 시나리오 5 — 인증 실패가 조회 전에 잡히는가

```bash
sed -i.bak 's/api_key: .*/api_key: "wrong-key"/' /tmp/crawler-it/env.yaml
.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00
echo "exit=$?"
```

**기대**: 종료 코드 `1`. 첫 구간이 `failed` 로 기록되고 오류 메시지가 stderr 에 나옵니다.
API Key 값 자체는 **어디에도 찍히지 않아야** 합니다.

```bash
.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00 2>&1 | grep -c "wrong-key"
```
**기대**: `0`

### 시나리오 6 — 실제 매핑에서 형태 대조가 도는가

```bash
sed -i.bak 's/api_key: .*/api_key: "<올바른 값>"/' /tmp/crawler-it/env.yaml
rm -rf /tmp/crawler-it/outputs

.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00 2>/dev/null | grep -A5 "^schema"
```

**기대**: `schema` 줄이 표본 크기와 함께 나옵니다.
`INPUT_SCHEMA` 가 자리표시 상태이므로 실제 인덱스와 어긋나는 것이 정상이며,
**그 어긋남이 사람이 옮겨 적을 수 있는 형태로 나오는지**가 확인 대상입니다.

### 시나리오 7 — 추가 필터가 서버에서 먹히는가

```yaml
query:
  extra_filters:
    - {term: {"level": "ERROR"}}
```

```bash
rm -rf /tmp/crawler-it/outputs
.venv/bin/python src/run.py --config /tmp/crawler-it/env.yaml \
    --from 2026-09-08T18:00 --to 2026-09-09T18:00 2>/dev/null | grep "^extract"
```

**기대**: `extract : 3,572 docs -> 1 jsonl` (25,000 중 7의 배수 인덱스)

---

## 4. 정리

```bash
docker compose -f /tmp/es-test.yml down -v
rm -rf /tmp/crawler-it /tmp/es-test.yml
```

---

## 5. 실행 시점

| 언제 | 무엇 |
|---|---|
| 태그를 내기 전 | 시나리오 1, 2, 3, 4 (핵심 경로) |
| `load.py` 를 고쳤을 때 | 시나리오 1, 2, 7 |
| `chunker.py` 를 고쳤을 때 | 시나리오 3 |
| `checkpoint.py` 를 고쳤을 때 | 시나리오 4 |
| 클러스터 버전이 바뀌었을 때 | 전부 |

**자동화하지 않았습니다.** Docker 로 8.15.3 을 띄울 수 있는 환경이 항상 있다고 볼 수
없고, 단위 테스트가 클러스터 없이 통과해야 한다는 조건과 섞이면 그 보장이 흐려집니다.
