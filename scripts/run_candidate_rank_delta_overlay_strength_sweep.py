from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"
WEB_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"

MODEL_CODE = "AI-CANDIDATE-RANK-DELTA-V01"
MODEL_NAME_KO = "후보순위조정AI"

BASE_MULTIPLIERS = {
    "rank_upgrade_candidate": 1.15,
    "rank_upgrade_watch": 1.05,
    "rank_hold": 1.00,
    "rank_downgrade_watch": 0.80,
    "rank_downgrade_candidate": 0.60,
    "rank_drop_watch": 0.50,
    "rank_drop_candidate": 0.25,
    "rank_observe": 0.80,
}

DEFAULT_STRENGTHS = [0.0, 0.25, 0.50, 0.75, 1.00, 1.25, 1.50]
POLICY_MODES = ["renorm", "cash"]


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _initial_weights(frame: pd.DataFrame) -> pd.Series:
    w = pd.to_numeric(frame.get("weight"), errors="coerce")
    if w.notna().sum() and float(w.fillna(0).sum()) > 0:
        w = w.fillna(0).clip(lower=0)
        return w / w.sum()
    return pd.Series(1.0 / len(frame), index=frame.index)


def _scaled_multiplier(decision: pd.Series, strength: float) -> pd.Series:
    base = decision.fillna("rank_observe").map(BASE_MULTIPLIERS).fillna(BASE_MULTIPLIERS["rank_observe"])
    scaled = 1.0 + float(strength) * (base - 1.0)
    return scaled.clip(lower=0.0, upper=2.5)


def _policy_weights(frame: pd.DataFrame, mode: str, strength: float) -> pd.Series:
    base = _initial_weights(frame)
    if float(strength) == 0:
        return base
    decision = frame.get("rank_delta_decision", pd.Series(index=frame.index, dtype=object))
    weights = base * _scaled_multiplier(decision, strength)
    if mode == "renorm":
        return weights / weights.sum() if float(weights.sum()) > 0 else base
    if mode == "cash":
        return weights
    raise ValueError(f"unknown policy mode: {mode}")


def _nav_mdd(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    nav = (1.0 + returns.fillna(0)).cumprod()
    dd = nav / nav.cummax() - 1.0
    return round(float(dd.min()), 8)


def _run_sweep(scored: pd.DataFrame, strengths: list[float]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = ["scope_key", "model_id", "snapshot_date", "next_snapshot_date"]
    for keys, frame in scored.groupby(group_cols, dropna=False):
        scope_key, model_id, snapshot_date, next_snapshot_date = keys
        frame = frame.sort_values(["rank_no", "ticker"]).copy()
        returns = pd.to_numeric(frame["period_return"], errors="coerce")
        decision = frame.get("rank_delta_decision", pd.Series(index=frame.index, dtype=object)).fillna("rank_observe")
        for mode in POLICY_MODES:
            for strength in strengths:
                weights = _policy_weights(frame, mode, strength)
                valid = frame.loc[returns.notna()].copy()
                valid_weights = weights.loc[valid.index]
                period_return = float((valid["period_return"] * valid_weights).sum()) if not valid.empty else np.nan
                rows.append(
                    {
                        "scope_key": scope_key,
                        "model_id": model_id,
                        "snapshot_date": snapshot_date,
                        "next_snapshot_date": next_snapshot_date,
                        "policy_mode": mode,
                        "strength": round(float(strength), 4),
                        "policy": f"rank_delta_{mode}_s{strength:.2f}",
                        "selected_count": int(len(frame)),
                        "priced_count": int(returns.notna().sum()),
                        "rank_drop_candidate_count": int(decision.eq("rank_drop_candidate").sum()),
                        "rank_drop_watch_count": int(decision.eq("rank_drop_watch").sum()),
                        "rank_upgrade_count": int(decision.isin(["rank_upgrade_candidate", "rank_upgrade_watch"]).sum()),
                        "rank_downgrade_count": int(decision.isin(["rank_downgrade_candidate", "rank_downgrade_watch"]).sum()),
                        "removed_weight": round(float(max(0.0, 1.0 - weights.sum())), 8),
                        "effective_weight": round(float(weights.sum()), 8),
                        "period_return": round(period_return, 8) if not np.isnan(period_return) else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def _summarize(periods: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, frame in periods.groupby(["scope_key", "model_id", "policy_mode", "strength", "policy"], dropna=False):
        scope_key, model_id, policy_mode, strength, policy = keys
        r = pd.to_numeric(frame["period_return"], errors="coerce").dropna()
        rows.append(
            {
                "scope_key": scope_key,
                "model_id": model_id,
                "policy_mode": policy_mode,
                "strength": round(float(strength), 4),
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
                "avg_rank_upgrade_count": round(float(frame["rank_upgrade_count"].mean()), 4),
            }
        )
    return pd.DataFrame(rows).sort_values(["scope_key", "model_id", "policy_mode", "strength"]).reset_index(drop=True)


def _recommend(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, frame in summary.groupby(["scope_key", "model_id"], dropna=False):
        scope_key, model_id = keys
        base = frame[(frame["strength"] == 0) & (frame["policy_mode"] == "renorm")]
        if base.empty:
            continue
        base_row = base.iloc[0]
        if pd.isna(base_row.get("avg_period_return")):
            continue
        candidates = frame[frame["strength"] > 0].copy()
        candidates = candidates[pd.to_numeric(candidates["avg_period_return"], errors="coerce").notna()]
        if candidates.empty:
            continue
        candidates["avg_return_delta"] = candidates["avg_period_return"] - float(base_row["avg_period_return"])
        candidates["compounded_return_delta"] = candidates["compounded_return"] - float(base_row["compounded_return"])
        candidates["mdd_delta"] = candidates["nav_mdd"] - float(base_row["nav_mdd"])
        candidates["downside_delta"] = candidates["downside_period_rate"] - float(base_row["downside_period_rate"])
        guard = candidates[
            (candidates["avg_return_delta"] >= 0)
            & (candidates["mdd_delta"] >= -0.03)
            & (candidates["downside_delta"] <= 0.02)
        ]
        pool = guard if not guard.empty else candidates
        best = pool.sort_values(
            ["avg_period_return", "compounded_return", "nav_mdd", "downside_period_rate"],
            ascending=[False, False, False, True],
        ).iloc[0]
        use_overlay = float(best["avg_return_delta"]) > 0
        if not use_overlay:
            best_policy_mode = "baseline"
            best_strength = 0.0
            best_policy = "baseline"
            best_avg_period_return = float(base_row["avg_period_return"])
            best_compounded_return = float(base_row["compounded_return"])
            best_nav_mdd = float(base_row["nav_mdd"])
            avg_return_delta = 0.0
            compounded_return_delta = 0.0
            mdd_delta = 0.0
            downside_delta = 0.0
            risk_guard_pass = False
        else:
            best_policy_mode = best["policy_mode"]
            best_strength = float(best["strength"])
            best_policy = best["policy"]
            best_avg_period_return = float(best["avg_period_return"])
            best_compounded_return = float(best["compounded_return"])
            best_nav_mdd = float(best["nav_mdd"])
            avg_return_delta = float(best["avg_return_delta"])
            compounded_return_delta = float(best["compounded_return_delta"])
            mdd_delta = float(best["mdd_delta"])
            downside_delta = float(best["downside_delta"])
            risk_guard_pass = bool(not guard.empty and best.name in guard.index)
        rows.append(
            {
                "scope_key": scope_key,
                "model_id": model_id,
                "baseline_avg_period_return": round(float(base_row["avg_period_return"]), 8),
                "baseline_compounded_return": round(float(base_row["compounded_return"]), 8),
                "baseline_nav_mdd": round(float(base_row["nav_mdd"]), 8),
                "recommended_policy_mode": best_policy_mode,
                "recommended_strength": round(best_strength, 4),
                "recommended_policy": best_policy,
                "recommended_avg_period_return": round(best_avg_period_return, 8),
                "recommended_compounded_return": round(best_compounded_return, 8),
                "recommended_nav_mdd": round(best_nav_mdd, 8),
                "avg_return_delta": round(avg_return_delta, 8),
                "compounded_return_delta": round(compounded_return_delta, 8),
                "mdd_delta": round(mdd_delta, 8),
                "downside_delta": round(downside_delta, 8),
                "risk_guard_pass": risk_guard_pass,
                "recommendation": "use_overlay" if use_overlay else "keep_baseline",
            }
        )
    return pd.DataFrame(rows).sort_values(["scope_key", "model_id"]).reset_index(drop=True)


def _write_report(asof: str, summary: pd.DataFrame, recommendation: pd.DataFrame, out_dir: Path) -> Path:
    path = out_dir / f"CANDIDATE_RANK_DELTA_OVERLAY_STRENGTH_SWEEP_{_token(asof)}.md"
    lines = [
        "# Candidate Rank Delta Overlay Strength Sweep",
        "",
        f"- asof: {asof}",
        f"- model: {MODEL_CODE} / {MODEL_NAME_KO}",
        "- objective: return-first strategy-level overlay strength tuning.",
        "- baseline: strength 0.00 equals original strategy portfolio.",
        "- strength: 1.00 equals the existing fixed tilt profile; 0.50 is half strength; 1.50 is stronger tilt.",
        "",
        "## Recommended Strength",
        "",
        "| scope | model | mode | strength | avg ret delta | compounded delta | MDD delta | downside delta | action |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in recommendation.iterrows():
        lines.append(
            f"| {row['scope_key']} | {row['model_id']} | {row['recommended_policy_mode']} | {row['recommended_strength']:.2f} | "
            f"{row['avg_return_delta']:.2%} | {row['compounded_return_delta']:.2%} | "
            f"{row['mdd_delta']:.2%} | {row['downside_delta']:.2%} | {row['recommendation']} |"
        )
    lines.extend(
        [
            "",
            "## Sweep Summary",
            "",
            "| scope | model | mode | strength | avg ret | compounded | win | downside | MDD | removed w |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['scope_key']} | {row['model_id']} | {row['policy_mode']} | {row['strength']:.2f} | "
            f"{row['avg_period_return']:.2%} | {row['compounded_return']:.2%} | {row['win_rate']:.2%} | "
            f"{row['downside_period_rate']:.2%} | {row['nav_mdd']:.2%} | {row['avg_removed_weight']:.2%} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep strategy-specific overlay strength for Candidate Rank Delta AI.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--scored-csv", default=None)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--web-current-dir", default=str(WEB_CURRENT_DIR))
    parser.add_argument("--strengths", default=",".join(str(x) for x in DEFAULT_STRENGTHS))
    args = parser.parse_args()

    asof = str(args.asof)
    token = _token(asof)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    web_current_dir = Path(args.web_current_dir)
    web_current_dir.mkdir(parents=True, exist_ok=True)
    scored_path = Path(args.scored_csv) if args.scored_csv else out_dir / f"candidate_rank_delta_ai_weekly_overlay_scored_{token}.csv"
    if not scored_path.exists():
        raise SystemExit(f"scored csv not found: {scored_path}")

    strengths = sorted({round(float(x.strip()), 4) for x in str(args.strengths).split(",") if x.strip()})
    if 0.0 not in strengths:
        strengths = [0.0, *strengths]

    scored = pd.read_csv(scored_path, low_memory=False)
    scored["rank_no"] = pd.to_numeric(scored.get("rank_no"), errors="coerce")
    scored["period_return"] = pd.to_numeric(scored.get("period_return"), errors="coerce")

    periods = _run_sweep(scored, strengths)
    summary = _summarize(periods)
    recommendation = _recommend(summary)
    report_path = _write_report(asof, summary, recommendation, out_dir)

    periods_path = out_dir / f"candidate_rank_delta_overlay_strength_periods_{token}.csv"
    summary_path = out_dir / f"candidate_rank_delta_overlay_strength_sweep_{token}.csv"
    recommendation_path = out_dir / f"candidate_rank_delta_overlay_strength_recommendation_{token}.csv"
    json_path = out_dir / f"candidate_rank_delta_overlay_strength_sweep_{token}.json"
    current_path = web_current_dir / "candidate_rank_delta_overlay_strength_current.json"

    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    recommendation.to_csv(recommendation_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asof": asof,
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "objective": "return_first_strategy_level_overlay_strength_tuning",
        "strength_definition": {
            "0.00": "baseline; no overlay",
            "1.00": "existing fixed candidate-rank-delta tilt",
            "1.50": "stronger-than-current tilt",
        },
        "base_multipliers": BASE_MULTIPLIERS,
        "recommendations": recommendation.to_dict(orient="records"),
        "outputs": {
            "periods_csv": str(periods_path),
            "summary_csv": str(summary_path),
            "recommendation_csv": str(recommendation_path),
            "json": str(json_path),
            "current_json": str(current_path),
            "markdown": str(report_path),
        },
    }
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    current_path.write_text(json_text, encoding="utf-8")
    print(json_text)


if __name__ == "__main__":
    main()
