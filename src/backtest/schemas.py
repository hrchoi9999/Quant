# schemas.py ver 2026-02-09_001
from __future__ import annotations

from typing import Dict, Optional, List
import pandas as pd


def attach_market_col(df: Optional[pd.DataFrame], market_map: Dict[str, str], *, ticker_col: str = "ticker", out_col: str = "market") -> Optional[pd.DataFrame]:
    if df is None:
        return None
    if df.empty:
        if out_col not in df.columns:
            df[out_col] = ""
        return df
    out = df.copy()
    if ticker_col not in out.columns:
        # nothing to do
        if out_col not in out.columns:
            out[out_col] = ""
        return out
    out[out_col] = out[ticker_col].astype(str).map(market_map).fillna("")
    return out


def sort_snapshot_by_return(df: Optional[pd.DataFrame], *, return_col: str = "return") -> Optional[pd.DataFrame]:
    if df is None:
        return None
    if df.empty or return_col not in df.columns:
        return df
    out = df.copy()
    out[return_col] = pd.to_numeric(out[return_col], errors="coerce")
    out = out.sort_values(by=[return_col], ascending=False, kind="mergesort").reset_index(drop=True)
    return out


def verify_snapshot_sorted_by_return(df: Optional[pd.DataFrame], *, return_col: str = "return") -> None:
    if df is None or df.empty or return_col not in df.columns:
        return
    vals = pd.to_numeric(df[return_col], errors="coerce").fillna(float("-inf")).tolist()
    for i in range(1, len(vals)):
        if vals[i] > vals[i-1] + 1e-12:
            raise ValueError(f"Snapshot not sorted by {return_col} desc at idx={i}: {vals[i-1]} < {vals[i]}")


def make_trades_c(trades_df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Closed (round-trip) trades table, compatible with v4 output."""
    if trades_df is None or trades_df.empty:
        return None
    if "status" not in trades_df.columns:
        return None
    tdf_c = trades_df[trades_df["status"].astype(str).str.upper() == "CLOSED"].copy()
    keep_cols = ["trade_id","ticker","name","buy_date","buy_price","sell_date","sell_price","holding_days","return","return_pct","status"]
    keep_cols = [c for c in keep_cols if c in tdf_c.columns]
    if keep_cols:
        tdf_c = tdf_c[keep_cols].copy()
    return tdf_c
