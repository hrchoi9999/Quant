from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from src.backtest.configs.s6_defensive_config import S6DefensiveConfig


@dataclass(frozen=True)
class S6AllocationResult:
    weights: dict[str, float]
    selection_df: pd.DataFrame
    diagnostics: dict[str, float | bool | str | None]


def _pick_group_ticker(core_df: pd.DataFrame, group_key: str, available: set[str]) -> tuple[str, str, float] | None:
    group = core_df.loc[core_df['group_key'].astype(str) == str(group_key)].copy()
    if available:
        group = group.loc[group['ticker'].astype(str).str.zfill(6).isin(available)].copy()
    if group.empty:
        return None
    group['ticker'] = group['ticker'].astype(str).str.zfill(6)
    group['liquidity_20d_value'] = pd.to_numeric(group['liquidity_20d_value'], errors='coerce').fillna(0.0)
    picked = group.sort_values(['liquidity_20d_value', 'ticker'], ascending=[False, True]).iloc[0]
    return str(picked['ticker']), str(picked.get('name', '')), float(picked.get('liquidity_20d_value', 0.0) or 0.0)


def _safe_ret(close_wide: pd.DataFrame, ticker: str | None, dt: pd.Timestamp, lookback: int) -> float | None:
    if not ticker or ticker not in close_wide.columns:
        return None
    s = pd.to_numeric(close_wide[ticker], errors='coerce').dropna()
    s = s.loc[s.index <= pd.Timestamp(dt)]
    if len(s) <= lookback:
        return None
    now = float(s.iloc[-1])
    prev = float(s.iloc[-1 - lookback])
    if prev == 0:
        return None
    return now / prev - 1.0


def _safe_vol(ret_wide: pd.DataFrame, ticker: str | None, dt: pd.Timestamp, lookback: int) -> float | None:
    if not ticker or ticker not in ret_wide.columns:
        return None
    s = pd.to_numeric(ret_wide[ticker], errors='coerce').dropna()
    s = s.loc[s.index <= pd.Timestamp(dt)].tail(lookback)
    if len(s) < max(5, lookback // 2):
        return None
    return float(s.std(ddof=0))


def _apply_shift(weights: dict[str, float], to_key: str, amount: float, from_keys: list[str]) -> None:
    amt = max(0.0, float(amount))
    if amt <= 0:
        return
    remaining = amt
    for src in from_keys:
        if remaining <= 0:
            break
        avail = max(0.0, float(weights.get(src, 0.0)))
        take = min(avail, remaining)
        if take <= 0:
            continue
        weights[src] = avail - take
        remaining -= take
    moved = amt - remaining
    weights[to_key] = float(weights.get(to_key, 0.0)) + moved


def _clip_and_normalize(weights: dict[str, float], cfg: S6DefensiveConfig) -> dict[str, float]:
    out = {k: max(0.0, float(v)) for k, v in weights.items()}
    for key, min_v in cfg.bounds.min_weights.items():
        out[key] = max(float(min_v), float(out.get(key, 0.0)))
    for key, max_v in cfg.bounds.max_weights.items():
        out[key] = min(float(max_v), float(out.get(key, 0.0)))
    out['hedge_inverse_kr'] = min(float(out.get('hedge_inverse_kr', 0.0)), float(cfg.bounds.inverse_cap))

    total = sum(out.values())
    if total <= 0:
        out['CASH'] = 1.0
        total = 1.0
    out = {k: float(v) / total for k, v in out.items()}

    total = sum(out.values())
    if abs(total - 1.0) > 1e-10:
        out['CASH'] = float(out.get('CASH', 0.0)) + (1.0 - total)
    return out


def allocate_s6_defensive(
    *,
    core_df: pd.DataFrame,
    close_wide: pd.DataFrame,
    ret_wide: pd.DataFrame,
    asof: pd.Timestamp,
    cfg: S6DefensiveConfig,
    available_tickers: Iterable[str] | None = None,
) -> S6AllocationResult:
    available = {str(t).zfill(6) for t in (available_tickers or [])}
    picks = {}
    for group in ['bond_long', 'bond_short', 'fx_usd', 'commodity_gold', 'hedge_inverse_kr', cfg.signals.market_group]:
        picked = _pick_group_ticker(core_df, group, available)
        if picked:
            picks[group] = picked

    market_ticker = picks.get(cfg.signals.market_group, (None, '', 0.0))[0]
    bond_long_ticker = picks.get('bond_long', (None, '', 0.0))[0]
    usd_ticker = picks.get('fx_usd', (None, '', 0.0))[0]
    gold_ticker = picks.get('commodity_gold', (None, '', 0.0))[0]

    market_vol = _safe_vol(ret_wide, market_ticker, asof, cfg.signals.vol_lookback)
    market_ret_5d = _safe_ret(close_wide, market_ticker, asof, 5)
    market_ret_20d = _safe_ret(close_wide, market_ticker, asof, 20)
    usd_ret_20d = _safe_ret(close_wide, usd_ticker, asof, 20)
    gold_ret_20d = _safe_ret(close_wide, gold_ticker, asof, 20)
    bond_long_ret_20d = _safe_ret(close_wide, bond_long_ticker, asof, 20)

    vol_expand = market_vol is not None and market_vol >= float(cfg.signals.vol_expand_threshold)
    crash = (market_ret_5d is not None and market_ret_5d <= float(cfg.signals.market_drawdown_5d)) or (market_ret_20d is not None and market_ret_20d <= float(cfg.signals.market_drawdown_20d))
    usd_strong = usd_ret_20d is not None and usd_ret_20d >= float(cfg.signals.usd_momo_20d)
    gold_strong = gold_ret_20d is not None and gold_ret_20d >= float(cfg.signals.gold_momo_20d)
    bond_long_friendly = bond_long_ret_20d is not None and bond_long_ret_20d >= float(cfg.signals.bond_long_momo_20d)

    weights = dict(cfg.base.weights)

    if vol_expand:
        _apply_shift(weights, 'bond_short', cfg.signals.stress_short_bond_boost, ['bond_long', 'CASH'])
        _apply_shift(weights, 'CASH', cfg.signals.stress_cash_boost, ['bond_long'])
        _apply_shift(weights, 'hedge_inverse_kr', cfg.signals.stress_inverse_boost, ['bond_long', 'commodity_gold'])

    if crash:
        if cfg.signals.prefer_short_bond_over_long_bond_in_crash:
            _apply_shift(weights, 'bond_short', cfg.signals.drawdown_short_bond_boost, ['bond_long'])
        _apply_shift(weights, 'CASH', cfg.signals.drawdown_cash_boost, ['bond_long', 'commodity_gold'])
        _apply_shift(weights, 'hedge_inverse_kr', cfg.signals.stress_inverse_boost, ['bond_long', 'fx_usd'])

    if usd_strong:
        _apply_shift(weights, 'fx_usd', cfg.signals.usd_boost, ['bond_long', 'CASH'])

    if gold_strong:
        _apply_shift(weights, 'commodity_gold', cfg.signals.gold_boost, ['bond_long', 'CASH'])

    if bond_long_friendly and not crash:
        _apply_shift(weights, 'bond_long', cfg.signals.bond_long_boost, ['bond_short', 'CASH'])

    weights = _clip_and_normalize(weights, cfg)

    final_weights = {}
    rows = []
    residual_cash = float(weights.get('CASH', 0.0))
    for group_key, target_weight in weights.items():
        if group_key == 'CASH':
            rows.append({
                'group_key': 'CASH', 'ticker': 'CASH', 'name': 'CASH', 'target_group_weight': target_weight,
                'assigned_weight': target_weight, 'selected': True, 'available': True, 'liquidity_20d_value': 0.0,
            })
            continue
        picked = picks.get(group_key)
        if not picked:
            rows.append({
                'group_key': group_key, 'ticker': '', 'name': '', 'target_group_weight': target_weight,
                'assigned_weight': 0.0, 'selected': False, 'available': False, 'liquidity_20d_value': 0.0,
            })
            residual_cash += target_weight
            continue
        ticker, name, liq = picked
        final_weights[ticker] = final_weights.get(ticker, 0.0) + float(target_weight)
        rows.append({
            'group_key': group_key, 'ticker': ticker, 'name': name, 'target_group_weight': target_weight,
            'assigned_weight': target_weight, 'selected': True, 'available': True, 'liquidity_20d_value': liq,
        })

    if residual_cash > 0:
        final_weights['CASH'] = float(residual_cash)

    diagnostics = {
        'market_proxy': market_ticker,
        'market_vol_20d': market_vol,
        'market_ret_5d': market_ret_5d,
        'market_ret_20d': market_ret_20d,
        'usd_ret_20d': usd_ret_20d,
        'gold_ret_20d': gold_ret_20d,
        'bond_long_ret_20d': bond_long_ret_20d,
        'vol_expand': vol_expand,
        'crash': crash,
        'usd_strong': usd_strong,
        'gold_strong': gold_strong,
        'bond_long_friendly': bond_long_friendly,
    }
    return S6AllocationResult(weights=final_weights, selection_df=pd.DataFrame(rows), diagnostics=diagnostics)
