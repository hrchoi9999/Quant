# compare_summary_equity.py ver 2026-02-03_001
"""
목적
- summary CSV의 (cagr, mdd, sharpe 등) 값이 equity CSV로 재계산한 값과 일치하는지 검증
- 불일치하면 '어떤 지표가 얼마나 다른지'를 한 눈에 보여줌

사용 예
python .\tools\compare_summary_equity.py ^
  --equity  .\reports\backtest_regime\regime_bt_equity_....csv ^
  --summary .\reports\backtest_regime\regime_bt_summary_....csv
"""
from __future__ import annotations
import argparse, math
import pandas as pd
import numpy as np

TRADING_DAYS=252.0

def calc_cagr(eq: pd.Series, dates: pd.Series) -> float:
    dates = pd.to_datetime(dates)
    years = (dates.iloc[-1]-dates.iloc[0]).days/365.25
    if years<=0: return float("nan")
    return float((eq.iloc[-1]/eq.iloc[0])**(1.0/years)-1.0)

def calc_mdd(eq: pd.Series)->float:
    return float((eq/eq.cummax()-1.0).min())

def calc_sharpe(r: pd.Series)->float:
    r=r.dropna()
    if len(r)<2: return float("nan")
    mu=float(r.mean()); sd=float(r.std(ddof=1))
    if sd==0: return float("nan")
    return float((mu/sd)*math.sqrt(TRADING_DAYS))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--equity", required=True)
    ap.add_argument("--summary", required=True)
    args=ap.parse_args()

    eq=pd.read_csv(args.equity)
    su=pd.read_csv(args.summary)

    if "date" not in eq.columns or "equity" not in eq.columns:
        raise SystemExit("equity csv must have date,equity")
    eq["date"]=pd.to_datetime(eq["date"])
    eq=eq.sort_values("date").reset_index(drop=True)
    if "port_ret" in eq.columns:
        r=eq["port_ret"].astype(float)
    else:
        r=eq["equity"].astype(float).pct_change().fillna(0.0)

    eq_norm=eq["equity"].astype(float)/float(eq["equity"].iloc[0])
    calc={
        "cagr": calc_cagr(eq_norm, eq["date"]),
        "mdd": calc_mdd(eq_norm),
        "sharpe": calc_sharpe(r),
        "avg_daily_ret": float(r.mean()),
        "vol_daily": float(r.std(ddof=1)),
        "start": eq["date"].iloc[0].date().isoformat(),
        "end": eq["date"].iloc[-1].date().isoformat(),
        "days": int(len(eq)),
        "final_equity": float(eq_norm.iloc[-1])
    }

    # summary 첫 행 기준
    s0=su.iloc[0].to_dict()
    keys=["cagr","mdd","sharpe","avg_daily_ret","vol_daily"]
    rows=[]
    for k in keys:
        if k in s0:
            rows.append([k, float(s0[k]), float(calc[k]), float(calc[k])-float(s0[k])])
        else:
            rows.append([k, float("nan"), float(calc[k]), float("nan")])
    out=pd.DataFrame(rows, columns=["metric","summary","recalc_from_equity","diff(recalc-summary)"])
    print("[EQUITY]", args.equity)
    print("[SUMMARY]", args.summary)
    print("period:", calc["start"], "->", calc["end"], "days=", calc["days"], "final_equity=", round(calc["final_equity"],6))
    print(out.to_string(index=False))

if __name__=="__main__":
    main()
