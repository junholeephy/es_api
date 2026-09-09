# NFR 설계 패턴 (NFR Design Patterns) — `es-crawler`

**단계**: CONSTRUCTION - NFR Design
**단위(Unit)**: `es-crawler`

> **우선순위**: `general_implementation` 규약 > 다른 모든 규약 (사용자 지시)

---

## P-1. 재시도는 한 계층에만 둔다

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-R01, NFR-R02, NFR-R03 |
| 패턴 | 클라이언트 계층 단일 재시도 |

```python
Elasticsearch(
    hosts=cfg.es.hosts,
    api_key=cfg.es.api_key,
    request_timeout=60,
    max_retries=3,
    retry_on_timeout=True,
    retry_on_status=(429, 502, 503, 504),
)
```

**애플리케이션 레벨 재시도 루프를 중첩하지 않습니다.** 두 계층에 재시도를 두면
실제 대기 시간이 곱으로 늘어납니다 — 3회 x 3회 = 9회, 타임아웃 60초 기준 최악 9분입니다.
청크 하나가 그렇게 매달리는 동안 나머지 청크는 시작조차 못 합니다.

재시도로 회복되지 않은 실패만 `CheckpointStore.mark_failed()` 에 도달하고,
그것은 다음 날 실행에서 자동 재시도됩니다(BR-K03). **재시도의 두 번째 계층은 "내일"입니다.**

---

## P-2. 실패 격리 — 청크 경계가 곧 격리 경계

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-R04, BR-X06 |
| 패턴 | 루프 내 예외 포획 + 상태 기록 + 계속 진행 |

```python
for window in windows:
    try:
        ...                                  # 추출 -> 저장
        checkpoint.mark_done(window, count)
        results.append(ChunkResult(window, "done", count))
    except Exception as exc:
        checkpoint.mark_failed(window, str(exc))
        results.append(ChunkResult(window, "failed", 0, str(exc)))
        continue
```

`except Exception` 으로 넓게 잡는 것이 의도입니다 — 어떤 예외든 그 청크만 잃고
나머지 일정은 계속됩니다. `KeyboardInterrupt` 와 `SystemExit` 은 `BaseException` 이라
이 그물에 걸리지 않으므로, 사람이 중단하면 정상적으로 멈춥니다.

---

## P-3. 원자적 쓰기 + `fsync`

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-R06, BR-F05, BR-K05 |
| 적용 대상 | JSONL, CSV, 체크포인트 **셋 모두** |
| 결정 | Q6=A — `fsync` 후 `os.replace` |

```python
def atomic_write(path: Path, write_body) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding=...) as f:
            write_body(f)
            f.flush()
            os.fsync(f.fileno())      # OS 버퍼를 디스크로 (Q6=A)
        os.replace(tmp, path)         # 원자적 교체
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
```

**`fsync` 비용은 청크당 한 번**입니다. 하루 1청크 기준 실행당 3회(JSONL·CSV·체크포인트)이므로
무시할 수준이고, 그 대가로 갑작스러운 종료에도 상태가 남습니다.

이 패턴이 **P-6(체크포인트 조정)의 전제**입니다 — 최종 이름을 가진 파일은
구조적으로 항상 완성본입니다.

---

## P-4. scroll 컨텍스트 정리 보장

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-R07, 제약 C-2 |
| 패턴 | 제너레이터 + `try/finally` + 호출부 `closing()` |

```python
def iter_documents(self, window) -> Iterator[dict]:
    response  = self._client.search(...)
    scroll_id = response["_scroll_id"]
    try:
        while True:
            hits = response["hits"]["hits"]
            if not hits:
                break
            yield from hits
            response  = self._client.scroll(scroll_id=scroll_id, scroll=ttl)
            scroll_id = response["_scroll_id"]        # 매번 갱신
    finally:
        self._clear(scroll_id)                        # 실패해도 삼킨다
```

호출부는 반드시 감쌉니다.

```python
with closing(extractor.iter_documents(window)) as docs:
    count = writer.write(window, docs)
```

**`closing()` 이 없으면 `finally` 가 즉시 실행되지 않습니다.** 제너레이터가 끝까지
소비되지 않은 채(예: `write` 가 도중에 예외) 참조만 사라지면 정리는 GC 시점으로 밀립니다.
`closing()` 은 `.close()` 를 호출해 제너레이터 안에 `GeneratorExit` 을 던지고,
그 순간 `finally` 가 돕니다.

**이것이 이 프로젝트에서 가장 조용히 깨질 수 있는 부분입니다.** 컨텍스트가 남아도
프로그램은 정상 종료하고 로그도 깨끗합니다. 부하는 클러스터 쪽에서만 보입니다.

---

## P-5. 스트리밍 경계

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-P04, NFR-M05 |
| 패턴 | 제너레이터 체인. 리스트로 materialize 하는 지점을 **명시적으로 한정** |

```
ES scroll  --(Iterator[dict])-->  JsonlWriter.write  --(파일)-->  CsvConverter.convert
                  |                                                        |
                  +-- 표본 1000건만 list 로 모음 (P-10)                      +-- 한 줄씩 읽음
```

**리스트가 만들어지는 곳은 두 곳뿐이고 둘 다 상한이 있습니다.**
- 스키마 표본: 최대 `schema_sample`(기본 1000)건
- scroll 한 배치: 최대 `batch_size`(기본 2000)건 — `elasticsearch-py` 응답 자체

100만 건 전체가 메모리에 올라오는 경로는 없습니다.

---

## P-6. 체크포인트 조정 (Reconciliation)

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-R05, FR-6 |
| 결정 | Q2=B — JSONL이 있으면 완료로 간주하고 체크포인트를 보정 |

```python
def reconcile(self, windows):
    """파일은 있는데 체크포인트에 없는 창을 done 으로 채워 넣는다."""
    for w in windows:
        if not self.is_done(w) and writer.exists(w):
            count = count_lines(writer.path_for(w))
            self.mark_done(w, count)
            log.warning("checkpoint backfilled from existing file: %s", w.key)
```

**이 패턴이 안전한 이유는 P-3 때문입니다.** 최종 이름(`data-....jsonl`)을 가진 파일은
`os.replace` 를 통과한 것뿐이므로 **구조적으로 항상 완성본**입니다.
쓰다 만 파일은 `.tmp` 이름으로만 존재할 수 있고, 이 이름은 절대 조회되지 않습니다.

메우려는 구멍은 구체적입니다 — `os.replace` 는 성공했지만 `mark_done()` 전에
프로세스가 죽은 창(BR-E08의 순서 규칙이 남기는 유일한 틈).

### 잔여 엣지: 남겨진 `.tmp` 파일

BR-F06은 예외 시 `.tmp` 를 지우지만, 하드 크래시에는 그럴 기회가 없습니다.

**규칙**: 조정은 **최종 이름만** 봅니다. 남겨진 `.tmp` 는 산출물로 오인되지 않으며,
같은 창을 다시 추출할 때 덮어써집니다. 별도의 청소 절차를 두지 않습니다 —
이름이 겹치므로 자연히 회수됩니다.

---

## P-7. 부분 실패 시의 변환

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-X03, 폐기된 D-4의 재해석 |
| 결정 | Q3=A — **성공한 청크만 변환** |

```python
report_extract = self._extract(windows)
done = [r.window for r in report_extract.results if r.status in ("done", "skipped")]
report_convert = self._convert(done)          # 실패한 청크는 대상에서 빠진다
```

**폐기된 D-4(`extract && convert`)와의 차이**: `&&` 는 "하나라도 실패하면 아무것도 변환하지 않는다"였습니다.
단일 실행으로 합치면서 그 의미를 **청크 단위로 좁혔습니다** — 성공한 3일치는 지금 CSV로 나오고,
실패한 2일치는 다음 실행에서 추출과 변환이 함께 이뤄집니다.

부분 결과가 즉시 쓸 수 있게 되는 대신, "CSV 디렉터리가 완전하다"는 보장이 사라집니다.
그 사실은 종료 코드 `1` 과 RUN SUMMARY 의 `chunks: failed N` 줄로 드러납니다.

---

## P-8. 관측성 — RUN SUMMARY 조립

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-O01 ~ NFR-O09 |
| 결정 | Q4=A — `status` 가 원인을 구분 |

### 스트림 분리 (NFR-O02)

| 스트림 | 내용 |
|---|---|
| **stdout** | RUN SUMMARY 블록 **하나만** |
| **stderr** | 진행 상황, 경고, 예외 |

`python src/run.py ... > summary.txt` 로 요약만 깔끔히 남길 수 있어야 합니다.
요약이 stderr 로 새면 그 파일이 빕니다.

### `status` 어휘 (Q4=A)

| `status` | 조건 | 종료 코드 |
|---|---|---|
| `OK` | 스키마 위반 없음, 실패 청크 없음 | `0` |
| `SCHEMA MISMATCH` | 스키마 위반 있음, 실패 청크 없음 | `1` |
| `CHUNKS FAILED` | 스키마 위반 없음, 실패 청크 있음 | `1` |
| `SCHEMA MISMATCH + CHUNKS FAILED` | 둘 다 | `1` |

종료 코드 `1` 의 원인이 둘이라 화면만 보고 구분되어야 합니다.
`2`(시작도 못 함)는 RUN SUMMARY 를 찍지 못하고 죽으므로 이 표에 없습니다.

### 표시 폭 (NFR-O05)

한글은 터미널에서 두 칸을 차지하므로 `len()` 으로 자르면 정렬이 깨집니다.
`unicodedata.east_asian_width(ch) in "WF"` 이면 2로 세어 80칸을 지킵니다
(규약 `report.py` 의 `_w()` 와 동일한 방식).

---

## P-9. 진행 로깅

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-O08, FR-10 |
| 결정 | Q5=B — 청크 단위 + N건마다 진행률 |

```
[stderr]
chunk 1/5  2026-09-01T18:00+09:00 .. 2026-09-02T18:00+09:00
  ... 50,000 docs
  ... 100,000 docs
  done  152,431 docs in 412.3s -> outputs/data-2026-09-02T1800+0900.jsonl
chunk 2/5  ...
```

진행률 간격(`progress_every`)은 기본 50,000건이며 설정으로 조정합니다.
100만 건이면 20줄이라 "살아 있는가"를 알기에 충분하고 스크롤을 뒤덮지 않습니다.

---

## P-10. 스키마 표본 검증

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-O06, 제약 C5 |
| 결정 | Q1=A — **첫 청크에서만** 1000건 표본 |

```python
sample: list[dict] = []
for hit in docs:
    if is_first_chunk and len(sample) < cfg.output.schema_sample:
        sample.append(hit)
    yield hit
...
report = validate(sample)
```

RUN SUMMARY 는 표본이었음을 반드시 드러냅니다.

```
schema    : 6 ok / 1 MISMATCH   (sampled 1,000 from first chunk)
```

**전수 검사가 아님을 표기하는 것이 규칙입니다.** 표기가 없으면 "1건도 안 틀렸다"로 읽히고,
회수 채널(C5)이 거짓 안심을 줍니다.

**첫 청크만으로 충분하다고 본 근거**: 포맷은 하루 사이에 잘 바뀌지 않고,
이 검사의 목적은 전수 품질 보증이 아니라 "내 가정과 실제 포맷이 다른가"를 알아내는 것입니다.
포맷이 도중에 바뀌는 상황을 겪게 되면 그때 Q1=B(매 청크 합집합)로 올립니다 — 규약 §4의 되돌리기 고리.

---

## P-11. 시크릿 로딩과 마스킹

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-S01 ~ NFR-S04 |

| 규칙 | 구현 |
|---|---|
| 시크릿은 `configs/env.yaml` 에서만 | `config.py` 가 유일한 로딩 지점 |
| 로그·RUN SUMMARY 에 키 미출력 | `EsConfig.__repr__` 를 재정의해 `api_key='***'` 로 |
| 예외 로깅 시 설정 객체 덤프 금지 | 예외 메시지에 `cfg` 를 포함하지 않음 |
| `args` 줄에 시크릿 없음 | 시크릿은 CLI 인자가 아니라 설정 파일에만 존재 |

`args` 줄을 그대로 찍는 것(NFR-O03)이 안전한 이유는 **시크릿이 인자에 없기 때문**입니다.
이 분리가 깨지면(예: `--api-key` 인자 추가) NFR-O03과 NFR-S03이 즉시 충돌합니다.

---

## P-12. 조기 실패 (Fail Fast)

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-X04, 규약 §1.3 |

**어떤 계산도 하기 전에** 검사하는 것들:

```
1. CLI 인자 형식        (BR-T01 ~ BR-T06)
2. 설정 파일 로드·검증   (BR-C01 ~ BR-C11)
3. 체크포인트 파일 파싱  (BR-K06)
4. ES 연결·인증         (client.info() 한 번)
5. 출력 디렉터리 생성 가능
```

전부 통과한 뒤에야 첫 scroll 을 던집니다. 종료 코드는 `2` 입니다.

**30분 돌린 뒤 인자 하나 때문에 죽으면 사이클 하나를 통째로 버립니다** (규약 §1.3).
`chunk_hours > 24`(BR-C01)를 여기서 잡는 것이 제약 C-3을 코드로 강제하는 지점입니다.

---

## P-13. venv 갈아타기

| 항목 | 내용 |
|---|---|
| 대응 NFR | NFR-X05, 규약 §3.1 |

`src/run.py` 가 `configs/env.yaml` 의 `paths.venv` 를 **argparse 이전에** 훔쳐보고,
값이 있으면 그 파이썬으로 `os.execv` 합니다.

- **PyYAML 을 쓰지 않습니다** — 이 시점에는 아직 의존성이 설치되지 않았을 수 있습니다.
  규약의 `run.py` 처럼 손으로 두 칸 들여쓰기 매핑을 읽습니다
- 경로에 파이썬이 없으면 **어떤 계산도 하기 전에** 종료 코드 `2`
- 이미 그 venv 면 아무것도 하지 않습니다 (`sys.prefix` 비교)
- 환경변수 플래그로 재진입을 막습니다

> 설정에 적어만 두고 쓰지 않으면 "설정했는데 무시된다"가 됩니다.
> 설정 파일의 값이 아무것도 바꾸지 않는 것은 그 자체로 결함입니다. (규약 §3.1)

---

## 확장 규칙 준수 요약 (Extension Compliance)

| 규칙 | 상태 | 근거 |
|---|---|---|
| PBT-02, PBT-03 | 사전 식별됨 | Functional Design L-10의 P-1~P-10. 이 단계는 패턴 설계이며 테스트 구현은 Code Generation |
| PBT-07, PBT-08 | 사전 식별됨 | 동일 |
| PBT-09 | ✅ 이전 단계에서 충족 | `hypothesis` 선정 완료 |
| Security Baseline | N/A | 옵트아웃 (Q12=B) |
| Resiliency Baseline | N/A | 옵트아웃 (Q13=B). 단 P-1~P-3, P-6은 복원력 패턴이며 NFR-R01~R07에서 도출된 이 프로젝트 자체의 요구사항 |

**차단성 발견 사항(Blocking findings): 없음.**
