"""Accepted common arithmetic revision; no collection or database writes."""
import math

import numpy as np
import pandas as pd

REVISION = 'common_calculation_20260922_v1'


def growth_change(current, previous, current_year, previous_year,
                  current_period='FY', previous_period='FY'):
    values = [current, previous, current_year, previous_year]
    try:
        if any(pd.isna(v) or not math.isfinite(float(v)) for v in values):
            return np.nan
    except (TypeError, ValueError):
        return np.nan
    if not current_period or current_period != previous_period:
        return np.nan
    if current_year != int(current_year) or previous_year != int(previous_year):
        return np.nan
    if current_year - previous_year != 1 or previous == 0:
        return np.nan
    return (current - previous) / abs(previous)


def annual_growth(frame):
    out = frame.sort_values(['stock_code', 'bsns_year']).copy()
    if out.duplicated(['stock_code', 'bsns_year']).any():
        raise ValueError('Ambiguous annual source pair')
    groups = ['stock_code'] + (['corp_code'] if 'corp_code' in out else [])
    grouped = out.groupby(groups)
    prior_year = grouped.bsns_year.shift(1)
    for field in ['revenue', 'op_income']:
        out[field + '_prev'] = grouped[field].shift(1)
        valid = np.isfinite(out[field]) & np.isfinite(out[field + '_prev']) & out[field + '_prev'].ne(0)
        out['_legacy_' + field + '_yoy'] = (out[field] / out[field + '_prev'] - 1).where(valid)
        out[field + '_yoy'] = [growth_change(c, p, y, py) for c, p, y, py in
                              zip(out[field], out[field + '_prev'], out.bsns_year, prior_year)]
    return out


def preserve_historical_growth(incoming, existing):
    """Repair only proven existing source pairs; preserve unknown raw history.

    Pair matching is retrospective evidence, never historical PIT certification.
    Recompute cross-sectional ranks after merging the verified corrections.
    """
    if incoming.duplicated(['date', 'ticker']).any() or existing.duplicated(['date', 'ticker']).any():
        raise ValueError('Duplicate persisted/incoming monthly keys')
    out = incoming.copy().set_index(['date', 'ticker'])
    old = existing.set_index(['date', 'ticker'])
    # Today's source/universe cannot invent or erase historical cohort members.
    old_dates = set(existing.date)
    keep = [key in old.index or key[0] not in old_dates for key in out.index]
    out = out.loc[keep].copy()
    out['bsns_year'] = out.bsns_year.astype('Int64')
    overlap = out.index.intersection(old.index)
    if len(overlap):
        current = out.loc[overlap].copy()
        saved = old.loc[overlap]
        same_source = (current.bsns_year.eq(saved.bsns_year)
                       & current.available_from.eq(saved.available_from))
        for field in ['revenue_yoy', 'op_income_yoy']:
            observed = pd.to_numeric(saved[field], errors='coerce')
            legacy = current['_legacy_' + field]
            verified = same_source & np.isfinite(observed) & np.isfinite(legacy)
            verified &= np.isclose(observed, legacy, rtol=1e-10, atol=1e-10)
            # An already-corrected row is also stable across repeated next-cycle runs.
            verified |= same_source & np.isclose(observed, current[field], rtol=1e-10, atol=1e-10)
            out.loc[overlap, field] = current[field].where(verified, observed)
        for field in ['corp_name', 'bsns_year', 'available_from']:
            out.loc[overlap, field] = saved[field].astype('Int64') if field == 'bsns_year' else saved[field]
    missing = old.index.difference(out.index)
    if len(missing):
        out = pd.concat([out, old.loc[missing]])
    out = out.reset_index()
    rev = out.groupby('date').revenue_yoy.rank(ascending=False, method='average', na_option='bottom')
    op = out.groupby('date').op_income_yoy.rank(ascending=False, method='average', na_option='bottom')
    out['growth_score'] = .7 * rev + .3 * op
    return out


def corrected_features(history):
    """Calendar-month lag with observable dates; raw unknown values remain missing."""
    from src.quant2.evaluation.quant25_selection_candidate import corrected_fund_snapshot

    if history.duplicated(['date', 'ticker']).any():
        raise ValueError('Duplicate monthly source keys')
    pieces = []
    for day, rows in history.groupby('date', sort=True):
        current = rows.copy()
        calc = corrected_fund_snapshot(history, day, rows.ticker.tolist()).set_index('ticker')
        current = current.set_index('ticker')
        # Legacy growth_score stays smaller-is-better for the S2 consumer.
        current['rev_delta_3m'] = calc.revenue_yoy - calc.prior_revenue_yoy
        current['op_delta_3m'] = calc.op_income_yoy - calc.prior_op_income_yoy
        current['gs_delta_3m'] = calc.accel_change
        current['fund_accel_score'] = calc.accel_pct
        pieces.append(current.reset_index())
    return pd.concat(pieces, ignore_index=True) if pieces else history.copy()


def load_fund_snapshot(connection, table, cutoff):
    """Read the actual selector's dated raw features; no later monthly rows."""
    from src.quant2.evaluation.quant25_selection_candidate import corrected_fund_snapshot

    if not table.replace('_', '').isalnum():
        raise ValueError('Invalid feature table')
    history = pd.read_sql_query(
        f'SELECT * FROM {table} WHERE date <= ? AND available_from <= ?',
        connection, params=[cutoff, cutoff])
    if history.empty:
        raise ValueError('No dated fundamental source; withhold selection')
    history['ticker'] = history.ticker.astype(str).str.zfill(6)
    raw = corrected_fund_snapshot(history, cutoff, sorted(history.ticker.unique()))
    old = history.sort_values(['ticker', 'available_from', 'date']).groupby('ticker').tail(1)
    return raw.merge(old[['ticker', 'growth_score', 'gs_delta_3m', 'fund_accel_score']],
                     on='ticker', how='left', validate='one_to_one')


def score_fields(frame):
    complete = np.isfinite(frame[['revenue_yoy', 'op_income_yoy']]).all(axis=1)
    level = (.7 * frame.revenue_yoy.where(complete).rank(pct=True)
             + .3 * frame.op_income_yoy.where(complete).rank(pct=True))
    acceleration = frame.accel_change.where(complete & frame.accel_complete.eq(True)).rank(pct=True)
    return level, acceleration


def bounded_normalize(weights, minimum, maximum):
    """Accepted bounded proportional allocation, with cash as sole empty fallback."""
    keys = sorted(set(weights) | set(minimum) | set(maximum))
    raw = np.array([weights.get(k, 0.) for k in keys], dtype=float)
    low = np.array([minimum.get(k, 0.) for k in keys], dtype=float)
    high = np.array([maximum.get(k, 1.) for k in keys], dtype=float)
    if not np.isfinite(np.r_[raw, low, high]).all():
        raise ValueError('Nonfinite allocation')
    if (low < 0).any() or (high < low).any() or low.sum() > 1 + 1e-12 or high.sum() < 1 - 1e-12:
        raise ValueError('Infeasible allocation bounds')
    x = np.clip(np.maximum(raw, 0), low, high)
    for _ in range(2 * len(keys) + 2):
        residual = 1 - x.sum()
        if abs(residual) <= 1e-12:
            return dict(zip(keys, x.tolist()))
        room = high - x if residual > 0 else x - low
        eligible = (room > 1e-12) & (x > 0)
        if not eligible.any() and residual > 0 and 'CASH' in keys:
            eligible[keys.index('CASH')] = room[keys.index('CASH')] > 1e-12
        if not eligible.any():
            raise ValueError('Cannot normalize without introducing new asset exposure')
        proportions = np.where(eligible, x, 0)
        if proportions.sum() == 0:
            proportions = eligible.astype(float)
        change = np.minimum(room, abs(residual) * proportions / proportions.sum())
        x += change if residual > 0 else -change
    raise ValueError('Normalization did not converge')
