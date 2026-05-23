from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
DEFAULT_I_DB = ROOT / r"data\db\i_series_research_strong_rsi_raw_top30_s65.db"
QUANT_DB = ROOT / r"data\db\quant_service.db"
DETAIL_DB = ROOT / r"data\db\quant_service_detail.db"
TSERIES_DB = ROOT / r"data\db\tseries_operational.db"
C_SERIES_DIR = ROOT / r"reports\c_series"
OUT_DB = ROOT / r"data\db\i_series_research.db"
OUT_DIR = ROOT / r"reports\i_series_stock_v01"


S_MODELS = ["S2", "S2_PIT_V01", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5", "S6"]
FORWARD_COLS = ["ret_fwd_1w", "ret_fwd_2w", "ret_fwd_4w", "ret_fwd_8w", "ret_fwd_12w"]


def _zfill_ticker(frame: pd.DataFrame, col: str = "ticker") -> pd.DataFrame:
    frame = frame.copy()
    frame[col] = frame[col].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    return frame


def _load_i_holdings(i_db: Path, start: str, asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(i_db)) as con:
        df = pd.read_sql_query(
            """
            SELECT date AS i_signal_date, ticker, name, portfolio_rank_no,
                   universe_rank_no, universe_rank_score, i_raw_score, i_score, i_signal
            FROM i_stock_v01_backtest_holdings
            WHERE date >= ? AND date <= ?
            """,
            con,
            params=[start, asof],
            parse_dates=["i_signal_date"],
        )
    if df.empty:
        return df
    return _zfill_ticker(df).sort_values(["i_signal_date", "portfolio_rank_no"]).reset_index(drop=True)


def _load_i_forward_returns(i_db: Path, start: str, asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(i_db)) as con:
        df = pd.read_sql_query(
            f"""
            SELECT ticker, date AS return_anchor_date, close, {", ".join(FORWARD_COLS)}
            FROM i_stock_v01_features_daily
            WHERE date >= ? AND date <= ?
            """,
            con,
            params=[start, asof],
            parse_dates=["return_anchor_date"],
        )
    if df.empty:
        return df
    return _zfill_ticker(df)


def _load_s_history(start: str, asof: str) -> pd.DataFrame:
    if not QUANT_DB.exists() or not DETAIL_DB.exists():
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(S_MODELS))
    with sqlite3.connect(str(QUANT_DB)) as con:
        current = pd.read_sql_query(
            f"""
            SELECT model_code, published_run_id
            FROM pub_model_current
            WHERE model_code IN ({placeholders})
            """,
            con,
            params=S_MODELS,
        )
    if current.empty:
        return pd.DataFrame()
    rows: list[pd.DataFrame] = []
    with sqlite3.connect(str(DETAIL_DB)) as con:
        for item in current.itertuples(index=False):
            frame = pd.read_sql_query(
                """
                SELECT date AS base_date, ticker, rank_no, weight, score
                FROM run_holdings_history
                WHERE run_id = ?
                  AND date >= ?
                  AND date <= ?
                  AND ticker IS NOT NULL
                  AND upper(ticker) <> 'CASH'
                """,
                con,
                params=[item.published_run_id, start, asof],
                parse_dates=["base_date"],
            )
            if frame.empty:
                continue
            frame["scope"] = "S"
            frame["base_model_code"] = item.model_code
            frame["base_bucket"] = "holding"
            frame["base_score"] = pd.to_numeric(frame["score"], errors="coerce")
            rows.append(frame)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    return _zfill_ticker(out)


def _load_t_history(start: str, asof: str) -> pd.DataFrame:
    if not TSERIES_DB.exists():
        return pd.DataFrame()
    with sqlite3.connect(str(TSERIES_DB)) as con:
        df = pd.read_sql_query(
            """
            SELECT asof_date AS base_date, model_code AS base_model_code, ticker, name,
                   candidate_bucket AS base_bucket, stage1_prob, stage2_prob
            FROM ts_candidates_latest
            WHERE asof_date >= ? AND asof_date <= ?
            """,
            con,
            params=[start, asof],
            parse_dates=["base_date"],
        )
    if df.empty:
        return df
    df["scope"] = "T"
    df["base_score"] = pd.to_numeric(df["stage2_prob"], errors="coerce").fillna(
        pd.to_numeric(df["stage1_prob"], errors="coerce")
    )
    return _zfill_ticker(df)


def _load_c_history(start: str, asof: str) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in sorted(C_SERIES_DIR.glob("c_series_v01_top_overlay_*.csv")):
        token = path.stem.rsplit("_", 1)[-1]
        date = pd.Timestamp(f"{token[:4]}-{token[4:6]}-{token[6:]}")
        if date < pd.Timestamp(start) or date > pd.Timestamp(asof):
            continue
        df = pd.read_csv(path, dtype={"ticker": str})
        if df.empty:
            continue
        frame = pd.DataFrame(
            {
                "scope": "C",
                "base_date": date,
                "base_model_code": df.get("base_model_code", "C-REL-V01"),
                "ticker": df["ticker"].astype(str).str.zfill(6),
                "name": df.get("name"),
                "base_bucket": df.get("relationship_status"),
                "base_score": pd.to_numeric(df.get("final_adjusted_score"), errors="coerce"),
            }
        )
        rows.append(frame)
    if not rows:
        return pd.DataFrame()
    return _zfill_ticker(pd.concat(rows, ignore_index=True))


def _latest_i_for_dates(i_holdings: pd.DataFrame, base_dates: list[pd.Timestamp]) -> dict[pd.Timestamp, pd.Timestamp]:
    i_dates = pd.Series(sorted(i_holdings["i_signal_date"].dropna().unique()))
    out: dict[pd.Timestamp, pd.Timestamp] = {}
    for base_date in sorted(pd.Timestamp(d) for d in base_dates):
        candidates = i_dates.loc[i_dates <= base_date]
        if not candidates.empty:
            out[base_date] = pd.Timestamp(candidates.iloc[-1])
    return out


def build_overlay(i_db: Path, start: str, asof: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    i_holdings = _load_i_holdings(i_db, start, asof)
    returns = _load_i_forward_returns(i_db, start, asof)
    base = pd.concat([_load_s_history(start, asof), _load_t_history(start, asof), _load_c_history(start, asof)], ignore_index=True)
    if i_holdings.empty or base.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    base["base_date"] = pd.to_datetime(base["base_date"])
    date_map = _latest_i_for_dates(i_holdings, base["base_date"].dropna().unique().tolist())
    i_by_date = {pd.Timestamp(date): frame.copy() for date, frame in i_holdings.groupby("i_signal_date")}

    overlay_rows: list[dict[str, object]] = []
    for (scope, model, base_date), base_frame in base.groupby(["scope", "base_model_code", "base_date"], dropna=False):
        base_date = pd.Timestamp(base_date)
        i_date = date_map.get(base_date)
        if i_date is None:
            continue
        i_frame = i_by_date.get(i_date, pd.DataFrame())
        base_codes = set(base_frame["ticker"].astype(str))
        i_codes = set(i_frame["ticker"].astype(str))

        base_lookup = base_frame.drop_duplicates("ticker").set_index("ticker")
        i_lookup = i_frame.drop_duplicates("ticker").set_index("ticker")
        all_codes = sorted(base_codes | i_codes)
        for ticker in all_codes:
            in_base = ticker in base_codes
            in_i = ticker in i_codes
            if in_base and in_i:
                group = "base_i_intersection"
            elif in_base:
                group = "base_only"
            else:
                group = "i_only"
            brow = base_lookup.loc[ticker] if in_base else None
            irow = i_lookup.loc[ticker] if in_i else None
            overlay_rows.append(
                {
                    "scope": scope,
                    "base_model_code": model,
                    "base_date": base_date.strftime("%Y-%m-%d"),
                    "i_signal_date": i_date.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "display_name": (
                        getattr(irow, "name", None)
                        if in_i and pd.notna(getattr(irow, "name", None))
                        else (getattr(brow, "name", None) if in_base and "name" in base_lookup.columns else ticker)
                    ),
                    "overlay_group": group,
                    "in_base": bool(in_base),
                    "in_i_top": bool(in_i),
                    "base_bucket": getattr(brow, "base_bucket", None) if in_base else None,
                    "base_score": getattr(brow, "base_score", np.nan) if in_base else np.nan,
                    "portfolio_rank_no": getattr(irow, "portfolio_rank_no", np.nan) if in_i else np.nan,
                    "universe_rank_no": getattr(irow, "universe_rank_no", np.nan) if in_i else np.nan,
                    "universe_rank_score": getattr(irow, "universe_rank_score", np.nan) if in_i else np.nan,
                    "i_raw_score": getattr(irow, "i_raw_score", np.nan) if in_i else np.nan,
                    "i_score": getattr(irow, "i_score", np.nan) if in_i else np.nan,
                    "i_signal": getattr(irow, "i_signal", None) if in_i else None,
                }
            )

    overlay = pd.DataFrame(overlay_rows)
    if overlay.empty:
        return overlay, pd.DataFrame(), pd.DataFrame()

    returns_keyed = returns.rename(columns={"return_anchor_date": "base_date"})
    returns_keyed["base_date"] = pd.to_datetime(returns_keyed["base_date"]).dt.strftime("%Y-%m-%d")
    overlay = overlay.merge(returns_keyed[["ticker", "base_date", *FORWARD_COLS]], on=["ticker", "base_date"], how="left")

    summary_rows: list[dict[str, object]] = []
    group_cols = ["scope", "base_model_code", "overlay_group"]
    for keys, frame in overlay.groupby(group_cols, dropna=False):
        row = dict(zip(group_cols, keys))
        row["row_count"] = int(len(frame))
        row["snapshot_count"] = int(frame["base_date"].nunique())
        row["avg_i_raw_score"] = float(pd.to_numeric(frame["i_raw_score"], errors="coerce").mean()) if frame["i_raw_score"].notna().any() else None
        row["avg_universe_rank_score"] = float(pd.to_numeric(frame["universe_rank_score"], errors="coerce").mean()) if frame["universe_rank_score"].notna().any() else None
        for col in FORWARD_COLS:
            vals = pd.to_numeric(frame[col], errors="coerce").dropna()
            row[f"avg_{col.replace('ret_fwd_', '')}"] = None if vals.empty else float(vals.mean())
            row[f"win_{col.replace('ret_fwd_', '')}"] = None if vals.empty else float((vals > 0).mean())
            row[f"n_{col.replace('ret_fwd_', '')}"] = int(len(vals))
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows).sort_values(["scope", "base_model_code", "overlay_group"])

    latest_date = overlay["base_date"].max()
    latest = overlay.loc[overlay["base_date"] == latest_date].copy()
    return overlay, summary, latest


def _format_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def write_report(summary: pd.DataFrame, latest: pd.DataFrame, outdir: Path, asof: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"I_STRONG_RSI_STC_OVERLAY_{asof.replace('-', '')}.md"
    lines = [
        f"# I Strong RSI Raw vs S/T/C Overlay ({asof})",
        "",
        "## Historical Forward Return Summary",
        "",
        "| scope | model | group | rows | snaps | avg 1w | avg 4w | avg 8w | avg 12w | win 4w |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            f"| {row.scope} | {row.base_model_code} | {row.overlay_group} | "
            f"{int(row.row_count)} | {int(row.snapshot_count)} | "
            f"{_format_pct(getattr(row, 'avg_1w'))} | {_format_pct(getattr(row, 'avg_4w'))} | "
            f"{_format_pct(getattr(row, 'avg_8w'))} | {_format_pct(getattr(row, 'avg_12w'))} | "
            f"{_format_pct(getattr(row, 'win_4w'))} |"
        )
    lines.extend(
        [
            "",
            "## Latest Overlay Counts",
            "",
            "| scope | model | group | rows | avg raw | avg universe rank score |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    if not latest.empty:
        latest_summary = (
            latest.groupby(["scope", "base_model_code", "overlay_group"], dropna=False)
            .agg(
                rows=("ticker", "count"),
                avg_raw=("i_raw_score", "mean"),
                avg_rank_score=("universe_rank_score", "mean"),
            )
            .reset_index()
            .sort_values(["scope", "base_model_code", "overlay_group"])
        )
        for row in latest_summary.itertuples(index=False):
            lines.append(
                f"| {row.scope} | {row.base_model_code} | {row.overlay_group} | {int(row.rows)} | "
                f"{'' if pd.isna(row.avg_raw) else f'{float(row.avg_raw):.2f}'} | "
                f"{'' if pd.isna(row.avg_rank_score) else f'{float(row.avg_rank_score):.2f}'} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation Guide",
            "",
            "- `base_i_intersection`: 기존 S/T/C 종목이 I strong RSI top30에도 포함된 합의 종목입니다.",
            "- `base_only`: 기존 S/T/C에는 있으나 I strong RSI top30에는 없는 종목입니다.",
            "- `i_only`: 해당 기존 모델에는 없지만 I strong RSI top30에는 있는 독립 발굴 후보입니다.",
            "- ETF 모델은 I-STOCK 신호 coverage가 제한되므로 해석에서 분리해야 합니다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze I strong RSI raw overlay against existing S/T/C selections.")
    ap.add_argument("--asof", default="2026-04-29")
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--i-db", default=str(DEFAULT_I_DB))
    ap.add_argument("--out-db", default=str(OUT_DB))
    ap.add_argument("--outdir", default=str(OUT_DIR))
    args = ap.parse_args()

    overlay, summary, latest = build_overlay(Path(args.i_db), args.start, args.asof)
    out_db = Path(args.out_db)
    outdir = Path(args.outdir)
    with sqlite3.connect(str(out_db)) as con:
        overlay.to_sql("i_strong_rsi_stc_overlay_history", con, if_exists="replace", index=False)
        summary.to_sql("i_strong_rsi_stc_overlay_summary", con, if_exists="replace", index=False)
        latest.to_sql("i_strong_rsi_stc_overlay_latest", con, if_exists="replace", index=False)
        pd.DataFrame(
            [
                {
                    "asof_date": args.asof,
                    "start": args.start,
                    "i_db": str(Path(args.i_db)),
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "overlay_rows": int(len(overlay)),
                    "summary_rows": int(len(summary)),
                    "latest_rows": int(len(latest)),
                }
            ]
        ).to_sql("i_strong_rsi_stc_overlay_run_meta", con, if_exists="replace", index=False)
    report = write_report(summary, latest, outdir, args.asof)
    print(
        json.dumps(
            {
                "status": "ok",
                "asof": args.asof,
                "overlay_rows": int(len(overlay)),
                "summary_rows": int(len(summary)),
                "latest_rows": int(len(latest)),
                "out_db": str(out_db),
                "report": str(report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
