from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline


ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_e_series_etf_sleeve_selection_ai_v1 import TARGET_LABEL, _feature_columns, _preprocessor
from scripts.run_e_series_etf_selection_policy_ablation import _ensure_scores, _load_inputs


REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
STRATEGY_MODEL_CODE = "E-ETF-V01"
SLEEVE_MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"
BASE_POLICY = "hybrid_b50_ai50_top3_role"
TAIL_POLICY = "wf_tail_asset_policy"


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


def _pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _load_scored_data(asof: str, valid_start: str) -> pd.DataFrame:
    data = _ensure_scores(_load_inputs(asof))
    data["signal_date"] = pd.to_datetime(data["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return data[data["signal_date"].ge(valid_start)].copy()


def _policy_score_col(policy: str) -> str:
    return {
        "baseline_top3_role": "e_baseline_selection_score",
        "hybrid_b50_ai50_top3_role": "e_hybrid_b50_ai50_score",
        "hybrid_b70_ai30_top3_role": "e_hybrid_b70_ai30_score",
        "ai_quality_guard_top3_role": "e_ai_quality_guard_score",
        "ai_top3_role": "sleeve_selection_prob",
    }.get(policy, "e_hybrid_b50_ai50_score")


def _select_top3_by_role(data: pd.DataFrame, policy: str, gate: str = "none") -> pd.DataFrame:
    score_col = _policy_score_col(policy)
    rows: list[pd.DataFrame] = []
    for (signal_date, role), frame in data.groupby(["signal_date", "e_series_role"], dropna=False):
        work = frame.copy()
        original = work.copy()
        if gate == "liq_integrity_p20":
            work = work[
                pd.to_numeric(work.get("e_tradeability_score"), errors="coerce").fillna(0.5).ge(0.20)
                & pd.to_numeric(work.get("e_etf_integrity_score"), errors="coerce").fillna(0.5).ge(0.20)
            ].copy()
        elif gate == "liq_integrity_p30_premium":
            premium = pd.to_numeric(work.get("etf_metric_premium_discount_abs"), errors="coerce").fillna(0)
            work = work[
                pd.to_numeric(work.get("e_tradeability_score"), errors="coerce").fillna(0.5).ge(0.30)
                & pd.to_numeric(work.get("e_etf_integrity_score"), errors="coerce").fillna(0.5).ge(0.30)
                & premium.le(0.03)
            ].copy()
        elif gate == "quality_guard_p40":
            work = work[
                pd.to_numeric(work.get("e_quality_score"), errors="coerce").fillna(0.5).ge(0.40)
                & pd.to_numeric(work.get("e_tracking_quality_score_in_role"), errors="coerce").fillna(0.5).ge(0.30)
            ].copy()
        if work.empty:
            work = original
        selected = work.sort_values([score_col, "ticker"], ascending=[False, True]).head(3).copy()
        selected["policy"] = f"{policy}__gate_{gate}"
        selected["effective_policy"] = policy
        selected["gate"] = gate
        selected["selected_count_in_role"] = len(selected)
        selected["policy_weight"] = pd.to_numeric(selected["e_mode_role_weight"], errors="coerce") / max(len(selected), 1)
        rows.append(selected)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _period_returns(selected: pd.DataFrame, policy_col: str = "policy") -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (policy, signal_date), frame in selected.groupby([policy_col, "signal_date"], dropna=False):
        valid = frame[frame["fwd_ret_1m"].notna()].copy()
        weights = pd.to_numeric(valid["policy_weight"], errors="coerce").fillna(0)
        rows.append(
            {
                "policy": policy,
                "signal_date": signal_date,
                "holding_count": int(frame["ticker"].nunique()),
                "period_return": _safe_float((valid["fwd_ret_1m"] * weights).sum()),
                "period_risk_adj": _safe_float((valid["risk_adj_1m"] * weights).sum()),
                "period_mdd_proxy": _safe_float((valid["path_mdd_1m"] * weights).sum()),
            }
        )
    return pd.DataFrame(rows)


def _summary(periods: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for policy, frame in periods.groupby("policy", dropna=False):
        ret = pd.to_numeric(frame["period_return"], errors="coerce").dropna()
        risk = pd.to_numeric(frame["period_risk_adj"], errors="coerce").dropna()
        mdd = pd.to_numeric(frame["period_mdd_proxy"], errors="coerce").dropna()
        rows.append(
            {
                "policy": policy,
                "periods": int(len(frame)),
                "avg_1m_ret": _safe_float(ret.mean()),
                "win_rate": _safe_float((ret > 0).mean()) if not ret.empty else None,
                "avg_1m_risk_adj": _safe_float(risk.mean()),
                "avg_1m_mdd_proxy": _safe_float(mdd.mean()),
                "worst_1m_ret": _safe_float(ret.min()),
                "compounded_return": _safe_float((1 + ret).prod() - 1) if not ret.empty else None,
            }
        )
    out = pd.DataFrame(rows)
    base = out[out["policy"].astype(str).eq(f"{BASE_POLICY}__gate_none")]
    if not base.empty:
        base_row = base.iloc[0]
        for col in ["avg_1m_ret", "avg_1m_risk_adj", "worst_1m_ret", "compounded_return"]:
            out[f"{col}_delta_vs_base"] = pd.to_numeric(out[col], errors="coerce") - pd.to_numeric(base_row[col], errors="coerce")
    return out.sort_values(["avg_1m_risk_adj", "avg_1m_ret"], ascending=False, na_position="last")


def run_gate_test(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = pd.concat(
        [_select_top3_by_role(data, BASE_POLICY, gate) for gate in ["none", "liq_integrity_p20", "liq_integrity_p30_premium", "quality_guard_p40"]],
        ignore_index=True,
    )
    periods = _period_returns(selected)
    return selected, _summary(periods)


def _fit_role_model(train: pd.DataFrame, numeric: list[str], categorical: list[str]) -> Pipeline:
    model = GradientBoostingClassifier(random_state=42, n_estimators=120, max_depth=3)
    return Pipeline([("preprocess", _preprocessor(numeric, categorical)), ("model", model)]).fit(
        train[numeric + categorical],
        train["_target"],
    )


def run_role_label_test(asof: str) -> pd.DataFrame:
    token = _token(asof)
    mart_path = REPORT_DIR / f"e_series_etf_mart_v2_{token}.csv"
    scores_path = REPORT_DIR / f"e_series_etf_sleeve_selection_valid_scored_{token}.csv"
    mart = pd.read_csv(mart_path, dtype={"ticker": str}, low_memory=False)
    scores = pd.read_csv(scores_path, dtype={"ticker": str}, low_memory=False)
    mart["ticker"] = mart["ticker"].astype(str).str.zfill(6)
    scores["ticker"] = scores["ticker"].astype(str).str.zfill(6)
    mart["signal_date"] = pd.to_datetime(mart["signal_date"], errors="coerce")
    scores["signal_date"] = pd.to_datetime(scores["signal_date"], errors="coerce")
    labeled = mart[mart[TARGET_LABEL].notna()].copy()
    labeled["_target"] = pd.to_numeric(labeled[TARGET_LABEL], errors="coerce")
    labeled = labeled[labeled["_target"].isin([0, 1])].copy()
    numeric, categorical = _feature_columns(labeled)
    rows: list[dict[str, Any]] = []
    for role, frame in labeled.groupby("e_series_role", dropna=False):
        train = frame[frame["signal_date"].le(pd.Timestamp("2025-12-31"))].copy()
        valid = frame[(frame["signal_date"].ge(pd.Timestamp("2026-01-01"))) & (frame["signal_date"].le(pd.Timestamp(asof)))].copy()
        common = scores[scores["e_series_role"].astype(str).eq(str(role))].copy() if "e_series_role" in scores.columns else pd.DataFrame()
        common_auc = np.nan
        if not common.empty and common["_target"].nunique() > 1:
            common_auc = roc_auc_score(common["_target"], common["sleeve_selection_prob"])
        role_auc = np.nan
        status = "insufficient_samples"
        if len(train) >= 80 and len(valid) >= 20 and train["_target"].nunique() > 1 and valid["_target"].nunique() > 1:
            model = _fit_role_model(train, numeric, categorical)
            prob = model.predict_proba(valid[numeric + categorical])[:, 1]
            role_auc = roc_auc_score(valid["_target"], prob)
            status = "candidate" if pd.notna(role_auc) and (pd.isna(common_auc) or role_auc >= common_auc) else "observe_only"
        rows.append(
            {
                "e_series_role": role,
                "train_rows": int(len(train)),
                "valid_rows": int(len(valid)),
                "positive_rate": _safe_float(valid["_target"].mean()) if not valid.empty else None,
                "common_auc": _safe_float(common_auc),
                "role_specific_auc": _safe_float(role_auc),
                "auc_delta": _safe_float(role_auc - common_auc) if pd.notna(role_auc) and pd.notna(common_auc) else None,
                "status": status,
            }
        )
    return pd.DataFrame(rows).sort_values(["status", "auc_delta"], ascending=[True, False], na_position="last")


def _stress_score(row: pd.Series) -> float:
    vals = [
        pd.to_numeric(pd.Series([row.get("qm_risk_market_stress_score")]), errors="coerce").iloc[0],
        pd.to_numeric(pd.Series([row.get("qm_risk_drawdown_pressure_score")]), errors="coerce").iloc[0],
        pd.to_numeric(pd.Series([row.get("qm_market_risk_off_score")]), errors="coerce").iloc[0],
    ]
    vals = [float(v) for v in vals if pd.notna(v)]
    return max(vals) if vals else 0.0


def _load_mode_switch_selected(asof: str) -> pd.DataFrame:
    path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_selected_{_token(asof)}.csv"
    selected = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    selected["ticker"] = selected["ticker"].astype(str).str.zfill(6)
    selected["signal_date"] = pd.to_datetime(selected["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return selected


def _date_context(selected: pd.DataFrame) -> pd.DataFrame:
    base = selected[selected["policy"].eq(BASE_POLICY)].copy()
    rows: list[dict[str, Any]] = []
    for signal_date, frame in base.groupby("signal_date", dropna=False):
        row = {"signal_date": signal_date, "e_market_mode": frame["e_market_mode"].mode().iloc[0] if "e_market_mode" in frame.columns else None}
        for col in ["qm_risk_market_stress_score", "qm_risk_drawdown_pressure_score", "qm_market_risk_off_score"]:
            vals = pd.to_numeric(frame.get(col), errors="coerce").dropna()
            row[col] = float(vals.median()) if not vals.empty else np.nan
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("signal_date").reset_index(drop=True)
    out["stress_score"] = out.apply(_stress_score, axis=1)
    return out


def _hysteresis_states(context: pd.DataFrame, enter: float, exit: float, min_hold: int) -> pd.DataFrame:
    rows = []
    state = False
    hold = 0
    for _, row in context.iterrows():
        score = float(row["stress_score"])
        if state:
            hold += 1
            if hold >= min_hold and score <= exit:
                state = False
                hold = 0
        elif score >= enter:
            state = True
            hold = 1
        item = row.to_dict()
        item["is_stress"] = state
        item["enter_threshold"] = enter
        item["exit_threshold"] = exit
        item["min_hold"] = min_hold
        rows.append(item)
    return pd.DataFrame(rows)


def _select_from_states(selected: pd.DataFrame, states: pd.DataFrame, policy_name: str) -> pd.DataFrame:
    parts = []
    for _, state in states.iterrows():
        source_policy = TAIL_POLICY if bool(state["is_stress"]) else BASE_POLICY
        part = selected[selected["signal_date"].eq(state["signal_date"]) & selected["policy"].eq(source_policy)].copy()
        part["policy"] = policy_name
        part["source_policy"] = source_policy
        parts.append(part)
    return pd.concat([p for p in parts if not p.empty], ignore_index=True) if parts else pd.DataFrame()


def _state_summary(states: pd.DataFrame, policy_name: str) -> dict[str, Any]:
    flags = states["is_stress"].astype(bool).tolist()
    transitions = sum(1 for i in range(1, len(flags)) if flags[i] != flags[i - 1])
    flips = 0
    for i, flag in enumerate(flags):
        prev_same = i > 0 and flags[i - 1] == flag
        next_same = i + 1 < len(flags) and flags[i + 1] == flag
        if not prev_same and not next_same:
            flips += 1
    return {"policy": policy_name, "stress_dates": int(sum(flags)), "transitions": int(transitions), "single_flips": int(flips)}


def _cap_single_weights(frame: pd.DataFrame, cap: float) -> pd.DataFrame:
    out = frame.copy()
    weights = pd.to_numeric(out["policy_weight"], errors="coerce").fillna(0)
    excess = weights.sub(cap).clip(lower=0).sum()
    out["policy_weight"] = weights.clip(upper=cap)
    if excess > 0:
        receivers = out["e_series_role"].astype(str).isin(["CASH_LIKE", "DEFENSIVE", "INCOME"])
        if not receivers.any():
            receivers = pd.Series(True, index=out.index)
        base = out.loc[receivers, "policy_weight"]
        denom = float(base.sum())
        if denom > 0:
            out.loc[receivers, "policy_weight"] = base + excess * base / denom
        else:
            out.loc[receivers, "policy_weight"] = base + excess / max(int(receivers.sum()), 1)
    total = out["policy_weight"].sum()
    if total > 0:
        out["policy_weight"] = out["policy_weight"] / total
    return out


def _cap_high_risk(frame: pd.DataFrame, cap: float) -> pd.DataFrame:
    out = frame.copy()
    risk_control = pd.to_numeric(out.get("e_risk_control_score_in_role"), errors="coerce").fillna(
        pd.to_numeric(out.get("e_risk_control_score"), errors="coerce")
    ).fillna(0.5)
    high_risk = (
        risk_control.lt(0.25)
        | out.get("e_strategy_bucket", "").astype(str).isin(["LEVERAGED_TACTICAL", "INVERSE_HEDGE"])
        | out.get("e_product_structure", "").astype(str).str.contains("LEVERAGED|INVERSE", regex=True)
    )
    high_weight = pd.to_numeric(out.loc[high_risk, "policy_weight"], errors="coerce").fillna(0).sum()
    if high_weight <= cap:
        return out
    scale = cap / high_weight if high_weight > 0 else 1.0
    original = pd.to_numeric(out["policy_weight"], errors="coerce").fillna(0)
    out.loc[high_risk, "policy_weight"] = original.loc[high_risk] * scale
    excess = float(original.sum() - out["policy_weight"].sum())
    receivers = ~high_risk
    if receivers.any() and excess > 0:
        base = out.loc[receivers, "policy_weight"]
        denom = float(base.sum())
        out.loc[receivers, "policy_weight"] = base + excess * base / denom if denom > 0 else base + excess / int(receivers.sum())
    return out


def run_hysteresis_and_risk_cap(asof: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selected = _load_mode_switch_selected(asof)
    context = _date_context(selected)
    variants = [
        ("no_hysteresis_base", _hysteresis_states(context, enter=2.5, exit=2.5, min_hold=1)),
        ("hysteresis_base", _hysteresis_states(context, enter=2.7, exit=2.0, min_hold=2)),
        ("hysteresis_tight", _hysteresis_states(context, enter=2.9, exit=2.1, min_hold=2)),
    ]
    selected_variants = []
    state_rows = []
    for name, states in variants:
        state_rows.append(states.assign(policy=name))
        selected_variants.append(_select_from_states(selected, states, name))
    hys_selected = pd.concat(selected_variants, ignore_index=True)
    hys_summary = _summary(_period_returns(hys_selected))
    state_summary = pd.DataFrame([_state_summary(states, name) for name, states in variants])
    hys_summary = hys_summary.merge(state_summary, on="policy", how="left")

    best_policy = str(hys_summary.sort_values(["avg_1m_risk_adj", "avg_1m_ret"], ascending=False).iloc[0]["policy"])
    base = hys_selected[hys_selected["policy"].eq(best_policy)].copy()
    risk_parts = []
    for name, func in [
        ("risk_cap_none", lambda x: x),
        ("single_8pct_cap", lambda x: _cap_single_weights(x, 0.08)),
        ("single_8pct_highrisk_30pct_cap", lambda x: _cap_high_risk(_cap_single_weights(x, 0.08), 0.30)),
    ]:
        capped = base.groupby("signal_date", group_keys=False).apply(func).copy()
        capped["policy"] = name
        capped["source_hysteresis_policy"] = best_policy
        risk_parts.append(capped)
    risk_selected = pd.concat(risk_parts, ignore_index=True)
    risk_summary = _summary(_period_returns(risk_selected))
    return hys_summary, risk_summary, pd.concat(state_rows, ignore_index=True)


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# E-Series ETF Operational Hardening",
        "",
        f"- 기준일: `{payload['as_of_date']}`",
        "",
        "## 1. ETF 유동성/괴리율 Gate",
        "",
        "| policy | avg 1M | risk adj | worst | compounded |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["liquidity_gate_summary"]:
        lines.append(
            f"| `{row['policy']}` | {_pct(row.get('avg_1m_ret'))} | {_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_pct(row.get('worst_1m_ret'))} | {_pct(row.get('compounded_return'))} |"
        )
    lines.extend(["", "## 2. Role-Specific Label", "", "| role | common AUC | role AUC | delta | status |", "| --- | ---: | ---: | ---: | --- |"])
    for row in payload["role_label_summary"]:
        lines.append(
            f"| `{row['e_series_role']}` | {_pct(row.get('common_auc'))} | {_pct(row.get('role_specific_auc'))} | "
            f"{_pct(row.get('auc_delta'))} | `{row['status']}` |"
        )
    lines.extend(["", "## 3. Hysteresis", "", "| policy | avg 1M | risk adj | worst | stress dates | flips |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in payload["hysteresis_summary"]:
        lines.append(
            f"| `{row['policy']}` | {_pct(row.get('avg_1m_ret'))} | {_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_pct(row.get('worst_1m_ret'))} | {row.get('stress_dates')} | {row.get('single_flips')} |"
        )
    lines.extend(["", "## 4. Portfolio Risk Cap", "", "| policy | avg 1M | risk adj | worst | compounded |", "| --- | ---: | ---: | ---: | ---: |"])
    for row in payload["risk_cap_summary"]:
        lines.append(
            f"| `{row['policy']}` | {_pct(row.get('avg_1m_ret'))} | {_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_pct(row.get('worst_1m_ret'))} | {_pct(row.get('compounded_return'))} |"
        )
    lines.extend(
        [
            "",
            "## 운영 판단",
            "",
            "- gate, role label, hysteresis, risk cap은 모두 shadow hardening 후보로 둔다.",
            "- 운영 기본값을 바로 교체하지 않고 다음 데이터 업데이트 후 재현성을 확인한다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(asof: str, valid_start: str) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    data = _load_scored_data(asof, valid_start)
    gate_selected, gate_summary = run_gate_test(data)
    role_label = run_role_label_test(asof)
    hys_summary, risk_summary, states = run_hysteresis_and_risk_cap(asof)

    gate_path = REPORT_DIR / f"e_series_etf_operational_hardening_gate_selected_{token}.csv"
    gate_summary_path = REPORT_DIR / f"e_series_etf_operational_hardening_gate_summary_{token}.csv"
    role_path = REPORT_DIR / f"e_series_etf_operational_hardening_role_label_{token}.csv"
    hys_path = REPORT_DIR / f"e_series_etf_operational_hardening_hysteresis_{token}.csv"
    risk_path = REPORT_DIR / f"e_series_etf_operational_hardening_risk_cap_{token}.csv"
    states_path = REPORT_DIR / f"e_series_etf_operational_hardening_states_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_operational_hardening_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_operational_hardening_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_operational_hardening_current.json"

    gate_selected.to_csv(gate_path, index=False, encoding="utf-8-sig")
    gate_summary.to_csv(gate_summary_path, index=False, encoding="utf-8-sig")
    role_label.to_csv(role_path, index=False, encoding="utf-8-sig")
    hys_summary.to_csv(hys_path, index=False, encoding="utf-8-sig")
    risk_summary.to_csv(risk_path, index=False, encoding="utf-8-sig")
    states.to_csv(states_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_operational_hardening",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "as_of_date": asof,
        "valid_start": valid_start,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "liquidity_gate_summary": _records(gate_summary),
        "role_label_summary": _records(role_label),
        "hysteresis_summary": _records(hys_summary),
        "risk_cap_summary": _records(risk_summary),
        "recommendation": {
            "liquidity_gate": str(gate_summary.iloc[0]["policy"]) if not gate_summary.empty else None,
            "role_label": "role_specific_candidate_only_where_auc_improves",
            "hysteresis": str(hys_summary.iloc[0]["policy"]) if not hys_summary.empty else None,
            "risk_cap": str(risk_summary.iloc[0]["policy"]) if not risk_summary.empty else None,
            "operation_status": "shadow_hardening_candidate",
        },
        "outputs": {
            "gate_selected_csv": str(gate_path),
            "gate_summary_csv": str(gate_summary_path),
            "role_label_csv": str(role_path),
            "hysteresis_csv": str(hys_path),
            "risk_cap_csv": str(risk_path),
            "states_csv": str(states_path),
            "json": str(json_path),
            "markdown": str(md_path),
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E-series ETF operational hardening tests.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run(str(args.asof), str(args.valid_start))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "as_of_date": payload["as_of_date"],
                "recommendation": payload["recommendation"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
