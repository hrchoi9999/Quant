# price_cleaning.py ver 2025-12-11_001

"""키움/기타 소스에서 수집한 가격 데이터를 정제하는 모듈.

역할:
- 누락된 날짜/값 보정
- 분할, 액면분할, 상장폐지 등 이벤트 처리(추후)
- data/processed/prices/ 아래 표준 가격 패널 저장
"""

import pandas as pd
import pathlib

PROC_PRICE_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "processed" / "prices"

def build_price_panel() -> pd.DataFrame:
    """여러 종목의 가격 데이터를 하나의 패널 DataFrame으로 통합한다."""
    # TODO: 구현
    raise NotImplementedError("build_price_panel()는 아직 구현되지 않았습니다.")
