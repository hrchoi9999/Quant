# build_growth_universe_flags.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from .common import norm_ticker, now_ts, read_sql, write_table
from .config import CLASSIFICATION_DB, DEFAULT_UNIVERSE, FEATURE_TABLE, OUT_DB, REPORT_DIR

GROWTH_FLAG_TABLE = "growth_universe_flags"
STRUCTURAL_GROWTH_THEMES = {
    "semiconductor_tech",
    "ai_software_platform",
    "robotics_automation",
    "bio_healthcare",
    "battery_ev_materials",
    "energy_utility_infra",
    "defense_aerospace",
    "shipbuilding_machinery",
    "auto_mobility",
    "contents_entertainment",
}


def _load_universe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ticker": str})
    df["ticker"] = df["ticker"].map(norm_ticker)
    return df.dropna(subset=["ticker"]).drop_duplicates("ticker")


def _load_latest_features(db: Path, asof: str) -> pd.DataFrame:
    df = read_sql(db, f"SELECT * FROM {FEATURE_TABLE} WHERE asof_date <= ?", [asof], parse_dates=["asof_date"])
    if df.empty:
        raise SystemExit("no valuation features found; run build_features first")
    latest_by_ticker = df.sort_values(["ticker", "asof_date"]).groupby("ticker", as_index=False).tail(1).copy()
    latest_by_ticker["ticker"] = latest_by_ticker["ticker"].astype(str).str.zfill(6)
    return latest_by_ticker


def _load_classification() -> pd.DataFrame:
    if not CLASSIFICATION_DB.exists():
        return pd.DataFrame()
    with sqlite3.connect(str(CLASSIFICATION_DB)) as con:
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", con)["name"].tolist()
        if "security_classification_master" not in tables:
            return pd.DataFrame()
        df = pd.read_sql_query(
            """
            SELECT ticker, name, market, sector_bucket, theme_bucket, theme_name_kr, source_quality, confidence_score
            FROM security_classification_master
            WHERE is_active = 1
            """,
            con,
        )
    if df.empty:
        return df
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df.sort_values(["ticker", "confidence_score"]).drop_duplicates("ticker", keep="last")


def _pct(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rank(pct=True, method="average").fillna(0.0)


def _reason(row: pd.Series) -> str:
    reasons: list[str] = []
    if int(row.get("growth_financial_flag") or 0):
        reasons.append("financial_growth")
    if int(row.get("growth_price_flag") or 0):
        reasons.append("price_revaluation")
    if int(row.get("growth_theme_flag") or 0):
        reasons.append("structural_growth_theme")
    if not int(row.get("growth_quality_flag") or 0):
        reasons.append("quality_or_data_coverage_weak")
    if not reasons:
        reasons.append("non_growth_reference")
    return ",".join(reasons)


def build_growth_flags(universe: Path, asof: str, db: Path = OUT_DB) -> pd.DataFrame:
    uni = _load_universe(universe)
    features = _load_latest_features(db, asof)
    cls = _load_classification()
    out = uni.merge(features, on="ticker", how="left", suffixes=("_universe", ""))
    if not cls.empty:
        out = out.merge(cls, on="ticker", how="left", suffixes=("", "_cls"))
        for col in ["name", "market", "sector_bucket", "theme_bucket"]:
            cls_col = f"{col}_cls"
            if cls_col in out.columns:
                out[col] = out[col].fillna(out[cls_col])

    out["market"] = out["market"].fillna(out.get("market_universe")).fillna("unknown")
    out["sector_bucket"] = out["sector_bucket"].fillna("unknown")
    out["theme_bucket"] = out["theme_bucket"].fillna("unknown")

    financial_raw = (
        pd.to_numeric(out.get("pit_growth_score"), errors="coerce").fillna(0)
        + pd.to_numeric(out.get("annual_revenue_yoy"), errors="coerce").fillna(0) * 5
        + pd.to_numeric(out.get("annual_op_income_yoy"), errors="coerce").fillna(0) * 5
        + pd.to_numeric(out.get("q_revenue_yoy_delta_1q"), errors="coerce").fillna(0)
        + pd.to_numeric(out.get("q_op_income_yoy_delta_1q"), errors="coerce").fillna(0)
    )
    price_raw = (
        pd.to_numeric(out.get("ret_3m"), errors="coerce").fillna(0)
        + pd.to_numeric(out.get("ret_6m"), errors="coerce").fillna(0) * 0.5
        + pd.to_numeric(out.get("excess_ret_3m_sector"), errors="coerce").fillna(0)
    )
    quality_raw = (
        pd.to_numeric(out.get("coverage_score"), errors="coerce").fillna(0)
        + pd.to_numeric(out.get("trading_value_20d"), errors="coerce").notna().astype(float)
        + pd.to_numeric(out.get("vol_60d"), errors="coerce").notna().astype(float)
    )

    out["financial_growth_score"] = (_pct(financial_raw) * 100).round(3)
    out["price_growth_score"] = (_pct(price_raw) * 100).round(3)
    out["quality_coverage_score"] = (_pct(quality_raw) * 100).round(3)
    out["growth_financial_flag"] = (out["financial_growth_score"] >= 60).astype(int)
    out["growth_price_flag"] = (out["price_growth_score"] >= 65).astype(int)
    out["growth_theme_flag"] = out["theme_bucket"].isin(STRUCTURAL_GROWTH_THEMES).astype(int)
    out["growth_quality_flag"] = (
        (pd.to_numeric(out.get("trading_value_20d"), errors="coerce").notna())
        & (pd.to_numeric(out.get("vol_60d"), errors="coerce").notna())
    ).astype(int)
    signal_count = out[["growth_financial_flag", "growth_price_flag", "growth_theme_flag"]].sum(axis=1)
    out["growth_signal_count"] = signal_count.astype(int)
    out["growth_universe_flag"] = ((signal_count >= 2) & (out["growth_quality_flag"].eq(1))).astype(int)
    out["growth_scope_reason"] = out.apply(_reason, axis=1)
    out["asof_date"] = asof
    out["model_code"] = "AI-GROWTH-VALUATION-V01"
    out["created_at"] = now_ts()

    keep = [
        "asof_date",
        "ticker",
        "name",
        "market",
        "sector_bucket",
        "theme_bucket",
        "theme_name_kr",
        "growth_universe_flag",
        "growth_signal_count",
        "growth_financial_flag",
        "growth_price_flag",
        "growth_theme_flag",
        "growth_quality_flag",
        "financial_growth_score",
        "price_growth_score",
        "quality_coverage_score",
        "growth_scope_reason",
        "model_code",
        "created_at",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    write_table(db, GROWTH_FLAG_TABLE, out)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    out.to_csv(REPORT_DIR / f"growth_universe_flags_{token}.csv", index=False, encoding="utf-8-sig")
    summary = (
        out.groupby(["market", "growth_universe_flag"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values(["market", "growth_universe_flag"])
    )
    summary.to_csv(REPORT_DIR / f"growth_universe_flags_summary_{token}.csv", index=False, encoding="utf-8-sig")
    (REPORT_DIR / f"growth_universe_flags_summary_{token}.json").write_text(
        json.dumps(
            {
                "asof_date": asof,
                "universe_rows": int(len(out)),
                "growth_rows": int(out["growth_universe_flag"].sum()),
                "summary": summary.to_dict(orient="records"),
                "generated_at": now_ts(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build growth universe flags for AI-GROWTH-VALUATION-V01.")
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE).replace("_fundready", ""))
    parser.add_argument("--asof", required=True)
    parser.add_argument("--db", default=str(OUT_DB))
    args = parser.parse_args()
    df = build_growth_flags(Path(args.universe), args.asof, Path(args.db))
    summary = df.groupby(["market", "growth_universe_flag"], as_index=False).size().rename(columns={"size": "count"})
    print(
        json.dumps(
            {
                "status": "ok",
                "asof_date": args.asof,
                "rows": int(len(df)),
                "growth_rows": int(df["growth_universe_flag"].sum()),
                "summary": summary.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
