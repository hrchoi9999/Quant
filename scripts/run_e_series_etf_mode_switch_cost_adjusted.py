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


def _load_selected(asof: str) -> pd.DataFrame:
    path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_selected_{_token(asof)}.csv"
    if not path.exists():
        raise SystemExit(f"missing selected CSV: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in ["policy_weight", "fwd_ret_1m", "risk_adj_1m", "path_mdd_1m"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _portfolio_turnover(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for policy, policy_frame in frame.groupby("policy", dropna=False):
        prev_weights: dict[str, float] = {}
        for signal_date, date_frame in policy_frame.sort_values("signal_date").groupby("signal_date", dropna=False):
            weights = (
                date_frame.groupby("ticker")["policy_weight"]
                .sum()
                .dropna()
                .astype(float)
                .to_dict()
            )
            tickers = set(prev_weights) | set(weights)
            turnover = 0.5 * sum(abs(weights.get(ticker, 0.0) - prev_weights.get(ticker, 0.0)) for ticker in tickers)
            rows.append(
                {
                    "policy": policy,
                    "signal_date": signal_date,
                    "holding_count": int(len(weights)),
                    "one_way_turnover": _safe_float(turnover),
                }
            )
            prev_weights = weights
    return pd.DataFrame(rows)


def _period_returns(frame: pd.DataFrame, turnover: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    cost_rate = float(cost_bps) / 10000.0
    turnover_key = turnover.set_index(["policy", "signal_date"])["one_way_turnover"].to_dict()
    for (policy, signal_date), date_frame in frame.groupby(["policy", "signal_date"], dropna=False):
        valid = date_frame[date_frame["fwd_ret_1m"].notna()].copy()
        weights = pd.to_numeric(valid["policy_weight"], errors="coerce").fillna(0)
        gross_ret = float((valid["fwd_ret_1m"] * weights).sum()) if not valid.empty else np.nan
        gross_risk_adj = float((valid["risk_adj_1m"] * weights).sum()) if not valid.empty else np.nan
        mdd = float((valid["path_mdd_1m"] * weights).sum()) if not valid.empty else np.nan
        one_way_turnover = float(turnover_key.get((policy, signal_date), 0.0) or 0.0)
        cost = one_way_turnover * cost_rate
        rows.append(
            {
                "policy": policy,
                "signal_date": signal_date,
                "priced_count": int(len(valid)),
                "gross_return": _safe_float(gross_ret),
                "one_way_turnover": _safe_float(one_way_turnover),
                "transaction_cost": _safe_float(cost),
                "net_return": _safe_float(gross_ret - cost if pd.notna(gross_ret) else np.nan),
                "gross_risk_adj": _safe_float(gross_risk_adj),
                "net_risk_adj": _safe_float(gross_risk_adj - cost if pd.notna(gross_risk_adj) else np.nan),
                "path_mdd_proxy": _safe_float(mdd),
            }
        )
    return pd.DataFrame(rows)


def _summary(periods: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for policy, frame in periods.groupby("policy", dropna=False):
        gross = pd.to_numeric(frame["gross_return"], errors="coerce").dropna()
        net = pd.to_numeric(frame["net_return"], errors="coerce").dropna()
        net_risk = pd.to_numeric(frame["net_risk_adj"], errors="coerce").dropna()
        mdd = pd.to_numeric(frame["path_mdd_proxy"], errors="coerce").dropna()
        turnover = pd.to_numeric(frame["one_way_turnover"], errors="coerce").dropna()
        cost = pd.to_numeric(frame["transaction_cost"], errors="coerce").dropna()
        rows.append(
            {
                "policy": policy,
                "periods": int(len(frame)),
                "priced_periods": int(len(net)),
                "avg_gross_1m_ret": _safe_float(gross.mean()),
                "avg_net_1m_ret": _safe_float(net.mean()),
                "net_win_rate": _safe_float((net > 0).mean()) if not net.empty else None,
                "avg_net_1m_risk_adj": _safe_float(net_risk.mean()),
                "avg_1m_mdd_proxy": _safe_float(mdd.mean()),
                "worst_net_1m_ret": _safe_float(net.min()),
                "avg_one_way_turnover": _safe_float(turnover.mean()),
                "max_one_way_turnover": _safe_float(turnover.max()),
                "avg_transaction_cost": _safe_float(cost.mean()),
                "compounded_gross_return": _safe_float((1.0 + gross).prod() - 1.0) if not gross.empty else None,
                "compounded_net_return": _safe_float((1.0 + net).prod() - 1.0) if not net.empty else None,
            }
        )
    out = pd.DataFrame(rows)
    base = out[out["policy"].eq("baseline_top3_role")]
    if not base.empty:
        base_row = base.iloc[0]
        for col in [
            "avg_net_1m_ret",
            "net_win_rate",
            "avg_net_1m_risk_adj",
            "worst_net_1m_ret",
            "avg_one_way_turnover",
            "compounded_net_return",
        ]:
            out[f"baseline_{col}"] = base_row[col]
            out[f"{col}_delta"] = pd.to_numeric(out[col], errors="coerce") - pd.to_numeric(base_row[col], errors="coerce")
    return out.sort_values(["avg_net_1m_risk_adj", "avg_net_1m_ret"], ascending=False, na_position="last")


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    def pct(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""
        return f"{float(value):.2%}"

    lines = [
        "# E-Series ETF Mode Switch Cost Adjusted Backtest",
        "",
        f"- strategy model: `{payload['strategy_model_code']}`",
        f"- sleeve model: `{payload['sleeve_model_code']}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- transaction cost: `{payload['cost_bps']} bps` per one-way turnover",
        "",
        "## Summary",
        "",
        "| policy | avg net 1M ret | net delta | net risk adj | worst net | avg turnover | compounded net |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['policy']}` | {pct(row.get('avg_net_1m_ret'))} | {pct(row.get('avg_net_1m_ret_delta'))} | "
            f"{pct(row.get('avg_net_1m_risk_adj'))} | {pct(row.get('worst_net_1m_ret'))} | "
            f"{pct(row.get('avg_one_way_turnover'))} | {pct(row.get('compounded_net_return'))} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- turnover는 직전 평가일 holdings 대비 one-way 기준으로 계산했다.",
            "- 첫 평가일은 초기 진입 비용을 포함한다.",
            "- 비용 차감 후에도 mode switch 정책이 우위면 운영 후보의 신뢰도가 올라간다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_cost_adjusted(asof: str, cost_bps: float) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    selected = _load_selected(asof)
    turnover = _portfolio_turnover(selected)
    periods = _period_returns(selected, turnover, cost_bps)
    summary = _summary(periods)

    turnover_path = REPORT_DIR / f"e_series_etf_mode_switch_cost_adjusted_turnover_{token}.csv"
    periods_path = REPORT_DIR / f"e_series_etf_mode_switch_cost_adjusted_periods_{token}.csv"
    summary_path = REPORT_DIR / f"e_series_etf_mode_switch_cost_adjusted_summary_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_mode_switch_cost_adjusted_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_mode_switch_cost_adjusted_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_cost_adjusted_current.json"

    turnover.to_csv(turnover_path, index=False, encoding="utf-8-sig")
    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_mode_switch_cost_adjusted",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cost_bps": float(cost_bps),
        "best_net_policy": _records(summary.head(1)),
        "summary": _records(summary),
        "recent_turnover": _records(turnover.tail(30)),
        "outputs": {
            "turnover_csv": str(turnover_path),
            "periods_csv": str(periods_path),
            "summary_csv": str(summary_path),
            "json": str(json_path),
            "markdown": str(md_path),
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, summary)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run cost-adjusted E-series ETF mode switch backtest.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()
    payload = run_cost_adjusted(str(args.asof), float(args.cost_bps))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "strategy_model_code": payload["strategy_model_code"],
                "as_of_date": payload["as_of_date"],
                "cost_bps": payload["cost_bps"],
                "best_net_policy": payload["best_net_policy"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
