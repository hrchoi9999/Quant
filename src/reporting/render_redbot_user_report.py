from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import yaml

from src.reporting.public_model_terms import build_public_model_metadata
from src.reporting.redbot_user_report_schema import validate_report_dict

MAPPING_PATH = ROOT / "data" / "configs" / "redbot_model_mapping.yml"
REPORT_DIR = ROOT / "reports" / "redbot_user_reports"
COMPARE_DIR = ROOT / "reports" / "model_compare"
ROUTER_DIR = ROOT / "reports" / "backtest_router"
ETF_DIR = ROOT / "reports" / "backtest_etf_allocation"
PRICE_DB = ROOT / "data" / "db" / "price.db"

CANONICAL_USER_MODELS = {
    "stable": {
        "user_model_name": "안정형",
        "description": "방어자산과 현금성 비중을 함께 활용하는 멀티애셋 데이터 기반 퀀트투자 모델",
        "risk_label": "low",
        "target_user_type": "변동성 완화와 자산 방어를 우선하는 공개형 모델 정보를 참고하려는 이용자",
        "key_assets": ["bond", "fx_usd", "commodity_gold", "cash_like"],
        "primary_internal_models": ["S6"],
        "secondary_internal_models": ["Router(stable)"],
    },
    "balanced": {
        "user_model_name": "균형형",
        "description": "주식과 ETF를 함께 사용하는 공개 기준 기반 퀀트투자 모델",
        "risk_label": "medium",
        "target_user_type": "주식과 ETF를 함께 활용한 공개형 모델 기준안을 참고하려는 이용자",
        "key_assets": ["stock", "equity_etf", "bond_short", "dividend", "low_vol"],
        "primary_internal_models": ["S2", "S5"],
        "secondary_internal_models": ["Router(balanced)"],
    },
    "growth": {
        "user_model_name": "성장형",
        "description": "추세와 모멘텀 데이터를 적극 반영하는 멀티애셋 데이터 기반 퀀트투자 모델",
        "risk_label": "high",
        "target_user_type": "추세와 모멘텀을 반영한 성장 지향 공개형 모델 정보를 참고하려는 이용자",
        "key_assets": ["momentum_stock", "equity_growth_etf", "sector_momentum"],
        "primary_internal_models": ["S3", "S4"],
        "secondary_internal_models": ["Router(growth)"],
    },
    "auto": {
        "user_model_name": "자동전환형",
        "description": "시장 상태에 따라 자산 비중 구조를 조정하는 주간 브리핑용 퀀트투자 모델",
        "risk_label": "adaptive",
        "target_user_type": "시장 상태 변화에 따라 조정되는 공개형 모델 기준안을 참고하려는 이용자",
        "key_assets": ["multi_asset", "regime_switching", "dynamic_allocation"],
        "primary_internal_models": ["Router(auto)"],
        "secondary_internal_models": ["S2", "S3", "S4", "S5", "S6"],
    },
}

RISK_LABEL_KR = {"low": "낮음", "medium": "보통", "high": "높음", "adaptive": "자동조정"}
REGIME_KR = {"risk_on": "상승 우위", "neutral": "중립", "risk_off": "하락 방어", "unknown": "미확인"}
PROFILE_LABELS = {"stable": "방어 중심 모델", "balanced": "균형 배분 모델", "growth": "성장 추세 모델", "auto": "국면 대응 모델"}
SERVICE_MODEL_SOURCE = {
    "stable": {"summary_model": "Router", "weights_kind": "router_stable", "compare_profile": "stable"},
    "balanced": {"summary_model": "Router", "weights_kind": "router_balanced", "compare_profile": "balanced"},
    "growth": {"summary_model": "Router", "weights_kind": "router_growth", "compare_profile": "growth"},
    "auto": {"summary_model": "Router", "weights_kind": "router_auto", "compare_profile": "auto"},
}
ROLE_SUMMARY_BY_GROUP = {"cash": "현금성 대기 자산", "etf": "ETF 분산 투자", "stock": "주식 직접 투자", "other": "기타 자산"}
GARBLED_TOKENS = ["??", "\ufffd", "챙", "챗", "쨌", "혮", "湲", "誘", "멸", "뎅", "좊", "몃", "쾭", "꾧", "梨", "곕", "툕"]


def latest_file(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern), key=lambda p: (p.stat().st_mtime, p.name))
    if not files:
        raise FileNotFoundError(f"No files for pattern {pattern} in {directory}")
    return files[-1]


def load_mapping() -> dict[str, Any]:
    data: dict[str, Any] = {}
    if MAPPING_PATH.exists():
        with MAPPING_PATH.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    data["user_models"] = [{"service_profile": profile, **values} for profile, values in CANONICAL_USER_MODELS.items()]
    return data


def get_user_model(mapping: dict[str, Any], user_model_name: str | None, service_profile: str | None) -> dict[str, Any]:
    models = mapping["user_models"]
    if user_model_name:
        for row in models:
            if row["user_model_name"] == user_model_name:
                return row
        raise ValueError(f"Unknown user_model_name: {user_model_name}")
    if service_profile:
        for row in models:
            if row["service_profile"] == service_profile:
                return row
        raise ValueError(f"Unknown service_profile: {service_profile}")
    return next(row for row in models if row["service_profile"] == "balanced")


def load_compare_frames(service_profile: str) -> tuple[pd.DataFrame, pd.DataFrame, Path, Path]:
    summary_path = latest_file(COMPARE_DIR, f"model_compare_summary_*_{service_profile}.csv")
    periods_path = latest_file(COMPARE_DIR, f"model_compare_periods_*_{service_profile}.csv")
    return (
        pd.read_csv(summary_path),
        pd.read_csv(periods_path),
        summary_path,
        periods_path,
    )


def load_router_decisions(profile: str) -> pd.DataFrame:
    return pd.read_csv(latest_file(ROUTER_DIR, f"router_decisions_*_{profile}.csv"))


def load_weights_frame(kind: str) -> pd.DataFrame:
    if kind == "router_auto":
        return pd.read_csv(latest_file(ROUTER_DIR, "router_weights_*_auto.csv"))
    if kind == "router_balanced":
        return pd.read_csv(latest_file(ROUTER_DIR, "router_weights_*_balanced.csv"))
    if kind == "router_growth":
        return pd.read_csv(latest_file(ROUTER_DIR, "router_weights_*_growth.csv"))
    if kind == "router_stable":
        return pd.read_csv(latest_file(ROUTER_DIR, "router_weights_*_stable.csv"))
    if kind == "s6":
        return pd.read_csv(latest_file(ETF_DIR, "s6_alloc_weights_*_M_*.csv"))
    raise ValueError(f"Unsupported weights kind: {kind}")


def latest_weights(weights_df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    date_col = "trade_date" if "trade_date" in weights_df.columns else "date"
    latest_dt = str(sorted(weights_df[date_col].astype(str).unique())[-1])
    return weights_df[weights_df[date_col].astype(str) == latest_dt].copy(), latest_dt


def previous_weights(weights_df: pd.DataFrame, current_date: str) -> pd.DataFrame:
    date_col = "trade_date" if "trade_date" in weights_df.columns else "date"
    dates = sorted(weights_df[date_col].astype(str).unique())
    prev_dates = [d for d in dates if d < current_date]
    if not prev_dates:
        return pd.DataFrame(columns=weights_df.columns)
    return weights_df[weights_df[date_col].astype(str) == prev_dates[-1]].copy()


def _normalize_security_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"CASH", "00CASH", "NONE", "NAN"}:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else None


def _looks_garbled(text: Any) -> bool:
    if text is None:
        return True
    value = str(text).strip()
    return (not value) or any(token in value for token in GARBLED_TOKENS)


def _load_canonical_name_map() -> dict[str, str]:
    con = sqlite3.connect(PRICE_DB)
    try:
        rows = con.execute("select ticker, name from instrument_master where name is not null and trim(name) <> ''").fetchall()
    finally:
        con.close()
    return {str(ticker).zfill(6): str(name) for ticker, name in rows if str(name).strip()}


CANONICAL_NAME_MAP = _load_canonical_name_map()


def summarize_changes(current: pd.DataFrame, previous: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["security_code", "display_name", "weight"])
        rows = []
        for row in df.itertuples():
            raw_ticker = getattr(row, "ticker", None)
            security_code = _normalize_security_code(raw_ticker)
            display_name = getattr(row, "name", None) or raw_ticker or "CASH"
            if security_code and (_looks_garbled(display_name) or str(display_name).strip() == security_code):
                display_name = CANONICAL_NAME_MAP.get(security_code, display_name)
            if security_code is None:
                display_name = "현금/대기자금"
            rows.append({
                "security_code": security_code,
                "display_name": str(display_name),
                "weight": float(pd.to_numeric(getattr(row, "weight", 0.0), errors="coerce") or 0.0),
            })
        out = pd.DataFrame(rows)
        return out.groupby(["security_code", "display_name"], dropna=False, as_index=False)["weight"].sum()

    def to_items(df: pd.DataFrame, direction: str) -> list[dict[str, Any]]:
        items = []
        for row in df.itertuples():
            delta = float(row.delta)
            if direction == "increase" and delta <= 0.0001:
                continue
            if direction == "decrease" and delta >= -0.0001:
                continue
            items.append({
                "display_name": row.display_name,
                "security_code": row.security_code,
                "delta_weight": round(delta, 6),
                "direction": direction,
            })
        return items

    cur = normalize(current)
    prev = normalize(previous)
    merged = cur.merge(prev, on=["security_code", "display_name"], how="outer", suffixes=("_cur", "_prev"))
    merged["weight_cur"] = pd.to_numeric(merged["weight_cur"], errors="coerce").fillna(0.0)
    merged["weight_prev"] = pd.to_numeric(merged["weight_prev"], errors="coerce").fillna(0.0)
    merged["display_name"] = merged["display_name"].fillna("미확인 자산")
    merged["security_code"] = merged["security_code"].where(merged["security_code"].notna(), None)
    merged["delta"] = merged["weight_cur"] - merged["weight_prev"]
    inc = merged.sort_values("delta", ascending=False).head(5)
    dec = merged.sort_values("delta", ascending=True).head(5)
    return to_items(inc, "increase"), to_items(dec, "decrease")


def build_portfolio_rows(weights: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for row in weights.sort_values("weight", ascending=False).itertuples():
        raw_ticker = getattr(row, "ticker", None)
        security_code = _normalize_security_code(raw_ticker)
        display_name = getattr(row, "name", None) or raw_ticker or "CASH"
        if security_code and (_looks_garbled(display_name) or str(display_name).strip() == security_code):
            display_name = CANONICAL_NAME_MAP.get(security_code, display_name)
        market = getattr(row, "market", "")
        source_type = str(getattr(row, "source_sleeve", market or "mixed"))
        if security_code is None:
            asset_group = "cash"
            display_name = "현금/대기자금"
        elif market == "ETF":
            asset_group = "etf"
        elif market in {"KOSPI", "KOSDAQ"}:
            asset_group = "stock"
        else:
            asset_group = (market or "other").lower()
        rows.append({
            "security_code": security_code,
            "asset_group": asset_group,
            "display_name": str(display_name),
            "target_weight": round(float(getattr(row, "weight", 0.0)), 6),
            "role_summary": ROLE_SUMMARY_BY_GROUP.get(asset_group, ROLE_SUMMARY_BY_GROUP["other"]),
            "source_type": source_type,
        })
    return rows


def build_model_rationale(service_profile: str, regime: str, mapping_row: dict[str, Any]) -> list[str]:
    bullets = [
        "이 모델은 멀티애셋 데이터 기반 퀀트투자 모델입니다.",
        "이 모델은 공개 기준 기반 퀀트투자 모델입니다.",
        "이 모델은 주간 브리핑용 퀀트투자 모델입니다.",
        "이 모델은 모델 포트폴리오를 산출하는 퀀트투자 모델입니다.",
        "시장·자산·리스크 데이터를 바탕으로 공개된 기준에 따라 산출됩니다.",
        "동일한 기준이 모든 이용자에게 동일하게 적용됩니다.",
        "주간 기준일 단위로 모델 포트폴리오와 변화 내용을 제공합니다.",
        f"현재 시장 판단은 '{REGIME_KR.get(regime, regime)}' 구간입니다.",
        f"현재 공개형 모델 정보는 {mapping_row['description']} 성격을 반영합니다.",
    ]
    return bullets[:6]




def build_public_compliance_metadata(*, asof_date: str, start_date: str, end_date: str, rebalance_frequency: str, fee_bps: float, slippage_bps: float, service_profile: str) -> dict[str, Any]:
    benchmark_name = {
        "stable": "KOSPI200",
        "balanced": "KOSPI200",
        "growth": "KOSPI200",
        "auto": "KOSPI200",
    }.get(service_profile, "KOSPI200")
    return {
        "content_class": "service_public_backtest",
        "public_same_for_all_users": True,
        "non_personalized": True,
        "is_personalized_advice": False,
        "is_one_to_one_advisory": False,
        "is_actual_trade_instruction": False,
        "actual_investment_result": False,
        "backtest_result": True,
        "disclaimer_required": True,
        "data_basis": "rule_based_public_model_output",
        "model_version": f"public-model-{asof_date.replace('-', '.')}",
        "calculation_version": "calc-2026-03-24-compliance-v1",
        "asof_date": asof_date,
        "rebalance_frequency": rebalance_frequency,
        "fee_bps": float(fee_bps),
        "slippage_bps": float(slippage_bps),
        "benchmark_name": benchmark_name,
        "backtest_start_date": start_date,
        "backtest_end_date": end_date,
        "universe_definition": "KR stocks + KR ETFs used by public rule-based models",
        "data_source_summary": "KRX daily prices, KR ETF daily prices, internal fundamentals views, rule-based monthly rebalance outputs",
    }

def performance_payload(summary_df: pd.DataFrame, periods_df: pd.DataFrame, summary_model: str) -> dict[str, Any]:
    row = summary_df.loc[summary_df["model"] == summary_model].iloc[0]
    periods = periods_df.loc[periods_df["model"] == summary_model].copy()
    period_order = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "FULL"]
    period_metrics = []
    period_map: dict[str, dict[str, float]] = {}
    for period in period_order:
        subset = periods.loc[periods["period"] == period]
        if subset.empty:
            continue
        p = subset.iloc[0]
        payload = {
            "period": period,
            "total_return": round(float(p.get("total_return", float("nan"))), 6),
            "cagr": round(float(p["cagr"]), 6),
            "mdd": round(float(p["mdd"]), 6),
            "sharpe": round(float(p["sharpe"]), 6),
        }
        period_metrics.append(payload)
        period_map[period] = payload
    primary_period = "1Y" if "1Y" in period_map else ("6M" if "6M" in period_map else ("3M" if "3M" in period_map else "FULL"))
    primary = period_map.get(primary_period) or {
        "period": "FULL",
        "cagr": round(float(row["cagr"]), 6),
        "mdd": round(float(row["mdd"]), 6),
        "sharpe": round(float(row["sharpe"]), 6),
    }
    headline = {
        "primary_period": primary_period,
        "display_metric": "cagr",
        "cagr": round(float(primary["cagr"]), 6),
        "total_return": round(float(primary.get("total_return", float("nan"))), 6),
        "mdd": round(float(primary["mdd"]), 6),
        "sharpe": round(float(primary["sharpe"]), 6),
        "trailing_3m": period_map.get("3M"),
        "trailing_6m": period_map.get("6M"),
        "trailing_1y": period_map.get("1Y"),
        "reference_5y": period_map.get("5Y"),
        "reference_full": period_map.get("FULL") or {
            "period": "FULL",
            "cagr": round(float(row["cagr"]), 6),
            "mdd": round(float(row["mdd"]), 6),
            "sharpe": round(float(row["sharpe"]), 6),
        },
    }
    return {"headline_metrics": headline, "period_metrics": period_metrics}


def determine_market_diagnosis() -> tuple[str, str, str]:
    latest = load_router_decisions("auto").iloc[-1]
    regime = str(latest["detected_regime"])
    regime_summary = {
        "risk_on": "위험자산 선호가 강한 국면으로 해석되는 구간입니다.",
        "neutral": "방향성이 뚜렷하지 않아 균형형 공개 모델이 중심이 되는 구간입니다.",
        "risk_off": "방어 자산 선호가 강한 구간으로 해석됩니다.",
        "unknown": "시장 국면을 명확히 구분하기 어려운 구간입니다.",
    }.get(regime, "시장 국면을 명확히 구분하기 어려운 구간입니다.")
    reference_response = {
        "risk_on": "주식 및 성장 자산 비중이 상대적으로 높아지는 공개 기준 기반 모델 방향입니다.",
        "neutral": "주식과 ETF를 함께 사용해 균형 구성을 유지하는 공개 기준 기반 모델 방향입니다.",
        "risk_off": "채권, 달러, 금 등 방어 자산 비중이 상대적으로 높아지는 공개 기준 기반 모델 방향입니다.",
        "unknown": "확정적 방향성보다 분산과 방어를 우선하는 공개 기준 기반 모델 방향입니다.",
    }.get(regime, "확정적 방향성보다 분산과 방어를 우선하는 공개 규칙 방향입니다.")
    return regime, regime_summary, reference_response


def build_report(user_model_name: str | None, service_profile: str | None, asof: str | None) -> tuple[dict[str, Any], Path, Path]:
    mapping = load_mapping()
    user_model = get_user_model(mapping, user_model_name, service_profile)
    service_profile = user_model["service_profile"]
    source_cfg = SERVICE_MODEL_SOURCE[service_profile]
    summary_df, periods_df, compare_summary_path, compare_periods_path = load_compare_frames(source_cfg["compare_profile"])
    regime, regime_summary, reference_response = determine_market_diagnosis()
    weights_df = load_weights_frame(source_cfg["weights_kind"])
    current_weights, current_date = latest_weights(weights_df)
    previous = previous_weights(weights_df, current_date)
    increased, decreased = summarize_changes(current_weights, previous)
    portfolio_rows = build_portfolio_rows(current_weights)
    perf = performance_payload(summary_df, periods_df, source_cfg["summary_model"])
    report_asof = asof or current_date
    summary_row = summary_df.loc[summary_df["model"] == source_cfg["summary_model"]].iloc[0]
    public_model_metadata = build_public_model_metadata(service_profile)
    compliance_metadata = build_public_compliance_metadata(
        asof_date=str(report_asof),
        start_date=str(summary_row.get("start", report_asof)),
        end_date=str(summary_row.get("end", report_asof)),
        rebalance_frequency="monthly",
        fee_bps=float(summary_row.get("fee_bps", 0.0) or 0.0),
        slippage_bps=float(summary_row.get("slippage_bps", 0.0) or 0.0),
        service_profile=service_profile,
    )
    report = {
        "header": {
            "report_title": "기준일 모델 정보 리포트",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "user_model_name": user_model["user_model_name"],
            "service_profile": service_profile,
            "report_version": "v2",
        },
        "executive_summary": {
            "current_model_label": user_model["user_model_name"],
            "market_view": REGIME_KR.get(regime, regime),
            "summary_basis": public_model_metadata["model_one_line_desc"],
            "risk_level": RISK_LABEL_KR.get(user_model["risk_label"], user_model["risk_label"]),
        },
        "market_diagnosis": {
            "current_regime": regime,
            "regime_summary": regime_summary,
            "reference_response": reference_response,
        },
        "model_overview": {
            "model_name": public_model_metadata["model_display_name"],
            "model_character": public_model_metadata["model_one_line_desc"],
            "model_profile_label": PROFILE_LABELS[service_profile],
            "core_role": public_model_metadata["model_role_desc"],
        },
        "model_metadata": public_model_metadata,
        "model_portfolio": portfolio_rows,
        "model_rationale": build_model_rationale(service_profile, regime, user_model),
        "risk_guide": {
            "risk_level": RISK_LABEL_KR.get(user_model["risk_label"], user_model["risk_label"]),
            "expected_drawdown_note": "시장 상황에 따라 손실이 발생할 수 있으며 단기 변동성은 항상 존재합니다.",
            "reference_usage_context": public_model_metadata["model_profile_desc"],
            "reference_holding_period": "중기 이상 관점에서 과거 규칙 결과를 해석하는 참고용 기간 정보입니다.",
        },
        "recent_performance": {**perf, "performance_subject_name": public_model_metadata["performance_subject_name"], "performance_subject_type": public_model_metadata["performance_subject_type"], "portfolio_generation_basis": public_model_metadata["portfolio_generation_basis"]},
        "model_changes": {
            "increased_assets": increased,
            "decreased_assets": decreased,
            "change_subject_name": public_model_metadata["change_subject_name"],
            "change_basis": public_model_metadata["change_basis_desc"],
            "change_reason_desc": public_model_metadata["change_reason_desc"],
        },
        "disclaimer": {
            "investment_risk": "투자에는 원금 손실 가능성이 있습니다.",
            "past_performance": "과거 성과가 미래 수익을 보장하지 않습니다.",
            "informational_purpose": "이 자료는 공개 기준 기반 퀀트투자 모델 정보와 백테스트 결과를 설명하기 위한 참고자료이며 특정 개인에 대한 투자자문이나 실제 매매 지시가 아닙니다.",
            "final_decision": "최종 투자 판단과 그 책임은 이용자 본인에게 있습니다.",
        },
        "compliance_metadata": compliance_metadata,
        "internal_metadata": {
            "source_models": user_model["primary_internal_models"],
            "generated_from_files": [str(compare_summary_path), str(compare_periods_path)],
            "user_visible_internal_models": False,
        },
    }
    errors = validate_report_dict(report)
    if errors:
        raise ValueError("Report validation failed: " + "; ".join(errors))
    json_path = REPORT_DIR / f"redbot_user_report_{service_profile}_{str(report_asof).replace('-', '')}.json"
    md_path = REPORT_DIR / f"redbot_user_report_{service_profile}_{str(report_asof).replace('-', '')}.md"
    return report, json_path, md_path


def render_markdown(report: dict[str, Any]) -> str:
    header = report["header"]
    perf = report["recent_performance"]
    portfolio_lines = [
        f"- {row['display_name']}{(' (' + row['security_code'] + ')') if row.get('security_code') else ''}: {row['target_weight']:.1%} | {row['role_summary']}"
        for row in report["model_portfolio"]
    ]
    why_lines = [f"- {item}" for item in report["model_rationale"]]
    inc_lines = [
        f"- {item['display_name']}{(' (' + item['security_code'] + ')') if item.get('security_code') else ''}: {item['delta_weight']:+.2%}"
        for item in report["model_changes"]["increased_assets"]
    ] or ["- 없음"]
    dec_lines = [
        f"- {item['display_name']}{(' (' + item['security_code'] + ')') if item.get('security_code') else ''}: {item['delta_weight']:+.2%}"
        for item in report["model_changes"]["decreased_assets"]
    ] or ["- 없음"]
    period_lines = []
    for row in perf["period_metrics"]:
        if row["period"] in {"3M", "6M"}:
            period_lines.append(f"- {row['period']}: 누적수익률 {row['total_return']:.2%}, MDD {row['mdd']:.2%}, Sharpe {row['sharpe']:.2f}")
        else:
            period_lines.append(f"- {row['period']}: CAGR {row['cagr']:.2%}, MDD {row['mdd']:.2%}, Sharpe {row['sharpe']:.2f}")
    headline = perf["headline_metrics"]
    return "\n".join([
        f"# {header['report_title']}",
        "",
        f"- 생성시각: {header['generated_at']}",
        f"- 모델명: {header['user_model_name']}",
        f"- 서비스 프로필: {header['service_profile']}",
        f"- 버전: {header['report_version']}",
        "",
        "## 요약",
        f"- 현재 기준 모델: {report['executive_summary']['current_model_label']}",
        f"- 시장 판단: {report['executive_summary']['market_view']}",
        f"- 산출 기준: {report['executive_summary']['summary_basis']}",
        f"- 위험 수준: {report['executive_summary']['risk_level']}",
        "",
        "## 시장 진단",
        f"- 현재 국면: {report['market_diagnosis']['current_regime']}",
        f"- 해석: {report['market_diagnosis']['regime_summary']}",
        f"- 공개 규칙 기준 방향: {report['market_diagnosis']['reference_response']}",
        "",
        "## 기준일 모델 구성",
        *portfolio_lines,
        "",
        "## 산출 배경",
        *why_lines,
        "",
        "## 성과 요약",
        f"- 주요 기간({headline['primary_period']}) CAGR: {headline['cagr']:.2%}",
        f"- 주요 기간({headline['primary_period']}) MDD: {headline['mdd']:.2%}",
        f"- 주요 기간({headline['primary_period']}) Sharpe: {headline['sharpe']:.2f}",
        *period_lines,
        "",
        "## 최근 변경",
        "### 비중 확대",
        *inc_lines,
        "### 비중 축소",
        *dec_lines,
        f"- 변경 기준: {report['model_changes']['change_basis']}",
        "",
        "## 유의사항",
        f"- {report['disclaimer']['investment_risk']}",
        f"- {report['disclaimer']['past_performance']}",
        f"- {report['disclaimer']['informational_purpose']}",
        f"- {report['disclaimer']['final_decision']}",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Render user-facing public model snapshot report payload")
    parser.add_argument("--user-model-name", default=None)
    parser.add_argument("--service-profile", default=None, choices=["stable", "balanced", "growth", "auto"])
    parser.add_argument("--asof", default=None)
    args = parser.parse_args()
    report, json_path, md_path = build_report(args.user_model_name, args.service_profile, args.asof)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()


