# normalize_financials.py ver 2025-12-11_001

"""DART 재무제표 원본을 표준화된 패널 데이터 형태로 변환하는 모듈.

역할:
- 원본 재무제표(raw)를 읽어서 항목명/계정과목명을 정규화
- 종목 × 기준일 × 재무지표 형태의 패널 데이터로 변환
- data/processed/financials/ 아래에 저장
"""

import pandas as pd
import pathlib

RAW_DART_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "dart"
PROC_FIN_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "processed" / "financials"

def build_financial_panel() -> pd.DataFrame:
    """여러 파일에 흩어져 있는 재무제표를 읽어 하나의 패널 DataFrame으로 통합한다.

    TODO:
    - 파일 스캔
    - 항목 매핑
    - 표준화 로직 구현
    """
    # TODO: 구현
    raise NotImplementedError("build_financial_panel()는 아직 구현되지 않았습니다.")
