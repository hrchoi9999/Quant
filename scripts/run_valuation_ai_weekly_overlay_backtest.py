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
SRC_DIR = ROOT / "src"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import run_ai_candidate_validation_weekly_rerank as weekly_cv  # noqa: E402
from models.valuation_ai.rule_score_engine import build_rule_scores  # noqa: E402


ADMIN_PAYLOAD = ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"
FEATURE_DIR = ROOT / r"reports\valuation_ai"
MODEL_DIR = ROOT / r"data\models\valuation_ai"
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

MODEL_CODE = "AI-GROWTH-VALUATION-V01"
MODEL_NAME_KO = "주가수준평가AI"

POLICIES = [
    "baseline",
    "valuation_avoid_cash",
    "valuation_overheated_cash",
    "valuation_tilt_cash",
    "valuation_tilt_renorm",
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
        raise SystemExit(f"no valuation AI model found under {MODEL_DIR}")
    return candidates[-1]


def _default_feature_path(asof: str) -> Path:
    exact = FEATURE_DIR / f"valuation_features_{_token(asof)}.csv"
    if exact.exists():
        return exact
    candidates = sorted(FEATURE_DIR.glob("valuation_features_*.csv"), key=lambda p: p.name)
    candidates = [p for p in candidates if p.stem.rsplit("_", 1)[-1] <= _token(asof)]
    if not candidates:
        raise SystemExit(f"no valuation feature file found under {FEATURE_DIR}")
    return candidates[-1]


def _load_features(feature_path: Path | None, asof: str) -> pd.DataFrame:
    feature_path = feature_path or _default_feature_path(asof)
    if not feature_path.exists():
        raise SystemExit(f"valuation feature file not found: {feature_path}")
    df = pd.read_csv(feature_path, dtype={"ticker": str}, parse_dates=["asof_date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df = df.loc[df["asof_date"] <= pd.Timestamp(asof)].copy()
    if df.empty:
        raise SystemExit("no valuation feature rows available before asof")
    return df.sort_values(["asof_date", "ticker"]).reset_index(drop=True)


def _score_features(features: pd.DataFrame, model_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    bundle = joblib.load(model_path)
    regressor = bundle["regressor"]
    predicted = pd.Series(regressor.predict(features), index=features.index)
    scored = build_rule_scores(features, predicted)
    scored["asof_date"] = pd.to_datetime(scored["asof_date"], errors="coerce")
    keep = [
        "asof_date",
        "ticker",
        "valuation_ai_score",
        "valuation_state",
        "predicted_excess_return_12m",
        "current_valuation_percentile",
        "valuation_safety_score",
        "growth_quality_score",
        "downside_risk_score",
        "confidence_score",
    ]
    meta = {
        "model_path": str(model_path),
        "model_version": bundle.get("model_version") or model_path.stem,
    }
    return scored[[c for c in keep if c in scored.columns]].copy(), meta


def _attach_valuation_scores(weekly: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    score_cols = [c for c in scored.columns if c not in {"ticker", "asof_date"}]
    score_by_ticker = {ticker: frame.sort_values("asof_date") for ticker, frame in scored.groupby("ticker", sort=False)}
    weekly = weekly.copy()
    weekly["snapshot_ts"] = pd.to_datetime(weekly["snapshot_date"], errors="coerce")
    for ticker, frame in weekly.groupby("ticker", sort=False):
        val = score_by_ticker.get(ticker)
        if val is None or val.empty:
            part = frame.copy()
            for col in ["valuation_asof_date", *score_cols]:
                part[col] = np.nan
            parts.append(part)
            continue
        left = frame.sort_values("snapshot_ts").copy()
        right = val.rename(columns={"asof_date": "valuation_asof_date"}).sort_values("valuation_asof_date")
        merged = pd.merge_asof(
            left,
            right,
            left_on="snapshot_ts",
            right_on="valuation_asof_date",
            direction="backward",
        )
        if "ticker_x" in merged.columns:
            merged = merged.rename(columns={"ticker_x": "ticker"}).drop(columns=[c for c in ["ticker_y"] if c in merged.columns])
        parts.append(merged)
    out = pd.concat(parts, ignore_index=True) if parts else weekly
    out["valuation_state"] = out["valuation_state"].fillna("OUT_OF_SCOPE_OR_MISSING")
    return out.drop(columns=["snapshot_ts"], errors="ignore")


def _initial_weights(frame: pd.DataFrame) -> pd.Series:
    w = pd.to_numeric(frame.get("weight"), errors="coerce")
    if w.notna().sum() and float(w.fillna(0).sum()) > 0:
        w = w.fillna(0).clip(lower=0)
        return w / w.sum()
    return pd.Series(1.0 / len(frame), index=frame.index)


def _policy_weights(frame: pd.DataFrame, policy: str) -> pd.Series:
    base = _initial_weights(frame)
    state = frame.get("valuation_state", pd.Series(index=frame.index, dtype=object)).fillna("OUT_OF_SCOPE_OR_MISSING")
    if policy == "baseline":
        return base
    if policy == "valuation_avoid_cash":
        return base.where(~state.eq("AVOID"), 0.0)
    if policy == "valuation_overheated_cash":
        return base.where(~state.isin(["AVOID", "OVERHEATED"]), 0.0)
    if policy == "valuation_tilt_cash":
        mult = state.map({"UNDERVALUED": 1.05, "FAIR": 1.0, "OVERHEATED": 0.75, "AVOID": 0.35}).fillna(0.75)
        return base * mult
    if policy == "valuation_tilt_renorm":
        mult = state.map({"UNDERVALUED": 1.15, "FAIR": 1.0, "OVERHEATED": 0.70, "AVOID": 0.30}).fillna(0.75)
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
        state = frame.get("valuation_state", pd.Series(index=frame.index, dtype=object)).fillna("OUT_OF_SCOPE_OR_MISSING")
        ret = pd.to_numeric(frame["period_return"], errors="coerce")
        for policy in POLICIES:
            weights = _policy_weights(frame, policy)
            valid = frame.loc[ret.notna()].copy()
            valid_weights = weights.loc[valid.index]
            portfolio_return = float((valid["period_return"] * valid_weights).sum()) if not valid.empty else np.nan
            removed_weight = float(1.0 - weights.sum()) if policy != "valuation_tilt_renorm" else 0.0
            perf_rows.append(
                {
                    "scope_key": scope_key,
                    "model_id": model_id,
                    "snapshot_date": snapshot_date,
                    "next_snapshot_date": next_snapshot_date,
                    "policy": policy,
                    "selected_count": int(len(frame)),
                    "priced_count": int(ret.notna().sum()),
                    "undervalued_count": int(state.eq("UNDERVALUED").sum()),
                    "fair_count": int(state.eq("FAIR").sum()),
                    "overheated_count": int(state.eq("OVERHEATED").sum()),
                    "avoid_count": int(state.eq("AVOID").sum()),
                    "missing_count": int(state.eq("OUT_OF_SCOPE_OR_MISSING").sum()),
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
                        "valuation_asof_date",
                        "valuation_ai_score",
                        "valuation_state",
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
                "avg_avoid_count": round(float(frame["avoid_count"].mean()), 4),
                "avg_overheated_count": round(float(frame["overheated_count"].mean()), 4),
                "avg_fair_count": round(float(frame["fair_count"].mean()), 4),
                "avg_undervalued_count": round(float(frame["undervalued_count"].mean()), 4),
            }
        )
    return pd.DataFrame(rows).sort_values(["scope_key", "model_id", "policy"]).reset_index(drop=True)


def _write_report(asof: str, summary: pd.DataFrame, coverage: pd.DataFrame, meta: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / f"VALUATION_AI_WEEKLY_OVERLAY_BACKTEST_{_token(asof)}.md"
    lines = [
        "# Valuation AI Weekly Overlay Backtest",
        "",
        f"- asof: {asof}",
        f"- overlay: {MODEL_CODE} / {MODEL_NAME_KO}",
        f"- model_version: `{meta.get('model_version')}`",
        "- scope: stock-only weekly rankings; ETF excluded",
        "- note: weekly strategy overlay test using latest monthly valuation score at each snapshot.",
        "",
        "## Coverage",
        "",
        "| scope | model | rows | periods | undervalued | fair | overheated | avoid | missing |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in coverage.iterrows():
        lines.append(
            f"| {row['scope_key']} | {row['model_id']} | {int(row['rows'])} | {int(row['periods'])} | "
            f"{int(row.get('UNDERVALUED', 0))} | {int(row.get('FAIR', 0))} | "
            f"{int(row.get('OVERHEATED', 0))} | {int(row.get('AVOID', 0))} | "
            f"{int(row.get('OUT_OF_SCOPE_OR_MISSING', 0))} |"
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
            "- `valuation_avoid_cash`: sets `AVOID` positions to cash.",
            "- `valuation_overheated_cash`: sets `AVOID` and `OVERHEATED` positions to cash.",
            "- `valuation_tilt_cash`: lowers expensive/risky valuation weights and keeps unallocated weight in cash.",
            "- `valuation_tilt_renorm`: valuation tilt then renormalizes to full investment.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest AI-GROWTH-VALUATION-V01 as a weekly valuation overlay.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--admin-payload", default=str(ADMIN_PAYLOAD))
    parser.add_argument("--feature-path")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    asof = str(args.asof)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    weekly = weekly_cv._load_weekly_rankings(Path(args.admin_payload), weekly_cv._load_etf_tickers())
    features = _load_features(Path(args.feature_path) if args.feature_path else None, asof)
    monthly_scores, meta = _score_features(features, _latest_model_path(asof))
    scored = _attach_valuation_scores(weekly, monthly_scores)
    scored = weekly_cv._attach_next_dates(scored, asof)
    scored = weekly_cv._load_price_returns(scored)
    holdings, perf = _run_backtest(scored)
    summary = _summarize(perf)

    coverage = (
        scored.groupby(["scope_key", "model_id", "valuation_state"], dropna=False)
        .size()
        .reset_index(name="count")
        .pivot_table(index=["scope_key", "model_id"], columns="valuation_state", values="count", fill_value=0, aggfunc="sum")
        .reset_index()
    )
    total = scored.groupby(["scope_key", "model_id"]).agg(rows=("ticker", "size"), periods=("snapshot_date", "nunique")).reset_index()
    coverage = total.merge(coverage, on=["scope_key", "model_id"], how="left").fillna(0)

    token = _token(asof)
    scored_path = out_dir / f"valuation_ai_weekly_overlay_scored_{token}.csv"
    holdings_path = out_dir / f"valuation_ai_weekly_overlay_holdings_{token}.csv"
    periods_path = out_dir / f"valuation_ai_weekly_overlay_periods_{token}.csv"
    summary_path = out_dir / f"valuation_ai_weekly_overlay_summary_{token}.csv"
    coverage_path = out_dir / f"valuation_ai_weekly_overlay_coverage_{token}.csv"
    json_path = out_dir / f"valuation_ai_weekly_overlay_backtest_{token}.json"
    monthly_scores_path = out_dir / f"valuation_ai_monthly_scores_for_backtest_{token}.csv"
    report_path = _write_report(asof, summary, coverage, meta, out_dir)

    monthly_scores.to_csv(monthly_scores_path, index=False, encoding="utf-8-sig")
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
        "monthly_score_rows": int(len(monthly_scores)),
        "scored_rows": int(len(scored)),
        "holdings_rows": int(len(holdings)),
        "period_rows": int(len(perf)),
        "outputs": {
            "monthly_scores_csv": str(monthly_scores_path),
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
