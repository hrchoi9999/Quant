from __future__ import annotations

import argparse
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
REPORTS_S2 = PROJECT_ROOT / r"reports\backtest_regime_refactor"
REPORTS_S3 = PROJECT_ROOT / r"reports\backtest_s3_dev"
REPORTS_ETF = PROJECT_ROOT / r"reports\backtest_etf_allocation"
CORE_DB = PROJECT_ROOT / r"data\db\quant_service.db"
DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"

MODEL_VERSION_MAP = {
    "S2": "S2__2026_03_12_001",
    "S3": "S3__2026_03_12_001",
    "S3_CORE2": "S3_CORE2__2026_03_12_001",
    "S4": "S4__2026_03_20_001",
    "S5": "S5__2026_03_20_001",
    "S6": "S6__2026_03_20_001",
}

MODEL_META = {
    "S2": {"display_name": "Quant S2", "description": "Fundamental stock strategy", "asset_class": "stock", "rebalance_frequency": "W", "benchmark_code": "KOSPI", "risk_grade": "medium"},
    "S3": {"display_name": "Quant S3", "description": "Trend stock strategy", "asset_class": "stock", "rebalance_frequency": "W", "benchmark_code": "KOSDAQ", "risk_grade": "high"},
    "S3_CORE2": {"display_name": "Quant S3 core2", "description": "Trend stock strategy with breadth gate", "asset_class": "stock", "rebalance_frequency": "W", "benchmark_code": "KOSDAQ", "risk_grade": "high"},
    "S4": {"display_name": "Quant S4", "description": "Risk-on ETF allocation", "asset_class": "etf", "rebalance_frequency": "M", "benchmark_code": "KOSPI", "risk_grade": "high"},
    "S5": {"display_name": "Quant S5", "description": "Neutral ETF allocation", "asset_class": "etf", "rebalance_frequency": "M", "benchmark_code": "KOSPI", "risk_grade": "medium"},
    "S6": {"display_name": "Quant S6", "description": "Defensive ETF allocation", "asset_class": "etf", "rebalance_frequency": "M", "benchmark_code": "KOSPI", "risk_grade": "low"},
}


def _as_yyyymmdd(s: str) -> str:
    return str(s).replace("-", "")


def _to_date_str(s: str) -> str:
    s = str(s)
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _safe_float(v):
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    try:
        out = float(v)
    except Exception:
        return None
    if math.isnan(out):
        return None
    return out


def _safe_int(v):
    fv = _safe_float(v)
    return None if fv is None else int(fv)


def _calc_summary_from_nav(nav_df: pd.DataFrame, nav_col: str = "nav") -> dict[str, float | int | None]:
    d = nav_df.copy()
    d[nav_col] = pd.to_numeric(d[nav_col], errors="coerce")
    d = d.dropna(subset=[nav_col]).copy()
    if d.empty:
        return {}
    d["ret"] = d[nav_col].pct_change().fillna(0.0)
    total_return = float(d[nav_col].iloc[-1] / d[nav_col].iloc[0] - 1.0)
    n = max(len(d) - 1, 1)
    years = n / 252.0
    cagr = float((d[nav_col].iloc[-1] / d[nav_col].iloc[0]) ** (1.0 / years) - 1.0) if years > 0 else None
    vol_daily = float(d["ret"].std(ddof=0)) if len(d) > 1 else 0.0
    avg_daily_ret = float(d["ret"].mean())
    sharpe = None if not vol_daily or vol_daily <= 0 else float((avg_daily_ret / vol_daily) * math.sqrt(252.0))
    d["peak"] = d[nav_col].cummax()
    d["dd"] = d[nav_col] / d["peak"] - 1.0
    return {
        "cagr": cagr,
        "sharpe": sharpe,
        "mdd": float(d["dd"].min()),
        "total_return": total_return,
        "avg_daily_ret": avg_daily_ret,
        "vol_daily": vol_daily,
        "final_nav": float(d[nav_col].iloc[-1]),
    }


@dataclass
class RunSpec:
    model_code: str
    run_id: str
    batch_id: str
    snapshot_id: str
    start_date: str
    end_date: str
    asof_date: str
    outdir: Path
    summary_path: Path | None
    nav_path: Path
    holdings_path: Path | None
    trade_path: Path | None
    artifacts: list[Path]
    variant_tag: str | None = None


def _latest_s2_spec(asof_date: str, batch_id: str, snapshot_id: str) -> RunSpec:
    end_token = _as_yyyymmdd(asof_date)
    summary = sorted(REPORTS_S2.glob(f"regime_bt_summary_*_{end_token}.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[0]
    stem_suffix = summary.stem.replace("regime_bt_summary_", "")
    run_id = f"RUN__S2__{end_token}__{stem_suffix}"

    def _p(prefix: str, extra: str = "") -> Path:
        return REPORTS_S2 / f"{prefix}_{stem_suffix}{extra}.csv"

    return RunSpec(
        model_code="S2",
        run_id=run_id,
        batch_id=batch_id,
        snapshot_id=snapshot_id,
        start_date=_to_date_str(stem_suffix.split("_")[-2]),
        end_date=asof_date,
        asof_date=asof_date,
        outdir=REPORTS_S2,
        summary_path=summary,
        nav_path=_p("regime_bt_equity"),
        holdings_path=_p("regime_bt_holdings"),
        trade_path=_p("regime_bt_ledger"),
        artifacts=[
            summary,
            _p("regime_bt_equity"),
            _p("regime_bt_holdings"),
            _p("regime_bt_ledger"),
            _p("regime_bt_snapshot"),
            _p("regime_bt_snapshot", "__trades"),
            _p("regime_bt_trades_C"),
            _p("regime_bt_perf_windows"),
        ],
    )


def _latest_s3_specs(asof_date: str, batch_id: str, snapshot_id: str) -> list[RunSpec]:
    specs: list[RunSpec] = []
    end_token = asof_date
    base_nav = REPORTS_S3 / f"s3_nav_hold_top20_2013-10-14_{end_token}.csv"
    if base_nav.exists():
        specs.append(RunSpec(
            model_code="S3",
            run_id=f"RUN__S3__{_as_yyyymmdd(asof_date)}__2013_10_14__{_as_yyyymmdd(asof_date)}__001",
            batch_id=batch_id,
            snapshot_id=snapshot_id,
            start_date="2013-10-14",
            end_date=asof_date,
            asof_date=asof_date,
            outdir=REPORTS_S3,
            summary_path=None,
            nav_path=base_nav,
            holdings_path=REPORTS_S3 / f"s3_holdings_history_top20_2013-10-14_{end_token}.csv",
            trade_path=None,
            artifacts=[
                base_nav,
                REPORTS_S3 / f"s3_holdings_history_top20_2013-10-14_{end_token}.csv",
                REPORTS_S3 / f"s3_holdings_last_top20_{end_token}.csv",
            ],
        ))
    for nav in sorted(REPORTS_S3.glob(f"s3_nav_hold_top20_*_2013-10-14_{end_token}.csv")):
        m = re.match(r"s3_nav_hold_top20_(.+)_2013-10-14_" + re.escape(end_token) + r"\.csv$", nav.name)
        if not m:
            continue
        tag = m.group(1)
        if tag == "2013-10-14":
            continue
        specs.append(RunSpec(
            model_code="S3_CORE2",
            run_id=f"RUN__S3_CORE2__{_as_yyyymmdd(asof_date)}__{tag}",
            batch_id=batch_id,
            snapshot_id=snapshot_id,
            start_date="2013-10-14",
            end_date=asof_date,
            asof_date=asof_date,
            outdir=REPORTS_S3,
            summary_path=None,
            nav_path=nav,
            holdings_path=REPORTS_S3 / f"s3_holdings_history_top20_{tag}_2013-10-14_{end_token}.csv",
            trade_path=None,
            artifacts=[
                nav,
                REPORTS_S3 / f"s3_holdings_history_top20_{tag}_2013-10-14_{end_token}.csv",
                REPORTS_S3 / f"s3_holdings_last_top20_{tag}_{end_token}.csv",
            ],
            variant_tag=tag,
        ))
    return specs


def _latest_etf_specs(asof_date: str, batch_id: str, snapshot_id: str) -> list[RunSpec]:
    specs: list[RunSpec] = []
    asof_token = _as_yyyymmdd(asof_date)
    patterns = {
        'S4': ('s4_alloc_summary', 's4_alloc_equity', 's4_alloc_weights', 's4_alloc_trades'),
        'S5': ('s5_alloc_summary', 's5_alloc_equity', 's5_alloc_weights', 's5_alloc_trades'),
        'S6': ('s6_alloc_summary', 's6_alloc_equity', 's6_alloc_weights', 's6_alloc_trades'),
    }
    for model_code, (sum_prefix, eq_prefix, wt_prefix, tr_prefix) in patterns.items():
        matches = sorted(REPORTS_ETF.glob(f"{sum_prefix}_{asof_token}_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            continue
        summary = matches[0]
        suffix = summary.stem.replace(f"{sum_prefix}_", "")
        parts = suffix.split('_')
        start_date = _to_date_str(parts[2]) if len(parts) >= 4 else '2024-01-02'
        end_date = _to_date_str(parts[3]) if len(parts) >= 4 else asof_date
        specs.append(RunSpec(
            model_code=model_code,
            run_id=f"RUN__{model_code}__{asof_token}__{suffix}",
            batch_id=batch_id,
            snapshot_id=snapshot_id,
            start_date=start_date,
            end_date=end_date,
            asof_date=asof_date,
            outdir=REPORTS_ETF,
            summary_path=summary,
            nav_path=REPORTS_ETF / f"{eq_prefix}_{suffix}.csv",
            holdings_path=REPORTS_ETF / f"{wt_prefix}_{suffix}.csv",
            trade_path=REPORTS_ETF / f"{tr_prefix}_{suffix}.csv",
            artifacts=[
                summary,
                REPORTS_ETF / f"{eq_prefix}_{suffix}.csv",
                REPORTS_ETF / f"{wt_prefix}_{suffix}.csv",
                REPORTS_ETF / f"{tr_prefix}_{suffix}.csv",
            ],
            variant_tag=suffix,
        ))
    return specs


def _ingest_etf_allocation(core_con: sqlite3.Connection, detail_con: sqlite3.Connection, spec: RunSpec) -> None:
    summary_df = pd.read_csv(spec.summary_path)
    nav_df = pd.read_csv(spec.nav_path)
    holdings_df = pd.read_csv(spec.holdings_path, dtype={'ticker': str})
    trades_df = pd.read_csv(spec.trade_path, dtype={'ticker': str})

    summary_row = summary_df.iloc[0].to_dict()
    _insert_run_header(core_con, spec)
    _insert_params(core_con, spec.run_id, summary_row)
    core_con.execute(
        "INSERT INTO run_summary (run_id, cagr, sharpe, mdd, avg_daily_ret, vol_daily, turnover, rebalance_count, final_nav) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            spec.run_id,
            _safe_float(summary_row.get('cagr')),
            _safe_float(summary_row.get('sharpe')),
            _safe_float(summary_row.get('mdd')),
            _safe_float(summary_row.get('avg_daily_ret')),
            _safe_float(summary_row.get('vol_daily')),
            _safe_float(summary_row.get('turnover')),
            _safe_int(summary_row.get('rebalance_count')),
            _safe_float(nav_df['equity'].iloc[-1]) if 'equity' in nav_df.columns else None,
        ),
    )

    n = nav_df.copy()
    n['equity'] = pd.to_numeric(n['equity'], errors='coerce')
    n['peak'] = n['equity'].cummax()
    n['drawdown'] = n['equity'] / n['peak'] - 1.0
    detail_con.executemany(
        "INSERT INTO run_nav_daily (run_id, date, nav, drawdown, holdings_count, cash_weight, exposure, gate_open, gate_breadth, benchmark_nav) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(
            spec.run_id,
            str(row.date),
            _safe_float(row.equity),
            _safe_float(row.drawdown),
            _safe_int(getattr(row, 'n_holdings', None)),
            _safe_float(getattr(row, 'cash_weight', None)),
            _safe_float(getattr(row, 'gross_exposure', None)),
            None,
            None,
            None,
        ) for row in n.itertuples(index=False)],
    )

    h = holdings_df.copy()
    date_col = 'trade_date' if 'trade_date' in h.columns else ('rebalance_date' if 'rebalance_date' in h.columns else None)
    if date_col is None:
        raise RuntimeError(f'ETF holdings file missing date column: {spec.holdings_path}')
    if 'selected' in h.columns:
        h = h[h['selected'].astype(str).str.lower() == 'true'].copy()
    if 'weight' in h.columns:
        h['weight'] = pd.to_numeric(h['weight'], errors='coerce').fillna(0.0)
        h = h[h['weight'] > 0].copy()
    if 'ticker' in h.columns:
        h = h[h['ticker'].fillna('').astype(str).str.strip() != ''].copy()
        h['ticker'] = h['ticker'].astype(str).str.zfill(6)
    if not h.empty:
        h['rank_no'] = h.groupby(date_col)['weight'].rank(method='first', ascending=False)
        hold_rows = [(
            spec.run_id,
            str(getattr(row, date_col)),
            str(row.ticker),
            _safe_int(getattr(row, 'rank_no', None)),
            _safe_float(getattr(row, 'weight', None)),
            None,
            None,
            None,
            _safe_float(getattr(row, 'price', None)),
            None,
            f"mode={getattr(row, 'mode', '')}; group_key={getattr(row, 'group_key', '')}",
        ) for row in h.itertuples(index=False)]
        detail_con.executemany(
            "INSERT INTO run_holdings_history (run_id, date, ticker, rank_no, weight, score, entry_date, entry_price, current_price, cum_return_since_entry, reason_summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            hold_rows,
        )

    t = trades_df.copy()
    if not t.empty:
        t = t[t['ticker'].fillna('').astype(str).str.strip() != ''].copy()
        t['ticker'] = t['ticker'].astype(str).str.zfill(6)
        trade_rows = [(
            spec.run_id,
            f"{spec.run_id}__{idx}",
            str(getattr(row, 'trade_date', getattr(row, 'rebalance_date', ''))),
            str(row.ticker),
            str(getattr(row, 'side', 'TRADE')),
            None,
            _safe_float(getattr(row, 'prev_weight', None)),
            _safe_float(getattr(row, 'new_weight', None)),
            _safe_float(getattr(row, 'exec_price', None)),
            _safe_float(getattr(row, 'turnover_component', None)),
            f"mode={getattr(row, 'mode', '')}; group_key={getattr(row, 'group_key', '')}",
        ) for idx, row in enumerate(t.itertuples(index=False), start=1)]
        detail_con.executemany(
            "INSERT INTO run_trades (run_id, trade_id, trade_date, ticker, side, quantity, weight_before, weight_after, trade_price, turnover_contrib, trade_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            trade_rows,
        )

def _get_max_date(db_path: Path, table: str) -> str | None:
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute(f"SELECT MAX(date) FROM {table}").fetchone()
        return None if not row or row[0] is None else str(row[0])
    finally:
        con.close()


def _ensure_model_seeds(con: sqlite3.Connection) -> None:
    for model_code, meta in MODEL_META.items():
        con.execute(
            """
            INSERT INTO meta_models (model_code, display_name, description, asset_class, rebalance_frequency, benchmark_code, risk_grade, status, service_enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1, datetime('now'))
            ON CONFLICT(model_code) DO UPDATE SET
              display_name=excluded.display_name,
              description=excluded.description,
              asset_class=excluded.asset_class,
              rebalance_frequency=excluded.rebalance_frequency,
              benchmark_code=excluded.benchmark_code,
              risk_grade=excluded.risk_grade,
              service_enabled=1,
              updated_at=datetime('now')
            """,
            (model_code, meta['display_name'], meta['description'], meta['asset_class'], meta['rebalance_frequency'], meta['benchmark_code'], meta['risk_grade']),
        )
        con.execute(
            """
            INSERT INTO meta_model_versions (model_version_id, model_code, version_label, code_ref, logic_summary, is_current_internal, created_at)
            VALUES (?, ?, ?, ?, ?, 1, datetime('now'))
            ON CONFLICT(model_version_id) DO UPDATE SET
              model_code=excluded.model_code,
              version_label=excluded.version_label,
              code_ref=excluded.code_ref,
              logic_summary=excluded.logic_summary,
              is_current_internal=1
            """,
            (MODEL_VERSION_MAP[model_code], model_code, MODEL_VERSION_MAP[model_code], model_code, meta['description']),
        )

def _upsert_batch_and_snapshot(con: sqlite3.Connection, batch_id: str, snapshot_id: str, asof_date: str) -> None:
    con.execute(
        """
        INSERT INTO run_batches (batch_id, batch_type, asof_date, status, started_at, finished_at, triggered_by, notes)
        VALUES (?, 'daily_backtest_ingest', ?, 'completed', datetime('now'), datetime('now'), 'codex', 'Initial result ingestion pipeline (core/detail split)')
        ON CONFLICT(batch_id) DO UPDATE SET
          status=excluded.status,
          finished_at=excluded.finished_at,
          notes=excluded.notes
        """,
        (batch_id, asof_date),
    )
    con.execute(
        """
        INSERT INTO run_data_snapshots (
          snapshot_id, batch_id, price_asof, regime_asof, fundamentals_asof,
          s3_price_features_asof, s3_fund_features_asof, universe_asof, universe_name
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_id) DO UPDATE SET
          price_asof=excluded.price_asof,
          regime_asof=excluded.regime_asof,
          fundamentals_asof=excluded.fundamentals_asof,
          s3_price_features_asof=excluded.s3_price_features_asof,
          s3_fund_features_asof=excluded.s3_fund_features_asof,
          universe_asof=excluded.universe_asof,
          universe_name=excluded.universe_name
        """,
        (
            snapshot_id,
            batch_id,
            _get_max_date(PROJECT_ROOT / r"data\db\price.db", "prices_daily"),
            _get_max_date(PROJECT_ROOT / r"data\db\regime.db", "regime_history"),
            _get_max_date(PROJECT_ROOT / r"data\db\fundamentals.db", "fundamentals_monthly_mix400_latest"),
            _get_max_date(PROJECT_ROOT / r"data\db_s3\features_s3.db", "s3_price_features_daily"),
            _get_max_date(PROJECT_ROOT / r"data\db_s3\features_s3.db", "s3_fund_features_monthly"),
            asof_date,
            "universe_mix_top400_latest",
        ),
    )


def _delete_existing_run_core(con: sqlite3.Connection, run_id: str) -> None:
    row = con.execute("SELECT model_code FROM run_runs WHERE run_id = ?", (run_id,)).fetchone()
    model_code = None if not row else row[0]

    con.execute("DELETE FROM ops_quality_checks WHERE run_id = ?", (run_id,))
    con.execute("DELETE FROM ops_publish_history WHERE new_run_id = ?", (run_id,))
    con.execute("DELETE FROM pub_model_current WHERE published_run_id = ?", (run_id,))

    if model_code:
        con.execute("DELETE FROM pub_model_performance WHERE model_code = ?", (model_code,))
        con.execute("DELETE FROM pub_model_nav_history WHERE model_code = ?", (model_code,))
        con.execute("DELETE FROM pub_model_current_holdings WHERE model_code = ?", (model_code,))
        con.execute("DELETE FROM pub_model_rebalance_events WHERE model_code = ?", (model_code,))

    for table in ["run_artifacts", "run_summary", "run_params", "run_runs"]:
        con.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))


def _delete_existing_run_detail(con: sqlite3.Connection, run_id: str) -> None:
    for table in ["run_signal_details_s3_core2", "run_signal_details_s3", "run_signal_details_s2", "run_trades", "run_holdings_history", "run_nav_daily"]:
        con.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))


def _insert_run_header(core_con: sqlite3.Connection, spec: RunSpec) -> None:
    core_con.execute(
        """
        INSERT INTO run_runs (
          run_id, batch_id, snapshot_id, model_code, model_version_id, run_kind,
          start_date, end_date, asof_date, status, exit_code, started_at, finished_at, runtime_seconds, outdir
        )
        VALUES (?, ?, ?, ?, ?, 'backtest', ?, ?, ?, 'completed', 0, datetime('now'), datetime('now'), NULL, ?)
        """,
        (spec.run_id, spec.batch_id, spec.snapshot_id, spec.model_code, MODEL_VERSION_MAP[spec.model_code], spec.start_date, spec.end_date, spec.asof_date, str(spec.outdir)),
    )


def _insert_params(core_con: sqlite3.Connection, run_id: str, params: dict[str, str | int | float | None]) -> None:
    rows = [(run_id, str(k), None if v is None else str(v)) for k, v in params.items()]
    core_con.executemany("INSERT INTO run_params (run_id, param_key, param_value) VALUES (?, ?, ?)", rows)


def _insert_artifacts(core_con: sqlite3.Connection, spec: RunSpec) -> None:
    rows = []
    for path in spec.artifacts:
        if path.exists():
            rows.append((spec.run_id, path.stem, str(path), path.suffix.lstrip(".")))
    if rows:
        core_con.executemany("INSERT INTO run_artifacts (run_id, artifact_type, artifact_path, file_format) VALUES (?, ?, ?, ?)", rows)


def _ingest_s2(core_con: sqlite3.Connection, detail_con: sqlite3.Connection, spec: RunSpec) -> None:
    summary_df = pd.read_csv(spec.summary_path)
    summary_row = summary_df.iloc[0].to_dict()
    nav_df = pd.read_csv(spec.nav_path)
    holdings_df = pd.read_csv(spec.holdings_path, dtype={"ticker": str})
    ledger_df = pd.read_csv(spec.trade_path, dtype={"ticker": str})

    _insert_run_header(core_con, spec)
    _insert_params(core_con, spec.run_id, summary_row)
    core_con.execute(
        "INSERT INTO run_summary (run_id, cagr, sharpe, mdd, avg_daily_ret, vol_daily, rebalance_count, final_nav) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (spec.run_id, _safe_float(summary_row.get("cagr")), _safe_float(summary_row.get("sharpe")), _safe_float(summary_row.get("mdd")), _safe_float(summary_row.get("avg_daily_ret")), _safe_float(summary_row.get("vol_daily")), _safe_int(summary_row.get("rebalance_count")), _safe_float(nav_df["equity"].iloc[-1])),
    )

    e = nav_df.copy()
    e["equity"] = pd.to_numeric(e["equity"], errors="coerce")
    e["peak"] = e["equity"].cummax()
    e["drawdown"] = e["equity"] / e["peak"] - 1.0
    detail_con.executemany(
        "INSERT INTO run_nav_daily (run_id, date, nav, drawdown, holdings_count, cash_weight, exposure, gate_open, gate_breadth, benchmark_nav) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(
            spec.run_id,
            str(row.date),
            _safe_float(row.equity),
            _safe_float(row.drawdown),
            _safe_int(getattr(row, "n_holdings", None)),
            _safe_float(getattr(row, "cash_weight", None)),
            _safe_float(getattr(row, "gross_exposure", None)),
            _safe_int(getattr(row, "market_ok", None)),
            None,
            _safe_float(getattr(row, "market_price", None)),
        ) for row in e.itertuples(index=False)],
    )

    h = holdings_df.copy()
    h["ticker"] = h["ticker"].astype(str)
    hold_rows = []
    signal_rows = []
    for row in h.itertuples(index=False):
        ticker = str(row.ticker)
        if ticker == "CASH":
            continue
        date = str(getattr(row, "trade_date", getattr(row, "rebalance_date", "")))
        hold_rows.append((spec.run_id, date, ticker, _safe_int(getattr(row, "score_rank", None)), _safe_float(getattr(row, "weight", None)), _safe_float(getattr(row, "growth_score", None)), None, None, _safe_float(getattr(row, "price", None)), None, f"regime={getattr(row, 'regime', '')}; market_ok={getattr(row, 'market_ok', '')}"))
        signal_rows.append((spec.run_id, date, ticker, _safe_float(getattr(row, "regime_score", None)), None if pd.isna(getattr(row, "regime", None)) else str(getattr(row, "regime", None)), _safe_float(getattr(row, "growth_score", None)), None, None, _safe_int(getattr(row, "market_ok", None)), _safe_int(getattr(row, "score_rank", None))))
    if hold_rows:
        detail_con.executemany("INSERT INTO run_holdings_history (run_id, date, ticker, rank_no, weight, score, entry_date, entry_price, current_price, cum_return_since_entry, reason_summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", hold_rows)
        detail_con.executemany("INSERT INTO run_signal_details_s2 (run_id, date, ticker, regime_value, regime_label, growth_score, sma140, above_sma_flag, market_gate_flag, selection_rank) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", signal_rows)

    l = ledger_df.copy()
    l["ticker"] = l["ticker"].astype(str)
    trade_rows = [(
        spec.run_id,
        f"{spec.run_id}__{idx}",
        str(row.trade_date),
        str(row.ticker),
        str(row.action),
        _safe_float(getattr(row, "qty", None)),
        None,
        None,
        _safe_float(getattr(row, "price", None)),
        None,
        f"rebalance_date={getattr(row, 'rebalance_date', '')}",
    ) for idx, row in enumerate(l.itertuples(index=False), start=1)]
    if trade_rows:
        detail_con.executemany("INSERT INTO run_trades (run_id, trade_id, trade_date, ticker, side, quantity, weight_before, weight_after, trade_price, turnover_contrib, trade_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", trade_rows)


def _ingest_s3_like(core_con: sqlite3.Connection, detail_con: sqlite3.Connection, spec: RunSpec) -> None:
    nav_df = pd.read_csv(spec.nav_path)
    holdings_df = pd.read_csv(spec.holdings_path, dtype={"ticker": str})

    _insert_run_header(core_con, spec)
    params = {"top_n": 20, "start": spec.start_date, "end": spec.end_date, "variant_tag": spec.variant_tag}
    if spec.model_code == "S3_CORE2":
        params["gate_enabled"] = 1
    _insert_params(core_con, spec.run_id, params)

    metrics = _calc_summary_from_nav(nav_df, nav_col="nav")
    core_con.execute(
        "INSERT INTO run_summary (run_id, cagr, sharpe, mdd, total_return, avg_daily_ret, vol_daily, rebalance_count, avg_holding_count, final_nav) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (spec.run_id, metrics.get("cagr"), metrics.get("sharpe"), metrics.get("mdd"), metrics.get("total_return"), metrics.get("avg_daily_ret"), metrics.get("vol_daily"), len(nav_df), _safe_float(pd.to_numeric(nav_df.get("holdings"), errors="coerce").mean() if "holdings" in nav_df.columns else None), metrics.get("final_nav")),
    )

    n = nav_df.copy()
    n["nav"] = pd.to_numeric(n["nav"], errors="coerce")
    n["peak"] = n["nav"].cummax()
    n["drawdown"] = n["nav"] / n["peak"] - 1.0
    detail_con.executemany(
        "INSERT INTO run_nav_daily (run_id, date, nav, drawdown, holdings_count, cash_weight, exposure, gate_open, gate_breadth, benchmark_nav) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(
            spec.run_id,
            str(row.date),
            _safe_float(row.nav),
            _safe_float(row.drawdown),
            _safe_int(getattr(row, "holdings", None)),
            _safe_float(getattr(row, "cash_weight", None)),
            _safe_float(getattr(row, "exposure", None)),
            _safe_int(getattr(row, "gate_open", None)),
            _safe_float(getattr(row, "gate_breadth", None)),
            None,
        ) for row in n.itertuples(index=False)],
    )

    h = holdings_df.copy()
    h["ticker"] = h["ticker"].astype(str)
    h["s3_score"] = pd.to_numeric(h.get("s3_score"), errors="coerce")
    h["rank_no"] = h.groupby("date")["s3_score"].rank(method="first", ascending=False)
    gate_map = {str(row.date): (_safe_int(getattr(row, "gate_open", None)), _safe_float(getattr(row, "gate_breadth", None))) for row in n.itertuples(index=False)}
    hold_rows = []
    s3_rows = []
    core2_rows = []
    for row in h.itertuples(index=False):
        date = str(row.date)
        hold_rows.append((spec.run_id, date, str(row.ticker), _safe_int(getattr(row, "rank_no", None)), None, _safe_float(getattr(row, "s3_score", None)), None, None, _safe_float(getattr(row, "close", None)), None, None))
        if spec.model_code == "S3":
            s3_rows.append((spec.run_id, date, str(row.ticker), _safe_float(getattr(row, "s3_score", None)), _safe_float(getattr(row, "mom20", None)), None, _safe_float(getattr(row, "vol_ratio_20", None)), None, _safe_int(getattr(row, "breakout60", None)), _safe_float(getattr(row, "ma60", None)), _safe_float(getattr(row, "ma120", None)), _safe_float(getattr(row, "ma60_slope", None)), _safe_float(getattr(row, "growth_score", None)), _safe_float(getattr(row, "fund_accel_score", None))))
        else:
            gate_open, gate_breadth = gate_map.get(date, (None, None))
            core2_rows.append((spec.run_id, date, str(row.ticker), _safe_float(getattr(row, "core_score", None)), _safe_float(getattr(row, "tie_score", None)), _safe_float(getattr(row, "s3_score", None)), gate_open, gate_breadth, _safe_float(getattr(row, "mom20_pct", None)), _safe_float(getattr(row, "vol_ratio_pct", None)), _safe_float(getattr(row, "fund_level_pct", None)), _safe_float(getattr(row, "fund_accel_pct", None))))
    detail_con.executemany("INSERT INTO run_holdings_history (run_id, date, ticker, rank_no, weight, score, entry_date, entry_price, current_price, cum_return_since_entry, reason_summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", hold_rows)
    if s3_rows:
        detail_con.executemany("INSERT INTO run_signal_details_s3 (run_id, date, ticker, s3_score, mom20, mom20_pct, vol_ratio_20, vol_ratio_pct, breakout60, ma60, ma120, ma60_slope, growth_score, fund_accel_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", s3_rows)
    if core2_rows:
        detail_con.executemany("INSERT INTO run_signal_details_s3_core2 (run_id, date, ticker, core_score, tie_score, s3_score, gate_open, gate_breadth, mom20_pct, vol_ratio_pct, fund_level_pct, fund_accel_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", core2_rows)


def ingest(asof_date: str, core_db_path: Path = CORE_DB, detail_db_path: Path = DETAIL_DB) -> None:
    batch_id = f"BATCH__{_as_yyyymmdd(asof_date)}__DAILY"
    snapshot_id = f"SNAPSHOT__{_as_yyyymmdd(asof_date)}__001"
    specs = [
        _latest_s2_spec(asof_date, batch_id, snapshot_id),
        *_latest_s3_specs(asof_date, batch_id, snapshot_id),
        *_latest_etf_specs(asof_date, batch_id, snapshot_id),
    ]

    core_con = sqlite3.connect(str(core_db_path))
    detail_con = sqlite3.connect(str(detail_db_path))
    try:
        core_con.execute("PRAGMA foreign_keys = ON")
        _ensure_model_seeds(core_con)
        _upsert_batch_and_snapshot(core_con, batch_id, snapshot_id, asof_date)
        for spec in specs:
            _delete_existing_run_core(core_con, spec.run_id)
            _delete_existing_run_detail(detail_con, spec.run_id)
            if spec.model_code == "S2":
                _ingest_s2(core_con, detail_con, spec)
            elif spec.model_code in {"S3", "S3_CORE2"}:
                _ingest_s3_like(core_con, detail_con, spec)
            else:
                _ingest_etf_allocation(core_con, detail_con, spec)
            _insert_artifacts(core_con, spec)
        core_con.commit()
        detail_con.commit()
    finally:
        core_con.close()
        detail_con.close()

    print(f"[OK] ingested batch={batch_id} runs={len(specs)}")
    print(f"  core   -> {core_db_path}")
    print(f"  detail -> {detail_db_path}")
    for spec in specs:
        print(f"  - {spec.model_code}: {spec.run_id}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=date.today().strftime("%Y-%m-%d"), help="YYYY-MM-DD. Default: today")
    ap.add_argument("--core-db", default=str(CORE_DB))
    ap.add_argument("--detail-db", default=str(DETAIL_DB))
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ingest(asof_date=args.asof, core_db_path=Path(args.core_db), detail_db_path=Path(args.detail_db))
