"""기능 하나. 복사해서 쓰는 원본이다.

**기능은 판정만이 아니다.** 같은 입력을 읽어 지표를 내는 독립 단위면 무엇이든
기능이다 — 사고 검출도, 분포 집계도, 성능 계산도.

    cp -r src/es_crawler/features/template src/es_crawler/features/<기능>

그다음 `pipeline.py` 의 `FEATURES` 에 한 줄 더하면 리포트에 나온다. 스키마·적재·
리포트·진입점은 손대지 않는다.

**이 폴더 자체는 지우지 마라.** 일곱 번째 기능을 만드는 사람이 기존 기능 하나를
골라 베끼면 그 기능만의 사정까지 따라간다. 원본이 있어야 깨끗한 데서 시작한다.

**기능이 커지면 파일을 옆에 만든다.** 이 폴더 안에 두고 여기서 import 한다
(`from .patterns import PATTERNS`). 폴더 깊이가 처음부터 고정이라 그때 상대 import
를 고칠 일이 없다.

**받는 것은 Elasticsearch 히트다.** 문서 본문이 아니라 그것을 감싼 봉투이고,
내용은 `_source` 안에 있다. 그래서 값은 `resolve` 로 꺼낸다 — 점 경로는 설정
파일의 `output.columns` 와 같은 표기다.

    resolve(hit, "user.name", None)   # 없으면 None
    hit["_id"]                        # 메타데이터는 봉투 최상위에

지켜야 하는 것 둘:

- **`process_data(hits) -> dict` 로 노출한다.** `pipeline.py` 가 이 이름으로 부른다
- **지표 이름 앞에 `NAME` 을 붙인다.** 여럿의 결과가 한 리포트에 모이므로 접두어가
  없으면 겹친다. 겹치면 등록부가 죽이지만, 죽기 전에 붙여라
"""

from typing import Any

from ...schema import resolve
from .._shared import tally

NAME = "template"  # 폴더 이름과 같게 둔다. 지표 접두어로 쓰인다


def process_data(hits: list[dict[str, Any]]) -> dict[str, str]:
    """뽑아낸 히트들을 보고 지표를 돌려준다. 실제 값·식별자는 넣지 않는다."""
    matched = sum(1 for hit in hits if _hit(hit))
    return {NAME: tally(matched, len(hits))}


def _hit(hit: dict[str, Any]) -> bool:
    """이 문서가 이 기능에 걸리는가.

    ⭐ TODO: 실제 내용을 여기에. 지금은 "이름이 비어 있나" 를 본다 — 자리를
    지키면서 전 구간이 도는 것까지만 보이는 최소 구현이다.
    """
    return resolve(hit, "user.name", None) in (None, "")
