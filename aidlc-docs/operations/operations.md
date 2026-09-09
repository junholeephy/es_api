# OPERATIONS 단계

**상태**: **플레이스홀더**
**작성일**: 2026-09-09

---

## 이 단계에 대해

AI-DLC 워크플로에서 OPERATIONS 는 현재 플레이스홀더이며, 향후 배포·모니터링·장애 대응
워크플로가 들어올 자리입니다. 빌드와 테스트는 전부 CONSTRUCTION 단계에서 끝났습니다.

**따라서 이 프로젝트의 AI-DLC 워크플로는 Build and Test 승인으로 완료되었습니다.**

---

## 이 프로젝트에서 운영에 해당하는 것은 어디에 있나

플레이스홀더라고 해서 운영 관련 산출물이 없는 것은 아닙니다.
규약을 따랐기 때문에 그 내용이 **이식되는 문서** 안에 이미 들어 있습니다.

| 운영 주제 | 어디에 |
|---|---|
| 배포(이식) 절차 | `scripts/sync.sh` + `build-instructions.md` 4장 (릴리스 게이트) |
| 실행 환경 준비 | `TODO.md` + `todo/config.md` |
| 스케줄 등록 (매일 19:00 KST) | `todo/runner.md` |
| 실행 스크립트와 종료 코드 분기 | `todo/runner.md` |
| 산출물 격리 (`.gitignore`) | `todo/gitignore.md` |
| 관측 — 무엇을 보고 판단하나 | `docs/usage.md` "화면에 나오는 것" |
| 장애 판단 기준 | 종료 코드 `0`/`1`/`2` — `docs/usage.md`, `todo/runner.md` |
| 성능 조정 | `performance-test-instructions.md` 4~5장 |
| 통합 검증 | `integration-test-instructions.md` 시나리오 7종 |

이 구조가 규약의 요점입니다 — 운영 지식이 별도 문서로 남는 것이 아니라
**실행 환경으로 함께 건너가는 문서** 안에 있어야 합니다.

---

## 첫 운영 사이클에서 회수할 것

실제 데이터를 만나야 정해지는 것들입니다. 첫 실행의 RUN SUMMARY 를 보고
아래를 기록해 개발 쪽에 반영합니다.

| 화면에서 본 것 | 고칠 곳 |
|---|---|
| `schema` 줄의 위반 내용 (전문) | `src/es_crawler/schema.py` 의 `INPUT_SCHEMA`. `note` 에 확인된 사실도 남긴다 |
| 새로 나타난 데이터 사고 유형 | `src/es_crawler/synth.py` 의 `_corrupt()` — 그 유형을 생성 가능하게 |
| "설정에 없어서 코드를 고치고 싶었던 값" | `configs/env.example.yaml` — 그 값을 설정 항목으로 승격 |
| 의존성 충돌 메시지 | `requirements.txt` |
| 하루치 실제 문서 수, 소요 시간, 최대 메모리 | `configs/env.example.yaml` 의 `batch_size` · `chunk_hours` 기본값 |

**반영의 종착점은 문서가 아니라 테스트입니다.** 규칙으로 굳은 것은 테스트로 옮기고,
관찰 날짜와 규모를 독스트링에 남깁니다 — 그래야 그 테스트가 깨질 때 무엇을 근거로
만든 규칙이었는지가 함께 나옵니다.

```python
def test_prev_question_accepts_the_shape_the_real_index_uses():
    """실제 인덱스의 user.name 은 배열이다 (2026-09-10, 152,431건)."""
```

---

## 아직 하지 않은 것

| 항목 | 왜 |
|---|---|
| 커밋 및 태그 생성 | 사용자가 요청하지 않았다. 현재 커밋 0개 |
| `sync.sh` preflight 실행 | 태그가 있어야 돈다 |
| 통합 테스트 실행 | Elasticsearch 8.15.3 인스턴스가 필요하다 |
