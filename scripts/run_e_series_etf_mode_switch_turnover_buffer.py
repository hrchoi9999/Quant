from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_e_series_etf_selection_policy_ablation import _ensure_scores, _load_inputs


REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"

STRATEGY_MODEL_CODE = "E-ETF-V01"
SLEEVE_MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"
TARGET_POLICY = "mode_switch_stress_tail_asset"


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


def _load_target(asof: str) -> pd.DataFrame:
    path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_selected_{_token(asof)}.csv"
    if not path.exists():
        raise SystemExit(f"missing selected CSV: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df[df["policy"].astype(str).eq(TARGET_POLICY)].copy()
    if df.empty:
        raise SystemExit(f"missing target policy: {TARGET_POLICY}")
    df["policy_weight"] = pd.to_numeric(df["policy_weight"], errors="coerce").fillna(0)
    return df


def _load_returns(asof: str) -> pd.DataFrame:
    data = _ensure_scores(_load_inputs(asof))
    data["ticker"] = data["ticker"].astype(str).str.zfill(6)
    data["signal_date"] = pd.to_datetime(data["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    keep = [
        "signal_date",
        "ticker",
        "name",
        "e_series_role",
        "e_asset_bucket",
        "e_market_mode",
        "fwd_ret_1m",
        "risk_adj_1m",
        "path_mdd_1m",
    ]
    out = data[[col for col in keep if col in data.columns]].copy()
    for col in ["fwd_ret_1m", "risk_adj_1m", "path_mdd_1m"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _weights_for_date(target: pd.DataFrame, signal_date: str) -> dict[str, float]:
    frame = target[target["signal_date"].eq(signal_date)]
    return frame.groupby("ticker")["policy_weight"].sum().astype(float).to_dict()


def _turnover(prev: dict[str, float], target: dict[str, float]) -> float:
    tickers = set(prev) | set(target)
    return 0.5 * sum(abs(target.get(ticker, 0.0) - prev.get(ticker, 0.0)) for ticker in tickers)


def _apply_cap(prev: dict[str, float], target: dict[str, float], cap: float | None) -> tuple[dict[str, float], float, float]:
    full_turnover = _turnover(prev, target)
    if not prev or cap is None or full_turnover <= cap:
        return dict(target), full_turnover, 1.0
    scale = float(cap) / full_turnover if full_turnover > 0 else 1.0
    tickers = set(prev) | set(target)
    out = {
        ticker: prev.get(ticker, 0.0) + scale * (target.get(ticker, 0.0) - prev.get(ticker, 0.0))
        for ticker in tickers
    }
    return {ticker: weight for ticker, weight in out.items() if abs(weight) > 1e-10}, _turnover(prev, out), scale


def _simulate_policy(
    target: pd.DataFrame,
    policy_name: str,
    turnover_cap: float | None,
    no_trade_buffer: float | None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    prev: dict[str, float] = {}
    for signal_date in sorted(target["signal_date"].dropna().unique()):
        target_weights = _weights_for_date(target, signal_date)
        target_turnover = _turnover(prev, target_weights)
        skipped = bool(prev and no_trade_buffer is not None and target_turnover < no_trade_buffer)
        if skipped:
            weights = dict(prev)
            actual_turnover = 0.0
            scale = 0.0
        else:
            weights, actual_turnover, scale = _apply_cap(prev, target_weights, turnover_cap)
        for ticker, weight in weights.items():
            rows.append(
                {
                    "policy": policy_name,
                    "signal_date": signal_date,
                    "ticker": ticker,
                    "policy_weight": weight,
                    "target_turnover": target_turnover,
                    "actual_turnover": actual_turnover,
                    "rebalance_scale": scale,
                    "rebalance_skipped": skipped,
                    "turnover_cap": turnover_cap,
                    "no_trade_buffer": no_trade_buffer,
                }
            )
        prev = weights
    return pd.DataFrame(rows)


def _policy_configs() -> list[dict[str, Any]]:
    return [
        {"policy": "mode_switch_full", "turnover_cap": None, "no_trade_buffer": None},
        {"policy": "mode_switch_cap_90", "turnover_cap": 0.90, "no_trade_buffer": None},
        {"policy": "mode_switch_cap_80", "turnover_cap": 0.80, "no_trade_buffer": None},
        {"policy": "mode_switch_cap_70", "turnover_cap": 0.70, "no_trade_buffer": None},
        {"policy": "mode_switch_cap_50", "turnover_cap": 0.50, "no_trade_buffer": None},
        {"policy": "mode_switch_cap_30", "turnover_cap": 0.30, "no_trade_buffer": None},
        {"policy": "mode_switch_buffer_20", "turnover_cap": None, "no_trade_buffer": 0.20},
        {"policy": "mode_switch_buffer_30", "turnover_cap": None, "no_trade_buffer": 0.30},
        {"policy": "mode_switch_buffer_50", "turnover_cap": None, "no_trade_buffer": 0.50},
        {"policy": "mode_switch_buffer_70", "turnover_cap": None, "no_trade_buffer": 0.70},
        {"policy": "mode_switch_buffer20_cap50", "turnover_cap": 0.50, "no_trade_buffer": 0.20},
        {"policy": "mode_switch_buffer30_cap50", "turnover_cap": 0.50, "no_trade_buffer": 0.30},
        {"policy": "mode_switch_buffer50_cap70", "turnover_cap": 0.70, "no_trade_buffer": 0.50},
        {"policy": "mode_switch_buffer50_cap50", "turnover_cap": 0.50, "no_trade_buffer": 0.50},
        {"policy": "mode_switch_buffer30_cap30", "turnover_cap": 0.30, "no_trade_buffer": 0.30},
    ]


def _period_returns(selected: pd.DataFrame, returns: pd.DataFrame, cost_bps: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    enriched = selected.merge(returns, on=["signal_date", "ticker"], how="left")
    rows: list[dict[str, Any]] = []
    cost_rate = float(cost_bps) / 10000.0
    for (policy, signal_date), frame in enriched.groupby(["policy", "signal_date"], dropna=False):
        valid = frame[frame["fwd_ret_1m"].notna()].copy()
        weights = pd.to_numeric(valid["policy_weight"], errors="coerce").fillna(0)
        actual_turnover = pd.to_numeric(frame["actual_turnover"], errors="coerce").dropna()
        turnover = float(actual_turnover.iloc[0]) if not actual_turnover.empty else 0.0
        cost = turnover * cost_rate
        gross_ret = float((valid["fwd_ret_1m"] * weights).sum()) if not valid.empty else np.nan
        gross_risk = float((valid["risk_adj_1m"] * weights).sum()) if not valid.empty else np.nan
        mdd = float((valid["path_mdd_1m"] * weights).sum()) if not valid.empty else np.nan
        rows.append(
            {
                "policy": policy,
                "signal_date": signal_date,
                "holding_count": int(frame["ticker"].nunique()),
                "priced_count": int(len(valid)),
                "target_turnover": _safe_float(frame["target_turnover"].dropna().iloc[0] if frame["target_turnover"].notna().any() else np.nan),
                "actual_turnover": _safe_float(turnover),
                "transaction_cost": _safe_float(cost),
                "gross_return": _safe_float(gross_ret),
                "net_return": _safe_float(gross_ret - cost if pd.notna(gross_ret) else np.nan),
                "gross_risk_adj": _safe_float(gross_risk),
                "net_risk_adj": _safe_float(gross_risk - cost if pd.notna(gross_risk) else np.nan),
                "path_mdd_proxy": _safe_float(mdd),
                "rebalance_skipped": bool(frame["rebalance_skipped"].any()),
            }
        )
    return enriched, pd.DataFrame(rows)


def _summary(periods: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for policy, frame in periods.groupby("policy", dropna=False):
        net = pd.to_numeric(frame["net_return"], errors="coerce").dropna()
        risk = pd.to_numeric(frame["net_risk_adj"], errors="coerce").dropna()
        mdd = pd.to_numeric(frame["path_mdd_proxy"], errors="coerce").dropna()
        turnover = pd.to_numeric(frame["actual_turnover"], errors="coerce").dropna()
        rows.append(
            {
                "policy": policy,
                "periods": int(len(frame)),
                "priced_periods": int(len(net)),
                "avg_net_1m_ret": _safe_float(net.mean()),
                "net_win_rate": _safe_float((net > 0).mean()) if not net.empty else None,
                "avg_net_1m_risk_adj": _safe_float(risk.mean()),
                "avg_mdd_proxy": _safe_float(mdd.mean()),
                "worst_net_1m_ret": _safe_float(net.min()),
                "compounded_net_return": _safe_float((1.0 + net).prod() - 1.0) if not net.empty else None,
                "avg_turnover": _safe_float(turnover.mean()),
                "max_turnover": _safe_float(turnover.max()),
                "skipped_periods": int(frame["rebalance_skipped"].sum()),
            }
        )
    out = pd.DataFrame(rows)
    base = out[out["policy"].eq("mode_switch_full")]
    if not base.empty:
        base_row = base.iloc[0]
        for col in ["avg_net_1m_ret", "avg_net_1m_risk_adj", "worst_net_1m_ret", "compounded_net_return", "avg_turnover"]:
            out[f"full_{col}"] = base_row[col]
            out[f"{col}_delta_vs_full"] = pd.to_numeric(out[col], errors="coerce") - pd.to_numeric(base_row[col], errors="coerce")
    return out.sort_values(["avg_net_1m_risk_adj", "avg_net_1m_ret"], ascending=False, na_position="last")


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    def pct(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""
        return f"{float(value):.2%}"

    lines = [
        "# E-Series ETF Mode Switch Turnover Buffer Test",
        "",
        f"- strategy model: `{payload['strategy_model_code']}`",
        f"- target policy: `{payload['target_policy']}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- cost: `{payload['cost_bps']} bps`",
        "",
        "## Summary",
        "",
        "| policy | avg net 1M | net risk adj | worst net | compounded net | avg turnover | max turnover | skipped |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['policy']}` | {pct(row.get('avg_net_1m_ret'))} | {pct(row.get('avg_net_1m_risk_adj'))} | "
            f"{pct(row.get('worst_net_1m_ret'))} | {pct(row.get('compounded_net_return'))} | "
            f"{pct(row.get('avg_turnover'))} | {pct(row.get('max_turnover'))} | {int(row.get('skipped_periods', 0))} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `mode_switch_full`은 목표 포트폴리오를 매 평가일 그대로 따라간다.",
            "- `cap` 정책은 목표와 직전 보유 간 변화량을 일정 turnover 이하로 스케일링한다.",
            "- `buffer` 정책은 목표 변화가 작으면 리밸런싱을 건너뛴다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_test(asof: str, cost_bps: float) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    target = _load_target(asof)
    returns = _load_returns(asof)
    selected_parts = [
        _simulate_policy(target, cfg["policy"], cfg["turnover_cap"], cfg["no_trade_buffer"])
        for cfg in _policy_configs()
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        selected = pd.concat([part for part in selected_parts if not part.empty], ignore_index=True)
    enriched, periods = _period_returns(selected, returns, cost_bps)
    summary = _summary(periods)

    token = _token(asof)
    selected_path = REPORT_DIR / f"e_series_etf_mode_switch_turnover_buffer_selected_{token}.csv"
    periods_path = REPORT_DIR / f"e_series_etf_mode_switch_turnover_buffer_periods_{token}.csv"
    summary_path = REPORT_DIR / f"e_series_etf_mode_switch_turnover_buffer_summary_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_mode_switch_turnover_buffer_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_mode_switch_turnover_buffer_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_turnover_buffer_current.json"

    enriched.to_csv(selected_path, index=False, encoding="utf-8-sig")
    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_mode_switch_turnover_buffer",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "target_policy": TARGET_POLICY,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cost_bps": float(cost_bps),
        "best_buffer_policy": _records(summary.head(1)),
        "summary": _records(summary),
        "outputs": {
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
    _write_markdown(md_path, payload, summary)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Test turnover cap and rebalance buffer for E-series ETF mode switch.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()
    payload = run_test(str(args.asof), float(args.cost_bps))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "strategy_model_code": payload["strategy_model_code"],
                "as_of_date": payload["as_of_date"],
                "cost_bps": payload["cost_bps"],
                "best_buffer_policy": payload["best_buffer_policy"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
