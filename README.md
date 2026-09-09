# es_api — Elasticsearch 시간 구간 추출기

Elasticsearch 에서 시간 구간별로 문서를 받아 JSONL 로 남기고, 설정한 컬럼만 CSV 로
정리한다. 하루 한 번 스케줄러가 돌리는 것을 전제로 만들었다.

> **이 파일은 이식되지 않는다** (`.gitattributes` 의 `export-ignore`).
> 사본을 받는 쪽이 읽을 문서는 `docs/usage.md` 와 `TODO.md` 다.

## 구조

```
src/run.py                진입점. venv 갈아타기 + 위임만
src/es_crawler/
  __main__.py             CLI 인자, 실행 순서, 종료 코드
  config.py               설정 로딩과 검증. 설정 파일을 읽는 유일한 곳
  chunker.py              시간 구간 자르기 (순수 로직)
  schema.py               입력 문서 형태의 단일 출처 + 대조
  synth.py                합성 문서 생성 + 가짜 검색 클라이언트
  load.py                 Elasticsearch 접근. 바깥 의존이 여기 하나뿐이다
  writer.py               JSONL 쓰기 (원자적)
  converter.py            JSONL -> CSV
  checkpoint.py           구간별 진행 상태
  pipeline.py             조립. 순서에 얽힌 규칙이 전부 여기 모인다
  report.py               RUN SUMMARY
configs/env.example.yaml  설정 예시. 실값은 운영 쪽에만
TODO.md · todo/           운영 환경에서 만들어야 하는 것과 그 규격
docs/usage.md             프로그램이 어떻게 도는지 (이식됨)
```

## 개발

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m pytest          # 클러스터 없이 전부 통과해야 한다
.venv/bin/ruff check src tests
.venv/bin/ruff format src tests
.venv/bin/mypy
```

```bash
.venv/bin/python src/run.py --dry-run --rows 2000
.venv/bin/python src/run.py --dry-run --adversarial
```

## 설계에서 조심한 것

| | |
|---|---|
| **검색 상태 정리** | `scroll` 은 서버 메모리에 상태를 남긴다. 정리를 놓쳐도 프로그램은 정상 종료하고 로그도 깨끗하다 — 부하는 클러스터 쪽에서만 보인다. `load.iter_documents` 를 반드시 `closing()` 으로 감싸는 이유다 |
| **기록 순서** | 파일을 확정한 **뒤에** 완료로 남긴다. 뒤집으면 "완료인데 파일은 없는" 상태가 생기고 그 구간은 영원히 건너뛰어진다 |
| **파일 이름** | 구간의 끝 **시각**을 쓴다. 날짜만 쓰면 하루보다 짧은 조각이 같은 이름을 갖는다 |
| **값 렌더링 순서** | `MISSING -> None -> bool -> dict/list -> str`. bool 검사가 숫자보다 뒤로 가면 `True` 가 `1` 로 기록된다 |
| **재시도는 한 계층** | 클라이언트에만 둔다. 겹치면 대기 시간이 곱으로 늘어난다 |
| **서머타임** | 구간의 두 끝은 UTC 오프셋이 달라도 된다. 같아야 한다고 두면 DST 를 넘는 구간이 통째로 거부된다 |

## 이식

```bash
git tag v1.0.0
bash scripts/sync.sh v1.0.0      # preflight. 통과해야 push
git push origin main --tags
```

## 문서

설계 과정과 결정 근거는 `aidlc-docs/` 에 있다 (이식되지 않는다).
