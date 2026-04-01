from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")
V2_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\ETF_T_SERIES_V2"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\ETF_T_SERIES_TRANSITION_RESEARCH"
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"

FEATURE_COLS = [
    "ret_20d",
    "ret_60d",
    "ret_120d",
    "ret_240d",
    "vol_20d",
    "vol_60d",
    "dd_60d",
    "dd_120d",
    "dist_ma20",
    "dist_ma60",
    "dist_ma120",
    "ma20_ma60_gap",
    "ma60_ma120_gap",
    "rsi20",
    "liquidity_20d_value",
]

LOWER_BUCKETS = ["OUTSIDE", "ET50_ex_ET30", "ET30_ex_ET10"]


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_df = pd.read_csv(V2_DIR / "etf_tseries_feature_panel.csv", dtype={"ticker": str})
    bucket_df = pd.read_csv(V2_DIR / "etf_tseries_bucket_panel.csv", dtype={"ticker": str})
    feature_df["ticker"] = feature_df["ticker"].astype(str).str.zfill(6)
    bucket_df["ticker"] = bucket_df["ticker"].astype(str).str.zfill(6)
    feature_df["signal_date"] = pd.to_datetime(feature_df["signal_date"])
    bucket_df["signal_date"] = pd.to_datetime(bucket_df["signal_date"])
    return feature_df, bucket_df


def _build_transition_panel(feature_df: pd.DataFrame, bucket_df: pd.DataFrame) -> pd.DataFrame:
    panels: list[pd.DataFrame] = []
    for horizon, horizon_df in bucket_df.groupby("horizon"):
        dates = sorted(pd.to_datetime(horizon_df["signal_date"]).drop_duplicates())
        next_map = {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}
        current = horizon_df.rename(columns={"bucket": "current_bucket"}).copy()
        current["next_signal_date"] = current["signal_date"].map(next_map)
        current = current[current["next_signal_date"].notna()].copy()

        nxt = horizon_df[["signal_date", "ticker", "bucket"]].rename(
            columns={"signal_date": "next_signal_date", "bucket": "next_bucket"}
        )
        merged = current.merge(nxt, on=["next_signal_date", "ticker"], how="left")
        merged = merged.merge(
            feature_df[
                ["signal_date", "ticker", "name", "asset_class", "group_key", "currency_exposure"] + FEATURE_COLS
            ],
            on=["signal_date", "ticker"],
            how="left",
        )
        merged["horizon"] = horizon
        panels.append(merged)
    out = pd.concat(panels, ignore_index=True)
    out["label_to_et10"] = out["next_bucket"].isin(["ET10_ex_ET3", "ET3"]).astype(int)
    out["label_to_et3"] = out["next_bucket"].eq("ET3").astype(int)
    return out


def _build_transition_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for (horizon, current_bucket), grp in panel.groupby(["horizon", "current_bucket"], dropna=False):
        denom = len(grp)
        next_counts = grp["next_bucket"].fillna("MISSING").value_counts()
        for next_bucket, cnt in next_counts.items():
            rows.append(
                {
                    "horizon": horizon,
                    "current_bucket": current_bucket,
                    "next_bucket": next_bucket,
                    "count": int(cnt),
                    "probability": float(cnt / denom) if denom else np.nan,
                }
            )
    return pd.DataFrame(rows).sort_values(["horizon", "current_bucket", "probability"], ascending=[True, True, False])


def _feature_summary(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    rows: list[dict] = []
    work = df.copy()
    work = work.dropna(subset=[label_col]).copy()
    for feature in FEATURE_COLS:
        sub = work[[feature, label_col]].replace([np.inf, -np.inf], np.nan).dropna()
        if sub.empty or sub[label_col].nunique() < 2:
            continue
        pos = sub.loc[sub[label_col] == 1, feature]
        neg = sub.loc[sub[label_col] == 0, feature]
        if len(pos) == 0 or len(neg) == 0:
            continue
        pooled = np.sqrt(((pos.std(ddof=0) ** 2) + (neg.std(ddof=0) ** 2)) / 2)
        effect = (pos.mean() - neg.mean()) / pooled if pooled and np.isfinite(pooled) else np.nan
        rows.append(
            {
                "feature": feature,
                "positive_n": int(len(pos)),
                "negative_n": int(len(neg)),
                "positive_mean": float(pos.mean()),
                "negative_mean": float(neg.mean()),
                "mean_diff": float(pos.mean() - neg.mean()),
                "effect_size": float(effect) if np.isfinite(effect) else np.nan,
                "corr_with_label": float(sub[feature].corr(sub[label_col])),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["effect_size", "corr_with_label"], ascending=[False, False])


def _write_report(
    panel: pd.DataFrame,
    matrix_df: pd.DataFrame,
    lower_summary: pd.DataFrame,
    et10_to_et3_summary: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# ETF T-series Transition Research")
    lines.append("")
    lines.append(f"- Transition observations: {len(panel):,}")
    lines.append(f"- Horizons: {', '.join(sorted(panel['horizon'].dropna().astype(str).unique().tolist()))}")
    lines.append("")
    for horizon in sorted(panel["horizon"].dropna().unique().tolist()):
        h = panel[panel["horizon"] == horizon]
        lower = h[h["current_bucket"].isin(LOWER_BUCKETS)]
        et10 = h[h["current_bucket"] == "ET10_ex_ET3"]
        lines.append(f"## {horizon}")
        lines.append("")
        lines.append(f"- lower -> ET10+ rate: {lower['label_to_et10'].mean():.2%}" if len(lower) else "- lower -> ET10+ rate: n/a")
        lines.append(f"- ET10 -> ET3 rate: {et10['label_to_et3'].mean():.2%}" if len(et10) else "- ET10 -> ET3 rate: n/a")
        top_matrix = matrix_df[matrix_df["horizon"] == horizon].head(12)
        for row in top_matrix.itertuples(index=False):
            lines.append(
                f"- {row.current_bucket} -> {row.next_bucket}: {row.probability:.2%} ({row.count})"
            )
        lines.append("")
    if not lower_summary.empty:
        lines.append("## Lower -> ET10 Top Features")
        lines.append("")
        for row in lower_summary.head(8).itertuples(index=False):
            lines.append(
                f"- {row.feature}: effect {row.effect_size:.3f}, corr {row.corr_with_label:.3f}, "
                f"pos_mean {row.positive_mean:.4f}, neg_mean {row.negative_mean:.4f}"
            )
        lines.append("")
    if not et10_to_et3_summary.empty:
        lines.append("## ET10 -> ET3 Top Features")
        lines.append("")
        for row in et10_to_et3_summary.head(8).itertuples(index=False):
            lines.append(
                f"- {row.feature}: effect {row.effect_size:.3f}, corr {row.corr_with_label:.3f}, "
                f"pos_mean {row.positive_mean:.4f}, neg_mean {row.negative_mean:.4f}"
            )
    (OUTDIR / "etf_tseries_transition_research.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    feature_df, bucket_df = _load_inputs()
    panel = _build_transition_panel(feature_df, bucket_df)
    matrix_df = _build_transition_matrix(panel)

    lower_panel = panel[panel["current_bucket"].isin(LOWER_BUCKETS)].copy()
    et10_panel = panel[panel["current_bucket"] == "ET10_ex_ET3"].copy()
    lower_summary = _feature_summary(lower_panel, "label_to_et10")
    et10_to_et3_summary = _feature_summary(et10_panel, "label_to_et3")

    panel.to_csv(OUTDIR / "etf_tseries_transition_panel.csv", index=False, encoding="utf-8-sig")
    matrix_df.to_csv(OUTDIR / "etf_tseries_transition_matrix.csv", index=False, encoding="utf-8-sig")
    lower_summary.to_csv(OUTDIR / "etf_lower_to_et10_feature_summary.csv", index=False, encoding="utf-8-sig")
    et10_to_et3_summary.to_csv(OUTDIR / "etf_et10_to_et3_feature_summary.csv", index=False, encoding="utf-8-sig")

    try:
        import sqlite3
        with sqlite3.connect(RESEARCH_DB) as conn:
            panel.to_sql("etf_tseries_transition_panel", conn, if_exists="replace", index=False)
            matrix_df.to_sql("etf_tseries_transition_matrix", conn, if_exists="replace", index=False)
            lower_summary.to_sql("etf_lower_to_et10_feature_summary", conn, if_exists="replace", index=False)
            et10_to_et3_summary.to_sql("etf_et10_to_et3_feature_summary", conn, if_exists="replace", index=False)
    except Exception as exc:
        print(f"[warn] failed to persist research tables: {exc}")

    _write_report(panel, matrix_df, lower_summary, et10_to_et3_summary)
    print(f"transition_rows={len(panel)}")
    print(f"lower_to_et10_rate={lower_panel['label_to_et10'].mean():.6f}" if len(lower_panel) else "lower_to_et10_rate=nan")
    print(f"et10_to_et3_rate={et10_panel['label_to_et3'].mean():.6f}" if len(et10_panel) else "et10_to_et3_rate=nan")
    if not lower_summary.empty:
        print("lower_top_features=" + ",".join(lower_summary.head(5)["feature"].tolist()))
    if not et10_to_et3_summary.empty:
        print("et10_top_features=" + ",".join(et10_to_et3_summary.head(5)["feature"].tolist()))


if __name__ == "__main__":
    main()
