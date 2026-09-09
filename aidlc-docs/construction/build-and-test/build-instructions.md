# 빌드 지침 (Build Instructions)

**단위(Unit)**: `es-crawler`
**작성일**: 2026-09-09

> 컴파일 단계가 없는 Python 프로젝트입니다. "빌드"는 **환경 구성 + 정적 검사 + 이식 표면 확인**을 뜻합니다.

---

## 1. 사전 요구사항

| 항목 | 값 | 확인 |
|---|---|---|
| Python | **3.14** 이상 | `python3.14 -V` |
| 패키지 설치 | 하지 않음 | `python src/run.py` 가 `sys.path[0]` 을 `src/` 로 잡는다 |
| git | 태그·archive 를 쓰므로 필요 | `git --version` |
| 디스크 | 하루치 JSONL + CSV. 10만 건 기준 약 20MB, 100만 건 기준 약 200MB | — |
| 네트워크 | 의존성 설치 시에만 (PyPI) | — |

**환경변수 없음.** 접속 정보와 경로는 전부 `configs/env.yaml` 로 들어갑니다.

---

## 2. 빌드 단계

### 2.1 가상환경 생성

```bash
cd /Users/junho/coding_work/es_api
python3.14 -m venv .venv
```

### 2.2 의존성 설치

```bash
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

**기대 출력**: 오류 없이 종료. 설치되는 것은 아래와 같습니다.

```
elasticsearch==8.19.3      elastic-transport==8.19.0
PyYAML==6.0.3              pytest==9.1.1
hypothesis==6.168.0        ruff==0.16.6
mypy==2.3.1                types-PyYAML==6.0.12.20260906
```

### 2.3 설치 검증

```bash
.venv/bin/pip check
.venv/bin/python -c "import elasticsearch, yaml, hypothesis; print(elasticsearch.__versionstr__)"
```

**기대 출력**: `8.19.3`

### 2.4 정적 검사

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/mypy
```

**기대 출력**

```
All checks passed!
21 files already formatted
Success: no issues found in 12 source files
```

### 2.5 동작 확인 (클러스터 없이)

```bash
.venv/bin/python src/run.py --dry-run --rows 2000
```

**기대 출력**: `status : OK`, 종료 코드 `0`

```bash
.venv/bin/python src/run.py --dry-run --rows 2000 --adversarial
echo $?
```

**기대 출력**: `status : SCHEMA MISMATCH`, 종료 코드 `1`
어긋난 문서를 섞어 넣었을 때 그것이 화면에 드러나는지 확인하는 단계입니다.

---

## 3. 산출물

컴파일 산출물은 없습니다. 빌드가 만드는 것은 `.venv/` 뿐이며, 이는 이식되지 않습니다.

실행이 만드는 산출물:

| 경로 | 내용 |
|---|---|
| `{output.directory}/data-<끝시각>.jsonl` | 받은 문서 원본 |
| `{output.directory}/data-<끝시각>.csv` | 설정한 컬럼만 |
| `{output.directory}/.checkpoint.json` | 구간별 진행 상태 |

---

## 4. 이식 표면 확인 (릴리스 게이트)

**태그를 내기 전에 반드시 통과해야 합니다.**

### 4.1 archive 내용 확인

```bash
git add -A
TREE=$(git write-tree)
git archive "$TREE" | tar t
git reset
```

**기대**: 29개 파일. 아래가 **하나도 없어야** 합니다.

```
aidlc-docs/          .aidlc-rule-details/   README.md
requirements-dev.txt ruff.toml              mypy.ini
CLAUDE.md            .gitattributes         scripts/sync.sh
.venv/               outputs/               configs/env.yaml
```

### 4.2 내용 검사

```bash
# 개인 머신 절대 경로
grep -rnE "/Users/|/home/[a-z]" src tests configs docs TODO.md todo

# 이메일
grep -rnE "[a-zA-Z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" src tests configs docs TODO.md todo

# src 안의 외부 API 호출
grep -rnE "anthropic|openai|requests\.|httpx" src
```

**기대**: 셋 다 출력 없음.

### 4.3 preflight

```bash
git tag v1.0.0
bash scripts/sync.sh v1.0.0
```

**기대**: 통과. 실패하면 태그를 지우고(`git tag -d v1.0.0`) 원인을 고친 뒤 다시 냅니다.
`sync.sh` 는 위 4.1·4.2 의 검사를 기계적으로 한 번 더 수행합니다.

---

## 5. 문제 해결

### `python3.14: command not found`

```bash
brew install python@3.14
```

3.14 를 쓰는 이유는 실행 환경과 같은 버전에서 미리 확인하기 위함입니다.
3.13 으로 내리면 3.14 wheel 이 없는 패키지를 여기서 걸러내지 못합니다.

### `pip install` 이 특정 패키지에서 실패

3.14 wheel 이 아직 없는 패키지입니다. **버전을 낮추지 말고** 그 사실을 기록한 뒤
`requirements.txt` 에서 해당 패키지의 고정 버전을 3.14 를 지원하는 것으로 올립니다.
버전 범위(`>=`)로 푸는 것은 규약이 금지합니다 — 어디서 돌리든 같은 버전이어야 합니다.

### `ModuleNotFoundError: No module named 'es_crawler'`

`src/run.py` 를 **경로째로** 실행해야 합니다.

```bash
python src/run.py --dry-run          # 맞다
cd src && python run.py --dry-run    # 이것도 맞다
python -m es_crawler                 # 틀리다. sys.path 에 src/ 가 없다
```

### `mypy` 가 `Library stubs not installed for "yaml"`

```bash
.venv/bin/pip install -r requirements-dev.txt
```

`types-PyYAML` 이 개발 의존성에 들어 있습니다. 운영 의존성에는 넣지 않습니다 —
타입 스텁은 실행에 필요 없습니다.

### `ruff format --check` 가 재포맷을 요구

```bash
.venv/bin/ruff format src tests
```

### 빌드는 되는데 `--dry-run` 이 `SCHEMA MISMATCH` 로 끝난다

`--adversarial` 없이 그렇다면 `schema.py` 의 `INPUT_SCHEMA` 와 `synth.py` 가
어긋난 것입니다. 둘 중 하나가 틀렸으니 스키마를 먼저 확인하십시오.
