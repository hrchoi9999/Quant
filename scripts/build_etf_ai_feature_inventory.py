from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(r"D:\Quant")
UNIVERSE_DIR = ROOT / r"data\universe"
PRICE_DB = ROOT / r"data\db\price.db"
MODEL_RESEARCH_DB = ROOT / r"data\db\model_research.db"
TSERIES_DB = ROOT / r"data\db\tseries_operational.db"
REPORT_DIR = ROOT / r"reports\etf_ai_feature_inventory"
BACKTEST_DIR = ROOT / r"reports\backtest_etf_allocation"


def _token(asof: str) -> str:
    return asof.replace("-", "")


def _read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False, **kwargs)


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if pd.isna(value):
            return None
        return round(float(value), 6)
    if pd.isna(value):
        return None
    return value


def _records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if df.empty:
        return []
    if limit is not None:
        df = df.head(limit)
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict("records")]


def _value_counts(df: pd.DataFrame, col: str, limit: int = 20) -> list[dict[str, Any]]:
    if df.empty or col not in df.columns:
        return []
    vc = (
        df[col]
        .fillna("UNKNOWN")
        .astype(str)
        .value_counts()
        .rename_axis(col)
        .reset_index(name="count")
        .head(limit)
    )
    return _records(vc)


def _table_info(db_path: Path, table: str) -> dict[str, Any]:
    if not db_path.exists():
        return {"exists": False, "rows": 0, "columns": []}
    with sqlite3.connect(db_path) as con:
        found = con.execute(
            "select 1 from sqlite_master where type='table' and name=?",
            (table,),
        ).fetchone()
        if not found:
            return {"exists": False, "rows": 0, "columns": []}
        rows = con.execute(f"select count(*) from {table}").fetchone()[0]
        columns = [row[1] for row in con.execute(f"pragma table_info({table})").fetchall()]
    return {"exists": True, "rows": int(rows), "columns": columns}


def _price_coverage(tickers: list[str], asof: str) -> dict[str, Any]:
    if not PRICE_DB.exists() or not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    query = f"""
        select ticker, min(date) as first_date, max(date) as last_date, count(*) as rows
        from prices_daily
        where ticker in ({placeholders})
        group by ticker
    """
    with sqlite3.connect(PRICE_DB) as con:
        coverage = pd.read_sql_query(query, con, params=tickers)
    if coverage.empty:
        return {"expected_tickers": len(tickers), "covered_tickers": 0}
    latest_counts = (
        coverage["last_date"]
        .fillna("UNKNOWN")
        .astype(str)
        .value_counts()
        .rename_axis("last_date")
        .reset_index(name="ticker_count")
        .sort_values(["last_date"], ascending=False)
    )
    return {
        "expected_tickers": len(tickers),
        "covered_tickers": int(coverage["ticker"].nunique()),
        "coverage_ratio": round(float(coverage["ticker"].nunique() / len(tickers)), 6),
        "first_price_date": str(coverage["first_date"].min()),
        "latest_price_date": str(coverage["last_date"].max()),
        "tickers_on_asof": int((coverage["last_date"].astype(str) >= asof).sum()),
        "latest_date_distribution": _records(latest_counts, 10),
    }


def _latest_file(folder: Path, pattern: str) -> Path | None:
    paths = sorted(folder.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return paths[0] if paths else None


def _t_etf_outputs(asof: str) -> dict[str, Any]:
    token = _token(asof)
    run_dir = ROOT / "reports" / "model_upgrade_research" / token / "ETF_T_SERIES_OPERATIONALIZATION_PIT"
    backfill_dir = ROOT / "reports" / "model_upgrade_research" / token / "ETF_T_SERIES_PIT_BACKFILL_V1"
    discovery_dir = ROOT / "reports" / "model_upgrade_research" / token / "ETF_TWO_STAGE_DISCOVERY_TUNED_PIT"

    candidates = _read_csv(run_dir / f"etf_tseries_pit_operational_candidates_{asof}.csv")
    feature_panel = _read_csv(backfill_dir / "etf_tseries_pit_feature_panel.csv")
    full_rank = _read_csv(discovery_dir / f"etf_two_stage_tuned_pit_full_rank_{asof}.csv")
    backtest = _read_csv(BACKTEST_DIR / f"etf_alloc_summary_{token}_M_20230608_{token}.csv")

    return {
        "operational_dir": str(run_dir),
        "feature_panel_rows": int(len(feature_panel)),
        "feature_panel_columns": list(feature_panel.columns),
        "operational_candidate_rows": int(len(candidates)),
        "candidate_grade_counts": _value_counts(candidates, "candidate_grade"),
        "current_full_rank_rows": int(len(full_rank)),
        "stage1_top_sample": _records(full_rank.sort_values("stage1_prob", ascending=False), 10)
        if "stage1_prob" in full_rank.columns
        else [],
        "allocation_backtest_summary": _records(backtest),
    }


def build_inventory(asof: str) -> dict[str, Any]:
    token = _token(asof)
    master = _read_csv(UNIVERSE_DIR / "universe_etf_master_latest.csv", dtype={"ticker": str})
    meta = _read_csv(UNIVERSE_DIR / f"etf_meta_{token}.csv", dtype={"ticker": str})
    core = _read_csv(UNIVERSE_DIR / f"universe_etf_core_{token}.csv", dtype={"ticker": str})
    pit = _read_csv(UNIVERSE_DIR / "etf_pit_backfill" / "universe_etf_pit_monthly_201701_202605.csv", dtype={"ticker": str})
    tickers = sorted(master["ticker"].dropna().astype(str).str.zfill(6).unique().tolist()) if not master.empty else []

    payload = {
        "source_name": "etf_ai_feature_inventory",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "ETF-only AI feature inventory; stock AI features are out-of-scope.",
        "universe": {
            "master_rows": int(len(master)),
            "meta_rows": int(len(meta)),
            "core_rows": int(len(core)),
            "pit_monthly_rows": int(len(pit)),
            "asset_class_counts": _value_counts(meta, "asset_class"),
            "group_key_counts": _value_counts(meta, "group_key"),
            "role_key_counts": _value_counts(meta, "role_key"),
            "currency_exposure_counts": _value_counts(meta, "currency_exposure"),
            "inverse_count": int(pd.to_numeric(meta.get("is_inverse"), errors="coerce").fillna(0).astype(bool).sum())
            if not meta.empty and "is_inverse" in meta.columns
            else 0,
            "leveraged_count": int(pd.to_numeric(meta.get("is_leveraged"), errors="coerce").fillna(0).astype(bool).sum())
            if not meta.empty and "is_leveraged" in meta.columns
            else 0,
        },
        "price_coverage": _price_coverage(tickers, asof),
        "db_tables": {
            "price.prices_daily": _table_info(PRICE_DB, "prices_daily"),
            "price.etf_meta": _table_info(PRICE_DB, "etf_meta"),
            "model_research.etf_tseries_pit_feature_panel": _table_info(MODEL_RESEARCH_DB, "etf_tseries_pit_feature_panel"),
            "model_research.etf_tseries_pit_bucket_panel": _table_info(MODEL_RESEARCH_DB, "etf_tseries_pit_bucket_panel"),
            "model_research.etf_tseries_model_summary": _table_info(MODEL_RESEARCH_DB, "etf_tseries_model_summary"),
            "tseries.ts_candidates_latest": _table_info(TSERIES_DB, "ts_candidates_latest"),
            "tseries.ts_shadow_tracking_summary": _table_info(TSERIES_DB, "ts_shadow_tracking_summary"),
        },
        "t_etf_outputs": _t_etf_outputs(asof),
        "feature_inventory": {
            "available_now": [
                "ETF identity: ticker, name, active flag, listing/history proxy",
                "ETF classification: asset_class, group_key, expanded_group, role_key",
                "Product structure: currency_exposure, is_inverse, is_leveraged",
                "Liquidity: liquidity_20d_value, volume/value from prices_daily",
                "Trend/momentum: ret_20d, ret_60d, ret_120d, ret_240d",
                "Risk: vol_20d, vol_60d, dd_60d, dd_120d, path_mdd_3M/6M/1Y",
                "Moving-average state: dist_ma20/60/120, ma20_ma60_gap, ma60_ma120_gap",
                "Timing oscillator: rsi20",
                "T-ETF model scores: stage1_prob, stage2_prob, candidate_grade",
                "Allocation backtest NAV metrics: CAGR, MDD, Sharpe, turnover",
            ],
            "missing_or_needs_collection": [
                "NAV/iNAV and premium-discount ratio",
                "Tracking error versus official benchmark index",
                "Expense ratio, AUM, shares outstanding",
                "Underlying index identifier and index return history",
                "ETF holdings/component weights",
                "Bid-ask spread or intraday liquidity proxy",
                "Creation/redemption or fund flow data",
                "FX/commodity/rate/global index context aligned by ETF exposure",
            ],
            "label_candidates": [
                "1W/2W tactical return and win label for timing",
                "1M/3M risk-adjusted return label for allocation",
                "drawdown-avoidance label using path_mdd",
                "role-aware label: CORE_BETA, DEFENSIVE_HEDGE, TACTICAL_HEDGE separately",
                "regime-aware label: risk_on, neutral, risk_off sleeves separately",
            ],
        },
    }
    return payload


def _write_md(payload: dict[str, Any], path: Path) -> None:
    universe = payload["universe"]
    price = payload["price_coverage"]
    tetf = payload["t_etf_outputs"]
    backtest = tetf.get("allocation_backtest_summary") or []
    bt = backtest[0] if backtest else {}
    lines = [
        f"# ETF AI Feature Inventory - {payload['as_of_date']}",
        "",
        "## Summary",
        "",
        f"- ETF master rows: {universe['master_rows']:,}",
        f"- ETF meta rows: {universe['meta_rows']:,}",
        f"- ETF core rows: {universe['core_rows']:,}",
        f"- PIT monthly rows: {universe['pit_monthly_rows']:,}",
        f"- Price coverage: {price.get('covered_tickers', 0):,}/{price.get('expected_tickers', 0):,} ({price.get('coverage_ratio')})",
        f"- Latest ETF price date: {price.get('latest_price_date')}",
        f"- T-ETF feature panel rows: {tetf.get('feature_panel_rows'):,}",
        f"- T-ETF operational candidate rows: {tetf.get('operational_candidate_rows'):,}",
        "",
        "## Universe Breakdown",
        "",
        "### Asset Class",
        "",
        *[f"- {row['asset_class']}: {row['count']}" for row in universe["asset_class_counts"]],
        "",
        "### Role",
        "",
        *[f"- {row['role_key']}: {row['count']}" for row in universe["role_key_counts"]],
        "",
        "## Current T-ETF Outputs",
        "",
        *[
            f"- {row.get('ticker')} {row.get('name')}: stage1={row.get('stage1_prob')}, group={row.get('group_key')}, role={row.get('role_key')}"
            for row in tetf.get("stage1_top_sample", [])[:10]
        ],
        "",
        "## ETF Allocation Backtest",
        "",
        f"- CAGR: {bt.get('cagr')}",
        f"- MDD: {bt.get('mdd')}",
        f"- Sharpe: {bt.get('sharpe')}",
        f"- Turnover: {bt.get('turnover')}",
        "",
        "## Available Features",
        "",
        *[f"- {item}" for item in payload["feature_inventory"]["available_now"]],
        "",
        "## Missing Or Needs Collection",
        "",
        *[f"- {item}" for item in payload["feature_inventory"]["missing_or_needs_collection"]],
        "",
        "## Label Candidates",
        "",
        *[f"- {item}" for item in payload["feature_inventory"]["label_candidates"]],
        "",
        "## Initial Judgment",
        "",
        "- ETF price, liquidity, classification, PIT monthly feature panel, and T-ETF scores are already usable.",
        "- ETF-specific valuation/allocation AI should start from available technical/liquidity/role/regime features.",
        "- NAV/iNAV, tracking error, expense ratio, AUM, official benchmark and holdings data are not yet available in the current inventory and should be separate data-collection work.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ETF AI feature inventory.")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    payload = build_inventory(args.asof)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(args.asof)
    json_path = REPORT_DIR / f"etf_ai_feature_inventory_{token}.json"
    md_path = REPORT_DIR / f"etf_ai_feature_inventory_{token}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(payload, md_path)
    print(json.dumps({"status": "ok", "as_of_date": args.asof, "outputs": {"json": str(json_path), "md": str(md_path)}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
