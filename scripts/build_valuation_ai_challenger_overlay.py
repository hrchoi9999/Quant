# build_valuation_ai_challenger_overlay.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_valuation_ai_feature_ablation import _feature_set, _fit_regressor, _load_joined
from src.models.valuation_ai.config import MODEL_CODE, OUT_DB, REPORT_DIR
from src.models.valuation_ai.rule_score_engine import build_rule_scores


ADMIN_TRACKER = ROOT / "service_platform" / "web" / "admin_data" / "current" / "admin_new_entry_tracker.json"
FAVORABLE_STATES = {"UNDERVALUED", "FAIR"}
CAUTION_STATES = {"OVERHEATED", "AVOID"}
STATE_RANK = {
    "OUT_OF_SCOPE_OR_MISSING": -1,
    "AVOID": 0,
    "OVERHEATED": 1,
    "FAIR": 2,
    "UNDERVALUED": 3,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare valuation AI champion/challenger overlays on latest model candidates.")
    parser.add_argument("--db", default=str(OUT_DB))
    parser.add_argument("--admin-tracker", default=str(ADMIN_TRACKER))
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--valid-end", default="2025-03-31")
    parser.add_argument("--champion", default="LOCAL_MARKET")
    parser.add_argument("--challengers", nargs="*", default=["QM_MARKET_THEME", "QM_MARKET_RISK", "QM_FULL"])
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_rank_rows(admin: dict[str, Any]) -> list[dict[str, Any]]:
    weekly = admin.get("weekly_rankings", {})
    out: list[dict[str, Any]] = []
    for scope_key in ["user_models", "internal_models", "tseries_models"]:
        for row in weekly.get(scope_key, []):
            if row.get("is_latest_snapshot") is True:
                model_key = row.get("model_code") or row.get("service_profile") or row.get("model_key")
                ticker = str(row.get("security_code", "")).zfill(6)
                if not ticker:
                    continue
                out.append(
                    {
                        "scope": row.get("scope") or scope_key.replace("_models", ""),
                        "source_table": f"weekly_rankings.{scope_key}",
                        "model_code": model_key,
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


def _latest_features(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    frame = df[df["asof_date"] <= pd.Timestamp(asof)].copy()
    if frame.empty:
        raise SystemExit(f"no features on or before {asof}")
    latest = frame["asof_date"].max()
    return frame[frame["asof_date"].eq(latest)].copy()


def _train_and_score_variant(df: pd.DataFrame, variant: str, train_end: str, valid_start: str, valid_end: str, asof: str) -> pd.DataFrame:
    feature_columns, categorical_columns, _ = _feature_set(variant)
    labeled = df[df["fwd_excess_ret_12m"].notna()].sort_values("asof_date").copy()
    train = labeled[labeled["asof_date"] <= pd.Timestamp(train_end)].copy()
    if train.empty:
        raise SystemExit(f"empty training rows for {variant}")
    model = _fit_regressor(train, [c for c in feature_columns if c in df.columns], [c for c in categorical_columns if c in df.columns])
    features = _latest_features(df, asof)
    pred = pd.Series(model.predict(features), index=features.index)
    scored = build_rule_scores(features, pred)
    scored["ticker"] = scored["ticker"].astype(str).str.zfill(6)
    scored["variant"] = variant
    keep = [
        "variant",
        "asof_date",
        "ticker",
        "name",
        "valuation_ai_score",
        "valuation_state",
        "predicted_excess_return_12m",
        "expected_return_score",
        "valuation_safety_score",
        "growth_quality_score",
        "revision_momentum_score",
        "downside_safety_score",
        "downside_risk_score",
        "confidence_score",
        "qm_market_state_label",
        "qm_market_state_score",
        "qm_quantmarket_theme_bucket",
        "qm_theme_momentum_score",
        "qm_theme_rotation_score",
        "qm_theme_mapping_confidence",
        "qm_risk_score",
        "qm_market_stress_score",
        "qm_volatility_regime_label",
    ]
    return scored[[c for c in keep if c in scored.columns]].copy()


def _score_map(scores: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in scores.to_dict(orient="records"):
        out[str(row["ticker"]).zfill(6)] = row
    return out


def _to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _state_delta(champion_state: str, challenger_state: str) -> int:
    return STATE_RANK.get(str(challenger_state), -1) - STATE_RANK.get(str(champion_state), -1)


def _change_label(delta: int) -> str:
    if delta >= 2:
        return "strong_upgrade"
    if delta == 1:
        return "upgrade"
    if delta == 0:
        return "same"
    if delta == -1:
        return "downgrade"
    return "strong_downgrade"


def build_overlay(rows: list[dict[str, Any]], score_by_variant: dict[str, dict[str, dict[str, Any]]], champion: str, variants: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for base in rows:
        ticker = base["security_code"]
        champion_score = score_by_variant[champion].get(ticker)
        champion_state = str(champion_score.get("valuation_state")) if champion_score else "OUT_OF_SCOPE_OR_MISSING"
        champion_value = _to_float(champion_score.get("valuation_ai_score")) if champion_score else None
        for variant in variants:
            score = score_by_variant[variant].get(ticker)
            state = str(score.get("valuation_state")) if score else "OUT_OF_SCOPE_OR_MISSING"
            value = _to_float(score.get("valuation_ai_score")) if score else None
            delta = _state_delta(champion_state, state)
            out.append(
                {
                    **base,
                    "valuation_variant": variant,
                    "champion_variant": champion,
                    "champion_state": champion_state,
                    "champion_score": None if champion_value is None else round(champion_value, 6),
                    "variant_state": state,
                    "variant_score": None if value is None else round(value, 6),
                    "score_delta_vs_champion": None if value is None or champion_value is None else round(value - champion_value, 6),
                    "state_delta_vs_champion": delta,
                    "state_change_label": _change_label(delta),
                    "predicted_excess_return_12m": None if not score else round(_to_float(score.get("predicted_excess_return_12m")) or 0.0, 6),
                    "qm_market_state_label": score.get("qm_market_state_label") if score else None,
                    "qm_quantmarket_theme_bucket": score.get("qm_quantmarket_theme_bucket") if score else None,
                    "qm_theme_momentum_score": None if not score else _to_float(score.get("qm_theme_momentum_score")),
                    "qm_theme_rotation_score": None if not score else _to_float(score.get("qm_theme_rotation_score")),
                    "qm_theme_mapping_confidence": None if not score else _to_float(score.get("qm_theme_mapping_confidence")),
                    "qm_risk_score": None if not score else _to_float(score.get("qm_risk_score")),
                    "qm_market_stress_score": None if not score else _to_float(score.get("qm_market_stress_score")),
                }
            )
    return out


def summarize(detail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in detail:
        grouped[(row["valuation_variant"], row["scope"], row["model_code"])].append(row)
    out: list[dict[str, Any]] = []
    for (variant, scope, model), rows in sorted(grouped.items()):
        state_counts = Counter(r["variant_state"] for r in rows)
        change_counts = Counter(r["state_change_label"] for r in rows)
        scores = [_to_float(r.get("variant_score")) for r in rows]
        scores = [v for v in scores if v is not None]
        favorable = sum(state_counts.get(s, 0) for s in FAVORABLE_STATES)
        caution = sum(state_counts.get(s, 0) for s in CAUTION_STATES)
        out.append(
            {
                "valuation_variant": variant,
                "scope": scope,
                "model_code": model,
                "candidate_count": len(rows),
                "favorable_count": favorable,
                "favorable_rate": round(favorable / len(rows), 6) if rows else None,
                "caution_count": caution,
                "caution_rate": round(caution / len(rows), 6) if rows else None,
                "avg_variant_score": None if not scores else round(mean(scores), 6),
                "undervalued": state_counts.get("UNDERVALUED", 0),
                "fair": state_counts.get("FAIR", 0),
                "overheated": state_counts.get("OVERHEATED", 0),
                "avoid": state_counts.get("AVOID", 0),
                "out_of_scope_or_missing": state_counts.get("OUT_OF_SCOPE_OR_MISSING", 0),
                "upgrade": change_counts.get("upgrade", 0),
                "strong_upgrade": change_counts.get("strong_upgrade", 0),
                "downgrade": change_counts.get("downgrade", 0),
                "strong_downgrade": change_counts.get("strong_downgrade", 0),
                "same": change_counts.get("same", 0),
            }
        )
    return out


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


def write_md(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary_by_model"]
    lines = [
        f"# {MODEL_CODE} Challenger Overlay Analysis - {payload['as_of_date']}",
        "",
        f"- champion: `{payload['champion_variant']}`",
        f"- challengers: `{', '.join(payload['challenger_variants'])}`",
        f"- candidate rows: `{payload['candidate_rows']}`",
        "",
        "## Summary By Model",
        "",
        "| variant | scope | model | candidates | favorable | caution | avg score | upgrade | downgrade |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            "| {valuation_variant} | {scope} | {model_code} | {candidate_count} | {favorable_count} | {caution_count} | {avg_variant_score} | {up} | {down} |".format(
                valuation_variant=row["valuation_variant"],
                scope=row["scope"],
                model_code=row["model_code"],
                candidate_count=row["candidate_count"],
                favorable_count=row["favorable_count"],
                caution_count=row["caution_count"],
                avg_variant_score=row["avg_variant_score"],
                up=row["upgrade"] + row["strong_upgrade"],
                down=row["downgrade"] + row["strong_downgrade"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `upgrade` means the challenger assigns a better valuation state than the champion.",
            "- `downgrade` means the challenger assigns a worse valuation state than the champion.",
            "- This is not a replacement decision; it is a current overlay sensitivity check.",
            "- Use this with ablation performance before promoting a challenger to shadow operation.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    variants = [args.champion, *args.challengers]
    df = _load_joined(Path(args.db))
    admin = load_json(Path(args.admin_tracker))
    candidate_rows = latest_rank_rows(admin)
    scores = {
        variant: _score_map(_train_and_score_variant(df, variant, args.train_end, args.valid_start, args.valid_end, args.asof))
        for variant in variants
    }
    detail = build_overlay(candidate_rows, scores, args.champion, args.challengers)
    summary = summarize(detail)
    token = args.asof.replace("-", "")
    detail_path = out_dir / f"valuation_ai_challenger_overlay_detail_{token}.csv"
    summary_path = out_dir / f"valuation_ai_challenger_overlay_summary_{token}.csv"
    json_path = out_dir / f"valuation_ai_challenger_overlay_{token}.json"
    md_path = out_dir / f"valuation_ai_challenger_overlay_{token}.md"
    payload = {
        "source_name": "valuation_ai_challenger_overlay",
        "schema_version": "1.0",
        "model_code": MODEL_CODE,
        "as_of_date": args.asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "champion_variant": args.champion,
        "challenger_variants": args.challengers,
        "candidate_rows": len(candidate_rows),
        "summary_by_model": summary,
        "outputs": {
            "detail_csv": str(detail_path),
            "summary_csv": str(summary_path),
            "json": str(json_path),
            "md": str(md_path),
        },
    }
    write_csv(detail_path, detail)
    write_csv(summary_path, summary)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(md_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
