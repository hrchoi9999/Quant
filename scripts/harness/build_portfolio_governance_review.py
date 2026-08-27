from __future__ import annotations

import argparse
import glob
import json
import sqlite3
from pathlib import Path
from statistics import median
from typing import Any

from harness_common import ROOT, now_stamp, read_json, read_yaml, write_json

REGISTRY_PATH = ROOT / "config" / "harness" / "model_scope_registry.yaml"
QUANT_ANALYSIS_ROOT = Path("D:/QuantAnalysis")
PORTFOLIO_CURRENT_PATH = QUANT_ANALYSIS_ROOT / "outputs" / "investment_portfolio_latest.json"
HISTORY_GLOB = str(QUANT_ANALYSIS_ROOT / "outputs" / "daily_portfolio_selection_history_*.json")
ANALYSIS_DB_PATH = QUANT_ANALYSIS_ROOT / "analysis.db"
OUT_ROOT = ROOT / "reports" / "harness_portfolio_governance"


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(median(values)), 4)


def _win_rate(values: list[float], threshold: float = 0.0) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value > threshold) / len(values) * 100.0, 2)


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [_to_float(row.get("return_from_portfolio_selection_pct")) for row in rows]
    returns = [value for value in returns if value is not None]
    relative = [_to_float(row.get("relative_to_index_pct")) for row in rows]
    relative = [value for value in relative if value is not None]
    return {
        "count": len(rows),
        "avg_return_pct": _mean(returns),
        "median_return_pct": _median(returns),
        "win_rate_pct": _win_rate(returns),
        "min_return_pct": round(min(returns), 4) if returns else None,
        "max_return_pct": round(max(returns), 4) if returns else None,
        "avg_relative_to_index_pct": _mean(relative),
        "median_relative_to_index_pct": _median(relative),
        "relative_win_rate_pct": _win_rate(relative),
    }


def _latest_history_path(pattern: str) -> Path | None:
    matches = [Path(path) for path in glob.glob(pattern)]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _load_history(path: Path | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if path is None or not path.exists():
        return {}, []
    payload = read_json(path)
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    rows = rows if isinstance(rows, list) else []
    return payload if isinstance(payload, dict) else {}, [row for row in rows if isinstance(row, dict)]


def _split_models(value: Any) -> list[str]:
    if not value:
        return []
    text = str(value).replace(",", "/")
    return [item.strip() for item in text.split("/") if item.strip()]


def _model_attribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for model in _split_models(row.get("models") or row.get("model_display") or row.get("model_display_codes")):
            buckets.setdefault(model, []).append(row)
    output: list[dict[str, Any]] = []
    for model, model_rows in sorted(buckets.items()):
        summary = _metric_summary(model_rows)
        output.append(
            {
                "model": model,
                "count": summary["count"],
                "avg_return_pct": summary["avg_return_pct"],
                "win_rate_pct": summary["win_rate_pct"],
                "avg_relative_to_index_pct": summary["avg_relative_to_index_pct"],
            }
        )
    return output


def _classify_model_combinations(model_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    weak: list[dict[str, Any]] = []
    strong: list[dict[str, Any]] = []
    for row in model_rows:
        avg_return = _to_float(row.get("avg_return_pct"))
        win_rate = _to_float(row.get("win_rate_pct"))
        avg_relative = _to_float(row.get("avg_relative_to_index_pct"))
        if avg_return is None or win_rate is None:
            continue
        if avg_return < 0 and win_rate < 40:
            weak.append(row)
        if avg_return > 0 or (avg_relative is not None and avg_relative > 0 and win_rate >= 50):
            strong.append(row)
    weak = sorted(weak, key=lambda row: (_to_float(row.get("avg_return_pct")) or 0))
    strong = sorted(strong, key=lambda row: (_to_float(row.get("avg_return_pct")) or 0), reverse=True)
    return weak, strong


def _read_latest_db_state(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"status": "missing", "path": str(db_path)}
    with sqlite3.connect(str(db_path)) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        run = cur.execute("select * from portfolio_runs order by run_id desc limit 1").fetchone()
        if run is None:
            return {"status": "empty", "path": str(db_path)}
        run_dict = dict(run)
        candidate_count = cur.execute(
            "select count(*) from portfolio_stock_candidates where run_id = ?",
            (run_dict["run_id"],),
        ).fetchone()[0]
        candidates = [
            dict(row)
            for row in cur.execute(
                """
                select ticker, name, model_display, decision, return_from_selection_pct,
                       return_from_first_portfolio_selection_pct, return_5d_pct,
                       relative_return_5d_pct, reactivity_rank, reactivity_score
                from portfolio_stock_candidates
                where run_id = ?
                order by coalesce(reactivity_rank, 999), ticker
                limit 10
                """,
                (run_dict["run_id"],),
            )
        ]
    return {
        "status": "ok",
        "path": str(db_path),
        "latest_run": {
            "run_id": run_dict.get("run_id"),
            "as_of_date": run_dict.get("as_of_date"),
            "generated_at": run_dict.get("generated_at") or run_dict.get("run_time"),
            "market_rating": run_dict.get("market_rating"),
            "selected_etf_model": run_dict.get("selected_etf_model"),
            "stock_exposure_guidance": run_dict.get("stock_exposure_guidance"),
            "live_data_status": run_dict.get("live_data_status"),
        },
        "latest_candidate_count": candidate_count,
        "latest_candidates": candidates,
    }


def _retired_models(registry: dict[str, Any]) -> set[str]:
    strategy = ((registry.get("model_scope_registry") or {}).get("strategy_models")) or {}
    return {str(item) for item in strategy.get("retired_excluded_from_default") or []}


def _risk_flags(
    *,
    history_rows: list[dict[str, Any]],
    overall: dict[str, Any],
    top3: dict[str, Any],
    model_rows: list[dict[str, Any]],
    retired: set[str],
) -> list[str]:
    flags: list[str] = []
    if not history_rows:
        flags.append("blocked_needs_selection_history")
    if (overall.get("avg_return_pct") or 0) < 0:
        flags.append("negative_average_portfolio_selection_return")
    if (overall.get("win_rate_pct") or 0) < 50:
        flags.append("low_selection_win_rate")
    if (top3.get("avg_return_pct") or 0) < 0:
        flags.append("negative_top3_average_return")
    if (overall.get("median_relative_to_index_pct") or 0) < 0:
        flags.append("negative_median_benchmark_relative_return")
    exposed_retired = sorted({row["model"] for row in model_rows if row["model"] in retired})
    if exposed_retired:
        flags.append("retired_or_excluded_model_exposure:" + ",".join(exposed_retired))
    return flags


def _portfolio_status(flags: list[str]) -> str:
    if "blocked_needs_selection_history" in flags:
        return "blocked_needs_history"
    severe = {
        "negative_average_portfolio_selection_return",
        "low_selection_win_rate",
        "negative_top3_average_return",
    }
    if severe.intersection(flags):
        return "improve"
    if flags:
        return "watch"
    return "operating_ok"


def _improvement_candidates(flags: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if "negative_top3_average_return" in flags or "low_selection_win_rate" in flags:
        candidates.append(
            {
                "candidate": "top3_selection_filter_review",
                "hypothesis": "Stricter top3 selection using reactivity, recent flow, and benchmark-relative filters may improve realized hit-rate.",
            }
        )
    if "negative_average_portfolio_selection_return" in flags:
        candidates.append(
            {
                "candidate": "weak_model_exposure_reduction_test",
                "hypothesis": "Reducing exposure to weak or REVIEW source models may reduce portfolio drag.",
            }
        )
    if "negative_median_benchmark_relative_return" in flags:
        candidates.append(
            {
                "candidate": "relative_to_index_filter_test",
                "hypothesis": "Requiring positive benchmark-relative evidence before portfolio inclusion may improve market-adjusted returns.",
            }
        )
    candidates.append(
        {
            "candidate": "portfolio_risk_metric_extension",
            "hypothesis": "Adding drawdown and turnover metrics will make allocation and candidate quality decisions more robust.",
        }
    )
    return candidates


def build_review(
    *,
    run_id: str,
    asof: str,
    registry_path: Path = REGISTRY_PATH,
    portfolio_current_path: Path = PORTFOLIO_CURRENT_PATH,
    history_pattern: str = HISTORY_GLOB,
    analysis_db_path: Path = ANALYSIS_DB_PATH,
) -> dict[str, Any]:
    registry = read_yaml(registry_path)
    portfolio_current = read_json(portfolio_current_path) if portfolio_current_path.exists() else {}
    history_path = _latest_history_path(history_pattern)
    history_payload, history_rows = _load_history(history_path)
    db_state = _read_latest_db_state(analysis_db_path)

    top3_rows = [row for row in history_rows if int(row.get("rank") or 999) <= 3]
    rank4_10_rows = [row for row in history_rows if 4 <= int(row.get("rank") or 999) <= 10]
    top10_rows = [row for row in history_rows if int(row.get("rank") or 999) <= 10]
    overall = _metric_summary(history_rows)
    top3 = _metric_summary(top3_rows)
    rank4_10 = _metric_summary(rank4_10_rows)
    top10 = _metric_summary(top10_rows)
    model_rows = _model_attribution(history_rows)
    weak_models, strong_models = _classify_model_combinations(model_rows)
    flags = _risk_flags(
        history_rows=history_rows,
        overall=overall,
        top3=top3,
        model_rows=model_rows,
        retired=_retired_models(registry),
    )
    status = _portfolio_status(flags)
    allocation = portfolio_current.get("target_allocation") or portfolio_current.get("allocation") or {}

    return {
        "source_name": "harness_portfolio_governance_review",
        "schema_version": "2026-07-10.v1",
        "run_id": run_id,
        "asof": asof,
        "generated_at": now_stamp(),
        "purpose": "Consolidate QuantAnalysis portfolio performance governance inputs. This report does not change portfolio policy or publish data.",
        "inputs": {
            "model_scope_registry": str(registry_path),
            "portfolio_current": str(portfolio_current_path),
            "selection_history": str(history_path) if history_path else None,
            "analysis_db": str(analysis_db_path),
            "portfolio_current_as_of_date": portfolio_current.get("as_of_date"),
            "selection_history_evaluation_date": history_payload.get("evaluation_date"),
            "analysis_db_latest_run_as_of_date": ((db_state.get("latest_run") or {}).get("as_of_date")),
        },
        "summary": {
            "portfolio_status": status,
            "history_row_count": len(history_rows),
            "overall_avg_return_pct": overall.get("avg_return_pct"),
            "overall_win_rate_pct": overall.get("win_rate_pct"),
            "overall_avg_relative_to_index_pct": overall.get("avg_relative_to_index_pct"),
            "top3_avg_return_pct": top3.get("avg_return_pct"),
            "top3_win_rate_pct": top3.get("win_rate_pct"),
            "rank4_10_avg_return_pct": rank4_10.get("avg_return_pct"),
            "top3_vs_rank4_10_gap_pct": round((top3.get("avg_return_pct") or 0) - (rank4_10.get("avg_return_pct") or 0), 4),
            "risk_flag_count": len(flags),
            "improvement_candidate_count": len(_improvement_candidates(flags)),
        },
        "current_portfolio_status": {
            "as_of_date": portfolio_current.get("as_of_date"),
            "generated_at": portfolio_current.get("generated_at"),
            "market_rating": portfolio_current.get("market_risk", {}).get("rating") or ((db_state.get("latest_run") or {}).get("market_rating")),
            "stock_target_pct": allocation.get("stock_target_pct"),
            "etf_target_pct": allocation.get("etf_target_pct"),
            "cash_target_pct": allocation.get("cash_target_pct"),
            "selected_etf_model": ((db_state.get("latest_run") or {}).get("selected_etf_model")),
        },
        "selection_history_summary": overall,
        "top10_performance": top10,
        "top3_performance": top3,
        "rank4_10_performance": rank4_10,
        "top3_vs_rank4_10_gap": {
            "avg_return_gap_pct": round((top3.get("avg_return_pct") or 0) - (rank4_10.get("avg_return_pct") or 0), 4),
            "win_rate_gap_pctp": round((top3.get("win_rate_pct") or 0) - (rank4_10.get("win_rate_pct") or 0), 4),
            "benchmark_relative_gap_pct": round(
                (top3.get("avg_relative_to_index_pct") or 0) - (rank4_10.get("avg_relative_to_index_pct") or 0),
                4,
            ),
        },
        "benchmark_relative_performance": {
            "avg_relative_to_index_pct": overall.get("avg_relative_to_index_pct"),
            "median_relative_to_index_pct": overall.get("median_relative_to_index_pct"),
            "relative_win_rate_pct": overall.get("relative_win_rate_pct"),
        },
        "model_attribution_summary": model_rows,
        "weak_model_combinations": weak_models,
        "strong_model_combinations": strong_models,
        "analysis_db_state": db_state,
        "risk_flags": flags,
        "policy_change_required": "no_direct_change_by_harness",
        "improvement_candidates_for_validation": _improvement_candidates(flags),
        "improvement_candidates_no_policy_change": _improvement_candidates(flags),
        "publish_allowed_with_performance_warning": status in {"watch", "improve"},
        "handoff_to_weekend_research": [
            "Ask Quant Model and QuantAnalysis to validate weak-model exposure reduction before any operational policy change.",
            "Ask QuantAnalysis to add or verify drawdown/turnover attribution for portfolio candidates.",
            "Ask weekend WE01 to compare S4/S5/S6-centered portfolio candidates against current top10 selection rules.",
        ],
        "known_issues": flags if flags else ["none"],
    }


def render_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# Harness Portfolio Governance Review",
        "",
        f"- run_id: `{review['run_id']}`",
        f"- asof: `{review['asof']}`",
        f"- generated_at: `{review['generated_at']}`",
        "- state_change: `not_performed`",
        "",
        "## Summary",
        "",
    ]
    for key, value in (review.get("summary") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Performance", ""])
    for name in (
        "selection_history_summary",
        "top10_performance",
        "top3_performance",
        "rank4_10_performance",
        "top3_vs_rank4_10_gap",
        "benchmark_relative_performance",
    ):
        lines.append(f"### {name}")
        for key, value in (review.get(name) or {}).items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    lines.extend(["## Model Attribution", "", "| model | count | avg return | win rate | avg relative |", "|---|---:|---:|---:|---:|"])
    for row in review.get("model_attribution_summary") or []:
        lines.append(
            f"| {row.get('model')} | {row.get('count')} | {row.get('avg_return_pct')} | "
            f"{row.get('win_rate_pct')} | {row.get('avg_relative_to_index_pct')} |"
        )
    lines.extend(["", "## Weak Model Combinations", "", "| model | count | avg return | win rate | avg relative |", "|---|---:|---:|---:|---:|"])
    for row in review.get("weak_model_combinations") or []:
        lines.append(
            f"| {row.get('model')} | {row.get('count')} | {row.get('avg_return_pct')} | "
            f"{row.get('win_rate_pct')} | {row.get('avg_relative_to_index_pct')} |"
        )
    lines.extend(["", "## Strong Model Combinations", "", "| model | count | avg return | win rate | avg relative |", "|---|---:|---:|---:|---:|"])
    for row in review.get("strong_model_combinations") or []:
        lines.append(
            f"| {row.get('model')} | {row.get('count')} | {row.get('avg_return_pct')} | "
            f"{row.get('win_rate_pct')} | {row.get('avg_relative_to_index_pct')} |"
        )
    lines.extend(["", "## Improvement Candidates", ""])
    for item in review.get("improvement_candidates_for_validation") or []:
        lines.append(f"- {item.get('candidate')}: {item.get('hypothesis')}")
    lines.extend(["", "## Known Issues", ""])
    for item in review.get("known_issues") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_review(review: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "portfolio_governance_review.json"
    md_path = out_dir / "portfolio_governance_review.md"
    write_json(json_path, review)
    md_path.write_text(render_markdown(review), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build harness portfolio performance governance review.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    parser.add_argument("--portfolio-current", default=str(PORTFOLIO_CURRENT_PATH))
    parser.add_argument("--history-pattern", default=HISTORY_GLOB)
    parser.add_argument("--analysis-db", default=str(ANALYSIS_DB_PATH))
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()
    review = build_review(
        run_id=args.run_id,
        asof=args.asof,
        registry_path=Path(args.registry),
        portfolio_current_path=Path(args.portfolio_current),
        history_pattern=args.history_pattern,
        analysis_db_path=Path(args.analysis_db),
    )
    out_dir = Path(args.out_dir) if args.out_dir else OUT_ROOT / args.run_id
    outputs = write_review(review, out_dir)
    print(json.dumps({"status": "ok", "outputs": outputs, "summary": review["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
