# validate_regime_monotonicity.py ver 2026-01-29_001
"""
Validate regime monotonicity (predictive ordering test)

Goal:
- Check whether higher regime today corresponds to higher future returns.

Inputs:
- regime.db::regime_history (date, ticker, horizon, score, regime)
- price.db::prices_daily (ticker, date, close, ...)

Method:
1) For a given horizon (e.g., '3m'), take (date, ticker, regime) snapshot series.
2) Compute forward returns from price.db:
   fwd_ret_k = close[t+k] / close[t] - 1  (k = 21, 63, 126 by default)
3) Group by (date, regime) and compute equal-weight mean/median forward return.
4) Aggregate across dates, report overall mean/median by regime and a monotonicity score.

Outputs:
- Console summary
- CSV files in reports/regime_validate/
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import List, Dict

import numpy as np
import pandas as pd


def _log(msg: str) -> None:
    print(msg, flush=True)


def resolve_project_root(start: Path) -> Path:
    p = start.resolve()
    if p.is_file():
        p = p.parent
    for _ in range(12):
        if (p / "src").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return start.resolve()


def _ensure_ticker6(x: str) -> str:
    s = str(x).strip()
    if s.isdigit() and len(s) < 6:
        s = s.zfill(6)
    return s


def load_regime_panel(
    regime_db: str,
    regime_table: str,
    horizon: str,
    start: str,
    end: str,
    universe_file: str = "",
    ticker_col: str = "ticker",
) -> pd.DataFrame:
    tickers: List[str] = []
    if universe_file:
        uni = pd.read_csv(universe_file)
        if ticker_col not in uni.columns:
            raise RuntimeError(f"ticker_col not found: {ticker_col}")
        tickers = sorted({_ensure_ticker6(x) for x in uni[ticker_col].dropna().astype(str).tolist()})

    con = sqlite3.connect(regime_db)
    try:
        if tickers:
            out = []
            chunk = 900
            for i in range(0, len(tickers), chunk):
                ct = tickers[i : i + chunk]
                ph = ",".join(["?"] * len(ct))
                sql = f"""
                    SELECT date, ticker, regime
                    FROM {regime_table}
                    WHERE horizon = ?
                      AND date >= ? AND date <= ?
                      AND ticker IN ({ph})
                """
                params = [horizon, start, end] + ct
                out.extend(con.execute(sql, params).fetchall())
            df = pd.DataFrame(out, columns=["date", "ticker", "regime"])
        else:
            sql = f"""
                SELECT date, ticker, regime
                FROM {regime_table}
                WHERE horizon = ?
                  AND date >= ? AND date <= ?
            """
            df = pd.read_sql_query(sql, con, params=(horizon, start, end))

    finally:
        con.close()

    if df.empty:
        raise RuntimeError("regime panel empty for given range/horizon/universe")

    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].map(_ensure_ticker6)
    df["regime"] = pd.to_numeric(df["regime"], errors="coerce").astype("Int64")
    df = df[df["regime"].notna()].copy()
    df["regime"] = df["regime"].astype(int)
    return df


def load_prices(
    price_db: str,
    price_table: str,
    tickers: List[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    con = sqlite3.connect(price_db)
    try:
        out = []
        chunk = 900
        for i in range(0, len(tickers), chunk):
            ct = tickers[i : i + chunk]
            ph = ",".join(["?"] * len(ct))
            sql = f"""
                SELECT date, ticker, close
                FROM {price_table}
                WHERE date >= ? AND date <= ?
                  AND ticker IN ({ph})
                ORDER BY date ASC
            """
            params = [start, end] + ct
            out.extend(con.execute(sql, params).fetchall())
        df = pd.DataFrame(out, columns=["date", "ticker", "close"])
    finally:
        con.close()

    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].map(_ensure_ticker6)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df[df["close"].notna()].copy()
    return df


def compute_forward_returns(price_df: pd.DataFrame, fwd_days: List[int]) -> pd.DataFrame:
    """
    price_df: columns [date, ticker, close] daily rows.
    returns: columns [date, ticker, fwd_21, fwd_63, ...] aligned to date t.
    """
    price_df = price_df.sort_values(["ticker", "date"]).copy()
    g = price_df.groupby("ticker", group_keys=False)

    out = price_df[["date", "ticker", "close"]].copy()
    for k in fwd_days:
        fwd = g["close"].shift(-k) / price_df["close"] - 1.0
        out[f"fwd_{k}"] = fwd

    # drop rows where all forward returns missing
    keep_cols = [f"fwd_{k}" for k in fwd_days]
    out = out.dropna(subset=keep_cols, how="all")
    return out[["date", "ticker"] + keep_cols]


def summarize_by_regime(df: pd.DataFrame, fwd_days: List[int]) -> Dict[str, pd.DataFrame]:
    """
    df: columns [date, ticker, regime, fwd_21, fwd_63, ...]
    Returns:
      - per_date: date x regime mean returns (each fwd)
      - overall: regime-level mean/median + sample sizes
    """
    res = {}

    # per-date equal-weight mean by regime
    for k in fwd_days:
        col = f"fwd_{k}"
        piv = (
            df.groupby(["date", "regime"])[col]
            .mean()
            .unstack("regime")
            .sort_index()
        )
        res[f"per_date_mean_{k}"] = piv

    # overall summary by regime (pool all observations)
    rows = []
    for r in sorted(df["regime"].dropna().unique()):
        sub = df[df["regime"] == r]
        row = {"regime": int(r), "n": int(len(sub))}
        for k in fwd_days:
            col = f"fwd_{k}"
            row[f"mean_{k}"] = float(sub[col].mean())
            row[f"median_{k}"] = float(sub[col].median())
        rows.append(row)

    overall = pd.DataFrame(rows).sort_values("regime")
    res["overall"] = overall
    return res


def monotonic_score(overall: pd.DataFrame, k: int, metric: str = "mean") -> float:
    """
    Returns a simple monotonicity score:
    - Spearman correlation between regime (0..4) and metric_{k} across 5 points.
    """
    col = f"{metric}_{k}"
    x = overall["regime"].to_numpy(dtype=float)
    y = overall[col].to_numpy(dtype=float)
    if len(x) < 2:
        return float("nan")
    # Spearman on 5 points: compute rank corr manually (stable enough)
    xr = pd.Series(x).rank().to_numpy()
    yr = pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(xr, yr)[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime-db", required=True)
    ap.add_argument("--regime-table", default="regime_history")
    ap.add_argument("--price-db", required=True)
    ap.add_argument("--price-table", default="prices_daily")
    ap.add_argument("--horizon", default="3m", help="regime horizon to validate: 1y/6m/3m")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--fwd-days", default="21,63", help="comma-separated forward days")
    ap.add_argument("--universe-file", default="")
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--outdir", default=r".\reports\regime_validate")
    args = ap.parse_args()

    project_root = resolve_project_root(Path.cwd())
    os.chdir(project_root)

    fwd_days = [int(x.strip()) for x in args.fwd_days.split(",") if x.strip()]
    outdir = (Path(project_root) / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    # regime panel
    reg = load_regime_panel(
        regime_db=args.regime_db,
        regime_table=args.regime_table,
        horizon=args.horizon,
        start=args.start,
        end=args.end,
        universe_file=args.universe_file,
        ticker_col=args.ticker_col,
    )
    tickers = sorted(reg["ticker"].unique().tolist())
    _log(f"[INFO] regime rows={len(reg):,} | tickers={len(tickers):,} | horizon={args.horizon}")

    # prices range must cover end + max(fwd_days) shift; easiest: extend end a bit
    # Here we load until args.end and accept that some tail dates will drop due to shift.
    px = load_prices(
        price_db=args.price_db,
        price_table=args.price_table,
        tickers=tickers,
        start=args.start,
        end=args.end,
    )
    _log(f"[INFO] price rows={len(px):,}")

    fwd = compute_forward_returns(px, fwd_days)
    _log(f"[INFO] fwd rows(after shift)={len(fwd):,}")

    merged = reg.merge(fwd, on=["date", "ticker"], how="inner")
    _log(f"[INFO] merged rows={len(merged):,}")

    res = summarize_by_regime(merged, fwd_days)
    overall = res["overall"]

    stamp = f"{args.horizon}_{args.start}_{args.end}"
    overall_path = outdir / f"regime_overall_{stamp}.csv"
    overall.to_csv(overall_path, index=False, encoding="utf-8-sig")

    _log("\n" + "=" * 80)
    _log(f"[OVERALL] horizon={args.horizon} | range={args.start}..{args.end}")
    _log("=" * 80)
    _log(overall.to_string(index=False))
    _log("")

    for k in fwd_days:
        s_mean = monotonic_score(overall, k, metric="mean")
        s_med = monotonic_score(overall, k, metric="median")
        _log(f"[MONO] fwd_{k}: spearman(mean)={s_mean:.3f} | spearman(median)={s_med:.3f}")

        per_date = res[f"per_date_mean_{k}"]
        per_date_path = outdir / f"regime_per_date_mean_{k}_{stamp}.csv"
        per_date.to_csv(per_date_path, encoding="utf-8-sig")
        _log(f"[SAVE] {per_date_path}")

    _log(f"[SAVE] {overall_path}")
    _log("[INFO] done.")


if __name__ == "__main__":
    main()
