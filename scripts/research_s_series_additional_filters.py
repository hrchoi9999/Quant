from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
DETAIL_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_selection_gap\s_series_selection_gap_detail.csv"
PRICE_FEAT_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
HIST_MCAP_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_challenger_backtest_historical_mcap\historical_mcap_signal_dates.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_filter_research"
WINDOW_START = pd.Timestamp("2025-04-24")
MODELS = ["S2", "S3", "S3_CORE2"]
HORIZONS = ["1M", "3M"]


def load_detail() -> pd.DataFrame:
    df = pd.read_csv(DETAIL_CSV, dtype={"ticker": str}, parse_dates=["date", "end_date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in [
        "selected",
        "score_value",
        "growth_score",
        "s2_growth_score",
        "fund_accel_score",
        "mom20",
        "vol_ratio_20",
        "breakout60",
        "trend_up",
        "ma_gap_60",
        "mcap",
        "forward_return",
        "forward_return_pct_rank",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_price_features() -> pd.DataFrame:
    import sqlite3

    con = sqlite3.connect(str(PRICE_FEAT_DB))
    try:
        feat = pd.read_sql_query(
            """
            SELECT ticker, date, value_won, adv20, adv60
            FROM s3_price_features_daily
            """,
            con,
            parse_dates=["date"],
        )
    finally:
        con.close()
    feat["ticker"] = feat["ticker"].astype(str).str.zfill(6)
    for col in ["value_won", "adv20", "adv60"]:
        feat[col] = pd.to_numeric(feat[col], errors="coerce")
    return feat


def load_hist_mcap() -> pd.DataFrame:
    if not HIST_MCAP_CSV.exists():
        return pd.DataFrame(columns=["date", "ticker", "mcap_hist"])
    df = pd.read_csv(HIST_MCAP_CSV, dtype={"ticker": str}, parse_dates=["date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["mcap_hist"] = pd.to_numeric(df.get("mcap"), errors="coerce")
    return df[["date", "ticker", "mcap_hist"]]


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    feat = load_price_features()
    hist = load_hist_mcap()
    out = df.merge(feat, on=["date", "ticker"], how="left")
    if not hist.empty:
        out = out.merge(hist, on=["date", "ticker"], how="left")
        out["mcap"] = out["mcap_hist"].combine_first(out["mcap"])
    out["adv_ratio_20_60"] = out["adv20"] / out["adv60"]
    out["value_to_adv20"] = out["value_won"] / out["adv20"]
    rank_cols = ["adv20", "adv60", "value_won", "adv_ratio_20_60", "mcap"]
    for col in rank_cols:
        out[f"{col}_pct"] = out.groupby("date")[col].rank(pct=True)
    return out


def eval_subset(sub: pd.DataFrame, rule_mask: pd.Series, objective: str) -> dict[str, float] | None:
    rule_mask = rule_mask.fillna(False)
    flagged = sub[rule_mask].copy()
    if flagged.empty:
        return None
    coverage = len(flagged) / len(sub)
    if coverage < 0.01 or coverage > 0.25:
        return None
    base_avg = float(sub["forward_return"].mean())
    flag_avg = float(flagged["forward_return"].mean())
    base_winner = float((sub["forward_return"] > 0).mean())
    flag_winner = float((flagged["forward_return"] > 0).mean())
    base_top = float((sub["forward_return_pct_rank"] >= 0.90).mean())
    flag_top = float((flagged["forward_return_pct_rank"] >= 0.90).mean())
    if objective == "reject":
        score = (base_avg - flag_avg) + 0.5 * ((1 - flag_winner) - (1 - base_winner)) + 0.2 * coverage
    else:
        score = (flag_avg - base_avg) + 0.5 * (flag_winner - base_winner) + 0.5 * (flag_top - base_top)
    return {
        "coverage": coverage,
        "base_avg_return": base_avg,
        "flag_avg_return": flag_avg,
        "delta_avg_return": flag_avg - base_avg,
        "base_winner_rate": base_winner,
        "flag_winner_rate": flag_winner,
        "base_topdecile_rate": base_top,
        "flag_topdecile_rate": flag_top,
        "score": score,
        "n_flagged": len(flagged),
        "n_total": len(sub),
    }


def scan_rules(sub: pd.DataFrame, objective: str) -> pd.DataFrame:
    features = [
        "score_value",
        "growth_score",
        "s2_growth_score",
        "fund_accel_score",
        "mom20",
        "vol_ratio_20",
        "ma_gap_60",
        "adv20_pct",
        "adv_ratio_20_60",
        "adv_ratio_20_60_pct",
        "mcap",
        "mcap_pct",
    ]
    rows = []
    for feature in features:
        if feature not in sub.columns:
            continue
        series = pd.to_numeric(sub[feature], errors="coerce")
        valid = sub.loc[series.notna()].copy()
        if len(valid) < 30:
            continue
        qvals = sorted(set(valid[feature].quantile([0.2, 0.35, 0.5, 0.65, 0.8]).dropna().tolist()))
        for thr in qvals:
            for direction in [">=", "<="]:
                mask = valid[feature] >= thr if direction == ">=" else valid[feature] <= thr
                stats = eval_subset(valid, mask, objective=objective)
                if stats is None:
                    continue
                rows.append(
                    {
                        "feature": feature,
                        "direction": direction,
                        "threshold": thr,
                        **stats,
                    }
                )

    combo_specs = [
        ("overheat_core", lambda x: (x["ma_gap_60"] >= 0.45) & (x["vol_ratio_20"] >= 2.0) & (x["mom20"] >= 0.10)),
        ("overheat_liq_midlow", lambda x: (x["ma_gap_60"] >= 0.45) & (x["vol_ratio_20"] >= 2.0) & (x["adv20_pct"] <= 0.60)),
        ("overheat_accel", lambda x: (x["ma_gap_60"] >= 0.45) & (x["vol_ratio_20"] >= 2.0) & (x["fund_accel_score"] >= 0.55)),
        ("reversal_core", lambda x: (x["score_value"] >= 200) & (x["fund_accel_score"] >= 0.60) & (x["trend_up"] == 0) & (x["ma_gap_60"].between(-0.12, 0.08)) & (x["mom20"].between(-0.15, 0.10))),
        ("reversal_liq", lambda x: (x["score_value"] >= 200) & (x["fund_accel_score"] >= 0.60) & (x["trend_up"] == 0) & (x["ma_gap_60"].between(-0.12, 0.08)) & (x["adv20_pct"] >= 0.50)),
        ("reversal_value_expand", lambda x: (x["score_value"] >= 200) & (x["fund_accel_score"] >= 0.60) & (x["trend_up"] == 0) & (x["adv_ratio_20_60"] >= 1.00)),
    ]
    for name, fn in combo_specs:
        try:
            mask = fn(sub).fillna(False)
        except Exception:
            continue
        stats = eval_subset(sub, mask, objective=objective)
        if stats is None:
            continue
        rows.append(
            {
                "feature": name,
                "direction": "combo",
                "threshold": np.nan,
                **stats,
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["score", "coverage"], ascending=[False, True]).reset_index(drop=True)
    return out


def run_research(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    reject_rows = []
    include_rows = []
    for model in MODELS:
        for horizon in HORIZONS:
            base = df[(df["model_code"] == model) & (df["horizon"] == horizon) & (df["date"] >= WINDOW_START)].copy()
            if base.empty:
                continue
            selected = base[base["selected"] == 1].copy()
            not_selected = base[base["selected"] == 0].copy()
            rej = scan_rules(selected, objective="reject")
            if not rej.empty:
                rej["model_code"] = model
                rej["horizon"] = horizon
                reject_rows.append(rej.head(12))
            inc = scan_rules(not_selected, objective="include")
            if not inc.empty:
                inc["model_code"] = model
                inc["horizon"] = horizon
                include_rows.append(inc.head(12))
    reject = pd.concat(reject_rows, ignore_index=True) if reject_rows else pd.DataFrame()
    include = pd.concat(include_rows, ignore_index=True) if include_rows else pd.DataFrame()
    return reject, include


def build_md(reject: pd.DataFrame, include: pd.DataFrame) -> str:
    lines = [
        "# S-Series Additional Filter Research",
        "",
        f"- window start: {WINDOW_START.date().isoformat()}",
        "- objective",
        "  - reject scan: find conditions inside selected names that are associated with lower forward return and higher loser rate",
        "  - include scan: find conditions inside not-selected names that are associated with higher forward return and higher winner/top-decile rate",
        "",
    ]

    if not reject.empty:
        lines.extend(
            [
                "## Top Reject Candidates",
                "| Model | Horizon | Rule | Coverage | Flag Avg Return | Delta Avg Return | Flag Winner Rate | Flag Top Decile | Score |",
                "|---|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in reject.itertuples(index=False):
            rule = row.feature if row.direction == "combo" else f"{row.feature} {row.direction} {row.threshold:.4f}"
            lines.append(
                f"| {row.model_code} | {row.horizon} | {rule} | {row.coverage:.2%} | {row.flag_avg_return:.2%} | {row.delta_avg_return:.2%} | "
                f"{row.flag_winner_rate:.2%} | {row.flag_topdecile_rate:.2%} | {row.score:.4f} |"
            )
        lines.append("")

    if not include.empty:
        lines.extend(
            [
                "## Top Inclusion Candidates",
                "| Model | Horizon | Rule | Coverage | Flag Avg Return | Delta Avg Return | Flag Winner Rate | Flag Top Decile | Score |",
                "|---|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in include.itertuples(index=False):
            rule = row.feature if row.direction == "combo" else f"{row.feature} {row.direction} {row.threshold:.4f}"
            lines.append(
                f"| {row.model_code} | {row.horizon} | {rule} | {row.coverage:.2%} | {row.flag_avg_return:.2%} | {row.delta_avg_return:.2%} | "
                f"{row.flag_winner_rate:.2%} | {row.flag_topdecile_rate:.2%} | {row.score:.4f} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    detail = enrich(load_detail())
    reject, include = run_research(detail)
    if not reject.empty:
        reject.to_csv(OUTDIR / "s_series_recent1y_reject_candidates.csv", index=False, encoding="utf-8-sig")
    if not include.empty:
        include.to_csv(OUTDIR / "s_series_recent1y_include_candidates.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s_series_recent1y_filter_research.md").write_text(build_md(reject, include), encoding="utf-8")
    print(f"[OK] wrote {OUTDIR}")


if __name__ == "__main__":
    main()
