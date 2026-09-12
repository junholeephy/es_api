"""실행 흐름을 조립하고, 기능 목록을 든다.

컴포넌트끼리는 서로를 모른다. 조합은 전부 여기서 일어나고, 그래서 순서에 얽힌
규칙도 전부 여기에 모인다.

`FEATURES` 가 여기 있는 것이 요점이다 — 이 파일은 프로젝트가 고치는 파일이고,
공유 코드(`schema` · `load` · `report` · `synth`)와 진입점은 기능이 늘어도
손대지 않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .checkpoint import CheckpointStore
from .chunker import DateChunker, TimeWindow
from .config import Config
from .converter import CsvConverter
from .load import EsExtractor, build_client
from .schema import Report as SchemaReport
from .schema import validate
from .writer import JsonlWriter, count_lines

log = logging.getLogger(__name__)


# --------------------------------------------------------------- 기능 등록부

# 화면에 뜨는 순서다. 사람이 사이클 사이에 눈으로 대조하므로 순서를 바꾸지 않는다.
#
# 비어 있는 이유는 이 프로그램의 본업이 **뽑아 떨구는 것**이라, 뽑은 문서를 읽어
# 지표를 내는 일이 아직 없기 때문이다. 진행 상황(extract·convert)은 본업의 결과지
# 입력을 읽어 만든 것이 아니라서 리포트가 직접 찍는다.
#
#     cp -r src/es_crawler/features/template src/es_crawler/features/<기능>
#     # 여기에 한 줄 더한다
FEATURES: tuple[Any, ...] = ()


def process_data(hits: list[dict[str, Any]]) -> dict[str, str]:
    """기능 전부를 돌리고 지표를 합친다.

    기능이 하나도 없어도 건수는 찍는다. 분모가 보이지 않으면 나중에 붙는 비율을
    읽을 수 없고, 이 표본은 전수가 아니라 첫 조각에서 뽑은 것이라 더 그렇다.
    """
    metrics: dict[str, str] = {"hits": f"{len(hits):,}"}
    for feature in FEATURES:
        result = feature.process_data(hits)
        collided = metrics.keys() & result.keys()
        if collided:
            # 조용히 덮어쓰면 화면의 숫자가 거짓이 된다 — 마지막 기능의 값만 남고
            # 덮였다는 사실은 어디에도 안 뜬다. 시끄럽게 죽는 쪽이 낫다.
            raise KeyError(
                f"{feature.NAME} 의 지표 이름이 겹친다: {sorted(collided)}. "
                f"지표 이름 앞에 NAME 을 붙여라"
            )
        metrics.update(result)
    return metrics


@dataclass
class ChunkResult:
    window: TimeWindow
    status: str
    doc_count: int = 0
    error: str | None = None


@dataclass
class Report:
    results: list[ChunkResult] = field(default_factory=list)

    def _count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def succeeded(self) -> int:
        return self._count("done")

    @property
    def failed(self) -> int:
        return self._count("failed")

    @property
    def skipped(self) -> int:
        return self._count("skipped")

    @property
    def total_documents(self) -> int:
        return sum(r.doc_count for r in self.results)

    @property
    def ok(self) -> bool:
        return self.failed == 0


class CrawlService:
    """이 패키지를 코드에서 쓸 때의 진입점."""

    def __init__(self, config: Config, client: Any | None = None) -> None:
        self._config = config
        self._chunker = DateChunker(config.chunk)
        self._writer = JsonlWriter(config.output.directory)
        self._converter = CsvConverter(config.output)
        self._checkpoint = CheckpointStore(config.output.directory / ".checkpoint.json")
        self._client = client
        self._extractor: EsExtractor | None = None
        self.schema_report: SchemaReport = SchemaReport([], [], 0)
        self.schema_total = 0
        # 스키마 대조에 쓴 표본. 기능(features/)도 같은 표본을 본다 — 두 번 뽑으면
        # 스키마는 통과했는데 기능은 다른 문서를 본 상태가 될 수 있다.
        self.schema_sample: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ setup

    @property
    def chunker(self) -> DateChunker:
        return self._chunker

    @property
    def writer(self) -> JsonlWriter:
        return self._writer

    def _get_extractor(self) -> EsExtractor:
        if self._extractor is None:
            client = self._client if self._client is not None else build_client(self._config.es)
            self._extractor = EsExtractor(client, self._config.query)
        return self._extractor

    def windows(self, start: datetime | None, end: datetime | None) -> list[TimeWindow]:
        if start is None or end is None:
            start, end = self._chunker.default_window(datetime.now(self._chunker.tz))
        return self._chunker.chunks(start, end)

    # ---------------------------------------------------------------- extract

    def extract(self, windows: Sequence[TimeWindow]) -> Report:
        """구간마다 받아서 파일로 남긴다. 하나가 실패해도 나머지는 계속 돈다."""
        self._reconcile(windows)

        extractor = self._get_extractor()
        report = Report()
        first = True

        for i, window in enumerate(windows, 1):
            if self._checkpoint.is_done(window):
                log.info("chunk %d/%d  %s  already done, skipping", i, len(windows), window)
                report.results.append(ChunkResult(window, "skipped"))
                continue

            log.info("chunk %d/%d  %s", i, len(windows), window)
            try:
                sample: list[dict[str, Any]] = []
                with closing(extractor.iter_documents(window)) as documents:
                    stream = self._instrument(documents, sample if first else None)
                    count = self._writer.write(window, stream)
                # 파일이 확정된 뒤에 완료로 남긴다. 순서가 뒤집히면 "완료인데
                # 파일은 없는" 상태가 생기고, 그 구간은 다시 조회되지 않는다.
                self._checkpoint.mark_done(window, count)
                report.results.append(ChunkResult(window, "done", count))
                log.info("  done  %s docs -> %s", f"{count:,}", self._writer.path_for(window))

                if first:
                    self.schema_report = validate(sample)
                    self.schema_sample = sample
                    self.schema_total = count
                    first = False
            except Exception as exc:
                self._checkpoint.mark_failed(window, f"{type(exc).__name__}: {exc}")
                report.results.append(ChunkResult(window, "failed", 0, str(exc)))
                log.error("  failed  %s: %s", type(exc).__name__, exc)
                continue

        return report

    def _reconcile(self, windows: Sequence[TimeWindow]) -> None:
        """파일은 있는데 완료 기록이 없는 구간을 메운다.

        메우려는 구멍은 좁다 — 파일 이름을 바꾼 직후, 완료로 적기 전에 프로세스가
        죽은 경우다. 최종 이름을 가진 파일은 언제나 완성본이므로(임시 파일은 다른
        이름을 쓴다) 그것을 근거로 삼아도 된다.
        """
        for window in windows:
            if self._checkpoint.is_done(window) or not self._writer.exists(window):
                continue
            count = count_lines(self._writer.path_for(window))
            self._checkpoint.mark_done(window, count)
            log.warning(
                "found an output file with no record, marking done: %s (%s docs)",
                self._writer.path_for(window).name,
                f"{count:,}",
            )

    def _instrument(
        self, documents: Iterable[dict[str, Any]], sample: list[dict[str, Any]] | None
    ) -> Iterator[dict[str, Any]]:
        """흘러가는 문서를 세고, 첫 구간에서는 표본을 모은다."""
        every = self._config.output.progress_every
        limit = self._config.output.schema_sample
        for seen, document in enumerate(documents, 1):
            if sample is not None and len(sample) < limit:
                sample.append(document)
            if every and seen % every == 0:
                log.info("  ... %s docs", f"{seen:,}")
            yield document

    # ---------------------------------------------------------------- convert

    def convert(self, windows: Sequence[TimeWindow]) -> Report:
        """이미 남긴 파일을 CSV 로 바꾼다. 클러스터에 접속하지 않는다."""
        report = Report()
        for window in windows:
            source = self._writer.path_for(window)
            if not source.is_file():
                log.warning("no input file, skipping: %s", source.name)
                report.results.append(ChunkResult(window, "skipped"))
                continue
            target = self._writer.csv_path_for(window)
            try:
                rows = self._converter.convert(source, target)
                report.results.append(ChunkResult(window, "done", rows))
                log.info("  converted  %s rows -> %s", f"{rows:,}", target.name)
            except Exception as exc:
                report.results.append(ChunkResult(window, "failed", 0, str(exc)))
                log.error("  convert failed  %s: %s", type(exc).__name__, exc)
                continue
        return report

    # -------------------------------------------------------------------- run

    def run(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[Report, Report, list[TimeWindow]]:
        """받아서 남기고, 성공한 것만 CSV 로 바꾼다.

        명령행 기본 실행은 이 메서드를 쓰지 않는다 — 받아서 남기는 데까지만 한다.
        두 단계를 한 번에 돌리는 것은 코드에서 이 패키지를 쓸 때의 경로다.

        실패한 구간은 변환 대상에서 빠진다. 그 구간은 다음 실행에서 조회와 변환을
        함께 하게 된다. 덕분에 성공한 부분은 지금 바로 쓸 수 있지만, CSV 디렉터리가
        요청 구간을 다 덮는다는 보장은 사라진다 — 그 사실은 종료 코드와 요약의
        실패 건수로 드러난다.
        """
        windows = self.windows(start, end)
        extract_report = self.extract(windows)
        usable = [r.window for r in extract_report.results if r.status in ("done", "skipped")]
        convert_report = self.convert(usable)
        return extract_report, convert_report, windows

    def convert_only(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[Report, Report, list[TimeWindow]]:
        windows = self.windows(start, end)
        return Report(), self.convert(windows), windows

    def extract_only(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[Report, Report, list[TimeWindow]]:
        windows = self.windows(start, end)
        return self.extract(windows), Report(), windows

    # ------------------------------------------------------------------ paths

    def checkpoint_path(self) -> Path:
        return self._checkpoint.path
