from __future__ import annotations

import argparse
import sys
from pathlib import Path
import re
import pandas as pd

from tseries_refresh_utils import ensure_run_dir, latest_asof_from_dir, normalize_run_date

if str(Path(r"D:\Quant")) not in sys.path:
    sys.path.insert(0, str(Path(r"D:\Quant")))

from src.universe.etf_role_classifier import add_role_classification

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = ""
ASOF_DATE = ""
TUNED_DIR = Path()
OUT_DIR = Path()


def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(TUNED_DIR / name, dtype={'ticker': str})


def enrich_role_columns(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        'role_key': 'UNCLASSIFIED',
        'role_confidence': 0.0,
        'role_reason': '',
        'role_schema_version': 'ETF_ROLE_COMMON_V1',
        'purity_issue': '',
        'is_role_purity_exception': False,
    }
    if df.empty:
        out = df.copy()
        for col, default in defaults.items():
            if col not in out.columns:
                out[col] = pd.Series(dtype=type(default))
        return out
    out = df.copy()
    out['ticker'] = out['ticker'].astype(str).str.zfill(6)
    asof_compact = ASOF_DATE.replace('-', '')
    meta_path = BASE_DIR / 'data' / 'universe' / f'etf_meta_{asof_compact}.csv'
    if meta_path.exists():
        meta = pd.read_csv(meta_path, dtype={'ticker': str})
        meta['ticker'] = meta['ticker'].astype(str).str.zfill(6)
        if 'role_key' not in meta.columns:
            meta = add_role_classification(meta)
        role_cols = [
            'ticker', 'role_key', 'role_confidence', 'role_reason',
            'role_schema_version', 'purity_issue', 'is_role_purity_exception',
        ]
        role_cols = [c for c in role_cols if c in meta.columns]
        out = out.merge(meta[role_cols].drop_duplicates('ticker'), on='ticker', how='left')
    if 'role_key' not in out.columns:
        out = add_role_classification(out)
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default
        out[col] = out[col].fillna(default)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Build ETF T-series PIT operational candidates.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD run folder.")
    ap.add_argument("--asof", default=None, help="Accepted for interface consistency; latest tuned PIT asof is used.")
    args = ap.parse_args()

    global RUN_DATE, ASOF_DATE, TUNED_DIR, OUT_DIR
    RUN_DATE = normalize_run_date(args.run_date)
    run_root = ensure_run_dir(RUN_DATE)
    TUNED_DIR = run_root / 'ETF_TWO_STAGE_DISCOVERY_TUNED_PIT'
    OUT_DIR = run_root / 'ETF_T_SERIES_OPERATIONALIZATION_PIT'
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ASOF_DATE = latest_asof_from_dir(TUNED_DIR, r'etf_two_stage_tuned_pit_stage1_candidates_(\d{4}-\d{2}-\d{2})\.csv')

    stage1 = load_csv(f'etf_two_stage_tuned_pit_stage1_candidates_{ASOF_DATE}.csv')
    confirmed = load_csv(f'etf_two_stage_tuned_pit_stage2_confirmed_{ASOF_DATE}.csv')
    near = load_csv(f'etf_two_stage_tuned_pit_stage2_near_{ASOF_DATE}.csv')

    confirmed_tickers = set(confirmed['ticker'])
    near_tickers = set(near['ticker'])
    observe = stage1[~stage1['ticker'].isin(confirmed_tickers) & ~stage1['ticker'].isin(near_tickers)].copy()

    confirmed['candidate_grade'] = 'confirmed'
    near['candidate_grade'] = 'near'
    observe['candidate_grade'] = 'observe'
    observe['stage2_prob'] = pd.NA

    keep_cols = [
        'signal_date','feature_date','ticker','name','asset_class','group_key','currency_exposure','is_inverse','is_leveraged',
        'expanded_group','liquidity_20d_value','ret_20d','ret_60d','ret_120d','vol_20d','vol_60d','dist_ma20','dist_ma60','dist_ma120',
        'ma20_ma60_gap','ma60_ma120_gap','rsi20','stage1_prob','stage2_prob','candidate_grade'
    ]
    role_cols = ['role_key','role_confidence','role_reason','role_schema_version','purity_issue','is_role_purity_exception']
    confirmed = enrich_role_columns(confirmed)[keep_cols + role_cols]
    near = enrich_role_columns(near)[keep_cols + role_cols]
    observe = enrich_role_columns(observe)[keep_cols + role_cols]
    combined = pd.concat([confirmed, near, observe], ignore_index=True)
    combined['grade_order'] = combined['candidate_grade'].map({'confirmed':0,'near':1,'observe':2})
    combined = combined.sort_values(['grade_order','stage2_prob','stage1_prob','liquidity_20d_value'], ascending=[True,False,False,False], na_position='last').drop(columns=['grade_order'])

    summary = pd.DataFrame([
        {'grade':'confirmed','count':len(confirmed),'avg_stage1_prob':round(confirmed['stage1_prob'].mean(),6),'avg_stage2_prob':round(confirmed['stage2_prob'].mean(),6)},
        {'grade':'near','count':len(near),'avg_stage1_prob':round(near['stage1_prob'].mean(),6),'avg_stage2_prob':round(near['stage2_prob'].mean(),6)},
        {'grade':'observe','count':len(observe),'avg_stage1_prob':round(observe['stage1_prob'].mean(),6),'avg_stage2_prob':''},
        {'grade':'total_stage1','count':len(stage1),'avg_stage1_prob':round(stage1['stage1_prob'].mean(),6),'avg_stage2_prob':''},
    ])

    summary.to_csv(OUT_DIR / f'etf_tseries_pit_operational_candidate_summary_{RUN_DATE}.csv', index=False, encoding='utf-8-sig')
    confirmed.to_csv(OUT_DIR / f'etf_tseries_pit_confirmed_candidates_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')
    near.to_csv(OUT_DIR / f'etf_tseries_pit_near_candidates_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')
    observe.to_csv(OUT_DIR / f'etf_tseries_pit_observe_candidates_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')
    combined.to_csv(OUT_DIR / f'etf_tseries_pit_operational_candidates_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')

    md = f"""# ETF T-series PIT Operational Candidates ({ASOF_DATE})

- stage1 universe candidates: {len(stage1)}
- confirmed candidates: {len(confirmed)}
- near candidates: {len(near)}
- observe candidates: {len(observe)}
"""
    (OUT_DIR / f'etf_tseries_pit_operational_candidates_{RUN_DATE}.md').write_text(md, encoding='utf-8')


if __name__ == '__main__':
    main()
