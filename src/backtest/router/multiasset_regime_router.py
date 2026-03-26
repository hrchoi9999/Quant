from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.backtest.configs.router_config import RouterConfig


@dataclass(frozen=True)
class RouterDecision:
    detected_regime: str
    stock_model: str
    etf_model: str
    stock_weight: float
    etf_weight: float
    stock_fallback: str | None
    etf_fallback: str | None


def map_regime_value_to_mode(regime_value: float | int | None, cfg: RouterConfig) -> str:
    if regime_value is None or pd.isna(regime_value):
        return cfg.regime.fallback_mode
    value = float(regime_value)
    if value >= float(cfg.regime.risk_on_min):
        return 'risk_on'
    if value <= float(cfg.regime.risk_off_max):
        return 'risk_off'
    return 'neutral'


def build_regime_mode_series(regime_panel: pd.DataFrame, cfg: RouterConfig) -> pd.DataFrame:
    if regime_panel is None or regime_panel.empty:
        return pd.DataFrame(columns=['date', 'regime_value', 'mode'])
    work = regime_panel.copy()
    work['date'] = pd.to_datetime(work['date'])
    work['regime'] = pd.to_numeric(work['regime'], errors='coerce')
    work = work.dropna(subset=['date', 'regime'])
    daily = work.groupby('date', as_index=False)['regime'].median().rename(columns={'regime': 'regime_value'}).sort_values('date')
    daily['mode'] = daily['regime_value'].map(lambda x: map_regime_value_to_mode(x, cfg))
    return daily


def resolve_mode_for_date(mode_df: pd.DataFrame, dt: pd.Timestamp, fallback_mode: str) -> tuple[str, float | None]:
    if mode_df is None or mode_df.empty:
        return fallback_mode, None
    dates = pd.to_datetime(mode_df['date'])
    mask = dates <= pd.Timestamp(dt)
    if not bool(mask.any()):
        return fallback_mode, None
    row = mode_df.loc[mask].iloc[-1]
    value = row['regime_value']
    return str(row['mode']), (None if pd.isna(value) else float(value))


def build_router_decision(mode: str, cfg: RouterConfig, service_profile: str) -> RouterDecision:
    d = cfg.resolve_mode_config(mode=mode, service_profile=service_profile)
    return RouterDecision(
        detected_regime=mode,
        stock_model=str(d['stock_model']),
        etf_model=str(d['etf_model']),
        stock_weight=float(d['stock_weight']),
        etf_weight=float(d['etf_weight']),
        stock_fallback=d.get('stock_fallback'),
        etf_fallback=d.get('etf_fallback'),
    )
