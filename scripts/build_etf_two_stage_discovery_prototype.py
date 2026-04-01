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
TRANSITION_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\ETF_T_SERIES_TRANSITION_RESEARCH"
V2_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\ETF_T_SERIES_V2"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\ETF_TWO_STAGE_DISCOVERY_PROTOTYPE"

NUMERIC_FEATURES_STAGE1 = [
    "ret_60d",
    "ret_120d",
    "ma20_ma60_gap",
    "ma60_ma120_gap",
    "vol_60d",
    "dist_ma120",
    "vol_20d",
    "dist_ma60",
]
NUMERIC_FEATURES_STAGE2 = [
    "vol_20d",
    "vol_60d",
    "dist_ma20",
    "dist_ma120",
    "dist_ma60",
    "ret_120d",
    "ma60_ma120_gap",
    "ret_20d",
]
CAT_FEATURES = ["asset_class", "group_key", "currency_exposure"]
LOWER_BUCKETS = ["OUTSIDE", "ET50_ex_ET30", "ET30_ex_ET10"]
TRAIN_SPLIT = 0.7


def _build_pipeline(num_features: list[str]) -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), num_features),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
        ]
    )
    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    return Pipeline([("pre", pre), ("clf", clf)])


def _time_split(dates: list[pd.Timestamp]) -> tuple[list[pd.Timestamp], list[pd.Timestamp]]:
    cut_idx = max(1, int(len(dates) * TRAIN_SPLIT))
    if cut_idx >= len(dates):
        cut_idx = len(dates) - 1
    return dates[:cut_idx], dates[cut_idx:]


def _eval_topn(pred_df: pd.DataFrame, top_ratio: float) -> tuple[float, float, float, float]:
    rows = []
    for d0, g in pred_df.groupby("signal_date"):
        ranked = g.sort_values(["pred_prob", "ticker"], ascending=[False, True]).copy()
        top_n = max(1, int(math.ceil(len(ranked) * top_ratio)))
        top = ranked.head(min(top_n, len(ranked))).copy()
        pos_n = int(g["label"].sum())
        hits = int(top["label"].sum())
        base = float(g["label"].mean()) if len(g) else 0.0
        precision = float(top["label"].mean()) if len(top) else 0.0
        capture = float(hits / pos_n) if pos_n else np.nan
        lift = float(precision / base) if base else np.nan
        rows.append((precision, capture, lift, base))
    arr = np.array(rows, dtype=float) if rows else np.empty((0, 4))
    if arr.size == 0:
        return (np.nan, np.nan, np.nan, np.nan)
    return tuple(np.nanmean(arr[:, i]) for i in range(4))


def _fit_stage(panel: pd.DataFrame, num_features: list[str], label_col: str, top_ratio: float, stage_name: str) -> tuple[pd.DataFrame, Pipeline]:
    work = panel.dropna(subset=num_features).copy()
    dates = sorted(pd.to_datetime(work["signal_date"]).drop_duplicates().tolist())
    train_dates, test_dates = _time_split(dates)
    train_df = work[work["signal_date"].isin(train_dates)].copy()
    test_df = work[work["signal_date"].isin(test_dates)].copy()
    pipe = _build_pipeline(num_features)
    pipe.fit(train_df[num_features + CAT_FEATURES], train_df[label_col])
    prob = pipe.predict_proba(test_df[num_features + CAT_FEATURES])[:, 1]
    auc = roc_auc_score(test_df[label_col], prob) if test_df[label_col].nunique() > 1 else np.nan
    pred_df = test_df[["signal_date", "ticker", "name", label_col]].copy().rename(columns={label_col: "label"})
    pred_df["pred_prob"] = prob
    precision, capture, lift, base = _eval_topn(pred_df, top_ratio)
    summary = pd.DataFrame([
        {
            "stage": stage_name,
            "test_auc": auc,
            "avg_precision": precision,
            "avg_capture": capture,
            "avg_lift": lift,
            "avg_base_rate": base,
            "top_ratio": top_ratio,
            "train_windows": len(train_dates),
            "test_windows": len(test_dates),
        }
    ])
    full_pipe = _build_pipeline(num_features)
    full_pipe.fit(work[num_features + CAT_FEATURES], work[label_col])
    return summary, full_pipe


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    trans = pd.read_csv(TRANSITION_DIR / 'etf_tseries_transition_panel.csv', dtype={"ticker": str})
    trans["ticker"] = trans["ticker"].astype(str).str.zfill(6)
    trans["signal_date"] = pd.to_datetime(trans["signal_date"])

    latest = pd.read_csv(V2_DIR / 'etf_tseries_feature_panel.csv', dtype={"ticker": str})
    latest["ticker"] = latest["ticker"].astype(str).str.zfill(6)
    latest["signal_date"] = pd.to_datetime(latest["signal_date"])
    latest = latest[latest["signal_date"] == latest["signal_date"].max()].copy()

    stage1_panel = trans[trans["current_bucket"].isin(LOWER_BUCKETS)].copy()
    stage2_panel = trans[trans["current_bucket"] == "ET10_ex_ET3"].copy()

    stage1_summary, stage1_model = _fit_stage(stage1_panel, NUMERIC_FEATURES_STAGE1, "label_to_et10", 0.10, "stage1_lower_to_et10")
    stage2_summary, stage2_model = _fit_stage(stage2_panel, NUMERIC_FEATURES_STAGE2, "label_to_et3", 0.03, "stage2_et10_to_et3")
    summary = pd.concat([stage1_summary, stage2_summary], ignore_index=True)

    latest_stage1 = latest.dropna(subset=NUMERIC_FEATURES_STAGE1).copy()
    latest_stage1["stage1_prob"] = stage1_model.predict_proba(latest_stage1[NUMERIC_FEATURES_STAGE1 + CAT_FEATURES])[:, 1]
    latest_stage1 = latest_stage1.sort_values(["stage1_prob", "ticker"], ascending=[False, True]).reset_index(drop=True)
    stage1_cut = max(1, int(math.ceil(len(latest_stage1) * 0.10)))
    stage1_candidates = latest_stage1.head(stage1_cut).copy()

    stage2_input = stage1_candidates.dropna(subset=NUMERIC_FEATURES_STAGE2).copy()
    stage2_input["stage2_prob"] = stage2_model.predict_proba(stage2_input[NUMERIC_FEATURES_STAGE2 + CAT_FEATURES])[:, 1]
    stage2_input = stage2_input.sort_values(["stage2_prob", "stage1_prob", "ticker"], ascending=[False, False, True]).reset_index(drop=True)
    stage2_cut = max(1, int(math.ceil(len(latest_stage1) * 0.03)))
    stage2_candidates = stage2_input.head(min(stage2_cut, len(stage2_input))).copy()

    watch = stage2_input[[
        "signal_date","ticker","name","asset_class","group_key","currency_exposure",
        "stage1_prob","stage2_prob","ret_20d","ret_60d","ret_120d","dist_ma20","dist_ma60","dist_ma120"
    ]].copy()

    summary.to_csv(OUTDIR / 'etf_two_stage_model_summary.csv', index=False, encoding='utf-8-sig')
    latest_stage1.to_csv(OUTDIR / 'etf_two_stage_full_rank_2026-03-31.csv', index=False, encoding='utf-8-sig')
    stage1_candidates.to_csv(OUTDIR / 'etf_stage1_et10_candidates_2026-03-31.csv', index=False, encoding='utf-8-sig')
    stage2_candidates.to_csv(OUTDIR / 'etf_stage2_et3_candidates_2026-03-31.csv', index=False, encoding='utf-8-sig')
    watch.to_csv(OUTDIR / 'etf_stage2_watchlist_2026-03-31.csv', index=False, encoding='utf-8-sig')

    lines = []
    lines.append('# ETF Two-Stage Discovery Prototype')
    lines.append('')
    for row in summary.itertuples(index=False):
        lines.append(
            f"- {row.stage}: AUC {row.test_auc:.4f}, precision {row.avg_precision:.2%}, capture {row.avg_capture:.2%}, lift {row.avg_lift:.2f}x, base {row.avg_base_rate:.2%}"
        )
    lines.append('')
    lines.append(f"- latest stage1 candidates: {len(stage1_candidates)}")
    lines.append(f"- latest stage2 candidates: {len(stage2_candidates)}")
    (OUTDIR / 'etf_two_stage_discovery_prototype_2026-03-31.md').write_text('\n'.join(lines), encoding='utf-8')

    print(summary.to_string(index=False))
    print(f"latest_stage1_candidates={len(stage1_candidates)}")
    print(f"latest_stage2_candidates={len(stage2_candidates)}")
    print('stage2_top=' + ','.join(stage2_candidates['name'].tolist()))


if __name__ == '__main__':
    main()
