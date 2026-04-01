from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(r"D:\Quant")
TRANSITION_PATH = PROJECT_ROOT / r"reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_BACKFILL_V1\etf_tseries_pit_transition_panel.csv"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_TUNING"
OUTDIR.mkdir(parents=True, exist_ok=True)

CAT_FEATURES = ["asset_class", "group_key", "currency_exposure"]
LOWER_BUCKETS = ["OUTSIDE", "ET50_ex_ET30", "ET30_ex_ET10"]
MIN_TRAIN_WINDOWS = 24

STAGE1_SETS = {
    "baseline8": ["ret_60d","ret_120d","ma20_ma60_gap","ma60_ma120_gap","vol_60d","dist_ma120","vol_20d","dist_ma60"],
    "momentum_trend": ["ret_60d","ret_120d","ret_240d","dist_ma60","dist_ma120","ma20_ma60_gap","ma60_ma120_gap","rsi20"],
    "momentum_stack": ["ret_20d","ret_60d","ret_120d","dist_ma20","dist_ma60","dist_ma120","ma20_ma60_gap","ma60_ma120_gap"],
    "compact6": ["ret_60d","ret_120d","ma60_ma120_gap","dist_ma120","vol_20d","liquidity_20d_value"],
}
STAGE2_SETS = {
    "baseline8": ["vol_20d","vol_60d","dist_ma20","dist_ma120","dist_ma60","ret_120d","ma60_ma120_gap","ret_20d"],
    "momentum_stack": ["ret_20d","ret_60d","ret_120d","dist_ma20","dist_ma60","dist_ma120","ma60_ma120_gap","vol_20d"],
    "vol_trend_compact": ["vol_20d","vol_60d","dist_ma20","dist_ma60","dist_ma120","ma20_ma60_gap","ma60_ma120_gap"],
    "top5_transition": ["ret_60d","ret_120d","vol_20d","dist_ma20","dist_ma60"],
}

STAGE1_CONFIGS = [
    ("top_ratio", 0.08),
    ("top_ratio", 0.10),
    ("top_ratio", 0.12),
    ("threshold", 0.50),
    ("threshold", 0.55),
]
STAGE2_CONFIGS = [
    ("top_ratio", 0.02),
    ("top_ratio", 0.03),
    ("top_ratio", 0.05),
    ("threshold", 0.55),
    ("threshold", 0.60),
    ("threshold", 0.65),
    ("threshold", 0.70),
]


def build_pipeline(num_features: list[str]) -> Pipeline:
    pre = ColumnTransformer([
        ("num", StandardScaler(), num_features),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
    ])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    return Pipeline([("pre", pre), ("clf", clf)])


def eval_mode(df: pd.DataFrame, prob_col: str, label_col: str, mode: str, param: float) -> tuple[float, float, float, float, float]:
    ranked = df.sort_values([prob_col, "ticker"], ascending=[False, True]).copy()
    if mode == "top_ratio":
        n = max(1, int(math.ceil(len(ranked) * param)))
        top = ranked.head(min(n, len(ranked))).copy()
    else:
        top = ranked[ranked[prob_col] >= param].copy()
        if top.empty:
            return np.nan, np.nan, np.nan, np.nan, 0.0
    positives = int(df[label_col].sum())
    hits = int(top[label_col].sum())
    precision = float(top[label_col].mean()) if len(top) else np.nan
    capture = float(hits / positives) if positives else np.nan
    base = float(df[label_col].mean()) if len(df) else np.nan
    lift = float(precision / base) if base and np.isfinite(base) and base > 0 else np.nan
    return precision, capture, lift, base, float(len(top))


def strict_tuning(panel: pd.DataFrame, feature_sets: dict[str, list[str]], label_col: str, configs: list[tuple[str, float]], stage_name: str) -> pd.DataFrame:
    work = panel.copy()
    work["signal_date"] = pd.to_datetime(work["signal_date"])
    dates = sorted(work["signal_date"].drop_duplicates().tolist())
    rows = []
    for set_name, num_features in feature_sets.items():
        use = work.dropna(subset=num_features).copy()
        use_dates = sorted(use["signal_date"].drop_duplicates().tolist())
        if len(use_dates) <= MIN_TRAIN_WINDOWS:
            continue
        window_preds = []
        for i in range(MIN_TRAIN_WINDOWS, len(use_dates)):
            test_date = use_dates[i]
            train_dates = use_dates[:i]
            train_df = use[use["signal_date"].isin(train_dates)].copy()
            test_df = use[use["signal_date"] == test_date].copy()
            if train_df.empty or test_df.empty or train_df[label_col].nunique() < 2 or test_df[label_col].nunique() < 2:
                continue
            pipe = build_pipeline(num_features)
            pipe.fit(train_df[num_features + CAT_FEATURES], train_df[label_col])
            test_df = test_df.copy()
            test_df["pred_prob"] = pipe.predict_proba(test_df[num_features + CAT_FEATURES])[:, 1]
            auc = roc_auc_score(test_df[label_col], test_df["pred_prob"]) if test_df[label_col].nunique() > 1 else np.nan
            for mode, param in configs:
                precision, capture, lift, base, selected_n = eval_mode(test_df, "pred_prob", label_col, mode, param)
                window_preds.append({
                    "feature_set": set_name,
                    "stage": stage_name,
                    "signal_date": pd.Timestamp(test_date).date().isoformat(),
                    "mode": mode,
                    "param": param,
                    "auc": auc,
                    "precision": precision,
                    "capture": capture,
                    "lift": lift,
                    "base_rate": base,
                    "selected_n": selected_n,
                })
        if window_preds:
            rows.extend(window_preds)
    by_window = pd.DataFrame(rows)
    if by_window.empty:
        return by_window
    summary = by_window.groupby(["feature_set", "mode", "param"], as_index=False).agg(
        windows=("signal_date", "size"),
        avg_auc=("auc", "mean"),
        avg_precision=("precision", "mean"),
        avg_capture=("capture", "mean"),
        avg_lift=("lift", "mean"),
        avg_base_rate=("base_rate", "mean"),
        avg_selected_n=("selected_n", "mean"),
    )
    summary = summary.sort_values(["avg_lift", "avg_precision", "avg_capture"], ascending=[False, False, False])
    return by_window, summary


def main() -> None:
    trans = pd.read_csv(TRANSITION_PATH, dtype={"ticker": str})
    trans["ticker"] = trans["ticker"].astype(str).str.zfill(6)
    trans["signal_date"] = pd.to_datetime(trans["signal_date"])

    stage1_panel = trans[trans["current_bucket"].isin(LOWER_BUCKETS)].copy()
    stage2_panel = trans[trans["current_bucket"] == "ET10_ex_ET3"].copy()

    s1_window, s1_summary = strict_tuning(stage1_panel, STAGE1_SETS, "label_to_et10", STAGE1_CONFIGS, "stage1_lower_to_et10")
    s2_window, s2_summary = strict_tuning(stage2_panel, STAGE2_SETS, "label_to_et3", STAGE2_CONFIGS, "stage2_et10_to_et3")

    s1_window.to_csv(OUTDIR / 'etf_stage1_pit_tuning_by_window.csv', index=False, encoding='utf-8-sig')
    s1_summary.to_csv(OUTDIR / 'etf_stage1_pit_tuning_summary.csv', index=False, encoding='utf-8-sig')
    s2_window.to_csv(OUTDIR / 'etf_stage2_pit_tuning_by_window.csv', index=False, encoding='utf-8-sig')
    s2_summary.to_csv(OUTDIR / 'etf_stage2_pit_tuning_summary.csv', index=False, encoding='utf-8-sig')

    lines = ['# ETF PIT Tuning Summary', '']
    lines.append('## Stage1')
    for row in s1_summary.head(10).itertuples(index=False):
        lines.append(f"- {row.feature_set} / {row.mode} {row.param}: lift {row.avg_lift:.2f}x, precision {row.avg_precision:.2%}, capture {row.avg_capture:.2%}, auc {row.avg_auc:.4f}")
    lines.append('')
    lines.append('## Stage2')
    for row in s2_summary.head(10).itertuples(index=False):
        lines.append(f"- {row.feature_set} / {row.mode} {row.param}: lift {row.avg_lift:.2f}x, precision {row.avg_precision:.2%}, capture {row.avg_capture:.2%}, auc {row.avg_auc:.4f}")
    (OUTDIR / 'etf_pit_tuning_summary.md').write_text('\n'.join(lines), encoding='utf-8')

    print('STAGE1_TOP')
    print(s1_summary.head(10).to_string(index=False))
    print('STAGE2_TOP')
    print(s2_summary.head(10).to_string(index=False))


if __name__ == '__main__':
    main()
