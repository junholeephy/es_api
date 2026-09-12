"""실행 흐름.

진입점은 src/run.py 지만 본체는 여기다 — 저쪽은 venv 를 갈아타고 이리로 넘긴다.

바뀔 만한 값은 전부 인자나 설정으로 받는다. 실행할 때 코드를 고칠 수 없다고 보므로,
"한 줄만 고치면 되는데" 하는 순간이 오면 그건 이 규칙이 이미 깨졌다는 신호다.

종료 코드 — 실행 스크립트가 여기에 분기한다:
    0  정상
    1  돌았지만 온전치 않다 (형태 어긋남, 실패한 구간). 재시도해도 같다
    2  시작도 못 했다 (인자 누락·설정 오류·접속 실패). 고치고 다시 돌린다
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from .chunker import parse_boundary
from .config import Config, ConfigError, build_config, load_config
from .schema import INPUT_SCHEMA


def read_version() -> str:
    """저장소 루트의 VERSION 에 적힌 값. 없으면 unversioned."""
    path = Path(__file__).resolve().parent.parent.parent / "VERSION"
    try:
        return path.read_text(encoding="utf-8").strip() or "unversioned"
    except OSError:
        return "unversioned"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run.py",
        description="Elasticsearch 에서 구간별로 문서를 받아 JSONL 로 남긴다.",
    )
    ap.add_argument("--config", help="설정 파일 경로. --dry-run 이 아니면 필수")
    ap.add_argument(
        "--from",
        dest="start",
        help="시작 시각. 시각까지 적는다 (예: 2026-09-01T18:00)",
    )
    ap.add_argument("--to", dest="end", help="종료 시각. 이 시각은 포함하지 않는다")
    ap.add_argument(
        "--only",
        choices=("extract", "convert"),
        help="convert 를 주면 받아둔 JSONL 을 CSV 로만 바꾼다. 기본은 JSONL 로 남기는 것까지",
    )
    ap.add_argument("--dry-run", action="store_true", help="합성 문서로 전 구간 스모크")
    ap.add_argument("--rows", type=int, default=1000, help="--dry-run 이 생성할 문서 수")
    ap.add_argument("--seed", type=int, default=0, help="--dry-run 생성 시드")
    ap.add_argument("--adversarial", action="store_true", help="--dry-run 에 사고 유형 주입")
    ap.add_argument("--log-level", default="INFO", help="DEBUG / INFO / WARNING")
    return ap


def _resolve_bounds(
    args: argparse.Namespace, config: Config
) -> tuple[datetime | None, datetime | None]:
    """--from / --to 를 해석한다. 둘 다 주거나 둘 다 빼야 한다."""
    if (args.start is None) != (args.end is None):
        raise ValueError("--from and --to must be given together, or both omitted")
    if args.start is None:
        return None, None
    tz = config.chunk.tz
    return parse_boundary(args.start, tz), parse_boundary(args.end, tz)


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    raw_args = " ".join(argv if argv is not None else sys.argv[1:]) or "(none)"

    # 진행 상황은 stderr. 요약이 stdout 이라야 `> summary.txt` 가 비지 않는다.
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stderr,
    )

    # 조기 실패 — 어떤 조회도 하기 전에 죽는다. 30분 돌린 뒤 인자 하나 때문에
    # 죽으면 그 실행을 통째로 버리게 된다.
    if not args.dry_run and not args.config:
        ap.error("--config is required unless --dry-run")

    tempdir = None
    try:
        if args.dry_run:
            from tempfile import TemporaryDirectory

            from .synth import FakeSearchClient, dry_run_config, generate

            tempdir = TemporaryDirectory(prefix="es-crawler-dry-run-")
            config = build_config(dry_run_config(tempdir.name))
            mode = "adversarial" if args.adversarial else "normal"
            client = FakeSearchClient(generate(args.rows, seed=args.seed, mode=mode))
            print(
                f"실행 조건: synthetic(n={args.rows}, seed={args.seed}, mode={mode}) "
                f"-> {tempdir.name}",
                file=sys.stderr,
            )
        else:
            config, client = load_config(args.config), None
        start, end = _resolve_bounds(args, config)
    except (ConfigError, ValueError) as exc:
        print(f"{exc}", file=sys.stderr)
        if tempdir is not None:
            tempdir.cleanup()
        return 2

    from .checkpoint import CheckpointError
    from .pipeline import CrawlService, process_data
    from .report import peak_gb, render, status_for

    started = time.perf_counter()
    service = CrawlService(config, client=client)

    try:
        # 기본은 받아서 JSONL 로 남기는 것까지다. CSV 로 바꾸는 것은 --only convert
        # 로 따로 돌린다 — 받아오는 일과 정리하는 일은 실패 조건이 다르고,
        # 정리 규칙이 바뀌어도 이미 받아둔 문서를 다시 조회할 이유는 없다.
        if args.only == "convert":
            extract, convert, windows = service.convert_only(start, end)
        else:
            extract, convert, windows = service.extract_only(start, end)
        converted = args.only == "convert"
    except CheckpointError as exc:
        print(f"{exc}", file=sys.stderr)
        return 2
    except (ConfigError, ValueError) as exc:
        print(f"{exc}", file=sys.stderr)
        return 2
    finally:
        if tempdir is not None:
            tempdir.cleanup()

    schema = service.schema_report
    stage = convert if converted else extract
    failed = extract.failed + convert.failed
    status = status_for(schema_ok=schema.ok, chunks_failed=failed)

    window_text = f"{windows[0].start.isoformat()} .. {windows[-1].end.isoformat()}"
    print(
        render(
            version=read_version(),
            args=raw_args,
            window=window_text,
            n_chunks=len(windows),
            schema_violations=schema.violations,
            schema_notes=schema.notes,
            schema_fields=len(INPUT_SCHEMA),
            schema_sampled=schema.sampled,
            schema_total=service.schema_total,
            # 돌린 단계의 결과를 센다. convert 만 돌렸는데 extract 쪽 0 을 찍으면
            # 한 구간도 처리하지 못한 것처럼 읽힌다.
            counts={
                "done": stage.succeeded,
                "failed": failed,
                "skipped": stage.skipped,
            },
            # 뽑은 히트를 보는 기능들. 기능이 없어도 표본 건수는 찍는다.
            metrics=process_data(service.schema_sample),
            extracted_docs=None if converted else extract.total_documents,
            extracted_files=None if converted else extract.succeeded,
            converted_rows=convert.total_documents if converted else None,
            converted_files=convert.succeeded if converted else None,
            runtime_s=time.perf_counter() - started,
            peak_gb=peak_gb(),
            status=status,
        )
    )
    return 0 if status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
