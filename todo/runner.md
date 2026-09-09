# 실행 스크립트

## 왜 필요한가

매일 도는 명령을 손으로 치면 언젠가 인자를 빠뜨린다. 그때 프로그램은 **죽지 않고
기본값으로 돈다** — 실패가 아니라 다른 결과가 나오고, 화면만 보면 알아채기 어렵다.

종료 코드도 마찬가지다. 사람이 눈으로만 보면 `1` 과 `2` 의 차이가 묻힌다.

| 코드 | 뜻 | 할 일 |
|---|---|---|
| `0` | 정상 | 다음으로 |
| `1` | 돌았지만 온전치 않다 (형태 어긋남, 실패한 구간) | 다시 돌려도 같다. 화면을 사람이 본다 |
| `2` | 시작도 못 했다 (설정·인자·접속) | 고치고 다시 돌린다 |

## 만드는 법

작업 폴더 루트에 `run_daily.sh` 를 만든다.

```bash
#!/usr/bin/env bash
set -uo pipefail

CODE_DIR="<코드폴더>"
CONFIG="configs/env.yaml"
LOG_DIR="logs"

mkdir -p "$LOG_DIR"
STAMP=$(date +%Y%m%d-%H%M%S)

python "$CODE_DIR/src/run.py" --config "$CONFIG" \
    > "$LOG_DIR/summary-$STAMP.txt" \
    2> "$LOG_DIR/progress-$STAMP.log"
CODE=$?

cat "$LOG_DIR/summary-$STAMP.txt"

case $CODE in
  0) echo "[run_daily] ok" ;;
  1) echo "[run_daily] 결과가 온전치 않다. summary-$STAMP.txt 를 확인하라" >&2 ;;
  2) echo "[run_daily] 시작하지 못했다. progress-$STAMP.log 를 확인하라" >&2 ;;
  *) echo "[run_daily] 예상 못 한 종료 코드 $CODE" >&2 ;;
esac
exit $CODE
```

```bash
chmod +x run_daily.sh
```

**요약과 진행 상황을 다른 파일로 가른다.** 요약은 표준 출력, 진행 상황은 표준 오류로
나온다. 한 파일에 섞으면 나중에 요약만 꺼내기 어렵다.

## 스케줄 등록

하루 한 번, **19:00** 에 돈다. 인자를 주지 않으면 **전날 18:00 부터 당일 18:00 까지**를
가져온다 — 실행 시각이 구간의 끝보다 한 시간 뒤라, 늦게 색인된 문서까지 들어온다.

```cron
0 19 * * *  cd /경로/작업폴더 && ./run_daily.sh
```

`cd` 를 빠뜨리지 마라. 설정과 출력 경로가 모두 실행 위치 기준이다.

## 지난 구간을 메울 때

며칠 밀렸으면 범위를 직접 준다. **날짜만으로는 안 되고 시각까지 적어야 한다** —
하루의 경계가 자정이 아니기 때문이다.

```bash
python "$CODE_DIR/src/run.py" --config configs/env.yaml \
    --from 2026-09-01T18:00 --to 2026-09-06T18:00
```

하루씩 나뉘어 차례로 돈다. 이미 끝난 구간은 건너뛴다.
