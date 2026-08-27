from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import yaml

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("build_portfolio_governance_review", HARNESS_DIR / "build_portfolio_governance_review.py")
assert SPEC is not None
GOVERNANCE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GOVERNANCE)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_db(path: Path) -> None:
    with sqlite3.connect(str(path)) as con:
        con.executescript(
            """
            create table portfolio_runs (
                run_id integer primary key,
                as_of_date text,
                generated_at text,
                market_rating text,
                selected_etf_model text,
                stock_exposure_guidance text,
                live_data_status text
            );
            create table portfolio_stock_candidates (
                run_id integer,
                ticker text,
                name text,
                model_display text,
                decision text,
                return_from_selection_pct real,
                return_from_first_portfolio_selection_pct real,
                return_5d_pct real,
                relative_return_5d_pct real,
                reactivity_rank integer,
                reactivity_score real
            );
            insert into portfolio_runs values (
                7, '2026-07-08', '2026-07-08T19:00:00+09:00', '3등급 주의 관찰',
                'S6_DEFENSIVE_V1', 'stock 0~15', 'ok'
            );
            insert into portfolio_stock_candidates values
                (7, '000001', 'A', 'S4', '검토', 4.0, 5.0, 1.0, 2.0, 1, 91),
                (7, '000002', 'B', 'S2', '검토', -8.0, -9.0, -2.0, -1.0, 2, 80);
            """
        )


def test_model_scope_registry_includes_portfolio_governance_rules() -> None:
    registry_path = Path(__file__).resolve().parents[1] / "config" / "harness" / "model_scope_registry.yaml"
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    governance = data["model_scope_registry"]["portfolio_performance_governance"]

    assert governance["final_goal"].startswith("Improve realized investment returns")
    assert "operating_ok" in governance["decision_labels"]["portfolio_status"]
    assert "blocked_needs_history" in governance["decision_labels"]["portfolio_status"]
    assert "reports/harness_portfolio_governance/<run_id>/portfolio_governance_review.json" in governance["default_report_outputs"]


def test_build_portfolio_governance_review_from_sample_payloads(tmp_path: Path) -> None:
    registry_path = tmp_path / "model_scope_registry.yaml"
    current_path = tmp_path / "investment_portfolio_latest.json"
    history_path = tmp_path / "daily_portfolio_selection_history_20260708.json"
    db_path = tmp_path / "analysis.db"
    out_dir = tmp_path / "out"

    registry_path.write_text(
        yaml.safe_dump(
            {
                "model_scope_registry": {
                    "strategy_models": {
                        "retired_excluded_from_default": ["S2_PIT_V01"],
                    }
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _write_json(
        current_path,
        {
            "as_of_date": "2026-07-08",
            "generated_at": "2026-07-08T19:00:00+09:00",
            "target_allocation": {"stock_target_pct": 10, "etf_target_pct": 72, "cash_target_pct": 18},
        },
    )
    _write_json(
        history_path,
        {
            "evaluation_date": "2026-07-08",
            "rows": [
                {
                    "rank": 1,
                    "models": "S4",
                    "return_from_portfolio_selection_pct": 3.2,
                    "relative_to_index_pct": 1.1,
                },
                {
                    "rank": 2,
                    "models": "S2",
                    "return_from_portfolio_selection_pct": -9.0,
                    "relative_to_index_pct": -4.0,
                },
                {
                    "rank": 4,
                    "models": "S2_PIT_V01",
                    "return_from_portfolio_selection_pct": -6.0,
                    "relative_to_index_pct": -3.0,
                },
            ],
        },
    )
    _build_db(db_path)

    review = GOVERNANCE.build_review(
        run_id="unit_portfolio_governance",
        asof="2026-07-08",
        registry_path=registry_path,
        portfolio_current_path=current_path,
        history_pattern=str(tmp_path / "daily_portfolio_selection_history_*.json"),
        analysis_db_path=db_path,
    )
    outputs = GOVERNANCE.write_review(review, out_dir)

    assert review["summary"]["portfolio_status"] == "improve"
    assert review["summary"]["history_row_count"] == 3
    assert review["selection_history_summary"]["avg_return_pct"] == -3.9333
    assert review["rank4_10_performance"]["count"] == 1
    assert review["top3_vs_rank4_10_gap"]["avg_return_gap_pct"] == 3.1
    assert "negative_average_portfolio_selection_return" in review["risk_flags"]
    assert "retired_or_excluded_model_exposure:S2_PIT_V01" in review["risk_flags"]
    assert [row["model"] for row in review["weak_model_combinations"]] == ["S2", "S2_PIT_V01"]
    assert [row["model"] for row in review["strong_model_combinations"]] == ["S4"]
    assert review["improvement_candidates_for_validation"]
    assert review["improvement_candidates_no_policy_change"]
    assert review["publish_allowed_with_performance_warning"] is True
    assert review["analysis_db_state"]["latest_run"]["as_of_date"] == "2026-07-08"
    assert Path(outputs["json"]).exists()
    assert Path(outputs["markdown"]).exists()
    assert "Harness Portfolio Governance Review" in Path(outputs["markdown"]).read_text(encoding="utf-8")
