# analyze_equity_gate_regime.py ver 2026-02-03_001
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def calc_mdd(equity: pd.Series) -> float:
    eq = equity.astype(float)
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return float(dd.min())


def calc_cagr(equity: pd.Series, dates: pd.Series) -> float:
    eq = equity.astype(float)
    d0 = pd.to_datetime(dates.iloc[0])
    d1 = pd.to_datetime(dates.iloc[-1])
    years = (d1 - d0).days / 365.25
    if years <= 0:
        return np.nan
    return float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1)


def calc_sharpe(port_ret: pd.Series, ann_factor: int = 252) -> float:
    r = port_ret.astype(float)
    mu = r.mean()
    sd = r.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return np.nan
    return float((mu / sd) * np.sqrt(ann_factor))


def chain_segment_equity(df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    """
    방식 A: 해당 구간의 일별 수익률만 이어붙여 '가상 equity' 생성
    - "그 구간에만 투자했다면" 성과를 보기 좋음
    """
    seg = df.loc[mask, ["date", "port_ret"]].copy()
    if seg.empty:
        return seg.assign(seg_equity=pd.Series(dtype=float))
    seg["seg_equity"] = (1.0 + seg["port_ret"].astype(float)).cumprod()
    return seg


def summarize(df: pd.DataFrame, label: str, mask: pd.Series) -> dict:
    seg = df.loc[mask].copy()
    if seg.empty:
        return {"segment": label, "days": 0}

    out = {
        "segment": label,
        "days": int(len(seg)),
        "start": str(seg["date"].iloc[0]),
        "end": str(seg["date"].iloc[-1]),
        "gate_on_pct": float((seg["market_ok"] == 1).mean()),
        "avg_cash_weight": float(seg["cash_weight"].mean()),
        "avg_n_holdings": float(seg["n_holdings"].mean()),
        "avg_regime_good_ratio": float(seg["regime_good_ratio"].dropna().mean()) if seg["regime_good_ratio"].notna().any() else np.nan,
    }

    # 전체 운용 equity 기준(방식 B 성격)
    out["mdd_fullcurve"] = calc_mdd(seg["equity"])
    out["cagr_fullcurve"] = calc_cagr(seg["equity"], seg["date"])
    out["sharpe_fullcurve"] = calc_sharpe(seg["port_ret"])

    # 구간 수익률만 이어붙인 가상 equity 기준(방식 A)
    seg2 = chain_segment_equity(df, mask)
    if not seg2.empty:
        out["mdd_segment_chain"] = calc_mdd(seg2["seg_equity"])
        out["cagr_segment_chain"] = calc_cagr(seg2["seg_equity"], seg2["date"])
        out["sharpe_segment_chain"] = calc_sharpe(seg2["port_ret"])
    else:
        out["mdd_segment_chain"] = np.nan
        out["cagr_segment_chain"] = np.nan
        out["sharpe_segment_chain"] = np.nan

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity", required=True, help="regime_bt_equity_*.csv 경로")
    ap.add_argument("--outdir", default="", help="출력 폴더(기본: equity 파일과 동일 폴더)")
    ap.add_argument("--regime-th", type=float, default=0.5, help="regime_good_ratio 임계값(기본 0.5)")
    args = ap.parse_args()

    equity_path = Path(args.equity).resolve()
    df = pd.read_csv(equity_path)
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)

    # 기본 마스크
    mask_all = pd.Series(True, index=df.index)

    # 워밍업(시장 SMA NaN) 구간
    mask_warmup = df["market_sma"].isna()

    # Gate ON/OFF (워밍업은 market_ok=0로 들어가 있으니, 별도 분리)
    mask_gate_on = (df["market_ok"] == 1)
    mask_gate_off = (df["market_ok"] == 0) & (~mask_warmup)

    # Regime GOOD/BAD (현금/워밍업은 NaN이라 자동 제외될 수 있음)
    th = float(args.regime_th)
    mask_reg_good = df["regime_good_ratio"].notna() & (df["regime_good_ratio"] >= th)
    mask_reg_bad = df["regime_good_ratio"].notna() & (df["regime_good_ratio"] < th)

    rows = []
    rows.append(summarize(df, "ALL", mask_all))
    rows.append(summarize(df, "WARMUP(market_sma NaN)", mask_warmup))
    rows.append(summarize(df, "GATE_ON", mask_gate_on))
    rows.append(summarize(df, "GATE_OFF(ex_warmup)", mask_gate_off))
    rows.append(summarize(df, f"REGIME_GOOD(ratio>={th})", mask_reg_good))
    rows.append(summarize(df, f"REGIME_BAD(ratio<{th})", mask_reg_bad))

    # 2x2 (Gate ON/OFF × Regime GOOD/BAD)
    rows.append(summarize(df, f"GATE_ON & REGIME_GOOD(ratio>={th})", mask_gate_on & mask_reg_good))
    rows.append(summarize(df, f"GATE_ON & REGIME_BAD(ratio<{th})", mask_gate_on & mask_reg_bad))
    rows.append(summarize(df, f"GATE_OFF & REGIME_GOOD(ratio>={th})", mask_gate_off & mask_reg_good))
    rows.append(summarize(df, f"GATE_OFF & REGIME_BAD(ratio<{th})", mask_gate_off & mask_reg_bad))

    out_df = pd.DataFrame(rows)

    outdir = Path(args.outdir).resolve() if args.outdir else equity_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    stem = equity_path.stem
    out_csv = outdir / f"{stem}__segment_report_th{str(th).replace('.','p')}.csv"
    out_df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    print("[SAVE]", out_csv)
    print(out_df.to_string(index=False))


if __name__ == "__main__":
    main()
