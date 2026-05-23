from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

import build_ai_overlay_v01 as cv_ai
import build_downside_risk_ai_v01 as downside_ai
import run_ai_candidate_validation_weekly_rerank as weekly_cv


ROOT = Path(__file__).resolve().parents[1]
ADMIN_PAYLOAD = ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"
MODEL_DIR = ROOT / r"data\models\downside_risk_ai"
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

MODEL_CODE = "AI-DOWNSIDE-RISK-V01"
MODEL_NAME_KO = "하락위험예측AI"

POLICIES = [
    "baseline",
    "risk_exit_cash",
    "risk_caution_cash",
    "risk_tilt_cash",
    "risk_tilt_renorm",
]


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _latest_model_path(asof: str) -> Path:
    exact = MODEL_DIR / f"{MODEL_CODE}_{_token(asof)}_001.joblib"
    if exact.exists():
        return exact
    paths = sorted(MODEL_DIR.glob(f"{MODEL_CODE}_*.joblib"), key=lambda p: p.name)
    paths = [p for p in paths if p.name.split("_")[-2] <= _token(asof)]
    if not paths:
        raise SystemExit(f"no downside risk model found under {MODEL_DIR}")
    return paths[-1]


def _prepare_feature_frame(base: pd.DataFrame, asof: str, numeric: list[str], categorical: list[str]) -> pd.DataFrame:
    feat = base.copy()
    feat["event_date"] = feat["snapshot_date"]
    feat["is_current"] = 1
    for col in ["model_overlap_count", "overlap_user_count", "overlap_internal_count", "overlap_tseries_count"]:
        if col not in feat.columns:
            feat[col] = 1 if col == "model_overlap_count" else 0
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
    model = bundle["model"]
    numeric = list(bundle.get("numeric_features") or [])
    categorical = list(bundle.get("categorical_features") or [])
    feat = _prepare_feature_frame(weekly, asof, numeric, categorical)
    feat["downside_risk_prob"] = model.predict_proba(feat)[:, 1] if not feat.empty else np.nan
    feat["downside_risk_tag"] = feat["downside_risk_prob"].map(downside_ai._risk_tag)
    keep = [
        "scope_key",
        "model_id",
        "ticker",
        "snapshot_date",
        "week_end",
        "downside_risk_prob",
        "downside_risk_tag",
    ]
    scored = weekly.merge(feat[[c for c in keep if c in feat.columns]], on=["scope_key", "model_id", "ticker", "snapshot_date", "week_end"], how="left")
    meta = {
        "model_path": str(model_path),
        "model_version": bundle.get("model_version"),
        "label": bundle.get("label"),
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
    tag = frame.get("downside_risk_tag", pd.Series(index=frame.index, dtype=object)).fillna("risk_unknown")
    if policy == "baseline":
        return base
    if policy == "risk_exit_cash":
        return base.where(~tag.eq("risk_exit_watch"), 0.0)
    if policy == "risk_caution_cash":
        return base.where(~tag.isin(["risk_exit_watch", "risk_caution"]), 0.0)
    if policy == "risk_tilt_cash":
        mult = tag.map({"risk_clear": 1.0, "risk_watch": 0.80, "risk_caution": 0.50, "risk_exit_watch": 0.20}).fillna(0.75)
        return base * mult
    if policy == "risk_tilt_renorm":
        mult = tag.map({"risk_clear": 1.10, "risk_watch": 0.85, "risk_caution": 0.55, "risk_exit_watch": 0.20}).fillna(0.75)
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
        tag = frame.get("downside_risk_tag", pd.Series(index=frame.index, dtype=object)).fillna("risk_unknown")
        ret = pd.to_numeric(frame["period_return"], errors="coerce")
        for policy in POLICIES:
            weights = _policy_weights(frame, policy)
            valid = frame.loc[ret.notna()].copy()
            valid_weights = weights.loc[valid.index]
            portfolio_return = float((valid["period_return"] * valid_weights).sum()) if not valid.empty else np.nan
            removed_weight = float(1.0 - weights.sum()) if policy != "risk_tilt_renorm" else 0.0
            perf_rows.append(
                {
                    "scope_key": scope_key,
                    "model_id": model_id,
                    "snapshot_date": snapshot_date,
                    "next_snapshot_date": next_snapshot_date,
                    "policy": policy,
                    "selected_count": int(len(frame)),
                    "priced_count": int(ret.notna().sum()),
                    "risk_exit_count": int(tag.eq("risk_exit_watch").sum()),
                    "risk_caution_count": int(tag.eq("risk_caution").sum()),
                    "risk_watch_count": int(tag.eq("risk_watch").sum()),
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
                        "downside_risk_prob",
                        "downside_risk_tag",
                    ]
                ]
            )
    return (
        pd.concat(holdings, ignore_index=True) if holdings else pd.DataFrame(),
        pd.DataFrame(perf_rows),
    )


def _nav_mdd(returns: pd.Series) -> float | None:
    r = pd.to_numeric(returns, errors="coerce").dropna()
    if r.empty:
        return None
    nav = (1.0 + r).cumprod()
    dd = nav / nav.cummax() - 1.0
    return round(float(dd.min()), 8)


def _summarize(perf: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if perf.empty:
        return pd.DataFrame()
    for keys, frame in perf.groupby(["scope_key", "model_id", "policy"], dropna=False):
        scope_key, model_id, policy = keys
        frame = frame.sort_values("snapshot_date")
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
                "avg_risk_exit_count": round(float(frame["risk_exit_count"].mean()), 4),
                "avg_risk_caution_count": round(float(frame["risk_caution_count"].mean()), 4),
                "avg_risk_watch_count": round(float(frame["risk_watch_count"].mean()), 4),
            }
        )
    return pd.DataFrame(rows).sort_values(["scope_key", "model_id", "policy"]).reset_index(drop=True)


def _write_report(asof: str, summary: pd.DataFrame, coverage: pd.DataFrame, meta: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / f"DOWNSIDE_RISK_AI_WEEKLY_OVERLAY_BACKTEST_{_token(asof)}.md"
    lines = [
        "# Downside Risk AI Weekly Overlay Backtest",
        "",
        f"- asof: {asof}",
        f"- overlay: {MODEL_CODE} / {MODEL_NAME_KO}",
        f"- model_version: `{meta.get('model_version')}`",
        "- scope: stock-only weekly rankings; ETF excluded",
        "- note: This is a research backtest, not production strategy replacement.",
        "",
        "## Coverage",
        "",
        "| scope | model | rows | periods | risk_exit | risk_caution | risk_watch | risk_clear |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in coverage.iterrows():
        lines.append(
            f"| {row['scope_key']} | {row['model_id']} | {int(row['rows'])} | {int(row['periods'])} | "
            f"{int(row.get('risk_exit_watch', 0))} | {int(row.get('risk_caution', 0))} | "
            f"{int(row.get('risk_watch', 0))} | {int(row.get('risk_clear', 0))} |"
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
            "- `risk_exit_cash`: sets `risk_exit_watch` positions to cash.",
            "- `risk_caution_cash`: sets `risk_exit_watch` and `risk_caution` positions to cash.",
            "- `risk_tilt_cash`: cuts risk weights but keeps unallocated weight in cash.",
            "- `risk_tilt_renorm`: cuts risk weights then renormalizes to full investment.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest AI-DOWNSIDE-RISK-V01 as a weekly risk overlay.")
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
        scored.groupby(["scope_key", "model_id", "downside_risk_tag"], dropna=False)
        .size()
        .reset_index(name="count")
        .pivot_table(index=["scope_key", "model_id"], columns="downside_risk_tag", values="count", fill_value=0, aggfunc="sum")
        .reset_index()
    )
    total = scored.groupby(["scope_key", "model_id"]).agg(rows=("ticker", "size"), periods=("snapshot_date", "nunique")).reset_index()
    coverage = total.merge(coverage, on=["scope_key", "model_id"], how="left").fillna(0)

    token = _token(asof)
    scored_path = out_dir / f"downside_risk_ai_weekly_overlay_scored_{token}.csv"
    holdings_path = out_dir / f"downside_risk_ai_weekly_overlay_holdings_{token}.csv"
    periods_path = out_dir / f"downside_risk_ai_weekly_overlay_periods_{token}.csv"
    summary_path = out_dir / f"downside_risk_ai_weekly_overlay_summary_{token}.csv"
    coverage_path = out_dir / f"downside_risk_ai_weekly_overlay_coverage_{token}.csv"
    json_path = out_dir / f"downside_risk_ai_weekly_overlay_backtest_{token}.json"
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
