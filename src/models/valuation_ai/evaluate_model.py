# evaluate_model.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .common import now_ts, read_sql, write_json, write_table
from .config import EVAL_TABLE, FEATURE_TABLE, LABEL_TABLE, MODEL_CODE, MODEL_NAME_KR, MODEL_DIR, OUT_DB, REPORT_DIR
from .predict_scores import _latest_model_path
from .rule_score_engine import build_rule_scores


def _load_joined(db: Path) -> pd.DataFrame:
    features = read_sql(db, f"SELECT * FROM {FEATURE_TABLE}", parse_dates=["asof_date"])
    labels = read_sql(db, f"SELECT * FROM {LABEL_TABLE}", parse_dates=["asof_date"])
    features["ticker"] = features["ticker"].astype(str).str.zfill(6)
    labels["ticker"] = labels["ticker"].astype(str).str.zfill(6)
    return features.merge(labels, on=["asof_date", "ticker"], how="left", suffixes=("", "_label"))


def _metric_row(frame: pd.DataFrame, name: str) -> dict[str, Any]:
    valid = frame.dropna(subset=["valuation_ai_score", "fwd_excess_ret_12m"]).copy()
    if valid.empty:
        return {"window": name, "sample_count": 0}
    top = valid.sort_values("valuation_ai_score", ascending=False).head(max(1, int(len(valid) * 0.10)))
    bottom = valid.sort_values("valuation_ai_score", ascending=True).head(max(1, int(len(valid) * 0.10)))
    return {
        "window": name,
        "start": str(valid["asof_date"].min().date()),
        "end": str(valid["asof_date"].max().date()),
        "sample_count": int(len(valid)),
        "ic": round(float(valid["valuation_ai_score"].corr(valid["fwd_excess_ret_12m"])), 6),
        "rank_ic": round(float(valid["valuation_ai_score"].rank().corr(valid["fwd_excess_ret_12m"].rank())), 6),
        "top_decile_avg_excess_12m": round(float(top["fwd_excess_ret_12m"].mean()), 6),
        "bottom_decile_avg_excess_12m": round(float(bottom["fwd_excess_ret_12m"].mean()), 6),
        "top_decile_spread": round(float(top["fwd_excess_ret_12m"].mean() - bottom["fwd_excess_ret_12m"].mean()), 6),
        "top_decile_win_rate": round(float((top["fwd_excess_ret_12m"] > 0).mean()), 6),
        "created_at": now_ts(),
    }


def _portfolio_stats(frame: pd.DataFrame, name: str, top_n: int = 30) -> dict[str, Any]:
    valid = frame.dropna(subset=["valuation_ai_score", "fwd_ret_1m"]).copy()
    if valid.empty:
        return {
            "window": name,
            "portfolio_sample_months": 0,
            "portfolio_cagr": None,
            "portfolio_mdd": None,
            "portfolio_sharpe": None,
            "portfolio_avg_monthly_return": None,
            "portfolio_monthly_vol": None,
        }
    returns = []
    for asof_date, month_frame in valid.groupby("asof_date"):
        selected = month_frame.sort_values("valuation_ai_score", ascending=False).head(min(top_n, len(month_frame)))
        returns.append({"asof_date": pd.Timestamp(asof_date), "portfolio_ret_1m": float(selected["fwd_ret_1m"].mean()), "holding_count": int(len(selected))})
    curve = pd.DataFrame(returns).sort_values("asof_date")
    if curve.empty:
        return {"window": name, "portfolio_sample_months": 0}
    monthly = pd.to_numeric(curve["portfolio_ret_1m"], errors="coerce").dropna()
    equity = (1.0 + monthly).cumprod()
    months = len(monthly)
    cagr = None if months <= 0 else float(equity.iloc[-1] ** (12.0 / months) - 1.0)
    dd = equity / equity.cummax() - 1.0
    vol = float(monthly.std()) if len(monthly) > 1 else 0.0
    sharpe = None if vol <= 0 else float(monthly.mean() / vol * np.sqrt(12))
    return {
        "window": name,
        "portfolio_sample_months": int(months),
        "portfolio_cagr": None if cagr is None else round(cagr, 6),
        "portfolio_mdd": None if dd.empty else round(float(dd.min()), 6),
        "portfolio_sharpe": None if sharpe is None else round(sharpe, 6),
        "portfolio_avg_monthly_return": None if monthly.empty else round(float(monthly.mean()), 6),
        "portfolio_monthly_vol": None if len(monthly) <= 1 else round(float(monthly.std()), 6),
        "portfolio_top_n": int(top_n),
    }


def evaluate_model(db: Path, asof: str, model_path: Path | None = None) -> pd.DataFrame:
    model_path = model_path or _latest_model_path(MODEL_DIR)
    bundle = joblib.load(model_path)
    model_version = str(bundle.get("model_version") or model_path.stem)
    regressor = bundle["regressor"]
    joined = _load_joined(db).dropna(subset=["fwd_excess_ret_12m"]).copy()
    joined = joined[joined["asof_date"] <= pd.Timestamp(asof)].copy()
    if joined.empty:
        raise SystemExit("no labeled rows available for valuation evaluation")
    predicted = pd.Series(regressor.predict(joined), index=joined.index)
    scored = build_rule_scores(joined, predicted)
    rows = [{**_metric_row(scored, "FULL"), **_portfolio_stats(scored, "FULL")}]
    end = scored["asof_date"].max()
    for years in [1, 2, 3, 5]:
        start = end - pd.DateOffset(years=years)
        window_frame = scored[scored["asof_date"] >= start]
        rows.append({**_metric_row(window_frame, f"{years}Y"), **_portfolio_stats(window_frame, f"{years}Y")})
    out = pd.DataFrame(rows)
    out["model_code"] = MODEL_CODE
    out["model_name_ko"] = MODEL_NAME_KR
    out["model_version"] = model_version
    write_table(db, EVAL_TABLE, out)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    out.to_csv(REPORT_DIR / f"valuation_backtest_eval_{token}.csv", index=False, encoding="utf-8-sig")
    write_json(
        REPORT_DIR / f"valuation_backtest_eval_{token}.json",
        {
            "model_code": MODEL_CODE,
            "model_name_ko": MODEL_NAME_KR,
            "model_version": model_version,
            "rows": out.to_dict(orient="records"),
        },
    )
    lines = [
        f"# {MODEL_CODE} Evaluation - {asof}",
        "",
        f"- model_name_ko: `{MODEL_NAME_KR}`",
        "",
        "## Ranking Quality",
        "",
        "| window | samples | Rank IC | Top decile excess 12M | Spread | Win rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in out.to_dict(orient="records"):
        lines.append(
            "| {window} | {sample_count} | {rank_ic} | {top} | {spread} | {win} |".format(
                window=row.get("window"),
                sample_count=int(row.get("sample_count") or 0),
                rank_ic="N/A" if pd.isna(row.get("rank_ic")) else f"{float(row['rank_ic']):.3f}",
                top="N/A" if pd.isna(row.get("top_decile_avg_excess_12m")) else f"{float(row['top_decile_avg_excess_12m']):.2%}",
                spread="N/A" if pd.isna(row.get("top_decile_spread")) else f"{float(row['top_decile_spread']):.2%}",
                win="N/A" if pd.isna(row.get("top_decile_win_rate")) else f"{float(row['top_decile_win_rate']):.2%}",
            )
        )
    lines.extend(
        [
            "",
            "## Top-N Portfolio Proxy",
            "",
            "| window | months | CAGR | MDD | Sharpe | Avg monthly ret | Monthly vol |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in out.to_dict(orient="records"):
        lines.append(
            "| {window} | {months} | {cagr} | {mdd} | {sharpe} | {avg} | {vol} |".format(
                window=row.get("window"),
                months=int(row.get("portfolio_sample_months") or 0),
                cagr="N/A" if pd.isna(row.get("portfolio_cagr")) else f"{float(row['portfolio_cagr']):.2%}",
                mdd="N/A" if pd.isna(row.get("portfolio_mdd")) else f"{float(row['portfolio_mdd']):.2%}",
                sharpe="N/A" if pd.isna(row.get("portfolio_sharpe")) else f"{float(row['portfolio_sharpe']):.3f}",
                avg="N/A" if pd.isna(row.get("portfolio_avg_monthly_return")) else f"{float(row['portfolio_avg_monthly_return']):.2%}",
                vol="N/A" if pd.isna(row.get("portfolio_monthly_vol")) else f"{float(row['portfolio_monthly_vol']):.2%}",
            )
        )
    (REPORT_DIR / f"valuation_backtest_eval_{token}.md").write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate AI-GROWTH-VALUATION-V01 ranking quality.")
    parser.add_argument("--db", default=str(OUT_DB))
    parser.add_argument("--asof", required=True)
    parser.add_argument("--model-path")
    args = parser.parse_args()
    out = evaluate_model(Path(args.db), args.asof, Path(args.model_path) if args.model_path else None)
    print(json.dumps({"status": "ok", "rows": out.to_dict(orient="records")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
