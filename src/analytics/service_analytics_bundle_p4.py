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


def _latest_per_model(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors='coerce')
    latest = work.groupby('model_code', as_index=False)[date_col].max()
    return work.merge(latest, on=['model_code', date_col], how='inner')


def _load_frames() -> dict[str, pd.DataFrame]:
    conn = sqlite3.connect(ANALYTICS_DB)
    try:
        overview = _read_table(conn, 'analytics_model_run_overview')
        asset_detail = _read_table(conn, 'analytics_model_asset_detail_weekly')
        change_activity = _read_table(conn, 'analytics_model_change_activity_weekly')
        change_impact = _read_table(conn, 'analytics_model_change_impact_weekly')
    finally:
        conn.close()
    return {
        'overview': overview,
        'asset_detail': asset_detail,
        'change_activity': change_activity,
        'change_impact': change_impact,
    }


def _date_context(asof: str, week_end: object) -> dict[str, object]:
    dt = pd.to_datetime(week_end, errors='coerce')
    value = dt.strftime('%Y-%m-%d') if pd.notna(dt) else None
    return {
        'asof_date': asof,
        'signal_date': asof,
        'effective_date': asof,
        'week_end': value,
    }


def _intensity_label(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 35:
        return 'high'
    if score >= 15:
        return 'medium'
    return 'low'


def build_bundle(asof: str) -> dict[str, object]:
    frames = _load_frames()
    overview = frames['overview'].copy().sort_values('model_code')
    asset_detail = frames['asset_detail'].copy()
    asset_detail['week_end'] = pd.to_datetime(asset_detail['week_end'], errors='coerce')
    change_activity = frames['change_activity'].copy()
    change_activity['week_end'] = pd.to_datetime(change_activity['week_end'], errors='coerce')
    change_impact = frames['change_impact'].copy()
    change_impact['event_week_end'] = pd.to_datetime(change_impact['event_week_end'], errors='coerce')
    change_impact['first_seen_date'] = pd.to_datetime(change_impact['first_seen_date'], errors='coerce')
    change_impact['last_seen_date'] = pd.to_datetime(change_impact['last_seen_date'], errors='coerce')

    latest_asset_detail = _latest_per_model(asset_detail, 'week_end')
    latest_change_activity = _latest_per_model(change_activity, 'week_end')
    latest_week = change_activity['week_end'].max()
    recent_cut = latest_week - pd.Timedelta(days=56) if pd.notna(latest_week) else pd.Timestamp(asof)

    exposure_models = []
    impact_models = []

    for _, row in overview.iterrows():
        model_code = str(row['model_code'])
        display_name = row['display_name']
        latest_detail_rows = latest_asset_detail.loc[latest_asset_detail['model_code'] == model_code].sort_values('bucket_weight', ascending=False)
        latest_activity_row = latest_change_activity.loc[latest_change_activity['model_code'] == model_code]
        detail_trend_rows = asset_detail.loc[asset_detail['model_code'] == model_code].sort_values('week_end').tail(26 * 8)
        impact_rows = change_impact.loc[(change_impact['model_code'] == model_code) & (change_impact['event_week_end'] >= recent_cut)].sort_values(['event_week_end', 'event_type'], ascending=[False, True])
        new_rows = impact_rows.loc[impact_rows['event_type'] == 'new'].head(20)
        exit_rows = impact_rows.loc[impact_rows['event_type'] == 'exit'].head(20)

        trend_points = []
        for week_end, grp in detail_trend_rows.groupby('week_end'):
            buckets = {str(r['detail_bucket']): _safe_float(r['bucket_weight']) for _, r in grp.iterrows()}
            trend_points.append({
                'week_end': pd.to_datetime(week_end).strftime('%Y-%m-%d') if pd.notna(week_end) else None,
                'bucket_weights': buckets,
            })
        trend_points = trend_points[-26:]

        latest_score = _safe_float(latest_activity_row['change_intensity_score'].iloc[0]) if not latest_activity_row.empty else None

        exposure_models.append({
            'model_code': model_code,
            'display_name': display_name,
            'date_context': _date_context(asof, latest_detail_rows['week_end'].iloc[0] if not latest_detail_rows.empty else None),
            'latest_asset_detail': [
                {
                    'detail_bucket': r['detail_bucket'],
                    'bucket_weight': _safe_float(r['bucket_weight']),
                }
                for _, r in latest_detail_rows.iterrows()
            ],
            'asset_detail_trend_26w': trend_points,
            'latest_change_activity': {
                'change_intensity_score': latest_score,
                'change_intensity_label': _intensity_label(latest_score),
                'event_count_total': _safe_int(latest_activity_row['event_count_total'].iloc[0]) if not latest_activity_row.empty else None,
                'abs_delta_sum': _safe_float(latest_activity_row['abs_delta_sum'].iloc[0]) if not latest_activity_row.empty else None,
            },
        })

        change_trend = change_activity.loc[change_activity['model_code'] == model_code].sort_values('week_end').tail(26)
        impact_models.append({
            'model_code': model_code,
            'display_name': display_name,
            'date_context': _date_context(asof, latest_activity_row['week_end'].iloc[0] if not latest_activity_row.empty else None),
            'latest_change_activity': {
                'new_count': _safe_int(latest_activity_row['new_count'].iloc[0]) if not latest_activity_row.empty else None,
                'exit_count': _safe_int(latest_activity_row['exit_count'].iloc[0]) if not latest_activity_row.empty else None,
                'increase_count': _safe_int(latest_activity_row['increase_count'].iloc[0]) if not latest_activity_row.empty else None,
                'decrease_count': _safe_int(latest_activity_row['decrease_count'].iloc[0]) if not latest_activity_row.empty else None,
                'event_count_total': _safe_int(latest_activity_row['event_count_total'].iloc[0]) if not latest_activity_row.empty else None,
                'abs_delta_sum': _safe_float(latest_activity_row['abs_delta_sum'].iloc[0]) if not latest_activity_row.empty else None,
                'change_intensity_score': latest_score,
                'change_intensity_label': _intensity_label(latest_score),
            },
            'change_activity_trend_26w': [
                {
                    'week_end': pd.to_datetime(r['week_end']).strftime('%Y-%m-%d') if pd.notna(r['week_end']) else None,
                    'new_count': _safe_int(r['new_count']),
                    'exit_count': _safe_int(r['exit_count']),
                    'event_count_total': _safe_int(r['event_count_total']),
                    'abs_delta_sum': _safe_float(r['abs_delta_sum']),
                    'change_intensity_score': _safe_float(r['change_intensity_score']),
                }
                for _, r in change_trend.iterrows()
            ],
            'recent_new_entries_impact_8w': [
                {
                    'event_week_end': pd.to_datetime(r['event_week_end']).strftime('%Y-%m-%d') if pd.notna(r['event_week_end']) else None,
                    'ticker': r['ticker'],
                    'name': r['name'],
                    'delta_weight': _safe_float(r['delta_weight']),
                    'holding_days_observed': _safe_int(r['holding_days_observed']),
                    'return_since_entry_observed': _safe_float(r['return_since_entry_observed']),
                    'outcome_status': r['outcome_status'],
                }
                for _, r in new_rows.iterrows()
            ],
            'recent_exits_impact_8w': [
                {
                    'event_week_end': pd.to_datetime(r['event_week_end']).strftime('%Y-%m-%d') if pd.notna(r['event_week_end']) else None,
                    'ticker': r['ticker'],
                    'name': r['name'],
                    'delta_weight': _safe_float(r['delta_weight']),
                    'holding_days_observed': _safe_int(r['holding_days_observed']),
                    'return_since_entry_observed': _safe_float(r['return_since_entry_observed']),
                    'outcome_status': r['outcome_status'],
                }
                for _, r in exit_rows.iterrows()
            ],
            'impact_summary': {
                'new_events_8w': len(new_rows),
                'exit_events_8w': len(exit_rows),
                'avg_new_return_observed_8w': _safe_float(new_rows['return_since_entry_observed'].mean()) if not new_rows.empty else None,
                'avg_exit_return_observed_8w': _safe_float(exit_rows['return_since_entry_observed'].mean()) if not exit_rows.empty else None,
            },
        })

    return {
        'meta': build_common_meta(asof, 'p4', ['asset_exposure_detail', 'change_impact']),
        'asset_exposure_detail': {'models': exposure_models},
        'change_impact': {'models': impact_models},
    }


def write_bundle(asof: str) -> dict[str, Path]:
    data = build_bundle(asof)
    stamp = asof.replace('-', '')
    outdir = OUTPUT_ROOT / stamp / 'p4_bundle'
    outdir.mkdir(parents=True, exist_ok=True)

    manifest_path = outdir / f'bundle_manifest_{stamp}.json'
    exposure_path = outdir / f'asset_exposure_detail_{stamp}.json'
    impact_path = outdir / f'change_impact_{stamp}.json'

    exposure_path.write_text(json.dumps({'meta': data['meta'], **data['asset_exposure_detail']}, ensure_ascii=False, indent=2), encoding='utf-8')
    impact_path.write_text(json.dumps({'meta': data['meta'], **data['change_impact']}, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = finalize_manifest(data['meta'], {
        'asset_exposure_detail': exposure_path,
        'change_impact': impact_path,
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    return {
        'outdir': outdir,
        'manifest': manifest_path,
        'asset_exposure_detail': exposure_path,
        'change_impact': impact_path,
    }
