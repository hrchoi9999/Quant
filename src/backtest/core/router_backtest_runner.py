from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.backtest.configs.router_config import RouterConfig
from src.backtest.contracts import BacktestResult
from src.backtest.core.data import next_trading_day
from src.backtest.router.multiasset_regime_router import build_router_decision, resolve_mode_for_date


@dataclass(frozen=True)
class ModelBundle:
    model: str
    equity_df: pd.DataFrame
    holdings_df: pd.DataFrame


@dataclass(frozen=True)
class _PendingDecision:
    decision_date: pd.Timestamp
    exec_date: pd.Timestamp
    mode: str
    regime_value: float | None
    stock_model: str | None
    etf_model: str | None
    stock_weight: float
    etf_weight: float
    fallback_used: bool
    note: str
    agg_weights: pd.Series
    holdings_df: pd.DataFrame


def _calc_turnover(prev_w: pd.Series, new_w: pd.Series) -> float:
    return float(new_w.fillna(0.0).sub(prev_w.fillna(0.0), fill_value=0.0).abs().sum() / 2.0)


def _perf_metrics(equity_df: pd.DataFrame) -> dict[str, float]:
    if equity_df is None or equity_df.empty:
        return {'cagr': float('nan'), 'mdd': float('nan'), 'sharpe': float('nan'), 'avg_daily_ret': float('nan'), 'vol_daily': float('nan'), 'total_return': float('nan')}
    rets = pd.to_numeric(equity_df['port_ret'], errors='coerce').fillna(0.0)
    eq = pd.to_numeric(equity_df['equity'], errors='coerce').dropna()
    n = int(len(eq))
    if n == 0:
        return {'cagr': float('nan'), 'mdd': float('nan'), 'sharpe': float('nan'), 'avg_daily_ret': float('nan'), 'vol_daily': float('nan'), 'total_return': float('nan')}
    start_eq = float(eq.iloc[0])
    end_eq = float(eq.iloc[-1])
    years = max(n / 252.0, 1.0 / 252.0)
    total_return = float(end_eq / start_eq - 1.0) if start_eq > 0 else float('nan')
    cagr = float((end_eq / start_eq) ** (1.0 / years) - 1.0) if start_eq > 0 and end_eq > 0 else float('nan')
    dd = eq / eq.cummax() - 1.0
    mdd = float(dd.min()) if len(dd) else float('nan')
    vol = float(rets.std(ddof=0))
    sharpe = float((rets.mean() / vol) * np.sqrt(252.0)) if vol > 0 else float('nan')
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'avg_daily_ret': float(rets.mean()), 'vol_daily': vol, 'total_return': total_return}


def _window_metric(equity_df: pd.DataFrame, years: int) -> dict[str, float]:
    return _perf_metrics(equity_df.tail(252 * years).copy() if equity_df is not None else pd.DataFrame())

def _best_growth_stock_model(model_bundles: dict[str, ModelBundle], dt: pd.Timestamp) -> str | None:
    candidates = []
    for model in ['S3', 'S3_CORE2']:
        bundle = model_bundles.get(model)
        if bundle is None or bundle.equity_df is None or bundle.equity_df.empty:
            continue
        eq = bundle.equity_df.copy()
        eq['date'] = pd.to_datetime(eq['date'])
        eq = eq.loc[eq['date'] <= pd.Timestamp(dt)].copy()
        if eq.empty:
            continue
        one_year = _window_metric(eq, 1)
        candidates.append((model, one_year.get('cagr', float('nan')), one_year.get('mdd', float('nan'))))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-np.nan_to_num(x[1], nan=-1e9), np.nan_to_num(abs(x[2]), nan=1e9)))
    return candidates[0][0]


def _select_model_for_date(model_returns: dict[str, pd.Series], model: str | None, fallback: str | None, dt: pd.Timestamp) -> tuple[str | None, bool, str]:
    if model and model in model_returns and dt in model_returns[model].index:
        return model, False, ''
    if fallback and fallback != 'CASH' and fallback in model_returns and dt in model_returns[fallback].index:
        return fallback, True, f'{model}->{fallback}'
    target = 'CASH' if fallback in {None, 'CASH'} else str(fallback)
    return None, True, f'{model}->{target}'


def _latest_holdings_before(holdings_df: pd.DataFrame, dt: pd.Timestamp) -> pd.DataFrame:
    if holdings_df is None or holdings_df.empty:
        return pd.DataFrame(columns=['trade_date', 'ticker', 'name', 'market', 'weight'])
    work = holdings_df.copy()
    work['trade_date'] = pd.to_datetime(work['trade_date'])
    eligible = work.loc[work['trade_date'] <= pd.Timestamp(dt)].copy()
    if eligible.empty:
        return pd.DataFrame(columns=work.columns)
    target_dt = eligible['trade_date'].max()
    return eligible.loc[eligible['trade_date'] == target_dt].copy()


def _aggregate_holdings(stock_holdings: pd.DataFrame, etf_holdings: pd.DataFrame, stock_weight: float, etf_weight: float) -> tuple[pd.Series, pd.DataFrame]:
    rows = []
    agg: dict[str, float] = {}
    for sleeve_name, sleeve_df, sleeve_weight in [('stock', stock_holdings, stock_weight), ('etf', etf_holdings, etf_weight)]:
        if sleeve_df is None or sleeve_df.empty or sleeve_weight <= 0:
            continue
        for row in sleeve_df.to_dict('records'):
            ticker = str(row.get('ticker', '')).strip()
            name = row.get('name', '')
            market = row.get('market', '')
            weight = float(row.get('weight', 0.0) or 0.0)
            scaled = sleeve_weight * weight
            if scaled <= 0:
                continue
            agg[ticker] = agg.get(ticker, 0.0) + scaled
            rows.append({'ticker': ticker, 'name': name, 'market': market, 'weight': scaled, 'source_sleeve': sleeve_name})
    gross = float(sum(v for k, v in agg.items() if k != 'CASH'))
    cash_weight = max(0.0, 1.0 - gross)
    if cash_weight > 0:
        agg['CASH'] = agg.get('CASH', 0.0) + cash_weight
        rows.append({'ticker': 'CASH', 'name': 'CASH', 'market': 'CASH', 'weight': cash_weight, 'source_sleeve': 'cash'})
    return pd.Series(agg, dtype=float).sort_index(), pd.DataFrame(rows)


def run_router_backtest(*, model_bundles: dict[str, ModelBundle], regime_mode_df: pd.DataFrame, rebalance_dates: list[pd.Timestamp], cfg: RouterConfig, service_profile: str) -> BacktestResult:
    if not model_bundles:
        raise RuntimeError('No model bundles provided')
    model_returns: dict[str, pd.Series] = {}
    common_dates = None
    for model, bundle in model_bundles.items():
        eq = bundle.equity_df.copy()
        eq['date'] = pd.to_datetime(eq['date'])
        s = pd.Series(pd.to_numeric(eq['port_ret'], errors='coerce').fillna(0.0).values, index=eq['date'])
        model_returns[model] = s
        common_dates = s.index if common_dates is None else common_dates.intersection(s.index)
    if common_dates is None or len(common_dates) == 0:
        raise RuntimeError('No overlapping model dates for router')

    dates = pd.DatetimeIndex(sorted(pd.to_datetime(common_dates).unique()))
    rb_set = set(pd.to_datetime([d for d in rebalance_dates if pd.Timestamp(d) in set(dates)]))
    current_stock_model = None
    current_etf_model = None
    current_stock_w = 0.0
    current_etf_w = 0.0
    current_holdings = pd.Series({'CASH': 1.0}, dtype=float)
    pending = None
    eq = 1.0
    turnover_total = 0.0
    equity_rows = []
    weights_rows = []
    trades_rows = []
    decision_rows = []

    for dt in dates:
        eq_prev = eq
        stock_ret = float(model_returns[current_stock_model].get(dt, 0.0)) if current_stock_model else 0.0
        etf_ret = float(model_returns[current_etf_model].get(dt, 0.0)) if current_etf_model else 0.0
        eq *= 1.0 + (current_stock_w * stock_ret + current_etf_w * etf_ret)

        if pending is not None and pd.Timestamp(dt) == pending.exec_date:
            prev_holdings = current_holdings.copy()
            current_stock_model = pending.stock_model
            current_etf_model = pending.etf_model
            current_stock_w = pending.stock_weight
            current_etf_w = pending.etf_weight
            current_holdings = pending.agg_weights.copy()
            turnover = _calc_turnover(prev_holdings, current_holdings)
            turnover_total += turnover
            eq *= 1.0 - turnover * ((cfg.execution.fee_bps + cfg.execution.slippage_bps) / 10000.0)
            union = sorted(set(prev_holdings.index).union(set(current_holdings.index)))
            for ticker in union:
                prev_weight = float(prev_holdings.get(ticker, 0.0))
                new_weight = float(current_holdings.get(ticker, 0.0))
                delta = new_weight - prev_weight
                if abs(delta) < 1e-12:
                    continue
                trades_rows.append({'rebalance_date': pending.decision_date.strftime('%Y-%m-%d'), 'trade_date': pending.exec_date.strftime('%Y-%m-%d'), 'ticker': ticker, 'side': 'BUY' if delta > 0 else 'SELL', 'prev_weight': prev_weight, 'new_weight': new_weight, 'delta_weight': delta, 'mode': pending.mode, 'stock_model': pending.stock_model or 'CASH', 'etf_model': pending.etf_model or 'CASH', 'fallback_used': pending.fallback_used, 'note': pending.note})
            if not pending.holdings_df.empty:
                for row in pending.holdings_df.to_dict('records'):
                    weights_rows.append({'rebalance_date': pending.decision_date.strftime('%Y-%m-%d'), 'trade_date': pending.exec_date.strftime('%Y-%m-%d'), 'mode': pending.mode, 'ticker': row.get('ticker', ''), 'name': row.get('name', ''), 'market': row.get('market', ''), 'weight': float(row.get('weight', 0.0) or 0.0), 'source_sleeve': row.get('source_sleeve', ''), 'stock_model': pending.stock_model or 'CASH', 'etf_model': pending.etf_model or 'CASH', 'fallback_used': pending.fallback_used})
            pending = None

        if pd.Timestamp(dt) in rb_set:
            trade_dt = next_trading_day(dates, dt) or pd.Timestamp(dt)
            mode, regime_value = resolve_mode_for_date(regime_mode_df, dt, cfg.regime.fallback_mode)
            decision = build_router_decision(mode=mode, cfg=cfg, service_profile=service_profile)
            stock_model_override = None
            override_note = ''
            if service_profile == 'growth' and mode in {'risk_on', 'neutral'}:
                stock_model_override = _best_growth_stock_model(model_bundles, pd.Timestamp(trade_dt))
                if stock_model_override and stock_model_override != decision.stock_model:
                    override_note = f'growth_override:{decision.stock_model}->{stock_model_override}'
            chosen_stock_model = stock_model_override or decision.stock_model
            sel_stock, fb_stock, note_stock = _select_model_for_date(model_returns, chosen_stock_model, decision.stock_fallback, pd.Timestamp(trade_dt))
            sel_etf, fb_etf, note_etf = _select_model_for_date(model_returns, decision.etf_model, decision.etf_fallback, pd.Timestamp(trade_dt))
            note_parts = [x for x in [override_note, note_stock, note_etf] if x]
            fallback_used = bool(fb_stock or fb_etf)
            stock_w = decision.stock_weight if sel_stock else 0.0
            etf_w = decision.etf_weight if sel_etf else 0.0
            total = stock_w + etf_w
            if total > 0 and total != 1.0:
                stock_w /= total
                etf_w /= total
            stock_holdings = _latest_holdings_before(model_bundles[sel_stock].holdings_df, trade_dt) if sel_stock else pd.DataFrame(columns=['trade_date', 'ticker', 'name', 'market', 'weight'])
            etf_holdings = _latest_holdings_before(model_bundles[sel_etf].holdings_df, trade_dt) if sel_etf else pd.DataFrame(columns=['trade_date', 'ticker', 'name', 'market', 'weight'])
            agg_weights, agg_rows = _aggregate_holdings(stock_holdings, etf_holdings, stock_w, etf_w)
            pending = _PendingDecision(decision_date=pd.Timestamp(dt), exec_date=pd.Timestamp(trade_dt), mode=mode, regime_value=regime_value, stock_model=sel_stock, etf_model=sel_etf, stock_weight=stock_w, etf_weight=etf_w, fallback_used=fallback_used, note='; '.join(note_parts), agg_weights=agg_weights, holdings_df=agg_rows)
            decision_rows.append({'date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'trade_date': pd.Timestamp(trade_dt).strftime('%Y-%m-%d'), 'detected_regime': mode, 'regime_value': regime_value, 'selected_models': '|'.join([x for x in [sel_stock or 'CASH', sel_etf or 'CASH'] if x]), 'stock_model': sel_stock or 'CASH', 'etf_model': sel_etf or 'CASH', 'stock_sleeve_weight': stock_w, 'etf_sleeve_weight': etf_w, 'service_profile': service_profile, 'fallback_used': fallback_used, 'note': '; '.join(note_parts)})

        gross = float(sum(v for k, v in current_holdings.items() if k != 'CASH'))
        cash_weight = max(0.0, 1.0 - gross)
        equity_rows.append({'date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'port_ret': float(eq / eq_prev - 1.0), 'equity': float(eq), 'mode': decision_rows[-1]['detected_regime'] if decision_rows else cfg.regime.fallback_mode, 'stock_model': current_stock_model or 'CASH', 'etf_model': current_etf_model or 'CASH', 'stock_sleeve_weight': current_stock_w, 'etf_sleeve_weight': current_etf_w, 'gross_exposure': gross, 'cash_weight': cash_weight})

    equity_df = pd.DataFrame(equity_rows)
    summary_metrics = _perf_metrics(equity_df)
    one_year = _window_metric(equity_df, 1)
    two_year = _window_metric(equity_df, 2)
    three_year = _window_metric(equity_df, 3)
    five_year = _window_metric(equity_df, 5)
    summary_df = pd.DataFrame([{'strategy': cfg.strategy_name, 'start': str(equity_df['date'].iloc[0]), 'end': str(equity_df['date'].iloc[-1]), 'days': int(len(equity_df)), 'cagr': summary_metrics['cagr'], 'mdd': summary_metrics['mdd'], 'sharpe': summary_metrics['sharpe'], 'avg_daily_ret': summary_metrics['avg_daily_ret'], 'vol_daily': summary_metrics['vol_daily'], 'turnover': float(turnover_total), 'rebalance_count': int(len(decision_rows)), 'fee_bps': float(cfg.execution.fee_bps), 'slippage_bps': float(cfg.execution.slippage_bps), 'service_profile': service_profile, 'cagr_1y': one_year['cagr'], 'sharpe_1y': one_year['sharpe'], 'mdd_1y': one_year['mdd'], 'cagr_2y': two_year['cagr'], 'sharpe_2y': two_year['sharpe'], 'mdd_2y': two_year['mdd'], 'cagr_3y': three_year['cagr'], 'sharpe_3y': three_year['sharpe'], 'mdd_3y': three_year['mdd'], 'cagr_5y': five_year['cagr'], 'sharpe_5y': five_year['sharpe'], 'mdd_5y': five_year['mdd']}])
    return BacktestResult(summary_df=summary_df, equity_df=equity_df, holdings_df=pd.DataFrame(weights_rows), trades_df=pd.DataFrame(trades_rows), meta={'decisions_df': pd.DataFrame(decision_rows)})
