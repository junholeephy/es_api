"""문서를 보고 지표를 내는 기능들. 하나가 폴더 하나고, 이 파일이 등록부다.

`pipeline.py` 는 문서를 뽑아 파일로 떨구는 조립을 맡고, 여기는 **뽑은 문서가
어떤가**를 보는 일을 맡는다. 둘을 가르는 이유는 성격이 달라서다 — 저쪽은 순서가
있는 단계고, 이쪽은 서로 독립인 판정들이다.

기능을 만들려면 둘이면 된다:

    cp -r src/<pkg>/features/template src/<pkg>/features/<기능>
    # 아래 FEATURES 에 한 줄 더한다

기능을 늘려도 스키마·적재·리포트·진입점은 손대지 않는다. 자리를 미리 잡아두는
이유는 나중에 옮기는 편이 더 비싸기 때문이다 — 옮기는 순간에 import 도 테스트도
지표 이름도 함께 흔들리고, 그 순간은 하필 기능을 만드느라 바쁠 때 온다.
"""

# 화면에 뜨는 순서다. 사람이 사이클 사이에 눈으로 대조하므로 순서를 바꾸지 않는다.
#
# 비어 있으면 리포트에 metrics 줄이 나오지 않는다. 아직 판정이 없다는 뜻이고,
# 그건 결함이 아니다 — 이 프로그램의 본업은 뽑아 떨구는 것이다.
FEATURES: tuple = ()


def process_data(rows: list[dict]) -> dict:
    """기능 전부를 돌리고 지표를 합친다. 기능이 없으면 빈 dict 다."""
    metrics: dict = {}
    for feature in FEATURES:
        result = feature.process_data(rows)
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
