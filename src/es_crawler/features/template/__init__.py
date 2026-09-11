"""기능 하나의 판정. 복사해서 쓰는 원본이다.

    cp -r src/<pkg>/features/template src/<pkg>/features/<기능>

그다음 `features/__init__.py` 의 `FEATURES` 에 한 줄 더하면 리포트에 나온다. 스키마·적재·
리포트·진입점은 손대지 않는다.

**이 폴더 자체는 지우지 마라.** 일곱 번째 기능을 만드는 사람이 기존 기능 하나를
골라 베끼면 그 기능만의 사정까지 따라간다. 원본이 있어야 깨끗한 데서 시작한다.

**기능이 커지면 파일을 옆에 만든다.** 이 폴더 안에 두고 여기서 import 한다. 폴더
깊이가 처음부터 고정이라 그때 상대 import 를 고칠 일이 없다.

지켜야 하는 것 둘:

- **`process_data(rows) -> dict` 로 노출한다.** 등록부가 이 이름으로 부른다
- **지표 이름 앞에 `NAME` 을 붙인다.** 여럿의 결과가 한 리포트에 모이므로 접두어가
  없으면 겹친다. 겹치면 등록부가 죽이지만, 죽기 전에 붙여라
"""

from .._shared import tally

NAME = "template"  # 폴더 이름과 같게 둔다. 지표 접두어로 쓰인다


def process_data(rows: list[dict]) -> dict:
    """뽑아낸 문서들을 보고 지표를 돌려준다. 실제 값·식별자는 넣지 않는다."""
    hits = sum(1 for row in rows if _hit(row))
    return {NAME: tally(hits, len(rows))}


def _hit(row: dict) -> bool:
    """이 문서가 이 기능에 걸리는가.

    ⭐ TODO: 실제 판정을 여기에. 지금은 "빈 값이 하나라도 있나" 를 본다.
    """
    return any(value in (None, "") for value in row.values())
