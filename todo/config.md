# `configs/env.yaml`

## 어디에 두나

작업 폴더의 루트다. **코드 폴더 안에 두지 마라** — 코드는 갱신할 때 통째로
지워졌다 다시 생기므로, 그 안에 둔 설정은 다음 갱신에서 사라진다.

```
작업폴더/
  configs/env.yaml      <- 여기
  outputs/
  run_daily.sh
  <코드폴더>/            <- 통째로 교체된다
```

## 만드는 법

코드 폴더의 `configs/env.example.yaml` 을 복사해서 값을 채운다.

```bash
mkdir -p configs
cp <코드폴더>/configs/env.example.yaml configs/env.yaml
chmod 600 configs/env.yaml
```

## 채워야 하는 값

| 키 | 무엇 | 비우면 |
|---|---|---|
| `paths.venv` | 쓸 파이썬 환경의 경로 | 지금 켜져 있는 것으로 돈다 |
| `elasticsearch.hosts` | 클러스터 주소 목록 | 시작하지 못한다 |
| `elasticsearch.api_key` | API Key | 시작하지 못한다 |
| `elasticsearch.ca_certs` | 자체 서명 인증서를 쓸 때만 | 시스템 인증서를 쓴다 |
| `elasticsearch.verify_certs` | 인증서를 검증할지. 예시 파일은 `false` 다 | 검증한다 |
| `query.index` | 조회할 인덱스. 와일드카드 가능 | 시작하지 못한다 |
| `query.time_field` | 시간 범위를 걸 필드 이름 | 시작하지 못한다 |
| `output.columns` | CSV 로 뽑을 필드와 그 헤더 이름 | 시작하지 못한다 |
| `output.directory` | 결과를 쌓을 곳. 상대 경로는 실행 위치 기준 | `outputs` |

## 확인

```bash
python <코드폴더>/src/run.py --config configs/env.yaml --only extract
```

값이 잘못됐으면 **아무것도 조회하지 않고** 종료 코드 `2` 로 죽는다. 무엇이 잘못됐는지는
화면에 한 줄로 나온다.

## 주의

- 이 파일은 커밋되지 않는다. 코드 폴더의 `.gitignore` 가 `configs/*.yaml` 을 통째로 막는다
- API Key 는 화면에도 로그에도 찍히지 않는다. 실행 인자로 넘길 방법도 일부러 두지 않았다
- `chunk.chunk_hours` 를 24 보다 크게 적으면 **시작하지 않는다**. 한 번의 조회가 덮는
  시간 폭에 상한이 있기 때문이다
