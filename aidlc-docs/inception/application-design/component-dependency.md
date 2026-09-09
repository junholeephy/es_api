# 컴포넌트 의존 관계 (Component Dependency)

**단위(Unit)**: `es-crawler`

---

## 1. 계층 구조

```
+------------------------------------------+
| Entry Layer                              |
| cli.py                __init__.py        |
+------------------------------------------+
                     |
                     v
+------------------------------------------+
| Orchestration Layer                      |
| pipeline.py : CrawlService               |
+------------------------------------------+
                     |
                     v
+------------------------------------------+
| Component Layer                          |
| chunker.py   extractor.py   writer.py    |
| converter.py checkpoint.py               |
+------------------------------------------+
                     |
                     v
+------------------------------------------+
| Foundation Layer                         |
| config.py    elasticsearch-py (external) |
+------------------------------------------+
```

**규칙**: 의존은 **위에서 아래로만** 흐릅니다. 아래 계층이 위 계층을 참조하지 않습니다.
컴포넌트끼리도 서로 참조하지 않으며, 조합은 `CrawlService`가 전담합니다.

---

## 2. 의존 매트릭스

행이 열에 의존합니다. `X` = 직접 의존.

| 의존 주체 \ 대상 | Config | DateChunker | EsExtractor | JsonlWriter | CsvConverter | CheckpointStore | CrawlService | es-py |
|---|---|---|---|---|---|---|---|---|
| **CLI**             | X |   |   |   |   |   | X |   |
| **CrawlService**    | X | X | X | X | X | X |   | X |
| **DateChunker**     | X |   |   |   |   |   |   |   |
| **EsExtractor**     | X |   |   |   |   |   |   | X |
| **JsonlWriter**     |   |   |   |   |   |   |   |   |
| **CsvConverter**    |   |   |   |   |   |   |   |   |
| **CheckpointStore** |   |   |   |   |   |   |   |   |
| **Config**          |   |   |   |   |   |   |   |   |

### 관찰

- **`JsonlWriter`, `CsvConverter`, `CheckpointStore`는 의존이 전혀 없습니다.**
  생성자로 필요한 값(경로, 컬럼 목록)만 받으므로 ES나 설정 없이 단독 테스트가 가능합니다.
- **`DateChunker`는 `ChunkConfig`만 의존**하고 부수효과가 없어, 속성 기반 테스트의 주 대상입니다.
- **`EsExtractor`만 `elasticsearch-py`에 직접 의존**합니다. 외부 시스템 의존이 한 곳에 격리되어,
  테스트에서 이 컴포넌트에 주입되는 클라이언트만 모킹하면 됩니다 (Q6=A).
- **`CrawlService`가 유일하게 여러 컴포넌트에 의존**합니다. 결합의 복잡도가 여기 한 곳에 모입니다.

---

## 3. 통신 패턴

| 관계 | 패턴 | 비고 |
|---|---|---|
| CLI -> CrawlService | 직접 메서드 호출 | 동기 |
| CrawlService -> 컴포넌트 | 직접 메서드 호출 | 동기, 순차 |
| CrawlService -> EsExtractor | **이터레이터(제너레이터) 반환** | 스트리밍, 지연 평가 (NFR-5) |
| EsExtractor -> Elasticsearch | HTTP (elasticsearch-py) | scroll 페이징, 클라이언트가 재시도 |
| CheckpointStore -> 파일시스템 | 원자적 쓰기 (tmp + `os.replace`) | 손상 방지 |
| JsonlWriter -> 파일시스템 | 원자적 쓰기 (tmp + `os.replace`) | 불완전 파일 방지 |

**의존성 주입**: `Elasticsearch` 클라이언트는 `CrawlService` 생성자에서 선택적으로 주입받아
`EsExtractor`에 전달합니다. 이것이 테스트에서 ES를 대체하는 유일한 지점입니다.

---

## 4. 데이터 흐름: `extract`

```
+----------+     +--------------+     +------------------+
|  Config  | --> | CrawlService | --> |   DateChunker    |
+----------+     +--------------+     +------------------+
                        |
                        | list[TimeWindow]
                        v
                 +------------------+
                 | CheckpointStore  |
                 |   pending()      |
                 +------------------+
                        |
                        | unfinished chunks
                        v
                 +------------------+
                 |   EsExtractor    |
                 |   scroll paging  |
                 +------------------+
                        |
                        | Iterator[dict]
                        v
                 +------------------+
                 |   JsonlWriter    |
                 +------------------+
                        |
                        | data-YYYY-MM-DD.jsonl
                        v
                 +------------------+
                 | CheckpointStore  |
                 |   mark_done()    |
                 +------------------+
```

## 5. 데이터 흐름: `convert`

```
+----------+     +--------------+     +------------------+
|  Config  | --> | CrawlService | --> |   DateChunker    |
+----------+     +--------------+     +------------------+
                        |
                        | list[TimeWindow]
                        v
                 +------------------+
                 |   JsonlWriter    |
                 |   path_for()     |
                 +------------------+
                        |
                        | data-YYYY-MM-DD.jsonl
                        v
                 +------------------+
                 |   CsvConverter   |
                 +------------------+
                        |
                        | data-YYYY-MM-DD.csv
                        v
                 +------------------+
                 |      Report      |
                 +------------------+
```

**주목**: `convert` 흐름에는 `EsExtractor`도 `CheckpointStore`도 등장하지 않습니다.
Elasticsearch에 접속하지 않고 동작하므로, 변환 로직만 고쳐 재실행할 때 클러스터에 부하를 주지 않습니다.

---

## 6. 출력 디렉터리 구조

```
output/
  .checkpoint.json          체크포인트 상태 (CheckpointStore)
  data-2026-09-08.jsonl     추출 원본 (JsonlWriter)
  data-2026-09-09.jsonl
  data-2026-09-08.csv       변환 결과 (CsvConverter)
  data-2026-09-09.csv
```

파일명의 날짜는 창의 **종료 날짜**입니다.
`data-2026-09-09.jsonl` = `[2026-09-08 18:00 KST, 2026-09-09 18:00 KST)` (D-1).

---

## 7. 결합도 평가

| 컴포넌트 | 팬인(누가 의존) | 팬아웃(무엇에 의존) | 평가 |
|---|---|---|---|
| Config | 4 | 0 | 안정적 기반. 변경 시 파급이 크므로 필드 추가는 신중히 |
| DateChunker | 1 | 1 | 낮은 결합. 순수 로직 |
| EsExtractor | 1 | 2 | 외부 의존을 여기 한 곳으로 격리 |
| JsonlWriter | 1 | 0 | 독립적 |
| CsvConverter | 1 | 0 | 독립적 |
| CheckpointStore | 1 | 0 | 독립적 |
| CrawlService | 1 | 6 | 팬아웃이 높지만 의도된 것 — 조합 책임이 한 곳에 모임 |
| CLI | 0 | 2 | 얇은 껍데기 |

**순환 의존 없음.** 의존 그래프는 단방향 비순환(DAG)입니다.
