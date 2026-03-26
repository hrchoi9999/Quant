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
        quality = _read_table(conn, 'analytics_model_quality_weekly')
        changes = _read_table(conn, 'analytics_model_change_log')
        quality_checks = _read_table(conn, 'analytics_data_quality_checks')
    finally:
        conn.close()
    return {
        'overview': overview,
        'quality': quality,
        'changes': changes,
        'quality_checks': quality_checks,
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


def _date_context(asof: str, qrow: pd.DataFrame) -> dict[str, object]:
    week_end = pd.to_datetime(qrow['week_end'].iloc[0], errors='coerce') if not qrow.empty else pd.NaT
    return {
        'asof_date': asof,
        'signal_date': asof,
        'effective_date': asof,
        'week_end': week_end.strftime('%Y-%m-%d') if pd.notna(week_end) else None,
        'quality_week_end': week_end.strftime('%Y-%m-%d') if pd.notna(week_end) else None,
    }


def _build_briefing_points(
    display_name: str,
    return_4w: float | None,
    return_12w: float | None,
    current_drawdown: float | None,
    new_8w: int,
    exit_8w: int,
    cash_weight: float | None,
    rel_vs_bm_12w: float | None,
    turnover_avg_4w: float | None,
    top5_weight: float | None,
    holdings_hhi: float | None,
) -> list[str]:
    points: list[str] = []
    if return_4w is not None:
        if return_4w >= 0.05:
            points.append(f'{display_name}은 최근 4주 성과가 강한 편입니다.')
        elif return_4w <= -0.03:
            points.append(f'{display_name}은 최근 4주 성과가 약해 단기 점검이 필요합니다.')
        else:
            points.append(f'{display_name}은 최근 4주 성과가 중립권에 가깝습니다.')
    if return_12w is not None:
        if return_12w >= 0.20:
            points.append('최근 12주 흐름은 우상향 성격이 분명합니다.')
        elif return_12w <= 0:
            points.append('최근 12주 기준으로는 추세 강도가 높지 않습니다.')
    if rel_vs_bm_12w is not None:
        if rel_vs_bm_12w >= 0.05:
            points.append('최근 12주 기준으로 벤치마크 대비 상대성과가 좋은 편입니다.')
        elif rel_vs_bm_12w <= -0.05:
            points.append('최근 12주 기준으로 벤치마크 대비 상대성과는 약한 편입니다.')
    if current_drawdown is not None:
        if current_drawdown <= -0.10:
            points.append('현재 낙폭이 큰 편이라 리스크 관리 관점의 해석이 필요합니다.')
        elif current_drawdown >= -0.03:
            points.append('현재 낙폭은 비교적 얕은 편입니다.')
    total_changes = new_8w + exit_8w
    if total_changes >= 20:
        points.append('최근 8주간 종목 교체가 많아 변화 강도가 높은 모델입니다.')
    elif total_changes == 0:
        points.append('최근 8주간 신규/제외 변화가 거의 없어 포트폴리오 유지 성향이 강합니다.')
    if turnover_avg_4w is not None:
        if turnover_avg_4w >= 0.20:
            points.append('최근 4주 평균 회전율이 높아 포트폴리오 조정 강도가 큰 편입니다.')
        elif turnover_avg_4w <= 0.05:
            points.append('최근 4주 평균 회전율이 낮아 포트폴리오 유지 성향이 뚜렷합니다.')
    if top5_weight is not None:
        if top5_weight >= 0.45:
            points.append('상위 5개 보유 비중이 높아 핵심 종목 집중도가 큰 편입니다.')
        elif top5_weight <= 0.25:
            points.append('상위 5개 보유 비중이 과도하지 않아 분산도가 상대적으로 높습니다.')
    elif holdings_hhi is not None and holdings_hhi >= 0.10:
        points.append('전체 보유구성의 집중도가 다소 높은 편입니다.')
    if cash_weight is not None:
        if cash_weight >= 0.15:
            points.append('현금 비중이 상대적으로 높아 방어적인 성격이 일부 반영돼 있습니다.')
        elif cash_weight <= 0.05:
            points.append('현금 비중이 낮아 자산 투자 비중이 높은 상태입니다.')
    unique_points = []
    for point in points:
        if point not in unique_points:
            unique_points.append(point)
    return unique_points[:5]


def build_bundle(asof: str) -> dict[str, object]:
    frames = _load_frames()
    overview = frames['overview'].copy().sort_values('model_code')
    quality = frames['quality'].copy()
    quality['week_end'] = pd.to_datetime(quality['week_end'], errors='coerce')
    latest_quality = _latest_per_model(quality, 'week_end')
    quality_trend = quality.sort_values(['model_code', 'week_end'])

    changes = frames['changes'].copy()
    changes['week_end'] = pd.to_datetime(changes['week_end'], errors='coerce')
    latest_week = changes['week_end'].max()
    recent_cut = latest_week - pd.Timedelta(days=56)
    recent_changes = changes.loc[changes['week_end'] >= recent_cut].copy()
    one_week_cut = latest_week - pd.Timedelta(days=7)
    one_week_changes = changes.loc[changes['week_end'] >= one_week_cut].copy()

    p1 = _load_p1_today(asof)
    quality_checks = frames['quality_checks'].copy()

    quality_models = []
    briefing_models = []

    for _, row in overview.iterrows():
        model_code = str(row['model_code'])
        display_name = row['display_name']
        qrow = latest_quality.loc[latest_quality['model_code'] == model_code]
        qtrend = quality_trend.loc[quality_trend['model_code'] == model_code].tail(26)
        p1_row = p1.get(model_code, {})
        recent_summary = p1_row.get('recent_change_summary', {})
        one_week_model_changes = one_week_changes.loc[one_week_changes['model_code'] == model_code].sort_values(['week_end', 'change_type', 'delta_weight'], ascending=[False, True, False])
        recent_model_changes = recent_changes.loc[recent_changes['model_code'] == model_code].sort_values(['week_end', 'change_type', 'delta_weight'], ascending=[False, True, False])
        model_quality_checks = quality_checks.loc[quality_checks['model_code'] == model_code].sort_values('check_name')

        return_4w = _safe_float(qrow['return_4w'].iloc[0]) if not qrow.empty else None
        return_12w = _safe_float(qrow['return_12w'].iloc[0]) if not qrow.empty else None
        current_drawdown = _safe_float(qrow['drawdown_current'].iloc[0]) if not qrow.empty else None
        rel_vs_bm = _safe_float(qrow['relative_strength_vs_benchmark_4w'].iloc[0]) if not qrow.empty else None
        rel_vs_bm_12w = _safe_float(qrow['relative_strength_vs_benchmark_12w'].iloc[0]) if not qrow.empty else None
        rel_vs_bm_52w = _safe_float(qrow['relative_strength_vs_benchmark_52w'].iloc[0]) if not qrow.empty else None
        cash_weight_avg_4w = _safe_float(qrow['cash_weight_avg_4w'].iloc[0]) if not qrow.empty else None
        holdings_count_avg_4w = _safe_float(qrow['holdings_count_avg_4w'].iloc[0]) if not qrow.empty else None
        turnover_1w = _safe_float(qrow['turnover_1w'].iloc[0]) if not qrow.empty else None
        turnover_avg_4w = _safe_float(qrow['turnover_avg_4w'].iloc[0]) if not qrow.empty else None
        top1_weight = _safe_float(qrow['top1_weight'].iloc[0]) if not qrow.empty else None
        top3_weight = _safe_float(qrow['top3_weight'].iloc[0]) if not qrow.empty else None
        top5_weight = _safe_float(qrow['top5_weight'].iloc[0]) if not qrow.empty else None
        holdings_hhi = _safe_float(qrow['holdings_hhi'].iloc[0]) if not qrow.empty else None
        asset_mix = p1_row.get('asset_mix', {})
        cash_weight = asset_mix.get('cash_weight')
        new_8w = int(recent_summary.get('new_8w', 0) or 0)
        exit_8w = int(recent_summary.get('exit_8w', 0) or 0)
        increase_8w = int(recent_summary.get('increase_8w', 0) or 0)
        decrease_8w = int(recent_summary.get('decrease_8w', 0) or 0)

        quality_models.append({
            'model_code': model_code,
            'display_name': display_name,
            'risk_grade': row['risk_grade'],
            'date_context': _date_context(asof, qrow),
            'latest_quality': {
                'cagr': _safe_float(row['cagr']),
                'mdd': _safe_float(row['mdd']),
                'sharpe': _safe_float(row['sharpe']),
                'return_4w': return_4w,
                'return_12w': return_12w,
                'current_drawdown': current_drawdown,
                'relative_strength_vs_benchmark_4w': rel_vs_bm,
                'relative_strength_vs_benchmark_12w': rel_vs_bm_12w,
                'relative_strength_vs_benchmark_52w': rel_vs_bm_52w,
                'cash_weight_avg_4w': cash_weight_avg_4w,
                'holdings_count_avg_4w': holdings_count_avg_4w,
                'turnover_1w': turnover_1w,
                'turnover_avg_4w': turnover_avg_4w,
                'top1_weight': top1_weight,
                'top3_weight': top3_weight,
                'top5_weight': top5_weight,
                'holdings_hhi': holdings_hhi,
            },
            'quality_trend_26w': [
                {
                    'week_end': pd.to_datetime(r['week_end']).strftime('%Y-%m-%d') if pd.notna(r['week_end']) else None,
                    'return_1w': _safe_float(r['return_1w']),
                    'return_4w': _safe_float(r['return_4w']),
                    'return_12w': _safe_float(r['return_12w']),
                    'return_52w': _safe_float(r['return_52w']),
                    'drawdown_current': _safe_float(r['drawdown_current']),
                    'relative_strength_vs_benchmark_4w': _safe_float(r['relative_strength_vs_benchmark_4w']),
                    'relative_strength_vs_benchmark_12w': _safe_float(r['relative_strength_vs_benchmark_12w']),
                    'relative_strength_vs_benchmark_52w': _safe_float(r['relative_strength_vs_benchmark_52w']),
                    'cash_weight_avg_4w': _safe_float(r['cash_weight_avg_4w']),
                    'holdings_count_avg_4w': _safe_float(r['holdings_count_avg_4w']),
                    'turnover_1w': _safe_float(r['turnover_1w']),
                    'turnover_avg_4w': _safe_float(r['turnover_avg_4w']),
                    'top1_weight': _safe_float(r['top1_weight']),
                    'top3_weight': _safe_float(r['top3_weight']),
                    'top5_weight': _safe_float(r['top5_weight']),
                    'holdings_hhi': _safe_float(r['holdings_hhi']),
                }
                for _, r in qtrend.iterrows()
            ],
            'change_density': {
                'new_8w': new_8w,
                'exit_8w': exit_8w,
                'increase_8w': increase_8w,
                'decrease_8w': decrease_8w,
            },
            'quality_checks': [
                {
                    'check_name': r['check_name'],
                    'status': r['status'],
                    'metric_value': _safe_float(r['metric_value']),
                    'detail': r['detail'],
                }
                for _, r in model_quality_checks.iterrows()
            ],
        })

        briefing_models.append({
            'model_code': model_code,
            'display_name': display_name,
            'date_context': _date_context(asof, qrow),
            'summary': {
                'return_4w': return_4w,
                'return_12w': return_12w,
                'current_drawdown': current_drawdown,
                'cash_weight': cash_weight,
                'new_8w': new_8w,
                'exit_8w': exit_8w,
                'relative_strength_vs_benchmark_12w': rel_vs_bm_12w,
                'turnover_avg_4w': turnover_avg_4w,
                'top5_weight': top5_weight,
            },
            'briefing_points': _build_briefing_points(display_name, return_4w, return_12w, current_drawdown, new_8w, exit_8w, cash_weight, rel_vs_bm_12w, turnover_avg_4w, top5_weight, holdings_hhi),
            'top_holdings': p1_row.get('top_holdings', [])[:5],
            'one_week_changes': [
                {
                    'week_end': pd.to_datetime(r['week_end']).strftime('%Y-%m-%d') if pd.notna(r['week_end']) else None,
                    'ticker': r['ticker'],
                    'name': r['name'],
                    'change_type': r['change_type'],
                    'delta_weight': _safe_float(r['delta_weight']),
                }
                for _, r in one_week_model_changes.head(12).iterrows()
            ],
            'recent_changes_8w': [
                {
                    'week_end': pd.to_datetime(r['week_end']).strftime('%Y-%m-%d') if pd.notna(r['week_end']) else None,
                    'ticker': r['ticker'],
                    'name': r['name'],
                    'change_type': r['change_type'],
                    'delta_weight': _safe_float(r['delta_weight']),
                }
                for _, r in recent_model_changes.head(20).iterrows()
            ],
        })

    return {
        'meta': build_common_meta(asof, 'p3', ['model_quality', 'weekly_briefing']),
        'model_quality': {'models': quality_models},
        'weekly_briefing': {'models': briefing_models},
    }


def write_bundle(asof: str) -> dict[str, Path]:
    data = build_bundle(asof)
    stamp = asof.replace('-', '')
    outdir = OUTPUT_ROOT / stamp / 'p3_bundle'
    outdir.mkdir(parents=True, exist_ok=True)

    manifest_path = outdir / f'bundle_manifest_{stamp}.json'
    quality_path = outdir / f'model_quality_{stamp}.json'
    briefing_path = outdir / f'weekly_briefing_{stamp}.json'

    quality_path.write_text(json.dumps({'meta': data['meta'], **data['model_quality']}, ensure_ascii=False, indent=2), encoding='utf-8')
    briefing_path.write_text(json.dumps({'meta': data['meta'], **data['weekly_briefing']}, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = finalize_manifest(data['meta'], {
        'model_quality': quality_path,
        'weekly_briefing': briefing_path,
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    return {
        'outdir': outdir,
        'manifest': manifest_path,
        'model_quality': quality_path,
        'weekly_briefing': briefing_path,
    }
