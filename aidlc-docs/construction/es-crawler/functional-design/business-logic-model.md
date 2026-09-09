# 비즈니스 로직 모델 (Business Logic Model) — `es-crawler`

**단계**: CONSTRUCTION - Functional Design
**단위(Unit)**: `es-crawler`

---

## L-1. 청크 분할 (`DateChunker.chunks`)

Q2=C에 따라 **anchor 정렬을 하지 않고**, 주어진 시작 시각부터 `chunk_hours` 간격으로 자릅니다.

```
chunks(start, end):
    검증: start, end 모두 tz-aware        -> 아니면 ValidationError
    검증: start < end                     -> 아니면 ValidationError
    size = timedelta(hours=chunk_hours)

    windows = []
    cursor  = start
    while cursor < end:
        next_edge = min(cursor + size, end)
        windows.append(TimeWindow(cursor, next_edge))
        cursor = next_edge
    return windows
```

### 설계 근거

| 선택 | 이유 |
|---|---|
| 반개구간 `[start, end)` | 인접 청크의 경계 문서가 **누락되지도 중복되지도** 않음 |
| `min(cursor + size, end)` | 요청 범위를 절대 넘지 않음. 마지막 청크는 `chunk_hours`보다 짧을 수 있음 |
| 커서를 `next_edge`로 이동 | 부동소수 누적 오차 없이 정확히 이어붙음 |

### 예시

```
chunk_hours = 24
start = 2026-09-01T18:00+09:00
end   = 2026-09-04T18:00+09:00

-> [2026-09-01T18:00, 2026-09-02T18:00)
   [2026-09-02T18:00, 2026-09-03T18:00)
   [2026-09-03T18:00, 2026-09-04T18:00)
```

```
chunk_hours = 24
start = 2026-09-01T18:00+09:00
end   = 2026-09-03T06:00+09:00        (2일 12시간)

-> [2026-09-01T18:00, 2026-09-02T18:00)   24h
   [2026-09-02T18:00, 2026-09-03T06:00)   12h  <- 마지막 청크는 짧음
```

---

## L-2. 기본 창 계산 (`DateChunker.default_window`)

인자 없이 실행할 때만 쓰입니다 (D-1). anchor가 관여하는 **유일한** 지점입니다.

```
default_window(now):
    tz         = ZoneInfo(config.timezone)
    now_local  = now.astimezone(tz)
    today_edge = datetime.combine(now_local.date(), anchor_time, tzinfo=tz)

    if now_local >= today_edge:
        end = today_edge                 # 오늘 anchor가 이미 지남
    else:
        end = today_edge - 1 day         # 아직 안 지남 -> 직전 완결 창

    start = end - 24 hours
    return (start, end)
```

### 동작 확인

| 실행 시각 (KST) | `end` | `start` | 설명 |
|---|---|---|---|
| 2026-09-09 **19:00** | 09-09 18:00 | 09-08 18:00 | **정상 스케줄 실행** (D-1) |
| 2026-09-09 17:00 | 09-08 18:00 | 09-07 18:00 | anchor 전이므로 직전 완결 창 |
| 2026-09-09 18:00 | 09-09 18:00 | 09-08 18:00 | 경계 포함 (`>=`) |

`chunk_hours < 24` 인 경우, 이 24시간 창이 그대로 `chunks()`에 전달되어 여러 청크로 나뉩니다.
즉 기본 창은 항상 "하루"이고, 분할 단위는 별개입니다.

---

## L-3. Elasticsearch 쿼리 생성 (`EsExtractor.build_query`)

```
build_query(window):
    return {
      "query": {
        "bool": {
          "filter": [
            {"range": {time_field: {
                "gte": window.start.isoformat(),
                "lt":  window.end.isoformat()
            }}},
            *extra_filters
          ]
        }
      },
      "size": batch_size,
      "sort": ["_doc"]
    }
```

### 설계 근거

| 선택 | 이유 |
|---|---|
| `gte` / `lt` | 도메인의 반개구간과 정확히 일치. `lte`를 쓰면 경계 문서가 두 청크에 중복됨 |
| `sort: ["_doc"]` | scroll에서 가장 효율적인 정렬. 점수 계산과 정렬 비용을 없앰 |
| `bool.filter` | 스코어링을 하지 않아 캐시 활용도가 높음 |

### 타임존 처리에 대한 구현 노트 (요구사항 D-2의 단순화)

요구사항에는 "쿼리 시 **UTC로 변환**"이라고 적혀 있습니다.
구현에서는 **오프셋을 포함한 ISO 8601 문자열을 그대로 전송**합니다.

```
"gte": "2026-09-01T18:00:00+09:00"      (전송값)
        == 2026-09-01T09:00:00Z          (Elasticsearch가 내부적으로 해석하는 값)
```

Elasticsearch는 오프셋이 붙은 값을 UTC로 정규화하므로 **의미는 동일**하며,
직접 UTC로 변환하는 코드를 두지 않아 변환 실수의 여지를 없앱니다.
결과적으로 D-2의 의도(하루 경계는 KST, 질의는 절대시각 기준)를 그대로 만족합니다.

---

## L-4. scroll 페이징 (`EsExtractor.iter_documents`)

```
iter_documents(window):
    response   = client.search(index=index, body=build_query(window), scroll=scroll_ttl)
    scroll_id  = response["_scroll_id"]
    try:
        while True:
            hits = response["hits"]["hits"]
            if not hits:
                break
            for hit in hits:
                yield hit
            response  = client.scroll(scroll_id=scroll_id, scroll=scroll_ttl)
            scroll_id = response["_scroll_id"]      # 매 응답마다 갱신될 수 있음
    finally:
        if scroll_id:
            try:
                client.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass        # 정리 실패가 추출 결과를 뒤엎지 않게 함 (로그만 남김)
```

### 반드시 지켜야 할 세 가지

| 항목 | 이유 |
|---|---|
| **`finally`로 `clear_scroll` 보장** | 제약 C-2의 유일한 방어선. 정상 종료·예외·소비자 조기 중단 **모두**에서 정리되어야 함 |
| **`scroll_id`를 매 응답마다 갱신** | ES는 scroll id를 바꿔 돌려줄 수 있음. 첫 id만 들고 정리하면 실제 컨텍스트가 남음 |
| **제너레이터로 yield** | 전체를 메모리에 모으지 않음 (NFR-5) |

**주의**: 제너레이터이므로 소비자가 끝까지 순회하지 않으면 `finally`가 즉시 실행되지 않습니다.
`CrawlService`는 반드시 `with contextlib.closing(...)` 또는 완전 소비로 감싸 정리를 보장합니다.

---

## L-5. JSONL 저장 (`JsonlWriter.write`)

```
write(window, documents):
    final = directory / f"data-{window.slug}.jsonl"
    tmp   = directory / f"data-{window.slug}.jsonl.tmp"

    count = 0
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            for doc in documents:
                f.write(json.dumps(doc, ensure_ascii=False))
                f.write("\n")
                count += 1
        os.replace(tmp, final)          # 원자적 확정
    except Exception:
        tmp.unlink(missing_ok=True)     # 불완전 파일 제거
        raise
    return count
```

| 선택 | 이유 |
|---|---|
| 임시 파일 + `os.replace` | 같은 파일시스템에서 원자적. **불완전한 파일이 완성본으로 오인되지 않음** |
| 실패 시 `tmp` 삭제 | 쓰레기 파일이 쌓이지 않음. 재시도 시 처음부터 다시 씀 |
| `ensure_ascii=False` | 한글이 `\uXXXX`로 이스케이프되지 않아 파일을 눈으로 확인 가능 |
| 문서 0건이어도 파일 생성 | Q6=A — "확인했고 데이터가 없었다"가 기록으로 남음 |

---

## L-6. 체크포인트 (`CheckpointStore`)

### 저장 형식 (`{output_dir}/.checkpoint.json`)

```json
{
  "version": 1,
  "chunks": {
    "2026-09-08T18:00:00+09:00": {
      "status": "done", "doc_count": 15234,
      "updated_at": "2026-09-09T19:03:11+09:00", "error": null
    },
    "2026-09-09T18:00:00+09:00": {
      "status": "failed", "doc_count": 0,
      "updated_at": "2026-09-09T19:05:42+09:00",
      "error": "ConnectionTimeout: ..."
    }
  }
}
```

### 미처리 청크 선별 (Q7=A)

```
pending(windows):
    state = load()
    return [w for w in windows
            if w.key not in state or state[w.key].status == "failed"]
```

`failed`는 미처리로 간주되어 **자동 재시도**됩니다.
매일 실행되는 구조이므로 일시적 장애는 다음 날 실행에서 자연히 복구됩니다.

### 원자적 쓰기

```
save(state):
    tmp = path.with_suffix(".json.tmp")
    write json to tmp
    os.replace(tmp, path)
```

기록 시점은 **JSONL 확정 이후**입니다 (E-2 상태 전이의 "중요" 항목 참조).

---

## L-7. CSV 변환 (`CsvConverter`)

### 값 추출 (순수 함수)

```
MISSING = sentinel object            # "필드 없음"을 None과 구별하기 위한 표식
METADATA = {"_id", "_index", "_score"}

extract_value(hit, path):
    if path in METADATA:
        return hit.get(path, MISSING)

    node = hit.get("_source", {})
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return MISSING
    return node
```

`MISSING` 표식이 필요한 이유: Q5=B에서 "필드 없음"과 "값이 `null`"을 **구분**하기로 했으므로,
`None`을 반환값으로 쓰면 두 경우를 구별할 수 없습니다.

### 행 생성 (순수 함수)

```
to_row(hit):
    row = []
    for spec in columns:
        value = extract_value(hit, spec.source)
        row.append(render(value))
    return row

render(value):
    if value is MISSING:                 return missing_value      # ""      (Q5=B)
    if value is None:                    return null_value         # "NULL"  (CQ2=A)
    if isinstance(value, bool):          return "true" / "false"
    if isinstance(value, (dict, list)):  return json.dumps(value, ensure_ascii=False)   # (Q4=A)
    return str(value)
```

| 입력 값 | CSV 셀 |
|---|---|
| 필드 자체가 없음 | `` (빈 문자열) |
| `null` | `NULL` |
| `true` | `true` |
| `"kim"` | `kim` |
| `42` | `42` |
| `["a","b"]` | `["a", "b"]` |
| `{"x":1}` | `{"x": 1}` |

`bool`을 먼저 검사하는 이유: Python에서 `bool`은 `int`의 하위 타입이라
순서를 바꾸면 `True`가 `1`로 기록됩니다.

### 파일 변환

```
convert(jsonl_path, csv_path):
    tmp = csv_path + ".tmp"
    rows = 0
    with open(jsonl_path, encoding="utf-8") as src,
         open(tmp, "w", encoding="utf-8-sig", newline="") as dst:      # (Q9=B)
        writer = csv.writer(dst)
        if write_header:
            writer.writerow([spec.header for spec in columns])
        for line in src:
            line = line.strip()
            if not line:
                continue
            writer.writerow(to_row(json.loads(line)))
            rows += 1
    os.replace(tmp, csv_path)
    return rows
```

| 선택 | 이유 |
|---|---|
| `encoding="utf-8-sig"` | BOM이 붙어 Excel에서 한글이 깨지지 않음. pandas도 그대로 읽음 (Q9=B) |
| `newline=""` | `csv` 모듈 권장. Windows에서 빈 줄이 끼는 문제 방지 |
| 한 줄씩 스트리밍 | 파일 전체를 메모리에 올리지 않음 (NFR-5) |
| 임시 파일 + `os.replace` | 변환 중 중단 시 불완전한 CSV가 남지 않음 |

---

## L-8. 오케스트레이션 — `extract`

```
extract(start=None, end=None):
    if start is None or end is None:
        start, end = chunker.default_window(now())          # D-1

    windows = chunker.chunks(start, end)                    # L-1
    todo    = checkpoint.pending(windows)                   # L-6
    results = []

    for window in windows:
        if window not in todo:
            results.append(ChunkResult(window, "skipped"))
            continue
        try:
            with closing(extractor.iter_documents(window)) as docs:
                count = writer.write(window, docs)          # L-4 -> L-5
            checkpoint.mark_done(window, count)             # 반드시 write 이후
            results.append(ChunkResult(window, "done", count))
        except Exception as exc:
            checkpoint.mark_failed(window, str(exc))
            results.append(ChunkResult(window, "failed", 0, str(exc)))
            continue                                        # 다음 청크로 계속 (NFR-4)

    return Report(results)
```

**순차 실행**입니다 (NFR-7). 한 청크의 실패가 나머지를 막지 않습니다.

## L-9. 오케스트레이션 — `convert`

```
convert(start=None, end=None):
    if start is None or end is None:
        start, end = chunker.default_window(now())

    windows = chunker.chunks(start, end)                    # D-3: extract와 동일 인자
    results = []

    for window in windows:
        jsonl = writer.path_for(window)
        if not jsonl.exists():
            log.warning("JSONL not found, skipping: %s", jsonl)
            results.append(ChunkResult(window, "skipped"))   # 오류 아님 (D-3)
            continue
        try:
            rows = converter.convert(jsonl, csv_path_for(window))
            results.append(ChunkResult(window, "done", rows))
        except Exception as exc:
            results.append(ChunkResult(window, "failed", 0, str(exc)))
            continue

    return Report(results)
```

`convert`는 **체크포인트를 읽지도 쓰지도 않습니다.** 체크포인트는 추출만 추적합니다.
CSV 변환은 멱등이므로 몇 번을 다시 돌려도 결과가 같습니다.

---

## L-10. 테스트 가능한 속성 (PBT-01)

Property-Based Testing 확장이 **Partial 모드**로 활성화되어 있습니다
(PBT-02, PBT-03, PBT-07, PBT-08, PBT-09만 차단성).

| ID | 컴포넌트 | 범주 | 속성 | PBT 규칙 | 강제 |
|---|---|---|---|---|---|
| P-1 | `DateChunker.chunks` | 불변식 | 청크들의 합집합 == `[start, end)` — 빈틈 없음 | PBT-03 | **차단성** |
| P-2 | `DateChunker.chunks` | 불변식 | 인접 청크가 겹치지 않음 (`w[i].end == w[i+1].start`) | PBT-03 | **차단성** |
| P-3 | `DateChunker.chunks` | 불변식 | 모든 청크의 `0 < duration <= chunk_hours` | PBT-03 | **차단성** |
| P-4 | `DateChunker.chunks` | 불변식 | 시간순 정렬, `first.start == start`, `last.end == end` | PBT-03 | **차단성** |
| P-5 | `JsonlWriter` + 리더 | 왕복 | 문서 목록 -> 쓰기 -> 읽기 == 원본 | PBT-02 | **차단성** |
| P-6 | `CsvConverter.convert` | 불변식 | 출력 행 수 == 입력 문서 수 | PBT-03 | **차단성** |
| P-7 | `CsvConverter.to_row` | 불변식 | 모든 행의 길이 == `len(headers)` | PBT-03 | **차단성** |
| P-8 | `CsvConverter.extract_value` | 불변식 | 문서에 존재하는 경로는 항상 그 값을 반환 | PBT-03 | **차단성** |
| P-9 | `TimeWindow.key` | 왕복 | `parse(window.key) == window.end` | PBT-02 | **차단성** |
| P-10 | `TimeWindow.slug` | 불변식 | 서로 다른 창은 서로 다른 `slug` (파일명 충돌 불가, CQ1=A) | PBT-03 | **차단성** |
| P-11 | 도메인 제너레이터 | 생성기 품질 | ES 히트·시간 창·컬럼 명세용 제너레이터를 재사용 가능하게 정의 | PBT-07 | **차단성** |
| P-12 | 전체 PBT | 재현성 | shrinking 활성, 실패 시 시드 로깅 | PBT-08 | **차단성** |
| P-13 | `CsvConverter.convert` | 멱등성 | 두 번 변환해도 결과 파일이 동일 | PBT-04 | 권고 |
| P-14 | `CheckpointStore` | 상태 기반 | 임의의 mark 순서 후에도 `done`은 `failed`로 되돌아가지 않음 | PBT-06 | 권고 |

### 속성이 식별되지 않은 컴포넌트

| 컴포넌트 | 사유 |
|---|---|
| `EsExtractor` | 외부 시스템 I/O가 본질. 속성보다 **예제 기반 테스트 + 모킹**이 적합. 단 "scroll 컨텍스트가 항상 정리된다"는 예제 테스트로 반드시 검증 |
| `CLI` | 인자 파싱과 종료 코드 매핑. 예제 기반 테스트로 충분 |
| `Config` | 검증 규칙 모음. 경계값 예제 테스트로 충분 |
