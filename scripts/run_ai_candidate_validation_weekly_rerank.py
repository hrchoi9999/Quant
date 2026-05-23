from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ADMIN_PAYLOAD = ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"
AI_SCORES_DIR = ROOT / r"reports\ai_overlay_v01"
ETF_UNIVERSE = ROOT / r"data\universe\universe_etf_master_latest.csv"
PRICE_DB = ROOT / r"data\db\price.db"
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

DEFAULT_TOP_N = {
    "S2": 30,
    "S2_PIT_V01": 30,
    "S3": 20,
    "S3_ACCEL_V01": 20,
    "S3_CORE2": 20,
    "I-STOCK-STRONG-RSI-V01": 30,
    "T-STOCK-V01": 10,
    "stable": 30,
    "balanced": 30,
    "growth": 20,
}

POLICIES = ["baseline", "cv_guardrail", "cv_rerank", "cv_tilt"]


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _zfill_ticker(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _load_etf_tickers() -> set[str]:
    if not ETF_UNIVERSE.exists():
        return set()
    df = pd.read_csv(ETF_UNIVERSE, dtype={"ticker": str})
    return {_zfill_ticker(x) for x in df["ticker"].dropna().tolist()} if "ticker" in df.columns else set()


def _load_weekly_rankings(payload_path: Path, etf_tickers: set[str]) -> pd.DataFrame:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    frames: list[pd.DataFrame] = []

    section_map = {
        "internal_models": ("internal", "model_code"),
        "tseries_models": ("tseries", "model_code"),
        "user_models": ("user", "service_profile"),
    }
    for section, (scope_key, model_col) in section_map.items():
        rows = payload.get("weekly_rankings", {}).get(section, []) or []
        if not rows:
            continue
        df = pd.DataFrame(rows)
        if df.empty:
            continue
        df["scope_key"] = scope_key
        df["model_id"] = df[model_col].astype(str)
        df["ticker"] = df["security_code"].map(_zfill_ticker)
        df["name"] = df.get("display_name")
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["rank_no"] = pd.to_numeric(df["rank_no"], errors="coerce")
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        df["weight"] = pd.to_numeric(df.get("weight"), errors="coerce") if "weight" in df.columns else np.nan
        df["is_etf"] = df["ticker"].isin(etf_tickers) | df["model_id"].eq("T-ETF-V01")
        df = df.loc[~df["is_etf"]].copy()
        frames.append(
            df[
                [
                    "scope_key",
                    "model_id",
                    "snapshot_date",
                    "week_end",
                    "ticker",
                    "name",
                    "rank_no",
                    "score",
                    "weight",
                    "score_basis",
                    "is_latest_snapshot",
                ]
            ]
        )

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["snapshot_date", "ticker", "rank_no"])
    out = out.sort_values(["scope_key", "model_id", "snapshot_date", "rank_no", "ticker"]).reset_index(drop=True)
    return out


def _load_candidate_validation_scores(asof: str) -> pd.DataFrame:
    path = AI_SCORES_DIR / f"ai_overlay_shadow_scores_{_token(asof)}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"ticker": str})
    needed = [
        "scope_key",
        "model_id",
        "ticker",
        "week_end",
        "ai_quality_prob",
        "ai_risk_prob",
        "ai_shadow_decision",
        "ai_model_specific_quality_prob",
        "ai_model_specific_risk_prob",
        "ai_model_specific_tag",
    ]
    df = df[[c for c in needed if c in df.columns]].copy()
    df["ticker"] = df["ticker"].map(_zfill_ticker)
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in [
        "ai_quality_prob",
        "ai_risk_prob",
        "ai_model_specific_quality_prob",
        "ai_model_specific_risk_prob",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates(["scope_key", "model_id", "ticker", "week_end"], keep="last")


def _attach_next_dates(weekly: pd.DataFrame, asof: str) -> pd.DataFrame:
    dates = (
        weekly[["scope_key", "model_id", "snapshot_date"]]
        .drop_duplicates()
        .sort_values(["scope_key", "model_id", "snapshot_date"])
    )
    dates["next_snapshot_date"] = dates.groupby(["scope_key", "model_id"])["snapshot_date"].shift(-1)
    dates["next_snapshot_date"] = dates["next_snapshot_date"].fillna(asof)
    out = weekly.merge(dates, on=["scope_key", "model_id", "snapshot_date"], how="left")
    out = out.loc[pd.to_datetime(out["next_snapshot_date"]) > pd.to_datetime(out["snapshot_date"])].copy()
    return out


def _load_price_returns(weekly: pd.DataFrame) -> pd.DataFrame:
    tickers = sorted(weekly["ticker"].dropna().unique().tolist())
    dates = sorted(set(weekly["snapshot_date"].dropna().tolist()) | set(weekly["next_snapshot_date"].dropna().tolist()))
    if not tickers or not dates:
        return weekly.assign(period_return=np.nan)

    placeholders_t = ",".join("?" for _ in tickers)
    placeholders_d = ",".join("?" for _ in dates)
    query = f"""
        SELECT ticker, date, close
        FROM prices_daily
        WHERE ticker IN ({placeholders_t})
          AND date IN ({placeholders_d})
    """
    with sqlite3.connect(PRICE_DB) as con:
        px = pd.read_sql_query(query, con, params=[*tickers, *dates])

    px["ticker"] = px["ticker"].map(_zfill_ticker)
    px["date"] = pd.to_datetime(px["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    px["close"] = pd.to_numeric(px["close"], errors="coerce")

    start_px = px.rename(columns={"date": "snapshot_date", "close": "start_close"})
    end_px = px.rename(columns={"date": "next_snapshot_date", "close": "end_close"})
    out = weekly.merge(start_px[["ticker", "snapshot_date", "start_close"]], on=["ticker", "snapshot_date"], how="left")
    out = out.merge(end_px[["ticker", "next_snapshot_date", "end_close"]], on=["ticker", "next_snapshot_date"], how="left")
    out["period_return"] = out["end_close"] / out["start_close"] - 1.0
    return out


def _base_score(frame: pd.DataFrame) -> pd.Series:
    rank = pd.to_numeric(frame["rank_no"], errors="coerce")
    max_rank = max(float(rank.max()), 1.0)
    rank_component = 1.0 - (rank - 1.0) / max_rank
    raw_score = pd.to_numeric(frame["score"], errors="coerce")
    if raw_score.notna().sum() >= 2 and raw_score.max() != raw_score.min():
        score_component = (raw_score - raw_score.min()) / (raw_score.max() - raw_score.min())
        return (rank_component.fillna(0.0) * 0.7) + (score_component.fillna(0.0) * 0.3)
    return rank_component.fillna(0.0)


def _cv_signal(frame: pd.DataFrame) -> pd.Series:
    tag = frame.get("ai_model_specific_tag", pd.Series(index=frame.index, dtype=object)).fillna("")
    quality = frame.get("ai_model_specific_quality_prob", pd.Series(index=frame.index, dtype=float)).fillna(
        frame.get("ai_quality_prob", pd.Series(index=frame.index, dtype=float))
    )
    risk = frame.get("ai_model_specific_risk_prob", pd.Series(index=frame.index, dtype=float)).fillna(
        frame.get("ai_risk_prob", pd.Series(index=frame.index, dtype=float))
    )
    prob_edge = (pd.to_numeric(quality, errors="coerce").fillna(0.5) - pd.to_numeric(risk, errors="coerce").fillna(0.5)).clip(-0.5, 0.5)
    tag_bonus = pd.Series(0.0, index=frame.index)
    tag_bonus.loc[tag.eq("MS_CONFIRM")] = 0.20
    tag_bonus.loc[tag.eq("MS_OBSERVE")] = 0.0
    tag_bonus.loc[tag.eq("MS_RISK_REVIEW")] = -0.25
    tag_bonus.loc[tag.eq("MS_FALLBACK_COMMON")] = -0.10
    return tag_bonus + prob_edge * 0.25


def _select_policy(frame: pd.DataFrame, policy: str, target_n: int) -> pd.DataFrame:
    work = frame.copy()
    work["base_rank_score"] = _base_score(work)
    work["cv_signal"] = _cv_signal(work)
    work["has_cv_score"] = work["ai_model_specific_tag"].notna() | work["ai_shadow_decision"].notna()
    work["policy"] = policy

    if policy == "baseline":
        work["policy_score"] = work["base_rank_score"]
        work["policy_weight_raw"] = 1.0
        chosen = work.sort_values(["rank_no", "ticker"]).head(target_n).copy()
    elif policy == "cv_guardrail":
        tag = work.get("ai_model_specific_tag", pd.Series(index=work.index, dtype=object)).fillna("")
        work["is_excluded_by_cv"] = tag.isin(["MS_RISK_REVIEW", "MS_FALLBACK_COMMON"])
        work["policy_score"] = work["base_rank_score"] + work["cv_signal"]
        eligible = work.loc[~work["is_excluded_by_cv"]].sort_values(["rank_no", "ticker"])
        excluded = work.loc[work["is_excluded_by_cv"]].sort_values(["rank_no", "ticker"])
        if len(eligible) >= target_n:
            chosen = eligible.head(target_n).copy()
        else:
            chosen = pd.concat([eligible, excluded.head(target_n - len(eligible))], ignore_index=False).copy()
        chosen["policy_weight_raw"] = 1.0
    elif policy == "cv_rerank":
        work["policy_score"] = work["base_rank_score"] + work["cv_signal"]
        work["policy_weight_raw"] = 1.0
        chosen = work.sort_values(["policy_score", "base_rank_score", "ticker"], ascending=[False, False, True]).head(target_n).copy()
    elif policy == "cv_tilt":
        work["policy_score"] = work["base_rank_score"]
        chosen = work.sort_values(["rank_no", "ticker"]).head(target_n).copy()
        chosen["policy_weight_raw"] = (1.0 + chosen["cv_signal"]).clip(0.5, 1.5)
    else:
        raise ValueError(f"unknown policy: {policy}")

    if chosen.empty:
        return chosen
    total = chosen["policy_weight_raw"].sum()
    chosen["policy_weight"] = chosen["policy_weight_raw"] / total if total else 1.0 / len(chosen)
    chosen["selected_count"] = len(chosen)
    chosen["target_n"] = target_n
    chosen["cv_scored_selected"] = int(chosen["has_cv_score"].sum())
    return chosen


def _target_n(model_id: str, group_size: int) -> int:
    default = DEFAULT_TOP_N.get(str(model_id), group_size)
    return max(1, min(int(default), int(group_size)))


def _run_simulation(scored: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    holdings: list[pd.DataFrame] = []
    perf_rows: list[dict[str, Any]] = []

    group_cols = ["scope_key", "model_id", "snapshot_date", "next_snapshot_date"]
    for keys, frame in scored.groupby(group_cols, dropna=False):
        scope_key, model_id, snapshot_date, next_snapshot_date = keys
        frame = frame.sort_values(["rank_no", "ticker"]).copy()
        target_n = _target_n(str(model_id), len(frame))
        baseline_set = set(frame.sort_values(["rank_no", "ticker"]).head(target_n)["ticker"].tolist())

        for policy in POLICIES:
            chosen = _select_policy(frame, policy, target_n)
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
                    "snapshot_date": snapshot_date,
                    "next_snapshot_date": next_snapshot_date,
                    "policy": policy,
                    "target_n": target_n,
                    "selected_count": int(len(chosen)),
                    "priced_count": int(ret.notna().sum()),
                    "cv_scored_selected": int(chosen["has_cv_score"].sum()),
                    "cv_scored_ratio": round(float(chosen["has_cv_score"].mean()), 6),
                    "changed_count_vs_baseline": int(changed_count),
                    "period_return": round(portfolio_return, 8) if not np.isnan(portfolio_return) else np.nan,
                    "avg_selected_return": round(float(ret.mean()), 8) if ret.notna().any() else np.nan,
                    "win_rate_selected": round(float((ret.dropna() > 0).mean()), 6) if ret.notna().any() else np.nan,
                }
            )
            holdings.append(
                chosen[
                    [
                        "scope_key",
                        "model_id",
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
                ]
            )

    holdings_df = pd.concat(holdings, ignore_index=True) if holdings else pd.DataFrame()
    perf = pd.DataFrame(perf_rows)
    return holdings_df, perf


def _summarize(perf: pd.DataFrame) -> pd.DataFrame:
    if perf.empty:
        return pd.DataFrame()
    rows = []
    for keys, frame in perf.groupby(["scope_key", "model_id", "policy"], dropna=False):
        scope_key, model_id, policy = keys
        r = pd.to_numeric(frame["period_return"], errors="coerce").dropna()
        rows.append(
            {
                "scope_key": scope_key,
                "model_id": model_id,
                "policy": policy,
                "periods": int(len(frame)),
                "priced_periods": int(len(r)),
                "avg_period_return": round(float(r.mean()), 8) if not r.empty else np.nan,
                "median_period_return": round(float(r.median()), 8) if not r.empty else np.nan,
                "win_rate": round(float((r > 0).mean()), 6) if not r.empty else np.nan,
                "worst_period_return": round(float(r.min()), 8) if not r.empty else np.nan,
                "best_period_return": round(float(r.max()), 8) if not r.empty else np.nan,
                "avg_cv_scored_ratio": round(float(frame["cv_scored_ratio"].mean()), 6),
                "avg_changed_count": round(float(frame["changed_count_vs_baseline"].mean()), 4),
                "compounded_return": round(float((1.0 + r).prod() - 1.0), 8) if not r.empty else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values(["scope_key", "model_id", "policy"]).reset_index(drop=True)


def _write_report(asof: str, summary: pd.DataFrame, out_dir: Path) -> Path:
    path = out_dir / f"AI_CANDIDATE_VALIDATION_WEEKLY_RERANK_{_token(asof)}.md"
    lines = [
        "# AI Candidate Validation Weekly Rerank Simulation",
        "",
        f"- asof: {asof}",
        "- overlay: AI-CANDIDATE-VALIDATION-V01 / 퀀트후보검증AI",
        "- scope: stock-only weekly rankings; ETF excluded",
        "- note: This is a weekly rerank/tilt simulation, not production model replacement.",
        "",
        "## 1M-like Weekly Period Summary",
        "",
        "| scope | model | policy | periods | avg period return | win rate | worst | changed avg | cv coverage |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if not summary.empty:
        for _, row in summary.iterrows():
            lines.append(
                f"| {row['scope_key']} | {row['model_id']} | {row['policy']} | {int(row['priced_periods'])} | "
                f"{row['avg_period_return']:.2%} | {row['win_rate']:.2%} | {row['worst_period_return']:.2%} | "
                f"{row['avg_changed_count']:.2f} | {row['avg_cv_scored_ratio']:.2%} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `baseline` keeps the original weekly rank.",
            "- `cv_guardrail` tries to push `MS_RISK_REVIEW` and `MS_FALLBACK_COMMON` below eligible candidates.",
            "- `cv_rerank` combines original rank score and candidate-validation signal.",
            "- `cv_tilt` keeps the same selected names but mildly tilts weights by candidate-validation signal.",
            "- If average changed count is near zero, that model's weekly list does not have enough replacement candidates for selection-level change.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Run AI-CANDIDATE-VALIDATION-V01 weekly rerank simulation.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument("--admin-payload", default=str(ADMIN_PAYLOAD))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    asof = str(args.asof)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    weekly = _load_weekly_rankings(Path(args.admin_payload), _load_etf_tickers())
    scores = _load_candidate_validation_scores(asof)
    scored = weekly.merge(scores, on=["scope_key", "model_id", "ticker", "week_end"], how="left")
    scored = _attach_next_dates(scored, asof)
    scored = _load_price_returns(scored)

    holdings, perf = _run_simulation(scored)
    summary = _summarize(perf)

    token = _token(asof)
    scored_path = out_dir / f"ai_candidate_validation_weekly_rerank_scored_universe_{token}.csv"
    holdings_path = out_dir / f"ai_candidate_validation_weekly_rerank_holdings_{token}.csv"
    perf_path = out_dir / f"ai_candidate_validation_weekly_rerank_periods_{token}.csv"
    summary_path = out_dir / f"ai_candidate_validation_weekly_rerank_summary_{token}.csv"
    json_path = out_dir / f"ai_candidate_validation_weekly_rerank_{token}.json"

    scored.to_csv(scored_path, index=False, encoding="utf-8-sig")
    holdings.to_csv(holdings_path, index=False, encoding="utf-8-sig")
    perf.to_csv(perf_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    report_path = _write_report(asof, summary, out_dir)

    coverage = (
        scored.assign(has_cv_score=scored["ai_model_specific_tag"].notna() | scored["ai_shadow_decision"].notna())
        .groupby(["scope_key", "model_id"], dropna=False)["has_cv_score"]
        .agg(["sum", "count", "mean"])
        .reset_index()
        .rename(columns={"sum": "covered_rows", "count": "total_rows", "mean": "coverage"})
    )
    payload = {
        "status": "ok",
        "asof": asof,
        "weekly_universe_rows": int(len(scored)),
        "holdings_rows": int(len(holdings)),
        "period_rows": int(len(perf)),
        "coverage": coverage.to_dict(orient="records"),
        "outputs": {
            "scored_universe_csv": str(scored_path),
            "holdings_csv": str(holdings_path),
            "periods_csv": str(perf_path),
            "summary_csv": str(summary_path),
            "json": str(json_path),
            "markdown": str(report_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
