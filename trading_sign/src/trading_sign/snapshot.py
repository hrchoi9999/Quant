from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .model_profiles import PUBLIC_CURRENT_MODEL_CODES, get_model_profile
from .pipeline import DailySignalRunResult

STATE_ORDER = ["매수", "보유", "주의", "매도", "매수 대기"]
MODEL_DISPLAY_NAMES = {
    "STABLE": "안정형",
    "BALANCED": "균형형",
    "GROWTH": "성장형",
    "T_STOCK_DISCOVERY": "T 주식 발굴형",
    "T_ETF_DISCOVERY": "T ETF 발굴형",
}


def _ordered_state_counts(state_counts: dict[str, int]) -> dict[str, int]:
    ordered = {state: int(state_counts.get(state, 0)) for state in STATE_ORDER}
    for key, value in state_counts.items():
        if key not in ordered:
            ordered[key] = int(value)
    return ordered


def _build_signal_sections(result: DailySignalRunResult) -> List[dict]:
    recommended = [record for record in result.records if record.is_recommended and not record.is_held]
    held = [record for record in result.records if record.is_held]
    sections = []
    for section_key, title, records in (
        ("recommended", "추천 종목 신호", recommended),
        ("held", "보유 종목 신호", held),
    ):
        state_counts: dict[str, int] = {}
        rows = []
        for record in records:
            state_counts[record.current_state] = state_counts.get(record.current_state, 0) + 1
            rows.append(
                {
                    "ticker": record.ticker,
                    "security_name": record.security_name or record.ticker,
                    "current_state": record.current_state,
                    "reason_summary": record.reason_summary,
                    "latest_state_change_date": record.latest_state_change_date or record.signal_date,
                    "entry_score": record.entry_score,
                    "exit_risk_score": record.exit_risk_score,
                }
            )
        sections.append(
            {
                "section_key": section_key,
                "title": title,
                "record_count": len(rows),
                "state_counts": _ordered_state_counts(state_counts),
                "signals": rows,
            }
        )
    return sections


def _build_ui_block(result: DailySignalRunResult, generated_at: str) -> dict:
    data_asof_date = result.records[0].data_asof_date if result.records else result.signal_date
    profile = get_model_profile(result.model_code)
    return {
        "title": "전일 종가 기준 일간 신호",
        "description": "이 신호는 전일 종가 기준으로 계산된 참고용 일간 점검 정보입니다.",
        "disclaimer": "이 상태는 공개 규칙 기반 모델의 참고용 해석이며 특정 이용자에 대한 개별 매매 지시가 아닙니다.",
        "signal_date": result.signal_date,
        "data_asof_date": data_asof_date,
        "generated_at": generated_at,
        "state_chips": [
            {"state": state, "count": int(result.state_counts.get(state, 0))}
            for state in STATE_ORDER
        ],
        "sections": _build_signal_sections(result),
        "profile_code": profile.profile_code,
    }


def _validate_public_result_model_codes(results: List[DailySignalRunResult]) -> None:
    invalid = sorted(
        {
            str(result.model_code).strip().upper()
            for result in results
            if str(result.model_code).strip().upper() not in PUBLIC_CURRENT_MODEL_CODES
        }
    )
    if invalid:
        raise ValueError(
            "public trading_sign snapshot contains non-exposed model codes: "
            + ", ".join(invalid)
        )


def build_overview_payload(results: Iterable[DailySignalRunResult]) -> dict:
    results = list(results)
    _validate_public_result_model_codes(results)
    rows = []
    total_states: dict[str, int] = {}
    asof = None
    generated_at = datetime.now().isoformat(timespec="seconds")
    for result in results:
        asof = asof or result.signal_date
        rows.append(
            {
                "model_code": result.model_code,
                "model_name": MODEL_DISPLAY_NAMES.get(result.model_code, result.model_code),
                "signal_date": result.signal_date,
                "record_count": result.record_count,
                "state_counts": _ordered_state_counts(result.state_counts),
            }
        )
        for key, value in result.state_counts.items():
            total_states[key] = total_states.get(key, 0) + int(value)
    return {
        "asof": asof,
        "generated_at": generated_at,
        "schema_version": "v1",
        "summary": {
            "model_count": len(rows),
            "signal_count": sum(int(row["record_count"]) for row in rows),
            "state_counts": _ordered_state_counts(total_states),
            "state_order": STATE_ORDER,
        },
        "models": rows,
    }


def build_model_detail_payload(results: Iterable[DailySignalRunResult]) -> dict:
    results = list(results)
    _validate_public_result_model_codes(results)
    models = []
    asof = None
    generated_at = datetime.now().isoformat(timespec="seconds")
    for result in results:
        asof = asof or result.signal_date
        models.append(
            {
                "model_code": result.model_code,
                "model_name": MODEL_DISPLAY_NAMES.get(result.model_code, result.model_code),
                "signal_date": result.signal_date,
                "record_count": result.record_count,
                "state_counts": _ordered_state_counts(result.state_counts),
                "ui_block": _build_ui_block(result, generated_at),
                "signals": [asdict(record) for record in result.records],
            }
        )
    return {
        "asof": asof,
        "generated_at": generated_at,
        "schema_version": "v1",
        "models": models,
    }


def build_manifest_payload(results: Iterable[DailySignalRunResult]) -> dict:
    results = list(results)
    overview = build_overview_payload(results)
    return {
        "asof": overview.get("asof"),
        "generated_at": overview.get("generated_at"),
        "schema_version": "v1",
        "files": [
            "tradingsign_overview.json",
            "tradingsign_model_detail.json",
            "tradingsign_manifest.json",
        ],
        "freshness": {
            "signal_refresh_frequency": "daily_eod",
            "data_cutoff": "previous_trading_day_close",
        },
    }


def write_current_snapshots(output_dir: Path, results: List[DailySignalRunResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    overview = build_overview_payload(results)
    detail = build_model_detail_payload(results)
    manifest = build_manifest_payload(results)
    (output_dir / "tradingsign_overview.json").write_text(
        json.dumps(overview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "tradingsign_model_detail.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "tradingsign_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
