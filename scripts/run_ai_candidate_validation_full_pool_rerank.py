from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import analyze_stock_model_score_correlation as stock_pool  # noqa: E402
import build_ai_overlay_v01 as cv_ai  # noqa: E402
import run_ai_candidate_validation_weekly_rerank as weekly_cv  # noqa: E402


QS_DB = ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = ROOT / r"data\db\quant_service_detail.db"
PRICE_DB = ROOT / r"data\db\price.db"
I_SOURCE_DB = ROOT / r"data\db\i_series_research_strong_rsi_raw_top30_s65.db"
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
MODEL_NAME_KO = "퀀트후보검증AI"
DEFAULT_START = "2024-01-01"
DEFAULT_POOL_N = 200


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _read_sql(db: Path, query: str, params: tuple[Any, ...] = (), parse_dates: list[str] | None = None) -> pd.DataFrame:
    with sqlite3.connect(str(db)) as con:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates or None)


def _zfill_ticker(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else ""


def _latest_runs(asof: str) -> dict[str, str]:
    df = _read_sql(
        QS_DB,
        """
        SELECT model_code, run_id
        FROM (
          SELECT model_code, run_id, created_at,
                 ROW_NUMBER() OVER (PARTITION BY model_code ORDER BY created_at DESC) AS rn
          FROM run_runs
          WHERE model_code IN ('S2','S3','S3_CORE2')
            AND status = 'completed'
            AND asof_date <= ?
        ) WHERE rn = 1
        """,
        (asof,),
    )
    return dict(zip(df["model_code"], df["run_id"]))


def _load_prices() -> pd.DataFrame:
    px = _read_sql(PRICE_DB, "SELECT ticker, date, close FROM prices_daily", parse_dates=["date"])
    px["ticker"] = px["ticker"].map(_zfill_ticker)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    return px.dropna(subset=["date", "close"]).sort_values(["ticker", "date"]).reset_index(drop=True)


def _next_period_returns(px: pd.DataFrame, candidates: pd.DataFrame, asof: str) -> pd.DataFrame:
    out = candidates.copy()
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"], errors="coerce")

    date_map = (
        out[["scope_key", "model_id", "snapshot_date"]]
        .drop_duplicates()
        .sort_values(["scope_key", "model_id", "snapshot_date"])
    )
    date_map["next_snapshot_date"] = date_map.groupby(["scope_key", "model_id"])["snapshot_date"].shift(-1)
    date_map["next_snapshot_date"] = date_map["next_snapshot_date"].fillna(pd.Timestamp(asof))
    out = out.merge(date_map, on=["scope_key", "model_id", "snapshot_date"], how="left")
    out = out.loc[out["next_snapshot_date"] > out["snapshot_date"]].copy()
    if out.empty:
        return out.assign(period_return=np.nan)

    dates = sorted(
        set(out["snapshot_date"].dt.strftime("%Y-%m-%d").tolist())
        | set(pd.to_datetime(out["next_snapshot_date"]).dt.strftime("%Y-%m-%d").tolist())
    )
    tickers = sorted(out["ticker"].dropna().unique().tolist())
    px_need = px.loc[
        px["ticker"].isin(tickers) & px["date"].dt.strftime("%Y-%m-%d").isin(dates),
        ["ticker", "date", "close"],
    ].copy()
    px_need["date"] = px_need["date"].dt.strftime("%Y-%m-%d")
    out["snapshot_date"] = out["snapshot_date"].dt.strftime("%Y-%m-%d")
    out["next_snapshot_date"] = pd.to_datetime(out["next_snapshot_date"]).dt.strftime("%Y-%m-%d")

    start_px = px_need.rename(columns={"date": "snapshot_date", "close": "start_close"})
    end_px = px_need.rename(columns={"date": "next_snapshot_date", "close": "end_close"})
    out = out.merge(start_px, on=["ticker", "snapshot_date"], how="left")
    out = out.merge(end_px, on=["ticker", "next_snapshot_date"], how="left")
    out["period_return"] = out["end_close"] / out["start_close"] - 1.0
    return out


def _finalize_pool(df: pd.DataFrame, model_id: str, score_col: str, pool_n: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["ticker"] = work["ticker"].map(_zfill_ticker)
    work["snapshot_date"] = pd.to_datetime(work["date"], errors="coerce")
    work["score"] = pd.to_numeric(work[score_col], errors="coerce")
    work = work.dropna(subset=["snapshot_date", "ticker", "score"])
    work["rank_no"] = (
        work.sort_values(["snapshot_date", "score", "ticker"], ascending=[True, False, True])
        .groupby("snapshot_date")
        .cumcount()
        + 1
    )
    work = work.loc[work["rank_no"] <= pool_n].copy()
    work["scope_key"] = "internal"
    work["model_id"] = model_id
    work["week_end"] = work["snapshot_date"].dt.strftime("%Y-%m-%d")
    work["event_date"] = work["week_end"]
    work["event_type"] = "full_pool_candidate"
    work["score_basis"] = score_col
    work["candidate_bucket"] = f"top{pool_n}_pool"
    work["asset_group"] = "stock"
    work["weight"] = np.nan
    work["stage1_prob"] = np.nan
    work["stage2_prob"] = np.nan
    work["universe_rank_no"] = work["rank_no"].astype(float)
    group_count = work.groupby("snapshot_date")["ticker"].transform("nunique")
    work["universe_rank_score"] = np.where(
        group_count > 1,
        (1.0 - (work["rank_no"] - 1) / (group_count - 1)) * 100.0,
        100.0,
    )
    work["display_score"] = work["score"]
    work["is_current"] = 0
    keep = [
        "scope_key",
        "model_id",
        "ticker",
        "name",
        "snapshot_date",
        "event_date",
        "week_end",
        "event_type",
        "score_basis",
        "candidate_bucket",
        "asset_group",
        "rank_no",
        "score",
        "weight",
        "stage1_prob",
        "stage2_prob",
        "universe_rank_no",
        "universe_rank_score",
        "display_score",
        "is_current",
    ]
    return work[[col for col in keep if col in work.columns]].sort_values(["snapshot_date", "rank_no", "ticker"])


def _build_s_pools(asof: str, start: str, pool_n: int, px: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    runs = _latest_runs(asof)
    skipped: list[str] = []
    frames: list[pd.DataFrame] = []
    signal_table_map = {
        "S2": "run_signal_details_s2",
        "S3": "run_signal_details_s3",
        "S3_CORE2": "run_signal_details_s3_core2",
    }
    builders = {
        "S2": stock_pool._s2_candidates,
        "S3": stock_pool._s3_candidates,
        "S3_CORE2": stock_pool._s3_core2_candidates,
    }
    for model_id, table in signal_table_map.items():
        run_id = runs.get(model_id)
        if not run_id:
            skipped.append(f"{model_id}: latest run not found")
            continue
        selected = _read_sql(
            QS_DETAIL_DB,
            f"SELECT date, ticker FROM {table} WHERE run_id=? AND date>=? AND date<=?",
            (run_id, start, asof),
            parse_dates=["date"],
        )
        if selected.empty:
            skipped.append(f"{model_id}: no selected signal dates")
            continue
        selected["ticker"] = selected["ticker"].map(_zfill_ticker)
        signal_dates = sorted(selected["date"].dropna().unique())
        px_fwd = stock_pool._forward_return(px.copy(), signal_dates)
        cand, score_col = builders[model_id](signal_dates, px_fwd, selected)
        frames.append(_finalize_pool(cand, model_id, score_col, pool_n))
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), skipped


def _build_i_pool(asof: str, start: str, pool_n: int) -> tuple[pd.DataFrame, list[str]]:
    if not I_SOURCE_DB.exists():
        return pd.DataFrame(), ["I-STOCK-STRONG-RSI-V01: source DB not found"]
    df = _read_sql(
        I_SOURCE_DB,
        """
        SELECT date, ticker, name, market, universe_rank_no, universe_rank_score,
               i_raw_score, i_score AS display_score, i_signal
        FROM i_stock_v01_signals_weekly
        WHERE date >= ? AND date <= ?
        """,
        (start, asof),
        parse_dates=["date"],
    )
    if df.empty:
        return pd.DataFrame(), ["I-STOCK-STRONG-RSI-V01: no full universe weekly signals"]
    work = df.copy()
    work["ticker"] = work["ticker"].map(_zfill_ticker)
    work["rank_no"] = pd.to_numeric(work["universe_rank_no"], errors="coerce")
    work["score"] = pd.to_numeric(work["i_raw_score"], errors="coerce")
    work = work.dropna(subset=["date", "ticker", "rank_no"])
    work = work.loc[work["rank_no"] <= pool_n].copy()
    work["scope_key"] = "internal"
    work["model_id"] = "I-STOCK-STRONG-RSI-V01"
    work["snapshot_date"] = work["date"]
    work["week_end"] = work["date"].dt.strftime("%Y-%m-%d")
    work["event_date"] = work["week_end"]
    work["event_type"] = "full_pool_candidate"
    work["score_basis"] = "i_raw_score"
    work["candidate_bucket"] = f"top{pool_n}_pool"
    work["asset_group"] = "stock"
    work["weight"] = np.nan
    work["stage1_prob"] = np.nan
    work["stage2_prob"] = np.nan
    work["is_current"] = 0
    keep = [
        "scope_key",
        "model_id",
        "ticker",
        "name",
        "snapshot_date",
        "event_date",
        "week_end",
        "event_type",
        "score_basis",
        "candidate_bucket",
        "asset_group",
        "rank_no",
        "score",
        "weight",
        "stage1_prob",
        "stage2_prob",
        "universe_rank_no",
        "universe_rank_score",
        "display_score",
        "is_current",
    ]
    return work[keep].sort_values(["snapshot_date", "rank_no", "ticker"]), []


def _build_full_pool(asof: str, start: str, pool_n: int) -> tuple[pd.DataFrame, list[str]]:
    px = _load_prices()
    s_pools, skipped = _build_s_pools(asof, start, pool_n, px)
    i_pool, i_skipped = _build_i_pool(asof, start, pool_n)
    skipped.extend(i_skipped)
    frames = [x for x in [s_pools, i_pool] if not x.empty]
    pool = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if pool.empty:
        return pool, skipped
    pool = _next_period_returns(px, pool, asof)
    return pool.sort_values(["scope_key", "model_id", "snapshot_date", "rank_no", "ticker"]).reset_index(drop=True), skipped


def _score_full_pool(pool: pd.DataFrame, asof: str, feature_set: str) -> pd.DataFrame:
    if pool.empty:
        return pool

    with sqlite3.connect(str(cv_ai.OUT_DB)) as con:
        mart = pd.read_sql_query("SELECT * FROM ai_overlay_training_mart", con)
    if mart.empty:
        raise SystemExit("ai_overlay_training_mart is empty. Run build_ai_overlay_v01.py first.")

    quality_model, _quality_eval, _ = cv_ai._fit_model(mart, "label_quality_1m", "gb", feature_set)
    risk_model, _risk_eval, _ = cv_ai._fit_model(mart, "label_risk_1m", "gb", feature_set)
    extra_models: dict[str, Any] = {}
    for key, label in {
        "short_confirm": "label_positive_1m",
        "medium_quality": "label_quality_2m",
        "long_quality": "label_quality_3m",
        "upside_strict": "label_quality_1m_strict",
        "risk_strict": "label_bad_1m_strict",
    }.items():
        model, _eval, _ = cv_ai._fit_model(mart, label, "gb", feature_set)
        extra_models[key] = model

    feature_frame = pool.copy()
    feature_frame["is_current"] = 1
    for col in ["model_overlap_count", "overlap_user_count", "overlap_internal_count", "overlap_tseries_count"]:
        if col not in feature_frame.columns:
            feature_frame[col] = 1 if col == "model_overlap_count" else 0
    feature_frame = cv_ai._attach_price_features(feature_frame, asof)
    feature_frame = cv_ai._attach_static_features(feature_frame, asof)
    feature_frame = cv_ai._attach_external_features(feature_frame, asof)

    shadow = cv_ai._score_shadow(feature_frame, quality_model, risk_model, asof, extra_models)
    ms_models, _ms_evals = cv_ai._fit_model_specific_models(mart, feature_set)
    shadow = cv_ai._apply_model_specific_scores(shadow, feature_frame, ms_models)

    score_cols = [
        "scope_key",
        "model_id",
        "ticker",
        "event_date",
        "week_end",
        "ai_quality_prob",
        "ai_risk_prob",
        "ai_shadow_decision",
        "ai_shadow_tags",
        "ai_model_specific_quality_prob",
        "ai_model_specific_risk_prob",
        "ai_model_specific_tag",
    ]
    scored = pool.merge(shadow[[c for c in score_cols if c in shadow.columns]], on=["scope_key", "model_id", "ticker", "event_date", "week_end"], how="left")
    return scored


def _write_report(
    asof: str,
    start: str,
    pool_n: int,
    summary: pd.DataFrame,
    coverage: pd.DataFrame,
    skipped: list[str],
    out_dir: Path,
) -> Path:
    path = out_dir / f"AI_CANDIDATE_VALIDATION_FULL_POOL_RERANK_{_token(asof)}.md"
    lines = [
        "# AI Candidate Validation Full-Pool Rerank Simulation",
        "",
        f"- asof: {asof}",
        f"- start: {start}",
        f"- candidate pool: strategy universe top{pool_n}",
        f"- overlay: {MODEL_CODE} / {MODEL_NAME_KO}",
        "- scope: stock-only; ETF excluded",
        "- note: This is a research simulation. It does not replace production strategy holdings.",
        "",
        "## Pool Coverage",
        "",
        "| scope | model | rows | periods | avg pool size | cv coverage |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    if not coverage.empty:
        for _, row in coverage.iterrows():
            lines.append(
                f"| {row['scope_key']} | {row['model_id']} | {int(row['rows'])} | {int(row['periods'])} | "
                f"{row['avg_pool_size']:.1f} | {row['cv_coverage']:.2%} |"
            )

    lines.extend(
        [
            "",
            "## Policy Summary",
            "",
            "| scope | model | policy | periods | avg period return | win rate | worst | changed avg |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if not summary.empty:
        for _, row in summary.iterrows():
            lines.append(
                f"| {row['scope_key']} | {row['model_id']} | {row['policy']} | {int(row['priced_periods'])} | "
                f"{row['avg_period_return']:.2%} | {row['win_rate']:.2%} | {row['worst_period_return']:.2%} | "
                f"{row['avg_changed_count']:.2f} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `baseline` selects the original strategy top N from the top200 pool.",
            "- `cv_guardrail` pushes model-specific risk-review/fallback names below eligible candidates.",
            "- `cv_rerank` adds the candidate-validation AI signal to the original strategy rank score.",
            "- `cv_tilt` keeps baseline names but adjusts weights by the AI signal.",
            "- A large `changed avg` means the 200-name pool is wide enough for the AI to actually alter selections.",
        ]
    )
    if skipped:
        lines.extend(["", "## Excluded Or Missing Pools", ""])
        lines.extend([f"- {item}" for item in skipped])
        lines.append("- T/C/user strategy models are not included here unless a 200-name point-in-time candidate pool is persisted or rebuilt.")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CandidateValidation AI rerank on full top200 strategy candidate pools.")
    parser.add_argument("--asof", required=True, help="YYYY-MM-DD")
    parser.add_argument("--start", default=DEFAULT_START, help="YYYY-MM-DD")
    parser.add_argument("--pool-n", type=int, default=DEFAULT_POOL_N)
    parser.add_argument("--feature-set", default="kiwoom_dart", choices=["base", "kiwoom", "dart", "kiwoom_dart", "all"])
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    asof = str(args.asof)
    start = str(args.start)
    pool_n = int(args.pool_n)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pool, skipped = _build_full_pool(asof, start, pool_n)
    scored = _score_full_pool(pool, asof, str(args.feature_set))
    holdings, perf = weekly_cv._run_simulation(scored)
    summary = weekly_cv._summarize(perf)

    scored["has_cv_score"] = scored["ai_model_specific_tag"].notna() | scored["ai_shadow_decision"].notna()
    coverage = (
        scored.groupby(["scope_key", "model_id"], dropna=False)
        .agg(
            rows=("ticker", "size"),
            periods=("snapshot_date", "nunique"),
            avg_pool_size=("ticker", lambda s: float(len(s) / scored.loc[s.index, "snapshot_date"].nunique())),
            cv_coverage=("has_cv_score", "mean"),
        )
        .reset_index()
    )

    token = _token(asof)
    scored_path = out_dir / f"ai_candidate_validation_full_pool_scored_top{pool_n}_{token}.csv"
    holdings_path = out_dir / f"ai_candidate_validation_full_pool_holdings_top{pool_n}_{token}.csv"
    periods_path = out_dir / f"ai_candidate_validation_full_pool_periods_top{pool_n}_{token}.csv"
    summary_path = out_dir / f"ai_candidate_validation_full_pool_summary_top{pool_n}_{token}.csv"
    coverage_path = out_dir / f"ai_candidate_validation_full_pool_coverage_top{pool_n}_{token}.csv"
    json_path = out_dir / f"ai_candidate_validation_full_pool_rerank_top{pool_n}_{token}.json"
    report_path = _write_report(asof, start, pool_n, summary, coverage, skipped, out_dir)

    scored.to_csv(scored_path, index=False, encoding="utf-8-sig")
    holdings.to_csv(holdings_path, index=False, encoding="utf-8-sig")
    perf.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asof": asof,
        "start": start,
        "pool_n": pool_n,
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "candidate_rows": int(len(scored)),
        "holdings_rows": int(len(holdings)),
        "period_rows": int(len(perf)),
        "coverage": coverage.to_dict(orient="records"),
        "skipped": skipped,
        "outputs": {
            "scored_csv": str(scored_path),
            "holdings_csv": str(holdings_path),
            "periods_csv": str(periods_path),
            "summary_csv": str(summary_path),
            "coverage_csv": str(coverage_path),
            "json": str(json_path),
            "markdown": str(report_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
