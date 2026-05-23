from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADMIN_TRACKER = ROOT / "service_platform" / "web" / "admin_data" / "current" / "admin_new_entry_tracker.json"
VALUATION_REPORT_DIR = ROOT / "reports" / "valuation_ai"
VALUATION_SCORE_PATTERN = "valuation_scores_*.csv"

FAVORABLE_STATES = {"UNDERVALUED", "FAIR"}
CAUTION_STATES = {"OVERHEATED", "AVOID"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Join AI-GROWTH-VALUATION-V01 scores to latest S/T/I/user model candidates.",
    )
    parser.add_argument("--asof", help="Asof date such as 2026-05-04. Defaults to latest valuation score file.")
    parser.add_argument("--admin-tracker", default=str(ADMIN_TRACKER))
    parser.add_argument("--score-csv", help="Explicit valuation_scores_YYYYMMDD.csv path.")
    parser.add_argument("--out-dir", default=str(VALUATION_REPORT_DIR))
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def safe_round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def latest_score_file(out_dir: Path, asof: str | None) -> Path:
    if asof:
        compact = asof.replace("-", "")
        candidate = out_dir / f"valuation_scores_{compact}.csv"
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"valuation score file not found for asof={asof}: {candidate}")
    files = sorted(out_dir.glob(VALUATION_SCORE_PATTERN), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"no {VALUATION_SCORE_PATTERN} files under {out_dir}")
    return files[0]


def load_valuation_scores(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    scores: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker", "")).zfill(6)
        if ticker:
            scores[ticker] = row
    return scores


def latest_rank_rows(admin: dict[str, Any]) -> list[dict[str, Any]]:
    weekly = admin.get("weekly_rankings", {})
    out: list[dict[str, Any]] = []
    for scope_key in ["user_models", "internal_models", "tseries_models"]:
        for row in weekly.get(scope_key, []):
            if row.get("is_latest_snapshot") is True:
                model_key = row.get("model_code") or row.get("service_profile") or row.get("model_key")
                out.append(
                    {
                        "scope": row.get("scope") or scope_key.replace("_models", ""),
                        "source_table": f"weekly_rankings.{scope_key}",
                        "model_code": model_key,
                        "service_profile": row.get("service_profile"),
                        "week_end": row.get("week_end"),
                        "snapshot_date": row.get("snapshot_date"),
                        "security_code": str(row.get("security_code", "")).zfill(6),
                        "display_name": row.get("display_name"),
                        "rank_no": row.get("rank_no"),
                        "score": row.get("score"),
                        "score_basis": row.get("score_basis"),
                        "weight": row.get("weight"),
                        "candidate_bucket": row.get("candidate_bucket"),
                        "stage1_prob": row.get("stage1_prob"),
                        "stage2_prob": row.get("stage2_prob"),
                    }
                )
    return out


def enrich_rows(rows: list[dict[str, Any]], scores: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        ticker = row["security_code"]
        val = scores.get(ticker)
        if val:
            state = val.get("valuation_state")
            ai_score = to_float(val.get("valuation_ai_score"))
            coverage_status = "covered"
        else:
            state = "OUT_OF_SCOPE_OR_MISSING"
            ai_score = None
            coverage_status = "out_of_scope_or_missing"
        enriched.append(
            {
                **row,
                "valuation_coverage_status": coverage_status,
                "valuation_ai_score": safe_round(ai_score, 6),
                "valuation_state": state,
                "market_regime": safe_round(to_float(val.get("market_regime")) if val else None),
                "market_regime_label": val.get("market_regime_label") if val else None,
                "market_ret_1m": safe_round(to_float(val.get("market_ret_1m")) if val else None),
                "market_ret_3m": safe_round(to_float(val.get("market_ret_3m")) if val else None),
                "market_ret_6m": safe_round(to_float(val.get("market_ret_6m")) if val else None),
                "market_breadth_ret_pos_1m": safe_round(to_float(val.get("market_breadth_ret_pos_1m")) if val else None),
                "market_breadth_above_sma60": safe_round(to_float(val.get("market_breadth_above_sma60")) if val else None),
                "market_breadth_above_sma120": safe_round(to_float(val.get("market_breadth_above_sma120")) if val else None),
                "market_context_available": to_float(val.get("market_context_available")) if val else None,
                "predicted_excess_return_12m": safe_round(to_float(val.get("predicted_excess_return_12m")) if val else None),
                "current_valuation_percentile": safe_round(to_float(val.get("current_valuation_percentile")) if val else None),
                "implied_growth_pressure": safe_round(to_float(val.get("implied_growth_pressure")) if val else None),
                "valuation_growth_gap": safe_round(to_float(val.get("valuation_growth_gap")) if val else None),
                "outperform_prob": safe_round(to_float(val.get("outperform_prob")) if val else None),
                "underperform_prob": safe_round(to_float(val.get("underperform_prob")) if val else None),
                "overheated_prob": safe_round(to_float(val.get("overheated_prob")) if val else None),
                "reason_codes": val.get("reason_codes") if val else None,
            }
        )
    return enriched


def summarize(enriched: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        grouped[(row["scope"], row["model_code"])].append(row)

    summary: list[dict[str, Any]] = []
    for (scope, model), rows in sorted(grouped.items()):
        covered = [r for r in rows if r["valuation_coverage_status"] == "covered"]
        scores = [to_float(r.get("valuation_ai_score")) for r in covered]
        scores = [v for v in scores if v is not None]
        states = Counter(r["valuation_state"] for r in rows)
        favorable = sum(states.get(s, 0) for s in FAVORABLE_STATES)
        caution = sum(states.get(s, 0) for s in CAUTION_STATES)
        summary.append(
            {
                "scope": scope,
                "model_code": model,
                "candidate_count": len(rows),
                "valuation_covered_count": len(covered),
                "coverage_rate": safe_round(len(covered) / len(rows) if rows else None, 4),
                "favorable_count": favorable,
                "favorable_rate_on_covered": safe_round(favorable / len(covered) if covered else None, 4),
                "caution_count": caution,
                "caution_rate_on_covered": safe_round(caution / len(covered) if covered else None, 4),
                "avg_valuation_ai_score": safe_round(mean(scores) if scores else None, 4),
                "median_valuation_ai_score": safe_round(median(scores) if scores else None, 4),
                "undervalued": states.get("UNDERVALUED", 0),
                "fair": states.get("FAIR", 0),
                "overheated": states.get("OVERHEATED", 0),
                "avoid": states.get("AVOID", 0),
                "out_of_scope_or_missing": states.get("OUT_OF_SCOPE_OR_MISSING", 0),
            }
        )
    return summary


def state_summary(enriched: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        grouped[row["valuation_state"]].append(row)
    out = []
    for state, rows in sorted(grouped.items()):
        scores = [to_float(r.get("valuation_ai_score")) for r in rows]
        scores = [v for v in scores if v is not None]
        out.append(
            {
                "valuation_state": state,
                "candidate_count": len(rows),
                "avg_valuation_ai_score": safe_round(mean(scores) if scores else None, 4),
                "models_count": len({(r["scope"], r["model_code"]) for r in rows}),
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
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_md(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary_by_model"]
    state = payload["summary_by_state"]
    lines = [
        f"# AI-GROWTH-VALUATION-V01 Overlay Validation - {payload['as_of_date']}",
        "",
        "## Scope",
        "",
        "- Source candidates: latest weekly rankings from user, internal, and T-series models.",
        "- Valuation source: latest `valuation_scores_YYYYMMDD.csv`.",
        "- Growth stock flags are intentionally excluded from this validation.",
        "- ETF rows are treated as out-of-scope for this stock valuation model.",
        "",
        "## Summary By Model",
        "",
        "| scope | model | candidates | covered | favorable | caution | avg score | UNDER | FAIR | OVER | AVOID | out of scope |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            "| {scope} | {model_code} | {candidate_count} | {valuation_covered_count} | "
            "{favorable_count} | {caution_count} | {avg_valuation_ai_score} | "
            "{undervalued} | {fair} | {overheated} | {avoid} | {out_of_scope_or_missing} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Summary By Valuation State",
            "",
            "| state | candidates | avg score | model groups |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in state:
        lines.append(
            "| {valuation_state} | {candidate_count} | {avg_valuation_ai_score} | {models_count} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `UNDERVALUED` and `FAIR` are favorable valuation overlay states.",
            "- `OVERHEATED` and `AVOID` are caution states. They do not automatically remove a candidate yet.",
            "- This is a current cross-sectional overlay validation, not a live performance verdict.",
            "- The next step is live-only shadow tracking by valuation state.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    score_path = Path(args.score_csv) if args.score_csv else latest_score_file(out_dir, args.asof)
    asof = args.asof or score_path.stem.replace("valuation_scores_", "")
    if len(asof) == 8 and asof.isdigit():
        asof = f"{asof[:4]}-{asof[4:6]}-{asof[6:]}"

    admin = load_json(Path(args.admin_tracker))
    scores = load_valuation_scores(score_path)
    rows = latest_rank_rows(admin)
    enriched = enrich_rows(rows, scores)
    summary = summarize(enriched)
    state = state_summary(enriched)

    compact = asof.replace("-", "")
    detail_path = out_dir / f"valuation_overlay_current_candidates_{compact}.csv"
    summary_path = out_dir / f"valuation_overlay_summary_by_model_{compact}.csv"
    state_path = out_dir / f"valuation_overlay_summary_by_state_{compact}.csv"
    json_path = out_dir / f"valuation_overlay_validation_{compact}.json"
    md_path = out_dir / f"valuation_overlay_validation_{compact}.md"

    payload = {
        "source_name": "valuation_ai_overlay_validation",
        "schema_version": "1.0",
        "as_of_date": asof,
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "model_code": "AI-GROWTH-VALUATION-V01",
        "admin_tracker": str(Path(args.admin_tracker)),
        "score_csv": str(score_path),
        "summary_by_model": summary,
        "summary_by_state": state,
    }

    write_csv(detail_path, enriched)
    write_csv(summary_path, summary)
    write_csv(state_path, state)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(md_path, payload)

    print(json.dumps({"as_of_date": asof, "rows": len(enriched), "summary_rows": len(summary), "outputs": [str(detail_path), str(summary_path), str(state_path), str(json_path), str(md_path)]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
