from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
CORE_DB = PROJECT_ROOT / r"data\db\quant_service.db"
DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"

DISCLAIMER_TEXT = "Backtest-based model data for service display. Not investment advice."


@dataclass
class PublishSpec:
    model_code: str
    run_id: str
    asof_date: str


def _load_runs_to_publish(con: sqlite3.Connection, asof_date: str, models: list[str] | None) -> list[PublishSpec]:
    params: list[str] = [asof_date]
    sql = """
    SELECT rr.model_code, rr.run_id, rr.asof_date
    FROM run_runs rr
    JOIN meta_models mm ON mm.model_code = rr.model_code
    WHERE rr.status='completed'
      AND rr.asof_date=?
      AND mm.service_enabled=1
    """
    if models:
        placeholders = ",".join(["?"] * len(models))
        sql += f" AND rr.model_code IN ({placeholders})"
        params.extend(models)
    sql += " ORDER BY rr.model_code, rr.created_at DESC"
    df = pd.read_sql_query(sql, con, params=params)
    if df.empty:
        return []
    df = df.drop_duplicates(subset=["model_code"], keep="first")
    return [PublishSpec(model_code=row.model_code, run_id=row.run_id, asof_date=row.asof_date) for row in df.itertuples(index=False)]


def _load_meta(con: sqlite3.Connection, model_code: str) -> dict:
    row = con.execute(
        "SELECT display_name, description, benchmark_code, risk_grade FROM meta_models WHERE model_code=?",
        (model_code,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"meta_models missing: {model_code}")
    return {
        "display_name": row[0],
        "description": row[1],
        "benchmark_code": row[2],
        "risk_grade": row[3],
    }


def _load_nav(detail_con: sqlite3.Connection, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT date, nav, drawdown, holdings_count, cash_weight, exposure, gate_open, gate_breadth, benchmark_nav FROM run_nav_daily WHERE run_id=? ORDER BY date",
        detail_con,
        params=[run_id],
    )


def _load_current_holdings(detail_con: sqlite3.Connection, run_id: str) -> tuple[pd.DataFrame, str | None, pd.DataFrame]:
    hist = pd.read_sql_query(
        "SELECT date, ticker, rank_no, weight, score, entry_date, entry_price, current_price, cum_return_since_entry, reason_summary FROM run_holdings_history WHERE run_id=? ORDER BY date, rank_no, ticker",
        detail_con,
        params=[run_id],
    )
    if hist.empty:
        return hist, None, hist
    latest_date = str(hist["date"].max())
    current = hist[hist["date"].astype(str) == latest_date].copy()
    if current["weight"].isna().all() and len(current) > 0:
        current["weight"] = 1.0 / len(current)
    return current, latest_date, hist


def _nearest_nav(nav: pd.DataFrame, target_date: pd.Timestamp) -> pd.Series | None:
    x = nav[nav["_dt"] <= target_date]
    if x.empty:
        return None
    return x.iloc[-1]


def _calc_period_stats(nav: pd.DataFrame, start_idx: int) -> tuple[float | None, float | None]:
    seg = nav.iloc[start_idx:].copy()
    if len(seg) < 2:
        return None, None
    seg["ret"] = seg["nav"].pct_change().fillna(0.0)
    vol = float(seg["ret"].std(ddof=0)) if len(seg) > 1 else 0.0
    sharpe = None if vol <= 0 else float((seg["ret"].mean() / vol) * (252.0 ** 0.5))
    peak = seg["nav"].cummax()
    mdd = float((seg["nav"] / peak - 1.0).min())
    return sharpe, mdd


def _build_performance_rows(model_code: str, asof_date: str, nav: pd.DataFrame) -> list[tuple]:
    if nav.empty:
        return []
    nav = nav.copy()
    nav["_dt"] = pd.to_datetime(nav["date"])
    nav["nav"] = pd.to_numeric(nav["nav"], errors="coerce")
    nav = nav.dropna(subset=["nav"]).copy()
    if nav.empty:
        return []
    latest = nav.iloc[-1]
    latest_dt = latest["_dt"]
    periods = {
        "M1": latest_dt - pd.DateOffset(months=1),
        "M3": latest_dt - pd.DateOffset(months=3),
        "M6": latest_dt - pd.DateOffset(months=6),
        "YTD": pd.Timestamp(year=latest_dt.year, month=1, day=1),
        "Y1": latest_dt - pd.DateOffset(years=1),
        "ITD": nav.iloc[0]["_dt"],
    }
    rows = []
    for code, target_dt in periods.items():
        start_row = _nearest_nav(nav, target_dt)
        if start_row is None:
            continue
        start_pos = int(start_row.name)
        start_nav = float(start_row["nav"])
        end_nav = float(latest["nav"])
        ret = None if start_nav == 0 else float(end_nav / start_nav - 1.0)
        sharpe, mdd = _calc_period_stats(nav, start_pos)
        rows.append((model_code, code, asof_date, ret, None, None, mdd, sharpe))
    return rows


def _build_rebalance_events(model_code: str, latest_date: str | None, hist: pd.DataFrame) -> list[tuple]:
    if latest_date is None or hist.empty:
        return []
    dates = sorted(hist["date"].astype(str).unique().tolist())
    if len(dates) < 2:
        return []
    prev_date = dates[-2]
    curr = hist[hist["date"].astype(str) == latest_date]
    prev = hist[hist["date"].astype(str) == prev_date]
    curr_set = set(curr["ticker"].astype(str))
    prev_set = set(prev["ticker"].astype(str))
    entries = sorted(curr_set - prev_set)
    exits = sorted(prev_set - curr_set)
    rows = []
    for t in entries:
        rows.append((model_code, latest_date, t, "IN", f"Included at rebalance {latest_date}"))
    for t in exits:
        rows.append((model_code, latest_date, t, "OUT", f"Removed at rebalance {latest_date}"))
    return rows


def _quality_payload(run_id: str, nav: pd.DataFrame, current_holdings: pd.DataFrame) -> list[tuple[str, str, dict]]:
    checks: list[tuple[str, str, dict]] = []
    checks.append(("nav_nonempty", "PASS" if not nav.empty else "FAIL", {"rows": int(len(nav))}))
    checks.append(("current_holdings_nonempty", "PASS" if not current_holdings.empty else "FAIL", {"rows": int(len(current_holdings))}))
    latest_nav = None if nav.empty else float(pd.to_numeric(nav["nav"], errors="coerce").iloc[-1])
    checks.append(("latest_nav_positive", "PASS" if latest_nav is not None and latest_nav > 0 else "FAIL", {"latest_nav": latest_nav}))
    return checks


def _rationale_title(model_code: str) -> str:
    if model_code == "S2":
        return "Regime and market filter aligned"
    if model_code == "S3_CORE2":
        return "Core trend score with breadth gate"
    if model_code == "S4":
        return "Risk-on ETF allocation"
    if model_code == "S5":
        return "Neutral ETF allocation"
    if model_code == "S6":
        return "Defensive ETF allocation"
    return "Trend and score aligned"


def _rationale_detail(model_code: str, row: pd.Series) -> str:
    score = row.get("score")
    score_txt = "" if pd.isna(score) else f" score={float(score):.4f};"
    if model_code == "S2":
        return f"Selected by S2 regime screen and market gate.{score_txt}".strip()
    if model_code == "S3_CORE2":
        return f"Selected by core score and breadth gate conditions.{score_txt}".strip()
    if model_code in {"S4", "S5", "S6"}:
        reason = row.get('reason_summary')
        return f"Selected by {model_code} ETF allocation rule. {reason or ''}".strip()
    return f"Selected by S3 score and trend conditions.{score_txt}".strip()


def publish(asof_date: str, core_db_path: Path = CORE_DB, detail_db_path: Path = DETAIL_DB, models: list[str] | None = None) -> None:
    core_con = sqlite3.connect(str(core_db_path))
    detail_con = sqlite3.connect(str(detail_db_path))
    try:
        runs = _load_runs_to_publish(core_con, asof_date, models)
        if not runs:
            raise RuntimeError(f"No completed runs found for asof={asof_date}")

        for spec in runs:
            meta = _load_meta(core_con, spec.model_code)
            nav = _load_nav(detail_con, spec.run_id)
            current_holdings, latest_holdings_date, hist = _load_current_holdings(detail_con, spec.run_id)
            latest_nav_row = nav.iloc[-1] if not nav.empty else None

            prev_row = core_con.execute(
                "SELECT published_run_id FROM pub_model_current WHERE model_code=?",
                (spec.model_code,),
            ).fetchone()
            previous_run_id = None if not prev_row else prev_row[0]

            core_con.execute("DELETE FROM pub_model_current_holdings WHERE model_code=?", (spec.model_code,))
            core_con.execute("DELETE FROM pub_model_nav_history WHERE model_code=?", (spec.model_code,))
            core_con.execute("DELETE FROM pub_model_performance WHERE model_code=?", (spec.model_code,))
            core_con.execute("DELETE FROM pub_model_rebalance_events WHERE model_code=?", (spec.model_code,))
            core_con.execute("DELETE FROM ops_quality_checks WHERE run_id=?", (spec.run_id,))

            core_con.execute(
                """
                INSERT INTO pub_model_current (
                  model_code, published_run_id, published_at, display_name, short_description,
                  long_description, benchmark_code, data_asof, signal_asof, latest_nav,
                  latest_drawdown, latest_holdings_count, latest_rebalance_date, risk_grade, disclaimer_text
                ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_code) DO UPDATE SET
                  published_run_id=excluded.published_run_id,
                  published_at=excluded.published_at,
                  display_name=excluded.display_name,
                  short_description=excluded.short_description,
                  long_description=excluded.long_description,
                  benchmark_code=excluded.benchmark_code,
                  data_asof=excluded.data_asof,
                  signal_asof=excluded.signal_asof,
                  latest_nav=excluded.latest_nav,
                  latest_drawdown=excluded.latest_drawdown,
                  latest_holdings_count=excluded.latest_holdings_count,
                  latest_rebalance_date=excluded.latest_rebalance_date,
                  risk_grade=excluded.risk_grade,
                  disclaimer_text=excluded.disclaimer_text
                """,
                (
                    spec.model_code,
                    spec.run_id,
                    meta["display_name"],
                    meta["description"],
                    meta["description"],
                    meta["benchmark_code"],
                    spec.asof_date,
                    latest_holdings_date,
                    None if latest_nav_row is None else float(latest_nav_row["nav"]),
                    None if latest_nav_row is None else float(latest_nav_row["drawdown"]),
                    int(len(current_holdings)),
                    latest_holdings_date,
                    meta["risk_grade"],
                    DISCLAIMER_TEXT,
                ),
            )

            if not nav.empty:
                nav_rows = [
                    (spec.model_code, str(row.date), float(row.nav), None if pd.isna(row.benchmark_nav) else float(row.benchmark_nav), None if pd.isna(row.drawdown) else float(row.drawdown))
                    for row in nav.itertuples(index=False)
                ]
                core_con.executemany(
                    "INSERT INTO pub_model_nav_history (model_code, date, nav, benchmark_nav, drawdown) VALUES (?, ?, ?, ?, ?)",
                    nav_rows,
                )

            perf_rows = _build_performance_rows(spec.model_code, spec.asof_date, nav)
            if perf_rows:
                core_con.executemany(
                    "INSERT INTO pub_model_performance (model_code, period_code, asof_date, return_pct, benchmark_return_pct, excess_return_pct, mdd, sharpe) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    perf_rows,
                )

            if not current_holdings.empty:
                hold_rows = []
                for row in current_holdings.itertuples(index=False):
                    s = pd.Series(row._asdict())
                    hold_rows.append((
                        spec.model_code,
                        spec.asof_date,
                        str(s["ticker"]),
                        None if pd.isna(s.get("rank_no")) else int(float(s.get("rank_no"))),
                        None if pd.isna(s.get("weight")) else float(s.get("weight")),
                        None if pd.isna(s.get("score")) else float(s.get("score")),
                        _rationale_title(spec.model_code),
                        _rationale_detail(spec.model_code, s),
                    ))
                core_con.executemany(
                    "INSERT INTO pub_model_current_holdings (model_code, asof_date, ticker, rank_no, weight, score, rationale_title, rationale_detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    hold_rows,
                )

            events = _build_rebalance_events(spec.model_code, latest_holdings_date, hist)
            if events:
                core_con.executemany(
                    "INSERT INTO pub_model_rebalance_events (model_code, event_date, ticker, event_type, detail_text) VALUES (?, ?, ?, ?, ?)",
                    events,
                )

            checks = _quality_payload(spec.run_id, nav, current_holdings)
            for check_type, status, detail in checks:
                core_con.execute(
                    "INSERT INTO ops_quality_checks (check_id, batch_id, run_id, check_type, status, detail_json, created_at) VALUES (?, NULL, ?, ?, ?, ?, datetime('now'))",
                    (f"{spec.run_id}__{check_type}", spec.run_id, check_type, status, json.dumps(detail, ensure_ascii=True)),
                )

            publish_id = f"PUBLISH__{spec.model_code}__{spec.asof_date.replace('-', '')}"
            core_con.execute(
                "INSERT OR REPLACE INTO ops_publish_history (publish_id, model_code, previous_run_id, new_run_id, published_at, published_by, note_text) VALUES (?, ?, ?, ?, datetime('now'), 'codex', ?)",
                (publish_id, spec.model_code, previous_run_id, spec.run_id, 'Initial publish pipeline from run_* to pub_*'),
            )

        core_con.commit()
    finally:
        core_con.close()
        detail_con.close()

    print(f"[OK] published asof={asof_date} models={len(runs)}")
    for spec in runs:
        print(f"  - {spec.model_code}: {spec.run_id}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=date.today().strftime("%Y-%m-%d"), help="YYYY-MM-DD. Default: today")
    ap.add_argument("--models", default="", help="comma-separated model codes")
    ap.add_argument("--core-db", default=str(CORE_DB))
    ap.add_argument("--detail-db", default=str(DETAIL_DB))
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    models = [x.strip() for x in str(args.models).split(",") if x.strip()] or None
    publish(asof_date=args.asof, core_db_path=Path(args.core_db), detail_db_path=Path(args.detail_db), models=models)
