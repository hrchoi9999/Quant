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
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_STRICT_WALKFORWARD"
OUTDIR.mkdir(parents=True, exist_ok=True)

NUMERIC_FEATURES_STAGE1 = [
    "ret_60d","ret_120d","ma20_ma60_gap","ma60_ma120_gap",
    "vol_60d","dist_ma120","vol_20d","dist_ma60",
]
NUMERIC_FEATURES_STAGE2 = [
    "vol_20d","vol_60d","dist_ma20","dist_ma120",
    "dist_ma60","ret_120d","ma60_ma120_gap","ret_20d",
]
CAT_FEATURES = ["asset_class", "group_key", "currency_exposure"]
LOWER_BUCKETS = ["OUTSIDE", "ET50_ex_ET30", "ET30_ex_ET10"]
MIN_TRAIN_WINDOWS = 24


def build_pipeline(num_features: list[str]) -> Pipeline:
    pre = ColumnTransformer([
        ("num", StandardScaler(), num_features),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
    ])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    return Pipeline([("pre", pre), ("clf", clf)])


def eval_topn(df: pd.DataFrame, prob_col: str, label_col: str, top_ratio: float) -> tuple[float, float, float, float, int, int]:
    ranked = df.sort_values([prob_col, "ticker"], ascending=[False, True]).copy()
    top_n = max(1, int(math.ceil(len(ranked) * top_ratio)))
    top = ranked.head(min(top_n, len(ranked))).copy()
    positives = int(df[label_col].sum())
    hits = int(top[label_col].sum())
    precision = float(top[label_col].mean()) if len(top) else np.nan
    capture = float(hits / positives) if positives else np.nan
    base = float(df[label_col].mean()) if len(df) else np.nan
    lift = float(precision / base) if base and np.isfinite(base) and base > 0 else np.nan
    return precision, capture, lift, base, len(top), positives


def strict_walkforward(panel: pd.DataFrame, num_features: list[str], label_col: str, top_ratio: float, stage_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = panel.dropna(subset=num_features).copy()
    work["signal_date"] = pd.to_datetime(work["signal_date"])
    dates = sorted(work["signal_date"].drop_duplicates().tolist())
    window_rows = []
    pred_rows = []
    for i in range(MIN_TRAIN_WINDOWS, len(dates)):
        test_date = dates[i]
        train_dates = dates[:i]
        train_df = work[work["signal_date"].isin(train_dates)].copy()
        test_df = work[work["signal_date"] == test_date].copy()
        if train_df.empty or test_df.empty or train_df[label_col].nunique() < 2 or test_df[label_col].nunique() < 2:
            continue
        pipe = build_pipeline(num_features)
        pipe.fit(train_df[num_features + CAT_FEATURES], train_df[label_col])
        test_df = test_df.copy()
        test_df["pred_prob"] = pipe.predict_proba(test_df[num_features + CAT_FEATURES])[:, 1]
        auc = roc_auc_score(test_df[label_col], test_df["pred_prob"]) if test_df[label_col].nunique() > 1 else np.nan
        precision, capture, lift, base, selected_n, positives = eval_topn(test_df, "pred_prob", label_col, top_ratio)
        window_rows.append({
            "stage": stage_name,
            "signal_date": pd.Timestamp(test_date).date().isoformat(),
            "train_windows": i,
            "test_count": int(len(test_df)),
            "selected_n": int(selected_n),
            "positives": int(positives),
            "auc": float(auc) if np.isfinite(auc) else np.nan,
            "precision": precision,
            "capture": capture,
            "lift": lift,
            "base_rate": base,
        })
        top_n = max(1, int(math.ceil(len(test_df) * top_ratio)))
        top = test_df.sort_values(["pred_prob", "ticker"], ascending=[False, True]).head(top_n).copy()
        top["stage"] = stage_name
        top["label"] = top[label_col]
        pred_rows.append(top[["stage","signal_date","ticker","name","pred_prob","label"]])
    summary = pd.DataFrame(window_rows)
    preds = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame(columns=["stage","signal_date","ticker","name","pred_prob","label"])
    return summary, preds


def main() -> None:
    trans = pd.read_csv(TRANSITION_PATH, dtype={"ticker": str})
    trans["ticker"] = trans["ticker"].astype(str).str.zfill(6)
    trans["signal_date"] = pd.to_datetime(trans["signal_date"])

    stage1_panel = trans[trans["current_bucket"].isin(LOWER_BUCKETS)].copy()
    stage2_panel = trans[trans["current_bucket"] == "ET10_ex_ET3"].copy()

    stage1_window, stage1_preds = strict_walkforward(stage1_panel, NUMERIC_FEATURES_STAGE1, "label_to_et10", 0.10, "stage1_lower_to_et10")
    stage2_window, stage2_preds = strict_walkforward(stage2_panel, NUMERIC_FEATURES_STAGE2, "label_to_et3", 0.03, "stage2_et10_to_et3")

    all_window = pd.concat([stage1_window, stage2_window], ignore_index=True)
    all_preds = pd.concat([stage1_preds, stage2_preds], ignore_index=True)

    overall = all_window.groupby("stage").agg(
        windows=("signal_date", "size"),
        avg_auc=("auc", "mean"),
        avg_precision=("precision", "mean"),
        avg_capture=("capture", "mean"),
        avg_lift=("lift", "mean"),
        avg_base_rate=("base_rate", "mean"),
        avg_selected_n=("selected_n", "mean"),
        avg_test_count=("test_count", "mean"),
    ).reset_index()

    overall.to_csv(OUTDIR / 'etf_tseries_pit_strict_walkforward_overall.csv', index=False, encoding='utf-8-sig')
    all_window.to_csv(OUTDIR / 'etf_tseries_pit_strict_walkforward_by_window.csv', index=False, encoding='utf-8-sig')
    all_preds.to_csv(OUTDIR / 'etf_tseries_pit_strict_walkforward_top_picks.csv', index=False, encoding='utf-8-sig')

    lines = []
    lines.append('# ETF T-series PIT Strict Walk-Forward Validation')
    lines.append('')
    lines.append(f'- minimum training windows: {MIN_TRAIN_WINDOWS}')
    lines.append('- method: expanding train / one-month forward test / no future leakage / PIT universe')
    lines.append('')
    for row in overall.itertuples(index=False):
        lines.append(
            f"- {row.stage}: windows {int(row.windows)}, AUC {row.avg_auc:.4f}, precision {row.avg_precision:.2%}, capture {row.avg_capture:.2%}, lift {row.avg_lift:.2f}x, base {row.avg_base_rate:.2%}"
        )
    (OUTDIR / 'etf_tseries_pit_strict_walkforward.md').write_text('\n'.join(lines), encoding='utf-8')

    print(overall.to_string(index=False))


if __name__ == '__main__':
    main()
