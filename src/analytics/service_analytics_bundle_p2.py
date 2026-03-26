from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from src.analytics.service_analytics_bundle_common import build_common_meta, finalize_manifest

ROOT = Path(r'D:\Quant')
ANALYTICS_DB = ROOT / 'data' / 'db' / 'service_analytics.db'
OUTPUT_ROOT = ROOT / 'reports' / 'service_analytics_review'


def _read_table(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(f'SELECT * FROM {table}', conn)


def _safe_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _safe_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _load_frames() -> dict[str, pd.DataFrame]:
    conn = sqlite3.connect(ANALYTICS_DB)
    try:
        overview = _read_table(conn, 'analytics_model_run_overview')
        asset_mix = _read_table(conn, 'analytics_model_asset_mix_weekly')
        lifecycle = _read_table(conn, 'analytics_holding_lifecycle')
        changes = _read_table(conn, 'analytics_model_change_log')
        quality = _read_table(conn, 'analytics_model_quality_weekly')
    finally:
        conn.close()
    return {
        'overview': overview,
        'asset_mix': asset_mix,
        'lifecycle': lifecycle,
        'changes': changes,
        'quality': quality,
    }


def _latest_per_model(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors='coerce')
    latest = work.groupby('model_code', as_index=False)[date_col].max()
    return work.merge(latest, on=['model_code', date_col], how='inner')


def _load_p1_today(asof: str) -> dict[str, dict]:
    stamp = asof.replace('-', '')
    path = OUTPUT_ROOT / stamp / 'p1_bundle' / f'today_model_info_{stamp}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    return {row['model_code']: row for row in data['models']}


def _date_context(asof: str, mix_row: pd.DataFrame) -> dict[str, object]:
    week_end = pd.to_datetime(mix_row['week_end'].iloc[0], errors='coerce') if not mix_row.empty else pd.NaT
    return {
        'asof_date': asof,
        'signal_date': asof,
        'effective_date': asof,
        'week_end': week_end.strftime('%Y-%m-%d') if pd.notna(week_end) else None,
        'asset_mix_week_end': week_end.strftime('%Y-%m-%d') if pd.notna(week_end) else None,
    }



def build_bundle(asof: str) -> dict[str, object]:
    frames = _load_frames()
    overview = frames['overview'].copy().sort_values('model_code')
    asset_mix = frames['asset_mix'].copy()
    asset_mix['week_end'] = pd.to_datetime(asset_mix['week_end'], errors='coerce')
    lifecycle = frames['lifecycle'].copy()
    changes = frames['changes'].copy()
    changes['week_end'] = pd.to_datetime(changes['week_end'], errors='coerce')
    quality = frames['quality'].copy()
    quality['week_end'] = pd.to_datetime(quality['week_end'], errors='coerce')

    latest_mix = _latest_per_model(asset_mix, 'week_end')
    latest_quality = _latest_per_model(quality, 'week_end')
    p1_models = _load_p1_today(asof)

    recent_cut = changes['week_end'].max() - pd.Timedelta(days=56)
    recent_changes = changes.loc[changes['week_end'] >= recent_cut].copy()

    structure_models = []
    lifecycle_models = []

    for _, row in overview.iterrows():
        model_code = str(row['model_code'])
        display_name = row['display_name']
        mix_row = latest_mix.loc[latest_mix['model_code'] == model_code]
        quality_row = latest_quality.loc[latest_quality['model_code'] == model_code]
        trend_rows = asset_mix.loc[asset_mix['model_code'] == model_code].sort_values('week_end').tail(26)
        p1 = p1_models.get(model_code, {})
        top_holdings = p1.get('top_holdings', [])
        current_highlights = p1.get('holding_highlights', [])

        top_weights = [float(item['weight']) for item in top_holdings if item.get('weight') is not None]
        concentration = {
            'top1_weight': _safe_float(top_weights[0]) if len(top_weights) >= 1 else None,
            'top3_weight': sum(top_weights[:3]) if top_weights else None,
            'top5_weight': sum(top_weights[:5]) if top_weights else None,
            'current_holdings_count': len(top_holdings),
        }

        structure_models.append({
            'model_code': model_code,
            'display_name': display_name,
            'risk_grade': row['risk_grade'],
            'date_context': _date_context(asof, mix_row),
            'latest_asset_mix': {
                'stock_weight': _safe_float(mix_row['stock_weight'].iloc[0]) if not mix_row.empty else None,
                'etf_weight': _safe_float(mix_row['etf_weight'].iloc[0]) if not mix_row.empty else None,
                'cash_weight': _safe_float(mix_row['cash_weight'].iloc[0]) if not mix_row.empty else None,
                'other_weight': _safe_float(mix_row['other_weight'].iloc[0]) if not mix_row.empty else None,
            },
            'asset_mix_trend_26w': [
                {
                    'week_end': pd.to_datetime(r['week_end']).strftime('%Y-%m-%d') if pd.notna(r['week_end']) else None,
                    'stock_weight': _safe_float(r['stock_weight']),
                    'etf_weight': _safe_float(r['etf_weight']),
                    'cash_weight': _safe_float(r['cash_weight']),
                    'other_weight': _safe_float(r['other_weight']),
                }
                for _, r in trend_rows.iterrows()
            ],
            'current_allocation_breakdown': top_holdings,
            'concentration': concentration,
            'quality_context': {
                'return_4w': _safe_float(quality_row['return_4w'].iloc[0]) if not quality_row.empty else None,
                'return_12w': _safe_float(quality_row['return_12w'].iloc[0]) if not quality_row.empty else None,
                'cash_weight_avg_4w': _safe_float(quality_row['cash_weight_avg_4w'].iloc[0]) if not quality_row.empty else None,
                'holdings_count_avg_4w': _safe_float(quality_row['holdings_count_avg_4w'].iloc[0]) if not quality_row.empty else None,
            },
        })

        lifecycle_rows = lifecycle.loc[lifecycle['model_code'] == model_code].copy().sort_values(['holding_days_observed', 'latest_weight'], ascending=[False, False])
        current_tickers = {item.get('ticker') for item in top_holdings}
        current_lifecycle = lifecycle_rows.loc[(lifecycle_rows['ticker'].isin(current_tickers)) & (lifecycle_rows['is_current_episode'] == 1)].head(20)
        longest_historical = lifecycle_rows.head(20)
        recent_new = recent_changes.loc[(recent_changes['model_code'] == model_code) & (recent_changes['change_type'] == 'new')].sort_values('week_end', ascending=False).head(20)
        recent_exit = recent_changes.loc[(recent_changes['model_code'] == model_code) & (recent_changes['change_type'] == 'exit')].sort_values('week_end', ascending=False).head(20)

        lifecycle_models.append({
            'model_code': model_code,
            'display_name': display_name,
            'date_context': _date_context(asof, mix_row),
            'current_holdings_lifecycle': [
                {
                    'ticker': r['ticker'],
                    'name': r['name'],
                    'asset_type': r['asset_type'],
                    'first_seen_date': pd.to_datetime(r['first_seen_date']).strftime('%Y-%m-%d') if pd.notna(r['first_seen_date']) else None,
                    'last_seen_date': pd.to_datetime(r['last_seen_date']).strftime('%Y-%m-%d') if pd.notna(r['last_seen_date']) else None,
                    'holding_days_observed': _safe_int(r['holding_days_observed']),
                    'latest_weight': _safe_float(r['latest_weight']),
                    'latest_return_since_entry': _safe_float(r['latest_return_since_entry']),
                }
                for _, r in current_lifecycle.iterrows()
            ],
            'longest_historical_holdings': [
                {
                    'ticker': r['ticker'],
                    'name': r['name'],
                    'asset_type': r['asset_type'],
                    'holding_days_observed': _safe_int(r['holding_days_observed']),
                    'first_seen_date': pd.to_datetime(r['first_seen_date']).strftime('%Y-%m-%d') if pd.notna(r['first_seen_date']) else None,
                    'last_seen_date': pd.to_datetime(r['last_seen_date']).strftime('%Y-%m-%d') if pd.notna(r['last_seen_date']) else None,
                    'latest_weight': _safe_float(r['latest_weight']),
                }
                for _, r in longest_historical.iterrows()
            ],
            'recent_new_entries_8w': [
                {
                    'week_end': pd.to_datetime(r['week_end']).strftime('%Y-%m-%d') if pd.notna(r['week_end']) else None,
                    'ticker': r['ticker'],
                    'name': r['name'],
                    'delta_weight': _safe_float(r['delta_weight']),
                }
                for _, r in recent_new.iterrows()
            ],
            'recent_exits_8w': [
                {
                    'week_end': pd.to_datetime(r['week_end']).strftime('%Y-%m-%d') if pd.notna(r['week_end']) else None,
                    'ticker': r['ticker'],
                    'name': r['name'],
                    'delta_weight': _safe_float(r['delta_weight']),
                }
                for _, r in recent_exit.iterrows()
            ],
            'current_holding_highlights': current_highlights,
        })

    return {
        'meta': build_common_meta(asof, 'p2', ['portfolio_structure', 'holding_lifecycle']),
        'portfolio_structure': {'models': structure_models},
        'holding_lifecycle': {'models': lifecycle_models},
    }


def write_bundle(asof: str) -> dict[str, Path]:
    data = build_bundle(asof)
    stamp = asof.replace('-', '')
    outdir = OUTPUT_ROOT / stamp / 'p2_bundle'
    outdir.mkdir(parents=True, exist_ok=True)

    manifest_path = outdir / f'bundle_manifest_{stamp}.json'
    structure_path = outdir / f'portfolio_structure_{stamp}.json'
    lifecycle_path = outdir / f'holding_lifecycle_{stamp}.json'

    structure_path.write_text(json.dumps({'meta': data['meta'], **data['portfolio_structure']}, ensure_ascii=False, indent=2), encoding='utf-8')
    lifecycle_path.write_text(json.dumps({'meta': data['meta'], **data['holding_lifecycle']}, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = finalize_manifest(data['meta'], {
        'portfolio_structure': structure_path,
        'holding_lifecycle': lifecycle_path,
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    return {
        'outdir': outdir,
        'manifest': manifest_path,
        'portfolio_structure': structure_path,
        'holding_lifecycle': lifecycle_path,
    }
