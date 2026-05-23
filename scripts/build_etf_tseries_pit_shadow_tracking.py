from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from tseries_refresh_utils import ensure_run_dir, latest_asof_from_dir, normalize_run_date

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = ""
ASOF_DATE = ""
OUT_DIR = Path()
WF_DIR = Path()


def is_inverse_or_leverage_name(name: object) -> bool:
    text = str(name or '')
    return any(token in text for token in ['레버리지', '인버스', '2X'])


def build_historical_shadow() -> pd.DataFrame:
    df = pd.read_csv(WF_DIR / 'etf_tseries_pit_strict_walkforward_top_picks.csv', dtype={'ticker': str})
    df = df.loc[~df['name'].map(is_inverse_or_leverage_name)].copy()
    df = df.groupby(['stage','signal_date','ticker','name'], as_index=False).agg(pred_prob=('pred_prob','max'), target_hit=('label','max'))
    df['candidate_grade'] = df['stage'].map({'stage1_lower_to_et10':'historical_stage1','stage2_et10_to_et3':'historical_stage2'})
    df['tracking_status'] = 'resolved'
    df['source'] = 'strict_walkforward_pit'
    df['asof_date'] = pd.NA
    return df[['source','stage','signal_date','asof_date','ticker','name','candidate_grade','pred_prob','target_hit','tracking_status']]


def build_current_shadow() -> pd.DataFrame:
    df = pd.read_csv(OUT_DIR / f'etf_tseries_pit_risk_filtered_candidates_{ASOF_DATE}.csv', dtype={'ticker': str})
    if df.empty:
        return pd.DataFrame(columns=['source','stage','signal_date','asof_date','ticker','name','candidate_grade','role_key','theme_bucket','pred_prob','target_hit','tracking_status'])
    df['stage'] = df['candidate_grade'].map({'confirmed':'stage2_et10_to_et3','near':'stage2_et10_to_et3','observe':'stage1_lower_to_et10'})
    df['pred_prob'] = df['stage2_prob'].where(df['stage2_prob'].notna(), df['stage1_prob'])
    df['target_hit'] = pd.NA
    df['tracking_status'] = 'pending'
    df['source'] = 'latest_operational_pit'
    df['asof_date'] = ASOF_DATE
    df['signal_date'] = ASOF_DATE
    for col in ['role_key', 'theme_bucket']:
        if col not in df.columns:
            df[col] = None
    return df[['source','stage','signal_date','asof_date','ticker','name','candidate_grade','role_key','theme_bucket','pred_prob','target_hit','tracking_status']]


def main() -> None:
    ap = argparse.ArgumentParser(description="Build ETF T-series PIT shadow tracking outputs.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD run folder.")
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD candidate asof to use; defaults to latest available in run folder.")
    args = ap.parse_args()

    global RUN_DATE, ASOF_DATE, OUT_DIR, WF_DIR
    RUN_DATE = normalize_run_date(args.run_date)
    run_root = ensure_run_dir(RUN_DATE)
    OUT_DIR = run_root / 'ETF_T_SERIES_OPERATIONALIZATION_PIT'
    WF_DIR = run_root / 'ETF_T_SERIES_PIT_STRICT_WALKFORWARD'
    ASOF_DATE = latest_asof_from_dir(OUT_DIR, r'etf_tseries_pit_risk_filtered_candidates_(\d{4}-\d{2}-\d{2})\.csv')

    historical = build_historical_shadow()
    current = build_current_shadow()
    for col in ['role_key', 'theme_bucket']:
        if col not in historical.columns:
            historical[col] = None
    combined = pd.concat([historical, current], ignore_index=True)
    combined.to_csv(OUT_DIR / f'etf_tseries_pit_shadow_tracking_history_{RUN_DATE}.csv', index=False, encoding='utf-8-sig')

    hist_summary = historical.groupby(['stage','candidate_grade'], as_index=False).agg(candidate_count=('ticker','count'), unique_tickers=('ticker', pd.Series.nunique), avg_pred_prob=('pred_prob','mean'), hit_rate=('target_hit','mean'))
    hist_summary.to_csv(OUT_DIR / f'etf_tseries_pit_shadow_tracking_historical_summary_{RUN_DATE}.csv', index=False, encoding='utf-8-sig')

    latest_summary = current.groupby(['stage','candidate_grade'], as_index=False).agg(candidate_count=('ticker','count'), avg_pred_prob=('pred_prob','mean')) if not current.empty else pd.DataFrame(columns=['stage','candidate_grade','candidate_count','avg_pred_prob'])
    latest_summary.to_csv(OUT_DIR / f'etf_tseries_pit_latest_watchlist_summary_{RUN_DATE}.csv', index=False, encoding='utf-8-sig')

    latest_watch = pd.read_csv(OUT_DIR / f'etf_tseries_pit_risk_filtered_candidates_{ASOF_DATE}.csv', dtype={'ticker': str})
    if latest_watch.empty:
        latest_watch = pd.DataFrame(columns=['candidate_grade','ticker','name','theme_bucket','stage1_prob','stage2_prob'])
    else:
        latest_watch['watch_priority'] = latest_watch['candidate_grade'].map({'confirmed':0,'near':1,'observe':2})
        latest_watch = latest_watch.sort_values(['watch_priority','stage2_prob','stage1_prob'], ascending=[True,False,False], na_position='last').drop(columns=['watch_priority'])
    latest_watch.to_csv(OUT_DIR / f'etf_tseries_pit_latest_watchlist_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')

    md = f"""# ETF T-series PIT Latest Watchlist ({ASOF_DATE})

- confirmed: {int((latest_watch['candidate_grade'] == 'confirmed').sum()) if not latest_watch.empty else 0}
- near: {int((latest_watch['candidate_grade'] == 'near').sum()) if not latest_watch.empty else 0}
- observe: {int((latest_watch['candidate_grade'] == 'observe').sum()) if not latest_watch.empty else 0}
"""
    (OUT_DIR / f'etf_tseries_pit_latest_watchlist_{RUN_DATE}.md').write_text(md, encoding='utf-8')


if __name__ == '__main__':
    main()
