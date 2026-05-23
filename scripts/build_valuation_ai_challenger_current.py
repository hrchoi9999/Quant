# build_valuation_ai_challenger_current.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_valuation_ai_feature_ablation import _feature_set, _fit_regressor, _load_joined
from src.models.valuation_ai.config import MODEL_CODE, MODEL_NAME_KR, MODEL_DIR, OUT_DB, REPORT_DIR
from src.models.valuation_ai.rule_score_engine import build_rule_scores


ADMIN_TRACKER = ROOT / "service_platform" / "web" / "admin_data" / "current" / "admin_new_entry_tracker.json"
ADMIN_CURRENT_DIR = ROOT / "service_platform" / "web" / "admin_data" / "current"
STATE_RANK = {"OUT_OF_SCOPE_OR_MISSING": -1, "AVOID": 0, "OVERHEATED": 1, "FAIR": 2, "UNDERVALUED": 3}
FAVORABLE_STATES = {"UNDERVALUED", "FAIR"}
CAUTION_STATES = {"OVERHEATED", "AVOID"}
TICKER_RE = re.compile(r"^\d{1,6}$")
QM_MARKET_RISK_WATCH_THRESHOLD = -2.0
QM_MARKET_STRESS_WATCH_THRESHOLD = 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build admin current payload for valuation AI challenger/risk overlay.")
    parser.add_argument("--db", default=str(OUT_DB))
    parser.add_argument("--admin-tracker", default=str(ADMIN_TRACKER))
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--valid-end", default="2025-03-31")
    parser.add_argument("--champion", default="LOCAL_MARKET")
    parser.add_argument("--challenger", default="QM_MARKET_THEME")
    parser.add_argument("--risk-variant", default="QM_MARKET_RISK")
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    parser.add_argument("--admin-current-dir", default=str(ADMIN_CURRENT_DIR))
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_ticker(value: Any) -> str | None:
    ticker = str(value or "").strip()
    if not TICKER_RE.match(ticker):
        return None
    return ticker.zfill(6)


def latest_rank_rows(admin: dict[str, Any]) -> list[dict[str, Any]]:
    weekly = admin.get("weekly_rankings", {})
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for scope_key in ["user_models", "internal_models", "tseries_models"]:
        for row in weekly.get(scope_key, []):
            if row.get("is_latest_snapshot") is True:
                ticker = normalize_ticker(row.get("security_code"))
                if not ticker:
                    continue
                scope = row.get("scope") or scope_key.replace("_models", "")
                model_code = row.get("model_code") or row.get("service_profile") or row.get("model_key")
                dedupe_key = (str(scope), str(model_code), ticker)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                out.append(
                    {
                        "scope": scope,
                        "source_table": f"weekly_rankings.{scope_key}",
                        "model_code": model_code,
                        "service_profile": row.get("service_profile"),
                        "week_end": row.get("week_end"),
                        "snapshot_date": row.get("snapshot_date"),
                        "security_code": ticker,
                        "display_name": row.get("display_name"),
                        "rank_no": row.get("rank_no"),
                        "score": row.get("score"),
                        "score_basis": row.get("score_basis"),
                        "weight": row.get("weight"),
                        "candidate_bucket": row.get("candidate_bucket"),
                    }
                )
    return out


def latest_features(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    frame = df[df["asof_date"] <= pd.Timestamp(asof)].copy()
    if frame.empty:
        raise SystemExit(f"no features on or before {asof}")
    latest = frame["asof_date"].max()
    return frame[frame["asof_date"].eq(latest)].copy()


def train_variant(
    df: pd.DataFrame,
    variant: str,
    train_end: str,
    asof: str,
    save_model: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    feature_columns, categorical_columns, description = _feature_set(variant)
    available_features = [col for col in feature_columns if col in df.columns]
    available_cats = [col for col in categorical_columns if col in df.columns]
    labeled = df[df["fwd_excess_ret_12m"].notna()].sort_values("asof_date").copy()
    train = labeled[labeled["asof_date"] <= pd.Timestamp(train_end)].copy()
    if train.empty:
        raise SystemExit(f"empty training rows for {variant}")
    regressor = _fit_regressor(train, available_features, available_cats)
    compact = asof.replace("-", "")
    model_version = f"{MODEL_CODE}-{variant.replace('_', '-')}-{compact}-001"
    model_path = None
    if save_model:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model_path = MODEL_DIR / f"{model_version}.joblib"
        joblib.dump(
            {
                "model_code": MODEL_CODE,
                "model_name_ko": MODEL_NAME_KR,
                "model_version": model_version,
                "feature_set": variant,
                "feature_columns": available_features,
                "categorical_columns": available_cats,
                "regressor": regressor,
            },
            model_path,
        )
        metadata_path = MODEL_DIR / f"{model_version}_metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "model_code": MODEL_CODE,
                    "model_name_ko": MODEL_NAME_KR,
                    "model_version": model_version,
                    "feature_set": variant,
                    "description": description,
                    "train_end": train_end,
                    "asof_date": asof,
                    "feature_count": len(available_features),
                    "categorical_count": len(available_cats),
                    "model_path": str(model_path),
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    features = latest_features(df, asof)
    pred = pd.Series(regressor.predict(features), index=features.index)
    scored = build_rule_scores(features, pred)
    scored["ticker"] = scored["ticker"].astype(str).str.zfill(6)
    scored["variant"] = variant
    meta = {
        "feature_set": variant,
        "model_name_ko": MODEL_NAME_KR,
        "description": description,
        "model_version": model_version,
        "model_path": str(model_path) if model_path else None,
        "feature_count": len(available_features),
        "categorical_count": len(available_cats),
    }
    return scored, meta


def score_map(scored: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {str(row["ticker"]).zfill(6): row for row in scored.to_dict(orient="records")}


def to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rounded(value: Any, digits: int = 6) -> float | None:
    val = to_float(value)
    return None if val is None else round(val, digits)


def state_delta(base_state: str, variant_state: str) -> int:
    return STATE_RANK.get(str(variant_state), -1) - STATE_RANK.get(str(base_state), -1)


def change_label(delta: int) -> str:
    if delta >= 2:
        return "strong_upgrade"
    if delta == 1:
        return "upgrade"
    if delta == 0:
        return "same"
    if delta == -1:
        return "downgrade"
    return "strong_downgrade"


def risk_tag(champion_state: str, risk_state: str, risk_delta: int, risk_score: float | None, stress_score: float | None) -> str:
    if risk_state == "OUT_OF_SCOPE_OR_MISSING":
        return "out_of_scope"
    if risk_delta <= -1 or risk_state == "AVOID":
        return "risk_caution"
    market_risk_watch = risk_score is not None and risk_score <= QM_MARKET_RISK_WATCH_THRESHOLD
    market_stress_watch = stress_score is not None and stress_score >= QM_MARKET_STRESS_WATCH_THRESHOLD
    if risk_state == "OVERHEATED" or market_stress_watch or market_risk_watch:
        return "risk_watch"
    if risk_state in FAVORABLE_STATES and champion_state in FAVORABLE_STATES:
        return "risk_clear"
    return "risk_neutral"


def build_candidates(
    rows: list[dict[str, Any]],
    champion_scores: dict[str, dict[str, Any]],
    challenger_scores: dict[str, dict[str, Any]],
    risk_scores: dict[str, dict[str, Any]],
    champion: str,
    challenger: str,
    risk_variant: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        ticker = row["security_code"]
        champ = champion_scores.get(ticker)
        chal = challenger_scores.get(ticker)
        risk = risk_scores.get(ticker)
        champion_state = str(champ.get("valuation_state")) if champ else "OUT_OF_SCOPE_OR_MISSING"
        challenger_state = str(chal.get("valuation_state")) if chal else "OUT_OF_SCOPE_OR_MISSING"
        risk_state = str(risk.get("valuation_state")) if risk else "OUT_OF_SCOPE_OR_MISSING"
        c_score = rounded(champ.get("valuation_ai_score")) if champ else None
        q_score = rounded(chal.get("valuation_ai_score")) if chal else None
        r_score = rounded(risk.get("valuation_ai_score")) if risk else None
        q_delta = state_delta(champion_state, challenger_state)
        r_delta = state_delta(champion_state, risk_state)
        out.append(
            {
                **row,
                "ai_model_code": MODEL_CODE,
                "ai_model_name_ko": MODEL_NAME_KR,
                "champion_variant": champion,
                "challenger_variant": challenger,
                "risk_variant": risk_variant,
                "champion_state": champion_state,
                "champion_score": c_score,
                "challenger_state": challenger_state,
                "challenger_score": q_score,
                "challenger_score_delta": None if c_score is None or q_score is None else round(q_score - c_score, 6),
                "challenger_state_delta": q_delta,
                "challenger_change_label": change_label(q_delta),
                "risk_state": risk_state,
                "risk_score": r_score,
                "risk_score_delta": None if c_score is None or r_score is None else round(r_score - c_score, 6),
                "risk_state_delta": r_delta,
                "risk_change_label": change_label(r_delta),
                "risk_tag": risk_tag(
                    champion_state,
                    risk_state,
                    r_delta,
                    rounded(risk.get("qm_risk_score")) if risk else None,
                    rounded(risk.get("qm_market_stress_score")) if risk else None,
                ),
                "qm_market_state_label": chal.get("qm_market_state_label") if chal else None,
                "qm_market_state_score": rounded(chal.get("qm_market_state_score")) if chal else None,
                "qm_quantmarket_theme_bucket": chal.get("qm_quantmarket_theme_bucket") if chal else None,
                "qm_theme_momentum_score": rounded(chal.get("qm_theme_momentum_score")) if chal else None,
                "qm_theme_rotation_score": rounded(chal.get("qm_theme_rotation_score")) if chal else None,
                "qm_theme_mapping_confidence": rounded(chal.get("qm_theme_mapping_confidence")) if chal else None,
                "qm_risk_score": rounded(risk.get("qm_risk_score")) if risk else None,
                "qm_market_stress_score": rounded(risk.get("qm_market_stress_score")) if risk else None,
                "qm_volatility_regime_label": risk.get("qm_volatility_regime_label") if risk else None,
                "predicted_excess_return_12m_champion": rounded(champ.get("predicted_excess_return_12m")) if champ else None,
                "predicted_excess_return_12m_challenger": rounded(chal.get("predicted_excess_return_12m")) if chal else None,
                "predicted_excess_return_12m_risk": rounded(risk.get("predicted_excess_return_12m")) if risk else None,
            }
        )
    return out


def summarize_by_model(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[(row["scope"], row["model_code"])].append(row)
    summary: list[dict[str, Any]] = []
    for (scope, model), rows in sorted(grouped.items()):
        challenger_states = Counter(r["challenger_state"] for r in rows)
        risk_tags = Counter(r["risk_tag"] for r in rows)
        changes = Counter(r["challenger_change_label"] for r in rows)
        scores = [to_float(r.get("challenger_score")) for r in rows]
        scores = [v for v in scores if v is not None]
        favorable = sum(challenger_states.get(s, 0) for s in FAVORABLE_STATES)
        caution = sum(challenger_states.get(s, 0) for s in CAUTION_STATES)
        summary.append(
            {
                "scope": scope,
                "model_code": model,
                "candidate_count": len(rows),
                "challenger_favorable_count": favorable,
                "challenger_caution_count": caution,
                "avg_challenger_score": None if not scores else round(mean(scores), 6),
                "challenger_upgrade_count": changes.get("upgrade", 0) + changes.get("strong_upgrade", 0),
                "challenger_downgrade_count": changes.get("downgrade", 0) + changes.get("strong_downgrade", 0),
                "risk_caution_count": risk_tags.get("risk_caution", 0),
                "risk_watch_count": risk_tags.get("risk_watch", 0),
                "risk_clear_count": risk_tags.get("risk_clear", 0),
                "risk_out_of_scope_count": risk_tags.get("out_of_scope", 0),
            }
        )
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    admin_current_dir = Path(args.admin_current_dir)
    df = _load_joined(Path(args.db))
    admin = load_json(Path(args.admin_tracker))
    source_rows = latest_rank_rows(admin)
    champion_scored, champion_meta = train_variant(df, args.champion, args.train_end, args.asof, save_model=False)
    challenger_scored, challenger_meta = train_variant(df, args.challenger, args.train_end, args.asof, save_model=True)
    risk_scored, risk_meta = train_variant(df, args.risk_variant, args.train_end, args.asof, save_model=True)
    candidates = build_candidates(
        source_rows,
        score_map(champion_scored),
        score_map(challenger_scored),
        score_map(risk_scored),
        args.champion,
        args.challenger,
        args.risk_variant,
    )
    summary = summarize_by_model(candidates)
    token = args.asof.replace("-", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    admin_current_dir.mkdir(parents=True, exist_ok=True)
    detail_path = out_dir / f"valuation_ai_challenger_current_candidates_{token}.csv"
    summary_path = out_dir / f"valuation_ai_challenger_current_summary_{token}.csv"
    report_json_path = out_dir / f"valuation_ai_challenger_current_{token}.json"
    current_json_path = admin_current_dir / "valuation_ai_challenger_current.json"
    payload = {
        "source_name": "valuation_ai_challenger_current",
        "schema_version": "1.0",
        "visibility": "admin_only",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KR,
        "as_of_date": args.asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metric_basis": "current_candidates_shadow_overlay",
        "description": "Champion valuation AI, QM theme challenger, and QM risk tag overlay for latest model candidates.",
        "champion": champion_meta,
        "challenger": challenger_meta,
        "risk_overlay": risk_meta,
        "summary_by_model": summary,
        "state_counts": {
            "champion": Counter(r["champion_state"] for r in candidates),
            "challenger": Counter(r["challenger_state"] for r in candidates),
            "risk": Counter(r["risk_state"] for r in candidates),
            "risk_tag": Counter(r["risk_tag"] for r in candidates),
            "challenger_change": Counter(r["challenger_change_label"] for r in candidates),
        },
        "candidates": candidates,
        "outputs": {
            "detail_csv": str(detail_path),
            "summary_csv": str(summary_path),
            "report_json": str(report_json_path),
            "admin_current_json": str(current_json_path),
        },
    }
    write_csv(detail_path, candidates)
    write_csv(summary_path, summary)
    report_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    current_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "as_of_date": args.asof, "candidate_rows": len(candidates), "outputs": payload["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
