# backtest_engine.py ver 2025-12-11_001

"""단순한 백테스트 엔진을 제공하는 모듈.

역할:
- 신호(DataFrame)와 가격 패널을 입력으로 받아
  포트폴리오의 일별/월별 수익률을 계산
"""

import pandas as pd

def run_backtest(price_panel: pd.DataFrame, signal_panel: pd.DataFrame) -> pd.DataFrame:
    """백테스트 실행 후 일별 포트폴리오 수익률 시계열을 반환한다."""
    # TODO: 구현
    raise NotImplementedError("run_backtest()는 아직 구현되지 않았습니다.")
