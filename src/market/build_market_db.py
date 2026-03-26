# build_market_db.py ver 2026-01-29_001
"""
market.db 생성 스크립트 (옵션2)
- 지수: pykrx (KOSPI=1001, KOSDAQ=2001, KOSPI200=1028)
- 환율: FinanceDataReader (USD/KRW)
- 금리: FinanceDataReader ECOS snapshot (/ECOS/SNAP/523, /ECOS/SNAP/512)
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

try:
    from pykrx import stock as krx_stock
except Exception as e:
    raise RuntimeError("pykrx import 실패. `pip install pykrx` 확인 필요") from e

try:
    import FinanceDataReader as fdr
except Exception as e:
    raise RuntimeError("FinanceDataReader import 실패. `pip install finance-datareader` 확인 필요") from e


# -----------------------------
# helpers
# -----------------------------
def _to_yyyymmdd(s: str) -> str:
    return s.replace("-", "")

def _safe_rename_cols(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    cols = {c: mapping[c] for c in df.columns if c in mapping}
    return df.rename(columns=cols)

def _add_derived(df: pd.DataFrame, px_col: str, prefix: str) -> pd.DataFrame:
    """단순 파생: 1d 수익률, SMA200, 21일 실현변동성"""
    x = df[px_col].astype(float)
    df[f"{prefix}_ret_1d"] = x.pct_change()
    df[f"{prefix}_sma_200"] = x.rolling(200, min_periods=50).mean()
    df[f"{prefix}_vol_21"] = df[f"{prefix}_ret_1d"].rolling(21, min_periods=10).std()
    return df

def fetch_index_ohlcv(code: str, start: str, end: str) -> pd.DataFrame:
    """
    1) pykrx로 시도 (OHLCV 완비)
    2) pykrx가 '지수명' KeyError 등으로 실패하면 FDR(KRX index code)로 fallback
    """
    s = _to_yyyymmdd(start)
    e = _to_yyyymmdd(end)

    # 1) pykrx first
    try:
        df = krx_stock.get_index_ohlcv_by_date(s, e, code)
        if df is None or df.empty:
            raise RuntimeError("pykrx returned empty")
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.rename(columns={
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
            "거래대금": "value",
        })
        # 일부 컬럼이 없을 수도 있으니 존재하는 것만 정렬
        cols = [c for c in ["open","high","low","close","volume","value"] if c in df.columns]
        return df[cols]

    except Exception as ex:
        print(f"[WARN] pykrx index fetch failed(code={code}): {type(ex).__name__}: {ex}")
        print("[WARN] fallback to FinanceDataReader(KRX index code)")

    # 2) fallback: FinanceDataReader
    df = fdr.DataReader(code, start, end)   # ex) "1001", "2001", "1028"
    if df is None or df.empty:
        raise RuntimeError(f"FDR index fetch failed: code={code}, range={start}..{end}")

    df = df.copy()
    df.index = pd.to_datetime(df.index)

    # FDR 컬럼 표준화(대부분 Open/High/Low/Close/Volume 형태)
    rename_map = {}
    for k in ["Open","High","Low","Close","Volume","Change"]:
        if k in df.columns:
            rename_map[k] = k.lower()
    df = df.rename(columns=rename_map)

    # value(거래대금)는 FDR에 없을 수 있으니 optional
    cols = [c for c in ["open","high","low","close","volume"] if c in df.columns]
    if "close" not in cols:
        # Close가 없으면 첫 컬럼을 close로 가정
        df = df.rename(columns={df.columns[0]: "close"})
        cols = [c for c in ["open","high","low","close","volume"] if c in df.columns]

    return df[cols]


def fetch_fx_usdkrw(start: str, end: str) -> pd.DataFrame:
    """FDR: USD/KRW"""
    df = fdr.DataReader("USD/KRW", start, end)
    if df is None or df.empty:
        raise RuntimeError("FDR USD/KRW fetch 실패")
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    # FDR는 보통 Close만 있거나 OHLC가 있을 수 있음. Close 우선.
    if "Close" in df.columns:
        df = df.rename(columns={"Close": "usdkrw"})
    elif "close" in df.columns:
        df = df.rename(columns={"close": "usdkrw"})
    else:
        # 첫 번째 컬럼을 close로 가정
        df = df.rename(columns={df.columns[0]: "usdkrw"})
    return df[["usdkrw"]]

def fetch_ecos_snapshot(path: str, start: str, end: str) -> pd.DataFrame:
    """
    FDR ECOS snapshot 시도.
    환경(FDR 버전)에 따라 미지원이면 예외가 나므로, 실패 시 빈 DF 반환.
    """
    try:
        df = fdr.DataReader(path, start, end)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as ex:
        print(f"[WARN] ECOS snapshot fetch failed({path}): {type(ex).__name__}: {ex}")
        return pd.DataFrame()


# -----------------------------
# main build
# -----------------------------
def build_market_db(
    out_db: str,
    out_table: str,
    start: str,
    end: str,
    include_vkosp: bool = False,
) -> None:
    out_db_path = Path(out_db)
    out_db_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) indices
    print(f"[FETCH] indices via pykrx: {start}..{end}")
    kospi = fetch_index_ohlcv("1001", start, end).rename(columns=lambda c: f"kospi_{c}")
    kosdaq = fetch_index_ohlcv("2001", start, end).rename(columns=lambda c: f"kosdaq_{c}")
    kospi200 = fetch_index_ohlcv("1028", start, end).rename(columns=lambda c: f"kospi200_{c}")

    # 파생지표
    kospi = _add_derived(kospi, "kospi_close", "kospi")
    kosdaq = _add_derived(kosdaq, "kosdaq_close", "kosdaq")
    kospi200 = _add_derived(kospi200, "kospi200_close", "kospi200")

    # 2) fx
    print("[FETCH] fx via FDR: USD/KRW")
    fx = fetch_fx_usdkrw(start, end)

    # 3) rates (optional, best-effort)
    print("[FETCH] rates via FDR(ECOS snapshot) (best-effort)")
    r_short = fetch_ecos_snapshot("/ECOS/SNAP/523", start, end)  # short-term
    r_long = fetch_ecos_snapshot("/ECOS/SNAP/512", start, end)   # long-term

    # 관심 컬럼만 뽑기(있으면)
    # 523: 기준금리/콜금리/CD 등, 512: 국고채(3년) 등
    rates = pd.DataFrame(index=pd.date_range(start, end, freq="D"))
    rates.index = pd.to_datetime(rates.index)

    if not r_short.empty:
        # 가능한 컬럼 후보들
        cand = [
            "한국은행 기준금리",
            "콜금리(익일물)",
            "CD수익률(91일)",
            "KORIBOR(3개월)",
        ]
        for c in cand:
            if c in r_short.columns:
                rates[c] = r_short[c]
    if not r_long.empty:
        cand = [
            "통안증권수익률(1년)",
            "국고채수익률(3년)",
            "국고채수익률(5년)",
            "회사채수익률(3년, AA-)",
        ]
        for c in cand:
            if c in r_long.columns:
                rates[c] = r_long[c]

    # 컬럼명 표준화
    rename_map = {
        "한국은행 기준금리": "rate_base",
        "콜금리(익일물)": "rate_call_overnight",
        "CD수익률(91일)": "rate_cd_91d",
        "KORIBOR(3개월)": "rate_koribor_3m",
        "통안증권수익률(1년)": "rate_msb_1y",
        "국고채수익률(3년)": "rate_ktb_3y",
        "국고채수익률(5년)": "rate_ktb_5y",
        "회사채수익률(3년, AA-)": "rate_cb_3y_aa_minus",
    }
    rates = _safe_rename_cols(rates, rename_map)

    # 4) merge (date index)
    df = kospi.join([kosdaq, kospi200, fx], how="outer")
    df = df.join(rates, how="left")
    df = df.sort_index()
    df.index.name = "date"

    # 5) 간단 risk_on 예시(추세 기반) - 필요하면 나중에 규칙 강화
    # - kospi_close > kospi_sma_200 AND kosdaq_close > kosdaq_sma_200
    df["risk_on_trend"] = (
        (df["kospi_close"] > df["kospi_sma_200"]) &
        (df["kosdaq_close"] > df["kosdaq_sma_200"])
    ).astype("int")

    # 6) write sqlite
    print(f"[WRITE] {out_db}::{out_table} rows={len(df):,}")
    con = sqlite3.connect(out_db)
    cur = con.cursor()

    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {out_table} (
        date TEXT PRIMARY KEY
    )
    """)
    con.commit()

    # pandas to_sql (replace) 대신: 안전하게 재생성
    cur.execute(f"DROP TABLE IF EXISTS {out_table}")
    con.commit()
    df_out = df.reset_index()
    df_out["date"] = df_out["date"].dt.strftime("%Y-%m-%d")

    df_out.to_sql(out_table, con, index=False)
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{out_table}_date ON {out_table}(date)")
    con.commit()
    con.close()

    print("[DONE] market.db build completed.")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--out-db", required=True)
    p.add_argument("--out-table", default="market_daily")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--include-vkosp", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    build_market_db(
        out_db=args.out_db,
        out_table=args.out_table,
        start=args.start,
        end=args.end,
        include_vkosp=args.include_vkosp,
    )


if __name__ == "__main__":
    main()
