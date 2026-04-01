from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_LOGISTIC_LABEL_WINDOW_ANALYSIS"
LOWER_BUCKETS = ["OUTSIDE", "T50_ex_T30", "T30_ex_T10"]
STAGE1_TOP_N = 40
STAGE2_TOP_N = 12
TRAIN_SPLIT = 0.7

STAGE1_FEATURES = [
    "revenue_yoy_pct", "op_income_yoy_pct", "dist_ma120_pct", "ma_stack_gap_pct",
    "dist_ma60_pct", "op_delta_3m_pct", "mom20_pct", "vol_ratio_20_pct"
]
STAGE2_FEATURES = [
    "revenue_yoy_pct", "op_income_yoy_pct", "dist_ma120_pct", "ma_stack_gap_pct",
    "dist_ma60_pct", "mom20_pct"
]
LABEL_SPECS = {
    "2to4": [2, 3, 4],
    "2to3": [2, 3],
    "3to4": [3, 4],
}


def read_sql(db: Path, query: str, parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, parse_dates=parse_dates)
    finally:
        con.close()


def pct_rank(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.rank(pct=True)


def build_panel() -> pd.DataFrame:
    panel = read_sql(
        RESEARCH_DB,
        """
        SELECT model_code, horizon, signal_date, next_signal_date, ticker, name, market, bucket,
               next_bucket, entered_t10_next, entered_t3_next, score, fwd_ret, path_mdd
        FROM s3_bucket_transition_panel
        WHERE model_code='S3' AND next_bucket IS NOT NULL
        """,
        parse_dates=["signal_date", "next_signal_date"],
    )
    panel["ticker"] = panel["ticker"].astype(str).str.zfill(6)

    s2 = read_sql(
        FUND_DB,
        "SELECT date, ticker, growth_score, revenue_yoy, op_income_yoy, score_rank FROM s2_fund_scores_monthly",
        parse_dates=["date"],
    )
    s2["ticker"] = s2["ticker"].astype(str).str.zfill(6)
    s3p = read_sql(
        S3_DB,
        "SELECT ticker, date, close, mom20, vol_ratio_20, breakout60, ma60, ma120 FROM s3_price_features_daily",
        parse_dates=["date"],
    )
    s3p["ticker"] = s3p["ticker"].astype(str).str.zfill(6)
    s3f = read_sql(
        S3_DB,
        "SELECT ticker, available_from, fund_accel_score, gs_delta_3m, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly",
        parse_dates=["available_from"],
    )
    s3f["ticker"] = s3f["ticker"].astype(str).str.zfill(6)

    panel = panel.merge(s3p, left_on=["ticker", "signal_date"], right_on=["ticker", "date"], how="left").drop(columns=["date"])
    out = []
    for d0, g in panel.groupby("signal_date"):
        left = g.sort_values("ticker").copy()
        right_s2 = s2[s2["date"] <= d0].sort_values(["ticker", "date"]).groupby("ticker", as_index=False).tail(1)
        left = left.merge(right_s2[["ticker", "growth_score", "revenue_yoy", "op_income_yoy", "score_rank"]], on="ticker", how="left")
        right_s3f = s3f[s3f["available_from"] <= d0].sort_values(["ticker", "available_from"]).groupby("ticker", as_index=False).tail(1)
        left = left.merge(right_s3f[["ticker", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m"]], on="ticker", how="left")
        out.append(left)
    panel = pd.concat(out, ignore_index=True)
    panel["dist_ma60"] = panel["close"] / panel["ma60"] - 1.0
    panel["dist_ma120"] = panel["close"] / panel["ma120"] - 1.0
    panel["ma_stack_gap"] = panel["ma60"] / panel["ma120"] - 1.0
    for feat in [
        "growth_score", "revenue_yoy", "op_income_yoy", "score_rank",
        "mom20", "vol_ratio_20", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m",
        "dist_ma60", "dist_ma120", "ma_stack_gap",
    ]:
        panel[feat] = pd.to_numeric(panel[feat], errors="coerce")
        panel[f"{feat}_pct"] = panel.groupby(["horizon", "signal_date"])[feat].transform(pct_rank)
    panel = panel.sort_values(["horizon", "ticker", "signal_date"]).copy()
    for step in [2,3,4]:
        panel[f"future_bucket_{step}"] = panel.groupby(["horizon", "ticker"])["bucket"].shift(-step)
    panel["enough_future_4"] = panel["future_bucket_4"].notna()
    return panel


def time_split_dates(df: pd.DataFrame):
    dates = sorted(pd.to_datetime(df["signal_date"]).drop_duplicates())
    cut_idx = max(1, int(len(dates) * TRAIN_SPLIT))
    if cut_idx >= len(dates):
        cut_idx = len(dates) - 1
    return dates[:cut_idx], dates[cut_idx:]


def build_model():
    return Pipeline([
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)),
    ])


def eval_topn(pred_df: pd.DataFrame, top_n: int):
    rows = []
    for (horizon, signal_date), g in pred_df.groupby(["horizon", "signal_date"]):
        top = g.sort_values(["pred_prob", "ticker"], ascending=[False, True]).head(min(top_n, len(g))).copy()
        pos_n = int(g["label"].sum())
        hits = int(top["label"].sum())
        base_rate = float(g["label"].mean()) if len(g) else 0.0
        precision = float(top["label"].mean()) if len(top) else 0.0
        rows.append({
            "horizon": horizon,
            "positive_n": pos_n,
            "hits": hits,
            "base_rate": base_rate,
            "precision": precision,
            "capture_rate": float(hits / pos_n) if pos_n else None,
            "lift": float(precision / base_rate) if base_rate else None,
        })
    return pd.DataFrame(rows)


def run_window(panel: pd.DataFrame, steps: list[int], stage_name: str, features: list[str], top_n: int, eligible_buckets: list[str], target_buckets: list[str]):
    work = panel[panel["bucket"].isin(eligible_buckets) & panel["enough_future_4"]].copy()
    work["label"] = work[[f"future_bucket_{s}" for s in steps]].isin(target_buckets).any(axis=1).astype(int)
    train_dates, test_dates = time_split_dates(work)
    train = work[work["signal_date"].isin(train_dates)].copy()
    test = work[work["signal_date"].isin(test_dates)].copy()
    model = build_model()
    model.fit(train[features].fillna(0.5), train["label"])
    prob = model.predict_proba(test[features].fillna(0.5))[:, 1]
    auc = roc_auc_score(test["label"], prob) if test["label"].nunique() > 1 else float('nan')
    pred = test[["horizon", "signal_date", "ticker", "name", "market", "bucket", "label"]].copy()
    pred["pred_prob"] = prob
    eval_df = eval_topn(pred, top_n)
    overall = eval_df.agg({
        "base_rate": "mean",
        "precision": "mean",
        "capture_rate": "mean",
        "lift": "mean",
    }).to_dict()
    overall["auc"] = auc
    overall["stage"] = stage_name
    overall["window"] = f"{steps[0]}to{steps[-1]}"
    overall["rows"] = len(test)
    coef = model.named_steps["clf"].coef_[0]
    feat = pd.DataFrame({"feature": features, "importance": coef}).sort_values("importance", ascending=False).reset_index(drop=True)
    return pd.DataFrame([overall]), eval_df, feat


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    panel = build_panel()
    summaries = []
    feature_tables = []
    eval_tables = []

    for label_name, steps in LABEL_SPECS.items():
        s1_summary, s1_eval, s1_feat = run_window(panel, steps, "stage1", STAGE1_FEATURES, STAGE1_TOP_N, LOWER_BUCKETS, ["T10_ex_T3", "T3"])
        s1_summary["label_spec"] = label_name
        s1_feat["stage"] = "stage1"
        s1_feat["label_spec"] = label_name
        s1_eval["stage"] = "stage1"
        s1_eval["label_spec"] = label_name
        summaries.append(s1_summary)
        feature_tables.append(s1_feat)
        eval_tables.append(s1_eval)

        s2_summary, s2_eval, s2_feat = run_window(panel, steps, "stage2", STAGE2_FEATURES, STAGE2_TOP_N, ["T10_ex_T3"], ["T3"])
        s2_summary["label_spec"] = label_name
        s2_feat["stage"] = "stage2"
        s2_feat["label_spec"] = label_name
        s2_eval["stage"] = "stage2"
        s2_eval["label_spec"] = label_name
        summaries.append(s2_summary)
        feature_tables.append(s2_feat)
        eval_tables.append(s2_eval)

    summary_df = pd.concat(summaries, ignore_index=True)
    feature_df = pd.concat(feature_tables, ignore_index=True)
    eval_df = pd.concat(eval_tables, ignore_index=True)
    summary_df.to_csv(OUTDIR / 'logistic_label_window_summary.csv', index=False, encoding='utf-8-sig')
    feature_df.to_csv(OUTDIR / 'logistic_label_window_feature_importance.csv', index=False, encoding='utf-8-sig')
    eval_df.to_csv(OUTDIR / 'logistic_label_window_eval_by_horizon.csv', index=False, encoding='utf-8-sig')
    print(summary_df.to_string(index=False))


if __name__ == '__main__':
    main()
