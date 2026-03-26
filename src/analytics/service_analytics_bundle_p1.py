from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from src.analytics.service_analytics_bundle_common import build_common_meta, finalize_manifest

ROOT = Path(r'D:\Quant')
ANALYTICS_DB = ROOT / 'data' / 'db' / 'service_analytics.db'
QUANT_SERVICE_DETAIL_DB = ROOT / 'data' / 'db' / 'quant_service_detail.db'
PRICE_DB = ROOT / 'data' / 'db' / 'price.db'
OUTPUT_ROOT = ROOT / 'reports' / 'service_analytics_review'


def _read(db: Path, query: str, params: tuple | None = None) -> pd.DataFrame:
    conn = sqlite3.connect(db)
    try:
        return pd.read_sql_query(query, conn, params=params or ())
    finally:
        conn.close()


def _normalize_ticker(value: object) -> str:
    text = str(value).strip()
    upper = text.upper()
    if upper.lstrip('0') == 'CASH':
        return 'CASH'
    return text.zfill(6) if text.isdigit() else upper


def _safe_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _safe_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _date_context(row: pd.Series, weekly_row: pd.DataFrame, asset_row: pd.DataFrame) -> dict[str, object]:
    signal_date = pd.to_datetime(row.get('data_asof'), errors='coerce')
    snapshot_date = pd.to_datetime(weekly_row['snapshot_date'].iloc[0], errors='coerce') if not weekly_row.empty else pd.NaT
    week_end = pd.to_datetime(weekly_row['week_end'].iloc[0], errors='coerce') if not weekly_row.empty else pd.NaT
    asset_week_end = pd.to_datetime(asset_row['week_end'].iloc[0], errors='coerce') if not asset_row.empty else pd.NaT
    return {
        'asof_date': signal_date.strftime('%Y-%m-%d') if pd.notna(signal_date) else None,
        'signal_date': signal_date.strftime('%Y-%m-%d') if pd.notna(signal_date) else None,
        'snapshot_date': snapshot_date.strftime('%Y-%m-%d') if pd.notna(snapshot_date) else None,
        'effective_date': snapshot_date.strftime('%Y-%m-%d') if pd.notna(snapshot_date) else None,
        'week_end': week_end.strftime('%Y-%m-%d') if pd.notna(week_end) else None,
        'asset_mix_week_end': asset_week_end.strftime('%Y-%m-%d') if pd.notna(asset_week_end) else None,
    }


def _fill_missing_weights(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out['weight'] = pd.to_numeric(out['weight'], errors='coerce')
    groups = []
    for _, grp in out.groupby(['run_id', 'date'], sort=False):
        work = grp.copy()
        if work['weight'].notna().any():
            work['weight'] = work['weight'].fillna(0.0)
        else:
            noncash_mask = work['ticker'].astype(str).str.upper().map(_normalize_ticker) != 'CASH'
            n = int(noncash_mask.sum())
            if n > 0:
                work.loc[noncash_mask, 'weight'] = 1.0 / n
                work.loc[~noncash_mask, 'weight'] = 0.0
            else:
                work['weight'] = 1.0 / max(len(work), 1)
        groups.append(work)
    return pd.concat(groups, ignore_index=True)
def _load_base_frames() -> dict[str, pd.DataFrame]:
    conn = sqlite3.connect(ANALYTICS_DB)
    try:
        overview = pd.read_sql_query('SELECT * FROM analytics_model_run_overview', conn)
        asset_mix = pd.read_sql_query('SELECT * FROM analytics_model_asset_mix_weekly', conn)
        changes = pd.read_sql_query('SELECT * FROM analytics_model_change_log', conn)
        lifecycle = pd.read_sql_query('SELECT * FROM analytics_holding_lifecycle', conn)
        quality = pd.read_sql_query('SELECT * FROM analytics_model_quality_weekly', conn)
        weekly = pd.read_sql_query('SELECT * FROM analytics_model_weekly_snapshot', conn)
    finally:
        conn.close()
    return {
        'overview': overview,
        'asset_mix': asset_mix,
        'changes': changes,
        'lifecycle': lifecycle,
        'quality': quality,
        'weekly': weekly,
    }


def _latest_per_model(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors='coerce')
    latest = work.groupby('model_code', as_index=False)[date_col].max()
    return work.merge(latest, on=['model_code', date_col], how='inner')


def _latest_holdings(run_ids: list[str]) -> pd.DataFrame:
    if not run_ids:
        return pd.DataFrame()
    placeholders = ','.join(['?'] * len(run_ids))
    holdings = _read(
        QUANT_SERVICE_DETAIL_DB,
        f'''
        SELECT run_id, date, ticker, rank_no, weight, score, reason_summary
        FROM run_holdings_history
        WHERE run_id IN ({placeholders})
        ''',
        tuple(run_ids),
    )
    if holdings.empty:
        return holdings
    master = _read(PRICE_DB, 'SELECT ticker, name, asset_type FROM instrument_master')
    master['ticker'] = master['ticker'].map(_normalize_ticker)
    holdings['ticker'] = holdings['ticker'].map(_normalize_ticker)
    holdings['date'] = pd.to_datetime(holdings['date'], errors='coerce')
    holdings = _fill_missing_weights(holdings)
    latest_dates = holdings.groupby('run_id', as_index=False)['date'].max()
    latest = holdings.merge(latest_dates, on=['run_id', 'date'], how='inner')
    latest = latest.merge(master, on='ticker', how='left')
    latest['asset_type'] = latest['asset_type'].fillna(latest['ticker'].map(lambda x: 'CASH' if x == 'CASH' else None))
    latest['name'] = latest['name'].fillna(latest['ticker'].map(lambda x: '현금' if x == 'CASH' else x))
    return latest.sort_values(['run_id', 'weight', 'rank_no'], ascending=[True, False, True]).copy()


def build_bundle(asof: str) -> dict[str, object]:
    frames = _load_base_frames()
    overview = frames['overview'].copy()
    overview['start_date'] = pd.to_datetime(overview['start_date'], errors='coerce')
    overview['end_date'] = pd.to_datetime(overview['end_date'], errors='coerce')

    latest_asset_mix = _latest_per_model(frames['asset_mix'], 'week_end')
    latest_quality = _latest_per_model(frames['quality'], 'week_end')
    latest_weekly = _latest_per_model(frames['weekly'], 'week_end')

    changes = frames['changes'].copy()
    changes['week_end'] = pd.to_datetime(changes['week_end'], errors='coerce')
    recent_cut = changes['week_end'].max() - pd.Timedelta(days=56)
    recent_changes = changes.loc[changes['week_end'] >= recent_cut].copy()

    change_summary = (
        recent_changes.groupby(['model_code', 'change_type'], as_index=False)
        .size()
        .pivot(index='model_code', columns='change_type', values='size')
        .fillna(0)
        .reset_index()
    )
    for col in ['new', 'exit', 'increase', 'decrease']:
        if col not in change_summary.columns:
            change_summary[col] = 0

    latest_holdings = _latest_holdings(overview['run_id'].astype(str).tolist())
    lifecycle = frames['lifecycle'].copy().sort_values(['model_code', 'holding_days_observed', 'latest_weight'], ascending=[True, False, False])

    today_models = []
    compare_rows = []
    changes_models = []

    for _, row in overview.sort_values('model_code').iterrows():
        model_code = str(row['model_code'])
        run_id = str(row['run_id'])
        asset_row = latest_asset_mix.loc[latest_asset_mix['model_code'] == model_code]
        quality_row = latest_quality.loc[latest_quality['model_code'] == model_code]
        weekly_row = latest_weekly.loc[latest_weekly['model_code'] == model_code]
        change_row = change_summary.loc[change_summary['model_code'] == model_code]
        holding_rows = latest_holdings.loc[latest_holdings['run_id'] == run_id].copy()
        life_rows = lifecycle.loc[(lifecycle['model_code'] == model_code) & (lifecycle['is_current_episode'] == 1)].head(5).copy()
        recent_model_changes = recent_changes.loc[recent_changes['model_code'] == model_code].sort_values(['week_end', 'change_type', 'delta_weight'], ascending=[False, True, False]).head(100)

        stock_weight = _safe_float(asset_row['stock_weight'].iloc[0]) if not asset_row.empty else None
        etf_weight = _safe_float(asset_row['etf_weight'].iloc[0]) if not asset_row.empty else None
        cash_weight = _safe_float(asset_row['cash_weight'].iloc[0]) if not asset_row.empty else None
        if (stock_weight or 0.0) + (etf_weight or 0.0) + (cash_weight or 0.0) == 0.0 and not holding_rows.empty:
            asset_types = set(holding_rows['asset_type'].dropna().astype(str))
            if asset_types and asset_types.issubset({'STOCK'}):
                stock_weight, etf_weight, cash_weight = 1.0, 0.0, 0.0
            elif asset_types and asset_types.issubset({'ETF'}):
                stock_weight, etf_weight, cash_weight = 0.0, 1.0, 0.0

        change_info = {
            'new_8w': _safe_int(change_row['new'].iloc[0]) if not change_row.empty else 0,
            'exit_8w': _safe_int(change_row['exit'].iloc[0]) if not change_row.empty else 0,
            'increase_8w': _safe_int(change_row['increase'].iloc[0]) if not change_row.empty else 0,
            'decrease_8w': _safe_int(change_row['decrease'].iloc[0]) if not change_row.empty else 0,
        }

        today_models.append({
            'model_code': model_code,
            'display_name': row['display_name'],
            'risk_grade': row['risk_grade'],
            'run_id': run_id,
            'date_context': _date_context(row, weekly_row, asset_row),
            'backtest_period': {
                'start_date': row['start_date'].strftime('%Y-%m-%d') if pd.notna(row['start_date']) else None,
                'end_date': row['end_date'].strftime('%Y-%m-%d') if pd.notna(row['end_date']) else None,
            },
            'headline_metrics': {
                'cagr': _safe_float(row['cagr']),
                'mdd': _safe_float(row['mdd']),
                'sharpe': _safe_float(row['sharpe']),
                'current_drawdown': _safe_float(weekly_row['drawdown_current'].iloc[0]) if not weekly_row.empty else None,
                'return_4w': _safe_float(quality_row['return_4w'].iloc[0]) if not quality_row.empty else None,
                'return_12w': _safe_float(quality_row['return_12w'].iloc[0]) if not quality_row.empty else None,
            },
            'asset_mix': {
                'stock_weight': stock_weight,
                'etf_weight': etf_weight,
                'cash_weight': cash_weight,
            },
            'recent_change_summary': change_info,
            'top_holdings': [
                {
                    'ticker': _normalize_ticker(h['ticker']),
                    'name': h['name'],
                    'asset_type': h['asset_type'],
                    'weight': _safe_float(h['weight']),
                    'rank_no': _safe_int(h['rank_no']),
                }
                for _, h in holding_rows.head(8).iterrows()
            ],
            'holding_highlights': [
                {
                    'ticker': _normalize_ticker(h['ticker']),
                    'name': h['name'],
                    'asset_type': h['asset_type'],
                    'holding_days_observed': _safe_int(h['holding_days_observed']),
                    'latest_weight': _safe_float(h['latest_weight']),
                    'latest_return_since_entry': _safe_float(h['latest_return_since_entry']),
                }
                for _, h in life_rows.iterrows()
            ],
        })

        compare_rows.append({
            'model_code': model_code,
            'display_name': row['display_name'],
            'risk_grade': row['risk_grade'],
            'cagr': _safe_float(row['cagr']),
            'mdd': _safe_float(row['mdd']),
            'sharpe': _safe_float(row['sharpe']),
            'return_4w': _safe_float(quality_row['return_4w'].iloc[0]) if not quality_row.empty else None,
            'return_12w': _safe_float(quality_row['return_12w'].iloc[0]) if not quality_row.empty else None,
            'current_drawdown': _safe_float(quality_row['drawdown_current'].iloc[0]) if not quality_row.empty else None,
            'relative_strength_vs_benchmark_4w': _safe_float(quality_row['relative_strength_vs_benchmark_4w'].iloc[0]) if not quality_row.empty else None,
            'date_context': _date_context(row, weekly_row, asset_row),
            'stock_weight': stock_weight,
            'etf_weight': etf_weight,
            'cash_weight': cash_weight,
            'new_8w': change_info['new_8w'],
            'exit_8w': change_info['exit_8w'],
            'increase_8w': change_info['increase_8w'],
            'decrease_8w': change_info['decrease_8w'],
        })

        changes_models.append({
            'model_code': model_code,
            'display_name': row['display_name'],
            'date_context': _date_context(row, weekly_row, asset_row),
            'summary': change_info,
            'items': [
                {
                    'week_end': pd.to_datetime(c['week_end']).strftime('%Y-%m-%d') if pd.notna(c['week_end']) else None,
                    'ticker': _normalize_ticker(c['ticker']),
                    'name': c['name'],
                    'asset_type': c['asset_type'],
                    'change_type': c['change_type'],
                    'weight_prev': _safe_float(c['weight_prev']),
                    'weight_curr': _safe_float(c['weight_curr']),
                    'delta_weight': _safe_float(c['delta_weight']),
                }
                for _, c in recent_model_changes.iterrows()
            ],
        })

    compare_rows = sorted(compare_rows, key=lambda x: (x['cagr'] is None, -(x['cagr'] or -999999)))

    return {
        'meta': build_common_meta(asof, 'p1', ['today_model_info', 'model_changes', 'model_compare']),
        'today_model_info': {
            'models': today_models,
        },
        'model_changes': {
            'models': changes_models,
        },
        'model_compare': {
            'rows': compare_rows,
        },
    }


def write_bundle(asof: str) -> dict[str, Path]:
    data = build_bundle(asof)
    outdir = OUTPUT_ROOT / asof.replace('-', '') / 'p1_bundle'
    outdir.mkdir(parents=True, exist_ok=True)

    manifest_path = outdir / f'bundle_manifest_{asof.replace("-", "")}.json'
    today_path = outdir / f'today_model_info_{asof.replace("-", "")}.json'
    changes_path = outdir / f'model_changes_{asof.replace("-", "")}.json'
    compare_path = outdir / f'model_compare_{asof.replace("-", "")}.json'

    today_path.write_text(json.dumps({'meta': data['meta'], **data['today_model_info']}, ensure_ascii=False, indent=2), encoding='utf-8')
    changes_path.write_text(json.dumps({'meta': data['meta'], **data['model_changes']}, ensure_ascii=False, indent=2), encoding='utf-8')
    compare_path.write_text(json.dumps({'meta': data['meta'], **data['model_compare']}, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = finalize_manifest(data['meta'], {
        'today_model_info': today_path,
        'model_changes': changes_path,
        'model_compare': compare_path,
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    return {
        'outdir': outdir,
        'manifest': manifest_path,
        'today_model_info': today_path,
        'model_changes': changes_path,
        'model_compare': compare_path,
    }
