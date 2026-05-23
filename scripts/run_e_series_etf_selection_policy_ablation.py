from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_e_series_etf_sleeve_portfolio_backtest import POLICIES, _load_inputs


REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
STRATEGY_MODEL_CODE = "E-ETF-V01"
SLEEVE_MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"


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


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _candidate_policies() -> dict[str, dict[str, Any]]:
    return {
        key: value
        for key, value in POLICIES.items()
        if key
        in {
            "baseline_top3_role",
            "hybrid_b70_ai30_top3_role",
            "hybrid_b50_ai50_top3_role",
            "ai_quality_guard_top3_role",
            "ai_top3_role",
        }
    }


def _ensure_scores(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    group = [out["signal_date"], out["e_series_role"]]
    out["e_baseline_score_pct_in_role"] = out.groupby(group)["e_baseline_selection_score"].rank(pct=True)
    out["e_ai_prob_pct_in_role"] = out.groupby(group)["sleeve_selection_prob"].rank(pct=True)
    out["e_hybrid_b70_ai30_score"] = (
        out["e_baseline_score_pct_in_role"].fillna(0.5) * 0.70 + out["e_ai_prob_pct_in_role"].fillna(0.5) * 0.30
    )
    out["e_hybrid_b50_ai50_score"] = (
        out["e_baseline_score_pct_in_role"].fillna(0.5) * 0.50 + out["e_ai_prob_pct_in_role"].fillna(0.5) * 0.50
    )
    out["e_ai_quality_guard_score"] = (
        out["e_ai_prob_pct_in_role"].fillna(0.5) * 0.45
        + pd.to_numeric(out.get("e_quality_score"), errors="coerce").fillna(0.5) * 0.25
        + pd.to_numeric(out.get("e_risk_control_score_in_role"), errors="coerce")
        .fillna(pd.to_numeric(out.get("e_risk_control_score"), errors="coerce"))
        .fillna(0.5)
        * 0.15
        + pd.to_numeric(out.get("e_etf_integrity_score"), errors="coerce").fillna(0.5) * 0.15
    )
    return out


def _select_fixed_policy(data: pd.DataFrame, policy: str) -> pd.DataFrame:
    cfg = POLICIES[policy]
    score_col = cfg["score_col"]
    top_n = int(cfg["top_n"])
    selected = (
        data.sort_values(["signal_date", "e_series_role", score_col, "ticker"], ascending=[True, True, False, True])
        .groupby(["signal_date", "e_series_role"], group_keys=False)
        .head(top_n)
        .copy()
    )
    selected["effective_policy"] = policy
    selected["policy"] = policy
    selected["policy_label"] = cfg["label"]
    selected["selected_count_in_role"] = selected.groupby(["signal_date", "e_series_role"])["ticker"].transform("count")
    selected["policy_weight"] = selected["e_mode_role_weight"] / selected["selected_count_in_role"].replace(0, np.nan)
    return selected


def _segment_policy_stats(data: pd.DataFrame, segment_col: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for policy in _candidate_policies():
        selected = _select_fixed_policy(data, policy)
        for segment, frame in selected.groupby(segment_col, dropna=False):
            ret = pd.to_numeric(frame["fwd_ret_1m"], errors="coerce").dropna()
            risk_adj = pd.to_numeric(frame["risk_adj_1m"], errors="coerce").dropna()
            mdd = pd.to_numeric(frame["path_mdd_1m"], errors="coerce").dropna()
            rows.append(
                {
                    "segment_type": segment_col,
                    "segment": str(segment),
                    "policy": policy,
                    "policy_label": POLICIES[policy]["label"],
                    "selected_rows": int(len(frame)),
                    "priced_rows": int(ret.shape[0]),
                    "dates": int(frame["signal_date"].nunique()),
                    "avg_1m_ret": _safe_float(ret.mean()),
                    "win_rate": _safe_float((ret > 0).mean()) if not ret.empty else None,
                    "avg_1m_risk_adj": _safe_float(risk_adj.mean()),
                    "avg_1m_mdd": _safe_float(mdd.mean()),
                    "worst_1m_ret": _safe_float(ret.min()),
                }
            )
    stats = pd.DataFrame(rows)
    if stats.empty:
        return stats
    base = stats[stats["policy"].eq("baseline_top3_role")][
        ["segment_type", "segment", "avg_1m_ret", "avg_1m_risk_adj", "worst_1m_ret"]
    ].rename(
        columns={
            "avg_1m_ret": "baseline_avg_1m_ret",
            "avg_1m_risk_adj": "baseline_avg_1m_risk_adj",
            "worst_1m_ret": "baseline_worst_1m_ret",
        }
    )
    stats = stats.merge(base, on=["segment_type", "segment"], how="left")
    stats["avg_1m_ret_delta"] = pd.to_numeric(stats["avg_1m_ret"], errors="coerce") - pd.to_numeric(
        stats["baseline_avg_1m_ret"], errors="coerce"
    )
    stats["avg_1m_risk_adj_delta"] = pd.to_numeric(stats["avg_1m_risk_adj"], errors="coerce") - pd.to_numeric(
        stats["baseline_avg_1m_risk_adj"], errors="coerce"
    )
    stats["worst_1m_ret_delta"] = pd.to_numeric(stats["worst_1m_ret"], errors="coerce") - pd.to_numeric(
        stats["baseline_worst_1m_ret"], errors="coerce"
    )
    return stats.sort_values(["segment_type", "segment", "avg_1m_risk_adj", "avg_1m_ret"], ascending=[True, True, False, False])


def _best_policy_map(stats: pd.DataFrame, segment_col: str, min_rows: int = 12) -> dict[str, str]:
    use = stats[(stats["segment_type"].eq(segment_col)) & (stats["priced_rows"].ge(min_rows))].copy()
    if use.empty:
        return {}
    use = use.sort_values(
        ["segment", "avg_1m_risk_adj", "avg_1m_ret", "worst_1m_ret"],
        ascending=[True, False, False, False],
    )
    best = use.groupby("segment", as_index=False).head(1)
    return dict(zip(best["segment"].astype(str), best["policy"].astype(str)))


def _select_adaptive_policy(
    data: pd.DataFrame,
    policy_name: str,
    role_map: dict[str, str],
    asset_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    policy_cfg = _candidate_policies()
    for (signal_date, role), frame in data.groupby(["signal_date", "e_series_role"], dropna=False):
        work = frame.copy()
        chosen_policy: list[str] = []
        chosen_score: list[float] = []
        for _, row in work.iterrows():
            role_key = str(role)
            asset_key = str(row.get("e_asset_bucket"))
            policy = (asset_map or {}).get(asset_key) or role_map.get(role_key) or "baseline_top3_role"
            score_col = policy_cfg[policy]["score_col"]
            chosen_policy.append(policy)
            chosen_score.append(float(row.get(score_col, np.nan)) if pd.notna(row.get(score_col, np.nan)) else np.nan)
        work["effective_policy"] = chosen_policy
        work["_adaptive_score"] = chosen_score
        selected = work.sort_values(["_adaptive_score", "ticker"], ascending=[False, True]).head(3).copy()
        selected["policy"] = policy_name
        selected["policy_label"] = policy_name
        selected["selected_count_in_role"] = len(selected)
        selected["policy_weight"] = selected["e_mode_role_weight"] / selected["selected_count_in_role"]
        rows.append(selected)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _period_returns(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (policy, signal_date), frame in selected.groupby(["policy", "signal_date"], dropna=False):
        valid = frame[frame["fwd_ret_1m"].notna()].copy()
        weights = pd.to_numeric(valid["policy_weight"], errors="coerce").fillna(0)
        rows.append(
            {
                "policy": policy,
                "signal_date": signal_date,
                "regime_mode": frame["e_market_mode"].mode().iloc[0] if not frame.empty else None,
                "selected_count": int(len(frame)),
                "priced_count": int(len(valid)),
                "effective_weight": _safe_float(weights.sum()),
                "period_return": _safe_float((valid["fwd_ret_1m"] * weights).sum()),
                "period_risk_adj": _safe_float((valid["risk_adj_1m"] * weights).sum()),
                "period_path_mdd_proxy": _safe_float((valid["path_mdd_1m"] * weights).sum()),
            }
        )
    return pd.DataFrame(rows)


def _portfolio_summary(periods: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for policy, frame in periods.groupby("policy", dropna=False):
        ret = pd.to_numeric(frame["period_return"], errors="coerce").dropna()
        risk_adj = pd.to_numeric(frame["period_risk_adj"], errors="coerce").dropna()
        mdd = pd.to_numeric(frame["period_path_mdd_proxy"], errors="coerce").dropna()
        rows.append(
            {
                "policy": policy,
                "periods": int(len(frame)),
                "priced_periods": int(ret.shape[0]),
                "avg_1m_ret": _safe_float(ret.mean()),
                "median_1m_ret": _safe_float(ret.median()),
                "win_rate": _safe_float((ret > 0).mean()) if not ret.empty else None,
                "avg_1m_risk_adj": _safe_float(risk_adj.mean()),
                "avg_1m_mdd_proxy": _safe_float(mdd.mean()),
                "worst_1m_ret": _safe_float(ret.min()),
                "compounded_validation_return": _safe_float((1.0 + ret).prod() - 1.0) if not ret.empty else None,
            }
        )
    out = pd.DataFrame(rows)
    base = out[out["policy"].eq("baseline_top3_role")]
    if not base.empty:
        base_row = base.iloc[0]
        for col in ["avg_1m_ret", "win_rate", "avg_1m_risk_adj", "avg_1m_mdd_proxy", "worst_1m_ret", "compounded_validation_return"]:
            out[f"baseline_{col}"] = base_row[col]
            out[f"{col}_delta"] = pd.to_numeric(out[col], errors="coerce") - pd.to_numeric(base_row[col], errors="coerce")
    return out.sort_values(["avg_1m_risk_adj", "avg_1m_ret"], ascending=False, na_position="last")


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame, role_best: pd.DataFrame, asset_best: pd.DataFrame) -> None:
    lines = [
        "# E-Series ETF Selection Policy Ablation",
        "",
        f"- strategy model: `{payload['strategy_model_code']}`",
        f"- sleeve model: `{payload['sleeve_model_code']}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- valid start: `{payload['valid_start']}`",
        "",
        "## Portfolio Summary",
        "",
        "| policy | avg 1M ret | return delta | win | risk adj | risk adj delta | MDD proxy | worst 1M | compounded |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['policy']}` | {_fmt_pct(row.get('avg_1m_ret'))} | {_fmt_pct(row.get('avg_1m_ret_delta'))} | "
            f"{_fmt_pct(row.get('win_rate'))} | {_fmt_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_fmt_pct(row.get('avg_1m_risk_adj_delta'))} | {_fmt_pct(row.get('avg_1m_mdd_proxy'))} | "
            f"{_fmt_pct(row.get('worst_1m_ret'))} | {_fmt_pct(row.get('compounded_validation_return'))} |"
        )
    lines.extend(["", "## Best Policy By Role", "", "| role | best policy | risk adj | return | rows |", "| --- | --- | ---: | ---: | ---: |"])
    for _, row in role_best.iterrows():
        lines.append(
            f"| `{row['segment']}` | `{row['policy']}` | {_fmt_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_fmt_pct(row.get('avg_1m_ret'))} | {int(row.get('priced_rows', 0))} |"
        )
    lines.extend(["", "## Best Policy By Asset Bucket", "", "| asset bucket | best policy | risk adj | return | rows |", "| --- | --- | ---: | ---: | ---: |"])
    for _, row in asset_best.head(25).iterrows():
        lines.append(
            f"| `{row['segment']}` | `{row['policy']}` | {_fmt_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_fmt_pct(row.get('avg_1m_ret'))} | {int(row.get('priced_rows', 0))} |"
        )
    lines.extend(
        [
            "",
            "## Note",
            "",
            "- 이 실험은 현재 validation 구간 기준 adaptive ablation입니다.",
            "- 바로 운영 정책으로 승격하기보다는 다음 단계에서 walk-forward 방식으로 재검증해야 합니다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_ablation(asof: str, valid_start: str) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    data = _ensure_scores(_load_inputs(asof))
    data = data[data["signal_date"].ge(valid_start)].copy()

    role_stats = _segment_policy_stats(data, "e_series_role")
    asset_stats = _segment_policy_stats(data, "e_asset_bucket")
    segment_stats = pd.concat([role_stats, asset_stats], ignore_index=True)
    role_map = _best_policy_map(segment_stats, "e_series_role", min_rows=12)
    asset_map = _best_policy_map(segment_stats, "e_asset_bucket", min_rows=12)

    selected_parts = [_select_fixed_policy(data, "baseline_top3_role")]
    selected_parts.extend(_select_fixed_policy(data, policy) for policy in ["hybrid_b50_ai50_top3_role", "hybrid_b70_ai30_top3_role"])
    selected_parts.append(_select_adaptive_policy(data, "role_adaptive_best_policy", role_map))
    selected_parts.append(_select_adaptive_policy(data, "asset_adaptive_best_policy", role_map={}, asset_map=asset_map))
    selected_parts.append(_select_adaptive_policy(data, "role_asset_adaptive_best_policy", role_map=role_map, asset_map=asset_map))
    selected = pd.concat([part for part in selected_parts if not part.empty], ignore_index=True)

    periods = _period_returns(selected)
    summary = _portfolio_summary(periods)
    role_best = (
        role_stats.sort_values(["segment", "avg_1m_risk_adj", "avg_1m_ret", "worst_1m_ret"], ascending=[True, False, False, False])
        .groupby("segment", as_index=False)
        .head(1)
    )
    asset_best = (
        asset_stats.sort_values(["segment", "avg_1m_risk_adj", "avg_1m_ret", "worst_1m_ret"], ascending=[True, False, False, False])
        .groupby("segment", as_index=False)
        .head(1)
    )

    segment_path = REPORT_DIR / f"e_series_etf_selection_policy_segment_ablation_{token}.csv"
    selected_path = REPORT_DIR / f"e_series_etf_selection_policy_ablation_selected_{token}.csv"
    periods_path = REPORT_DIR / f"e_series_etf_selection_policy_ablation_periods_{token}.csv"
    summary_path = REPORT_DIR / f"e_series_etf_selection_policy_ablation_summary_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_selection_policy_ablation_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_selection_policy_ablation_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_selection_policy_ablation_current.json"

    segment_stats.to_csv(segment_path, index=False, encoding="utf-8-sig")
    selected.to_csv(selected_path, index=False, encoding="utf-8-sig")
    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_selection_policy_ablation",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "valid_start": valid_start,
        "candidate_policies": _candidate_policies(),
        "role_policy_map": role_map,
        "asset_policy_map": asset_map,
        "best_portfolio_policy": _records(summary.head(1)),
        "portfolio_summary": _records(summary),
        "best_by_role": _records(role_best),
        "best_by_asset_bucket": _records(asset_best),
        "outputs": {
            "segment_ablation_csv": str(segment_path),
            "selected_csv": str(selected_path),
            "periods_csv": str(periods_path),
            "summary_csv": str(summary_path),
            "json": str(json_path),
            "markdown": str(md_path),
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, summary, role_best, asset_best)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E-series ETF role/asset bucket selection policy ablation.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run_ablation(str(args.asof), str(args.valid_start))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "strategy_model_code": payload["strategy_model_code"],
                "as_of_date": payload["as_of_date"],
                "best_portfolio_policy": payload["best_portfolio_policy"],
                "role_policy_map": payload["role_policy_map"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
