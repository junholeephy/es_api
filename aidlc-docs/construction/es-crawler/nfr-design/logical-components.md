# 논리 컴포넌트 (Logical Components) — `es-crawler`

**단계**: CONSTRUCTION - NFR Design
**단위(Unit)**: `es-crawler`

> **우선순위**: `general_implementation` 규약 > 다른 모든 규약 (사용자 지시)

---

## 1. 컴포넌트 배치

```
+-------------------------------------------------------------+
|  Entry Layer                                                |
|  src/run.py           venv switch (P-13) -> delegate only   |
+-------------------------------------------------------------+
                             |
                             v
+-------------------------------------------------------------+
|  CLI Layer                                                  |
|  __main__.py          args, fail-fast (P-12), exit codes    |
+-------------------------------------------------------------+
                             |
                             v
+-------------------------------------------------------------+
|  Orchestration Layer                                        |
|  pipeline.py          chunk loop, isolation (P-2),          |
|                       partial convert (P-7)                 |
+-------------------------------------------------------------+
                             |
                             v
+-------------------------------------------------------------+
|  Component Layer                                            |
|  chunker.py   load.py   writer.py   converter.py            |
|  checkpoint.py   schema.py   synth.py   report.py           |
+-------------------------------------------------------------+
                             |
                             v
+-------------------------------------------------------------+
|  Foundation Layer                                           |
|  config.py            elasticsearch-py (external)           |
+-------------------------------------------------------------+
```

---

## 2. 컴포넌트별 NFR 책임

| 컴포넌트 | 규약 역할 | 담당 NFR 패턴 |
|---|---|---|
| `run.py` | 진입점 | **P-13** venv 갈아타기 |
| `__main__.py` | CLI·종료 코드 | **P-12** 조기 실패, **P-8** 종료 코드 매핑 |
| `pipeline.py` | 기능 코드 | **P-2** 실패 격리, **P-5** 스트리밍 경계, **P-6** 조정, **P-7** 부분 변환, **P-9** 진행 로깅, **P-10** 표본 수집 |
| `load.py` | 입력 포맷을 아는 유일한 곳 | **P-1** 재시도(클라이언트 구성), **P-4** scroll 정리 |
| `writer.py` | (프로젝트 고유) | **P-3** 원자적 쓰기 + fsync |
| `converter.py` | (프로젝트 고유) | **P-3** 원자적 쓰기 |
| `checkpoint.py` | (프로젝트 고유) | **P-3** 원자적 쓰기 + fsync, **P-6** 조정 |
| `chunker.py` | (프로젝트 고유) | 순수 로직. NFR 패턴 없음 |
| `schema.py` | 스키마 단일 출처 | **P-10** 표본 검증 |
| `synth.py` | 가짜 데이터 생성 | NFR-T03, NFR-T07 (클러스터 없이 테스트) |
| `report.py` | RUN SUMMARY | **P-8** 조립·표시 폭·status 어휘 |
| `config.py` | 설정 로딩 | **P-11** 시크릿 로딩·마스킹, **P-12** 검증 |

---

## 3. NFR 관점의 데이터 흐름

```
  configs/env.yaml
        |
        | P-11 secrets, P-12 validate
        v
   +---------+      P-12 fail fast, exit 2
   | config  | -----------------------------> (abort before any query)
   +---------+
        |
        v
   +---------+      pure logic, no NFR concern
   | chunker |
   +---------+
        |
        | list[TimeWindow]
        v
   +------------+   P-6 reconcile: file exists but no record -> backfill
   | checkpoint |
   +------------+
        |
        | pending windows only
        v
   +---------+      P-1 client retry (single layer)
   |  load   |      P-4 scroll context always cleared
   +---------+
        |
        | Iterator[dict]   P-5 streaming, P-9 progress, P-10 sample
        v
   +---------+      P-3 fsync + os.replace
   | writer  |
   +---------+
        |
        | P-2 failure isolated here, loop continues
        v
   +------------+   P-3 fsync + os.replace, ordered AFTER writer
   | checkpoint |
   +------------+
        |
        | P-7 only succeeded windows pass
        v
   +-----------+    P-3 atomic write
   | converter |
   +-----------+
        |
        v
   +---------+      P-8 one block, stdout, status vocabulary
   | report  |
   +---------+
```

---

## 4. 도입하지 않은 인프라 컴포넌트

| 컴포넌트 | 판정 | 근거 |
|---|---|---|
| 메시지 큐 | 미도입 | 순차 실행이 확정(Q6=A)이고 생산자·소비자 분리가 필요 없습니다. 청크 목록 자체가 작업 큐 역할을 하며 체크포인트가 그 진행 상태입니다 |
| 워커 풀 / 스레드 풀 | 미도입 | 병렬 실행이 명시적 범위 밖입니다. 클러스터 부하를 줄이려 하루씩 쪼갠 것(C-3)이므로 병렬화는 목적에 반합니다 |
| 서킷 브레이커 | 미도입 | 대상 서비스가 하나이고 하루 한 번 실행됩니다. 브레이커가 열려도 다음 실행은 24시간 뒤이며, 그 사이 상태를 유지할 프로세스가 없습니다. 실패는 체크포인트에 남아 다음 날 재시도됩니다 |
| 캐시 | 미도입 | 같은 창을 두 번 조회하지 않습니다. 재조회를 막는 장치는 체크포인트 하나로 충분합니다 |
| 레이트 리미터 | 미도입 | 순차 실행 자체가 동시성 1의 레이트 리밋입니다. 추가 조절이 필요하면 `batch_size` 를 낮춥니다 |
| 데드레터 큐 | 미도입 | 실패한 청크는 사라지지 않고 체크포인트에 `failed` 로 남아 다음 실행에서 재시도됩니다. 별도 저장소가 필요 없습니다 |
| 메트릭 수집기 (Prometheus 등) | 미도입 | 제약 C4 — 파일도 로그도 반출할 수 없습니다. 회수 채널은 화면의 RUN SUMMARY 하나뿐이며, 메트릭 엔드포인트는 운영 환경에서 아무도 조회하지 않습니다 |
| 구조화 로깅 (structlog) | 미도입 | 위와 같은 이유. 로그 수집 시스템이 없는 환경이라 JSON 로그의 이점이 없고 의존성만 늘어납니다 |

**공통 근거**: 이 도구는 하루 한 번 도는 단일 프로세스 배치이고, 결과는 화면과 로컬 파일뿐입니다.
분산 시스템 패턴을 얹으면 운영 환경에서 진단할 수 없는 실패 모드만 늘어납니다.

---

## 5. 컴포넌트 간 계약

| 계약 | 내용 | 위반 시 |
|---|---|---|
| `writer.write()` 완료 -> `checkpoint.mark_done()` | **이 순서는 뒤집을 수 없다** (BR-E08) | "완료 기록은 있는데 파일은 없음". 재개가 그 청크를 영원히 건너뜀 |
| `load.iter_documents()` 는 `closing()` 으로 감싼다 | P-4 | scroll 컨텍스트 누수. 조용히 클러스터 부하 |
| `converter` 는 체크포인트를 읽지도 쓰지도 않는다 | BR-K07 | 변환 재실행이 추출 상태를 오염 |
| `report.render()` 는 stdout, 나머지는 stderr | NFR-O02 | `> summary.txt` 가 빈 파일이 됨 |
| `config` 외의 모듈은 `configs/env.yaml` 을 읽지 않는다 | P-11 | 시크릿 로딩 지점이 흩어져 마스킹 누락 |
| `src/` 는 `tools/` 를 import 하지 않는다 | 규약 §1.4 | 운영 환경에서 ImportError |

---

## 6. 확장 규칙 준수 요약 (Extension Compliance)

| 규칙 | 상태 | 근거 |
|---|---|---|
| PBT-01~08, 10 | 사전 식별됨 | 순수 로직 컴포넌트(`chunker`, `converter`, `schema`)가 속성 테스트 대상이며 NFR 패턴을 갖지 않는 것과 일치합니다 |
| PBT-09 | ✅ 충족 | `hypothesis` (NFR Requirements 단계) |
| Security Baseline | N/A | 옵트아웃 (Q12=B) |
| Resiliency Baseline | N/A | 옵트아웃 (Q13=B) |

**차단성 발견 사항(Blocking findings): 없음.**
