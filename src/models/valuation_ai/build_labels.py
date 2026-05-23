# build_labels.py ver 2026-05-06_001
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import now_ts, read_sql, write_table
from .config import FEATURE_TABLE, LABEL_TABLE, OUT_DB, PRICE_DB, REPORT_DIR

HORIZON_DAYS = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}


def _load_features(db: Path) -> pd.DataFrame:
    df = read_sql(db, f"SELECT asof_date, ticker, sector_bucket FROM {FEATURE_TABLE}", parse_dates=["asof_date"])
    if df.empty:
        raise SystemExit("no valuation features found; run build_features first")
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df


def _load_prices(tickers: list[str]) -> dict[str, pd.DataFrame]:
    placeholders = ",".join(["?"] * len(tickers))
    df = read_sql(
        PRICE_DB,
        f"""
        SELECT ticker, date, close
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND close IS NOT NULL
        ORDER BY ticker, date
        """,
        tickers,
        parse_dates=["date"],
    )
    if df.empty:
        raise SystemExit("no price rows for valuation labels")
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return {ticker: g.sort_values("date").reset_index(drop=True) for ticker, g in df.dropna(subset=["close"]).groupby("ticker")}


def _forward_metrics(price_frame: pd.DataFrame, asof: pd.Timestamp) -> dict[str, Any]:
    dates = price_frame["date"]
    idx_arr = np.flatnonzero(dates.values == np.datetime64(asof))
    if len(idx_arr) == 0:
        idx_arr = np.flatnonzero(dates.values <= np.datetime64(asof))
        if len(idx_arr) == 0:
            return {}
        idx = int(idx_arr[-1])
    else:
        idx = int(idx_arr[0])
    start_close = float(price_frame.iloc[idx]["close"])
    if start_close <= 0:
        return {}
    out: dict[str, Any] = {}
    closes = price_frame["close"].astype(float).to_numpy()
    for horizon, days in HORIZON_DAYS.items():
        end_idx = idx + days
        if end_idx < len(closes):
            out[f"fwd_ret_{horizon}"] = round(float(closes[end_idx] / start_close - 1.0), 6)
        else:
            out[f"fwd_ret_{horizon}"] = None
    dd_end = min(idx + HORIZON_DAYS["6m"], len(closes) - 1)
    if dd_end > idx:
        window = closes[idx : dd_end + 1]
        running_peak = np.maximum.accumulate(window)
        drawdown = window / running_peak - 1.0
        out["fwd_max_drawdown_6m"] = round(float(np.nanmin(drawdown)), 6)
    else:
        out["fwd_max_drawdown_6m"] = None
    sr_end = min(idx + HORIZON_DAYS["12m"], len(closes) - 1)
    if sr_end > idx + 20:
        window = closes[idx : sr_end + 1]
        rets = pd.Series(window).pct_change().dropna()
        if not rets.empty and float(rets.std()) > 0:
            out["fwd_sharpe_12m"] = round(float(rets.mean() / rets.std() * np.sqrt(252)), 6)
        else:
            out["fwd_sharpe_12m"] = None
    else:
        out["fwd_sharpe_12m"] = None
    return out


def build_labels(db: Path = OUT_DB) -> pd.DataFrame:
    features = _load_features(db)
    prices = _load_prices(sorted(features["ticker"].unique().tolist()))
    rows = []
    for row in features.itertuples(index=False):
        frame = prices.get(str(row.ticker))
        metrics = _forward_metrics(frame, pd.Timestamp(row.asof_date)) if frame is not None else {}
        rows.append(
            {
                "asof_date": pd.Timestamp(row.asof_date).strftime("%Y-%m-%d"),
                "ticker": row.ticker,
                "sector_bucket": row.sector_bucket,
                **metrics,
            }
        )
    out = pd.DataFrame(rows)
    sector = (
        out.groupby(["asof_date", "sector_bucket"], as_index=False)
        .agg(sector_fwd_ret_12m=("fwd_ret_12m", "median"))
    )
    out = out.merge(sector, on=["asof_date", "sector_bucket"], how="left")
    out["fwd_excess_ret_12m"] = pd.to_numeric(out["fwd_ret_12m"], errors="coerce") - pd.to_numeric(out["sector_fwd_ret_12m"], errors="coerce")

    out["label_outperform"] = np.nan
    out["label_underperform"] = np.nan
    for _, idx in out.groupby("asof_date").groups.items():
        vals = out.loc[idx, "fwd_excess_ret_12m"].dropna()
        if len(vals) < 20:
            continue
        high = vals.quantile(0.70)
        low = vals.quantile(0.30)
        out.loc[idx, "label_outperform"] = np.where(out.loc[idx, "fwd_excess_ret_12m"].notna(), (out.loc[idx, "fwd_excess_ret_12m"] >= high).astype(int), np.nan)
        out.loc[idx, "label_underperform"] = np.where(out.loc[idx, "fwd_excess_ret_12m"].notna(), (out.loc[idx, "fwd_excess_ret_12m"] <= low).astype(int), np.nan)

    out["label_overheated"] = np.where(
        out["fwd_ret_6m"].notna(),
        ((out["fwd_ret_6m"] < 0) & (out["fwd_max_drawdown_6m"].fillna(0) <= -0.15)).astype(int),
        np.nan,
    )
    out["label_value_creation"] = np.where(
        out["fwd_excess_ret_12m"].notna(),
        ((out["fwd_excess_ret_12m"] > 0) & (out["fwd_max_drawdown_6m"].fillna(0) > -0.20)).astype(int),
        np.nan,
    )
    out["created_at"] = now_ts()
    keep = [
        "asof_date",
        "ticker",
        "fwd_ret_1m",
        "fwd_ret_3m",
        "fwd_ret_6m",
        "fwd_ret_12m",
        "fwd_excess_ret_12m",
        "fwd_max_drawdown_6m",
        "fwd_sharpe_12m",
        "label_outperform",
        "label_underperform",
        "label_overheated",
        "label_value_creation",
        "created_at",
    ]
    out = out[keep].replace([np.inf, -np.inf], np.nan)
    write_table(db, LABEL_TABLE, out)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(REPORT_DIR / "valuation_labels_forward.csv", index=False, encoding="utf-8-sig")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build forward labels for AI-GROWTH-VALUATION-V01.")
    parser.add_argument("--db", default=str(OUT_DB))
    args = parser.parse_args()
    df = build_labels(Path(args.db))
    print({"status": "ok", "rows": int(len(df)), "labeled_12m": int(df["fwd_ret_12m"].notna().sum()), "out_db": args.db})


if __name__ == "__main__":
    main()
