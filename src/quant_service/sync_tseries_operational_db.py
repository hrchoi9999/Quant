from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import re
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
DB_PATH = PROJECT_ROOT / r"data\db\tseries_operational.db"
RUN_DATE = "20260331"


def latest_asof_from_dir(src_dir: Path, pattern: str) -> str:
    candidates: list[str] = []
    regex = re.compile(pattern)
    for p in src_dir.iterdir():
        m = regex.match(p.name)
        if m:
            candidates.append(m.group(1))
    if not candidates:
        raise FileNotFoundError(f"No matching files for {pattern} in {src_dir}")
    return max(candidates)



def _to_int_bool(s: pd.Series) -> pd.Series:
    return s.map(lambda x: None if pd.isna(x) else int(bool(x)))


def _write_df(con: sqlite3.Connection, table: str, df: pd.DataFrame, delete_sql: str | None = None, delete_params: tuple = ()) -> None:
    cur = con.cursor()
    if delete_sql:
        cur.execute(delete_sql, delete_params)
    if not df.empty:
        df.to_sql(table, con, if_exists="append", index=False)
    con.commit()


def _sync_rolling_watchlist(con: sqlite3.Connection, model_code: str, asof_date: str, run_id: str, latest_path: Path, summary_path: Path) -> None:
    if latest_path.exists():
        latest = pd.read_csv(latest_path, dtype={'ticker': str})
        if not latest.empty:
            latest['model_code'] = model_code
            latest['asof_date'] = asof_date
            for col in ['market','asset_class','group_key','theme_bucket','theme_name_kr','is_s2_overlap','stage1_prob','stage2_prob','mcap','liquidity_20d_value']:
                if col not in latest.columns:
                    latest[col] = None
            latest['is_current'] = latest['is_current'].map(lambda x: None if pd.isna(x) else int(bool(x)))
            latest['is_s2_overlap'] = latest['is_s2_overlap'].map(lambda x: None if pd.isna(x) else int(bool(x)))
            latest = latest[[
                'model_code','asof_date','watch_status','watch_tier','is_current','current_bucket','best_bucket_recent',
                'appearances_recent','consecutive_current','last_seen_asof','prev_seen_asof','ticker','name','market',
                'asset_class','group_key','theme_bucket','theme_name_kr','is_s2_overlap','stage1_prob','stage2_prob','mcap','liquidity_20d_value'
            ]]
        else:
            latest = pd.DataFrame(columns=['model_code','asof_date','watch_status','watch_tier','is_current','current_bucket','best_bucket_recent','appearances_recent','consecutive_current','last_seen_asof','prev_seen_asof','ticker','name','market','asset_class','group_key','theme_bucket','theme_name_kr','is_s2_overlap','stage1_prob','stage2_prob','mcap','liquidity_20d_value'])
        _write_df(con, 'ts_rolling_watchlist_latest', latest, 'DELETE FROM ts_rolling_watchlist_latest WHERE model_code=? AND asof_date=?', (model_code, asof_date))

    if summary_path.exists():
        summary = pd.read_csv(summary_path)
        if not summary.empty:
            summary['model_code'] = model_code
            summary['asof_date'] = asof_date
            summary = summary[['model_code','asof_date','bucket','count']]
        else:
            summary = pd.DataFrame(columns=['model_code','asof_date','bucket','count'])
        _write_df(con, 'ts_rolling_watchlist_summary', summary, 'DELETE FROM ts_rolling_watchlist_summary WHERE model_code=? AND asof_date=?', (model_code, asof_date))


def upsert_meta_models(con: sqlite3.Connection) -> None:
    rows = [
        ("T-STOCK-V01", "T-STOCK-V01", "stock", "two_stage", "V01", "active", "Stock transition-based discovery model operational V1."),
        ("T-ETF-V01", "T-ETF-V01", "etf", "two_stage", "V01", "active", "ETF transition-based discovery model operational V1."),
    ]
    con.executemany(
        """
        INSERT OR REPLACE INTO ts_meta_models (
          model_code, display_name, asset_scope, stage_structure, version_label, status, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        rows,
    )
    con.commit()


def sync_stock(con: sqlite3.Connection) -> None:
    model_code = "T-STOCK-V01"
    op_dir = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\T_STOCK_V01_OPERATIONALIZATION"
    asof_date = latest_asof_from_dir(op_dir, r"t_stock_v01_latest_watchlist_(\d{4}-\d{2}-\d{2})\.csv")
    labels_path = PROJECT_ROOT / r"data\labels\t_stock_v01_theme_labels_20260331.csv"
    run_id = f"{model_code}:{asof_date}:shadow_refresh"
    profile_id = f"{model_code}:operating_v2:{asof_date}"

    con.execute(
        """
        INSERT OR REPLACE INTO ts_threshold_profiles (
          profile_id, model_code, profile_code, asof_date, stage1_threshold, stage2_confirmed_th, stage2_near_th,
          risk_filter_version, is_current, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (profile_id, model_code, "operating_v2", asof_date, 0.52, 0.525, 0.52, "stock_risk_filter_v1", 1, "Stock operating profile recalibrated after 2017 backfill: stage1 0.52, stage2 confirmed 0.525, stage2 near 0.52."),
    )
    con.execute(
        """
        INSERT OR REPLACE INTO ts_runs (
          ts_run_id, model_code, profile_id, asof_date, refresh_kind, status, source_snapshot_ref, started_at, finished_at, outdir, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, datetime('now'))
        """,
        (run_id, model_code, profile_id, asof_date, "shadow_refresh", "success", f"research_outputs:{RUN_DATE}", str(op_dir), "Synced stock operational watchlist, labels, and shadow tracking from local outputs."),
    )
    con.commit()

    labels = pd.read_csv(labels_path, dtype={"ticker": str})
    labels = labels.assign(model_code=model_code)
    labels = labels[["model_code", "asof_date", "ticker", "name", "market", "theme_bucket", "theme_name_kr", "label_source", "label_scope"]]
    _write_df(con, "ts_theme_labels", labels, "DELETE FROM ts_theme_labels WHERE model_code=? AND asof_date=?", (model_code, asof_date))

    latest = pd.read_csv(op_dir / f"t_stock_v01_latest_watchlist_{asof_date}.csv", dtype={"ticker": str})
    latest["model_code"] = model_code
    latest["asset_class"] = None
    latest["group_key"] = None
    latest["liquidity_20d_value"] = None
    latest["risk_filtered_flag"] = 1
    latest["source_run_id"] = run_id
    latest["details_json"] = None
    latest["is_s2_overlap"] = _to_int_bool(latest["is_s2_overlap"])
    latest = latest[[
        "model_code", "asof_date", "candidate_bucket", "ticker", "name", "market", "asset_class", "group_key",
        "theme_bucket", "theme_name_kr", "is_s2_overlap", "stage1_prob", "stage2_prob", "mcap", "liquidity_20d_value",
        "risk_filtered_flag", "source_run_id", "details_json"
    ]]
    _write_df(con, "ts_candidates_latest", latest, "DELETE FROM ts_candidates_latest WHERE model_code=? AND asof_date=?", (model_code, asof_date))

    hist = pd.read_csv(op_dir / f"t_stock_v01_shadow_tracking_history_{RUN_DATE}.csv", dtype={"ticker": str})
    hist["model_code"] = model_code
    hist["asset_class"] = None
    hist["group_key"] = None
    hist["source_run_id"] = run_id
    hist["details_json"] = None
    hist["actual_t10_hit"] = _to_int_bool(hist["actual_t10_or_better_2to4"])
    hist["actual_t3_hit"] = _to_int_bool(hist["actual_t3_2to4"])
    hist = hist[[
        "model_code", "signal_date", "horizon", "candidate_bucket", "ticker", "name", "market", "asset_class", "group_key",
        "theme_bucket", "theme_name_kr", "stage1_prob", "stage2_prob", "actual_t10_hit", "actual_t3_hit", "source_run_id", "details_json"
    ]]
    _write_df(con, "ts_candidates_history", hist, "DELETE FROM ts_candidates_history WHERE model_code=?", (model_code,))

    overall = pd.read_csv(op_dir / f"t_stock_v01_shadow_tracking_historical_summary_{RUN_DATE}.csv")
    overall["model_code"] = model_code
    overall["asof_date"] = asof_date
    overall["horizon"] = None
    overall["avg_stage1_prob"] = None
    overall["avg_stage2_prob"] = None
    overall = overall[["model_code", "asof_date", "candidate_bucket", "horizon", "obs_n", "t10_hit_rate", "t3_hit_rate", "avg_stage1_prob", "avg_stage2_prob"]]

    by_h = pd.read_csv(op_dir / f"t_stock_v01_shadow_tracking_historical_summary_by_horizon_{RUN_DATE}.csv")
    by_h["model_code"] = model_code
    by_h["asof_date"] = asof_date
    by_h["avg_stage1_prob"] = None
    by_h["avg_stage2_prob"] = None
    by_h = by_h[["model_code", "asof_date", "candidate_bucket", "horizon", "obs_n", "t10_hit_rate", "t3_hit_rate", "avg_stage1_prob", "avg_stage2_prob"]]

    summary = pd.concat([overall, by_h], ignore_index=True)
    _write_df(con, "ts_shadow_tracking_summary", summary, "DELETE FROM ts_shadow_tracking_summary WHERE model_code=? AND asof_date=?", (model_code, asof_date))

    _sync_rolling_watchlist(
        con,
        model_code,
        asof_date,
        run_id,
        op_dir / f"t_stock_v01_rolling_watchlist_{asof_date}.csv",
        op_dir / f"t_stock_v01_rolling_watchlist_summary_{RUN_DATE}.csv",
    )

    artifacts = pd.DataFrame([
        {"ts_run_id": run_id, "artifact_type": "latest_watchlist", "artifact_path": str(op_dir / f"t_stock_v01_latest_watchlist_{asof_date}.csv")},
        {"ts_run_id": run_id, "artifact_type": "latest_watchlist_summary", "artifact_path": str(op_dir / f"t_stock_v01_latest_watchlist_summary_{RUN_DATE}.csv")},
        {"ts_run_id": run_id, "artifact_type": "shadow_tracking_history", "artifact_path": str(op_dir / f"t_stock_v01_shadow_tracking_history_{RUN_DATE}.csv")},
        {"ts_run_id": run_id, "artifact_type": "shadow_tracking_summary", "artifact_path": str(op_dir / f"t_stock_v01_shadow_tracking_historical_summary_{RUN_DATE}.csv")},
        {"ts_run_id": run_id, "artifact_type": "risk_filtered_candidates", "artifact_path": str(op_dir / f"t_stock_v01_risk_filtered_candidates_{asof_date}.csv")},
        {"ts_run_id": run_id, "artifact_type": "theme_labels", "artifact_path": str(labels_path)},
    ])
    _write_df(con, "ts_artifacts", artifacts, "DELETE FROM ts_artifacts WHERE ts_run_id=?", (run_id,))


def sync_etf(con: sqlite3.Connection) -> None:
    model_code = "T-ETF-V01"
    asof_date = "2026-03-31"
    op_dir = PROJECT_ROOT / r"reports\model_upgrade_research\20260401\ETF_T_SERIES_OPERATIONALIZATION_PIT"
    run_id = f"{model_code}:{asof_date}:shadow_refresh"
    profile_id = f"{model_code}:operational_pit_v1:{asof_date}"

    con.execute(
        """
        INSERT OR REPLACE INTO ts_threshold_profiles (
          profile_id, model_code, profile_code, asof_date, stage1_threshold, stage2_confirmed_th, stage2_near_th,
          risk_filter_version, is_current, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (profile_id, model_code, "operational_pit_v1", asof_date, None, 0.65, 0.60, "etf_pit_risk_filter_v3", 1, "ETF PIT operational profile: stage1 momentum_trend top_ratio 0.08, stage2 vol_trend_compact with confirmed 0.65 and near 0.60. Inverse/leverage excluded, liquidity floor 20d avg trading value >= 20 billion KRW."),
    )
    con.execute(
        """
        INSERT OR REPLACE INTO ts_runs (
          ts_run_id, model_code, profile_id, asof_date, refresh_kind, status, source_snapshot_ref, started_at, finished_at, outdir, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, datetime('now'))
        """,
        (run_id, model_code, profile_id, asof_date, "shadow_refresh", "success", "research_outputs:20260401", str(op_dir), "Synced ETF PIT operational watchlist and shadow tracking from local outputs with inverse/leverage excluded."),
    )
    con.commit()

    latest = pd.read_csv(op_dir / f"etf_tseries_pit_latest_watchlist_{asof_date}.csv", dtype={"ticker": str})
    latest["model_code"] = model_code
    latest["asof_date"] = asof_date
    latest["market"] = None
    latest["theme_name_kr"] = latest.get("theme_name_kr", pd.Series([None] * len(latest)))
    latest["is_s2_overlap"] = None
    latest["mcap"] = None
    latest["risk_filtered_flag"] = 1
    latest["source_run_id"] = run_id
    latest["details_json"] = None
    latest = latest.rename(columns={"candidate_grade": "candidate_bucket"})
    latest = latest[[
        "model_code", "asof_date", "candidate_bucket", "ticker", "name", "market", "asset_class", "group_key",
        "theme_bucket", "theme_name_kr", "is_s2_overlap", "stage1_prob", "stage2_prob", "mcap", "liquidity_20d_value",
        "risk_filtered_flag", "source_run_id", "details_json"
    ]]
    _write_df(con, "ts_candidates_latest", latest, "DELETE FROM ts_candidates_latest WHERE model_code=? AND asof_date=?", (model_code, asof_date))

    etf_labels = latest[["model_code", "asof_date", "ticker", "name", "market", "theme_bucket", "theme_name_kr"]].copy()
    etf_labels["label_source"] = "operational_watchlist_v1"
    etf_labels["label_scope"] = "t_etf_v01_operational_candidates"
    _write_df(con, "ts_theme_labels", etf_labels, "DELETE FROM ts_theme_labels WHERE model_code=? AND asof_date=?", (model_code, asof_date))

    hist = pd.read_csv(op_dir / "etf_tseries_pit_shadow_tracking_history_20260401.csv", dtype={"ticker": str})
    hist["model_code"] = model_code
    hist["horizon"] = None
    hist["market"] = None
    hist["asset_class"] = None
    hist["group_key"] = None
    hist["theme_bucket"] = None
    hist["theme_name_kr"] = None
    hist["stage1_prob"] = hist.apply(lambda r: r["pred_prob"] if r.get("stage") == "stage1_lower_to_et10" else None, axis=1)
    hist["stage2_prob"] = hist.apply(lambda r: r["pred_prob"] if r.get("stage") == "stage2_et10_to_et3" else None, axis=1)
    hist["actual_t10_hit"] = hist.apply(lambda r: int(r["target_hit"]) if pd.notna(r.get("target_hit")) and r.get("stage") == "stage1_lower_to_et10" else None, axis=1)
    hist["actual_t3_hit"] = hist.apply(lambda r: int(r["target_hit"]) if pd.notna(r.get("target_hit")) and r.get("stage") == "stage2_et10_to_et3" else None, axis=1)
    hist["source_run_id"] = run_id
    hist["details_json"] = None
    hist = hist.rename(columns={"candidate_grade": "candidate_bucket"})
    hist = hist[[
        "model_code", "signal_date", "horizon", "candidate_bucket", "ticker", "name", "market", "asset_class", "group_key",
        "theme_bucket", "theme_name_kr", "stage1_prob", "stage2_prob", "actual_t10_hit", "actual_t3_hit", "source_run_id", "details_json"
    ]]
    _write_df(con, "ts_candidates_history", hist, "DELETE FROM ts_candidates_history WHERE model_code=?", (model_code,))

    summary = pd.read_csv(op_dir / "etf_tseries_pit_shadow_tracking_historical_summary_20260401.csv")
    summary["model_code"] = model_code
    summary["asof_date"] = asof_date
    summary = summary.rename(columns={"candidate_count": "obs_n", "avg_pred_prob": "avg_stage1_prob"})
    summary["horizon"] = None
    summary["avg_stage2_prob"] = None
    summary["t10_hit_rate"] = summary.apply(lambda r: r["hit_rate"] * 100.0 if r["stage"] == "stage1_lower_to_et10" else None, axis=1)
    summary["t3_hit_rate"] = summary.apply(lambda r: r["hit_rate"] * 100.0 if r["stage"] == "stage2_et10_to_et3" else None, axis=1)
    summary = summary[["model_code", "asof_date", "candidate_grade", "horizon", "obs_n", "t10_hit_rate", "t3_hit_rate", "avg_stage1_prob", "avg_stage2_prob"]].rename(columns={"candidate_grade": "candidate_bucket"})
    _write_df(con, "ts_shadow_tracking_summary", summary, "DELETE FROM ts_shadow_tracking_summary WHERE model_code=? AND asof_date=?", (model_code, asof_date))

    _sync_rolling_watchlist(
        con,
        model_code,
        asof_date,
        run_id,
        op_dir / f"t_stock_v01_rolling_watchlist_{asof_date}.csv",
        op_dir / f"t_stock_v01_rolling_watchlist_summary_{RUN_DATE}.csv",
    )

    _sync_rolling_watchlist(
        con,
        model_code,
        asof_date,
        run_id,
        op_dir / f"etf_tseries_pit_rolling_watchlist_{asof_date}.csv",
        op_dir / "etf_tseries_pit_rolling_watchlist_summary_20260401.csv",
    )

    artifacts = pd.DataFrame([
        {"ts_run_id": run_id, "artifact_type": "latest_watchlist", "artifact_path": str(op_dir / f"etf_tseries_pit_latest_watchlist_{asof_date}.csv")},
        {"ts_run_id": run_id, "artifact_type": "latest_watchlist_summary", "artifact_path": str(op_dir / "etf_tseries_pit_latest_watchlist_summary_20260401.csv")},
        {"ts_run_id": run_id, "artifact_type": "shadow_tracking_history", "artifact_path": str(op_dir / "etf_tseries_pit_shadow_tracking_history_20260401.csv")},
        {"ts_run_id": run_id, "artifact_type": "shadow_tracking_summary", "artifact_path": str(op_dir / "etf_tseries_pit_shadow_tracking_historical_summary_20260401.csv")},
        {"ts_run_id": run_id, "artifact_type": "risk_filtered_candidates", "artifact_path": str(op_dir / f"etf_tseries_pit_risk_filtered_candidates_{asof_date}.csv")},
    ])
    _write_df(con, "ts_artifacts", artifacts, "DELETE FROM ts_artifacts WHERE ts_run_id=?", (run_id,))


def main() -> None:
    ap = argparse.ArgumentParser(description="Sync T-series operational outputs into tseries_operational.db")
    ap.add_argument("--model", choices=["stock", "etf", "all"], default="all")
    args = ap.parse_args()

    con = sqlite3.connect(str(DB_PATH))
    try:
        upsert_meta_models(con)
        if args.model in ("stock", "all"):
            sync_stock(con)
        if args.model in ("etf", "all"):
            sync_etf(con)
    finally:
        con.close()

    print(f"[OK] synced tseries operational db for model={args.model}")


if __name__ == "__main__":
    main()

