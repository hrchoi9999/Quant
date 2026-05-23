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
TSERIES_DB = ROOT / r"data\db\tseries_operational.db"
DEFAULT_I_DB = ROOT / r"data\db\i_series_research_strong_rsi_raw_top30_s65_recheck.db"
OUT_DB = ROOT / r"data\db\i_series_research.db"
OUT_DIR = ROOT / r"reports\i_series_stock_v01"
FORWARD_COLS = ["ret_fwd_1w", "ret_fwd_2w", "ret_fwd_4w", "ret_fwd_8w", "ret_fwd_12w"]


def _zfill(frame: pd.DataFrame, col: str = "ticker") -> pd.DataFrame:
    out = frame.copy()
    out[col] = out[col].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    return out


def _pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def load_tstock_candidates(start: str, asof: str, horizon: str) -> pd.DataFrame:
    with sqlite3.connect(str(TSERIES_DB)) as con:
        df = pd.read_sql_query(
            """
            SELECT model_code AS base_model_code,
                   signal_date AS base_date,
                   ticker,
                   name,
                   candidate_bucket,
                   horizon,
                   stage1_prob,
                   stage2_prob,
                   actual_t10_hit,
                   actual_t3_hit
            FROM ts_candidates_history
            WHERE model_code = 'T-STOCK-V01'
              AND signal_date >= ?
              AND signal_date <= ?
              AND horizon = ?
              AND ticker IS NOT NULL
            ORDER BY signal_date, candidate_bucket, ticker
            """,
            con,
            params=[start, asof, horizon],
            parse_dates=["base_date"],
        )
    if df.empty:
        return df
    out = _zfill(df)
    out["base_score"] = pd.to_numeric(out["stage2_prob"], errors="coerce").fillna(
        pd.to_numeric(out["stage1_prob"], errors="coerce")
    )
    out["weight"] = 1.0
    return out


def load_tstock_latest(asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(TSERIES_DB)) as con:
        latest_asof = pd.read_sql_query(
            """
            SELECT max(asof_date) AS asof_date
            FROM ts_candidates_latest
            WHERE model_code = 'T-STOCK-V01'
              AND asof_date <= ?
            """,
            con,
            params=[asof],
        )["asof_date"].iloc[0]
        if latest_asof is None:
            return pd.DataFrame()
        df = pd.read_sql_query(
            """
            SELECT model_code AS base_model_code,
                   asof_date AS base_date,
                   ticker,
                   name,
                   candidate_bucket,
                   stage1_prob,
                   stage2_prob
            FROM ts_candidates_latest
            WHERE model_code = 'T-STOCK-V01'
              AND asof_date = ?
            ORDER BY candidate_bucket, ticker
            """,
            con,
            params=[latest_asof],
            parse_dates=["base_date"],
        )
    if df.empty:
        return df
    out = _zfill(df)
    out["base_score"] = pd.to_numeric(out["stage2_prob"], errors="coerce").fillna(
        pd.to_numeric(out["stage1_prob"], errors="coerce")
    )
    out["weight"] = 1.0
    return out


def load_i_weekly(i_db: Path, start: str, asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(i_db)) as con:
        df = pd.read_sql_query(
            """
            SELECT date AS i_date, ticker, i_signal, i_raw_score, i_score,
                   universe_rank_no, universe_rank_score, heat_bucket, earlyness_score,
                   rsi14, ret_21d, ret_63d, ret_252d, gap_ma200
            FROM i_stock_v01_signals_weekly
            WHERE date >= ?
              AND date <= ?
            ORDER BY ticker, date
            """,
            con,
            params=[start, asof],
            parse_dates=["i_date"],
        )
    return _zfill(df) if not df.empty else df


def load_i_forward(i_db: Path, start: str, asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(i_db)) as con:
        df = pd.read_sql_query(
            f"""
            SELECT date AS base_date, ticker, {", ".join(FORWARD_COLS)}
            FROM i_stock_v01_features_daily
            WHERE date >= ?
              AND date <= ?
            ORDER BY ticker, date
            """,
            con,
            params=[start, asof],
            parse_dates=["base_date"],
        )
    return _zfill(df) if not df.empty else df


def attach_i_state(base: pd.DataFrame, i_weekly: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    h = base.sort_values(["ticker", "base_date"]).copy()
    i = i_weekly.sort_values(["ticker", "i_date"]).copy()
    for ticker, hframe in h.groupby("ticker", sort=False):
        iframe = i.loc[i["ticker"] == ticker].copy()
        if iframe.empty:
            out = hframe.copy()
            for col in [
                "i_date",
                "i_signal",
                "i_raw_score",
                "i_score",
                "universe_rank_no",
                "universe_rank_score",
                "heat_bucket",
                "earlyness_score",
                "rsi14",
                "ret_21d",
                "ret_63d",
                "ret_252d",
                "gap_ma200",
            ]:
                out[col] = np.nan
            rows.append(out)
            continue
        rows.append(
            pd.merge_asof(
                hframe.sort_values("base_date"),
                iframe.sort_values("i_date"),
                left_on="base_date",
                right_on="i_date",
                by="ticker",
                direction="backward",
            )
        )
    out = pd.concat(rows, ignore_index=True)
    out["heat_bucket"] = out["heat_bucket"].fillna("no_i_state")
    return out


def attach_forward_returns(tagged: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    f = forward.copy()
    f["base_date"] = pd.to_datetime(f["base_date"]).dt.strftime("%Y-%m-%d")
    out = tagged.copy()
    out["base_date"] = pd.to_datetime(out["base_date"]).dt.strftime("%Y-%m-%d")
    return out.merge(f, on=["ticker", "base_date"], how="left")


def summarize_forward(tagged: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = ["base_model_code", "candidate_bucket", "heat_bucket"]
    for keys, frame in tagged.groupby(group_cols, dropna=False):
        row = {
            "base_model_code": keys[0],
            "candidate_bucket": keys[1],
            "heat_bucket": keys[2],
            "rows": int(len(frame)),
            "snapshots": int(frame["base_date"].nunique()),
            "tickers": int(frame["ticker"].nunique()),
        }
        row["avg_stage1_prob"] = (
            float(pd.to_numeric(frame["stage1_prob"], errors="coerce").mean())
            if frame["stage1_prob"].notna().any()
            else None
        )
        row["avg_stage2_prob"] = (
            float(pd.to_numeric(frame["stage2_prob"], errors="coerce").mean())
            if frame["stage2_prob"].notna().any()
            else None
        )
        row["avg_i_raw_score"] = (
            float(pd.to_numeric(frame["i_raw_score"], errors="coerce").mean())
            if frame["i_raw_score"].notna().any()
            else None
        )
        if "actual_t10_hit" in frame.columns:
            row["t10_hit_rate"] = float(pd.to_numeric(frame["actual_t10_hit"], errors="coerce").mean())
            row["t3_hit_rate"] = float(pd.to_numeric(frame["actual_t3_hit"], errors="coerce").mean())
        for col in FORWARD_COLS:
            label = col.replace("ret_fwd_", "")
            vals = pd.to_numeric(frame[col], errors="coerce").dropna()
            row[f"avg_{label}"] = None if vals.empty else float(vals.mean())
            row[f"win_{label}"] = None if vals.empty else float((vals > 0).mean())
            row[f"n_{label}"] = int(len(vals))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(group_cols).reset_index(drop=True)


def summarize_overlay_policy(tagged: pd.DataFrame) -> pd.DataFrame:
    variants = {
        "all_t_candidates": None,
        "reaccel_only": {"reacceleration"},
        "reaccel_overheat": {"reacceleration", "overheated_watch"},
        "non_early": {"reacceleration", "overheated_watch", "no_i_state"},
    }
    rows: list[dict[str, Any]] = []
    for bucket, bucket_frame in tagged.groupby("candidate_bucket", dropna=False):
        for variant, allowed in variants.items():
            frame = bucket_frame if allowed is None else bucket_frame.loc[bucket_frame["heat_bucket"].isin(allowed)]
            row = {
                "base_model_code": "T-STOCK-V01",
                "candidate_bucket": bucket,
                "variant": variant,
                "rows": int(len(frame)),
                "coverage": 0.0 if len(bucket_frame) == 0 else float(len(frame) / len(bucket_frame)),
                "snapshots": int(frame["base_date"].nunique()) if not frame.empty else 0,
                "tickers": int(frame["ticker"].nunique()) if not frame.empty else 0,
            }
            if frame.empty:
                for col in ["ret_fwd_4w", "ret_fwd_8w", "ret_fwd_12w"]:
                    label = col.replace("ret_fwd_", "")
                    row[f"avg_{label}"] = None
                    row[f"win_{label}"] = None
                row["t10_hit_rate"] = None
                row["t3_hit_rate"] = None
            else:
                row["t10_hit_rate"] = float(pd.to_numeric(frame["actual_t10_hit"], errors="coerce").mean())
                row["t3_hit_rate"] = float(pd.to_numeric(frame["actual_t3_hit"], errors="coerce").mean())
                for col in ["ret_fwd_4w", "ret_fwd_8w", "ret_fwd_12w"]:
                    label = col.replace("ret_fwd_", "")
                    vals = pd.to_numeric(frame[col], errors="coerce").dropna()
                    row[f"avg_{label}"] = None if vals.empty else float(vals.mean())
                    row[f"win_{label}"] = None if vals.empty else float((vals > 0).mean())
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["candidate_bucket", "variant"]).reset_index(drop=True)


def write_report(summary: pd.DataFrame, policy: pd.DataFrame, latest: pd.DataFrame, outdir: Path, asof: str, horizon: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"I_REACCEL_TSERIES_OVERLAY_{asof.replace('-', '')}.md"
    lines = [
        f"# I Reaccel T-Series Overlay ({asof})",
        "",
        f"- 대상: `T-STOCK-V01` historical candidates, horizon `{horizon}`",
        "- 제외: `T-ETF-V01`은 I-STOCK 지표와 자산군이 달라 직접 overlay 검증에서 제외",
        "",
        "## Forward Return By T Bucket And I Heat Bucket",
        "",
        "| model | T bucket | I heat bucket | rows | snaps | tickers | avg 4w | avg 8w | avg 12w | win 4w | T10 hit | T3 hit | avg I raw |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            f"| {row.base_model_code} | {row.candidate_bucket} | {row.heat_bucket} | {int(row.rows)} | "
            f"{int(row.snapshots)} | {int(row.tickers)} | {_pct(getattr(row, 'avg_4w'))} | "
            f"{_pct(getattr(row, 'avg_8w'))} | {_pct(getattr(row, 'avg_12w'))} | "
            f"{_pct(getattr(row, 'win_4w'))} | {_pct(getattr(row, 't10_hit_rate'))} | "
            f"{_pct(getattr(row, 't3_hit_rate'))} | {_num(getattr(row, 'avg_i_raw_score'))} |"
        )
    lines.extend(
        [
            "",
            "## Overlay Policy Comparison",
            "",
            "| T bucket | variant | rows | coverage | avg 4w | avg 8w | avg 12w | win 4w | T10 hit | T3 hit |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in policy.itertuples(index=False):
        lines.append(
            f"| {row.candidate_bucket} | {row.variant} | {int(row.rows)} | {_pct(row.coverage)} | "
            f"{_pct(getattr(row, 'avg_4w'))} | {_pct(getattr(row, 'avg_8w'))} | {_pct(getattr(row, 'avg_12w'))} | "
            f"{_pct(getattr(row, 'win_4w'))} | {_pct(row.t10_hit_rate)} | {_pct(row.t3_hit_rate)} |"
        )
    lines.extend(
        [
            "",
            "## Latest T-STOCK Candidates Tagged With I State",
            "",
            "| T bucket | I heat bucket | rows | avg stage1 | avg stage2 | avg I raw |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    if latest.empty:
        lines.append("| - | - | 0 |  |  |  |")
    else:
        latest_summary = (
            latest.groupby(["candidate_bucket", "heat_bucket"], dropna=False)
            .agg(
                rows=("ticker", "count"),
                avg_stage1=("stage1_prob", "mean"),
                avg_stage2=("stage2_prob", "mean"),
                avg_i_raw=("i_raw_score", "mean"),
            )
            .reset_index()
            .sort_values(["candidate_bucket", "heat_bucket"])
        )
        for row in latest_summary.itertuples(index=False):
            lines.append(
                f"| {row.candidate_bucket} | {row.heat_bucket} | {int(row.rows)} | "
                f"{_num(row.avg_stage1, 4)} | {_num(row.avg_stage2, 4)} | {_num(row.avg_i_raw)} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation Guide",
            "",
            "- `all_t_candidates`: T-STOCK 후보를 모두 사용한 기준선.",
            "- `reaccel_only`: I 상태가 `reacceleration`인 후보만 유지.",
            "- `reaccel_overheat`: I 상태가 `reacceleration` 또는 `overheated_watch`인 후보만 유지.",
            "- `non_early`: `early`만 제외하는 완화형 필터.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Test whether I reaccel/overheat states improve T-STOCK candidate quality.")
    ap.add_argument("--asof", default="2026-04-29")
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--horizon", default="3M")
    ap.add_argument("--i-db", default=str(DEFAULT_I_DB))
    ap.add_argument("--out-db", default=str(OUT_DB))
    ap.add_argument("--outdir", default=str(OUT_DIR))
    args = ap.parse_args()

    i_db = Path(args.i_db)
    candidates = load_tstock_candidates(args.start, args.asof, args.horizon)
    i_weekly = load_i_weekly(i_db, args.start, args.asof)
    forward = load_i_forward(i_db, args.start, args.asof)
    if candidates.empty or i_weekly.empty or forward.empty:
        raise SystemExit("missing T-STOCK candidates, I weekly signals, or forward returns")

    tagged = attach_i_state(candidates, i_weekly)
    tagged = attach_forward_returns(tagged, forward)
    tagged["base_date"] = pd.to_datetime(tagged["base_date"]).dt.strftime("%Y-%m-%d")
    summary = summarize_forward(tagged)
    policy = summarize_overlay_policy(tagged)

    latest = load_tstock_latest(args.asof)
    if not latest.empty:
        latest = attach_i_state(latest, i_weekly)
        latest["base_date"] = pd.to_datetime(latest["base_date"]).dt.strftime("%Y-%m-%d")

    out_db = Path(args.out_db)
    with sqlite3.connect(str(out_db)) as con:
        tagged.to_sql("i_reaccel_tseries_overlay_history", con, if_exists="replace", index=False)
        summary.to_sql("i_reaccel_tseries_overlay_forward_summary", con, if_exists="replace", index=False)
        policy.to_sql("i_reaccel_tseries_overlay_policy_summary", con, if_exists="replace", index=False)
        latest.to_sql("i_reaccel_tseries_overlay_latest", con, if_exists="replace", index=False)
        pd.DataFrame(
            [
                {
                    "asof_date": args.asof,
                    "start": args.start,
                    "horizon": args.horizon,
                    "i_db": str(i_db),
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "tagged_rows": int(len(tagged)),
                    "latest_rows": int(len(latest)),
                    "excluded_model_note": "T-ETF-V01 excluded because I-STOCK signals are not ETF-native.",
                }
            ]
        ).to_sql("i_reaccel_tseries_overlay_run_meta", con, if_exists="replace", index=False)

    report = write_report(summary, policy, latest, Path(args.outdir), args.asof, args.horizon)
    print(
        json.dumps(
            {
                "status": "ok",
                "asof": args.asof,
                "horizon": args.horizon,
                "tagged_rows": int(len(tagged)),
                "summary_rows": int(len(summary)),
                "policy_rows": int(len(policy)),
                "latest_rows": int(len(latest)),
                "report": str(report),
                "out_db": str(out_db),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
