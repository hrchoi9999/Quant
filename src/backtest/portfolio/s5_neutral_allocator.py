from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from src.backtest.configs.s5_neutral_config import S5NeutralConfig


@dataclass(frozen=True)
class S5AllocationResult:
    weights: dict[str, float]
    selection_df: pd.DataFrame
    diagnostics: dict[str, float | bool | str | None]


def _eligible_group(core_df: pd.DataFrame, group_key: str, available: set[str]) -> pd.DataFrame:
    group = core_df.loc[core_df['group_key'].astype(str) == str(group_key)].copy()
    if group.empty:
        return group
    group['ticker'] = group['ticker'].astype(str).str.zfill(6)
    if available:
        group = group.loc[group['ticker'].isin(available)].copy()
    group = group.loc[~pd.to_numeric(group.get('is_inverse', 0), errors='coerce').fillna(0).astype(int).astype(bool)]
    group = group.loc[~pd.to_numeric(group.get('is_leveraged', 0), errors='coerce').fillna(0).astype(int).astype(bool)]
    group['liquidity_20d_value'] = pd.to_numeric(group['liquidity_20d_value'], errors='coerce').fillna(0.0)
    return group


def _pick_top_liquidity(group: pd.DataFrame) -> tuple[str, str, float] | None:
    if group is None or group.empty:
        return None
    row = group.sort_values(['liquidity_20d_value', 'ticker'], ascending=[False, True]).iloc[0]
    return str(row['ticker']).zfill(6), str(row.get('name', '')), float(row.get('liquidity_20d_value', 0.0) or 0.0)


def _rsi(series: pd.Series, window: int) -> float | None:
    s = pd.to_numeric(series, errors='coerce').dropna()
    if len(s) <= window:
        return None
    delta = s.diff().dropna()
    up = delta.clip(lower=0).tail(window).mean()
    down = (-delta.clip(upper=0)).tail(window).mean()
    if down == 0:
        return 100.0
    rs = up / down
    return 100.0 - (100.0 / (1.0 + rs))


def _broad_metrics(close_wide: pd.DataFrame, ticker: str | None, dt: pd.Timestamp, cfg: S5NeutralConfig) -> dict[str, float | bool | None]:
    if not ticker or ticker not in close_wide.columns:
        return {'ret_20d': None, 'vol_short': None, 'vol_long': None, 'rsi': None, 'below_lower_band': None, 'rebound': None}
    px = pd.to_numeric(close_wide[ticker], errors='coerce').dropna()
    px = px.loc[px.index <= pd.Timestamp(dt)]
    if len(px) < max(cfg.signals.lookback_vol_long + 2, cfg.signals.boll_window + 2):
        return {'ret_20d': None, 'vol_short': None, 'vol_long': None, 'rsi': None, 'below_lower_band': None, 'rebound': None}
    ret = px.pct_change(fill_method=None)
    ret_20d = float(px.iloc[-1] / px.iloc[-1 - cfg.signals.lookback_vol_long] - 1.0)
    vol_short = float(ret.tail(cfg.signals.lookback_vol_short).std(ddof=0))
    vol_long = float(ret.tail(cfg.signals.lookback_vol_long).std(ddof=0))
    rsi = _rsi(px, cfg.signals.rsi_window)
    ma = float(px.tail(cfg.signals.boll_window).mean())
    sd = float(px.tail(cfg.signals.boll_window).std(ddof=0))
    lower = ma - cfg.signals.boll_k * sd
    below_lower = bool(float(px.iloc[-1]) <= lower)
    rebound = bool(len(px) >= 2 and float(px.iloc[-2]) <= lower and float(px.iloc[-1]) > float(px.iloc[-2]))
    return {'ret_20d': ret_20d, 'vol_short': vol_short, 'vol_long': vol_long, 'rsi': rsi, 'below_lower_band': below_lower, 'rebound': rebound}


def _apply_shift(weights: dict[str, float], to_key: str, amount: float, from_keys: list[str]) -> None:
    remaining = max(0.0, float(amount))
    for src in from_keys:
        if remaining <= 0:
            break
        avail = max(0.0, float(weights.get(src, 0.0)))
        take = min(avail, remaining)
        if take <= 0:
            continue
        weights[src] = avail - take
        remaining -= take
    moved = max(0.0, float(amount)) - remaining
    weights[to_key] = float(weights.get(to_key, 0.0)) + moved


def _clip_and_normalize(weights: dict[str, float], cfg: S5NeutralConfig) -> dict[str, float]:
    out = {k: max(0.0, float(v)) for k, v in weights.items()}
    for key, min_v in cfg.bounds.min_weights.items():
        out[key] = max(float(min_v), float(out.get(key, 0.0)))
    for key, max_v in cfg.bounds.max_weights.items():
        out[key] = min(float(max_v), float(out.get(key, 0.0)))
    total = sum(out.values())
    if total <= 0:
        out['CASH'] = 1.0
        total = 1.0
    out = {k: float(v) / total for k, v in out.items()}
    total = sum(out.values())
    if abs(total - 1.0) > 1e-10:
        out['CASH'] = float(out.get('CASH', 0.0)) + (1.0 - total)
    return out


def allocate_s5_neutral(
    *,
    core_df: pd.DataFrame,
    close_wide: pd.DataFrame,
    asof: pd.Timestamp,
    cfg: S5NeutralConfig,
    available_tickers: Iterable[str] | None = None,
) -> S5AllocationResult:
    available = {str(t).zfill(6) for t in (available_tickers or [])}
    groups = {
        'equity_kr_broad': _eligible_group(core_df, cfg.signals.broad_group, available),
        'equity_low_vol': _eligible_group(core_df, cfg.signals.low_vol_group, available),
        'equity_dividend': _eligible_group(core_df, cfg.signals.dividend_group, available),
        'equity_covered_call': _eligible_group(core_df, cfg.signals.covered_call_group, available),
        'bond_short': _eligible_group(core_df, cfg.signals.fallback_group, available),
    }
    picks = {k: _pick_top_liquidity(v) for k, v in groups.items() if v is not None and not v.empty}

    broad_ticker = picks.get('equity_kr_broad', (None, '', 0.0))[0]
    m = _broad_metrics(close_wide, broad_ticker, asof, cfg)
    adx_low = m['ret_20d'] is not None and abs(float(m['ret_20d'])) <= float(cfg.signals.adx_like_abs_ret_20d)
    vol_contraction = (m['vol_short'] is not None and m['vol_long'] is not None and float(m['vol_short']) <= float(m['vol_long']) * float(cfg.signals.vol_contraction_ratio))
    oversold = (m['rsi'] is not None and float(m['rsi']) <= float(cfg.signals.oversold_rsi_threshold)) or bool(m['below_lower_band'])
    rebound = bool(m['rebound']) or (m['rsi'] is not None and float(m['rsi']) >= float(cfg.signals.rebound_rsi_threshold) and m['ret_20d'] is not None and float(m['ret_20d']) > -0.03)
    uncertainty = (m['vol_long'] is not None and float(m['vol_long']) >= float(cfg.signals.uncertainty_vol_threshold)) or (m['ret_20d'] is not None and abs(float(m['ret_20d'])) >= 0.08)

    weights = dict(cfg.base.weights)
    if adx_low:
        _apply_shift(weights, 'equity_low_vol', cfg.signals.low_vol_boost, ['equity_kr_broad', 'CASH'])
        _apply_shift(weights, 'equity_dividend', cfg.signals.dividend_boost, ['equity_kr_broad'])
        _apply_shift(weights, 'equity_covered_call', cfg.signals.covered_call_boost, ['CASH'])
    if vol_contraction:
        _apply_shift(weights, 'equity_kr_broad', cfg.signals.broad_reversion_boost / 2.0, ['bond_short'])
        _apply_shift(weights, 'equity_low_vol', cfg.signals.low_vol_boost / 2.0, ['CASH'])
    if oversold:
        _apply_shift(weights, 'equity_kr_broad', cfg.signals.broad_reversion_boost, ['bond_short', 'CASH'])
        _apply_shift(weights, 'equity_low_vol', cfg.signals.low_vol_boost, ['CASH'])
    if rebound:
        _apply_shift(weights, 'bond_short', cfg.signals.overheat_bond_boost / 2.0, ['equity_kr_broad'])
    if uncertainty:
        _apply_shift(weights, 'bond_short', cfg.signals.uncertainty_bond_boost, ['equity_kr_broad', 'equity_low_vol', 'equity_dividend'])
        _apply_shift(weights, 'CASH', cfg.signals.uncertainty_cash_boost, ['equity_covered_call', 'equity_kr_broad'])
    if rebound and not oversold:
        _apply_shift(weights, 'bond_short', cfg.signals.overheat_bond_boost, ['equity_kr_broad'])
        _apply_shift(weights, 'CASH', cfg.signals.overheat_cash_boost, ['equity_kr_broad', 'equity_low_vol'])

    weights = _clip_and_normalize(weights, cfg)

    final_weights = {}
    rows = []
    residual_cash = float(weights.get('CASH', 0.0))
    for group_key, target_weight in weights.items():
        if group_key == 'CASH':
            rows.append({'group_key': 'CASH', 'ticker': 'CASH', 'name': 'CASH', 'target_group_weight': target_weight, 'assigned_weight': target_weight, 'selected': True, 'available': True, 'liquidity_20d_value': 0.0})
            continue
        picked = picks.get(group_key)
        if not picked:
            residual_cash += target_weight
            rows.append({'group_key': group_key, 'ticker': '', 'name': '', 'target_group_weight': target_weight, 'assigned_weight': 0.0, 'selected': False, 'available': False, 'liquidity_20d_value': 0.0})
            continue
        ticker, name, liq = picked
        final_weights[ticker] = final_weights.get(ticker, 0.0) + float(target_weight)
        rows.append({'group_key': group_key, 'ticker': ticker, 'name': name, 'target_group_weight': target_weight, 'assigned_weight': target_weight, 'selected': True, 'available': True, 'liquidity_20d_value': liq})
    if residual_cash > 0:
        final_weights['CASH'] = float(residual_cash)

    diagnostics = {
        'adx_low': adx_low,
        'vol_contraction': vol_contraction,
        'oversold': oversold,
        'rebound': rebound,
        'uncertainty': uncertainty,
        'broad_ret_20d': m['ret_20d'],
        'broad_vol_short': m['vol_short'],
        'broad_vol_long': m['vol_long'],
        'broad_rsi': m['rsi'],
    }
    return S5AllocationResult(weights=final_weights, selection_df=pd.DataFrame(rows), diagnostics=diagnostics)
