"""Explicit 2026-09-13 scope; never replace missing AI inputs with values."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import re
from pathlib import Path

REVISION = "AI_OUTPUT_NONBLOCKING_20260913"
COMPLETION_BASIS = "user_revised_non_ai_scope"
MODELS = ("S2", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5", "S6")
DEFERRED_MODELS = ("T-STOCK-V01", "T-ETF-V01")
T_CURRENT = "quantservice_tseries_discovery.json"
T_HISTORY = "quantservice_tseries_discovery_history.json"


def admin_preserved_hash(payload: dict) -> str:
    """Hash every field outside the explicitly refreshed internal-model sections."""
    kept = copy.deepcopy(payload)
    for key in ("as_of_date", "generated_at", "internal_models", "scope_revision",
                "completion_basis", "non_ai_admin"):
        kept.pop(key, None)
    for key in ("summary", "model_performance_summary", "actual_live_performance_summary"):
        kept[key].pop("internal_models", None)
    kept["weekly_rankings"].pop("internal_models", None)
    kept["weekly_rankings"]["summary"].pop("internal_models", None)
    for key in ("internal_latest_event_date", "internal_latest_week_end"):
        kept["freshness"].pop(key, None)
    raw = json.dumps(kept, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def admin_scope_errors(payload: dict, asof: str) -> list[str]:
    """Shared producer/consumer checks; missing or stale internal models still fail."""
    errors = []
    meta = payload.get("non_ai_admin", {})
    if (payload.get("scope_revision") != REVISION
            or payload.get("completion_basis") != COMPLETION_BASIS
            or payload.get("visibility") != "admin_only"
            or payload.get("schema_version") != "v2"
            or payload.get("as_of_date") != asof):
        errors.append("non-AI admin identity/asof mismatch")
    try:
        if admin_preserved_hash(payload) != meta.get("preserved_sections_sha256"):
            errors.append("preserved admin sections changed")
        runs = meta["internal_source_runs"]
        from src.quant2.operations.standalone_retirement import active

        expected_models = {model for model in MODELS if active(model)}
        if len(runs) != len(expected_models) or {r["model_code"] for r in runs} != expected_models:
            errors.append("internal source model coverage mismatch")
        if any(r["asof_date"] != asof or r["data_asof"] != asof or r["end_date"] != asof
               or not r["run_id"] for r in runs):
            errors.append("stale internal source run")
        if meta["preserved_asof"] > asof or not meta["preserved_asof"]:
            errors.append("invalid preserved asof")
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append("invalid non-AI admin preservation evidence")
    return errors


def enabled(revision: str | None) -> bool:
    if revision not in (None, "", REVISION):
        raise ValueError("unknown non-AI scope revision")
    return revision == REVISION


def add_argument(parser) -> None:
    parser.add_argument("--scope-revision", choices=[REVISION], default=None)


def preservation(path: Path) -> dict:
    """Identify a retained artifact without rewriting its original date or bytes."""
    if not path.exists():
        return {"path": str(path), "sha256": None, "source_asof": None, "status": "ai_deferred_missing"}
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "source_asof": value.get("as_of_date", value.get("asof")), "status": "ai_deferred_preserved"}


def public_preservation(path: Path) -> dict:
    """Expose deferred status without private filesystem evidence."""
    if path.name not in {T_CURRENT, T_HISTORY}:
        raise ValueError("unknown public deferred component")
    retained = preservation(path)
    return {"component": path.name, "status": retained["status"],
            "source_asof": retained["source_asof"]}


def validate_authorization(path: Path, *, asof: str, root: Path) -> dict:
    body = json.loads(path.read_text(encoding="utf-8"))
    if (body.get("scope_revision") != REVISION or body.get("completion_basis") != COMPLETION_BASIS
            or body.get("data_asof") != asof or body.get("stage_id") != "WD04_QUANT_REAR"):
        raise ValueError("explicit same-run WD04 non-AI scope contract required")
    source = body.get("authorization", {})
    expected = root / "quant2/docs/Quant2_5/Q25_STAGE_1_5_USER_AUTHORIZATION_20260910.md"
    if Path(source.get("path", "")).resolve() != expected.resolve():
        raise ValueError("current approved authorization document required")
    raw = expected.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source.get("sha256"):
        raise ValueError("authorization changed; rebind the reviewed scope")
    if "AI 산출물 비차단 전환" not in raw.decode("utf-8-sig"):
        raise ValueError("non-AI authorization missing")
    if (body.get("run_id"), asof) != ("20260911_prompt_weekday_data_20260910", "2026-09-10"):
        _validate_cycle_binding(body, root, asof)
    return body


def _validate_cycle_binding(body: dict, root: Path, asof: str) -> None:
    """Bind subsequent approved cycles to their live Harness stage and input target."""
    run_id = body.get("run_id", "")
    if not re.fullmatch(r"\d{8}_prompt_weekday_data_\d{8}(?:_v[1-9]\d*)?", run_id):
        raise ValueError("explicit same-run WD04 non-AI scope contract required")
    run_root = root / "reports/prompt_handoff_runs" / run_id

    def pinned(name: str, expected: Path) -> dict:
        ref = body.get(name, {})
        if Path(ref.get("path", "")).resolve() != expected.resolve():
            raise ValueError(f"same-run {name} path required")
        raw = expected.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref.get("sha256"):
            raise ValueError(f"same-run {name} hash changed")
        return json.loads(raw.decode("utf-8-sig"))

    state = pinned("harness_state", run_root / "prompt_cycle_state.json")
    command = pinned("collection_command", run_root / "collection_command.json")
    stage = next((s for s in state.get("stages", []) if s.get("stage_id") == "WD04_QUANT_REAR"), {})
    binding = state.get("input_target_binding", {})
    execution = state.get("execution_scope", {})
    if (state.get("run_id") != run_id or state.get("cycle_type") != "weekday"
            or state.get("status") != "in_progress" or stage.get("status") != "in_progress"
            or binding.get("run_id") != run_id or binding.get("data_asof") != asof
            or execution.get("enabled") is not True or execution.get("revision") != REVISION
            or command.get("run_id") != run_id or command.get("data_asof") != asof
            or command.get("actor") != "USER" or command.get("action") != "COLLECT_DATA"
            or command.get("classification") != "ACTUAL_USER_COMMAND_BINDING"
            or state.get("collection_command_ref", {}).get("sha256") != body["collection_command"]["sha256"]):
        raise ValueError("explicit same-run active WD04 and exact input target required")
    report = Path(binding.get("report_file", ""))
    if (report.resolve() != (run_root / "WD01_QUANT_FRONT/thread_report.md").resolve()
            or hashlib.sha256(report.read_bytes()).hexdigest() != binding.get("report_sha256")):
        raise ValueError("same-run WD01 input binding changed")


def market_status(asof: str, handoff_dir: Path) -> dict:
    """Require actual exact-date non-AI state; legacy aggregate forecast readiness is separate."""
    path = handoff_dir / "market_model_input_daily_current.csv"
    result = {"scope_revision": REVISION, "target_asof": asof, "path": str(path),
              "ready": False, "forecast_requirement": "ai_deferred", "errors": []}
    if not path.exists():
        result["errors"].append("non-AI market input missing")
        return result
    result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    matches = {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("asof_date") != asof or row.get("forecast_horizon") != "20d":
                    continue
                scope = row.get("market_scope")
                if scope not in {"ALL", "KOSPI", "KOSDAQ"}:
                    continue
                if scope in matches:
                    result["errors"].append(f"duplicate non-AI state row: {scope}")
                score = float(row.get("market_state_score", ""))
                label = row.get("market_state_label")
                if not math.isfinite(score) or label not in {"strong_up", "up", "neutral", "down", "strong_down"}:
                    result["errors"].append(f"invalid non-AI state: {scope}")
                matches[scope] = {"asof_date": asof, "market_state_label": label, "market_state_score": score}
    except (ValueError, OSError, csv.Error) as exc:
        result["errors"].append(str(exc))
    if set(matches) != {"ALL", "KOSPI", "KOSDAQ"}:
        result["errors"].append("exact-date non-AI ALL/KOSPI/KOSDAQ states required")
    result["states"] = matches
    result["ready"] = not result["errors"]
    return result


def partition_models(commands: list[list[str]], root: Path) -> tuple[list[list[str]], list[dict]]:
    """Only inspected model entry points; an unknown entry is deferred individually."""
    allowed = {
        str((root / name).resolve()) for name in (
            "src/experiments/run_s3_trend_hold_top20.py",
            "src/experiments/run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py",
            "scripts/run_s3_accel_v01_operational_backtest.py",
            "src/backtest/run_backtest_s4_risk_on_allocation.py",
            "src/backtest/run_backtest_s5_neutral_allocation.py",
            "src/backtest/run_backtest_s6_defensive_allocation.py",
        )
    }
    kept, deferred = [], []
    for cmd in commands:
        module = len(cmd) > 3 and cmd[1:3] == ["-m", "src.backtest.run_backtest_v5"] and "--s2-refactor" in cmd
        script = len(cmd) > 1 and str(Path(cmd[1]).resolve()) in allowed
        if module or script:
            kept.append(cmd)
        else:
            deferred.append({"component": " ".join(cmd[1:3]),
                             "reason": "ai_deferred: actual input dependency not reviewed",
                             "source_asof": None, "evidence_files": [str(root / "src/quant_service/run_daily_quant_pipeline.py")]})
    return kept, deferred
