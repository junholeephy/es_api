# 작업 폴더의 `.gitignore`

## 왜 필요한가

이 폴더가 git 으로 관리된다면, 받아온 문서(`*.jsonl`)와 정리한 결과(`*.csv`)가
그대로 커밋될 수 있다. 코드 폴더 안의 `.gitignore` 는 **그 폴더 안에만** 적용되므로
바깥의 `outputs/` 를 막지 못한다.

## 만드는 법

작업 폴더 루트의 `.gitignore` 에 아래를 더한다. 파일이 없으면 새로 만든다.

```gitignore
# 받아온 문서와 정리한 결과
*.jsonl
*.csv
outputs/
logs/

# 접속 정보
configs/*.yaml
.env

# 코드 폴더는 갱신 때마다 통째로 교체된다
<코드폴더>/
```

## 확인

```bash
git status --short
```

`outputs/` 나 `configs/env.yaml` 이 목록에 보이면 아직 막히지 않은 것이다.

## 주의

막을 것을 **확장자와 폴더 단위로** 적는다. 파일 이름을 하나씩 나열하면 오타 한 번에
막이 풀리고, 그때 조용히 커밋된다.
