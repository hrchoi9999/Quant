from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
REPORT_ROOT = PROJECT_ROOT / "reports" / "etf_common_framework"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.configs.s4_risk_on_config import S4ExecutionConfig, S4RiskOnConfig
from src.backtest.configs.s5_neutral_config import S5ExecutionConfig, S5NeutralConfig
from src.backtest.configs.s6_defensive_config import S6DefensiveConfig, S6ExecutionConfig
from src.backtest.core.data import compute_daily_returns, load_prices_wide, month_end_dates, week_anchor_dates
from src.backtest.core.s4_backtest_runner import run_s4_backtest
from src.backtest.core.s5_backtest_runner import run_s5_backtest
from src.backtest.core.s6_backtest_runner import run_s6_backtest
from src.universe.etf_role_classifier import build_role_based_core_universe


def normalize_asof(raw: str) -> tuple[str, str]:
    compact = str(raw).strip().replace("-", "")
    dashed = f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return compact, dashed


def contains(series: pd.Series, pattern: str) -> pd.Series:
    return series.fillna("").astype(str).str.contains(pattern, case=False, regex=True)


def load_value_wide(price_db: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    where = []
    params: list[str] = []
    if tickers:
        where.append("ticker IN (" + ",".join(["?"] * len(tickers)) + ")")
        params.extend([str(t).zfill(6) for t in tickers])
    where.append("date >= ?")
    params.append(start)
    where.append("date <= ?")
    params.append(end)
    query = "SELECT date, ticker, value FROM prices_daily WHERE " + " AND ".join(where) + " ORDER BY date, ticker"
    with sqlite3.connect(str(price_db)) as con:
        df = pd.read_sql_query(query, con, params=params)
    if df.empty:
        return pd.DataFrame()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    wide = df.pivot(index="date", columns="ticker", values="value").sort_index()
    wide.index = pd.to_datetime(wide.index)
    return wide


def build_rebalance_dates(price_index: pd.DatetimeIndex, rebalance: str, anchor_weekday: int, holiday_shift: str) -> list[pd.Timestamp]:
    if str(rebalance).upper() == "W":
        return week_anchor_dates(price_index, anchor_weekday=anchor_weekday, holiday_shift=holiday_shift)
    return month_end_dates(price_index)


def pick_group(df: pd.DataFrame, group_key: str, mask: pd.Series, limit: int, exclude: set[str] | None = None) -> pd.DataFrame:
    exclude = exclude or set()
    picked = df.loc[mask].copy()
    if exclude:
        picked = picked.loc[~picked["ticker"].isin(exclude)].copy()
    if picked.empty:
        return pd.DataFrame(columns=df.columns)
    picked = picked.sort_values(["liquidity_20d_value", "ticker"], ascending=[False, True]).head(limit).copy()
    picked["group_key"] = group_key
    return picked


def run_models(core_df: pd.DataFrame, price_db: Path, start: str, end: str, rebalance: str, outdir: Path, tag: str) -> dict[str, pd.DataFrame]:
    tickers = core_df["ticker"].astype(str).str.zfill(6).drop_duplicates().tolist()
    close_wide = load_prices_wide(price_db=price_db, tickers=tickers, start=start, end=end)
    if close_wide.empty:
        raise RuntimeError("No ETF prices loaded for shadow core.")
    ret_wide = compute_daily_returns(close_wide).fillna(0.0)
    value_wide = load_value_wide(price_db, tickers, start, end)
    rebalance_dates = build_rebalance_dates(close_wide.index, rebalance, 2, "prev")
    name_map = {str(r["ticker"]).zfill(6): str(r.get("name", "")) for r in core_df.to_dict("records")}
    market_map = {str(r["ticker"]).zfill(6): str(r.get("market", "ETF")) for r in core_df.to_dict("records")}

    s4 = run_s4_backtest(
        close_wide=close_wide,
        value_wide=value_wide,
        ret_wide=ret_wide,
        core_df=core_df,
        rebalance_dates=rebalance_dates,
        cfg=S4RiskOnConfig(execution=S4ExecutionConfig(rebalance=rebalance)),
        name_map=name_map,
        market_map=market_map,
    )
    s5 = run_s5_backtest(
        close_wide=close_wide,
        ret_wide=ret_wide,
        core_df=core_df,
        rebalance_dates=rebalance_dates,
        cfg=S5NeutralConfig(execution=S5ExecutionConfig(rebalance=rebalance)),
        name_map=name_map,
        market_map=market_map,
    )
    s6 = run_s6_backtest(
        close_wide=close_wide,
        ret_wide=ret_wide,
        core_df=core_df,
        rebalance_dates=rebalance_dates,
        cfg=S6DefensiveConfig(execution=S6ExecutionConfig(rebalance=rebalance)),
        name_map=name_map,
        market_map=market_map,
    )

    results = {"S4": s4, "S5": s5, "S6": s6}
    output: dict[str, pd.DataFrame] = {}
    for model, result in results.items():
        prefix = f"{model.lower()}_{tag}"
        result.summary_df.to_csv(outdir / f"{prefix}_summary.csv", index=False, encoding="utf-8-sig")
        result.holdings_df.to_csv(outdir / f"{prefix}_weights.csv", index=False, encoding="utf-8-sig")
        result.trades_df.to_csv(outdir / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
        output[f"{model}_summary"] = result.summary_df
        output[f"{model}_weights"] = result.holdings_df
    return output


def latest_positive_holdings(weights: pd.DataFrame) -> pd.DataFrame:
    if weights.empty:
        return weights
    latest = weights["rebalance_date"].max()
    out = weights.loc[weights["rebalance_date"].eq(latest)].copy()
    out["weight"] = pd.to_numeric(out["weight"], errors="coerce").fillna(0.0)
    return out.loc[out["weight"] > 0, ["rebalance_date", "ticker", "name", "group_key", "weight"]].copy()


def compare_holdings(current_path: Path, shadow_weights: pd.DataFrame, model: str) -> pd.DataFrame:
    current = pd.read_csv(current_path, dtype={"ticker": "string"})
    cur = latest_positive_holdings(current)
    sh = latest_positive_holdings(shadow_weights)
    cur_keys = set(cur["ticker"].astype(str) + "|" + cur["group_key"].astype(str))
    sh_keys = set(sh["ticker"].astype(str) + "|" + sh["group_key"].astype(str))
    rows = []
    for _, row in cur.iterrows():
        key = str(row["ticker"]) + "|" + str(row["group_key"])
        rows.append({**row.to_dict(), "model": model, "side": "current_only" if key not in sh_keys else "both"})
    for _, row in sh.iterrows():
        key = str(row["ticker"]) + "|" + str(row["group_key"])
        if key not in cur_keys:
            rows.append({**row.to_dict(), "model": model, "side": "shadow_only"})
    return pd.DataFrame(rows)


def pct(x: float) -> str:
    if pd.isna(x):
        return ""
    return f"{x * 100:.2f}%"


def build_tseries_overlay(asof_compact: str, outdir: Path, role_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    asof_dashed = f"{asof_compact[:4]}-{asof_compact[4:6]}-{asof_compact[6:8]}"
    source = PROJECT_ROOT / "reports" / "model_upgrade_research" / asof_compact / "ETF_T_SERIES_OPERATIONALIZATION_PIT" / f"etf_tseries_pit_operational_candidates_{asof_dashed}.csv"
    if not source.exists():
        return pd.DataFrame(), pd.DataFrame()
    cand = pd.read_csv(source, dtype={"ticker": "string"})
    role_cols = ["ticker", "role_key", "role_confidence", "role_reason", "is_role_purity_exception", "purity_issue"]
    overlay = cand.merge(role_df[role_cols], on="ticker", how="left")
    overlay.to_csv(outdir / "t_etf_role_overlay_candidates.csv", index=False, encoding="utf-8-sig")
    summary = (
        overlay.groupby(["candidate_grade", "role_key"], dropna=False)
        .agg(count=("ticker", "count"), avg_stage1_prob=("stage1_prob", "mean"), avg_stage2_prob=("stage2_prob", "mean"))
        .reset_index()
    )
    summary.to_csv(outdir / "t_etf_role_overlay_summary.csv", index=False, encoding="utf-8-sig")
    return overlay, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare current KR ETF models with common-role shadow core.")
    parser.add_argument("--asof", default="20260427")
    parser.add_argument("--start", default="2023-06-08")
    parser.add_argument("--end", default="2026-04-27")
    parser.add_argument("--rebalance", default="M", choices=["M", "W"])
    parser.add_argument("--price-db", default=str(PROJECT_ROOT / "data" / "db" / "price.db"))
    args = parser.parse_args()

    asof_compact, _ = normalize_asof(args.asof)
    report_dir = REPORT_ROOT / asof_compact / "shadow_compare"
    report_dir.mkdir(parents=True, exist_ok=True)

    role_path = PROJECT_ROOT / "data" / "universe" / f"etf_role_classification_{asof_compact}.csv"
    current_core_path = PROJECT_ROOT / "data" / "universe" / f"universe_etf_core_{asof_compact}.csv"
    role_df = pd.read_csv(role_path, dtype={"ticker": "string"})
    current_core = pd.read_csv(current_core_path, dtype={"ticker": "string"})
    shadow_core = build_role_based_core_universe(role_df)
    shadow_core.to_csv(report_dir / f"universe_etf_core_role_shadow_{asof_compact}.csv", index=False, encoding="utf-8-sig")

    core_cmp = current_core.merge(
        shadow_core[["ticker", "group_key", "role_key", "role_reason"]],
        on=["ticker", "group_key"],
        how="outer",
        suffixes=("_current", "_shadow"),
        indicator=True,
    )
    core_cmp.to_csv(report_dir / "core_holdings_current_vs_role_shadow.csv", index=False, encoding="utf-8-sig")

    shadow_results = run_models(
        shadow_core,
        price_db=Path(args.price_db),
        start=args.start,
        end=args.end,
        rebalance=args.rebalance,
        outdir=report_dir,
        tag=f"role_shadow_{asof_compact}_{args.rebalance}_{args.start.replace('-', '')}_{args.end.replace('-', '')}",
    )

    rows = []
    current_summary_paths = {
        "S4": PROJECT_ROOT / "reports" / "backtest_etf_allocation" / f"s4_alloc_summary_{asof_compact}_{args.rebalance}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv",
        "S5": PROJECT_ROOT / "reports" / "backtest_etf_allocation" / f"s5_alloc_summary_{asof_compact}_{args.rebalance}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv",
        "S6": PROJECT_ROOT / "reports" / "backtest_etf_allocation" / f"s6_alloc_summary_{asof_compact}_{args.rebalance}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv",
    }
    for model, path in current_summary_paths.items():
        current = pd.read_csv(path).iloc[0].to_dict()
        shadow = shadow_results[f"{model}_summary"].iloc[0].to_dict()
        rows.append({"model": model, "variant": "current", **current})
        rows.append({"model": model, "variant": "role_shadow", **shadow})
        rows.append(
            {
                "model": model,
                "variant": "delta_shadow_minus_current",
                "cagr": float(shadow["cagr"]) - float(current["cagr"]),
                "mdd": float(shadow["mdd"]) - float(current["mdd"]),
                "sharpe": float(shadow["sharpe"]) - float(current["sharpe"]),
                "turnover": float(shadow["turnover"]) - float(current["turnover"]),
                "cagr_1y": float(shadow["cagr_1y"]) - float(current["cagr_1y"]),
                "mdd_1y": float(shadow["mdd_1y"]) - float(current["mdd_1y"]),
                "sharpe_1y": float(shadow["sharpe_1y"]) - float(current["sharpe_1y"]),
            }
        )
    summary_cmp = pd.DataFrame(rows)
    summary_cmp.to_csv(report_dir / "s456_current_vs_role_shadow_summary.csv", index=False, encoding="utf-8-sig")

    holding_parts = []
    weight_paths = {
        "S4": PROJECT_ROOT / "reports" / "backtest_etf_allocation" / f"s4_alloc_weights_{asof_compact}_{args.rebalance}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv",
        "S5": PROJECT_ROOT / "reports" / "backtest_etf_allocation" / f"s5_alloc_weights_{asof_compact}_{args.rebalance}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv",
        "S6": PROJECT_ROOT / "reports" / "backtest_etf_allocation" / f"s6_alloc_weights_{asof_compact}_{args.rebalance}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv",
    }
    for model, path in weight_paths.items():
        holding_parts.append(compare_holdings(path, shadow_results[f"{model}_weights"], model))
    holdings_cmp = pd.concat(holding_parts, ignore_index=True)
    holdings_cmp.to_csv(report_dir / "s456_latest_holdings_current_vs_role_shadow.csv", index=False, encoding="utf-8-sig")

    t_overlay, t_summary = build_tseries_overlay(asof_compact, report_dir, role_df)

    md_lines = [
        f"# ETF Common Role Shadow Comparison - {asof_compact}",
        "",
        f"- window: {args.start} to {args.end}",
        f"- rebalance: {args.rebalance}",
        f"- current_core_rows: {len(current_core)}",
        f"- role_shadow_core_rows: {len(shadow_core)}",
        "",
        "## S4/S5/S6 Summary",
        "",
        "| model | variant | CAGR | MDD | Sharpe | Turnover | 1Y CAGR | 1Y MDD | 1Y Sharpe |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        md_lines.append(
            f"| {row.get('model','')} | {row.get('variant','')} | {pct(row.get('cagr'))} | {pct(row.get('mdd'))} | "
            f"{row.get('sharpe', float('nan')):.2f} | {row.get('turnover', float('nan')):.2f} | "
            f"{pct(row.get('cagr_1y'))} | {pct(row.get('mdd_1y'))} | {row.get('sharpe_1y', float('nan')):.2f} |"
        )
    md_lines.extend(
        [
            "",
            "## Latest Holdings Difference",
            "",
            "| model | side | ticker | name | group_key | weight |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for _, row in holdings_cmp.iterrows():
        md_lines.append(
            f"| {row.get('model','')} | {row.get('side','')} | {row.get('ticker','')} | {row.get('name','')} | {row.get('group_key','')} | {float(row.get('weight',0.0)):.4f} |"
        )
    md_lines.extend(["", "## T-ETF Role Overlay", ""])
    if t_summary.empty:
        md_lines.append("- T-ETF operational candidate file was not found.")
    else:
        md_lines.append("| candidate_grade | role_key | count | avg_stage1_prob | avg_stage2_prob |")
        md_lines.append("| --- | --- | ---: | ---: | ---: |")
        for _, row in t_summary.iterrows():
            md_lines.append(
                f"| {row.get('candidate_grade','')} | {row.get('role_key','')} | {int(row.get('count',0))} | "
                f"{float(row.get('avg_stage1_prob',0.0)):.4f} | {float(row.get('avg_stage2_prob',0.0)) if pd.notna(row.get('avg_stage2_prob')) else float('nan'):.4f} |"
            )
    (report_dir / "ETF_COMMON_ROLE_SHADOW_COMPARISON.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"report_dir={report_dir}")
    print(summary_cmp.loc[summary_cmp["variant"].ne("delta_shadow_minus_current"), ["model", "variant", "cagr", "mdd", "sharpe", "turnover", "cagr_1y"]].to_string(index=False))
    print("delta:")
    print(summary_cmp.loc[summary_cmp["variant"].eq("delta_shadow_minus_current"), ["model", "cagr", "mdd", "sharpe", "turnover", "cagr_1y"]].to_string(index=False))


if __name__ == "__main__":
    main()
