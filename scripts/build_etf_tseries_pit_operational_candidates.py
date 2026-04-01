from __future__ import annotations

from pathlib import Path
import pandas as pd

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = "20260401"
ASOF_DATE = "2026-03-31"
TUNED_DIR = BASE_DIR / 'reports' / 'model_upgrade_research' / RUN_DATE / 'ETF_TWO_STAGE_DISCOVERY_TUNED_PIT'
OUT_DIR = BASE_DIR / 'reports' / 'model_upgrade_research' / RUN_DATE / 'ETF_T_SERIES_OPERATIONALIZATION_PIT'
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(TUNED_DIR / name, dtype={'ticker': str})


def main() -> None:
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
    confirmed = confirmed[keep_cols]
    near = near[keep_cols]
    observe = observe[keep_cols]
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
