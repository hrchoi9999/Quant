# asset_filters.py ver 2026-03-17_001
from __future__ import annotations

import pandas as pd


def filter_instruments_by_asset_class(df: pd.DataFrame, asset_class: str | None = None, asset_type: str | None = None) -> pd.DataFrame:
    out = df.copy()
    if asset_type:
        out = out[out["asset_type"].astype(str) == str(asset_type)]
    if asset_class and "asset_class" in out.columns:
        out = out[out["asset_class"].astype(str) == str(asset_class)]
    return out.reset_index(drop=True)


def filter_etf_by_group(df: pd.DataFrame, group_key: str | None = None, core_only: bool = False) -> pd.DataFrame:
    out = df.copy()
    if "asset_type" in out.columns:
        out = out[out["asset_type"].astype(str) == "ETF"]
    if group_key and "group_key" in out.columns:
        out = out[out["group_key"].astype(str) == str(group_key)]
    if core_only and "core_eligible" in out.columns:
        out = out[out["core_eligible"].astype(bool)]
    return out.reset_index(drop=True)
