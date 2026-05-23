from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\Quant")
ADMIN_CURRENT = ROOT / "service_platform" / "web" / "admin_data" / "current"
OUT_PATH = ADMIN_CURRENT / "internal_model_validation_current.json"
HISTORY_PATH = ADMIN_CURRENT / "internal_model_validation_history.json"
SNAPSHOT_DIR = ROOT / "reports" / "internal_model_validation"


MODEL_TARGETS: dict[str, dict[str, Any]] = {
    "default": {
        "target_profile": "standard_internal",
        "primary_metric": "total_validation_score",
        "min_backtest_1y_return": 0.30,
        "min_backtest_sharpe_1y": 1.4,
        "max_backtest_mdd_1y": -0.22,
        "min_live_1m_avg_return": 0.02,
        "min_live_1m_win_rate": 0.55,
        "min_live_1m_sample_count": 10,
        "min_live_current_avg_return": 0.0,
        "min_model_value_score": 55.0,
        "min_total_validation_score": 60.0,
    },
    "stable": {
        "target_profile": "stable_defensive",
        "primary_metric": "risk_controlled_return_and_drawdown",
        "min_backtest_1y_return": 0.10,
        "min_backtest_sharpe_1y": 1.0,
        "max_backtest_mdd_1y": -0.12,
        "min_live_1m_avg_return": 0.005,
        "min_live_1m_win_rate": 0.52,
        "min_live_1m_sample_count": 10,
        "min_live_current_avg_return": 0.0,
        "min_model_value_score": 50.0,
        "min_total_validation_score": 58.0,
    },
    "aggressive": {
        "target_profile": "aggressive_return",
        "primary_metric": "return_first_validation_score",
        "min_backtest_1y_return": 1.00,
        "min_backtest_sharpe_1y": 1.8,
        "max_backtest_mdd_1y": -0.35,
        "min_live_1m_avg_return": 0.03,
        "min_live_1m_win_rate": 0.55,
        "min_live_1m_sample_count": 10,
        "min_live_current_avg_return": 0.0,
        "min_model_value_score": 60.0,
        "min_total_validation_score": 65.0,
    },
    "tseries": {
        "target_profile": "timing_discovery",
        "primary_metric": "confirmed_candidate_quality",
        "min_backtest_1y_return": 0.30,
        "min_backtest_sharpe_1y": 1.2,
        "max_backtest_mdd_1y": -0.28,
        "min_live_1m_avg_return": 0.02,
        "min_live_1m_win_rate": 0.55,
        "min_live_1m_sample_count": 10,
        "min_live_current_avg_return": 0.0,
        "min_model_value_score": 65.0,
        "min_total_validation_score": 62.0,
        "min_confirmed_t10_hit_rate": 50.0,
        "min_confirmed_avg_excess_vs_all_1m": 1.0,
    },
    "etf": {
        "target_profile": "etf_timing_defensive",
        "primary_metric": "etf_return_with_drawdown_guard",
        "min_backtest_1y_return": 0.12,
        "min_backtest_sharpe_1y": 1.0,
        "max_backtest_mdd_1y": -0.15,
        "min_live_1m_avg_return": 0.005,
        "min_live_1m_win_rate": 0.52,
        "min_live_1m_sample_count": 10,
        "min_live_current_avg_return": 0.0,
        "min_model_value_score": 50.0,
        "min_total_validation_score": 58.0,
    },
}


MODEL_PROFILE_OVERRIDE = {
    "S2": "standard_internal",
    "S2_PIT_V01": "standard_internal",
    "S3": "aggressive_return",
    "S3_ACCEL_V01": "aggressive_return",
    "S3_CORE2": "aggressive_return",
    "S4": "standard_internal",
    "S5": "stable_defensive",
    "S6": "stable_defensive",
    "I-STOCK-STRONG-RSI-V01": "standard_internal",
    "T-STOCK-V01": "timing_discovery",
    "T-ETF-V01": "etf_timing_defensive",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _target_for(model_code: str, scope: str) -> dict[str, Any]:
    if model_code == "T-ETF-V01":
        return dict(MODEL_TARGETS["etf"])
    if scope == "tseries_models":
        return dict(MODEL_TARGETS["tseries"])
    if model_code in {"S3", "S3_ACCEL_V01", "S3_CORE2"}:
        return dict(MODEL_TARGETS["aggressive"])
    if model_code in {"S5", "S6"}:
        return dict(MODEL_TARGETS["stable"])
    return dict(MODEL_TARGETS["default"])


def _pass_min(actual: float | None, target: float | None) -> bool | None:
    if actual is None or target is None:
        return None
    return actual >= target


def _pass_mdd(actual: float | None, limit: float | None) -> bool | None:
    if actual is None or limit is None:
        return None
    return actual >= limit


def _metric_check(name: str, actual: float | None, target: float | None, direction: str) -> dict[str, Any]:
    if direction == "max_drawdown_floor":
        passed = _pass_mdd(actual, target)
    else:
        passed = _pass_min(actual, target)
    return {
        "metric": name,
        "actual": actual,
        "target": target,
        "direction": direction,
        "pass": passed,
    }


def _score_higher(actual: float | None, target: float | None) -> float | None:
    if actual is None or target is None:
        return None
    if target <= 0:
        return 100.0 if actual >= target else max(0.0, 50.0 + actual * 500.0)
    return max(0.0, min(100.0, actual / target * 100.0))


def _score_mdd(actual: float | None, limit: float | None) -> float | None:
    if actual is None or limit is None:
        return None
    if actual >= limit:
        return 100.0
    if limit == 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (abs(limit) / abs(actual))))


def _score_win_rate(actual: float | None, target: float | None) -> float | None:
    return _score_higher(actual, target)


def _avg_score(scores: list[float | None]) -> float | None:
    vals = [x for x in scores if x is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def _grade(score: float | None) -> str:
    if score is None:
        return "N/A"
    if score >= 95:
        return "S"
    if score >= 90:
        return "A"
    if score >= 85:
        return "B"
    return "C"


def _qualitative_assessment(
    model_code: str,
    state: str,
    grade: str,
    total_score: float | None,
    review_reasons: list[str],
    live_sample: int,
    sample_confidence: str,
) -> str:
    score_text = "N/A" if total_score is None else f"{total_score:.2f}"
    if state == "REVIEW":
        reason = review_reasons[0].split(" actual=", 1)[0] if review_reasons else "핵심 기준"
        return f"{model_code}는 {grade}등급({score_text})이며 {reason} 미달입니다. 표본신뢰도는 {sample_confidence}입니다. 현행 확대 적용은 보류하고 보정·강등·중단 후보로 검토해야 합니다."
    if state == "PASS":
        return f"{model_code}는 {grade}등급({score_text})으로 live-first 기준을 충족합니다. 표본신뢰도는 {sample_confidence}이며, 성과 지속성과 손실 방어를 계속 확인해야 합니다."
    return f"{model_code}는 {grade}등급({score_text})으로 관찰 구간입니다. 표본신뢰도는 {sample_confidence}이며, 다음 주말 검증에서 개선 여부를 확인해야 합니다."


def _sample_confidence(live_sample: int) -> str:
    if live_sample >= 30:
        return "high"
    if live_sample >= 10:
        return "medium"
    return "low"


def _live_map(payload: dict[str, Any], scope: str) -> dict[str, dict[str, Any]]:
    rows = payload.get("actual_live_performance_summary", {}).get(scope, []) or []
    return {str(row.get("model_code")): row for row in rows if row.get("model_code")}


def _supporting_validation(model_code: str, asof: str) -> dict[str, Any] | None:
    token = asof.replace("-", "")
    if model_code == "T-STOCK-V01":
        p = ROOT / "reports" / "model_upgrade_research" / token / "T_STOCK_V01_OPERATIONALIZATION" / f"t_stock_v01_validation_summary_{token}.csv"
        if not p.exists():
            return None
        try:
            import pandas as pd

            df = pd.read_csv(p)
            confirmed = df[df["candidate_bucket"] == "confirmed"]
            if confirmed.empty:
                return None
            row = confirmed.iloc[0].to_dict()
            return {
                "source": str(p),
                "summary": {
                    "confirmed_t10_hit_rate": _safe_float(row.get("t10_hit_rate")),
                    "confirmed_t3_hit_rate": _safe_float(row.get("t3_hit_rate")),
                    "confirmed_avg_ret_1m": _safe_float(row.get("avg_ret_1M")),
                    "confirmed_avg_excess_vs_all_1m": _safe_float(row.get("avg_excess_vs_all_1M")),
                    "confirmed_obs_n": int(row.get("obs_n", 0)),
                },
            }
        except Exception:
            return {"source": str(p), "summary": None, "warning": "failed_to_parse_supporting_validation"}
    return None


def _build_row(perf: dict[str, Any], live: dict[str, Any] | None, scope: str) -> dict[str, Any]:
    model_code = str(perf.get("model_code"))
    asof = str(perf.get("asof_date") or "")
    target = _target_for(model_code, scope)
    live_1m = ((live or {}).get("metrics") or {}).get("1m") or {}
    live_current = ((live or {}).get("metrics") or {}).get("current_return") or {}

    backtest_1y = _safe_float(perf.get("trailing_1y"))
    backtest_sharpe = _safe_float(perf.get("sharpe_1y"))
    backtest_mdd = _safe_float(perf.get("mdd_1y"))
    live_1m_avg_return = _safe_float(live_1m.get("avg_return"))
    live_1m_win_rate = _safe_float(live_1m.get("win_rate"))
    live_1m_avg_mdd = _safe_float(live_1m.get("avg_mdd"))
    live_current_avg_return = _safe_float(live_current.get("avg_return"))
    live_current_avg_mdd = _safe_float(live_current.get("avg_mdd"))

    checks = [
        _metric_check("live_1m_avg_return", live_1m_avg_return, target["min_live_1m_avg_return"], "higher_is_better"),
        _metric_check("live_current_avg_return", live_current_avg_return, target["min_live_current_avg_return"], "higher_is_better"),
        _metric_check("live_1m_win_rate", live_1m_win_rate, target["min_live_1m_win_rate"], "higher_is_better"),
        _metric_check("live_1m_avg_mdd", live_1m_avg_mdd, target["max_backtest_mdd_1y"], "max_drawdown_floor"),
    ]
    live_sample = int(live_1m.get("sample_count") or 0)
    sample_confidence = _sample_confidence(live_sample)
    supporting = _supporting_validation(model_code, asof)
    supporting_summary = (supporting or {}).get("summary") or {}
    confirmed_t10_hit = _safe_float(supporting_summary.get("confirmed_t10_hit_rate"))
    confirmed_excess_1m = _safe_float(supporting_summary.get("confirmed_avg_excess_vs_all_1m"))

    if confirmed_t10_hit is not None and target.get("min_confirmed_t10_hit_rate") is not None:
        checks.append(
            _metric_check("confirmed_t10_hit_rate", confirmed_t10_hit, target["min_confirmed_t10_hit_rate"], "higher_is_better")
        )
    if confirmed_excess_1m is not None and target.get("min_confirmed_avg_excess_vs_all_1m") is not None:
        checks.append(
            _metric_check(
                "confirmed_avg_excess_vs_all_1m",
                confirmed_excess_1m,
                target["min_confirmed_avg_excess_vs_all_1m"],
                "higher_is_better",
            )
        )

    live_1m_return_score = _score_higher(live_1m_avg_return, target["min_live_1m_avg_return"]) or 0.0
    live_current_return_score = _score_higher(live_current_avg_return, target["min_live_current_avg_return"]) or 0.0
    live_win_rate_score = _score_win_rate(live_1m_win_rate, target["min_live_1m_win_rate"]) or 0.0
    live_mdd_score = _score_mdd(live_1m_avg_mdd, target["max_backtest_mdd_1y"]) or 0.0
    backtest_reference_score = _avg_score(
        [
            _score_higher(backtest_1y, target["min_backtest_1y_return"]),
            _score_higher(backtest_sharpe, target["min_backtest_sharpe_1y"]),
            _score_mdd(backtest_mdd, target["max_backtest_mdd_1y"]),
        ]
    ) or 0.0
    profitability_score = _avg_score([live_1m_return_score, live_current_return_score])
    risk_score = live_mdd_score
    consistency_score = live_win_rate_score
    model_value_score = _avg_score(
        [
            _score_higher(confirmed_t10_hit / 100.0 if confirmed_t10_hit is not None else None, (target.get("min_confirmed_t10_hit_rate") or 50.0) / 100.0),
            _score_higher(confirmed_excess_1m / 100.0 if confirmed_excess_1m is not None else None, (target.get("min_confirmed_avg_excess_vs_all_1m") or 1.0) / 100.0),
        ]
    )
    if model_value_score is None:
        model_value_score = _avg_score([profitability_score, consistency_score])

    weighted_parts = [
        (live_1m_return_score, 0.35),
        (live_current_return_score, 0.15),
        (live_win_rate_score, 0.15),
        (live_mdd_score, 0.15),
        (model_value_score, 0.10),
        (backtest_reference_score, 0.10),
    ]
    valid_weight = sum(weight for score, weight in weighted_parts if score is not None)
    total_score = None
    if valid_weight:
        total_score = round(sum(float(score) * weight for score, weight in weighted_parts if score is not None) / valid_weight, 2)

    score_checks = [
        _metric_check("model_value_score", model_value_score, target["min_model_value_score"], "higher_is_better"),
        _metric_check("total_validation_score", total_score, 85.0, "higher_is_better"),
    ]
    checks.extend(score_checks)

    review_reasons: list[str] = []
    for check in checks:
        if check.get("pass") is False:
            review_reasons.append(
                f"{check.get('metric')} actual={check.get('actual')} target={check.get('target')}"
            )
    if total_score is None or total_score < 85.0:
        state = "REVIEW"
        action = "MODEL_REVIEW_OR_DOWNGRADE_CANDIDATE"
    elif total_score >= 90.0:
        state = "PASS"
        action = "MAINTAIN"
    else:
        state = "WATCH"
        action = "REVIEW_NEXT_WEEK"
    grade = _grade(total_score)
    qualitative_assessment = _qualitative_assessment(
        model_code=model_code,
        state=state,
        grade=grade,
        total_score=total_score,
        review_reasons=review_reasons,
        live_sample=live_sample,
        sample_confidence=sample_confidence,
    )

    return {
        "scope": scope,
        "model_code": model_code,
        "display_name": perf.get("display_name") or model_code,
        "model_profile": MODEL_PROFILE_OVERRIDE.get(model_code, target["target_profile"]),
        "asof_date": asof,
        "metric_basis": perf.get("metric_basis"),
        "review_state": state,
        "recommended_action": action,
        "review_reasons": review_reasons,
        "qualitative_assessment_ko": qualitative_assessment,
        "validation_score": {
            "total_score": total_score,
            "grade": grade,
            "grade_rule": "S>=95, A>=90, B>=85, C<85",
            "profitability_score": profitability_score,
            "risk_score": risk_score,
            "consistency_score": consistency_score,
            "model_value_score": model_value_score,
            "backtest_reference_score": backtest_reference_score,
            "score_weights": {
                "live_1m_avg_return": 0.35,
                "live_current_avg_return": 0.15,
                "live_1m_win_rate": 0.15,
                "live_1m_avg_mdd": 0.15,
                "model_value": 0.10,
                "backtest_reference": 0.10,
            },
            "score_basis": "live_first_v3",
            "backtest_reference_only": True,
        },
        "target": target,
        "current_backtest_metrics": {
            "trailing_1m": _safe_float(perf.get("trailing_1m")),
            "trailing_3m": _safe_float(perf.get("trailing_3m")),
            "trailing_6m": _safe_float(perf.get("trailing_6m")),
            "trailing_1y": _safe_float(perf.get("trailing_1y")),
            "itd_return": _safe_float(perf.get("itd_return")),
            "cagr": _safe_float(perf.get("cagr")),
            "mdd_1y": _safe_float(perf.get("mdd_1y")),
            "sharpe_1y": _safe_float(perf.get("sharpe_1y")),
            "sample_count": perf.get("sample_count"),
        },
        "current_live_metrics": {
            "live_start_date": (live or {}).get("live_start_date"),
            "live_event_count": (live or {}).get("live_event_count"),
            "latest_live_event_date": (live or {}).get("latest_live_event_date"),
            "current_avg_return": live_current_avg_return,
            "current_win_rate": _safe_float(live_current.get("win_rate")),
            "current_avg_mdd": live_current_avg_mdd,
            "one_month_sample_count": live_sample,
            "sample_confidence": sample_confidence,
            "one_month_avg_return": live_1m_avg_return,
            "one_month_win_rate": live_1m_win_rate,
            "one_month_avg_mdd": live_1m_avg_mdd,
        },
        "metric_checks": checks,
        "supporting_validation": supporting,
        "notes": [
            "Backtest metrics are published model NAV/proxy metrics.",
            "Live metrics use actual market-price forward returns since model live start.",
            "Weekly model correction/suspension decisions should use weekend review only.",
        ],
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_state: dict[str, int] = {}
    for row in rows:
        state = str(row.get("review_state"))
        by_state[state] = by_state.get(state, 0) + 1
    return {
        "model_count": len(rows),
        "by_review_state": by_state,
        "action_required_count": sum(1 for r in rows if r.get("recommended_action") not in {"MAINTAIN", "KEEP_OBSERVING"}),
    }


def build_payload(asof: str | None = None) -> dict[str, Any]:
    admin = _load_json(ADMIN_CURRENT / "admin_new_entry_tracker.json")
    asof_date = asof or admin.get("as_of_date")
    perf = admin.get("model_performance_summary") or {}
    rows: list[dict[str, Any]] = []
    for scope in ["internal_models", "tseries_models"]:
        live_by_model = _live_map(admin, scope)
        for item in perf.get(scope, []) or []:
            rows.append(_build_row(item, live_by_model.get(str(item.get("model_code"))), scope))

    payload = {
        "source_name": "internal_model_validation_current",
        "schema_version": "2026-05-17.v3",
        "visibility": "admin_only",
        "page_target": "admin_internal_models",
        "section_title_ko": "내부용 모델 검증",
        "as_of_date": asof_date,
        "generated_at": _now_iso(),
        "review_schedule": {
            "frequency": "weekly",
            "recommended_day": "weekend_after_week_close",
            "operating_rule": "모델 보정/수정/중단 판단은 주말 주 1회 검증 결과 기준으로만 수행한다.",
            "daily_pipeline_rule": "평일에는 payload 최신화와 표시만 허용하고 모델 정책 변경은 하지 않는다.",
        },
        "decision_policy": {
            "PASS": "live-first 점수 90점 이상. 현행 운영 유지.",
            "WATCH": "live-first 점수 85점 이상 90점 미만. 다음 주말 재검증.",
            "REVIEW": "live-first 점수 85점 미만. 보정/강등/중단 후보 검토.",
        },
        "metric_definitions": {
            "backtest_1y_return": "모델 NAV/proxy 기준 최근 1년 수익률",
            "backtest_sharpe_1y": "모델 NAV/proxy 기준 최근 1년 Sharpe",
            "backtest_mdd_1y": "모델 NAV/proxy 기준 최근 1년 최대낙폭",
            "live_1m_avg_return": "운영 시작 이후 편입 이벤트 중 1개월 성과가 확정된 표본의 평균 수익률",
            "live_1m_win_rate": "운영 시작 이후 편입 이벤트 중 1개월 성과가 플러스인 비율",
            "sample_confidence": "live 1M 표본 수 기반 신뢰도입니다. 30개 이상 high, 10개 이상 medium, 10개 미만 low입니다.",
            "model_value_score": "모델이 자체 목적을 달성하는지 보는 효용 점수입니다. T-STOCK은 confirmed 후보 lift와 초과수익을 반영합니다.",
            "backtest_reference_score": "백테스트 참고 점수입니다. live-first 평가에서 보조 10%만 반영합니다.",
            "total_validation_score": "live 1M 수익률 35%, 현재수익률 15%, live 1M 승률 15%, live 1M MDD 15%, 모델효용 10%, 백테스트 참고 10% 결합 점수입니다.",
            "grade": "S는 95점 이상, A는 90점 이상, B는 85점 이상, C는 85점 미만입니다.",
            "qualitative_assessment_ko": "Quant 쓰레드가 작성한 50단어 이내의 객관적·보수적·냉정한 정성 평가입니다.",
            "confirmed_t10_hit_rate": "T-STOCK confirmed 후보가 실제 T10 이상 성과군에 들어간 비율입니다.",
            "confirmed_avg_excess_vs_all_1m": "T-STOCK confirmed 후보의 1개월 평균 초과수익률입니다.",
        },
        "summary": _summary(rows),
        "models": rows,
        "source_payloads": {
            "admin_new_entry_tracker": str(ADMIN_CURRENT / "admin_new_entry_tracker.json"),
            "internal_model_performance_history": str(ADMIN_CURRENT / "internal_model_performance_history.json"),
            "internal_model_validation_history": str(HISTORY_PATH),
        },
    }
    return payload


def _history_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in payload.get("models", []) or []:
        score = model.get("validation_score") or {}
        backtest = model.get("current_backtest_metrics") or {}
        live = model.get("current_live_metrics") or {}
        rows.append(
            {
                "validation_asof_date": payload.get("as_of_date"),
                "generated_at": payload.get("generated_at"),
                "scope": model.get("scope"),
                "model_code": model.get("model_code"),
                "display_name": model.get("display_name"),
                "model_profile": model.get("model_profile"),
                "review_state": model.get("review_state"),
                "recommended_action": model.get("recommended_action"),
                "review_reasons": model.get("review_reasons"),
                "total_score": score.get("total_score"),
                "grade": score.get("grade"),
                "profitability_score": score.get("profitability_score"),
                "risk_score": score.get("risk_score"),
                "consistency_score": score.get("consistency_score"),
                "model_value_score": score.get("model_value_score"),
                "backtest_reference_score": score.get("backtest_reference_score"),
                "score_basis": score.get("score_basis"),
                "backtest_reference_only": score.get("backtest_reference_only"),
                "backtest_1y_return": backtest.get("trailing_1y"),
                "backtest_mdd_1y": backtest.get("mdd_1y"),
                "backtest_sharpe_1y": backtest.get("sharpe_1y"),
                "live_1m_sample_count": live.get("one_month_sample_count"),
                "sample_confidence": live.get("sample_confidence"),
                "live_1m_avg_return": live.get("one_month_avg_return"),
                "live_1m_win_rate": live.get("one_month_win_rate"),
                "live_1m_avg_mdd": live.get("one_month_avg_mdd"),
                "qualitative_assessment_ko": model.get("qualitative_assessment_ko"),
            }
        )
    return rows


def _build_history_payload(current_payload: dict[str, Any]) -> dict[str, Any]:
    existing_rows: list[dict[str, Any]] = []
    if HISTORY_PATH.exists():
        try:
            existing = _load_json(HISTORY_PATH)
            existing_rows = existing.get("history", []) or []
        except json.JSONDecodeError:
            existing_rows = []

    asof_date = current_payload.get("as_of_date")
    new_rows = _history_rows(current_payload)
    merged = [row for row in existing_rows if row.get("validation_asof_date") != asof_date] + new_rows
    merged.sort(key=lambda row: (str(row.get("validation_asof_date") or ""), str(row.get("model_code") or "")))

    validation_dates = sorted({str(row.get("validation_asof_date")) for row in merged if row.get("validation_asof_date")})
    latest_rows = [row for row in merged if row.get("validation_asof_date") == asof_date]
    latest_by_state: dict[str, int] = {}
    latest_by_grade: dict[str, int] = {}
    for row in latest_rows:
        latest_by_state[str(row.get("review_state"))] = latest_by_state.get(str(row.get("review_state")), 0) + 1
        latest_by_grade[str(row.get("grade"))] = latest_by_grade.get(str(row.get("grade")), 0) + 1

    return {
        "source_name": "internal_model_validation_history",
        "schema_version": "2026-05-17.v1",
        "visibility": "admin_only",
        "page_target": "admin_internal_models",
        "as_of_date": asof_date,
        "generated_at": current_payload.get("generated_at"),
        "history_grain": "weekly_model_validation_by_model",
        "dedupe_key": ["validation_asof_date", "model_code"],
        "summary": {
            "validation_week_count": len(validation_dates),
            "history_row_count": len(merged),
            "model_count_latest": len(latest_rows),
            "latest_by_review_state": latest_by_state,
            "latest_by_grade": latest_by_grade,
            "first_validation_asof_date": validation_dates[0] if validation_dates else None,
            "latest_validation_asof_date": validation_dates[-1] if validation_dates else None,
        },
        "history": merged,
    }


def _write_outputs(payload: dict[str, Any]) -> dict[str, Any]:
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    history = _build_history_payload(payload)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    token = str(payload.get("as_of_date") or "").replace("-", "")
    if token:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path = SNAPSHOT_DIR / f"internal_model_validation_{token}.json"
        snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        snapshot_path = None
    return {
        "current": str(OUT_PATH),
        "history": str(HISTORY_PATH),
        "snapshot": str(snapshot_path) if snapshot_path else None,
        "history_rows": len(history.get("history", [])),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build weekly internal model validation payload for QS admin page.")
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD. Defaults to admin_new_entry_tracker as_of_date.")
    args = ap.parse_args()
    payload = build_payload(args.asof)
    outputs = _write_outputs(payload)
    print({"out": outputs, "as_of_date": payload["as_of_date"], "models": len(payload["models"])})


if __name__ == "__main__":
    main()
