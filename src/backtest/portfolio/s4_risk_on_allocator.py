from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from src.backtest.configs.s4_risk_on_config import S4RiskOnConfig


@dataclass(frozen=True)
class S4AllocationResult:
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


def _last_metrics(close_wide: pd.DataFrame, value_wide: pd.DataFrame, ticker: str | None, dt: pd.Timestamp, cfg: S4RiskOnConfig) -> dict[str, float | bool | None]:
    if not ticker or ticker not in close_wide.columns:
        return {'ret_20d': None, 'ma_trend': None, 'breakout': None, 'value_ratio': None}
    px = pd.to_numeric(close_wide[ticker], errors='coerce').dropna()
    px = px.loc[px.index <= pd.Timestamp(dt)]
    if len(px) < max(cfg.signals.ma_long + 2, cfg.signals.breakout_lookback + 2):
        return {'ret_20d': None, 'ma_trend': None, 'breakout': None, 'value_ratio': None}
    ret_20d = float(px.iloc[-1] / px.iloc[-1 - cfg.signals.return_lookback] - 1.0)
    ma_s = float(px.tail(cfg.signals.ma_short).mean())
    ma_l = float(px.tail(cfg.signals.ma_long).mean())
    breakout = bool(float(px.iloc[-1]) >= float(px.tail(cfg.signals.breakout_lookback).max()))
    value_ratio = None
    if ticker in value_wide.columns:
        val = pd.to_numeric(value_wide[ticker], errors='coerce').dropna()
        val = val.loc[val.index <= pd.Timestamp(dt)]
        if len(val) >= cfg.signals.value_lookback:
            base = float(val.tail(cfg.signals.value_lookback).mean())
            if base > 0:
                value_ratio = float(val.iloc[-1]) / base
    return {'ret_20d': ret_20d, 'ma_trend': ma_s > ma_l, 'breakout': breakout, 'value_ratio': value_ratio}


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


def _clip_and_normalize(weights: dict[str, float], cfg: S4RiskOnConfig) -> dict[str, float]:
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


def allocate_s4_risk_on(
    *,
    core_df: pd.DataFrame,
    close_wide: pd.DataFrame,
    value_wide: pd.DataFrame,
    asof: pd.Timestamp,
    cfg: S4RiskOnConfig,
    available_tickers: Iterable[str] | None = None,
) -> S4AllocationResult:
    available = {str(t).zfill(6) for t in (available_tickers or [])}
    groups = {
        'equity_kr_broad': _eligible_group(core_df, cfg.signals.broad_group, available),
        'equity_kr_growth': _eligible_group(core_df, cfg.signals.growth_group, available),
        'equity_sector_momentum': _eligible_group(core_df, cfg.signals.sector_group, available),
        'bond_short': _eligible_group(core_df, cfg.signals.fallback_group, available),
    }

    picks = {}
    metrics = {}
    for group_key, g in groups.items():
        if g.empty:
            continue
        g = g.sort_values(['liquidity_20d_value', 'ticker'], ascending=[False, True]).copy()
        best = None
        best_score = None
        for _, row in g.iterrows():
            ticker = str(row['ticker']).zfill(6)
            m = _last_metrics(close_wide, value_wide, ticker, asof, cfg)
            score = 0.0
            score += float(m['ret_20d'] or 0.0)
            score += 0.03 if bool(m['ma_trend']) else -0.03
            score += 0.02 if bool(m['breakout']) else 0.0
            score += min(max(float(m['value_ratio'] or 1.0) - 1.0, -0.2), 0.5)
            score += float(row.get('liquidity_20d_value', 0.0) or 0.0) / 1e13
            if best is None or score > best_score:
                best = row
                best_score = score
                metrics[group_key] = m | {'score': score}
        if best is not None:
            picks[group_key] = (str(best['ticker']).zfill(6), str(best.get('name', '')), float(best.get('liquidity_20d_value', 0.0) or 0.0))

    weights = dict(cfg.base.weights)
    growth = metrics.get('equity_kr_growth', {})
    sector = metrics.get('equity_sector_momentum', {})
    broad = metrics.get('equity_kr_broad', {})

    strong_trend = bool(growth.get('ma_trend')) and bool(broad.get('ma_trend'))
    rs_growth = (growth.get('ret_20d') is not None and broad.get('ret_20d') is not None and float(growth['ret_20d']) > float(broad['ret_20d']))
    sector_hot = bool(sector.get('breakout')) and (sector.get('ret_20d') is not None and float(sector['ret_20d']) > 0)
    growth_participation = growth.get('value_ratio') is not None and float(growth['value_ratio']) >= 1.15
    weakening = not bool(broad.get('ma_trend')) or (broad.get('ret_20d') is not None and float(broad['ret_20d']) < 0)
    overheating = growth.get('ret_20d') is not None and float(growth['ret_20d']) >= float(cfg.signals.overheat_threshold)

    if strong_trend:
        _apply_shift(weights, 'equity_kr_growth', cfg.signals.trend_boost, ['equity_kr_broad', 'CASH'])
    if rs_growth:
        _apply_shift(weights, 'equity_kr_growth', cfg.signals.rs_boost, ['equity_kr_broad'])
    if sector_hot:
        _apply_shift(weights, 'equity_sector_momentum', cfg.signals.rs_boost, ['equity_kr_broad', 'CASH'])
    if growth_participation:
        _apply_shift(weights, 'equity_kr_growth', cfg.signals.participation_boost, ['CASH', 'equity_kr_broad'])
    if weakening:
        _apply_shift(weights, 'equity_kr_broad', cfg.signals.weakening_shift_to_broad, ['equity_kr_growth', 'equity_sector_momentum'])
        _apply_shift(weights, 'CASH', cfg.signals.weakening_shift_to_cash, ['equity_sector_momentum', 'equity_kr_growth'])
    if overheating:
        _apply_shift(weights, 'equity_kr_broad', cfg.signals.overheat_cut, ['equity_kr_growth'])
        _apply_shift(weights, 'CASH', cfg.signals.overheat_cut / 2.0, ['equity_sector_momentum'])

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
            if group_key == 'bond_short' and groups['bond_short'].empty:
                residual_cash += target_weight
            else:
                residual_cash += target_weight
            rows.append({'group_key': group_key, 'ticker': '', 'name': '', 'target_group_weight': target_weight, 'assigned_weight': 0.0, 'selected': False, 'available': False, 'liquidity_20d_value': 0.0})
            continue
        ticker, name, liq = picked
        final_weights[ticker] = final_weights.get(ticker, 0.0) + float(target_weight)
        rows.append({'group_key': group_key, 'ticker': ticker, 'name': name, 'target_group_weight': target_weight, 'assigned_weight': target_weight, 'selected': True, 'available': True, 'liquidity_20d_value': liq})
    if residual_cash > 0:
        final_weights['CASH'] = float(residual_cash)

    diagnostics = {
        'strong_trend': strong_trend,
        'rs_growth': rs_growth,
        'sector_hot': sector_hot,
        'growth_participation': growth_participation,
        'weakening': weakening,
        'overheating': overheating,
        'broad_ret_20d': broad.get('ret_20d'),
        'growth_ret_20d': growth.get('ret_20d'),
        'sector_ret_20d': sector.get('ret_20d'),
        'growth_value_ratio': growth.get('value_ratio'),
        'sector_value_ratio': sector.get('value_ratio'),
    }
    return S4AllocationResult(weights=final_weights, selection_df=pd.DataFrame(rows), diagnostics=diagnostics)
