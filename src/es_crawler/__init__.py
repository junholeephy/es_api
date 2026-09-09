"""Elasticsearch 에서 시간 구간별로 문서를 받아 JSONL 로 남기고 CSV 로 정리한다.

공개하는 것은 넷뿐이다. 나머지 모듈은 내부 구현이며, 필요해지면 그때 공개한다.

    from es_crawler import CrawlService, load_config

    cfg = load_config(Path("configs/env.yaml"))
    report = CrawlService(cfg).run()
"""

from .chunker import TimeWindow
from .config import Config, load_config
from .pipeline import CrawlService

__all__ = ["Config", "CrawlService", "TimeWindow", "load_config"]
