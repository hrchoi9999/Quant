from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"

STRATEGY_MODEL_CODE = "E-ETF-V01"
SLEEVE_MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"
BASE_POLICY = "hybrid_b50_ai50_top3_role"
SWITCH_POLICY = "mode_switch_stress_tail_asset"


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _safe_float(value: Any, digits: int = 6) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return _safe_float(value)
    if pd.isna(value):
        return None
    return value


def _records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    use = df.head(limit) if limit is not None else df
    return [{key: _json_value(value) for key, value in row.items()} for row in use.to_dict("records")]


def _current_context(asof: str) -> dict[str, Any]:
    path = ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_policy_walk_forward_current.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    maps = payload.get("recent_policy_maps") or []
    current = next((row for row in reversed(maps) if row.get("signal_date") == asof), maps[-1] if maps else {})
    return {
        "mode_switch_best_policy": (payload.get("best_portfolio_policy") or [{}])[0].get("policy"),
        "evaluated_dates": payload.get("evaluated_dates"),
        "stress_dates": payload.get("stress_dates"),
        "risk_off_dates": payload.get("risk_off_dates"),
        "stress_rule": payload.get("stress_rule"),
        "current_signal_date": current.get("signal_date"),
        "current_market_mode": current.get("e_market_mode"),
        "current_is_market_stress": current.get("is_market_stress"),
        "current_role_policy_map": current.get("role_policy_map"),
        "current_asset_policy_map": current.get("asset_policy_map"),
    }


def _load_selected(asof: str) -> pd.DataFrame:
    path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_selected_{_token(asof)}.csv"
    if not path.exists():
        raise SystemExit(f"missing mode switch selected CSV: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df[df["signal_date"].eq(asof)].copy()


def _policy_holdings(current: pd.DataFrame, policy: str) -> pd.DataFrame:
    keep_cols = [
        "signal_date",
        "policy",
        "effective_policy",
        "ticker",
        "name",
        "e_series_role",
        "e_asset_bucket",
        "e_strategy_bucket",
        "e_theme_bucket",
        "e_market_mode",
        "policy_weight",
        "sleeve_selection_prob",
        "e_baseline_selection_score",
        "e_hybrid_b50_ai50_score",
        "e_ai_quality_guard_score",
        "e_quality_score",
        "e_tradeability_score",
        "e_etf_integrity_score",
        "e_risk_control_score",
        "e_momentum_score",
        "switch_eval_mode",
        "switch_eval_stress",
    ]
    out = current[current["policy"].astype(str).eq(policy)].copy()
    for col in ["policy_weight", "sleeve_selection_prob", "e_baseline_selection_score"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out[[col for col in keep_cols if col in out.columns]].sort_values(
        ["e_series_role", "policy_weight", "ticker"], ascending=[True, False, True]
    )


def _role_summary(holdings: pd.DataFrame, label: str) -> pd.DataFrame:
    if holdings.empty:
        return pd.DataFrame()
    return (
        holdings.groupby(["e_series_role", "e_asset_bucket"], dropna=False)
        .agg(
            policy_weight=("policy_weight", "sum"),
            holdings=("ticker", "nunique"),
            avg_ai_prob=("sleeve_selection_prob", "mean"),
            avg_quality=("e_quality_score", "mean"),
            avg_integrity=("e_etf_integrity_score", "mean"),
        )
        .reset_index()
        .assign(policy=label)
    )


def _diff_holdings(base: pd.DataFrame, switch: pd.DataFrame) -> pd.DataFrame:
    base_cols = base[["ticker", "name", "e_series_role", "e_asset_bucket", "policy_weight"]].rename(
        columns={"policy_weight": "base_weight"}
    )
    switch_cols = switch[["ticker", "name", "e_series_role", "e_asset_bucket", "policy_weight", "effective_policy"]].rename(
        columns={"policy_weight": "switch_weight"}
    )
    diff = base_cols.merge(
        switch_cols,
        on=["ticker", "name", "e_series_role", "e_asset_bucket"],
        how="outer",
    )
    diff["base_weight"] = pd.to_numeric(diff["base_weight"], errors="coerce").fillna(0)
    diff["switch_weight"] = pd.to_numeric(diff["switch_weight"], errors="coerce").fillna(0)
    diff["weight_delta"] = diff["switch_weight"] - diff["base_weight"]
    diff["change_type"] = np.select(
        [
            diff["base_weight"].eq(0) & diff["switch_weight"].gt(0),
            diff["base_weight"].gt(0) & diff["switch_weight"].eq(0),
            diff["weight_delta"].abs().gt(1e-10),
        ],
        ["added_by_switch", "removed_by_switch", "weight_changed"],
        default="unchanged",
    )
    return diff.sort_values(["change_type", "e_series_role", "ticker"])


def build_compare(asof: str) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    current = _load_selected(asof)
    base = _policy_holdings(current, BASE_POLICY)
    switch = _policy_holdings(current, SWITCH_POLICY)
    if base.empty:
        raise SystemExit(f"missing base policy holdings: {BASE_POLICY}")
    if switch.empty:
        raise SystemExit(f"missing switch policy holdings: {SWITCH_POLICY}")

    diff = _diff_holdings(base, switch)
    role_summary = pd.concat([_role_summary(base, BASE_POLICY), _role_summary(switch, SWITCH_POLICY)], ignore_index=True)
    changed = diff[~diff["change_type"].eq("unchanged")].copy()
    turnover = float(diff["weight_delta"].abs().sum() / 2.0)

    token = _token(asof)
    base_path = REPORT_DIR / f"e_series_etf_mode_switch_base_holdings_{token}.csv"
    switch_path = REPORT_DIR / f"e_series_etf_mode_switch_switch_holdings_{token}.csv"
    diff_path = REPORT_DIR / f"e_series_etf_mode_switch_holdings_diff_{token}.csv"
    role_summary_path = REPORT_DIR / f"e_series_etf_mode_switch_holdings_role_summary_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_mode_switch_holdings_compare_{token}.json"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_holdings_compare_current.json"

    base.to_csv(base_path, index=False, encoding="utf-8-sig")
    switch.to_csv(switch_path, index=False, encoding="utf-8-sig")
    diff.to_csv(diff_path, index=False, encoding="utf-8-sig")
    role_summary.to_csv(role_summary_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_mode_switch_holdings_compare",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_policy": BASE_POLICY,
        "switch_policy": SWITCH_POLICY,
        "context": _current_context(asof),
        "summary": {
            "base_holding_count": int(base["ticker"].nunique()),
            "switch_holding_count": int(switch["ticker"].nunique()),
            "unchanged_count": int(diff["change_type"].eq("unchanged").sum()),
            "added_count": int(diff["change_type"].eq("added_by_switch").sum()),
            "removed_count": int(diff["change_type"].eq("removed_by_switch").sum()),
            "weight_changed_count": int(diff["change_type"].eq("weight_changed").sum()),
            "one_way_turnover": _safe_float(turnover),
        },
        "base_holdings": _records(base),
        "switch_holdings": _records(switch),
        "changed_holdings": _records(changed),
        "role_asset_summary": _records(role_summary),
        "outputs": {
            "base_holdings_csv": str(base_path),
            "switch_holdings_csv": str(switch_path),
            "diff_csv": str(diff_path),
            "role_summary_csv": str(role_summary_path),
            "json": str(json_path),
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build current holdings compare for E-series ETF mode switch policy.")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    payload = build_compare(str(args.asof))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "strategy_model_code": payload["strategy_model_code"],
                "as_of_date": payload["as_of_date"],
                "summary": payload["summary"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
