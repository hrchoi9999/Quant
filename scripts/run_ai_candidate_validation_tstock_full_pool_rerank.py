from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import run_ai_candidate_validation_full_pool_rerank as full_pool
import run_ai_candidate_validation_weekly_rerank as weekly_cv


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / r"reports\model_upgrade_research\20260511\S3_TWO_STAGE_MODELING\logistic_regression"
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
MODEL_NAME_KO = "퀀트후보검증AI"
T_MODEL_ID = "T-STOCK-V01"
DEFAULT_START = "2024-01-01"
DEFAULT_POOL_N = 200
DEFAULT_TOP_N = 10


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _zfill_ticker(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else ""


def _load_prediction_pool(asof: str, start: str, pool_n: int, horizon: str) -> pd.DataFrame:
    hist_path = MODEL_DIR / "stage1_test_predictions.csv"
    latest_path = MODEL_DIR / "latest_stage1_rank.csv"
    if not hist_path.exists() or not latest_path.exists():
        raise SystemExit(f"missing T-STOCK stage1 rank files under {MODEL_DIR}")

    hist = pd.read_csv(hist_path, dtype={"ticker": str})
    hist = hist.loc[hist["horizon"].astype(str).eq(horizon)].copy()
    hist["snapshot_date"] = pd.to_datetime(hist["signal_date"], errors="coerce")
    hist = hist.loc[(hist["snapshot_date"] >= pd.Timestamp(start)) & (hist["snapshot_date"] <= pd.Timestamp(asof))].copy()
    hist = hist.rename(columns={"pred_prob": "stage1_prob"})
    hist["asof_date"] = hist["snapshot_date"].dt.strftime("%Y-%m-%d")

    latest = pd.read_csv(latest_path, dtype={"ticker": str})
    latest["snapshot_date"] = pd.to_datetime(latest["asof_date"], errors="coerce")
    latest = latest.loc[latest["snapshot_date"] <= pd.Timestamp(asof)].copy()
    latest["horizon"] = horizon
    latest = latest.rename(columns={"pred_prob": "stage1_prob"})

    base_cols = ["snapshot_date", "ticker", "name", "market", "stage1_prob", "rank"]
    frames = [hist[[c for c in base_cols if c in hist.columns]]]
    if not latest.empty:
        frames.append(latest[[c for c in base_cols if c in latest.columns]])
    pool = pd.concat(frames, ignore_index=True)
    pool["ticker"] = pool["ticker"].map(_zfill_ticker)
    pool["score"] = pd.to_numeric(pool["stage1_prob"], errors="coerce")
    pool = pool.dropna(subset=["snapshot_date", "ticker", "score"])
    pool = pool.sort_values(["snapshot_date", "score", "ticker"], ascending=[True, False, True])
    pool["rank_no"] = pool.groupby("snapshot_date").cumcount() + 1
    pool = pool.loc[pool["rank_no"] <= pool_n].copy()

    pool["scope_key"] = "tseries"
    pool["model_id"] = T_MODEL_ID
    pool["horizon"] = horizon
    pool["event_date"] = pool["snapshot_date"].dt.strftime("%Y-%m-%d")
    pool["week_end"] = pool["event_date"]
    pool["event_type"] = "tstock_full_pool_candidate"
    pool["score_basis"] = "stage1_prob"
    pool["candidate_bucket"] = f"{horizon}_top{pool_n}_pool"
    pool["asset_group"] = "stock"
    pool["weight"] = np.nan
    pool["stage2_prob"] = np.nan
    pool["universe_rank_no"] = pool["rank_no"].astype(float)
    group_count = pool.groupby("snapshot_date")["ticker"].transform("nunique")
    pool["universe_rank_score"] = np.where(
        group_count > 1,
        (1.0 - (pool["rank_no"] - 1) / (group_count - 1)) * 100.0,
        100.0,
    )
    pool["display_score"] = pool["score"]
    pool["is_current"] = 0
    keep = [
        "scope_key",
        "model_id",
        "horizon",
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
    return pool[keep].sort_values(["snapshot_date", "rank_no", "ticker"]).reset_index(drop=True)


def _run_simulation(scored: pd.DataFrame, top_n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    holdings: list[pd.DataFrame] = []
    perf_rows: list[dict[str, Any]] = []
    group_cols = ["scope_key", "model_id", "horizon", "snapshot_date", "next_snapshot_date"]
    for keys, frame in scored.groupby(group_cols, dropna=False):
        scope_key, model_id, horizon, snapshot_date, next_snapshot_date = keys
        frame = frame.sort_values(["rank_no", "ticker"]).copy()
        target_n = max(1, min(int(top_n), len(frame)))
        baseline_set = set(frame.head(target_n)["ticker"].tolist())
        for policy in weekly_cv.POLICIES:
            chosen = weekly_cv._select_policy(frame, policy, target_n)
            if chosen.empty:
                continue
            ret = pd.to_numeric(chosen["period_return"], errors="coerce")
            valid = chosen.loc[ret.notna()].copy()
            portfolio_return = float((valid["period_return"] * valid["policy_weight"]).sum()) if not valid.empty else np.nan
            selected_set = set(chosen["ticker"].tolist())
            changed_count = len(selected_set.symmetric_difference(baseline_set)) // 2
            perf_rows.append(
                {
                    "scope_key": scope_key,
                    "model_id": model_id,
                    "horizon": horizon,
                    "snapshot_date": snapshot_date,
                    "next_snapshot_date": next_snapshot_date,
                    "policy": policy,
                    "target_n": target_n,
                    "selected_count": int(len(chosen)),
                    "priced_count": int(ret.notna().sum()),
                    "changed_count_vs_baseline": int(changed_count),
                    "period_return": round(portfolio_return, 8) if not np.isnan(portfolio_return) else np.nan,
                    "avg_selected_return": round(float(ret.mean()), 8) if ret.notna().any() else np.nan,
                    "win_rate_selected": round(float((ret.dropna() > 0).mean()), 6) if ret.notna().any() else np.nan,
                }
            )
            keep = [
                "scope_key",
                "model_id",
                "horizon",
                "snapshot_date",
                "next_snapshot_date",
                "policy",
                "ticker",
                "name",
                "rank_no",
                "score",
                "policy_score",
                "policy_weight",
                "period_return",
                "ai_model_specific_tag",
                "ai_model_specific_quality_prob",
                "ai_model_specific_risk_prob",
            ]
            holdings.append(chosen[[col for col in keep if col in chosen.columns]])
    return (
        pd.concat(holdings, ignore_index=True) if holdings else pd.DataFrame(),
        pd.DataFrame(perf_rows),
    )


def _summarize(perf: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if perf.empty:
        return pd.DataFrame()
    for keys, frame in perf.groupby(["scope_key", "model_id", "horizon", "policy"], dropna=False):
        scope_key, model_id, horizon, policy = keys
        r = pd.to_numeric(frame["period_return"], errors="coerce").dropna()
        rows.append(
            {
                "scope_key": scope_key,
                "model_id": model_id,
                "horizon": horizon,
                "policy": policy,
                "periods": int(len(frame)),
                "priced_periods": int(len(r)),
                "avg_period_return": round(float(r.mean()), 8) if not r.empty else np.nan,
                "median_period_return": round(float(r.median()), 8) if not r.empty else np.nan,
                "win_rate": round(float((r > 0).mean()), 6) if not r.empty else np.nan,
                "worst_period_return": round(float(r.min()), 8) if not r.empty else np.nan,
                "best_period_return": round(float(r.max()), 8) if not r.empty else np.nan,
                "avg_changed_count": round(float(frame["changed_count_vs_baseline"].mean()), 4),
                "compounded_return": round(float((1.0 + r).prod() - 1.0), 8) if not r.empty else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values(["horizon", "policy"]).reset_index(drop=True)


def _write_report(asof: str, start: str, pool_n: int, top_n: int, summary: pd.DataFrame, coverage: pd.DataFrame, out_dir: Path) -> Path:
    path = out_dir / f"AI_CANDIDATE_VALIDATION_TSTOCK_FULL_POOL_RERANK_{_token(asof)}.md"
    lines = [
        "# AI Candidate Validation T-STOCK Full-Pool Rerank Simulation",
        "",
        f"- asof: {asof}",
        f"- start: {start}",
        f"- candidate pool: T-STOCK stage1 probability top{pool_n}",
        f"- selected count: top{top_n}",
        f"- overlay: {MODEL_CODE} / {MODEL_NAME_KO}",
        "- scope: T-STOCK only; ETF excluded",
        "",
        "## Coverage",
        "",
        "| horizon | rows | periods | avg pool size | cv coverage |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for _, row in coverage.iterrows():
        lines.append(
            f"| {row['horizon']} | {int(row['rows'])} | {int(row['periods'])} | {row['avg_pool_size']:.1f} | {row['cv_coverage']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Policy Summary",
            "",
            "| horizon | policy | periods | avg period return | win rate | worst | changed avg |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['horizon']} | {row['policy']} | {int(row['priced_periods'])} | "
            f"{row['avg_period_return']:.2%} | {row['win_rate']:.2%} | {row['worst_period_return']:.2%} | "
            f"{row['avg_changed_count']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `baseline` selects top names by T-STOCK stage1 probability.",
            "- `cv_guardrail` lowers CandidateValidation risk-review/fallback names.",
            "- `cv_rerank` combines T-STOCK stage1 rank and CandidateValidation signal.",
            "- `cv_tilt` keeps baseline names but adjusts weights by CandidateValidation signal.",
            "- This is a research simulation, not a production T-STOCK replacement.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CandidateValidation AI rerank on T-STOCK full stage1 candidate pool.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--pool-n", type=int, default=DEFAULT_POOL_N)
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--horizons", default="3M,6M,1Y")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    asof = str(args.asof)
    start = str(args.start)
    pool_n = int(args.pool_n)
    top_n = int(args.top_n)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scored_frames: list[pd.DataFrame] = []
    for horizon in [h.strip() for h in str(args.horizons).split(",") if h.strip()]:
        pool = _load_prediction_pool(asof, start, pool_n, horizon)
        pool = full_pool._next_period_returns(full_pool._load_prices(), pool, asof)
        scored = full_pool._score_full_pool(pool.drop(columns=["horizon"], errors="ignore"), asof, "kiwoom_dart")
        scored["horizon"] = horizon
        scored_frames.append(scored)

    scored_all = pd.concat(scored_frames, ignore_index=True) if scored_frames else pd.DataFrame()
    holdings, perf = _run_simulation(scored_all, top_n)
    summary = _summarize(perf)

    scored_all["has_cv_score"] = scored_all["ai_model_specific_tag"].notna() | scored_all["ai_shadow_decision"].notna()
    coverage = (
        scored_all.groupby(["horizon"], dropna=False)
        .agg(
            rows=("ticker", "size"),
            periods=("snapshot_date", "nunique"),
            avg_pool_size=("ticker", lambda s: float(len(s) / scored_all.loc[s.index, "snapshot_date"].nunique())),
            cv_coverage=("has_cv_score", "mean"),
        )
        .reset_index()
    )

    token = _token(asof)
    scored_path = out_dir / f"ai_candidate_validation_tstock_full_pool_scored_top{pool_n}_{token}.csv"
    holdings_path = out_dir / f"ai_candidate_validation_tstock_full_pool_holdings_top{pool_n}_{token}.csv"
    periods_path = out_dir / f"ai_candidate_validation_tstock_full_pool_periods_top{pool_n}_{token}.csv"
    summary_path = out_dir / f"ai_candidate_validation_tstock_full_pool_summary_top{pool_n}_{token}.csv"
    coverage_path = out_dir / f"ai_candidate_validation_tstock_full_pool_coverage_top{pool_n}_{token}.csv"
    json_path = out_dir / f"ai_candidate_validation_tstock_full_pool_rerank_top{pool_n}_{token}.json"
    report_path = _write_report(asof, start, pool_n, top_n, summary, coverage, out_dir)

    scored_all.to_csv(scored_path, index=False, encoding="utf-8-sig")
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
        "top_n": top_n,
        "model_id": T_MODEL_ID,
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "candidate_rows": int(len(scored_all)),
        "holdings_rows": int(len(holdings)),
        "period_rows": int(len(perf)),
        "coverage": coverage.to_dict(orient="records"),
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
