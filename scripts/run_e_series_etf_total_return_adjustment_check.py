from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
STRATEGY_MODEL_CODE = "E-ETF-V01"
DISTRIBUTION_TABLE_CANDIDATES = (
    "etf_distributions",
    "etf_distribution_events",
    "etf_dividends",
    "etf_cash_distributions",
)
DISTRIBUTION_CSV_CANDIDATES = [
    ROOT / r"data\etf_distributions.csv",
    ROOT / r"data\universe\etf_distributions.csv",
]


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


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict("records")]


def _source_status() -> dict[str, Any]:
    tables: list[str] = []
    table_summaries: list[dict[str, Any]] = []
    if PRICE_DB.exists():
        with sqlite3.connect(PRICE_DB) as con:
            existing = {
                row[0]
                for row in con.execute("select name from sqlite_master where type='table'")
            }
            tables = [table for table in DISTRIBUTION_TABLE_CANDIDATES if table in existing]
            for table in tables:
                row = con.execute(f"select count(*) from {table}").fetchone()
                table_summaries.append({"table": table, "rows": int(row[0] or 0)})
    csvs = [str(path) for path in DISTRIBUTION_CSV_CANDIDATES if path.exists()]
    has_table_rows = any(item["rows"] > 0 for item in table_summaries)
    return {
        "distribution_tables_found": tables,
        "distribution_table_summaries": table_summaries,
        "distribution_csvs_found": csvs,
        "has_distribution_source": bool(has_table_rows or csvs),
    }


def _load_mart(asof: str) -> pd.DataFrame:
    path = REPORT_DIR / f"e_series_etf_mart_v2_{_token(asof)}.csv"
    if not path.exists():
        raise SystemExit(f"missing mart: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df


def run_check(asof: str) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    mart = _load_mart(asof)
    rows = []
    role_rows = []
    for horizon in ("1w", "2w", "1m"):
        source_col = f"total_return_source_{horizon}"
        adj_col = f"total_return_adjustment_{horizon}"
        price_col = f"fwd_ret_price_{horizon}"
        total_col = f"fwd_ret_total_{horizon}"
        dist_col = f"distribution_sum_{horizon}"
        if source_col not in mart.columns:
            continue
        adj = pd.to_numeric(mart.get(adj_col), errors="coerce")
        price_ret = pd.to_numeric(mart.get(price_col), errors="coerce")
        total_ret = pd.to_numeric(mart.get(total_col), errors="coerce")
        dist_sum = pd.to_numeric(mart.get(dist_col), errors="coerce")
        adjusted_mask = mart[source_col].astype(str).eq("distribution_adjusted")
        rows.append(
            {
                "horizon": horizon,
                "rows": int(len(mart)),
                "priced_rows": int(price_ret.notna().sum()),
                "adjusted_rows": int(adjusted_mask.sum()),
                "adjusted_tickers": int(mart.loc[adjusted_mask, "ticker"].nunique()),
                "adjustment_coverage": _safe_float(adjusted_mask.mean()),
                "avg_price_return": _safe_float(price_ret.mean()),
                "avg_total_return": _safe_float(total_ret.mean()),
                "avg_adjustment": _safe_float(adj.mean()),
                "max_adjustment": _safe_float(adj.max()),
                "total_distribution_amount": _safe_float(dist_sum.sum()),
            }
        )
        for role, frame in mart.groupby("e_series_role", dropna=False):
            role_adj = frame[source_col].astype(str).eq("distribution_adjusted")
            role_rows.append(
                {
                    "horizon": horizon,
                    "e_series_role": role,
                    "rows": int(len(frame)),
                    "adjusted_rows": int(role_adj.sum()),
                    "adjustment_coverage": _safe_float(role_adj.mean()),
                    "avg_adjustment": _safe_float(pd.to_numeric(frame.get(adj_col), errors="coerce").mean()),
                }
            )
    summary = pd.DataFrame(rows)
    role_summary = pd.DataFrame(role_rows)
    current = mart[mart["signal_date"].astype(str).eq(asof)].copy()
    current_cols = [
        "signal_date",
        "ticker",
        "name",
        "e_series_role",
        "e_asset_bucket",
        "fwd_ret_price_1m",
        "fwd_ret_total_1m",
        "distribution_sum_1m",
        "total_return_adjustment_1m",
        "total_return_source_1m",
    ]
    current_sample = current[[col for col in current_cols if col in current.columns]].sort_values(
        ["total_return_adjustment_1m", "ticker"], ascending=[False, True]
    )

    token = _token(asof)
    summary_path = REPORT_DIR / f"e_series_etf_total_return_adjustment_summary_{token}.csv"
    role_path = REPORT_DIR / f"e_series_etf_total_return_adjustment_role_summary_{token}.csv"
    current_path = REPORT_DIR / f"e_series_etf_total_return_adjustment_current_sample_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_total_return_adjustment_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_total_return_adjustment_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_total_return_adjustment_current.json"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    role_summary.to_csv(role_path, index=False, encoding="utf-8-sig")
    current_sample.head(100).to_csv(current_path, index=False, encoding="utf-8-sig")
    source_status = _source_status()
    payload = {
        "status": "ok",
        "source_name": "e_series_etf_total_return_adjustment",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_status": source_status,
        "summary": _records(summary),
        "role_summary": _records(role_summary),
        "current_sample": _records(current_sample.head(30)),
        "interpretation": (
            "distribution_adjusted rows use forward total-return fields; price_only rows currently fall back to price return."
        ),
        "outputs": {
            "summary_csv": str(summary_path),
            "role_summary_csv": str(role_path),
            "current_sample_csv": str(current_path),
            "json": str(json_path),
            "markdown": str(md_path),
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, summary)
    return payload


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    def pct(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""
        return f"{float(value):.2%}"

    lines = [
        "# E-Series ETF Total Return Adjustment Check",
        "",
        f"- 기준일: `{payload['as_of_date']}`",
        f"- 분배금 원천 존재: `{payload['source_status']['has_distribution_source']}`",
        "",
        "| horizon | rows | adjusted rows | coverage | avg price ret | avg total ret | avg adjustment |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['horizon']}` | {int(row['rows'])} | {int(row['adjusted_rows'])} | "
            f"{pct(row['adjustment_coverage'])} | {pct(row['avg_price_return'])} | "
            f"{pct(row['avg_total_return'])} | {pct(row['avg_adjustment'])} |"
        )
    has_source = bool(payload["source_status"]["has_distribution_source"])
    adjusted_rows = int(summary["adjusted_rows"].sum()) if "adjusted_rows" in summary.columns else 0
    lines.extend(["", "## 판단", ""])
    if has_source and adjusted_rows > 0:
        lines.extend(
            [
                "- ETF 분배금 이벤트 원천이 감지되어 일부 horizon의 forward return이 총수익률 기준으로 보정됐다.",
                "- 현재 coverage는 부분 원천 기준이므로 provider와 기간을 넓히면서 보정 범위를 확대한다.",
            ]
        )
    elif has_source:
        lines.extend(
            [
                "- ETF 분배금 이벤트 원천은 있으나 현재 mart horizon 안에서 보정된 row는 없다.",
                "- mart 기준일과 분배금 이벤트 날짜가 겹치는 구간이 생기면 `fwd_ret_*`가 총수익률 기준으로 자동 전환된다.",
            ]
        )
    else:
        lines.extend(
            [
                "- 현재 로컬 DB에는 ETF 분배금 이벤트 원천이 없어 모든 행이 `price_only` fallback이다.",
                "- 보정 구조는 mart에 반영되었으므로, 향후 분배금 테이블 또는 CSV가 들어오면 `fwd_ret_*`가 총수익률 기준으로 자동 전환된다.",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check E-series ETF distribution/total-return adjustment coverage.")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    payload = run_check(str(args.asof))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "as_of_date": payload["as_of_date"],
                "source_status": payload["source_status"],
                "summary": payload["summary"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
