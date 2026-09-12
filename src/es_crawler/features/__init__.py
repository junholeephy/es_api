"""기능 하나가 폴더 하나다. 목록은 여기가 아니라 `pipeline.py` 에 있다.

**기능**은 같은 입력을 읽어 지표를 내는 독립 단위다 — 사고 검출도, 분포 집계도,
성능 계산도 전부 기능이다. 계약은 `process_data` 하나뿐이라 안에서 무엇을 하든
상관없다.

기능을 만들려면 둘이면 된다:

    cp -r src/es_crawler/features/template src/es_crawler/features/<기능>
    # pipeline.py 의 FEATURES 에 한 줄 더한다

목록이 `pipeline.py` 에 있는 것이 요점이다 — 그쪽은 이 프로젝트가 고치는 파일이고,
공유 코드(`schema` · `load` · `report` · `synth`)와 진입점은 기능이 늘어도 손대지
않는다.
"""
