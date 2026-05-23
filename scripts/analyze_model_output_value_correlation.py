from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
TS_DB = PROJECT_ROOT / r"data\db\tseries_operational.db"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
USER_REPORT_DIR = PROJECT_ROOT / r"reports\redbot_user_reports"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_model_output"

HORIZONS = {
    "1W": 5,
    "2W": 10,
    "1M": 21,
    "3M": 63,
}

USER_PROFILES = ("stable", "balanced", "growth")
INTERNAL_MODELS = ("S2", "S3", "S3_CORE2", "S4", "S5", "S6")
TS_MODELS = ("T-STOCK-V01", "T-ETF-V01")


@dataclass(frozen=True)
class ModelMeta:
    scope: str
    model_code: str
    display_name: str
    score_basis: str


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def load_prices() -> pd.DataFrame:
    px = read_sql(
        PRICE_DB,
        """
        SELECT ticker, date, close
        FROM prices_daily
        WHERE close IS NOT NULL
        """,
        parse_dates=["date"],
    )
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px = px.dropna(subset=["close"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    return px


def trading_date_map(px: pd.DataFrame) -> dict[str, dict[pd.Timestamp, pd.Timestamp]]:
    dates = sorted(pd.to_datetime(px["date"].dropna().unique()))
    out: dict[str, dict[pd.Timestamp, pd.Timestamp]] = {}
    for label, steps in HORIZONS.items():
        mapping = {}
        for idx in range(len(dates) - steps):
            mapping[pd.Timestamp(dates[idx])] = pd.Timestamp(dates[idx + steps])
        out[label] = mapping
    return out


def load_internal_rows() -> tuple[pd.DataFrame, list[ModelMeta]]:
    current = read_sql(
        QS_DB,
        """
        SELECT model_code, published_run_id
        FROM pub_model_current
        WHERE model_code IN ('S2','S3','S3_CORE2','S4','S5','S6')
        """,
    )
    runs = {row.model_code: row.published_run_id for row in current.itertuples(index=False)}
    frames: list[pd.DataFrame] = []
    meta: list[ModelMeta] = []
    for model_code in INTERNAL_MODELS:
        run_id = runs.get(model_code)
        if not run_id:
            continue
        hist = read_sql(
            QS_DETAIL_DB,
            """
            SELECT date, ticker, rank_no, weight, score
            FROM run_holdings_history
            WHERE run_id=?
            """,
            params=(run_id,),
            parse_dates=["date"],
        )
        if hist.empty:
            continue
        hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
        hist["scope"] = "internal"
        hist["model_code"] = model_code
        hist["display_name"] = model_code
        if model_code in {"S4", "S5", "S6"}:
            hist["score_value"] = pd.to_numeric(hist["weight"], errors="coerce")
            score_basis = "weight_proxy"
        else:
            hist["score_value"] = pd.to_numeric(hist["score"], errors="coerce")
            score_basis = "model_score"
        hist["score_basis"] = score_basis
        frames.append(
            hist[
                [
                    "scope",
                    "model_code",
                    "display_name",
                    "date",
                    "ticker",
                    "rank_no",
                    "weight",
                    "score_value",
                    "score_basis",
                ]
            ].copy()
        )
        meta.append(ModelMeta("internal", model_code, model_code, score_basis))
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), meta


def parse_user_report(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    profile = str(payload.get("header", {}).get("service_profile") or "").strip().lower()
    rows = []
    for item in payload.get("model_portfolio", []):
        code = item.get("security_code")
        if not code:
            continue
        weight = pd.to_numeric(item.get("target_weight"), errors="coerce")
        rows.append(
            {
                "ticker": str(code).zfill(6),
                "display_name": item.get("display_name"),
                "weight": weight,
                "score_value": weight,
                "score_basis": "target_weight_proxy",
                "source_type": item.get("source_type"),
                "asset_group": item.get("asset_group"),
                "service_profile": profile,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["weight", "ticker"], ascending=[False, True]).reset_index(drop=True)
    df["rank_no"] = np.arange(1, len(df) + 1)
    df["date"] = pd.to_datetime(path.stem.rsplit("_", 1)[-1], format="%Y%m%d")
    return df


def load_user_rows() -> tuple[pd.DataFrame, list[ModelMeta]]:
    frames: list[pd.DataFrame] = []
    meta: list[ModelMeta] = []
    for profile in USER_PROFILES:
        files = sorted(USER_REPORT_DIR.glob(f"redbot_user_report_{profile}_*.json"))
        for path in files:
            df = parse_user_report(path)
            if df.empty:
                continue
            df["scope"] = "user"
            df["model_code"] = profile
            df["display_name"] = profile
            frames.append(
                df[
                    [
                        "scope",
                        "model_code",
                        "display_name",
                        "date",
                        "ticker",
                        "rank_no",
                        "weight",
                        "score_value",
                        "score_basis",
                    ]
                ].copy()
            )
        meta.append(ModelMeta("user", profile, profile, "target_weight_proxy"))
    non_empty = [frame for frame in frames if not frame.empty]
    return (pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame()), meta


def load_tseries_rows() -> tuple[pd.DataFrame, list[ModelMeta]]:
    hist = read_sql(
        TS_DB,
        """
        SELECT model_code, signal_date, candidate_bucket, ticker, name, stage1_prob, stage2_prob
        FROM ts_candidates_history
        WHERE model_code IN ('T-STOCK-V01','T-ETF-V01')
        """,
        parse_dates=["signal_date"],
    )
    if hist.empty:
        return pd.DataFrame(), []
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    bucket_rank = {
        "confirmed": 0,
        "near": 1,
        "historical_stage2": 1,
        "observe": 2,
        "historical_stage1": 2,
    }
    hist["bucket_rank"] = hist["candidate_bucket"].map(bucket_rank).fillna(9)
    hist["stage1_prob"] = pd.to_numeric(hist["stage1_prob"], errors="coerce")
    hist["stage2_prob"] = pd.to_numeric(hist["stage2_prob"], errors="coerce")
    hist = hist.sort_values(
        ["model_code", "signal_date", "ticker", "bucket_rank", "stage2_prob", "stage1_prob"],
        ascending=[True, True, True, True, False, False],
        na_position="last",
    )
    hist = hist.drop_duplicates(["model_code", "signal_date", "ticker"], keep="first").copy()
    hist["score_value"] = hist["stage2_prob"].where(hist["stage2_prob"].notna(), hist["stage1_prob"])
    hist["score_basis"] = np.where(hist["stage2_prob"].notna(), "stage2_prob", "stage1_prob")
    hist["scope"] = "tseries"
    hist["display_name"] = hist["model_code"]
    hist["date"] = hist["signal_date"]
    rank_frames = []
    for (model_code, dt), sub in hist.groupby(["model_code", "date"], sort=True):
        ranked = sub.sort_values(
            ["bucket_rank", "stage2_prob", "stage1_prob", "ticker"],
            ascending=[True, False, False, True],
            na_position="last",
        ).copy()
        ranked["rank_no"] = np.arange(1, len(ranked) + 1)
        rank_frames.append(ranked)
    ranked_all = pd.concat(rank_frames, ignore_index=True) if rank_frames else pd.DataFrame()
    ranked_all["weight"] = np.nan
    meta = [ModelMeta("tseries", code, code, "stage_prob") for code in TS_MODELS]
    return (
        ranked_all[
            [
                "scope",
                "model_code",
                "display_name",
                "date",
                "ticker",
                "rank_no",
                "weight",
                "score_value",
                "score_basis",
                "candidate_bucket",
                "stage1_prob",
                "stage2_prob",
            ]
        ].copy(),
        meta,
    )


def attach_forward_returns(base: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    if base.empty:
        return base
    work = base.copy()
    work["date"] = pd.to_datetime(work["date"])
    px_index = px.rename(columns={"close": "entry_close"})
    work = work.merge(px_index, on=["ticker", "date"], how="left")
    date_maps = trading_date_map(px)
    all_frames = []
    for label, mapping in date_maps.items():
        frame = work.copy()
        frame["horizon"] = label
        frame["end_date"] = frame["date"].map(mapping)
        frame = frame[frame["end_date"].notna()].copy()
        if frame.empty:
            continue
        target_px = px.rename(columns={"date": "end_date", "close": "end_close"})
        frame = frame.merge(target_px, on=["ticker", "end_date"], how="left")
        frame["forward_return"] = frame["end_close"] / frame["entry_close"] - 1.0
        all_frames.append(frame)
    if not all_frames:
        return pd.DataFrame()
    out = pd.concat(all_frames, ignore_index=True)
    out["rank_alpha"] = -pd.to_numeric(out["rank_no"], errors="coerce")
    return out


def safe_corr(df: pd.DataFrame, xcol: str, ycol: str, method: str) -> float | None:
    tmp = df[[xcol, ycol]].copy()
    tmp[xcol] = pd.to_numeric(tmp[xcol], errors="coerce")
    tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
    tmp = tmp.dropna()
    if len(tmp) < 3 or tmp[xcol].nunique() < 2 or tmp[ycol].nunique() < 2:
        return None
    return float(tmp[xcol].corr(tmp[ycol], method=method))


def summarize_correlations(detail: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    date_ic_rows = []
    bucket_rows = []
    for (scope, model_code, horizon), sub in detail.groupby(["scope", "model_code", "horizon"], sort=True):
        pooled_pearson = safe_corr(sub, "score_value", "forward_return", "pearson")
        pooled_spearman = safe_corr(sub, "score_value", "forward_return", "spearman")
        rank_spearman = safe_corr(sub, "rank_alpha", "forward_return", "spearman")

        date_ics = []
        for date, date_sub in sub.groupby("date", sort=True):
            score_ic = safe_corr(date_sub, "score_value", "forward_return", "spearman")
            rank_ic = safe_corr(date_sub, "rank_alpha", "forward_return", "spearman")
            date_ics.append(
                {
                    "scope": scope,
                    "model_code": model_code,
                    "horizon": horizon,
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "obs_n": int(len(date_sub)),
                    "score_ic_spearman": score_ic,
                    "rank_ic_spearman": rank_ic,
                    "avg_forward_return": float(pd.to_numeric(date_sub["forward_return"], errors="coerce").mean()),
                }
            )
        date_ic_df = pd.DataFrame(date_ics)
        if not date_ic_df.empty and date_ic_df[["score_ic_spearman", "rank_ic_spearman"]].notna().any().any():
            date_ic_rows.append(date_ic_df)

        bucket_src = sub.copy()
        score_series = pd.to_numeric(bucket_src["score_value"], errors="coerce")
        if score_series.notna().sum() >= 5 and score_series.nunique(dropna=True) >= 3:
            bucket_src = bucket_src.assign(score_bucket=pd.qcut(score_series, q=5, duplicates="drop"))
            grouped = (
                bucket_src.dropna(subset=["score_bucket", "forward_return"])
                .groupby("score_bucket", observed=False)["forward_return"]
                .agg(["count", "mean", "median"])
                .reset_index()
            )
            for row in grouped.itertuples(index=False):
                bucket_rows.append(
                    {
                        "scope": scope,
                        "model_code": model_code,
                        "horizon": horizon,
                        "score_bucket": str(row.score_bucket),
                        "n_obs": int(row.count),
                        "avg_forward_return": float(row.mean),
                        "median_forward_return": float(row.median),
                    }
                )

        summary_rows.append(
            {
                "scope": scope,
                "model_code": model_code,
                "horizon": horizon,
                "n_obs": int(len(sub)),
                "n_dates": int(sub["date"].nunique()),
                "avg_forward_return": float(pd.to_numeric(sub["forward_return"], errors="coerce").mean()),
                "median_forward_return": float(pd.to_numeric(sub["forward_return"], errors="coerce").median()),
                "pooled_pearson_score": pooled_pearson,
                "pooled_spearman_score": pooled_spearman,
                "avg_daily_ic_score": None if date_ic_df.empty else float(pd.to_numeric(date_ic_df["score_ic_spearman"], errors="coerce").mean()),
                "median_daily_ic_score": None if date_ic_df.empty else float(pd.to_numeric(date_ic_df["score_ic_spearman"], errors="coerce").median()),
                "avg_daily_ic_rank": None if date_ic_df.empty else float(pd.to_numeric(date_ic_df["rank_ic_spearman"], errors="coerce").mean()),
                "median_daily_ic_rank": None if date_ic_df.empty else float(pd.to_numeric(date_ic_df["rank_ic_spearman"], errors="coerce").median()),
                "rank_spearman_pooled": rank_spearman,
            }
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(["scope", "model_code", "horizon"]).reset_index(drop=True)
    non_empty_ic = [frame for frame in date_ic_rows if not frame.empty]
    date_ic_df = pd.concat(non_empty_ic, ignore_index=True) if non_empty_ic else pd.DataFrame()
    bucket_df = pd.DataFrame(bucket_rows)
    return summary_df, date_ic_df, bucket_df


def summarize_tseries_buckets(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty or "candidate_bucket" not in detail.columns:
        return pd.DataFrame()
    tdf = detail[detail["scope"] == "tseries"].copy()
    if tdf.empty:
        return pd.DataFrame()
    rows = []
    for (model_code, horizon, bucket), sub in tdf.groupby(["model_code", "horizon", "candidate_bucket"], sort=True):
        rows.append(
            {
                "model_code": model_code,
                "horizon": horizon,
                "candidate_bucket": bucket,
                "n_obs": int(len(sub)),
                "avg_score": float(pd.to_numeric(sub["score_value"], errors="coerce").mean()),
                "avg_forward_return": float(pd.to_numeric(sub["forward_return"], errors="coerce").mean()),
                "median_forward_return": float(pd.to_numeric(sub["forward_return"], errors="coerce").median()),
            }
        )
    return pd.DataFrame(rows).sort_values(["model_code", "horizon", "candidate_bucket"]).reset_index(drop=True)


def fmt_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.2%}"


def fmt_num(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.3f}"


def build_markdown(summary: pd.DataFrame, tseries_bucket: pd.DataFrame, detail: pd.DataFrame) -> str:
    lines = [
        "# Model Output vs Forward Return Correlation",
        "",
        "- analysis date: `2026-04-24`",
        "- price asof: `2026-04-23`",
        "- forward horizons: `1W=5 trading days`, `2W=10 trading days`, `1M=21 trading days`, `3M=63 trading days`",
        "- user model score is treated as `target_weight proxy`",
        "- S4/S5/S6 score is treated as `weight proxy` because holdings history has no explicit score field",
        "- T-series score is `stage2_prob` when available, otherwise `stage1_prob`",
        "",
    ]

    if not summary.empty:
        lines.append("## Summary")
        lines.append("| Scope | Model | Horizon | N | Avg Return | Pooled Spearman(score) | Avg Daily IC(score) | Pooled Spearman(rank) |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for row in summary.itertuples(index=False):
            lines.append(
                f"| {row.scope} | {row.model_code} | {row.horizon} | {row.n_obs} | {fmt_pct(row.avg_forward_return)} | "
                f"{fmt_num(row.pooled_spearman_score)} | {fmt_num(row.avg_daily_ic_score)} | {fmt_num(row.rank_spearman_pooled)} |"
            )
        lines.append("")

        strongest = (
            summary.dropna(subset=["avg_daily_ic_score"])
            .sort_values("avg_daily_ic_score", ascending=False)
            .head(10)
        )
        lines.append("## Strongest Positive Links")
        if strongest.empty:
            lines.append("- no model had enough observations for daily IC calculation.")
        else:
            for row in strongest.itertuples(index=False):
                lines.append(
                    f"- `{row.scope}/{row.model_code} {row.horizon}`: avg daily IC `{fmt_num(row.avg_daily_ic_score)}`, "
                    f"pooled score Spearman `{fmt_num(row.pooled_spearman_score)}`, avg forward return `{fmt_pct(row.avg_forward_return)}`"
                )
        lines.append("")

    if not tseries_bucket.empty:
        lines.append("## T-Series Bucket View")
        lines.append("| Model | Horizon | Bucket | N | Avg Score | Avg Forward Return | Median Forward Return |")
        lines.append("|---|---:|---|---:|---:|---:|---:|")
        for row in tseries_bucket.itertuples(index=False):
            lines.append(
                f"| {row.model_code} | {row.horizon} | {row.candidate_bucket} | {row.n_obs} | {fmt_num(row.avg_score)} | "
                f"{fmt_pct(row.avg_forward_return)} | {fmt_pct(row.median_forward_return)} |"
            )
        lines.append("")

    sample_cov = (
        detail.groupby(["scope", "model_code"])["date"]
        .agg(["min", "max", "nunique"])
        .reset_index()
        .sort_values(["scope", "model_code"])
    )
    lines.append("## Coverage")
    for row in sample_cov.itertuples(index=False):
        lines.append(
            f"- `{row.scope}/{row.model_code}`: dates `{pd.Timestamp(row.min).strftime('%Y-%m-%d')}` -> `{pd.Timestamp(row.max).strftime('%Y-%m-%d')}`, "
            f"snapshots `{int(row.nunique)}`"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    px = load_prices()
    internal_df, _ = load_internal_rows()
    user_df, _ = load_user_rows()
    tseries_df, _ = load_tseries_rows()

    base_frames = [frame for frame in [internal_df, user_df, tseries_df] if not frame.empty]
    base = pd.concat(base_frames, ignore_index=True, sort=False) if base_frames else pd.DataFrame()
    base["ticker"] = base["ticker"].astype(str).str.zfill(6)
    detail = attach_forward_returns(base, px)

    summary, date_ic, bucket = summarize_correlations(detail)
    tseries_bucket = summarize_tseries_buckets(detail)

    detail.to_csv(OUTDIR / "model_output_forward_return_detail.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTDIR / "model_output_forward_return_summary.csv", index=False, encoding="utf-8-sig")
    date_ic.to_csv(OUTDIR / "model_output_forward_return_daily_ic.csv", index=False, encoding="utf-8-sig")
    bucket.to_csv(OUTDIR / "model_output_forward_return_score_buckets.csv", index=False, encoding="utf-8-sig")
    tseries_bucket.to_csv(OUTDIR / "tseries_bucket_forward_return_summary.csv", index=False, encoding="utf-8-sig")

    md = build_markdown(summary, tseries_bucket, detail)
    (OUTDIR / "model_output_forward_return_review.md").write_text(md, encoding="utf-8")
    print(f"[OK] wrote {OUTDIR}")


if __name__ == "__main__":
    main()
