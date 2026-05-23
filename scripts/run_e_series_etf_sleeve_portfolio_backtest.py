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
POLICIES = {
    "baseline_top3_role": {"score_col": "e_baseline_selection_score", "top_n": 3, "label": "Baseline rule Top3 per role"},
    "ai_top1_role": {"score_col": "sleeve_selection_prob", "top_n": 1, "label": "AI Top1 per role"},
    "ai_top3_role": {"score_col": "sleeve_selection_prob", "top_n": 3, "label": "AI Top3 per role"},
    "ai_top5_role": {"score_col": "sleeve_selection_prob", "top_n": 5, "label": "AI Top5 per role"},
    "hybrid_b70_ai30_top3_role": {
        "score_col": "e_hybrid_b70_ai30_score",
        "top_n": 3,
        "label": "Hybrid baseline 70% + AI 30% Top3 per role",
    },
    "hybrid_b50_ai50_top3_role": {
        "score_col": "e_hybrid_b50_ai50_score",
        "top_n": 3,
        "label": "Hybrid baseline 50% + AI 50% Top3 per role",
    },
    "ai_quality_guard_top3_role": {
        "score_col": "e_ai_quality_guard_score",
        "top_n": 3,
        "label": "AI + quality/risk guard Top3 per role",
    },
}


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


def _load_inputs(asof: str) -> pd.DataFrame:
    token = _token(asof)
    mart_path = REPORT_DIR / f"e_series_etf_mart_v2_{token}.csv"
    valid_score_path = REPORT_DIR / f"e_series_etf_sleeve_selection_valid_scored_{token}.csv"
    current_score_path = REPORT_DIR / f"e_series_etf_sleeve_selection_current_scores_{token}.csv"
    if not mart_path.exists():
        raise SystemExit(f"missing mart: {mart_path}")
    if not valid_score_path.exists() or not current_score_path.exists():
        raise SystemExit("missing sleeve selection scores. Run build_e_series_etf_sleeve_selection_ai_v1.py first.")

    mart = pd.read_csv(mart_path, dtype={"ticker": str}, low_memory=False)
    valid_scores = pd.read_csv(valid_score_path, dtype={"ticker": str}, low_memory=False)
    current_scores = pd.read_csv(current_score_path, dtype={"ticker": str}, low_memory=False)
    for df in [mart, valid_scores, current_scores]:
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
        df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    scores = pd.concat(
        [
            valid_scores[["signal_date", "ticker", "sleeve_selection_prob"]],
            current_scores[["signal_date", "ticker", "sleeve_selection_prob"]],
        ],
        ignore_index=True,
    ).drop_duplicates(["signal_date", "ticker"], keep="last")

    out = mart.merge(scores, on=["signal_date", "ticker"], how="left")
    out = out[out["sleeve_selection_prob"].notna()].copy()
    for col in [
        "e_mode_role_weight",
        "e_baseline_selection_score",
        "sleeve_selection_prob",
        "fwd_ret_1m",
        "path_mdd_1m",
        "risk_adj_1m",
    ]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
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
        out["e_ai_prob_pct_in_role"].fillna(0.5) * 0.50
        + pd.to_numeric(out.get("e_quality_score"), errors="coerce").fillna(0.5) * 0.30
        + pd.to_numeric(out.get("e_risk_control_score"), errors="coerce").fillna(0.5) * 0.20
    )
    return out


def _select_policy(frame: pd.DataFrame, policy: str) -> pd.DataFrame:
    cfg = POLICIES[policy]
    score_col = cfg["score_col"]
    top_n = int(cfg["top_n"])
    selected = (
        frame.sort_values(["signal_date", "e_series_role", score_col, "ticker"], ascending=[True, True, False, True])
        .groupby(["signal_date", "e_series_role"], group_keys=False)
        .head(top_n)
        .copy()
    )
    selected["selected_count_in_role"] = selected.groupby(["signal_date", "e_series_role"])["ticker"].transform("count")
    selected["policy"] = policy
    selected["policy_label"] = cfg["label"]
    selected["policy_weight"] = selected["e_mode_role_weight"] / selected["selected_count_in_role"].replace(0, np.nan)
    return selected


def _period_returns(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (policy, signal_date), frame in selected.groupby(["policy", "signal_date"], dropna=False):
        valid = frame[frame["fwd_ret_1m"].notna()].copy()
        weight = pd.to_numeric(valid["policy_weight"], errors="coerce").fillna(0)
        rows.append(
            {
                "policy": policy,
                "signal_date": signal_date,
                "regime_mode": frame["e_market_mode"].mode().iloc[0] if "e_market_mode" in frame.columns and not frame.empty else None,
                "selected_count": int(len(frame)),
                "priced_count": int(len(valid)),
                "effective_weight": _safe_float(weight.sum()),
                "period_return": _safe_float((valid["fwd_ret_1m"] * weight).sum()),
                "period_risk_adj": _safe_float((valid["risk_adj_1m"] * weight).sum()),
                "period_path_mdd_proxy": _safe_float((valid["path_mdd_1m"] * weight).sum()),
            }
        )
    return pd.DataFrame(rows)


def _summary(periods: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for policy, frame in periods.groupby("policy", dropna=False):
        ret = pd.to_numeric(frame["period_return"], errors="coerce").dropna()
        risk_adj = pd.to_numeric(frame["period_risk_adj"], errors="coerce").dropna()
        mdd = pd.to_numeric(frame["period_path_mdd_proxy"], errors="coerce").dropna()
        rows.append(
            {
                "policy": policy,
                "policy_label": POLICIES.get(policy, {}).get("label", policy),
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


def run_backtest(asof: str, valid_start: str) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    data = _load_inputs(asof)
    data = data[data["signal_date"].ge(valid_start)].copy()
    selected = pd.concat([_select_policy(data, policy) for policy in POLICIES], ignore_index=True)
    periods = _period_returns(selected)
    summary = _summary(periods)

    current = selected[selected["signal_date"].eq(asof)].copy()
    current = current.sort_values(["policy", "e_series_role", "policy_weight", "ticker"], ascending=[True, True, False, True])

    selected_path = REPORT_DIR / f"e_series_etf_sleeve_portfolio_selected_{token}.csv"
    periods_path = REPORT_DIR / f"e_series_etf_sleeve_portfolio_periods_{token}.csv"
    summary_path = REPORT_DIR / f"e_series_etf_sleeve_portfolio_summary_{token}.csv"
    current_path = REPORT_DIR / f"e_series_etf_sleeve_portfolio_current_holdings_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_sleeve_portfolio_backtest_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_sleeve_portfolio_backtest_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_sleeve_portfolio_current.json"

    selected.to_csv(selected_path, index=False, encoding="utf-8-sig")
    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    current.to_csv(current_path, index=False, encoding="utf-8-sig")

    best = summary[~summary["policy"].eq("baseline_top3_role")].head(1)
    payload = {
        "status": "ok",
        "source_name": "e_series_etf_sleeve_portfolio_backtest",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "valid_start": valid_start,
        "policies": POLICIES,
        "best_ai_policy": _records(best),
        "summary": _records(summary),
        "current_holdings": _records(
            current[
                [
                    "policy",
                    "policy_label",
                    "signal_date",
                    "ticker",
                    "name",
                    "e_series_role",
                    "e_market_mode",
                    "policy_weight",
                    "sleeve_selection_prob",
                    "e_baseline_selection_score",
                    "e_quality_score",
                    "e_momentum_score",
                    "e_risk_control_score",
                ]
            ],
            160,
        ),
        "outputs": {
            "selected_csv": str(selected_path),
            "periods_csv": str(periods_path),
            "summary_csv": str(summary_path),
            "current_holdings_csv": str(current_path),
            "json": str(json_path),
            "markdown": str(md_path),
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, summary)
    return payload


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    lines = [
        "# E Series ETF Sleeve Portfolio Backtest",
        "",
        f"- strategy model: `{payload['strategy_model_code']}`",
        f"- sleeve model: `{payload['sleeve_model_code']}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- valid start: `{payload['valid_start']}`",
        "",
        "## Summary",
        "",
        "| policy | avg 1M ret | return delta | win | risk adj | risk adj delta | MDD proxy | compounded |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['policy']}` | {_fmt_pct(row.get('avg_1m_ret'))} | {_fmt_pct(row.get('avg_1m_ret_delta'))} | "
            f"{_fmt_pct(row.get('win_rate'))} | {_fmt_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_fmt_pct(row.get('avg_1m_risk_adj_delta'))} | {_fmt_pct(row.get('avg_1m_mdd_proxy'))} | "
            f"{_fmt_pct(row.get('compounded_validation_return'))} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `baseline_top3_role`은 E-series baseline rule score로 역할군별 상위 3개 ETF를 선택합니다.",
            "- `ai_top*_role`은 Sleeve Selection AI score로 역할군별 ETF를 선택합니다.",
            "- 같은 시장모드별 역할 비중을 사용하므로 차이는 ETF selection score에서 발생합니다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest E-series ETF baseline vs AI sleeve portfolio.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run_backtest(str(args.asof), str(args.valid_start))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "strategy_model_code": payload["strategy_model_code"],
                "as_of_date": payload["as_of_date"],
                "best_ai_policy": payload["best_ai_policy"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
