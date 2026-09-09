#!/usr/bin/env python3
"""진입점.

    python src/run.py --config configs/env.yaml
    python src/run.py --config configs/env.yaml --from 2026-09-01T18:00 --to 2026-09-06T18:00
    python src/run.py --dry-run

파일을 직접 실행하면 sys.path[0] 이 src/ 가 되므로 es_crawler 가 그대로 import 된다.
PYTHONPATH 도, 공용 venv 에 대한 설치도 필요 없다 — 공용 venv 에 이 패키지를 남기지
않아야 디렉터리를 통째로 갈아끼워도 아무 뒤처리가 없다.

이 파일이 하는 일은 둘뿐이다: venv 를 갈아타는 것과 본체로 넘기는 것.
나머지는 전부 es_crawler/ 안에 있다.
"""

import os
import sys
from pathlib import Path

_SWITCH_FLAG = "_ES_CRAWLER_VENV_SWITCHED"


def _config_path(argv: list[str]) -> str:
    """--config 를 argparse 전에 훔쳐본다. venv 를 갈아타려면 파싱보다 먼저다."""
    for i, arg in enumerate(argv):
        if arg == "--config" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--config="):
            return arg.split("=", 1)[1]
    return ""


def _peek_venv(config: str) -> str:
    """설정에서 paths.venv 만 뽑는다.

    의존성을 늘리지 않으려고 손으로 읽는다 — 2칸 들여쓰기 매핑을 가정하며,
    이 한 키를 보려고 PyYAML 을 requirements.txt 에 넣을 이유가 없다.
    갈아타기는 의존성이 설치되기 전에도 일어나야 하므로 여기서는 import 를 늘리지 않는다.
    """
    try:
        text = Path(config).expanduser().read_text(encoding="utf-8")
    except OSError:
        return ""

    in_paths = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[:1].isspace():
            in_paths = line.split(":")[0].strip() == "paths"
            continue
        if in_paths and line.strip().split(":")[0].strip() == "venv":
            value = line.split(":", 1)[1].split("#")[0].strip().strip("\"'")
            return "" if value in ("", "null", "~") else value
    return ""


def switch_venv(argv: list[str]) -> None:
    """설정에 적은 파이썬으로 갈아타고 같은 명령을 다시 시작한다.

    venv 가 여럿인 환경에서는 activate 를 잊거나 다른 것을 켠 채로 도는 일이
    흔하고, 그건 실패가 아니라 다른 결과로 나타난다.

    적어만 두고 쓰지 않으면 "설정했는데 무시된다"가 된다 — 설정 파일의 값이
    아무것도 바꾸지 않는 것은 그 자체로 결함이다.

    exec 라 이 프로세스가 그대로 대체된다. 인자와 cwd 가 보존되고, 아직 아무 계산도
    하지 않았으므로 잃을 것이 없다.
    """
    if os.environ.get(_SWITCH_FLAG):
        return
    config = _config_path(argv)
    want = _peek_venv(config) if config else ""
    if not want:
        return

    venv = Path(want).expanduser()
    if venv.resolve() == Path(sys.prefix).resolve():
        return

    for python in (venv / "bin" / "python", venv / "Scripts" / "python.exe"):
        if python.exists():
            break
    else:
        print(
            f"설정({config})의 paths.venv 에 파이썬이 없습니다: {venv}\n"
            f"  경로를 고치거나, paths.venv 를 비우고 그 venv 를 activate 한 뒤 "
            f"실행하세요.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    print(f"[venv] {sys.prefix}\n    -> {venv}   (설정 paths.venv)", file=sys.stderr)
    os.environ[_SWITCH_FLAG] = "1"
    os.execv(str(python), [str(python), *sys.argv])


if __name__ == "__main__":
    switch_venv(sys.argv[1:])

    from es_crawler.__main__ import main

    raise SystemExit(main())
