# analyze_equity_windows.py ver 2026-02-03_001
"""
목적
- equity CSV(일자별 포트폴리오 수익률/누적자산)에서 기간별(1y/3y/5y) CAGR, MDD를 계산
- 가능하면 gate(시장 게이트) ON/OFF 구간별로도 동일 지표를 계산

입력
- --equity: regime_bt_equity_*.csv (필수)
  * 필수 컬럼: date, equity
  * 권장 컬럼: port_ret (없으면 equity로부터 일간수익률을 역산)
  * 선택 컬럼: market_ok (0/1 또는 True/False) -> gate 구간 분석에 사용

출력
- *_windows_report.csv : window/segment별 CAGR/MDD/Sharpe 등

사용 예
python .\tools\analyze_equity_windows.py ^
  --equity .\reports\backtest_regime\regime_bt_equity_3m_S2_RBW_top50_GR43_SMA140_MG1_20131014_20260129.csv ^
  --out   .\reports\backtest_regime\equity_windows_report.csv
"""
from __future__ import annotations
import argparse
import math
from dataclasses import dataclass
from typing import Optional, Dict, List

import numpy as np
import pandas as pd


TRADING_DAYS = 252.0


def _to_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    # 0/1, "0"/"1", "True"/"False"
    return s.astype(str).str.lower().isin(["1", "true", "t", "yes", "y"])


def calc_cagr_from_equity(eq: pd.Series, dates: pd.Series) -> float:
    if len(eq) < 2:
        return float("nan")
    start = pd.to_datetime(dates.iloc[0])
    end = pd.to_datetime(dates.iloc[-1])
    years = (end - start).days / 365.25
    if years <= 0:
        return float("nan")
    if float(eq.iloc[0]) <= 0:
        return float("nan")
    return float((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0)


def calc_mdd(eq: pd.Series) -> float:
    if len(eq) < 2:
        return float("nan")
    dd = (eq / eq.cummax()) - 1.0
    return float(dd.min())


def calc_sharpe_from_ret(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 2:
        return float("nan")
    mu = float(r.mean())
    sd = float(r.std(ddof=1))
    if sd == 0:
        return float("nan")
    return float((mu / sd) * math.sqrt(TRADING_DAYS))


def build_equity_from_returns(r: pd.Series) -> pd.Series:
    return (1.0 + r.fillna(0.0)).cumprod()


def get_port_ret(df: pd.DataFrame) -> pd.Series:
    if "port_ret" in df.columns:
        return df["port_ret"].astype(float)
    # port_ret 없으면 equity로 역산
    eq = df["equity"].astype(float)
    r = eq.pct_change().fillna(0.0)
    return r


def window_slice(df: pd.DataFrame, years_back: int) -> pd.DataFrame:
    end = df["date"].max()
    start_target = end - pd.DateOffset(years=years_back)
    w = df[df["date"] >= start_target].copy()
    return w


def compute_segment_metrics(w: pd.DataFrame, seg_name: str, mask: Optional[pd.Series]) -> Dict[str, float]:
    r = w["port_ret"].copy()
    if mask is not None:
        mask = mask.reindex(w.index)
        r = r.where(mask, 0.0)

    eq = build_equity_from_returns(r)
    cagr = calc_cagr_from_equity(eq, w["date"])
    mdd = calc_mdd(eq)
    sharpe = calc_sharpe_from_ret(r)

    return {
        "segment": seg_name,
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "final_equity": float(eq.iloc[-1]) if len(eq) else float("nan"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity", required=True, help="equity csv path")
    ap.add_argument("--out", default="", help="output csv path (optional)")
    args = ap.parse_args()

    df = pd.read_csv(args.equity)
    if "date" not in df.columns:
        raise SystemExit("equity CSV must have 'date' column")
    if "equity" not in df.columns:
        raise SystemExit("equity CSV must have 'equity' column")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["port_ret"] = get_port_ret(df)

    has_gate = "market_ok" in df.columns
    if has_gate:
        df["market_ok"] = _to_bool_series(df["market_ok"])

    rows: List[Dict[str, object]] = []
    for y in [1, 3, 5]:
        w = window_slice(df, y)
        if len(w) < 2:
            continue
        base = {
            "window": f"{y}y",
            "start": w["date"].iloc[0].date().isoformat(),
            "end": w["date"].iloc[-1].date().isoformat(),
            "days": int(len(w)),
        }

        # ALL
        m_all = compute_segment_metrics(w, "ALL", None)
        rows.append({**base, **m_all})

        if has_gate:
            mask_on = w["market_ok"]
            mask_off = ~w["market_ok"]
            rows.append({**base, **compute_segment_metrics(w, "GATE_ON", mask_on)})
            rows.append({**base, **compute_segment_metrics(w, "GATE_OFF", mask_off)})

    out_df = pd.DataFrame(rows)
    if not args.out:
        args.out = args.equity.replace(".csv", "__windows_report.csv")
    out_df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print("[SAVE]", args.out)
    print(out_df.to_string(index=False))


if __name__ == "__main__":
    main()
