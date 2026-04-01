from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
MODEL_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_MODELING\logistic_regression"
STRICT_WF_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_STRICT_WALKFORWARD"
THRESHOLD_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_THRESHOLD_CANDIDATES"
S3_HISTORY = PROJECT_ROOT / r"reports\backtest_s3_dev\s3_holdings_history_top20_2013-10-14_2026-03-25.csv"
S3_CURRENT = PROJECT_ROOT / r"reports\backtest_s3_dev\s3_holdings_last_top20_2026-03-25.csv"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_OPERATING_V2_TRACKING"

STAGE1_TH = 0.53
STAGE2_TH = 0.52


def read_sql(path: Path, query: str, parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(path))
    try:
        return pd.read_sql_query(query, con, parse_dates=parse_dates)
    finally:
        con.close()


def build_future_labels() -> pd.DataFrame:
    panel = read_sql(
        RESEARCH_DB,
        """
        SELECT model_code, horizon, signal_date, ticker, bucket, next_bucket
        FROM s3_bucket_transition_panel
        WHERE model_code='S3' AND next_bucket IS NOT NULL
        """,
        parse_dates=["signal_date"],
    )
    panel["ticker"] = panel["ticker"].astype(str).str.zfill(6)
    panel = panel.sort_values(["horizon", "ticker", "signal_date"]).copy()
    for step in [2, 3, 4]:
        panel[f"future_bucket_{step}"] = panel.groupby(["horizon", "ticker"])["bucket"].shift(-step)
    panel["label_t10_2to4"] = panel[["future_bucket_2", "future_bucket_3", "future_bucket_4"]].isin(["T10_ex_T3", "T3"]).any(axis=1)
    panel["label_t3_2to4"] = panel[["future_bucket_2", "future_bucket_3", "future_bucket_4"]].eq("T3").any(axis=1)
    return panel[["horizon", "signal_date", "ticker", "bucket", "label_t10_2to4", "label_t3_2to4"]]


def load_official_history() -> pd.DataFrame:
    hist = pd.read_csv(S3_HISTORY, dtype={"ticker": str})
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    hist["date"] = pd.to_datetime(hist["date"])
    return hist[["date", "ticker", "name", "market", "s3_score"]].copy()


def prepare_stage_tracking_from_path(stage_name: str, csv_path: Path, label_col: str, threshold: float, future_labels: pd.DataFrame, official_hist: pd.DataFrame) -> pd.DataFrame:
    pred = pd.read_csv(csv_path, dtype={"ticker": str})
    pred["ticker"] = pred["ticker"].astype(str).str.zfill(6)
    pred["signal_date"] = pd.to_datetime(pred["signal_date"])
    pred["pred_prob"] = pd.to_numeric(pred["pred_prob"], errors="coerce")
    pred["label"] = pd.to_numeric(pred["label"], errors="coerce")
    pred = pred[pred["pred_prob"] >= threshold].copy()
    pred["stage_name"] = stage_name
    pred["threshold"] = threshold
    pred["actual_label_from_model"] = pred["label"]
    pred = pred.merge(
        future_labels,
        on=["horizon", "signal_date", "ticker", "bucket"],
        how="left",
    )
    pred = pred.merge(
        official_hist.rename(columns={"date": "signal_date", "s3_score": "official_s3_score"}),
        on=["signal_date", "ticker"],
        how="left",
        suffixes=("", "_official"),
    )
    pred["in_official_s3"] = pred["official_s3_score"].notna()
    pred["stage_only"] = ~pred["in_official_s3"]
    pred["actual_target_hit_2to4"] = pred[label_col]
    pred["actual_t10_or_better_2to4"] = pred["label_t10_2to4"]
    pred["actual_t3_2to4"] = pred["label_t3_2to4"]
    return pred


def latest_snapshot_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    stage1 = pd.read_csv(THRESHOLD_DIR / "operating_v2_stage1_candidates_2026-03-26.csv", dtype={"ticker": str})
    stage2 = pd.read_csv(THRESHOLD_DIR / "operating_v2_stage2_candidates_2026-03-26.csv", dtype={"ticker": str})
    current = pd.read_csv(S3_CURRENT, dtype={"ticker": str})
    current["ticker"] = current["ticker"].astype(str).str.zfill(6)
    current_tickers = set(current["ticker"])
    for df, stage_name, threshold in ((stage1, "stage1", STAGE1_TH), (stage2, "stage2", STAGE2_TH)):
        if df.empty:
            continue
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
        df["signal_date"] = pd.Timestamp("2026-03-26")
        df["stage_name"] = stage_name
        df["threshold"] = threshold
        df["actual_label_from_model"] = pd.NA
        df["label_t10_2to4"] = pd.NA
        df["label_t3_2to4"] = pd.NA
        df["actual_target_hit_2to4"] = pd.NA
        df["actual_t10_or_better_2to4"] = pd.NA
        df["actual_t3_2to4"] = pd.NA
        df["in_official_s3"] = df["ticker"].isin(current_tickers)
        df["stage_only"] = ~df["in_official_s3"]
    return stage1, stage2


def save_db(stage1_hist: pd.DataFrame, stage2_hist: pd.DataFrame, summary_overall: pd.DataFrame, summary_by_h: pd.DataFrame, latest_stage1: pd.DataFrame, latest_stage2: pd.DataFrame) -> None:
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        stage1_hist.to_sql("s3_operating_v2_stage1_tracking", con, if_exists="replace", index=False)
        stage2_hist.to_sql("s3_operating_v2_stage2_tracking", con, if_exists="replace", index=False)
        summary_overall.to_sql("s3_operating_v2_stage2_only_summary_overall", con, if_exists="replace", index=False)
        summary_by_h.to_sql("s3_operating_v2_stage2_only_summary_by_horizon", con, if_exists="replace", index=False)
        latest_stage1.to_sql("s3_operating_v2_stage1_latest", con, if_exists="replace", index=False)
        latest_stage2.to_sql("s3_operating_v2_stage2_latest", con, if_exists="replace", index=False)
    finally:
        con.close()


def render_md(summary_overall: pd.DataFrame, summary_by_h: pd.DataFrame, latest_stage2: pd.DataFrame, history_mode: str) -> str:
    lines = [
        "# S3 Operating V2 Tracking",
        "",
        f"- history source: `{history_mode}`",
        "- operating_v2 thresholds: `stage1 >= 0.53`, `stage2 >= 0.52`",
        "- labels: `2~4 step` transition windows",
        "- `stage2_only` means stage2 candidate and not in official S3 on the same signal date",
        "",
        "## Stage2-only Transition Summary",
        "",
        "| Scope | Obs | T10-or-better 2~4 step | T3 2~4 step |",
        "|---|---:|---:|---:|",
    ]
    for _, row in summary_overall.iterrows():
        lines.append(f"| overall | {int(row['obs_n'])} | {float(row['t10_or_better_rate']):.2%} | {float(row['t3_rate']):.2%} |")
    lines.extend([
        "",
        "## By Horizon",
        "",
        "| Horizon | Obs | T10-or-better 2~4 step | T3 2~4 step |",
        "|---|---:|---:|---:|",
    ])
    for _, row in summary_by_h.iterrows():
        lines.append(f"| {row['horizon']} | {int(row['obs_n'])} | {float(row['t10_or_better_rate']):.2%} | {float(row['t3_rate']):.2%} |")
    lines.extend(["", "## Latest Stage2-only Watch", ""])
    if latest_stage2.empty:
        lines.append("- none")
    else:
        for _, row in latest_stage2.iterrows():
            lines.append(f"- `{row['ticker']}` {row['name']} ({row['market']}) `pred_prob={float(row['pred_prob']):.4f}`")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    future_labels = build_future_labels()
    official_hist = load_official_history()

    stage1_pred_file = STRICT_WF_DIR / "stage1_strict_predictions.csv"
    stage2_pred_file = STRICT_WF_DIR / "stage2_strict_predictions.csv"
    history_mode = "strict_walkforward"
    if not stage1_pred_file.exists():
        stage1_pred_file = MODEL_DIR / "stage1_test_predictions.csv"
        history_mode = "train_test_split"
    if not stage2_pred_file.exists():
        stage2_pred_file = MODEL_DIR / "stage2_test_predictions.csv"
        history_mode = "train_test_split"

    stage1_hist = prepare_stage_tracking_from_path(
        "stage1", stage1_pred_file, "label_t10_2to4", STAGE1_TH, future_labels, official_hist
    )
    stage2_hist = prepare_stage_tracking_from_path(
        "stage2", stage2_pred_file, "label_t3_2to4", STAGE2_TH, future_labels, official_hist
    )

    stage2_only = stage2_hist[stage2_hist["stage_only"]].copy()
    summary_overall = pd.DataFrame([
        {
            "obs_n": int(len(stage2_only)),
            "t10_or_better_rate": float(pd.to_numeric(stage2_only["actual_t10_or_better_2to4"], errors="coerce").mean()) if len(stage2_only) else 0.0,
            "t3_rate": float(pd.to_numeric(stage2_only["actual_t3_2to4"], errors="coerce").mean()) if len(stage2_only) else 0.0,
        }
    ])
    summary_by_h = stage2_only.groupby("horizon").agg(
        obs_n=("ticker", "size"),
        t10_or_better_rate=("actual_t10_or_better_2to4", "mean"),
        t3_rate=("actual_t3_2to4", "mean"),
    ).reset_index()

    latest_stage1, latest_stage2 = latest_snapshot_rows()

    stage1_hist.to_csv(OUTDIR / "operating_v2_stage1_tracking_history.csv", index=False, encoding="utf-8-sig")
    stage2_hist.to_csv(OUTDIR / "operating_v2_stage2_tracking_history.csv", index=False, encoding="utf-8-sig")
    stage2_only.to_csv(OUTDIR / "operating_v2_stage2_only_tracking_history.csv", index=False, encoding="utf-8-sig")
    summary_overall.to_csv(OUTDIR / "operating_v2_stage2_only_summary_overall.csv", index=False, encoding="utf-8-sig")
    summary_by_h.to_csv(OUTDIR / "operating_v2_stage2_only_summary_by_horizon.csv", index=False, encoding="utf-8-sig")
    latest_stage1.to_csv(OUTDIR / "operating_v2_stage1_latest_watch.csv", index=False, encoding="utf-8-sig")
    latest_stage2.to_csv(OUTDIR / "operating_v2_stage2_latest_watch.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s3_operating_v2_tracking.md").write_text(render_md(summary_overall, summary_by_h, latest_stage2, history_mode), encoding="utf-8")

    save_db(stage1_hist, stage2_hist, summary_overall, summary_by_h, latest_stage1, latest_stage2)


if __name__ == "__main__":
    main()
