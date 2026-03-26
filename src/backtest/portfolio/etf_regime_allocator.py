from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from src.backtest.configs.etf_allocation_config import EtfAllocationConfig


@dataclass(frozen=True)
class AllocationSelection:
    mode: str
    weights: dict[str, float]
    selection_df: pd.DataFrame


def map_regime_value_to_mode(regime_value: float | int | None, cfg: EtfAllocationConfig) -> str:
    if regime_value is None or pd.isna(regime_value):
        return cfg.regime.fallback_mode
    value = float(regime_value)
    if value >= float(cfg.regime.risk_on_min):
        return "risk_on"
    if value <= float(cfg.regime.risk_off_max):
        return "risk_off"
    return "neutral"


def build_regime_mode_series(
    regime_panel: pd.DataFrame,
    cfg: EtfAllocationConfig,
    force_mode: str | None = None,
) -> pd.DataFrame:
    if force_mode:
        if regime_panel is None or regime_panel.empty:
            return pd.DataFrame(columns=["date", "regime_value", "mode"])
        dates = (
            pd.Series(pd.to_datetime(regime_panel["date"]))
            .sort_values()
            .drop_duplicates()
            .reset_index(drop=True)
        )
        return pd.DataFrame(
            {
                "date": dates,
                "regime_value": pd.NA,
                "mode": [str(force_mode).lower()] * len(dates),
            }
        )

    if regime_panel is None or regime_panel.empty:
        return pd.DataFrame(columns=["date", "regime_value", "mode"])

    work = regime_panel.copy()
    work["date"] = pd.to_datetime(work["date"])
    work["regime"] = pd.to_numeric(work["regime"], errors="coerce")
    work = work.dropna(subset=["date", "regime"])
    daily = (
        work.groupby("date", as_index=False)["regime"]
        .median()
        .rename(columns={"regime": "regime_value"})
        .sort_values("date")
    )
    daily["mode"] = daily["regime_value"].map(lambda x: map_regime_value_to_mode(x, cfg))
    return daily


def resolve_mode_for_date(
    mode_df: pd.DataFrame,
    dt: pd.Timestamp,
    fallback_mode: str,
) -> tuple[str, float | None]:
    if mode_df is None or mode_df.empty:
        return fallback_mode, None
    dates = pd.to_datetime(mode_df["date"])
    mask = dates <= pd.Timestamp(dt)
    if not bool(mask.any()):
        return fallback_mode, None
    row = mode_df.loc[mask].iloc[-1]
    value = row["regime_value"]
    return str(row["mode"]), (None if pd.isna(value) else float(value))


def allocate_group_representatives(
    *,
    core_df: pd.DataFrame,
    mode: str,
    cfg: EtfAllocationConfig,
    available_tickers: Iterable[str] | None = None,
) -> AllocationSelection:
    mode_weights = cfg.mode_weights(mode)
    available = {str(t).zfill(6) for t in (available_tickers or [])}

    meta = core_df.copy()
    meta["ticker"] = meta["ticker"].astype(str).str.zfill(6)
    meta["liquidity_20d_value"] = pd.to_numeric(meta["liquidity_20d_value"], errors="coerce").fillna(0.0)

    rows: list[dict[str, object]] = []
    final_weights: dict[str, float] = {}
    residual_cash = 0.0

    for group_key, target_weight in mode_weights.items():
        group_key = str(group_key)
        target_weight = float(target_weight)
        if group_key.upper() == "CASH":
            residual_cash += target_weight
            rows.append(
                {
                    "group_key": "CASH",
                    "ticker": "CASH",
                    "name": "CASH",
                    "target_group_weight": target_weight,
                    "assigned_weight": target_weight,
                    "selected": True,
                    "available": True,
                    "liquidity_20d_value": 0.0,
                }
            )
            continue

        group = meta.loc[meta["group_key"].astype(str) == group_key].copy()
        if available:
            group["available"] = group["ticker"].isin(available)
            group = group.loc[group["available"]].copy()
        else:
            group["available"] = True

        if group.empty:
            if cfg.execution.missing_group_to_cash:
                residual_cash += target_weight
            rows.append(
                {
                    "group_key": group_key,
                    "ticker": "",
                    "name": "",
                    "target_group_weight": target_weight,
                    "assigned_weight": 0.0,
                    "selected": False,
                    "available": False,
                    "liquidity_20d_value": 0.0,
                }
            )
            continue

        picked = group.sort_values(["liquidity_20d_value", "ticker"], ascending=[False, True]).iloc[0]
        ticker = str(picked["ticker"]).zfill(6)
        final_weights[ticker] = final_weights.get(ticker, 0.0) + target_weight
        rows.append(
            {
                "group_key": group_key,
                "ticker": ticker,
                "name": str(picked.get("name", "")),
                "target_group_weight": target_weight,
                "assigned_weight": target_weight,
                "selected": True,
                "available": True,
                "liquidity_20d_value": float(picked.get("liquidity_20d_value", 0.0) or 0.0),
            }
        )

    if residual_cash > 0:
        final_weights["CASH"] = final_weights.get("CASH", 0.0) + residual_cash

    return AllocationSelection(mode=mode, weights=final_weights, selection_df=pd.DataFrame(rows))
