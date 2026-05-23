from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd


ROOT = Path(r"D:\Quant")
I_DB = ROOT / r"data\db\i_series_research.db"
QUANT_DB = ROOT / r"data\db\quant_service.db"
DETAIL_DB = ROOT / r"data\db\quant_service_detail.db"
TSERIES_DB = ROOT / r"data\db\tseries_operational.db"
OUT_DB = ROOT / r"data\db\i_series_research.db"
OUT_DIR = ROOT / r"reports\i_series_stock_v01"
C_SERIES_DIR = ROOT / "reports" / "c_series"


def _load_i_latest(asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(I_DB)) as con:
        latest_date = pd.read_sql_query(
            "SELECT max(date) AS date FROM i_stock_v01_signals_weekly WHERE date <= ?",
            con,
            params=[asof],
        ).iloc[0]["date"]
        if pd.isna(latest_date):
            return pd.DataFrame()
        df = pd.read_sql_query(
            """
            SELECT date AS i_signal_date, ticker, name, i_signal, i_score, rsi14,
                   gap_price_cloud, lagging_strength_26, gap_span1_span2,
                   macd_hist, macd_hist_delta_5d
            FROM i_stock_v01_signals_weekly
            WHERE date = ?
            """,
            con,
            params=[latest_date],
        )
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df


def _load_s_latest(asof: str) -> pd.DataFrame:
    if not QUANT_DB.exists() or not DETAIL_DB.exists():
        return pd.DataFrame()
    with sqlite3.connect(str(QUANT_DB)) as con:
        current = pd.read_sql_query(
            """
            SELECT model_code, published_run_id, data_asof
            FROM pub_model_current
            WHERE model_code IN ('S2', 'S2_PIT_V01', 'S3', 'S3_CORE2', 'S3_ACCEL_V01', 'S4', 'S5', 'S6')
              AND data_asof <= ?
            """,
            con,
            params=[asof],
        )
    rows: list[pd.DataFrame] = []
    with sqlite3.connect(str(DETAIL_DB)) as con:
        for item in current.itertuples(index=False):
            frame = pd.read_sql_query(
                """
                SELECT ticker, rank_no, weight, score
                FROM run_holdings_history
                WHERE run_id = ?
                  AND date = ?
                  AND ticker IS NOT NULL
                  AND upper(ticker) <> 'CASH'
                """,
                con,
                params=[item.published_run_id, item.data_asof],
            )
            if frame.empty:
                continue
            frame["scope"] = "S"
            frame["base_model_code"] = item.model_code
            frame["base_asof_date"] = item.data_asof
            frame["base_bucket"] = "holding"
            frame["base_score"] = pd.to_numeric(frame["score"], errors="coerce")
            rows.append(frame)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    return out


def _load_t_latest(asof: str) -> pd.DataFrame:
    if not TSERIES_DB.exists():
        return pd.DataFrame()
    with sqlite3.connect(str(TSERIES_DB)) as con:
        latest_dates = pd.read_sql_query(
            """
            SELECT model_code, max(asof_date) AS asof_date
            FROM ts_candidates_latest
            WHERE asof_date <= ?
            GROUP BY model_code
            """,
            con,
            params=[asof],
        )
        frames = []
        for row in latest_dates.itertuples(index=False):
            frame = pd.read_sql_query(
                """
                SELECT ticker, name, candidate_bucket, stage1_prob, stage2_prob
                FROM ts_candidates_latest
                WHERE model_code = ? AND asof_date = ?
                """,
                con,
                params=[row.model_code, row.asof_date],
            )
            frame["scope"] = "T"
            frame["base_model_code"] = row.model_code
            frame["base_asof_date"] = row.asof_date
            frame["base_bucket"] = frame["candidate_bucket"]
            frame["base_score"] = pd.to_numeric(frame["stage2_prob"], errors="coerce").fillna(
                pd.to_numeric(frame["stage1_prob"], errors="coerce")
            )
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    return out


def _load_c_latest(asof: str) -> pd.DataFrame:
    files = sorted(C_SERIES_DIR.glob("c_series_v01_top_overlay_*.csv"))
    candidates: list[tuple[str, Path]] = []
    for path in files:
        token = path.stem.rsplit("_", 1)[-1]
        date = f"{token[:4]}-{token[4:6]}-{token[6:]}"
        if date <= asof:
            candidates.append((date, path))
    if not candidates:
        return pd.DataFrame()
    date, path = candidates[-1]
    df = pd.read_csv(path, dtype={"ticker": str})
    if df.empty:
        return df
    return pd.DataFrame(
        {
            "scope": "C",
            "base_model_code": df.get("base_model_code", "C-REL-V01"),
            "base_asof_date": date,
            "ticker": df["ticker"].astype(str).str.zfill(6),
            "name": df.get("name"),
            "base_bucket": df.get("relationship_status"),
            "base_score": pd.to_numeric(df.get("final_adjusted_score"), errors="coerce"),
        }
    )


def _overlay_status(signal: str) -> str:
    if signal in {"BUY", "HOLD"}:
        return "i_aligned"
    if signal in {"SELL", "EXIT_WATCH"}:
        return "i_conflict_or_exit_watch"
    return "i_neutral"


def build_overlay(asof: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    i_latest = _load_i_latest(asof)
    base = pd.concat([_load_s_latest(asof), _load_t_latest(asof), _load_c_latest(asof)], ignore_index=True)
    if base.empty:
        return pd.DataFrame(), pd.DataFrame()
    base["ticker"] = base["ticker"].astype(str).str.zfill(6)
    merged = base.merge(i_latest, on="ticker", how="left", suffixes=("", "_i"))
    merged["display_name"] = merged["name"].fillna(merged.get("name_i")).fillna(merged["ticker"])
    merged["i_signal"] = merged["i_signal"].fillna("NO_I_SIGNAL")
    merged["i_overlay_status"] = merged["i_signal"].map(_overlay_status).fillna("no_i_signal")
    keep = [
        "scope", "base_model_code", "base_asof_date", "ticker", "display_name", "base_bucket", "base_score",
        "i_signal_date", "i_signal", "i_overlay_status", "i_score", "rsi14", "gap_price_cloud",
        "lagging_strength_26", "gap_span1_span2", "macd_hist", "macd_hist_delta_5d",
    ]
    merged = merged[[col for col in keep if col in merged.columns]].sort_values(
        ["scope", "base_model_code", "i_overlay_status", "ticker"]
    )
    summary = (
        merged.groupby(["scope", "base_model_code", "i_overlay_status"], dropna=False)
        .agg(row_count=("ticker", "count"), avg_i_score=("i_score", "mean"))
        .reset_index()
    )
    return merged, summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Join latest S/T/C selected names with I-series technical signals.")
    ap.add_argument("--asof", required=True)
    ap.add_argument("--out-db", default=str(OUT_DB))
    ap.add_argument("--outdir", default=str(OUT_DIR))
    args = ap.parse_args()

    out_db = Path(args.out_db)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    overlay, summary = build_overlay(args.asof)
    with sqlite3.connect(str(out_db)) as con:
        overlay.to_sql("i_stock_v01_overlay_latest", con, if_exists="replace", index=False)
        summary.to_sql("i_stock_v01_overlay_summary", con, if_exists="replace", index=False)

    md_path = outdir / f"I_STOCK_V01_OVERLAY_REVIEW_{args.asof.replace('-', '')}.md"
    lines = [
        f"# I-STOCK-V01 Overlay Review ({args.asof})",
        "",
        "## Summary",
        "",
        "| scope | model | status | rows | avg_i_score |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for row in summary.itertuples(index=False):
        avg_score = "" if pd.isna(row.avg_i_score) else f"{float(row.avg_i_score):.2f}"
        lines.append(f"| {row.scope} | {row.base_model_code} | {row.i_overlay_status} | {int(row.row_count)} | {avg_score} |")
    lines.extend(["", "## Interpretation", "", "- `i_aligned`: 기존 S/T/C 후보가 I-series 기준 BUY/HOLD 상태입니다.", "- `i_conflict_or_exit_watch`: 기존 후보지만 I-series 기준 SELL 또는 EXIT_WATCH 상태입니다.", "- `i_neutral`: 기존 후보지만 I-series 타이밍 신호는 중립입니다."])
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "asof": args.asof,
        "overlay_rows": int(len(overlay)),
        "summary_rows": int(len(summary)),
        "db": str(out_db),
        "markdown": str(md_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
