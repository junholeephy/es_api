# 단위 테스트 실행 지침

**단위(Unit)**: `es-crawler`
**작성일**: 2026-09-09

---

## 1. 전체 실행

```bash
.venv/bin/python -m pytest
```

**기대 출력**

```
101 passed in ~6s
```

**Elasticsearch 접속 없이 전부 통과해야 합니다.** 접속이 필요한 테스트가 하나라도
생기면 개발 장비에서 실행 가능성을 기계적으로 확인할 방법이 사라집니다.

### 외부 자격증명 없이 통과하는지 확인

```bash
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u ES_API_KEY .venv/bin/python -m pytest
```

---

## 2. 파일별 구성

| 파일 | 개수 | 무엇을 지키는가 |
|---|---|---|
| `tests/test_chunker.py` | 23 | 구간 경계. 여기가 틀리면 문서가 조용히 빠지거나 겹친다 |
| `tests/test_writer.py` | 8 | 저장 왕복, 원자적 쓰기, 파일명 충돌 |
| `tests/test_converter.py` | 15 | 값 렌더링 판정 순서, 컬럼 선택, 인코딩 |
| `tests/test_checkpoint.py` | 11 | 상태 전이, 손상 파일 처리 |
| `tests/test_load.py` | 12 | 검색 상태 정리, 조회 본문 |
| `tests/test_schema.py` | 14 | 형태 대조, 위반과 노트 구분 |
| `tests/test_run.py` | 18 | 전 구간 스모크, 종료 코드, 출력 스트림 |

### 속성 기반 테스트 (13개)

| 대상 | 속성 |
|---|---|
| 구간 분할 | 합집합 = 요청 범위 / 인접 무겹침 / 폭 ≤ 24h / 시간순 정렬 |
| 구간 키 | `parse(key) == end` (왕복) |
| 파일명 | 서로 다른 구간 → 서로 다른 이름 |
| 기본 창 | 언제 실행하든 24시간이고 미래를 넘지 않음 |
| JSONL | 쓰기 → 읽기 = 원본 (왕복) |
| CSV | 행 수 = 문서 수 / 셀 수 = 헤더 수 / 존재하는 경로는 그 값 / 없는 경로는 MISSING |

---

## 3. 부분 실행

```bash
# 파일 하나
.venv/bin/python -m pytest tests/test_chunker.py -v

# 이름으로 고르기
.venv/bin/python -m pytest -k "scroll or release" -v

# 속성 기반만
.venv/bin/python -m pytest -k "property or round_trip" -v
```

---

## 4. 속성 테스트가 실패했을 때

속성 테스트는 실행할 때마다 다른 입력을 만듭니다. **어제 통과한 것이 오늘 실패할 수
있고, 그건 결함이지 불안정성이 아닙니다.**

실패하면 출력에 두 가지가 함께 나옵니다.

```
Falsifying example: test_a_path_that_exists_yields_its_value(
    document={'_index': '0', '_id': '0', '_score': None, '_source': {'_score': []}},
)
You can reproduce this test case by temporarily adding
@reproduce_failure('6.168.0', b'AIEwgTBBAAGGX3Njb3JlQQEAAA==') as a decorator
```

1. **최소 반례** — hypothesis 가 줄여 놓은 가장 작은 실패 입력
2. **재현 문구** — 테스트 함수 위에 붙이면 그 입력만 다시 돈다

### 조치 순서

1. 최소 반례를 읽고 **코드가 틀렸는지 테스트가 틀렸는지** 판단한다
2. 코드가 틀렸으면 고친다
3. 테스트가 틀렸으면 — 즉 그 입력이 실제로는 유효하지 않다면 — 생성기를 좁힌다
4. **어느 쪽이든 그 반례를 예시 테스트로 남긴다.** 다음에 같은 것이 깨지면 즉시 드러난다

실제로 이 프로젝트에서 두 번 일어났습니다.
- `_source` 안에 `_score` 라는 필드가 있는 문서 → 테스트가 틀렸음 →
  `test_metadata_names_are_reserved` 로 제약을 명시
- 서머타임을 넘는 구간 → 코드가 틀렸음 →
  `test_a_window_may_cross_a_daylight_saving_change` 로 회귀 방지

### 예제 수를 늘려서 더 찾기

```bash
.venv/bin/python -m pytest --hypothesis-seed=random -p no:randomly
.venv/bin/python -m pytest tests/test_chunker.py --hypothesis-show-statistics
```

---

## 5. 반복 실행으로 확인

속성 테스트가 있으므로 **한 번 통과했다고 끝이 아닙니다.**

```bash
for i in 1 2 3 4 5; do .venv/bin/python -m pytest -q | tail -1; done
```

**기대**: 다섯 번 모두 `101 passed`.

---

## 6. 커버리지

수치 목표를 두지 않기로 했습니다 (NFR-T02). 필요하면 임시로 볼 수 있습니다.

```bash
.venv/bin/pip install pytest-cov
.venv/bin/python -m pytest --cov=es_crawler --cov-report=term-missing
```

`pytest-cov` 를 `requirements-dev.txt` 에 넣지는 않습니다 — 쓰지 않는 도구를
고정해두면 설치 시간만 늘어납니다.

---

## 7. 테스트가 데이터 파일을 만들지 않는지 확인

```bash
.venv/bin/python -m pytest
git status --short
```

**기대**: 출력 없음. 테스트는 `tmp_path` 와 `synth.generate()` 만 쓰므로
저장소에 파일을 남기지 않습니다. 여기서 `.jsonl` 이나 `.csv` 가 보이면
어딘가에서 픽스처를 파일로 만든 것입니다.
