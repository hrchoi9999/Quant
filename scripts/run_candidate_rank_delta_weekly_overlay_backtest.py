from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_ai_overlay_v01 as cv_ai  # noqa: E402
import run_ai_candidate_validation_weekly_rerank as weekly_cv  # noqa: E402


ADMIN_PAYLOAD = ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"
MODEL_DIR = ROOT / r"data\models\candidate_rank_delta_ai"
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

MODEL_CODE = "AI-CANDIDATE-RANK-DELTA-V01"
MODEL_NAME_KO = "후보순위조정AI"

POLICIES = [
    "baseline",
    "rank_drop_candidate_cash",
    "rank_drop_watch_cash",
    "rank_delta_tilt_cash",
    "rank_delta_tilt_renorm",
]


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _latest_model_path(asof: str) -> Path:
    exact = MODEL_DIR / f"{MODEL_CODE}_{_token(asof)}_001.joblib"
    if exact.exists():
        return exact
    candidates = sorted(MODEL_DIR.glob(f"{MODEL_CODE}_*.joblib"), key=lambda p: p.name)
    candidates = [p for p in candidates if p.name.split("_")[-2] <= _token(asof)]
    if not candidates:
        raise SystemExit(f"no candidate rank delta model found under {MODEL_DIR}")
    return candidates[-1]


def _decision(row: pd.Series) -> str:
    drop_prob = pd.to_numeric(row.get("rank_drop_prob"), errors="coerce")
    rank_score = pd.to_numeric(row.get("retained_rank_change_score"), errors="coerce")
    if pd.notna(drop_prob):
        if drop_prob >= 0.70:
            return "rank_drop_candidate"
        if drop_prob >= 0.50:
            return "rank_drop_watch"
    if pd.isna(rank_score):
        return "rank_observe"
    if rank_score >= 0.25:
        return "rank_upgrade_candidate"
    if rank_score >= 0.10:
        return "rank_upgrade_watch"
    if rank_score <= -0.25:
        return "rank_downgrade_candidate"
    if rank_score <= -0.10:
        return "rank_downgrade_watch"
    return "rank_hold"


def _prepare_feature_frame(base: pd.DataFrame, asof: str, numeric: list[str], categorical: list[str]) -> pd.DataFrame:
    feat = base.copy()
    feat["event_date"] = feat["snapshot_date"]
    feat["week_end"] = feat.get("week_end", feat["snapshot_date"])
    feat["event_type"] = feat.get("event_type", "weekly_ranking_candidate")
    feat["candidate_bucket"] = feat.get("candidate_bucket", "candidate")
    feat["asset_type"] = "stock"
    feat["is_current"] = pd.to_numeric(feat.get("is_latest_snapshot"), errors="coerce").fillna(0)
    feat["is_live_event"] = feat["is_current"]
    for col in ["model_overlap_count", "overlap_user_count", "overlap_internal_count", "overlap_tseries_count"]:
        if col not in feat.columns:
            feat[col] = 1 if col == "model_overlap_count" else 0
    for col in ["stage1_prob", "stage2_prob", "universe_rank_no", "universe_rank_score", "display_score"]:
        if col not in feat.columns:
            feat[col] = np.nan
    feat["display_score"] = pd.to_numeric(feat.get("display_score"), errors="coerce").fillna(pd.to_numeric(feat.get("score"), errors="coerce"))
    feat = cv_ai._attach_price_features(feat, asof)
    feat = cv_ai._attach_static_features(feat, asof)
    feat = cv_ai._attach_external_features(feat, asof)
    for col in numeric:
        if col not in feat.columns:
            feat[col] = np.nan
    for col in categorical:
        if col not in feat.columns:
            feat[col] = None
    return feat


def _score_weekly(weekly: pd.DataFrame, asof: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    model_path = _latest_model_path(asof)
    bundle = joblib.load(model_path)
    numeric = list(bundle.get("numeric_features") or [])
    categorical = list(bundle.get("categorical_features") or [])
    labels = dict(bundle.get("labels") or {})
    models = dict(bundle.get("models") or {})
    feat = _prepare_feature_frame(weekly, asof, numeric, categorical)
    drop_model = models[labels.get("drop", "label_next_rank_drop")]
    upgrade_model = models[labels.get("retained_upgrade", "label_next_rank_upgrade_3_retained")]
    downgrade_model = models[labels.get("retained_downgrade", "label_next_rank_downgrade_3_retained")]
    feat["rank_drop_prob"] = drop_model.predict_proba(feat)[:, 1] if not feat.empty else np.nan
    feat["retained_rank_upgrade_prob"] = upgrade_model.predict_proba(feat)[:, 1] if not feat.empty else np.nan
    feat["retained_rank_downgrade_prob"] = downgrade_model.predict_proba(feat)[:, 1] if not feat.empty else np.nan
    feat["retained_rank_change_score"] = feat["retained_rank_upgrade_prob"] - feat["retained_rank_downgrade_prob"]
    feat["rank_delta_score"] = (1.0 - feat["rank_drop_prob"]) * feat["retained_rank_change_score"]
    feat["rank_delta_decision"] = feat.apply(_decision, axis=1)
    keep = [
        "scope_key",
        "model_id",
        "ticker",
        "snapshot_date",
        "week_end",
        "rank_drop_prob",
        "retained_rank_upgrade_prob",
        "retained_rank_downgrade_prob",
        "retained_rank_change_score",
        "rank_delta_score",
        "rank_delta_decision",
    ]
    scored = weekly.merge(feat[[c for c in keep if c in feat.columns]], on=["scope_key", "model_id", "ticker", "snapshot_date", "week_end"], how="left")
    meta = {
        "model_path": str(model_path),
        "model_version": bundle.get("model_version") or model_path.stem,
        "model_structure": bundle.get("model_structure"),
    }
    return scored, meta


def _initial_weights(frame: pd.DataFrame) -> pd.Series:
    w = pd.to_numeric(frame.get("weight"), errors="coerce")
    if w.notna().sum() and float(w.fillna(0).sum()) > 0:
        w = w.fillna(0).clip(lower=0)
        return w / w.sum()
    return pd.Series(1.0 / len(frame), index=frame.index)


def _policy_weights(frame: pd.DataFrame, policy: str) -> pd.Series:
    base = _initial_weights(frame)
    decision = frame.get("rank_delta_decision", pd.Series(index=frame.index, dtype=object)).fillna("rank_observe")
    if policy == "baseline":
        return base
    if policy == "rank_drop_candidate_cash":
        return base.where(~decision.eq("rank_drop_candidate"), 0.0)
    if policy == "rank_drop_watch_cash":
        return base.where(~decision.isin(["rank_drop_candidate", "rank_drop_watch"]), 0.0)
    if policy == "rank_delta_tilt_cash":
        mult = decision.map(
            {
                "rank_upgrade_candidate": 1.05,
                "rank_upgrade_watch": 1.00,
                "rank_hold": 1.00,
                "rank_downgrade_watch": 0.80,
                "rank_downgrade_candidate": 0.60,
                "rank_drop_watch": 0.50,
                "rank_drop_candidate": 0.25,
            }
        ).fillna(0.80)
        return base * mult
    if policy == "rank_delta_tilt_renorm":
        mult = decision.map(
            {
                "rank_upgrade_candidate": 1.15,
                "rank_upgrade_watch": 1.05,
                "rank_hold": 1.00,
                "rank_downgrade_watch": 0.80,
                "rank_downgrade_candidate": 0.60,
                "rank_drop_watch": 0.50,
                "rank_drop_candidate": 0.25,
            }
        ).fillna(0.80)
        w = base * mult
        return w / w.sum() if float(w.sum()) > 0 else base
    raise ValueError(policy)


def _run_backtest(scored: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    holdings: list[pd.DataFrame] = []
    perf_rows: list[dict[str, Any]] = []
    group_cols = ["scope_key", "model_id", "snapshot_date", "next_snapshot_date"]
    for keys, frame in scored.groupby(group_cols, dropna=False):
        scope_key, model_id, snapshot_date, next_snapshot_date = keys
        frame = frame.sort_values(["rank_no", "ticker"]).copy()
        decision = frame.get("rank_delta_decision", pd.Series(index=frame.index, dtype=object)).fillna("rank_observe")
        ret = pd.to_numeric(frame["period_return"], errors="coerce")
        for policy in POLICIES:
            weights = _policy_weights(frame, policy)
            valid = frame.loc[ret.notna()].copy()
            valid_weights = weights.loc[valid.index]
            portfolio_return = float((valid["period_return"] * valid_weights).sum()) if not valid.empty else np.nan
            removed_weight = float(1.0 - weights.sum()) if policy != "rank_delta_tilt_renorm" else 0.0
            perf_rows.append(
                {
                    "scope_key": scope_key,
                    "model_id": model_id,
                    "snapshot_date": snapshot_date,
                    "next_snapshot_date": next_snapshot_date,
                    "policy": policy,
                    "selected_count": int(len(frame)),
                    "priced_count": int(ret.notna().sum()),
                    "rank_drop_candidate_count": int(decision.eq("rank_drop_candidate").sum()),
                    "rank_drop_watch_count": int(decision.eq("rank_drop_watch").sum()),
                    "rank_upgrade_candidate_count": int(decision.eq("rank_upgrade_candidate").sum()),
                    "rank_upgrade_watch_count": int(decision.eq("rank_upgrade_watch").sum()),
                    "rank_downgrade_count": int(decision.isin(["rank_downgrade_candidate", "rank_downgrade_watch"]).sum()),
                    "removed_weight": round(removed_weight, 8),
                    "effective_weight": round(float(weights.sum()), 8),
                    "period_return": round(portfolio_return, 8) if not np.isnan(portfolio_return) else np.nan,
                }
            )
            part = frame.copy()
            part["policy"] = policy
            part["policy_weight"] = weights
            holdings.append(
                part[
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
                        "weight",
                        "policy_weight",
                        "period_return",
                        "rank_drop_prob",
                        "retained_rank_change_score",
                        "rank_delta_score",
                        "rank_delta_decision",
                    ]
                ]
            )
    return (
        pd.concat(holdings, ignore_index=True) if holdings else pd.DataFrame(),
        pd.DataFrame(perf_rows),
    )


def _nav_mdd(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    nav = (1.0 + returns.fillna(0)).cumprod()
    dd = nav / nav.cummax() - 1.0
    return round(float(dd.min()), 8)


def _summarize(perf: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if perf.empty:
        return pd.DataFrame()
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
                "downside_period_rate": round(float((r <= -0.03).mean()), 6) if not r.empty else np.nan,
                "worst_period_return": round(float(r.min()), 8) if not r.empty else np.nan,
                "compounded_return": round(float((1.0 + r).prod() - 1.0), 8) if not r.empty else np.nan,
                "nav_mdd": _nav_mdd(r),
                "avg_removed_weight": round(float(frame["removed_weight"].mean()), 8),
                "avg_rank_drop_candidate_count": round(float(frame["rank_drop_candidate_count"].mean()), 4),
                "avg_rank_drop_watch_count": round(float(frame["rank_drop_watch_count"].mean()), 4),
                "avg_rank_upgrade_count": round(float((frame["rank_upgrade_candidate_count"] + frame["rank_upgrade_watch_count"]).mean()), 4),
            }
        )
    return pd.DataFrame(rows).sort_values(["scope_key", "model_id", "policy"]).reset_index(drop=True)


def _write_report(asof: str, summary: pd.DataFrame, coverage: pd.DataFrame, meta: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / f"CANDIDATE_RANK_DELTA_AI_WEEKLY_OVERLAY_BACKTEST_{_token(asof)}.md"
    lines = [
        "# Candidate Rank Delta AI Weekly Overlay Backtest",
        "",
        f"- asof: {asof}",
        f"- overlay: {MODEL_CODE} / {MODEL_NAME_KO}",
        f"- model_version: `{meta.get('model_version')}`",
        "- scope: stock-only weekly rankings; ETF excluded",
        "- note: weekly strategy overlay test using predicted next-rebalance drop/rank-change signals.",
        "",
        "## Coverage",
        "",
        "| scope | model | rows | periods | drop candidate | drop watch | upgrade candidate | upgrade watch | downgrade | hold | observe |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in coverage.iterrows():
        lines.append(
            f"| {row['scope_key']} | {row['model_id']} | {int(row['rows'])} | {int(row['periods'])} | "
            f"{int(row.get('rank_drop_candidate', 0))} | {int(row.get('rank_drop_watch', 0))} | "
            f"{int(row.get('rank_upgrade_candidate', 0))} | {int(row.get('rank_upgrade_watch', 0))} | "
            f"{int(row.get('rank_downgrade_candidate', 0) + row.get('rank_downgrade_watch', 0))} | "
            f"{int(row.get('rank_hold', 0))} | {int(row.get('rank_observe', 0))} |"
        )
    lines.extend(
        [
            "",
            "## Policy Summary",
            "",
            "| scope | model | policy | periods | avg ret | win | downside <= -3% | worst | nav MDD | removed w |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['scope_key']} | {row['model_id']} | {row['policy']} | {int(row['priced_periods'])} | "
            f"{row['avg_period_return']:.2%} | {row['win_rate']:.2%} | {row['downside_period_rate']:.2%} | "
            f"{row['worst_period_return']:.2%} | {row['nav_mdd']:.2%} | {row['avg_removed_weight']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Policy Definitions",
            "",
            "- `baseline`: original weekly holdings/weights.",
            "- `rank_drop_candidate_cash`: sets only high drop-risk positions to cash.",
            "- `rank_drop_watch_cash`: sets drop candidate/watch positions to cash.",
            "- `rank_delta_tilt_cash`: tilts by predicted next-rank decision and keeps unallocated weight in cash.",
            "- `rank_delta_tilt_renorm`: tilts by predicted next-rank decision then renormalizes to full investment.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest AI-CANDIDATE-RANK-DELTA-V01 as a weekly overlay.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--admin-payload", default=str(ADMIN_PAYLOAD))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    asof = str(args.asof)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    weekly = weekly_cv._load_weekly_rankings(Path(args.admin_payload), weekly_cv._load_etf_tickers())
    scored, meta = _score_weekly(weekly, asof)
    scored = weekly_cv._attach_next_dates(scored, asof)
    scored = weekly_cv._load_price_returns(scored)
    holdings, perf = _run_backtest(scored)
    summary = _summarize(perf)

    coverage = (
        scored.groupby(["scope_key", "model_id", "rank_delta_decision"], dropna=False)
        .size()
        .reset_index(name="count")
        .pivot_table(index=["scope_key", "model_id"], columns="rank_delta_decision", values="count", fill_value=0, aggfunc="sum")
        .reset_index()
    )
    total = scored.groupby(["scope_key", "model_id"]).agg(rows=("ticker", "size"), periods=("snapshot_date", "nunique")).reset_index()
    coverage = total.merge(coverage, on=["scope_key", "model_id"], how="left").fillna(0)

    token = _token(asof)
    scored_path = out_dir / f"candidate_rank_delta_ai_weekly_overlay_scored_{token}.csv"
    holdings_path = out_dir / f"candidate_rank_delta_ai_weekly_overlay_holdings_{token}.csv"
    periods_path = out_dir / f"candidate_rank_delta_ai_weekly_overlay_periods_{token}.csv"
    summary_path = out_dir / f"candidate_rank_delta_ai_weekly_overlay_summary_{token}.csv"
    coverage_path = out_dir / f"candidate_rank_delta_ai_weekly_overlay_coverage_{token}.csv"
    json_path = out_dir / f"candidate_rank_delta_ai_weekly_overlay_backtest_{token}.json"
    report_path = _write_report(asof, summary, coverage, meta, out_dir)

    scored.to_csv(scored_path, index=False, encoding="utf-8-sig")
    holdings.to_csv(holdings_path, index=False, encoding="utf-8-sig")
    perf.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asof": asof,
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "model_meta": meta,
        "scored_rows": int(len(scored)),
        "holdings_rows": int(len(holdings)),
        "period_rows": int(len(perf)),
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
