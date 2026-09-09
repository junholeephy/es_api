"""실행 요약 블록.

화면이 결과를 확인하는 자리다. 한 줄에 한 항목, 표시 폭 80칸 이내 — 사람이 손으로
옮겨 적는 것이 전제다. 개별 문서의 값이나 식별자는 찍지 않는다.
"""

from __future__ import annotations

import unicodedata

WIDTH = 45

STATUS_OK = "OK"
STATUS_SCHEMA = "SCHEMA MISMATCH"
STATUS_CHUNKS = "CHUNKS FAILED"
STATUS_BOTH = "SCHEMA MISMATCH + CHUNKS FAILED"


def status_for(*, schema_ok: bool, chunks_failed: int) -> str:
    """종료 코드 1 의 원인이 둘이라, 화면만 보고도 구별되어야 한다."""
    if schema_ok and not chunks_failed:
        return STATUS_OK
    if not schema_ok and chunks_failed:
        return STATUS_BOTH
    return STATUS_SCHEMA if not schema_ok else STATUS_CHUNKS


def display_width(text: str) -> int:
    """표시 폭. 한글·한자는 터미널에서 두 칸을 쓰므로 len() 으로는 정렬이 깨진다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def render(
    *,
    version: str,
    args: str,
    window: str,
    n_chunks: int,
    schema_violations: list[str],
    schema_notes: list[str],
    schema_fields: int,
    schema_sampled: int,
    schema_total: int,
    counts: dict[str, int],
    extracted_docs: int,
    extracted_files: int,
    converted_rows: int,
    converted_files: int,
    runtime_s: float,
    peak_gb: float,
    status: str,
) -> str:
    # 빈칸이면 옮겨 적을 때 통째로 빠지고, 빠진 줄은 없었던 것이 된다.
    version = version.strip() or "unversioned"
    n_ok = max(0, schema_fields - len(schema_violations))

    sampled = (
        f"   (sampled {schema_sampled:,} of {schema_total:,} in first chunk)"
        if schema_sampled
        else "   (no documents sampled)"
    )

    lines = [
        "=" * WIDTH,
        "RUN SUMMARY".center(WIDTH),
        "=" * WIDTH,
        f"version   : {version}",
        f"args      : {args}",
        f"window    : {window} ({n_chunks} chunk{'s' if n_chunks != 1 else ''})",
        f"schema    : {n_ok} ok / {len(schema_violations)} MISMATCH{sampled}",
    ]
    lines += [f"  - {v}" for v in schema_violations]
    if schema_notes:
        lines.append(f"notes     : {len(schema_notes)} (no effect on output)")
        lines += [f"  - {n}" for n in schema_notes]

    lines.append("chunks    :")
    lines += [f"  {pad(k, 16)} {v:,}" for k, v in counts.items()]
    lines.append(f"extract   : {extracted_docs:,} docs -> {extracted_files:,} jsonl")
    lines.append(f"convert   : {converted_rows:,} rows -> {converted_files:,} csv")
    lines.append(f"runtime   : {runtime_s:.1f}s, peak {peak_gb:.2f}GB")
    lines.append(f"status    : {status}")
    lines.append("=" * WIDTH)
    return "\n".join(lines)


def peak_gb() -> float:
    import resource
    import sys

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 1024**3 if sys.platform == "darwin" else rss / 1024**2
