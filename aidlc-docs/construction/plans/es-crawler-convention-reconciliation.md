# 규약 정합성 질문 — `es-crawler`

**단계**: CONSTRUCTION - NFR Requirements
**사유**: `/Users/junho/coding_work/general_implementation` 규약과 기존 확정 결정의 충돌

---

## ✅ NFR 답변 확정

| # | 결정 |
|---|---|
| Q1=B | Python 3.12 이상 |
| Q2=A | `pyproject.toml` + `pip install -e .`, 프로젝트 폴더 안에 자체 venv |
| Q3=A | `elasticsearch>=8.15,<9` |
| Q4=C | 하루 10만 ~ 100만 건 (추정) |
| Q5=A | 재시도 3회 + 타임아웃 60초 |
| Q6=A | pytest + hypothesis, 커버리지 수치 목표 없음 — **PBT-09 충족** |
| Q7=A | ruff + mypy |
| Q8=A | stdout만 |
| Q9=A | 보관 정책 없음 (범위 밖) |

---

## 📖 규약 요약

`general_implementation`은 **개발 장비와 운영 환경이 분리된 상황**을 코드 구조로 강제하는 스캐폴드입니다.

| 제약 | 내용 |
|---|---|
| C1·C2 | 이식은 개발→운영 단방향. 운영 환경에서 코드 수정 불가 |
| C3 | 운영 실데이터는 밖으로 나올 수 없다 |
| C4 | 파일·문서 반출 불가. **결과 파일도 로그도 못 가져온다** |
| C5 | 회수 가능한 것은 입력 데이터의 **포맷**과 사람의 **인사이트** 둘뿐 |
| C7 | 운영 환경은 Python **3.14** + 기존 공용 venv |
| C8 | 운영 환경에서 LLM·외부 API 사용 불가 |
| C9 | 사본은 평범한 프로그램으로 보여야 한다 |

**구조 규칙**

```
src/run.py                    진입점. venv 갈아타기 + 위임만
src/<pkg>/__main__.py         CLI 인자, 실행 순서, 종료 코드
src/<pkg>/schema.py           입력 스키마 (단일 출처)
src/<pkg>/synth.py            스키마에서 가짜 데이터 생성 (파일 픽스처 금지)
src/<pkg>/load.py             입력 포맷을 아는 유일한 곳
src/<pkg>/report.py           RUN SUMMARY
src/<pkg>/pipeline.py         기능 코드
requirements.txt              운영 의존성, 버전 완전 고정
requirements-dev.txt          개발 전용 (이식 제외)
configs/env.example.yaml      설정 예시. 실값은 운영 환경에만
```

---

## 🔀 규약을 따르기로 자동 확정한 것 (질문 없음)

사용자가 "규약을 준수하는 방식으로"라고 지시했으므로, 아래는 규약을 우선 적용합니다.

| 항목 | 기존 결정 | 규약 적용 후 |
|---|---|---|
| 패키징 | Q2=A `pip install -e .` | **설치 없음.** `python src/run.py` 가 `sys.path[0]` 을 `src/` 로 잡아 패키지를 import (C7 — 공용 venv에 패키지를 남기지 않아야 통째 교체가 무연산). 프로젝트 자체 venv는 그대로 만듭니다 |
| 버전 핀 | Q3=A `>=8.15,<9` | **완전 고정** — `elasticsearch==8.15.1` 형태 |
| 모듈 배치 | Application Design Q1=A 9개 모듈 | 규약의 공유 모듈(`schema` `load` `synth` `report` `pipeline` `__main__`) + 우리 고유 모듈(`chunker` `writer` `converter` `checkpoint` `config`) |
| 리포트 | 설계에 없었음 | **RUN SUMMARY 블록 추가** (§3.2). 파일 산출물과 별개로 화면 요약이 회수 채널 |
| 종료 코드 | BR-X01~08 (0/1/2) | **그대로 유지** — 규약의 0/1/2 와 "계산을 시작했나" 기준이 정확히 일치 |
| 테스트 픽스처 | 미정 | **파일 금지.** `synth.generate()` 로 가짜 ES 히트를 런타임 생성. hypothesis와 잘 맞음 |
| 개발 도구 | ruff, mypy | `requirements-dev.txt` 에 두고 `export-ignore` |

---

## ✅ 결정 완료 (사용자 지시: 규약 우선)

**답변 방법**: `[Answer]:` 뒤에 알파벳을 적어주세요.

---

## Question 1 — 이식 모델을 실제로 적용하나요? ⚠️ 나머지 답을 좌우합니다

규약 전체가 "개발 장비에서는 실데이터·실클러스터에 접근할 수 없다"는 전제 위에 있습니다.

A) **완전히 적용** — Elasticsearch 클러스터가 운영 환경에 있고 개발 장비에서는 접근 불가.
   `sync.sh` 로 태그를 내어 이식하고, 개발 중에는 `synth.py` 의 가짜 히트로만 테스트.
   `TODO.md`, `configs/env.example.yaml`, `.gitattributes` 전부 갖춤

B) **구조만 차용** — 이식은 하지 않지만 파일 배치·단일 진입점·RUN SUMMARY·설정 분리 등
   **코드 구조 규약만** 따름. 개발 장비에서 실제 클러스터에 붙어 테스트 가능

C) **아직 미정** — 일단 B로 만들고, 나중에 이식이 필요해지면 A로 승격

X) Other (아래 [Answer]: A  (사용자 지시: "general_implementation의 규약이 다른 모든 규약보다 우선" — 규약 자체가 이식 모델이므로 완전 적용)뒤에 직접 설명해 주세요)

[Answer]: 

---

## Question 2 — Python 버전
Q1에서 3.12를 고르셨지만, 규약의 C7은 **운영 환경이 3.14**이고 개발 장비도 3.14를 쓰라고 합니다
(3.14 wheel이 없는 패키지를 미리 거르기 위함).

A) **3.14** — 규약을 따름. 운영 환경과 동일

B) **3.12** — 기존 답변 유지. 이식하지 않는다면 3.14를 강제할 이유가 없음

X) Other (아래 [Answer]: A  (C7: 3.14)뒤에 직접 설명해 주세요)

[Answer]: 

---

## Question 3 — `extract` / `convert` 를 어떻게 실행할까요? ⚠️ 기존 결정과 충돌

기존 결정은 **CLI 서브커맨드 2개**(Application Design Q2=B)이고,
스케줄러가 `extract && convert` 로 이어 실행합니다(D-4).

규약은 이를 금지합니다.
- **하지 말 것 #12**: "기능마다 진입점 두기 — 리포트가 여러 장으로 갈라지고, C4 때문에 합칠 수 없다"
- **§3.2**: "한 번 실행에 RUN SUMMARY 는 하나"

두 번 실행하면 RUN SUMMARY가 두 장 나오고, 파일로 못 꺼내므로 합치는 일이 사람 머릿속에서 일어납니다.

A) **한 번 실행으로 통합** — `python src/run.py --from ... --to ...` 가 추출과 변환을 모두 수행하고
   RUN SUMMARY 한 장. 개발용 보조 인자로 `--only extract` / `--only convert` 를 둠
   (규약이 "보조 진입점은 둬도 되지만 기본 실행은 전부 한 번에"라고 명시)
   → **Application Design Q2=B와 Q3=B, D-3, D-4를 이 방향으로 수정**

B) **기존 결정 유지** — 서브커맨드 2개, 스케줄러가 두 번 호출. RUN SUMMARY도 두 장
   (규약 #12 위반을 감수)

X) Other (아래 [Answer]: A  (하지 말 것 #12 및 §3.2 우선. Application Design Q2=B, D-3, D-4 수정)뒤에 직접 설명해 주세요)

[Answer]: 

---

## Question 4 — 설정 파일 구성
기존 설계는 `config.yaml`(구조 설정) + `.env`(시크릿) 두 파일입니다.
규약은 `configs/env.yaml` 하나를 쓰고, 그 안에 `paths.venv` 를 두어 진입점이 venv를 갈아탑니다.
`.gitignore` 는 `configs/*.yaml` 을 통째로 막고 `env.example.yaml` 만 예외로 둡니다.

A) **규약대로 `configs/env.yaml` 하나** — ES 접속 정보·API Key·인덱스·컬럼 매핑·`paths.venv` 를
   한 파일에. `.env` 를 쓰지 않음. 실값 파일은 커밋되지 않음
   (기존 NFR-6의 "시크릿은 `.env`에만"을 이 방향으로 수정)

B) **`configs/env.yaml` + `.env` 병행** — 구조 설정은 YAML, 시크릿만 `.env`.
   규약의 `.gitignore` 도 `.env` 를 막고 있어 양쪽 다 안전

X) Other (아래 [Answer]: A  (configs/env.yaml 단일 파일)뒤에 직접 설명해 주세요)

[Answer]: 

---

## Question 5 — 패키지 이름
규약의 기본 패키지 이름은 `core` 이고, `adopt.sh` 둘째 인자로 바꿀 수 있습니다.

A) **`es_crawler`** — 무엇을 하는지 이름에서 드러남

B) **`core`** — 규약 기본값. C9(사본은 평범한 프로그램으로 보여야 한다) 관점에서 중립적

X) Other (아래 [Answer]: A `es_crawler`  (규약이 adopt.sh 둘째 인자로 개명을 명시 허용하므로 충돌 아님. C9 위배도 아님 — 워크플로가 아니라 기능을 가리키는 평범한 이름)뒤에 직접 설명해 주세요)

[Answer]: 

---
