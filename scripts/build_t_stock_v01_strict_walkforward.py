from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import sqlite3
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_STRICT_WALKFORWARD"
OUTDIR.mkdir(parents=True, exist_ok=True)
LOWER_BUCKETS = ["OUTSIDE", "T50_ex_T30", "T30_ex_T10"]
FUTURE_STEPS = [2,3,4]
MIN_TRAIN_WINDOWS = 26
STAGE1_FEATURES = [
    "revenue_yoy_pct", "op_income_yoy_pct", "dist_ma120_pct", "ma_stack_gap_pct",
    "dist_ma60_pct", "op_delta_3m_pct", "mom20_pct", "vol_ratio_20_pct"
]
STAGE2_FEATURES = [
    "revenue_yoy_pct", "op_income_yoy_pct", "dist_ma120_pct", "ma_stack_gap_pct",
    "dist_ma60_pct", "mom20_pct"
]


def read_sql(db: Path, q: str, parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(q, con, parse_dates=parse_dates)
    finally:
        con.close()


def pct_rank(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.rank(pct=True)


def build_base_panel() -> pd.DataFrame:
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
    return panel


def attach_features(panel: pd.DataFrame) -> pd.DataFrame:
    s2 = read_sql(
        FUND_DB,
        "SELECT date, ticker, growth_score, revenue_yoy, op_income_yoy, score_rank FROM s2_fund_scores_monthly",
        parse_dates=["date"],
    )
    s2["ticker"] = s2["ticker"].astype(str).str.zfill(6)
    s3p = read_sql(
        S3_DB,
        "SELECT ticker, date, close, mom20, vol_ratio_20, breakout60, ma60, ma120, ma60_slope, ma120_slope FROM s3_price_features_daily",
        parse_dates=["date"],
    )
    s3p["ticker"] = s3p["ticker"].astype(str).str.zfill(6)
    s3f = read_sql(
        S3_DB,
        "SELECT ticker, available_from, fund_accel_score, gs_delta_3m, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly",
        parse_dates=["available_from"],
    )
    s3f["ticker"] = s3f["ticker"].astype(str).str.zfill(6)

    panel = panel.merge(
        s3p,
        left_on=["ticker", "signal_date"],
        right_on=["ticker", "date"],
        how="left",
    ).drop(columns=["date"])

    out = []
    for d0, g in panel.groupby("signal_date"):
        left = g.sort_values("ticker").copy()
        right_s2 = (
            s2[s2["date"] <= d0]
            .sort_values(["ticker", "date"])
            .groupby("ticker", as_index=False)
            .tail(1)
        )
        left = left.merge(
            right_s2[["ticker", "growth_score", "revenue_yoy", "op_income_yoy", "score_rank"]],
            on="ticker",
            how="left",
        )
        right_s3f = (
            s3f[s3f["available_from"] <= d0]
            .sort_values(["ticker", "available_from"])
            .groupby("ticker", as_index=False)
            .tail(1)
        )
        left = left.merge(
            right_s3f[["ticker", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m"]],
            on="ticker",
            how="left",
        )
        out.append(left)
    panel = pd.concat(out, ignore_index=True)

    panel["dist_ma60"] = panel["close"] / panel["ma60"] - 1.0
    panel["dist_ma120"] = panel["close"] / panel["ma120"] - 1.0
    panel["ma_stack_gap"] = panel["ma60"] / panel["ma120"] - 1.0

    raw_features = [
        "growth_score", "revenue_yoy", "op_income_yoy", "score_rank",
        "mom20", "vol_ratio_20", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m",
        "dist_ma60", "dist_ma120", "ma_stack_gap",
    ]
    for feat in raw_features:
        panel[feat] = pd.to_numeric(panel[feat], errors="coerce")
        panel[f"{feat}_pct"] = panel.groupby(["horizon", "signal_date"])[feat].transform(pct_rank)
    return panel


def add_future_labels(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values(["horizon", "ticker", "signal_date"]).copy()
    for step in FUTURE_STEPS:
        panel[f"future_bucket_{step}"] = panel.groupby(["horizon", "ticker"])["bucket"].shift(-step)
    panel["label_t10_2to4"] = panel[[f"future_bucket_{s}" for s in FUTURE_STEPS]].isin(["T10_ex_T3", "T3"]).any(axis=1).astype(float)
    panel["label_t3_2to4"] = panel[[f"future_bucket_{s}" for s in FUTURE_STEPS]].eq("T3").any(axis=1).astype(float)
    panel["enough_future_steps"] = panel[f"future_bucket_{max(FUTURE_STEPS)}"].notna()
    return panel


def build_logistic() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)),
    ])


def strict_walkforward(panel: pd.DataFrame, features: list[str], label_col: str, stage_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = panel.dropna(subset=features).copy()
    work = work[work["enough_future_steps"]].copy()
    dates = sorted(pd.to_datetime(work["signal_date"]).drop_duplicates().tolist())
    windows = []
    preds = []
    for i in range(MIN_TRAIN_WINDOWS, len(dates)):
        test_date = dates[i]
        train_dates = dates[:i]
        train_df = work[work["signal_date"].isin(train_dates)].copy()
        test_df = work[work["signal_date"] == test_date].copy()
        if train_df.empty or test_df.empty or train_df[label_col].nunique() < 2:
            continue
        pipe = build_logistic()
        pipe.fit(train_df[features].fillna(0.5), train_df[label_col].astype(int))
        test_df = test_df.copy()
        test_df["pred_prob"] = pipe.predict_proba(test_df[features].fillna(0.5))[:,1]
        test_df["label"] = test_df[label_col].astype(int)
        test_df["stage"] = stage_name
        preds.append(test_df[["horizon","signal_date","ticker","name","market","bucket","pred_prob","label","stage"]])
        windows.append({
            "stage": stage_name,
            "signal_date": pd.Timestamp(test_date).date().isoformat(),
            "train_windows": i,
            "test_count": int(len(test_df)),
            "positives": int(test_df["label"].sum()),
            "base_rate": float(test_df["label"].mean()) if len(test_df) else np.nan,
        })
    return pd.DataFrame(windows), (pd.concat(preds, ignore_index=True) if preds else pd.DataFrame())


def main() -> None:
    panel = add_future_labels(attach_features(build_base_panel()))
    stage1_panel = panel[panel["bucket"].isin(LOWER_BUCKETS)].copy()
    stage2_panel = panel[panel["bucket"] == "T10_ex_T3"].copy()
    s1w, s1p = strict_walkforward(stage1_panel, STAGE1_FEATURES, "label_t10_2to4", "stage1")
    s2w, s2p = strict_walkforward(stage2_panel, STAGE2_FEATURES, "label_t3_2to4", "stage2")
    s1w.to_csv(OUTDIR / 'stage1_strict_by_window.csv', index=False, encoding='utf-8-sig')
    s2w.to_csv(OUTDIR / 'stage2_strict_by_window.csv', index=False, encoding='utf-8-sig')
    s1p.to_csv(OUTDIR / 'stage1_strict_predictions.csv', index=False, encoding='utf-8-sig')
    s2p.to_csv(OUTDIR / 'stage2_strict_predictions.csv', index=False, encoding='utf-8-sig')
    overall = pd.DataFrame([
        {"stage":"stage1","windows":len(s1w),"min_signal_date":s1p['signal_date'].min() if not s1p.empty else None,"max_signal_date":s1p['signal_date'].max() if not s1p.empty else None,"rows":len(s1p)},
        {"stage":"stage2","windows":len(s2w),"min_signal_date":s2p['signal_date'].min() if not s2p.empty else None,"max_signal_date":s2p['signal_date'].max() if not s2p.empty else None,"rows":len(s2p)},
    ])
    overall.to_csv(OUTDIR / 'strict_walkforward_overall.csv', index=False, encoding='utf-8-sig')
    print(overall.to_string(index=False))

if __name__ == '__main__':
    main()
