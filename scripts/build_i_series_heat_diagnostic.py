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
ISERIES_DB = ROOT / r"data\db\i_series_operational.db"
REPORT_DIR = ROOT / r"reports\i_series_stock_v01\diagnostics"


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def _safe_round(value: Any, digits: int = 6) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _pct(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.{digits}f}%"


def _num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.{digits}f}"


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows_"
    cols = [str(col) for col in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in df.itertuples(index=False):
        values = []
        for value in row:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                values.append("-")
            else:
                values.append(str(value).replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def classify_heat(row: pd.Series) -> tuple[str, float, list[str]]:
    ret_1y = float(row.get("ret_252d") or 0.0)
    ret_3m = float(row.get("ret_63d") or 0.0)
    ret_1m = float(row.get("ret_21d") or 0.0)
    rsi14 = float(row.get("rsi14") or 50.0)
    gap_ma200 = float(row.get("gap_ma200") or 0.0)
    pct_below_52w_high = float(row.get("pct_below_52w_high") or 0.0)

    reasons: list[str] = []
    if ret_1y >= 2.0:
        reasons.append("1Y +200% 이상")
    elif ret_1y >= 1.0:
        reasons.append("1Y +100% 이상")
    if rsi14 >= 75:
        reasons.append("RSI 75+")
    elif rsi14 >= 70:
        reasons.append("RSI 70+")
    if gap_ma200 >= 1.2:
        reasons.append("MA200 +120% 이격")
    elif gap_ma200 >= 0.7:
        reasons.append("MA200 +70% 이격")
    if ret_3m >= 0.5:
        reasons.append("3M +50% 이상")
    if pct_below_52w_high >= -0.03 and ret_1y >= 0.8:
        reasons.append("52주 고점 3% 이내")

    penalty = 0.0
    penalty += min(max(ret_1y - 0.5, 0.0) * 22.0, 35.0)
    penalty += min(max(ret_3m - 0.3, 0.0) * 35.0, 20.0)
    penalty += min(max(ret_1m - 0.18, 0.0) * 35.0, 10.0)
    penalty += min(max(rsi14 - 65.0, 0.0) * 1.4, 20.0)
    penalty += min(max(gap_ma200 - 0.4, 0.0) * 25.0, 20.0)
    if pct_below_52w_high >= -0.03 and ret_1y >= 0.8:
        penalty += 8.0
    earlyness_score = max(0.0, min(100.0, 100.0 - penalty))

    severe_overheat = (
        ret_1y >= 2.0
        or gap_ma200 >= 1.2
        or (rsi14 >= 75 and ret_3m >= 0.35)
        or (ret_1y >= 1.0 and rsi14 >= 70 and gap_ma200 >= 0.7)
    )
    reacceleration = (
        ret_1y >= 0.8
        or ret_3m >= 0.4
        or rsi14 >= 70
        or gap_ma200 >= 0.6
        or (pct_below_52w_high >= -0.05 and ret_1y >= 0.5)
    )
    if severe_overheat:
        bucket = "overheated_watch"
    elif reacceleration:
        bucket = "reacceleration"
    else:
        bucket = "early"
        if not reasons:
            reasons.append("과열 징후 낮음")
    return bucket, earlyness_score, reasons


def load_candidates(model_code: str, asof: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(str(ISERIES_DB)) as con:
        latest = pd.read_sql_query(
            """
            SELECT *
            FROM is_candidates_latest
            WHERE model_code = ?
              AND asof_date <= ?
            ORDER BY portfolio_rank_no, ticker
            """,
            con,
            params=[model_code, asof],
        )
        hist = pd.read_sql_query(
            """
            SELECT *
            FROM is_candidates_history
            WHERE model_code = ?
              AND signal_date <= ?
            ORDER BY signal_date, portfolio_rank_no, ticker
            """,
            con,
            params=[model_code, asof],
        )
    if latest.empty or hist.empty:
        raise SystemExit(f"no I-series candidates found: model={model_code}, asof={asof}")
    latest["ticker"] = latest["ticker"].astype(str).str.zfill(6)
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    latest_asof = latest["asof_date"].max()
    latest = latest.loc[latest["asof_date"] == latest_asof].copy()
    return latest, hist


def load_price_features(tickers: list[str], asof: str) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in tickers)
    sql = f"""
        SELECT ticker, date, close, high
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND date <= ?
        ORDER BY ticker, date
    """
    with sqlite3.connect(str(PRICE_DB)) as con:
        prices = pd.read_sql_query(sql, con, params=[*tickers, asof])
    if prices.empty:
        raise SystemExit("no price rows found for I-series candidates")
    prices["ticker"] = prices["ticker"].astype(str).str.zfill(6)
    prices["date"] = pd.to_datetime(prices["date"])
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices["high"] = pd.to_numeric(prices["high"], errors="coerce")
    frames: list[pd.DataFrame] = []
    for ticker, frame in prices.groupby("ticker", sort=False):
        f = frame.sort_values("date").copy()
        close = f["close"]
        f["ret_21d"] = close.pct_change(21)
        f["ret_63d"] = close.pct_change(63)
        f["ret_126d"] = close.pct_change(126)
        f["ret_252d"] = close.pct_change(252)
        f["ma_200"] = close.rolling(200, min_periods=120).mean()
        f["gap_ma200"] = close / f["ma_200"] - 1.0
        f["rsi14"] = _rsi(close, 14)
        f["high_252d"] = f["high"].rolling(252, min_periods=120).max()
        f["pct_below_52w_high"] = close / f["high_252d"] - 1.0
        f["ticker"] = ticker
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def attach_features(candidates: pd.DataFrame, features: pd.DataFrame, date_col: str) -> pd.DataFrame:
    c = candidates.copy()
    c[date_col] = pd.to_datetime(c[date_col])
    f = features.sort_values(["ticker", "date"]).copy()
    merged: list[pd.DataFrame] = []
    for ticker, cf in c.groupby("ticker", sort=False):
        ff = f.loc[f["ticker"] == ticker].copy()
        if ff.empty:
            continue
        merged.append(
            pd.merge_asof(
                cf.sort_values(date_col),
                ff.sort_values("date"),
                left_on=date_col,
                right_on="date",
                by="ticker",
                direction="backward",
            )
        )
    if not merged:
        return pd.DataFrame()
    out = pd.concat(merged, ignore_index=True)
    classified = out.apply(classify_heat, axis=1, result_type="expand")
    out["heat_bucket"] = classified[0]
    out["earlyness_score"] = classified[1].astype(float).round(2)
    out["heat_reasons"] = classified[2].apply(lambda values: ", ".join(values))
    return out


def summarize_history(history_diag: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bucket, frame in history_diag.groupby("heat_bucket"):
        rows.append(
            {
                "heat_bucket": bucket,
                "rows": int(len(frame)),
                "avg_earlyness_score": round(float(frame["earlyness_score"].mean()), 2),
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
    return pd.DataFrame(rows).sort_values("heat_bucket", key=lambda s: s.map(order)).reset_index(drop=True)


def write_outputs(
    *,
    model_code: str,
    asof: str,
    latest_diag: pd.DataFrame,
    history_diag: pd.DataFrame,
    summary: pd.DataFrame,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_asof = asof.replace("-", "")
    csv_path = REPORT_DIR / f"{model_code}_HEAT_DIAGNOSTIC_LATEST_{safe_asof}.csv"
    report_path = REPORT_DIR / f"{model_code}_HEAT_DIAGNOSTIC_{safe_asof}.md"
    latest_diag.to_csv(csv_path, index=False, encoding="utf-8-sig")

    with sqlite3.connect(str(ISERIES_DB)) as con:
        latest_diag.to_sql("is_heat_diagnostic_latest", con, if_exists="replace", index=False)
        history_diag.to_sql("is_heat_diagnostic_history", con, if_exists="replace", index=False)
        summary.to_sql("is_heat_diagnostic_summary", con, if_exists="replace", index=False)

    latest_cols = [
        "portfolio_rank_no",
        "ticker",
        "name",
        "candidate_bucket",
        "i_raw_score",
        "display_score",
        "ret_21d",
        "ret_63d",
        "ret_252d",
        "rsi14",
        "gap_ma200",
        "pct_below_52w_high",
        "earlyness_score",
        "heat_bucket",
        "heat_reasons",
    ]
    lines: list[str] = []
    lines.append(f"# {model_code} Heat Diagnostic")
    lines.append("")
    lines.append(f"- asof: `{asof}`")
    lines.append(f"- generated_at: `{datetime.now().isoformat(timespec='seconds')}`")
    lines.append(f"- latest_rows: `{len(latest_diag)}`")
    lines.append(f"- history_rows: `{len(history_diag)}`")
    lines.append("")
    lines.append("## Latest Bucket Counts")
    lines.append("")
    counts = latest_diag["heat_bucket"].value_counts().rename_axis("heat_bucket").reset_index(name="count")
    lines.append(_markdown_table(counts))
    lines.append("")
    lines.append("## Historical Forward Return By Heat Bucket")
    lines.append("")
    show_summary = summary.copy()
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
        show_summary[col] = show_summary[col].apply(_pct)
    show_summary["avg_rsi14"] = show_summary["avg_rsi14"].apply(_num)
    show_summary["avg_earlyness_score"] = show_summary["avg_earlyness_score"].apply(_num)
    lines.append(_markdown_table(show_summary))
    lines.append("")
    lines.append("## Latest Top30 Diagnostic")
    lines.append("")
    show_latest = latest_diag[latest_cols].copy().sort_values("portfolio_rank_no")
    for col in ["ret_21d", "ret_63d", "ret_252d", "gap_ma200", "pct_below_52w_high"]:
        show_latest[col] = show_latest[col].apply(_pct)
    for col in ["i_raw_score", "display_score", "rsi14", "earlyness_score"]:
        show_latest[col] = show_latest[col].apply(_num)
    lines.append(_markdown_table(show_latest))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `early`는 과열 징후가 낮은 상승 초기/초기 회복 후보에 가깝다.")
    lines.append("- `reacceleration`은 이미 의미 있게 오른 뒤 다시 힘을 받는 추세 지속/재가속 후보에 가깝다.")
    lines.append("- `overheated_watch`는 1Y 급등, RSI 과열, MA200 과다 이격이 겹쳐 상승 초기로 보기 어려운 관찰 후보로 분리한다.")
    lines.append("- 이 분류는 hard exclude가 아니라 I-series 후보 해석을 위한 진단 overlay다.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Build I-series latest heat/earlyness diagnostic.")
    ap.add_argument("--model-code", default="I-STOCK-STRONG-RSI-V01")
    ap.add_argument("--asof", required=True)
    args = ap.parse_args()

    latest, hist = load_candidates(args.model_code, args.asof)
    tickers = sorted(hist["ticker"].unique().tolist())
    features = load_price_features(tickers, args.asof)
    latest_diag = attach_features(latest, features, "asof_date")
    history_diag = attach_features(hist, features, "signal_date")
    if latest_diag.empty or history_diag.empty:
        raise SystemExit("failed to attach price features to I-series candidates")
    summary = summarize_history(history_diag)
    report_path = write_outputs(
        model_code=args.model_code,
        asof=args.asof,
        latest_diag=latest_diag,
        history_diag=history_diag,
        summary=summary,
    )
    print(
        json.dumps(
            {
                "model_code": args.model_code,
                "asof": args.asof,
                "latest_rows": len(latest_diag),
                "history_rows": len(history_diag),
                "latest_bucket_counts": latest_diag["heat_bucket"].value_counts().to_dict(),
                "report_path": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
