from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_i_series_heat_diagnostic import (  # noqa: E402
    ISERIES_DB,
    REPORT_DIR,
    attach_features,
    load_price_features,
    _markdown_table,
    _num,
    _pct,
    _safe_round,
)

DEFAULT_RESEARCH_DB = ROOT / r"data\db\i_series_research_strong_rsi_raw_top30_s65.db"


def load_universe_signals(research_db: Path, asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(research_db)) as con:
        df = pd.read_sql_query(
            """
            SELECT ticker, date, name, market, rank_no, universe_rank_no, universe_rank_score,
                   i_raw_score, i_score AS display_score, i_signal,
                   ret_fwd_1w, ret_fwd_2w, ret_fwd_4w, ret_fwd_8w, ret_fwd_12w
            FROM i_stock_v01_signals_weekly
            WHERE date(date) <= date(?)
            ORDER BY date, rank_no, ticker
            """,
            con,
            params=[asof],
        )
    if df.empty:
        raise SystemExit(f"no weekly universe signals found: {research_db}, asof={asof}")
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def load_selected_keys(model_code: str, asof: str) -> set[tuple[str, str]]:
    with sqlite3.connect(str(ISERIES_DB)) as con:
        df = pd.read_sql_query(
            """
            SELECT signal_date, ticker
            FROM is_candidates_history
            WHERE model_code = ?
              AND signal_date <= ?
            """,
            con,
            params=[model_code, asof],
        )
    if df.empty:
        return set()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["signal_date"] = pd.to_datetime(df["signal_date"]).dt.strftime("%Y-%m-%d")
    return {(row.signal_date, row.ticker) for row in df.itertuples(index=False)}


def summarize(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bucket, frame in df.groupby("heat_bucket"):
        rows.append(
            {
                "scope": scope,
                "heat_bucket": bucket,
                "rows": int(len(frame)),
                "unique_tickers": int(frame["ticker"].nunique()),
                "avg_earlyness_score": round(float(frame["earlyness_score"].mean()), 2),
                "avg_i_raw_score": _safe_round(frame["i_raw_score"].mean()),
                "avg_ret_1m_at_signal": _safe_round(frame["ret_21d"].mean()),
                "avg_ret_3m_at_signal": _safe_round(frame["ret_63d"].mean()),
                "avg_ret_1y_at_signal": _safe_round(frame["ret_252d"].mean()),
                "avg_rsi14": _safe_round(frame["rsi14"].mean()),
                "avg_gap_ma200": _safe_round(frame["gap_ma200"].mean()),
                "avg_fwd_4w": _safe_round(frame["ret_fwd_4w"].mean()),
                "avg_fwd_8w": _safe_round(frame["ret_fwd_8w"].mean()),
                "avg_fwd_12w": _safe_round(frame["ret_fwd_12w"].mean()),
                "win_fwd_4w": _safe_round((frame["ret_fwd_4w"] > 0).mean()),
                "win_fwd_8w": _safe_round((frame["ret_fwd_8w"] > 0).mean()),
                "win_fwd_12w": _safe_round((frame["ret_fwd_12w"] > 0).mean()),
            }
        )
    order = {"early": 0, "reacceleration": 1, "overheated_watch": 2}
    return pd.DataFrame(rows).sort_values(["scope", "heat_bucket"], key=lambda s: s.map(order).fillna(99) if s.name == "heat_bucket" else s)


def format_summary(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in [
        "avg_ret_1m_at_signal",
        "avg_ret_3m_at_signal",
        "avg_ret_1y_at_signal",
        "avg_gap_ma200",
        "avg_fwd_4w",
        "avg_fwd_8w",
        "avg_fwd_12w",
        "win_fwd_4w",
        "win_fwd_8w",
        "win_fwd_12w",
    ]:
        out[col] = out[col].apply(_pct)
    for col in ["avg_earlyness_score", "avg_i_raw_score", "avg_rsi14"]:
        out[col] = out[col].apply(_num)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare I-series heat buckets across full universe, BUY/HOLD, and selected top30.")
    ap.add_argument("--model-code", default="I-STOCK-STRONG-RSI-V01")
    ap.add_argument("--asof", required=True)
    ap.add_argument("--research-db", default=str(DEFAULT_RESEARCH_DB))
    args = ap.parse_args()

    research_db = Path(args.research_db)
    signals = load_universe_signals(research_db, args.asof)
    selected_keys = load_selected_keys(args.model_code, args.asof)
    signals["is_model_selected"] = signals.apply(lambda row: (row["date"], row["ticker"]) in selected_keys, axis=1)
    tickers = sorted(signals["ticker"].unique().tolist())
    features = load_price_features(tickers, args.asof)
    diag = attach_features(signals, features, "date")
    if diag.empty:
        raise SystemExit("failed to attach price features to universe signals")

    full = diag.copy()
    buyhold = diag.loc[diag["i_signal"].isin(["BUY", "HOLD"])].copy()
    selected = diag.loc[diag["is_model_selected"]].copy()
    summaries = pd.concat(
        [
            summarize(full, "universe_all"),
            summarize(buyhold, "universe_buyhold"),
            summarize(selected, "model_top30"),
        ],
        ignore_index=True,
    )

    latest_date = pd.Timestamp(diag["date"].max()).strftime("%Y-%m-%d")
    latest_diag = diag.loc[diag["date"] == latest_date].copy()
    latest_summary = pd.concat(
        [
            summarize(latest_diag, "latest_universe_all"),
            summarize(latest_diag.loc[latest_diag["i_signal"].isin(["BUY", "HOLD"])], "latest_universe_buyhold"),
            summarize(latest_diag.loc[latest_diag["is_model_selected"]], "latest_model_top30"),
        ],
        ignore_index=True,
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_asof = args.asof.replace("-", "")
    report_path = REPORT_DIR / f"{args.model_code}_UNIVERSE_HEAT_DIAGNOSTIC_{safe_asof}.md"
    csv_path = REPORT_DIR / f"{args.model_code}_UNIVERSE_HEAT_DIAGNOSTIC_SUMMARY_{safe_asof}.csv"
    summaries.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with sqlite3.connect(str(ISERIES_DB)) as con:
        diag.to_sql("is_universe_heat_diagnostic_history", con, if_exists="replace", index=False)
        summaries.to_sql("is_universe_heat_diagnostic_summary", con, if_exists="replace", index=False)
        latest_summary.to_sql("is_universe_heat_diagnostic_latest_summary", con, if_exists="replace", index=False)

    lines: list[str] = []
    lines.append(f"# {args.model_code} Universe Heat Diagnostic")
    lines.append("")
    lines.append(f"- asof: `{args.asof}`")
    lines.append(f"- generated_at: `{datetime.now().isoformat(timespec='seconds')}`")
    lines.append(f"- research_db: `{research_db}`")
    lines.append(f"- universe_signal_rows: `{len(full)}`")
    lines.append(f"- buyhold_signal_rows: `{len(buyhold)}`")
    lines.append(f"- selected_rows: `{len(selected)}`")
    lines.append("")
    lines.append("## Historical Forward Return By Scope And Heat Bucket")
    lines.append("")
    lines.append(_markdown_table(format_summary(summaries)))
    lines.append("")
    lines.append("## Latest Scope Counts And Forward Context")
    lines.append("")
    lines.append(_markdown_table(format_summary(latest_summary)))
    lines.append("")
    lines.append("## Interpretation Guide")
    lines.append("")
    lines.append("- `universe_all`은 모델이 매수 후보로 보지 않는 전체 400개까지 포함한다.")
    lines.append("- `universe_buyhold`는 I 신호가 BUY/HOLD인 전체 후보군이다.")
    lines.append("- `model_top30`은 실제 운영 후보로 추출된 30개 이력이다.")
    lines.append("- 세 층을 함께 봐야 heat bucket이 universe 전체에서 좋은지, 또는 I score로 선별된 뒤에만 좋은지 구분할 수 있다.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "model_code": args.model_code,
                "asof": args.asof,
                "universe_rows": len(full),
                "buyhold_rows": len(buyhold),
                "selected_rows": len(selected),
                "latest_date": latest_date,
                "report_path": str(report_path),
                "summary_csv": str(csv_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
