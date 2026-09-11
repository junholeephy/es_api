"""전 구간 스모크.

클러스터도 설정 파일도 없이 끝까지 돈다. 여기서 실패하면 환경 문제다.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from es_crawler.__main__ import main

RUN_PY = Path(__file__).resolve().parent.parent / "src" / "run.py"


def test_a_dry_run_finishes_cleanly(capsys):
    assert main(["--dry-run", "--rows", "500"]) == 0
    assert "RUN SUMMARY" in capsys.readouterr().out


def test_the_summary_goes_to_stdout_and_progress_to_stderr(capsys):
    """요약이 stderr 로 새면 `> summary.txt` 가 빈 파일이 된다."""
    main(["--dry-run", "--rows", "100"])
    captured = capsys.readouterr()

    assert "RUN SUMMARY" in captured.out
    assert "RUN SUMMARY" not in captured.err
    assert "실행 조건" in captured.err


def test_the_summary_reports_what_it_actually_did(capsys):
    main(["--dry-run", "--rows", "300"])
    out = capsys.readouterr().out

    assert "300 docs -> 1 jsonl" in out
    assert "status    : OK" in out


def test_the_default_run_stops_at_jsonl(capsys):
    """기본 실행은 CSV 를 만들지 않는다. 만들지 않은 단계를 0 으로 찍지도 않는다 —
    0 으로 찍으면 변환을 시도했다가 한 건도 못 만든 것처럼 읽힌다."""
    main(["--dry-run", "--rows", "100"])
    out = capsys.readouterr().out
    assert "100 docs -> 1 jsonl" in out
    assert "csv" not in out


def test_the_summary_says_the_check_was_a_sample(capsys):
    """표기가 없으면 한 건도 안 틀렸다로 읽힌다."""
    main(["--dry-run", "--rows", "3000"])
    assert "sampled 1,000 of 3,000" in capsys.readouterr().out


def test_the_run_arguments_are_written_down(capsys):
    """어떤 조건으로 돌렸는지가 화면에만 남는다."""
    main(["--dry-run", "--rows", "100", "--seed", "7"])
    assert "--dry-run --rows 100 --seed 7" in capsys.readouterr().out


def test_a_shape_mismatch_shows_up_and_changes_the_exit_code(capsys):
    assert main(["--dry-run", "--rows", "2000", "--adversarial"]) == 1
    out = capsys.readouterr().out
    assert "SCHEMA MISMATCH" in out
    assert "MISMATCH" in out


def test_a_missing_config_stops_before_anything_runs():
    """30분 돌린 뒤 인자 하나 때문에 죽으면 그 실행을 통째로 버린다."""
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2


def test_an_unreadable_config_stops_before_anything_runs(capsys):
    assert main(["--config", "/nonexistent/env.yaml"]) == 2
    assert "cannot read config" in capsys.readouterr().err


def test_one_boundary_without_the_other_is_refused(capsys):
    assert main(["--dry-run", "--from", "2026-09-01T18:00"]) == 2
    assert "together" in capsys.readouterr().err


def test_a_date_without_a_time_is_refused(capsys):
    assert main(["--dry-run", "--from", "2026-09-01", "--to", "2026-09-02"]) == 2
    assert "no time component" in capsys.readouterr().err


def test_an_explicit_span_is_split_into_chunks(capsys):
    main(["--dry-run", "--rows", "50", "--from", "2026-09-01T18:00", "--to", "2026-09-04T18:00"])
    assert "(3 chunks)" in capsys.readouterr().out


def test_only_extract_is_still_accepted(capsys):
    """이미 이 인자를 적어둔 실행 스크립트가 있다. 기본과 같은 뜻이 되었을 뿐이다."""
    main(["--dry-run", "--rows", "100", "--only", "extract"])
    assert "100 docs -> 1 jsonl" in capsys.readouterr().out


def test_asking_for_the_conversion_alone_says_nothing_about_extraction(capsys):
    """--only convert 는 조회하지 않는다. extract 줄이 0 으로 뜨면 받아오다
    실패한 것처럼 읽힌다."""
    main(["--dry-run", "--rows", "100", "--only", "convert"])
    out = capsys.readouterr().out
    assert "csv" in out
    assert "jsonl" not in out


def test_the_same_seed_gives_the_same_run(capsys):
    main(["--dry-run", "--rows", "200", "--seed", "3"])
    first = capsys.readouterr().out
    main(["--dry-run", "--rows", "200", "--seed", "3"])
    second = capsys.readouterr().out

    def without_timing(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not ln.startswith("runtime")]

    assert without_timing(first) == without_timing(second)


def test_the_entry_point_works_as_a_plain_script(tmp_path):
    """설치도 PYTHONPATH 도 없이 파일을 직접 실행할 수 있어야 한다."""
    result = subprocess.run(
        [sys.executable, str(RUN_PY), "--dry-run", "--rows", "50"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "RUN SUMMARY" in result.stdout


def test_the_output_files_are_usable(tmp_path, monkeypatch):
    """만들어진 파일이 실제로 읽히는지 본다."""
    from es_crawler.config import build_config
    from es_crawler.pipeline import CrawlService
    from es_crawler.synth import FakeSearchClient, dry_run_config, generate

    config = build_config(dry_run_config(tmp_path))
    service = CrawlService(config, client=FakeSearchClient(generate(120, seed=2)))
    extract, convert, windows = service.run()

    assert extract.succeeded == 1
    assert convert.succeeded == 1

    jsonl = service.writer.path_for(windows[0])
    with open(jsonl, encoding="utf-8") as handle:
        documents = [json.loads(line) for line in handle]
    assert len(documents) == 120

    with open(service.writer.csv_path_for(windows[0]), encoding="utf-8-sig", newline="") as h:
        rows = list(csv.reader(h))
    assert len(rows) == 121


def test_a_second_run_skips_what_is_already_done(tmp_path):
    from es_crawler.config import build_config
    from es_crawler.pipeline import CrawlService
    from es_crawler.synth import FakeSearchClient, dry_run_config, generate

    config = build_config(dry_run_config(tmp_path))
    CrawlService(config, client=FakeSearchClient(generate(30))).run()

    again = CrawlService(config, client=FakeSearchClient(generate(30)))
    extract, _, _ = again.run()
    assert extract.skipped == 1
    assert extract.succeeded == 0


def test_an_output_file_with_no_record_is_adopted(tmp_path, caplog):
    """이름을 바꾼 직후 기록 전에 죽은 경우. 다시 조회하지 않는다."""
    from es_crawler.config import build_config
    from es_crawler.pipeline import CrawlService
    from es_crawler.synth import FakeSearchClient, dry_run_config, generate

    config = build_config(dry_run_config(tmp_path))
    first = CrawlService(config, client=FakeSearchClient(generate(40)))
    first.run()
    first.checkpoint_path().unlink()

    again = CrawlService(config, client=FakeSearchClient(generate(40)))
    extract, _, _ = again.run()
    assert extract.skipped == 1


def test_a_leftover_temp_file_is_not_adopted(tmp_path):
    from es_crawler.config import build_config
    from es_crawler.pipeline import CrawlService
    from es_crawler.synth import FakeSearchClient, dry_run_config, generate

    config = build_config(dry_run_config(tmp_path))
    service = CrawlService(config, client=FakeSearchClient(generate(10)))
    window = service.windows(None, None)[0]
    stale = service.writer.path_for(window)
    stale.with_name(stale.name + ".tmp").write_text('{"broken"', encoding="utf-8")

    extract, _, _ = service.run()
    assert extract.succeeded == 1
    assert extract.skipped == 0
