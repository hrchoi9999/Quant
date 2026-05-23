# predict_scores.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .common import now_ts, read_sql
from .config import FEATURE_TABLE, MODEL_CODE, MODEL_NAME_KR, MODEL_DIR, OUT_DB, REPORT_DIR, SCORE_TABLE
from .rule_score_engine import build_rule_scores


def _latest_model_path(model_dir: Path) -> Path:
    candidates = sorted(model_dir.glob(f"{MODEL_CODE}_*.joblib"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise SystemExit(f"no trained valuation AI model found in {model_dir}")
    return candidates[0]


def _load_features_for_asof(db: Path, asof: str) -> pd.DataFrame:
    df = read_sql(
        db,
        f"""
        SELECT *
        FROM {FEATURE_TABLE}
        WHERE asof_date <= ?
        """,
        [asof],
        parse_dates=["asof_date"],
    )
    if df.empty:
        raise SystemExit("no valuation features available for scoring")
    latest = df["asof_date"].max()
    return df[df["asof_date"].eq(latest)].copy()


def _upsert_scores(db: Path, scores: pd.DataFrame, asof: str, model_version: str) -> None:
    with sqlite3.connect(str(db)) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (SCORE_TABLE,)).fetchone()
        if exists:
            existing_cols = {row[1] for row in con.execute(f"PRAGMA table_info({SCORE_TABLE})").fetchall()}
            for col in scores.columns:
                if col not in existing_cols:
                    dtype = "REAL" if pd.api.types.is_numeric_dtype(scores[col]) else "TEXT"
                    con.execute(f"ALTER TABLE {SCORE_TABLE} ADD COLUMN {col} {dtype}")
            con.execute(f"DELETE FROM {SCORE_TABLE} WHERE asof_date = ? AND model_version = ?", (asof, model_version))
        scores.to_sql(SCORE_TABLE, con, if_exists="append", index=False)


def predict_scores(db: Path, asof: str, model_path: Path | None = None) -> pd.DataFrame:
    model_path = model_path or _latest_model_path(MODEL_DIR)
    bundle = joblib.load(model_path)
    model_version = str(bundle.get("model_version") or model_path.stem)
    regressor = bundle["regressor"]
    features = _load_features_for_asof(db, asof)
    predicted = pd.Series(regressor.predict(features), index=features.index)
    scored = build_rule_scores(features, predicted)

    for label, col in [
        ("label_outperform", "outperform_prob"),
        ("label_underperform", "underperform_prob"),
        ("label_overheated", "overheated_prob"),
        ("label_value_creation", "value_creation_prob"),
    ]:
        model = bundle.get(label)
        scored[col] = np.nan
        if model is not None:
            scored[col] = model.predict_proba(features)[:, 1]

    scored["model_code"] = MODEL_CODE
    scored["model_name_ko"] = MODEL_NAME_KR
    scored["model_version"] = model_version
    scored["created_at"] = now_ts()
    scored["asof_date"] = pd.to_datetime(scored["asof_date"]).dt.strftime("%Y-%m-%d")
    keep = [
        "asof_date",
        "ticker",
        "name",
        "market",
        "sector_bucket",
        "theme_bucket",
        "market_regime",
        "market_regime_label",
        "market_ret_1m",
        "market_ret_3m",
        "market_ret_6m",
        "market_breadth_ret_pos_1m",
        "market_breadth_above_sma60",
        "market_breadth_above_sma120",
        "market_context_available",
        "qm_market_state_label",
        "qm_market_state_score",
        "qm_trend_score",
        "qm_breadth_score",
        "qm_risk_score",
        "qm_defensive_flow_score",
        "qm_risk_on_score",
        "qm_risk_off_score",
        "qm_quantmarket_theme_bucket",
        "qm_theme_momentum_score",
        "qm_theme_rotation_score",
        "qm_theme_mapping_confidence",
        "qm_market_stress_score",
        "qm_volatility_regime_label",
        "qm_flow_context_available",
        "valuation_ai_score",
        "valuation_state",
        "predicted_excess_return_12m",
        "current_valuation_percentile",
        "implied_growth_pressure",
        "valuation_growth_gap",
        "expected_return_score",
        "valuation_safety_score",
        "growth_quality_score",
        "revision_momentum_score",
        "downside_safety_score",
        "downside_risk_score",
        "confidence_score",
        "outperform_prob",
        "underperform_prob",
        "overheated_prob",
        "value_creation_prob",
        "reason_codes",
        "model_code",
        "model_name_ko",
        "model_version",
        "created_at",
    ]
    scores = scored[[col for col in keep if col in scored.columns]].copy()
    _upsert_scores(db, scores, scores["asof_date"].iloc[0], model_version)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    scores.sort_values("valuation_ai_score", ascending=False).to_csv(REPORT_DIR / f"valuation_scores_{token}.csv", index=False, encoding="utf-8-sig")
    (REPORT_DIR / f"valuation_scores_{token}.json").write_text(
        json.dumps(
            {
                "model_code": MODEL_CODE,
                "model_name_ko": MODEL_NAME_KR,
                "model_version": model_version,
                "asof_date": scores["asof_date"].iloc[0],
                "rows": int(len(scores)),
                "generated_at": now_ts(),
                "score_state_counts": scores["valuation_state"].value_counts().to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return scores


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict growth valuation AI scores.")
    parser.add_argument("--db", default=str(OUT_DB))
    parser.add_argument("--asof", required=True)
    parser.add_argument("--model-path")
    args = parser.parse_args()
    scores = predict_scores(Path(args.db), args.asof, Path(args.model_path) if args.model_path else None)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": int(len(scores)),
                "asof_date": scores["asof_date"].iloc[0],
                "top": scores.sort_values("valuation_ai_score", ascending=False).head(5)[["ticker", "name", "valuation_ai_score", "valuation_state"]].to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
