# 어떻게 도는가

Elasticsearch 에서 정해진 시간 구간의 문서를 받아 **받은 그대로** 파일로 남긴다.

```
Elasticsearch  -->  data-<끝시각>.jsonl
                    받은 그대로
```

CSV 로 정리하는 것은 기본 실행에 들어있지 않다. 받아둔 뒤 따로 돌린다
(아래 [CSV 로 바꾸기](#csv-로-바꾸기)).

## 한 번 실행하면

1. 요청 구간을 **24시간 이하의 조각**으로 나눈다
2. 이미 끝난 조각은 건너뛴다
3. 남은 조각을 **하나씩 차례로** 받아 `.jsonl` 로 저장한다
4. 화면에 요약 한 장을 찍는다

한 번에 받는 양에 상한이 있어 조각으로 나눈다. 5일치를 요청하면 5번에 나눠 돈다.

## 하루의 경계는 자정이 아니다

기본 설정에서 하루는 **18:00 부터 다음 날 18:00 까지**(`chunk.anchor_time`)다.
그래서 날짜만으로는 어느 구간인지 정해지지 않고, 범위를 직접 줄 때는 시각까지 적어야 한다.

```bash
python src/run.py --config configs/env.yaml --from 2026-09-01T18:00 --to 2026-09-06T18:00
```

인자를 주지 않으면 **직전에 끝난 하루**를 가져온다. 19:00 에 실행하면 전날 18:00 부터
당일 18:00 까지다.

## 시간 외의 조건 걸기

`query.extra_filters` 에 Elasticsearch query DSL 절을 그대로 적는다. 시간 범위 뒤에
이어 붙고 전부 AND 로 묶인다.

```yaml
query:
  extra_filters:
    - exists: { field: "user.name" }     # 이 필드를 가진 문서만
    - term:   { level: "ERROR" }         # 값이 일치하는 문서만
```

없는 문서만 받으려면 뒤집는다.

```yaml
query:
  extra_filters:
    - bool:
        must_not:
          - exists: { field: "user.name" }
```

**`exists` 는 색인 여부를 본다.** JSON 에 그 키가 있는지가 아니다. 값이 `null` 이거나
빈 배열이면 색인되지 않으므로 `exists` 에서 빠진다 — `"user": {"name": null}` 인 문서는
잡히지 않는다. 매핑에 `null_value` 가 걸려 있으면 반대로 잡힌다.

필터를 걸지 않으면 필드가 없는 문서도 그대로 받아온다. CSV 에서는 `missing_value`
(기본은 빈 칸)로 찍혀 값이 `null` 인 경우(`null_value`, 기본 `NULL`)와 구별된다.
이 구분이 필요해서 두 값을 따로 둔 것이다.

## 파일 이름

```
data-2026-09-09T180000+0900.jsonl
```

구간의 **끝 시각**이 이름이 된다. CSV 로 바꾸면 확장자만 다른 같은 이름이 된다. 날짜만 쓰면 조각이 하루보다 짧을 때 같은 이름이
겹쳐 조용히 덮어쓴다.

## 중단되면

진행 상태가 `outputs/.checkpoint.json` 에 쌓인다. 다시 실행하면 끝난 조각은 건너뛰고
남은 것부터 이어서 돈다. 실패한 조각은 다음 실행에서 자동으로 다시 시도한다.

이 파일을 지우면 처음부터 다시 받는다. 파일이 깨져 읽을 수 없으면 **시작하지 않는다** —
조용히 전부 다시 받는 것보다 멈추는 편이 낫기 때문이다.

## 화면에 나오는 것

```
=============================================
                 RUN SUMMARY
=============================================
version   : v1.0.0
args      : --config configs/env.yaml
window    : 2026-09-08T18:00:00+09:00 .. 2026-09-09T18:00:00+09:00 (1 chunk)
schema    : 2 ok / 1 MISMATCH   (sampled 1,000 of 152,431 in first chunk)
  - user.name           : 812 docs missing this field
chunks    :
  done             1
  failed           0
  skipped          0
extract   : 152,431 docs -> 1 jsonl
runtime   : 412.3s, peak 0.31GB
status    : OK
=============================================
```

| 줄 | 읽는 법 |
|---|---|
| `args` | 이 실행을 재현하려면 이 한 줄이면 된다 |
| `window` | 실제로 조회한 구간과 조각 수 |
| `schema` | 문서의 형태가 `schema.py` 의 선언과 다른 부분. **표본이다** — 전수 검사가 아니다 |
| `chunks` | 조각별 결과. `failed` 가 0 이 아니면 그 구간의 파일은 아직 없다 |
| `metrics` | 받은 문서를 보고 낸 지표. 기능을 등록했을 때만 나오고, 분모는 **첫 조각의 표본**이다 |
| `status` | `OK` / `SCHEMA MISMATCH` / `CHUNKS FAILED` / 둘 다 |

`schema` 줄에 뜬 내용은 그대로 옮겨 적어 전달한다. 필드 이름과 건수만 나오고
값 자체는 찍지 않는다.

## 종료 코드

| 코드 | 뜻 |
|---|---|
| `0` | 정상 |
| `1` | 돌았지만 온전치 않다. 다시 돌려도 같다 |
| `2` | 시작도 못 했다. 설정이나 접속을 고치고 다시 |

`1` 은 두 가지 원인이 있다 — 형태가 어긋났거나, 조각이 실패했거나. `status` 줄이 구별해 준다.

## 접속하지 않고 확인하기

```bash
python src/run.py --dry-run
python src/run.py --dry-run --adversarial    # 어긋난 문서를 섞어 넣는다
```

합성 문서로 전 구간을 돈다. 클러스터도 설정 파일도 필요 없다. 여기서 실패하면 환경 문제다.

## CSV 로 바꾸기

```bash
python src/run.py --config configs/env.yaml --only convert
```

받아둔 `.jsonl` 을 `output.columns` 설정대로 `.csv` 로 정리한다. **클러스터에
접속하지 않는다** — 이미 파일로 있는 것만 읽는다. 그래서 CSV 규칙을 고쳤을 때
다시 돌려도 조회가 새로 일어나지 않는다.

구간은 기본 실행과 같은 방식으로 정해지므로, 어제치를 받아 바로 정리하려면
인자 없이 두 번 돌리면 된다.

```bash
python src/run.py --config configs/env.yaml
python src/run.py --config configs/env.yaml --only convert
```
