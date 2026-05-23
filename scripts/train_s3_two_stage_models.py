from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

from tseries_refresh_utils import ensure_run_dir, normalize_asof_date, normalize_run_date

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
OUTDIR = Path()
LOWER_BUCKETS = ["OUTSIDE", "T50_ex_T30", "T30_ex_T10"]
STAGE1_TOP_N = 40
STAGE2_TOP_N = 12
FUTURE_STEPS = [2, 3, 4]
TRAIN_SPLIT = 0.7

STAGE1_FEATURES = [
    "revenue_yoy_pct", "op_income_yoy_pct", "dist_ma120_pct", "ma_stack_gap_pct",
    "dist_ma60_pct", "op_delta_3m_pct", "mom20_pct", "vol_ratio_20_pct"
]
STAGE2_FEATURES = [
    "revenue_yoy_pct", "op_income_yoy_pct", "dist_ma120_pct", "ma_stack_gap_pct",
    "dist_ma60_pct", "mom20_pct"
]


def latest_stock_asof() -> pd.Timestamp:
    pattern = re.compile(r"s3_holdings_last_top20_(\d{4}-\d{2}-\d{2})\.csv$")
    candidates: list[tuple[str, Path]] = []
    for p in (PROJECT_ROOT / r"reports\backtest_s3_dev").glob("s3_holdings_last_top20_*.csv"):
        m = pattern.match(p.name)
        if m:
            candidates.append((m.group(1), p))
    if not candidates:
        raise FileNotFoundError("No stock S3 current holdings files found")
    _, latest_path = max(candidates, key=lambda item: item[0])
    sample = pd.read_csv(latest_path, usecols=["date"], nrows=1)
    return pd.Timestamp(sample.iloc[0]["date"])


ASOF_DATE: pd.Timestamp | None = None


def read_sql(db: Path, query: str, parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, parse_dates=parse_dates)
    finally:
        con.close()


def pct_rank(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.rank(pct=True)


def latest_snapshot(df: pd.DataFrame, date_col: str, asof: pd.Timestamp) -> pd.DataFrame:
    w = df[df[date_col] <= asof].copy()
    if w.empty:
        return w
    return w.sort_values(["ticker", date_col]).groupby("ticker", as_index=False).tail(1)


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


def time_split_dates(df: pd.DataFrame) -> tuple[pd.Timestamp, list[pd.Timestamp], list[pd.Timestamp]]:
    dates = sorted(pd.to_datetime(df["signal_date"]).drop_duplicates())
    cut_idx = max(1, int(len(dates) * TRAIN_SPLIT))
    if cut_idx >= len(dates):
        cut_idx = len(dates) - 1
    return dates[cut_idx - 1], dates[:cut_idx], dates[cut_idx:]


def build_logistic() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)),
    ])


def build_gb() -> GradientBoostingClassifier:
    return GradientBoostingClassifier(
        n_estimators=250,
        learning_rate=0.05,
        max_depth=3,
        min_samples_leaf=20,
        subsample=0.8,
        random_state=42,
    )


def fit_predict(train_df: pd.DataFrame, test_df: pd.DataFrame, features: list[str], model_name: str):
    X_train = train_df[features].fillna(0.5)
    y_train = train_df["label"].astype(int)
    X_test = test_df[features].fillna(0.5)
    y_test = test_df["label"].astype(int)

    if model_name == "gradient_boosting":
        model = build_gb()
        sw = compute_sample_weight(class_weight="balanced", y=y_train)
        model.fit(X_train, y_train, sample_weight=sw)
        prob = model.predict_proba(X_test)[:, 1]
        feat_imp = pd.DataFrame({"feature": features, "importance": model.feature_importances_})
    else:
        model = build_logistic()
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_test)[:, 1]
        coef = model.named_steps["clf"].coef_[0]
        feat_imp = pd.DataFrame({"feature": features, "importance": coef})

    auc = roc_auc_score(y_test, prob) if y_test.nunique() > 1 else np.nan
    pred_df = test_df[["horizon", "signal_date", "ticker", "name", "market", "bucket", "label"]].copy()
    pred_df["pred_prob"] = prob
    return model, pred_df, feat_imp.sort_values("importance", ascending=False).reset_index(drop=True), auc


def eval_topn(pred_df: pd.DataFrame, stage_name: str, top_n: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    selected_rows = []
    for (horizon, signal_date), g in pred_df.groupby(["horizon", "signal_date"]):
        ranked = g.sort_values(["pred_prob", "ticker"], ascending=[False, True]).copy()
        top = ranked.head(min(top_n, len(ranked))).copy()
        top["selected_rank"] = range(1, len(top) + 1)
        selected_rows.append(top)
        pos_n = int(g["label"].sum())
        hits = int(top["label"].sum())
        base_rate = float(g["label"].mean()) if len(g) else 0.0
        precision = float(top["label"].mean()) if len(top) else 0.0
        rows.append({
            "horizon": horizon,
            "signal_date": signal_date,
            "stage": stage_name,
            "candidate_pool_n": int(len(g)),
            "selected_n": int(len(top)),
            "positive_n": pos_n,
            "hits": hits,
            "base_rate": base_rate,
            "precision": precision,
            "capture_rate": float(hits / pos_n) if pos_n else None,
            "lift": float(precision / base_rate) if base_rate else None,
        })
    res = pd.DataFrame(rows)
    overall = res.groupby("stage").agg(
        windows=("stage", "size"),
        avg_candidate_pool_n=("candidate_pool_n", "mean"),
        avg_selected_n=("selected_n", "mean"),
        total_positive_n=("positive_n", "sum"),
        total_hits=("hits", "sum"),
        avg_base_rate=("base_rate", "mean"),
        avg_precision=("precision", "mean"),
        avg_capture_rate=("capture_rate", "mean"),
        avg_lift=("lift", "mean"),
    ).reset_index()
    by_h = res.groupby(["horizon", "stage"]).agg(
        windows=("stage", "size"),
        avg_candidate_pool_n=("candidate_pool_n", "mean"),
        avg_selected_n=("selected_n", "mean"),
        total_positive_n=("positive_n", "sum"),
        total_hits=("hits", "sum"),
        avg_base_rate=("base_rate", "mean"),
        avg_precision=("precision", "mean"),
        avg_capture_rate=("capture_rate", "mean"),
        avg_lift=("lift", "mean"),
    ).reset_index()
    selected = pd.concat(selected_rows, ignore_index=True) if selected_rows else pd.DataFrame()
    return overall, by_h, selected


def build_latest_snapshot() -> pd.DataFrame:
    if ASOF_DATE is None:
        raise RuntimeError("ASOF_DATE is not initialized")

    universe = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})[["ticker", "name", "market", "mcap"]]
    universe["ticker"] = universe["ticker"].astype(str).str.zfill(6)

    p = read_sql(S3_DB, "SELECT ticker, date, close, mom20, vol_ratio_20, breakout60, ma60, ma120 FROM s3_price_features_daily", parse_dates=["date"])
    p["ticker"] = p["ticker"].astype(str).str.zfill(6)
    p_row = p[p["date"] == pd.to_datetime(p.loc[p["date"] <= ASOF_DATE, "date"].max())].copy()

    s2 = read_sql(FUND_DB, "SELECT date, ticker, growth_score, revenue_yoy, op_income_yoy, score_rank FROM s2_fund_scores_monthly", parse_dates=["date"])
    s2["ticker"] = s2["ticker"].astype(str).str.zfill(6)
    s2_row = latest_snapshot(s2, "date", ASOF_DATE)

    s3f = read_sql(S3_DB, "SELECT ticker, available_from, fund_accel_score, gs_delta_3m, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly", parse_dates=["available_from"])
    s3f["ticker"] = s3f["ticker"].astype(str).str.zfill(6)
    s3f_row = latest_snapshot(s3f, "available_from", ASOF_DATE)

    snap = universe.merge(p_row, on="ticker", how="left").merge(
        s2_row[["ticker", "growth_score", "revenue_yoy", "op_income_yoy", "score_rank"]], on="ticker", how="left"
    ).merge(
        s3f_row[["ticker", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m"]], on="ticker", how="left"
    )
    snap["dist_ma60"] = snap["close"] / snap["ma60"] - 1.0
    snap["dist_ma120"] = snap["close"] / snap["ma120"] - 1.0
    snap["ma_stack_gap"] = snap["ma60"] / snap["ma120"] - 1.0
    for feat in [
        "growth_score", "revenue_yoy", "op_income_yoy", "score_rank",
        "mom20", "vol_ratio_20", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m",
        "dist_ma60", "dist_ma120", "ma_stack_gap",
    ]:
        snap[feat] = pd.to_numeric(snap[feat], errors="coerce")
        snap[f"{feat}_pct"] = pct_rank(snap[feat])
    snap["asof_date"] = ASOF_DATE
    return snap


def save_tables(model_name, feat_stage1, feat_stage2, stage1_overall, stage1_by_h, stage2_overall, stage2_by_h, latest_stage1, latest_stage2):
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        feat_stage1.to_sql(f"s3_two_stage_{model_name}_stage1_features", con, if_exists="replace", index=False)
        feat_stage2.to_sql(f"s3_two_stage_{model_name}_stage2_features", con, if_exists="replace", index=False)
        stage1_overall.to_sql(f"s3_two_stage_{model_name}_stage1_overall", con, if_exists="replace", index=False)
        stage1_by_h.to_sql(f"s3_two_stage_{model_name}_stage1_by_horizon", con, if_exists="replace", index=False)
        stage2_overall.to_sql(f"s3_two_stage_{model_name}_stage2_overall", con, if_exists="replace", index=False)
        stage2_by_h.to_sql(f"s3_two_stage_{model_name}_stage2_by_horizon", con, if_exists="replace", index=False)
        latest_stage1.to_sql(f"s3_two_stage_{model_name}_latest_stage1", con, if_exists="replace", index=False)
        latest_stage2.to_sql(f"s3_two_stage_{model_name}_latest_stage2", con, if_exists="replace", index=False)
    finally:
        con.close()


def render_md(summary_rows: list[dict]) -> str:
    lines = ["# S3 Two-Stage Discovery Models", ""]
    lines.append("- labels: `2~4 steps within` transition targets")
    lines.append("- stage1 target: lower buckets -> `T10_ex_T3 or T3`")
    lines.append("- stage2 target: `T10_ex_T3 -> T3`")
    lines.append("")
    lines.append("| Model | Stage | Test AUC | Avg precision | Avg capture | Avg lift |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in summary_rows:
        lines.append(f"| {r['model']} | {r['stage']} | {r['auc']:.4f} | {r['avg_precision']:.2%} | {r['avg_capture']:.2%} | {r['avg_lift']:.2f}x |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Train S3 two-stage discovery models and latest rank snapshots.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD output folder.")
    ap.add_argument("--asof", default=None, help="Accepted for interface consistency; latest official S3 current holdings date is used.")
    args = ap.parse_args()

    global OUTDIR, ASOF_DATE
    ASOF_DATE = pd.Timestamp(normalize_asof_date(args.asof)) if args.asof else latest_stock_asof()
    OUTDIR = ensure_run_dir(normalize_run_date(args.run_date)) / "S3_TWO_STAGE_MODELING"
    OUTDIR.mkdir(parents=True, exist_ok=True)
    panel = add_future_labels(attach_features(build_base_panel()))

    stage1_df = panel[(panel["bucket"].isin(LOWER_BUCKETS)) & (panel["enough_future_steps"])].copy()
    stage1_df["label"] = stage1_df["label_t10_2to4"].astype(int)
    stage2_df = panel[(panel["bucket"] == "T10_ex_T3") & (panel["enough_future_steps"])].copy()
    stage2_df["label"] = stage2_df["label_t3_2to4"].astype(int)

    cut1, train_dates1, test_dates1 = time_split_dates(stage1_df)
    cut2, train_dates2, test_dates2 = time_split_dates(stage2_df)
    latest = build_latest_snapshot()
    summary_rows = []

    for model_name in ["gradient_boosting", "logistic_regression"]:
        m1, pred1, feat1, auc1 = fit_predict(
            stage1_df[stage1_df["signal_date"].isin(train_dates1)].copy(),
            stage1_df[stage1_df["signal_date"].isin(test_dates1)].copy(),
            STAGE1_FEATURES,
            model_name,
        )
        s1_overall, s1_by_h, s1_selected = eval_topn(pred1, "stage1_to_t10_2to4", STAGE1_TOP_N)
        summary_rows.append({
            "model": model_name,
            "stage": "stage1",
            "auc": float(auc1),
            "avg_precision": float(s1_overall["avg_precision"].iloc[0]),
            "avg_capture": float(s1_overall["avg_capture_rate"].iloc[0]),
            "avg_lift": float(s1_overall["avg_lift"].iloc[0]),
        })

        m2, pred2, feat2, auc2 = fit_predict(
            stage2_df[stage2_df["signal_date"].isin(train_dates2)].copy(),
            stage2_df[stage2_df["signal_date"].isin(test_dates2)].copy(),
            STAGE2_FEATURES,
            model_name,
        )
        s2_overall, s2_by_h, s2_selected = eval_topn(pred2, "stage2_to_t3_2to4", STAGE2_TOP_N)
        summary_rows.append({
            "model": model_name,
            "stage": "stage2",
            "auc": float(auc2),
            "avg_precision": float(s2_overall["avg_precision"].iloc[0]),
            "avg_capture": float(s2_overall["avg_capture_rate"].iloc[0]),
            "avg_lift": float(s2_overall["avg_lift"].iloc[0]),
        })

        latest_stage1 = latest[["asof_date", "ticker", "name", "market", "mcap"] + STAGE1_FEATURES].copy()
        latest_stage1["pred_prob"] = m1.predict_proba(latest[STAGE1_FEATURES].fillna(0.5))[:, 1]
        latest_stage1 = latest_stage1.sort_values(["pred_prob", "ticker"], ascending=[False, True]).reset_index(drop=True)
        latest_stage1["rank"] = latest_stage1.index + 1

        latest_stage2 = latest_stage1.head(STAGE1_TOP_N).copy()
        latest_stage2["pred_prob"] = m2.predict_proba(latest_stage2[STAGE2_FEATURES].fillna(0.5))[:, 1]
        latest_stage2 = latest_stage2.sort_values(["pred_prob", "ticker"], ascending=[False, True]).reset_index(drop=True)
        latest_stage2["rank"] = latest_stage2.index + 1

        save_tables(model_name, feat1, feat2, s1_overall, s1_by_h, s2_overall, s2_by_h, latest_stage1, latest_stage2)

        model_dir = OUTDIR / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        feat1.to_csv(model_dir / "stage1_feature_importance.csv", index=False, encoding="utf-8-sig")
        feat2.to_csv(model_dir / "stage2_feature_importance.csv", index=False, encoding="utf-8-sig")
        pred1.to_csv(model_dir / "stage1_test_predictions.csv", index=False, encoding="utf-8-sig")
        pred2.to_csv(model_dir / "stage2_test_predictions.csv", index=False, encoding="utf-8-sig")
        s1_overall.to_csv(model_dir / "stage1_overall.csv", index=False, encoding="utf-8-sig")
        s1_by_h.to_csv(model_dir / "stage1_by_horizon.csv", index=False, encoding="utf-8-sig")
        s2_overall.to_csv(model_dir / "stage2_overall.csv", index=False, encoding="utf-8-sig")
        s2_by_h.to_csv(model_dir / "stage2_by_horizon.csv", index=False, encoding="utf-8-sig")
        latest_stage1.to_csv(model_dir / "latest_stage1_rank.csv", index=False, encoding="utf-8-sig")
        latest_stage2.to_csv(model_dir / "latest_stage2_rank.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame(summary_rows).to_csv(OUTDIR / "two_stage_model_summary.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "two_stage_model_summary.md").write_text(render_md(summary_rows), encoding="utf-8")
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == '__main__':
    main()

