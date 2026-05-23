from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ADMIN_PAYLOAD = ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"
ETF_UNIVERSE = ROOT / r"data\universe\universe_etf_master_latest.csv"
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

HORIZONS = ["1w", "2w", "1m", "2m", "3m", "6m", "1y"]


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _zfill_ticker(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"ticker": str, "security_code": str})


def _load_etf_tickers(path: Path) -> set[str]:
    if not path.exists():
        return set()
    df = pd.read_csv(path, dtype={"ticker": str})
    if "ticker" not in df.columns:
        return set()
    return {_zfill_ticker(x) for x in df["ticker"].dropna().tolist()}


def _flatten_event_rows(payload_path: Path, etf_tickers: set[str]) -> pd.DataFrame:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []

    for section in ("user_models", "internal_models", "tseries_models"):
        for item in payload.get(section, []) or []:
            ticker = _zfill_ticker(item.get("security_code"))
            model_id = item.get("model_code") or item.get("model_key") or item.get("service_profile")
            scope_key = item.get("scope") or ("tseries" if section == "tseries_models" else section.replace("_models", ""))
            asset_group = str(item.get("asset_group") or "").lower()
            is_etf = ticker in etf_tickers or asset_group == "etf" or str(model_id).upper() == "T-ETF-V01"
            if is_etf:
                continue

            row: dict[str, Any] = {
                "source_section": section,
                "scope_key": scope_key,
                "model_id": model_id,
                "ticker": ticker,
                "name": item.get("display_name"),
                "event_type": item.get("event_type"),
                "event_date": item.get("event_date"),
                "week_end": item.get("week_end"),
                "snapshot_date": item.get("snapshot_date") or item.get("weekly_snapshot_date"),
                "rank_no": item.get("rank_no") or item.get("weekly_rank_no"),
                "base_score": item.get("score") or item.get("weekly_score"),
                "base_weight": item.get("weight") or item.get("weekly_weight") or item.get("curr_weight"),
                "candidate_bucket": item.get("candidate_bucket") or item.get("weekly_candidate_bucket"),
                "is_current": item.get("is_current"),
                "latest_price_date": item.get("latest_price_date"),
                "current_return": item.get("current_return"),
            }

            forward_returns = item.get("forward_returns") or {}
            forward_risk = item.get("forward_risk_metrics") or {}
            for horizon in HORIZONS:
                row[f"ret_{horizon}"] = forward_returns.get(horizon)
                metrics = forward_risk.get(horizon) or {}
                row[f"mdd_{horizon}"] = metrics.get("mdd")
                row[f"sharpe_{horizon}"] = metrics.get("sharpe")
            rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["ticker"] = out["ticker"].map(_zfill_ticker)
    out["event_date"] = out["event_date"].astype(str)
    out["snapshot_date"] = out["snapshot_date"].astype(str)
    return out


def _merge_candidate_validation(events: pd.DataFrame, asof: str) -> pd.DataFrame:
    path = ROOT / "reports" / "ai_overlay_v01" / f"ai_overlay_shadow_scores_{_token(asof)}.csv"
    scores = _read_csv_if_exists(path)
    if scores.empty:
        return events

    cols = [
        "scope_key",
        "model_id",
        "ticker",
        "event_date",
        "ai_quality_prob",
        "ai_risk_prob",
        "ai_shadow_decision",
        "ai_model_specific_quality_prob",
        "ai_model_specific_risk_prob",
        "ai_model_specific_tag",
    ]
    scores = scores[[c for c in cols if c in scores.columns]].copy()
    scores["ticker"] = scores["ticker"].map(_zfill_ticker)
    scores["event_date"] = scores["event_date"].astype(str)
    scores = scores.drop_duplicates(["scope_key", "model_id", "ticker", "event_date"], keep="last")
    return events.merge(scores, on=["scope_key", "model_id", "ticker", "event_date"], how="left")


def _merge_downside(events: pd.DataFrame, asof: str) -> pd.DataFrame:
    path = ROOT / "reports" / "downside_risk_ai_v01" / f"downside_risk_ai_current_scores_{_token(asof)}.csv"
    scores = _read_csv_if_exists(path)
    if scores.empty:
        return events

    cols = [
        "scope_key",
        "model_id",
        "ticker",
        "event_date",
        "downside_risk_prob",
        "downside_risk_tag",
        "theme_bucket",
        "sector_bucket",
    ]
    scores = scores[[c for c in cols if c in scores.columns]].copy()
    scores["ticker"] = scores["ticker"].map(_zfill_ticker)
    scores["event_date"] = scores["event_date"].astype(str)
    scores = scores.drop_duplicates(["scope_key", "model_id", "ticker", "event_date"], keep="last")
    return events.merge(scores, on=["scope_key", "model_id", "ticker", "event_date"], how="left")


def _merge_rank_delta(events: pd.DataFrame, asof: str) -> pd.DataFrame:
    path = ROOT / "reports" / "candidate_rank_delta_ai_v01" / f"candidate_rank_delta_ai_current_scores_{_token(asof)}.csv"
    scores = _read_csv_if_exists(path)
    if scores.empty:
        return events

    cols = [
        "scope_key",
        "model_id",
        "ticker",
        "event_date",
        "rank_drop_prob",
        "retained_rank_upgrade_prob",
        "retained_rank_downgrade_prob",
        "retained_rank_change_score",
        "rank_delta_score",
        "rank_delta_decision",
        "theme_bucket",
        "sector_bucket",
    ]
    scores = scores[[c for c in cols if c in scores.columns]].copy()
    scores["ticker"] = scores["ticker"].map(_zfill_ticker)
    scores["event_date"] = scores["event_date"].astype(str)
    scores = scores.drop_duplicates(["scope_key", "model_id", "ticker", "event_date"], keep="last")
    return events.merge(scores, on=["scope_key", "model_id", "ticker", "event_date"], how="left", suffixes=("", "_rank"))


def _merge_valuation(events: pd.DataFrame, asof: str) -> pd.DataFrame:
    path = ROOT / "reports" / "valuation_ai" / f"valuation_ai_challenger_current_candidates_{_token(asof)}.csv"
    scores = _read_csv_if_exists(path)
    if scores.empty:
        return events

    cols = [
        "scope",
        "model_code",
        "security_code",
        "snapshot_date",
        "champion_state",
        "champion_score",
        "challenger_state",
        "challenger_score",
        "challenger_change_label",
        "risk_state",
        "risk_score",
        "risk_tag",
        "qm_quantmarket_theme_bucket",
        "qm_theme_mapping_confidence",
    ]
    scores = scores[[c for c in cols if c in scores.columns]].copy()
    scores = scores.rename(
        columns={
            "scope": "scope_key",
            "model_code": "model_id",
            "security_code": "ticker",
        }
    )
    scores["ticker"] = scores["ticker"].map(_zfill_ticker)
    scores["snapshot_date"] = scores["snapshot_date"].astype(str)
    scores = scores.drop_duplicates(["scope_key", "model_id", "ticker", "snapshot_date"], keep="last")
    return events.merge(scores, on=["scope_key", "model_id", "ticker", "snapshot_date"], how="left")


def _merge_theme(events: pd.DataFrame, asof: str) -> pd.DataFrame:
    path = ROOT / "reports" / "theme_persistence_ai_v01" / f"theme_persistence_ai_current_scores_{_token(asof)}.csv"
    scores = _read_csv_if_exists(path)
    if scores.empty or "theme_bucket" not in events.columns:
        return events

    cols = [
        "quant_theme_bucket",
        "theme_continue_prob",
        "theme_fade_prob",
        "theme_persistence_score",
        "theme_persistence_tag",
    ]
    scores = scores[[c for c in cols if c in scores.columns]].copy()
    scores = scores.rename(columns={"quant_theme_bucket": "theme_bucket"})
    scores = scores.drop_duplicates(["theme_bucket"], keep="last")
    return events.merge(scores, on="theme_bucket", how="left")


def _bucketize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["candidate_validation_bucket"] = out.get("ai_model_specific_tag", pd.Series(index=out.index, dtype=object)).fillna(
        out.get("ai_shadow_decision", pd.Series(index=out.index, dtype=object))
    )
    out["candidate_validation_bucket"] = out["candidate_validation_bucket"].fillna("no_score")
    out["downside_risk_bucket"] = out.get("downside_risk_tag", pd.Series(index=out.index, dtype=object)).fillna("no_score")
    out["rank_delta_bucket"] = out.get("rank_delta_decision", pd.Series(index=out.index, dtype=object)).fillna("no_score")
    out["valuation_bucket"] = out.get("challenger_state", pd.Series(index=out.index, dtype=object)).fillna(
        out.get("champion_state", pd.Series(index=out.index, dtype=object))
    )
    out["valuation_bucket"] = out["valuation_bucket"].fillna("no_score")
    out["valuation_risk_bucket"] = out.get("risk_tag", pd.Series(index=out.index, dtype=object)).fillna("no_score")
    out["theme_bucket_signal"] = out.get("theme_persistence_tag", pd.Series(index=out.index, dtype=object)).fillna("no_score")
    return out


def _policy_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["policy_downside_risk_guardrail"] = "missing"
    out.loc[out["downside_risk_bucket"].isin(["risk_clear", "risk_watch"]), "policy_downside_risk_guardrail"] = "selected"
    out.loc[out["downside_risk_bucket"].isin(["risk_caution", "risk_exit_watch"]), "policy_downside_risk_guardrail"] = "excluded"

    out["policy_rank_delta_guardrail"] = "missing"
    out.loc[
        out["rank_delta_bucket"].isin(["rank_upgrade_candidate", "rank_upgrade_watch", "rank_hold"]),
        "policy_rank_delta_guardrail",
    ] = "selected"
    out.loc[
        out["rank_delta_bucket"].isin(
            ["rank_drop_candidate", "rank_drop_watch", "rank_downgrade_candidate", "rank_downgrade_watch"]
        ),
        "policy_rank_delta_guardrail",
    ] = "excluded"

    out["policy_candidate_validation_guardrail"] = "missing"
    out.loc[
        out["candidate_validation_bucket"].isin(["MS_CONFIRM", "AI_CONFIRM"]),
        "policy_candidate_validation_guardrail",
    ] = "selected"
    out.loc[
        out["candidate_validation_bucket"].isin(
            ["MS_RISK", "MS_RISK_REVIEW", "MS_FALLBACK", "MS_FALLBACK_COMMON", "AI_RISK"]
        ),
        "policy_candidate_validation_guardrail",
    ] = "excluded"
    out.loc[
        out["candidate_validation_bucket"].isin(["MS_OBSERVE", "AI_OBSERVE", "OBSERVE", "AI_WATCH"]),
        "policy_candidate_validation_guardrail",
    ] = "neutral"

    out["policy_valuation_guardrail"] = "missing"
    out.loc[out["valuation_bucket"].isin(["UNDERVALUED", "FAIR"]), "policy_valuation_guardrail"] = "selected"
    out.loc[out["valuation_bucket"].isin(["OVERHEATED", "AVOID"]), "policy_valuation_guardrail"] = "excluded"
    out.loc[out["valuation_risk_bucket"].isin(["risk_caution", "risk_watch"]), "policy_valuation_guardrail"] = "excluded"

    out["policy_theme_guardrail"] = "missing"
    out.loc[out["theme_bucket_signal"].isin(["theme_persist_strong", "theme_persist_watch"]), "policy_theme_guardrail"] = "selected"
    out.loc[out["theme_bucket_signal"].isin(["theme_fade_watch", "theme_fade_risk"]), "policy_theme_guardrail"] = "excluded"
    out.loc[out["theme_bucket_signal"].eq("theme_neutral"), "policy_theme_guardrail"] = "neutral"

    out["policy_risk_rank_combo"] = "missing"
    risk_known = out["policy_downside_risk_guardrail"].ne("missing")
    rank_known = out["policy_rank_delta_guardrail"].ne("missing")
    out.loc[risk_known | rank_known, "policy_risk_rank_combo"] = "selected"
    out.loc[
        out["policy_downside_risk_guardrail"].eq("excluded") | out["policy_rank_delta_guardrail"].eq("excluded"),
        "policy_risk_rank_combo",
    ] = "excluded"

    out["policy_balanced_combo"] = "missing"
    any_known = (
        out["policy_downside_risk_guardrail"].ne("missing")
        | out["policy_rank_delta_guardrail"].ne("missing")
        | out["policy_candidate_validation_guardrail"].ne("missing")
    )
    any_bad = (
        out["policy_downside_risk_guardrail"].eq("excluded")
        | out["policy_rank_delta_guardrail"].eq("excluded")
        | out["policy_candidate_validation_guardrail"].eq("excluded")
    )
    any_good = (
        out["policy_downside_risk_guardrail"].eq("selected")
        | out["policy_rank_delta_guardrail"].eq("selected")
        | out["policy_candidate_validation_guardrail"].eq("selected")
    )
    out.loc[any_known, "policy_balanced_combo"] = "neutral"
    out.loc[any_good & ~any_bad, "policy_balanced_combo"] = "selected"
    out.loc[any_bad, "policy_balanced_combo"] = "excluded"

    return out


def _summarize(df: pd.DataFrame, group_cols: list[str], overlay_name: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if df.empty:
        return pd.DataFrame()

    for keys, frame in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        base = dict(zip(group_cols, keys))
        for horizon in HORIZONS:
            ret_col = f"ret_{horizon}"
            mdd_col = f"mdd_{horizon}"
            ret = pd.to_numeric(frame.get(ret_col), errors="coerce")
            mdd = pd.to_numeric(frame.get(mdd_col), errors="coerce") if mdd_col in frame.columns else pd.Series(dtype=float)
            valid = ret.dropna()
            row = {
                "overlay": overlay_name,
                **base,
                "horizon": horizon,
                "event_rows": int(len(frame)),
                "sample_count": int(valid.shape[0]),
                "avg_return": round(float(valid.mean()), 6) if not valid.empty else None,
                "median_return": round(float(valid.median()), 6) if not valid.empty else None,
                "win_rate": round(float((valid > 0).mean()), 6) if not valid.empty else None,
                "avg_mdd": round(float(mdd.dropna().mean()), 6) if not mdd.dropna().empty else None,
                "worst_return": round(float(valid.min()), 6) if not valid.empty else None,
                "best_return": round(float(valid.max()), 6) if not valid.empty else None,
            }
            rows.append(row)
    return pd.DataFrame(rows)


def _coverage(df: pd.DataFrame) -> list[dict[str, Any]]:
    fields = {
        "candidate_validation": "candidate_validation_bucket",
        "downside_risk": "downside_risk_bucket",
        "rank_delta": "rank_delta_bucket",
        "valuation": "valuation_bucket",
        "theme_persistence": "theme_bucket_signal",
    }
    rows = []
    total = len(df)
    for name, col in fields.items():
        if col not in df.columns:
            rows.append({"overlay": name, "covered_rows": 0, "total_rows": total, "coverage": 0.0})
            continue
        covered = int(df[col].ne("no_score").sum())
        rows.append(
            {
                "overlay": name,
                "covered_rows": covered,
                "total_rows": total,
                "coverage": round(covered / total, 6) if total else 0.0,
            }
        )
    return rows


def _write_report(asof: str, detail: pd.DataFrame, coverage: list[dict[str, Any]], summary: pd.DataFrame, policy: pd.DataFrame, out_dir: Path) -> Path:
    path = out_dir / f"AI_OVERLAY_EVENT_ABLATION_{_token(asof)}.md"
    lines = [
        "# AI Overlay Event-Level Ablation",
        "",
        f"- asof: {asof}",
        f"- event_rows: {len(detail):,}",
        "- scope: stock-only S/T/I/C and user/internal candidates; ETF excluded",
        "- purpose: Stage 1 fast ablation before weekly rerank / portfolio NAV backtest",
        "",
        "## Coverage",
        "",
        "| overlay | covered rows | total rows | coverage |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in coverage:
        lines.append(f"| {row['overlay']} | {row['covered_rows']} | {row['total_rows']} | {row['coverage']:.2%} |")

    lines.extend(["", "## Policy Snapshot - 1M", "", "| policy | bucket | sample | avg return | win rate | avg MDD |"])
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    if not policy.empty:
        view = policy.loc[policy["horizon"].eq("1m")].copy()
        view = view.sort_values(["overlay", "bucket"])
        for _, row in view.iterrows():
            avg_return = "" if pd.isna(row["avg_return"]) else f"{row['avg_return']:.2%}"
            win_rate = "" if pd.isna(row["win_rate"]) else f"{row['win_rate']:.2%}"
            avg_mdd = "" if pd.isna(row["avg_mdd"]) else f"{row['avg_mdd']:.2%}"
            lines.append(
                f"| {row['overlay']} | {row['bucket']} | {int(row['sample_count'])} | "
                f"{avg_return} | {win_rate} | {avg_mdd} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- This is not a portfolio backtest.",
            "- Current-only AI score files may have low coverage; coverage must be checked before interpreting performance.",
            "- Forward horizons with insufficient elapsed time remain empty and should be treated as N/A.",
            "- Policies that improve MDD/worst return move to weekly rerank simulation.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Stage 1 AI overlay event-level ablation.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument("--admin-payload", default=str(ADMIN_PAYLOAD))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    asof = str(args.asof)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    etf_tickers = _load_etf_tickers(ETF_UNIVERSE)
    events = _flatten_event_rows(Path(args.admin_payload), etf_tickers)
    events = _merge_candidate_validation(events, asof)
    events = _merge_downside(events, asof)
    events = _merge_rank_delta(events, asof)
    events = _merge_valuation(events, asof)
    events = _merge_theme(events, asof)
    detail = _policy_columns(_bucketize(events))

    overlay_frames = []
    for overlay, col in [
        ("candidate_validation", "candidate_validation_bucket"),
        ("downside_risk", "downside_risk_bucket"),
        ("rank_delta", "rank_delta_bucket"),
        ("valuation", "valuation_bucket"),
        ("valuation_risk", "valuation_risk_bucket"),
        ("theme_persistence", "theme_bucket_signal"),
    ]:
        overlay_frames.append(_summarize(detail, [col], overlay).rename(columns={col: "bucket"}))
        overlay_frames.append(_summarize(detail, ["model_id", col], overlay).rename(columns={col: "bucket"}))

    policy_frames = []
    for policy_col in [
        "policy_downside_risk_guardrail",
        "policy_rank_delta_guardrail",
        "policy_candidate_validation_guardrail",
        "policy_valuation_guardrail",
        "policy_theme_guardrail",
        "policy_risk_rank_combo",
        "policy_balanced_combo",
    ]:
        policy_frames.append(_summarize(detail, [policy_col], policy_col.replace("policy_", "")).rename(columns={policy_col: "bucket"}))

    summary = pd.concat([x for x in overlay_frames if not x.empty], ignore_index=True) if overlay_frames else pd.DataFrame()
    policy = pd.concat([x for x in policy_frames if not x.empty], ignore_index=True) if policy_frames else pd.DataFrame()
    coverage = _coverage(detail)

    detail_path = out_dir / f"ai_overlay_event_ablation_detail_{_token(asof)}.csv"
    summary_path = out_dir / f"ai_overlay_event_ablation_summary_{_token(asof)}.csv"
    policy_path = out_dir / f"ai_overlay_event_ablation_policy_{_token(asof)}.csv"
    json_path = out_dir / f"ai_overlay_event_ablation_{_token(asof)}.json"

    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    policy.to_csv(policy_path, index=False, encoding="utf-8-sig")
    report_path = _write_report(asof, detail, coverage, summary, policy, out_dir)

    payload = {
        "status": "ok",
        "asof": asof,
        "event_rows": int(len(detail)),
        "coverage": coverage,
        "outputs": {
            "detail_csv": str(detail_path),
            "summary_csv": str(summary_path),
            "policy_csv": str(policy_path),
            "json": str(json_path),
            "markdown": str(report_path),
        },
        "notes": [
            "Stage 1 event-level ablation only; not a portfolio NAV backtest.",
            "ETF rows are excluded.",
            "Low-coverage overlays should not be interpreted as production-ready.",
        ],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
