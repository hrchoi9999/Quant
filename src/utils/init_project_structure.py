# init_project_structure.py ver 2025-12-11_001

import os
from textwrap import dedent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def make_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def write_if_not_exists(path: str, content: str) -> None:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(dedent(content).lstrip("\n"))

def main():
    # ---------------------------
    # 1. 디렉터리 생성
    # ---------------------------
    src_dir = os.path.join(BASE_DIR, "src")
    data_dir = os.path.join(BASE_DIR, "data")
    notebooks_dir = os.path.join(BASE_DIR, "notebooks")

    make_dir(src_dir)
    make_dir(os.path.join(src_dir, "collectors"))
    make_dir(os.path.join(src_dir, "processing"))
    make_dir(os.path.join(src_dir, "factors"))
    make_dir(os.path.join(src_dir, "strategies"))
    make_dir(os.path.join(src_dir, "backtest"))
    make_dir(os.path.join(src_dir, "reports"))

    make_dir(os.path.join(data_dir, "raw", "dart"))
    make_dir(os.path.join(data_dir, "raw", "kiwoom"))
    make_dir(os.path.join(data_dir, "processed", "financials"))
    make_dir(os.path.join(data_dir, "processed", "prices"))
    make_dir(os.path.join(data_dir, "processed", "factors"))

    make_dir(notebooks_dir)

    # ---------------------------
    # 2. __init__.py (패키지 인식용)
    # ---------------------------
    for sub in ["", "collectors", "processing", "factors", "strategies", "backtest", "reports"]:
        init_path = os.path.join(src_dir, sub, "__init__.py") if sub else os.path.join(src_dir, "__init__.py")
        write_if_not_exists(
            init_path,
            f"""\
            # __init__.py ver 2025-12-11_001
            # 패키지 초기화 모듈
            """
        )

    # ---------------------------
    # 3. collectors 레이어
    # ---------------------------
    write_if_not_exists(
        os.path.join(src_dir, "collectors", "dart_financials.py"),
        """\
        # dart_financials.py ver 2025-12-11_001

        \"\"\"DART에서 국내 상장사 재무제표/공시 데이터를 수집하는 모듈.

        역할:
        - 상장사 목록(corp_code, 종목코드) 조회
        - 특정 연도/분기 재무제표 수집 (재무상태표, 손익계산서, 현금흐름표 등)
        - 원본 데이터를 data/raw/dart/ 경로에 저장 (CSV 또는 Parquet)

        실제 DART API 연동 로직은 이후 단계에서 구현한다.
        지금은 함수 시그니처만 정의해 둔다.
        \"\"\"

        from typing import List, Dict, Any
        import pandas as pd
        import pathlib

        RAW_DART_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "dart"

        def get_corp_list() -> pd.DataFrame:
            \"\"\"상장사 목록(corp_code, 종목코드 등)을 반환한다.

            TODO:
            - DART OpenAPI 또는 상장사 리스트 파일에서 불러오는 로직 구현
            \"\"\"
            # TODO: 구현
            raise NotImplementedError("get_corp_list()는 아직 구현되지 않았습니다.")

        def fetch_financial_statements(corp_code: str, year: int, report_code: str) -> pd.DataFrame:
            \"\"\"단일 기업(corp_code)의 특정 연도/보고서 유형 재무제표를 수집해 DataFrame으로 반환한다.

            report_code 예:
            - '11011' : 사업보고서(연간)
            - '11012' : 반기보고서
            - '11013' : 1분기보고서
            - '11014' : 3분기보고서
            \"\"\"
            # TODO: 구현
            raise NotImplementedError("fetch_financial_statements()는 아직 구현되지 않았습니다.")

        def save_raw_financials(df: pd.DataFrame, corp_code: str, year: int, report_code: str) -> pathlib.Path:
            \"\"\"수집한 재무제표를 data/raw/dart/ 아래 파일로 저장하고 경로를 반환한다.\"\"\"
            RAW_DART_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"fs_{corp_code}_{year}_{report_code}.parquet"
            path = RAW_DART_DIR / filename
            df.to_parquet(path)
            return path
        """
    )

    write_if_not_exists(
        os.path.join(src_dir, "collectors", "kiwoom_prices.py"),
        """\
        # kiwoom_prices.py ver 2025-12-11_001

        \"\"\"키움증권에서 수집한 가격 데이터를 로딩/표준화하는 모듈.

        전제:
        - 키움 OpenAPI+는 32bit/COM 기반이므로, 별도의 32bit 환경에서
          CSV 파일 형태로 data/raw/kiwoom/ 아래에 저장해 둔다.
        - 이 모듈은 그 CSV를 읽어와서, 퀀트 분석에 적합한 형태의 DataFrame으로 변환하는 역할만 맡는다.

        TODO:
        - 키움 CSV 포맷(컬럼명, 인코딩)을 정리
        - 일봉/분봉 등 주기별 로더 함수 구현
        \"\"\"

        from typing import Literal
        import pandas as pd
        import pathlib

        RAW_KIWOOM_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "kiwoom"

        def load_price_csv(
            code: str,
            freq: Literal["D", "m1", "m5", "m10"] = "D"
        ) -> pd.DataFrame:
            \"\"\"키움이 저장해 둔 특정 종목(code)의 가격 CSV를 읽어서 표준 컬럼명으로 반환한다.

            freq:
            - 'D'  : 일봉
            - 'm1' : 1분봉
            - 'm5' : 5분봉
            - 'm10': 10분봉
            \"\"\"
            # TODO: 실제 파일명 규칙에 맞게 구현
            pattern = f"{code}_{freq}.csv"
            path = RAW_KIWOOM_DIR / pattern
            if not path.exists():
                raise FileNotFoundError(f\"가격 데이터 파일을 찾을 수 없습니다: {path}\")
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
        """
    )

    # ---------------------------
    # 4. processing 레이어
    # ---------------------------
    write_if_not_exists(
        os.path.join(src_dir, "processing", "normalize_financials.py"),
        """\
        # normalize_financials.py ver 2025-12-11_001

        \"\"\"DART 재무제표 원본을 표준화된 패널 데이터 형태로 변환하는 모듈.

        역할:
        - 원본 재무제표(raw)를 읽어서 항목명/계정과목명을 정규화
        - 종목 × 기준일 × 재무지표 형태의 패널 데이터로 변환
        - data/processed/financials/ 아래에 저장
        \"\"\"

        import pandas as pd
        import pathlib

        RAW_DART_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "dart"
        PROC_FIN_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "processed" / "financials"

        def build_financial_panel() -> pd.DataFrame:
            \"\"\"여러 파일에 흩어져 있는 재무제표를 읽어 하나의 패널 DataFrame으로 통합한다.

            TODO:
            - 파일 스캔
            - 항목 매핑
            - 표준화 로직 구현
            \"\"\"
            # TODO: 구현
            raise NotImplementedError("build_financial_panel()는 아직 구현되지 않았습니다.")
        """
    )

    write_if_not_exists(
        os.path.join(src_dir, "processing", "price_cleaning.py"),
        """\
        # price_cleaning.py ver 2025-12-11_001

        \"\"\"키움/기타 소스에서 수집한 가격 데이터를 정제하는 모듈.

        역할:
        - 누락된 날짜/값 보정
        - 분할, 액면분할, 상장폐지 등 이벤트 처리(추후)
        - data/processed/prices/ 아래 표준 가격 패널 저장
        \"\"\"

        import pandas as pd
        import pathlib

        PROC_PRICE_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "processed" / "prices"

        def build_price_panel() -> pd.DataFrame:
            \"\"\"여러 종목의 가격 데이터를 하나의 패널 DataFrame으로 통합한다.\"\"\"
            # TODO: 구현
            raise NotImplementedError("build_price_panel()는 아직 구현되지 않았습니다.")
        """
    )

    # ---------------------------
    # 5. factors 레이어
    # ---------------------------
    write_if_not_exists(
        os.path.join(src_dir, "factors", "fundamental_factors.py"),
        """\
        # fundamental_factors.py ver 2025-12-11_001

        \"\"\"재무제표 기반 팩터(밸류/퀄리티 등)를 계산하는 모듈.\"\"\"

        import pandas as pd

        def compute_value_factors(fin_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"PER, PBR, PSR 등 밸류에이션 팩터 계산.\"\"\"
            # TODO: 구현
            raise NotImplementedError("compute_value_factors()는 아직 구현되지 않았습니다.")

        def compute_quality_factors(fin_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"ROE, ROA, 영업이익률 등 퀄리티 팩터 계산.\"\"\"
            # TODO: 구현
            raise NotImplementedError("compute_quality_factors()는 아직 구현되지 않았습니다.")
        """
    )

    write_if_not_exists(
        os.path.join(src_dir, "factors", "price_factors.py"),
        """\
        # price_factors.py ver 2025-12-11_001

        \"\"\"가격 기반 팩터(모멘텀, 변동성, 유동성 등)를 계산하는 모듈.\"\"\"

        import pandas as pd

        def compute_momentum_factors(price_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"N개월 수익률, 모멘텀 스코어 등 계산.\"\"\"
            # TODO: 구현
            raise NotImplementedError("compute_momentum_factors()는 아직 구현되지 않았습니다.")

        def compute_volatility_factors(price_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"변동성 관련 팩터(표준편차, ATR 등)를 계산.\"\"\"
            # TODO: 구현
            raise NotImplementedError("compute_volatility_factors()는 아직 구현되지 않았습니다.")
        """
    )

    write_if_not_exists(
        os.path.join(src_dir, "factors", "technical_indicators.py"),
        """\
        # technical_indicators.py ver 2025-12-11_001

        \"\"\"기술적 지표(RSI, MACD, 이동평균선 등)를 계산하는 모듈.\"\"\"

        import pandas as pd
        import pandas_ta_classic as ta  # df.ta 접근 방식 사용

        def add_basic_indicators(df: pd.DataFrame) -> pd.DataFrame:
            \"\"\"단일 종목의 시계열 DataFrame에 기본 기술지표 컬럼을 추가한다.

            필요 컬럼:
            - 'close'는 필수, 'high', 'low', 'open', 'volume' 있으면 추가 지표 계산 가능
            \"\"\"
            # 예시: RSI, MACD, 20일/60일 이동평균
            df.ta.rsi(length=14, append=True)
            df.ta.macd(append=True)
            df.ta.sma(length=20, append=True)
            df.ta.sma(length=60, append=True)
            return df
        """
    )

    # ---------------------------
    # 6. strategies 레이어
    # ---------------------------
    write_if_not_exists(
        os.path.join(src_dir, "strategies", "value_strategy.py"),
        """\
        # value_strategy.py ver 2025-12-11_001

        \"\"\"밸류(가치) 기반 전략을 정의하는 모듈.\"\"\"

        import pandas as pd

        def build_value_signal(factor_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"밸류 팩터 기반으로 매수/매도/보유 신호를 생성한다.\"\"\"
            # TODO: 구현
            raise NotImplementedError("build_value_signal()는 아직 구현되지 않았습니다.")
        """
    )

    write_if_not_exists(
        os.path.join(src_dir, "strategies", "momentum_strategy.py"),
        """\
        # momentum_strategy.py ver 2025-12-11_001

        \"\"\"모멘텀 기반 전략을 정의하는 모듈.\"\"\"

        import pandas as pd

        def build_momentum_signal(factor_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"모멘텀 팩터 기반으로 매수/매도/보유 신호를 생성한다.\"\"\"
            # TODO: 구현
            raise NotImplementedError("build_momentum_signal()는 아직 구현되지 않았습니다.")
        """
    )

    write_if_not_exists(
        os.path.join(src_dir, "strategies", "mixed_value_mom.py"),
        """\
        # mixed_value_mom.py ver 2025-12-11_001

        \"\"\"밸류 + 모멘텀 혼합 전략을 정의하는 모듈.\"\"\"

        import pandas as pd

        def build_mixed_signal(factor_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"밸류와 모멘텀 팩터를 조합한 신호를 생성한다.\"\"\"
            # TODO: 구현
            raise NotImplementedError("build_mixed_signal()는 아직 구현되지 않았습니다.")
        """
    )

    # ---------------------------
    # 7. backtest 레이어
    # ---------------------------
    write_if_not_exists(
        os.path.join(src_dir, "backtest", "backtest_engine.py"),
        """\
        # backtest_engine.py ver 2025-12-11_001

        \"\"\"단순한 백테스트 엔진을 제공하는 모듈.

        역할:
        - 신호(DataFrame)와 가격 패널을 입력으로 받아
          포트폴리오의 일별/월별 수익률을 계산
        \"\"\"

        import pandas as pd

        def run_backtest(price_panel: pd.DataFrame, signal_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"백테스트 실행 후 일별 포트폴리오 수익률 시계열을 반환한다.\"\"\"
            # TODO: 구현
            raise NotImplementedError("run_backtest()는 아직 구현되지 않았습니다.")
        """
    )

    write_if_not_exists(
        os.path.join(src_dir, "backtest", "portfolio_rebalancer.py"),
        """\
        # portfolio_rebalancer.py ver 2025-12-11_001

        \"\"\"리밸런싱 규칙(월별/분기별 등)을 정의하는 모듈.\"\"\"

        import pandas as pd

        def apply_rebalancing(weights_panel: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
            \"\"\"주어진 가중치 패널에 리밸런싱 규칙을 적용한다.\"\"\"
            # TODO: 구현
            raise NotImplementedError("apply_rebalancing()는 아직 구현되지 않았습니다.")
        """
    )

    # ---------------------------
    # 8. reports 레이어
    # ---------------------------
    write_if_not_exists(
        os.path.join(src_dir, "reports", "performance_report.py"),
        """\
        # performance_report.py ver 2025-12-11_001

        \"\"\"전략 성과 리포트를 생성하는 모듈.\"\"\"

        import pandas as pd

        def summarize_performance(equity_curve: pd.Series) -> pd.DataFrame:
            \"\"\"CAGR, MDD, Sharpe 등 핵심 지표를 정리한 DataFrame 반환.\"\"\"
            # TODO: 구현
            raise NotImplementedError("summarize_performance()는 아직 구현되지 않았습니다.")
        """
    )

    write_if_not_exists(
        os.path.join(src_dir, "reports", "factor_report.py"),
        """\
        # factor_report.py ver 2025-12-11_001

        \"\"\"팩터 특성, 상관관계 등을 분석하는 리포트를 생성하는 모듈.\"\"\"

        import pandas as pd

        def analyze_factor_distribution(factor_panel: pd.DataFrame) -> pd.DataFrame:
            \"\"\"팩터 분포/상관관계 등을 요약한 통계 반환.\"\"\"
            # TODO: 구현
            raise NotImplementedError("analyze_factor_distribution()는 아직 구현되지 않았습니다.")
        """
    )

if __name__ == "__main__":
    main()
