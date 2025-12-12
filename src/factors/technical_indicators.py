# technical_indicators.py ver 2025-12-11_001

"""기술적 지표(RSI, MACD, 이동평균선 등)를 계산하는 모듈."""

import pandas as pd
import pandas_ta_classic as ta  # df.ta 접근 방식 사용

def add_basic_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """단일 종목의 시계열 DataFrame에 기본 기술지표 컬럼을 추가한다.

    필요 컬럼:
    - 'close'는 필수, 'high', 'low', 'open', 'volume' 있으면 추가 지표 계산 가능
    """
    # 예시: RSI, MACD, 20일/60일 이동평균
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.sma(length=20, append=True)
    df.ta.sma(length=60, append=True)
    return df
