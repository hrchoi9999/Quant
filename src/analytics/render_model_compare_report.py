from __future__ import annotations

from pathlib import Path

import pandas as pd


def _to_md_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return '(empty)'
    work = df.copy()
    cols = [str(c) for c in work.columns]
    lines = []
    lines.append('| ' + ' | '.join(cols) + ' |')
    lines.append('| ' + ' | '.join(['---'] * len(cols)) + ' |')
    for row in work.itertuples(index=False, name=None):
        vals = []
        for v in row:
            if pd.isna(v):
                vals.append('')
            else:
                vals.append(str(v))
        lines.append('| ' + ' | '.join(vals) + ' |')
    return '\n'.join(lines)


def render_report(*, out_path: Path, summary_df: pd.DataFrame, periods_df: pd.DataFrame, yearly_df: pd.DataFrame, regime_df: pd.DataFrame, cost_df: pd.DataFrame, compare_note: str) -> None:
    lines = []
    lines.append('# Integrated Model Comparison Report')
    lines.append('')
    lines.append(compare_note)
    lines.append('')
    lines.append('## Full Summary')
    lines.append('')
    lines.append(_to_md_table(summary_df))
    lines.append('')
    lines.append('## Preferred Period Table')
    lines.append('')
    pref = periods_df.loc[periods_df['period'].isin(['1Y','2Y','3Y','5Y','FULL'])].copy()
    lines.append(_to_md_table(pref))
    lines.append('')
    lines.append('## Yearly')
    lines.append('')
    lines.append(_to_md_table(yearly_df))
    lines.append('')
    lines.append('## Regime')
    lines.append('')
    lines.append(_to_md_table(regime_df))
    lines.append('')
    lines.append('## Cost Sensitivity')
    lines.append('')
    lines.append(_to_md_table(cost_df))
    out_path.write_text('\n'.join(lines), encoding='utf-8')
