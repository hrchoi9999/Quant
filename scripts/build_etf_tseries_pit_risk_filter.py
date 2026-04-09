from __future__ import annotations

from pathlib import Path
import pandas as pd

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = "20260401"
ASOF_DATE = "2026-03-31"
IN_DIR = BASE_DIR / 'reports' / 'model_upgrade_research' / RUN_DATE / 'ETF_T_SERIES_OPERATIONALIZATION_PIT'

LIQUIDITY_FLOOR = 20_000_000_000
THEME_CAPS = {
    'gold': 1,
    'securities': 1,
    'semiconductor': 2,
    'broad_equity': 1,
    'dividend_income': 1,
    'auto': 1,
    'silver': 1,
    'esg': 1,
    'energy_materials': 2,
    'other': 1,
}
GRADE_ORDER = {'confirmed':0,'near':1,'observe':2}


def classify_theme(row: pd.Series) -> str:
    name = str(row.get('name',''))
    group_key = str(row.get('group_key',''))
    if group_key == 'commodity_gold' or '골드' in name or '금현물' in name:
        return 'gold'
    if '은선물' in name:
        return 'silver'
    if '증권' in name:
        return 'securities'
    if '반도체' in name or 'HBM' in name:
        return 'semiconductor'
    if group_key == 'equity_kr_broad' or '코스피' in name or '코리아TOP10' in name or name.endswith('200'):
        return 'broad_equity'
    if '고배당' in name or '배당' in name or '커버드콜' in name:
        return 'dividend_income'
    if '자동차' in name or '현대차' in name:
        return 'auto'
    if 'ESG' in name:
        return 'esg'
    if '원유' in name or '에너지' in name or '2차전지' in name or '소재' in name:
        return 'energy_materials'
    return 'other'


def _is_truthy(value: object) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {'1', 'true', 't', 'yes', 'y'}


def excluded_by_structural_rule(row: pd.Series) -> str | None:
    name = str(row.get('name', '') or '')
    if float(row.get('liquidity_20d_value', 0) or 0) < LIQUIDITY_FLOOR:
        return 'liquidity_floor'
    if _is_truthy(row.get('is_inverse')) or _is_truthy(row.get('is_leveraged')):
        return 'inverse_or_leverage'
    if any(token in name for token in ['레버리지', '인버스', '2X']):
        return 'inverse_or_leverage'
    return None


def main() -> None:
    df = pd.read_csv(IN_DIR / f'etf_tseries_pit_operational_candidates_{ASOF_DATE}.csv', dtype={'ticker': str})
    df['theme_bucket'] = df.apply(classify_theme, axis=1)
    df['structural_reason'] = df.apply(excluded_by_structural_rule, axis=1)
    df['is_excluded'] = df['structural_reason'].notna()
    df['grade_order'] = df['candidate_grade'].map(GRADE_ORDER)
    df = df.sort_values(['grade_order','stage2_prob','stage1_prob','liquidity_20d_value'], ascending=[True,False,False,False], na_position='last')

    kept_rows=[]
    excluded_rows=[]
    cap_usage={k:0 for k in THEME_CAPS}
    for _, row in df.iterrows():
        row_dict=row.to_dict()
        if row_dict['is_excluded']:
            row_dict['filter_reason']=f"structural_exclusion:{row_dict['structural_reason']}"
            excluded_rows.append(row_dict)
            continue
        theme=row_dict['theme_bucket']
        cap=THEME_CAPS.get(theme,1)
        if cap_usage.get(theme,0) >= cap:
            row_dict['filter_reason']=f'theme_cap_{theme}'
            excluded_rows.append(row_dict)
            continue
        cap_usage[theme]=cap_usage.get(theme,0)+1
        row_dict['filter_reason']='kept'
        kept_rows.append(row_dict)

    kept=pd.DataFrame(kept_rows)
    excluded=pd.DataFrame(excluded_rows)
    keep_cols=['candidate_grade','ticker','name','asset_class','group_key','theme_bucket','liquidity_20d_value','stage1_prob','stage2_prob','filter_reason']
    kept=kept[keep_cols] if not kept.empty else pd.DataFrame(columns=keep_cols)
    excluded=excluded[keep_cols] if not excluded.empty else pd.DataFrame(columns=keep_cols)

    kept.to_csv(IN_DIR / f'etf_tseries_pit_risk_filtered_candidates_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')
    excluded.to_csv(IN_DIR / f'etf_tseries_pit_risk_filtered_excluded_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')
    kept[kept['candidate_grade']=='confirmed'].to_csv(IN_DIR / f'etf_tseries_pit_risk_filtered_confirmed_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')
    kept[kept['candidate_grade']=='near'].to_csv(IN_DIR / f'etf_tseries_pit_risk_filtered_near_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')
    kept[kept['candidate_grade']=='observe'].to_csv(IN_DIR / f'etf_tseries_pit_risk_filtered_observe_{ASOF_DATE}.csv', index=False, encoding='utf-8-sig')

    summary = pd.DataFrame([
        {'bucket':'input_total','count':len(df)},
        {'bucket':'kept_total','count':len(kept)},
        {'bucket':'kept_confirmed','count':int((kept['candidate_grade']=='confirmed').sum())},
        {'bucket':'kept_near','count':int((kept['candidate_grade']=='near').sum())},
        {'bucket':'kept_observe','count':int((kept['candidate_grade']=='observe').sum())},
        {'bucket':'excluded_total','count':len(excluded)},
        {'bucket':'excluded_structural','count':int(excluded['filter_reason'].fillna('').str.startswith('structural_exclusion').sum()) if not excluded.empty else 0},
        {'bucket':'excluded_inverse_or_leverage','count':int((excluded['filter_reason']=='structural_exclusion:inverse_or_leverage').sum()) if not excluded.empty else 0},
        {'bucket':'excluded_liquidity_floor','count':int((excluded['filter_reason']=='structural_exclusion:liquidity_floor').sum()) if not excluded.empty else 0},
    ])
    summary.to_csv(IN_DIR / f'etf_tseries_pit_risk_filter_summary_{RUN_DATE}.csv', index=False, encoding='utf-8-sig')

    md = f"""# ETF T-series PIT Risk Filter ({ASOF_DATE})

- input total: {len(df)}
- kept total: {len(kept)}
- kept confirmed: {int((kept['candidate_grade'] == 'confirmed').sum())}
- kept near: {int((kept['candidate_grade'] == 'near').sum())}
- kept observe: {int((kept['candidate_grade'] == 'observe').sum())}
- excluded total: {len(excluded)}
- excluded inverse/leverage: {int((excluded['filter_reason'] == 'structural_exclusion:inverse_or_leverage').sum()) if not excluded.empty else 0}
- excluded liquidity floor: {int((excluded['filter_reason'] == 'structural_exclusion:liquidity_floor').sum()) if not excluded.empty else 0}
"""
    (IN_DIR / f'etf_tseries_pit_risk_filter_{RUN_DATE}.md').write_text(md, encoding='utf-8')


if __name__ == '__main__':
    main()
