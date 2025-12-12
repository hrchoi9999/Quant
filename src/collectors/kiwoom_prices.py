# kiwoom_prices.py ver 2025-12-11_001

"""키움증권에서 수집한 가격 데이터를 로딩/표준화하는 모듈.

전제:
- 키움 OpenAPI+는 32bit/COM 기반이므로, 별도의 32bit 환경에서
  CSV 파일 형태로 data/raw/kiwoom/ 아래에 저장해 둔다.
- 이 모듈은 그 CSV를 읽어와서, 퀀트 분석에 적합한 형태의 DataFrame으로 변환하는 역할만 맡는다.

TODO:
- 키움 CSV 포맷(컬럼명, 인코딩)을 정리
- 일봉/분봉 등 주기별 로더 함수 구현
"""

from typing import Literal
import pandas as pd
import pathlib

RAW_KIWOOM_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "kiwoom"

def load_price_csv(
    code: str,
    freq: Literal["D", "m1", "m5", "m10"] = "D"
) -> pd.DataFrame:
    """키움이 저장해 둔 특정 종목(code)의 가격 CSV를 읽어서 표준 컬럼명으로 반환한다.

    freq:
    - 'D'  : 일봉
    - 'm1' : 1분봉
    - 'm5' : 5분봉
    - 'm10': 10분봉
    """
    # TODO: 실제 파일명 규칙에 맞게 구현
    pattern = f"{code}_{freq}.csv"
    path = RAW_KIWOOM_DIR / pattern
    if not path.exists():
        raise FileNotFoundError(f"가격 데이터 파일을 찾을 수 없습니다: {path}")
    df = pd.read_csv(path)

    # TODO: 실제 컬럼명에 맞게 수정
    rename_map = {
        "날짜": "date",
        "시가": "open",
        "고가": "high",
        "저가": "low",
        "종가": "close",
        "거래량": "volume",
    }
    df = df.rename(columns=rename_map)
    return df
