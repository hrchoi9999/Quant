from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(r"D:\Quant")
REPORT_DIR = ROOT / r"reports\c_series"


def _load_rotation_payload(asof: str) -> dict:
    path = REPORT_DIR / f"c_series_rotation_leadlag_{asof.replace('-', '')}.json"
    if not path.exists():
        raise FileNotFoundError(f"Rotation payload not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _strong_themes(payload: dict, current_top_n: int, trend_top_n: int) -> tuple[list[str], pd.DataFrame, pd.DataFrame]:
    latest_week = payload["recent_rotation_path"][-1]
    current_rows = pd.DataFrame(latest_week["leaders"])
    current_rows = current_rows.rename(columns={"theme": "source_theme", "weekly_return": "latest_week_return"})

    trend_rows = pd.DataFrame(payload["theme_rotation_summary"])
    trend_rows = trend_rows.sort_values(["last_4w_avg_return", "last_8w_avg_return"], ascending=False).head(trend_top_n)
    trend_rows = trend_rows.rename(columns={"theme": "source_theme"})

    current_top = current_rows.head(current_top_n)["source_theme"].tolist()
    trend_top = trend_rows["source_theme"].tolist()
    ordered = list(dict.fromkeys(current_top + trend_top))
    return ordered, current_rows, trend_rows


def _build_candidate_tables(
    payload: dict,
    strong_themes: list[str],
    min_lag: int,
    max_lag: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pairs = pd.DataFrame(payload["core_lead_lag_top"])
    if pairs.empty:
        return pd.DataFrame(), pd.DataFrame()

    filtered = pairs.loc[
        pairs["source_theme"].isin(strong_themes)
        & pairs["lag_weeks"].between(min_lag, max_lag)
    ].copy()
    if filtered.empty:
        return filtered, pd.DataFrame()

    filtered["source_is_strong"] = True
    filtered["target_is_current_strong"] = filtered["target_theme"].isin(strong_themes)

    grouped = (
        filtered.groupby("target_theme", as_index=False)
        .agg(
            support_theme_count=("source_theme", "nunique"),
            source_theme_list=("source_theme", lambda s: ", ".join(dict.fromkeys(s))),
            dominant_lag_weeks=("lag_weeks", lambda s: int(s.mode().iloc[0]) if not s.mode().empty else int(s.iloc[0])),
            avg_lead_lag_score=("lead_lag_score", "mean"),
            max_lead_lag_score=("lead_lag_score", "max"),
            avg_future_up_ratio=("target_future_up_ratio", "mean"),
            avg_future_excess_return=("target_future_excess_return", "mean"),
            avg_handoff_rate=("relative_rank_handoff_rate", "mean"),
            already_current_strong=("target_is_current_strong", "max"),
        )
    )
    breadth_norm = grouped["support_theme_count"] / grouped["support_theme_count"].max()
    grouped["followup_candidate_score"] = (
        grouped["max_lead_lag_score"] * 0.45
        + grouped["avg_lead_lag_score"] * 0.30
        + grouped["avg_future_up_ratio"] * 0.15
        + breadth_norm * 0.10
    )
    grouped = grouped.sort_values(
        ["already_current_strong", "followup_candidate_score", "support_theme_count", "avg_future_excess_return"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)
    return filtered, grouped


def _write_outputs(
    asof: str,
    payload: dict,
    strong_themes: list[str],
    current_rows: pd.DataFrame,
    trend_rows: pd.DataFrame,
    details: pd.DataFrame,
    grouped: pd.DataFrame,
) -> tuple[Path, Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    json_path = REPORT_DIR / f"c_series_theme_followup_candidates_{token}.json"
    csv_path = REPORT_DIR / f"c_series_theme_followup_candidates_{token}.csv"
    md_path = REPORT_DIR / f"c_series_theme_followup_candidates_{token}.md"

    if not grouped.empty:
        grouped.to_csv(csv_path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(csv_path, index=False, encoding="utf-8-sig")

    out = {
        "asof_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "strong_theme_definition": {
            "current_week_leaders": current_rows.to_dict(orient="records"),
            "recent_trend_leaders": trend_rows[
                ["source_theme", "last_4w_avg_return", "last_8w_avg_return", "rank_turnover"]
            ].to_dict(orient="records"),
            "strong_theme_union": strong_themes,
        },
        "candidate_count": int(len(grouped)),
        "followup_candidates": grouped.to_dict(orient="records"),
        "supporting_pairs": details.to_dict(orient="records"),
    }
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# C-series Theme Follow-up Candidates",
        "",
        f"- asof_date: {asof}",
        f"- generated_at: {out['generated_at']}",
        "- candidate_rule: current strong themes 기준 3~4주 lag 핵심 pair를 묶어 후행 가능성 테마를 집계",
        "",
        "## Current Strong Themes",
        "",
    ]
    for row in current_rows.to_dict(orient="records"):
        lines.append(f"- current leader: {row['source_theme']} ({row['latest_week_return']:+.2%})")
    for row in trend_rows[["source_theme", "last_4w_avg_return", "last_8w_avg_return"]].to_dict(orient="records"):
        lines.append(
            f"- trend leader: {row['source_theme']} (4w_avg={row['last_4w_avg_return']:+.2%}, 8w_avg={row['last_8w_avg_return']:+.2%})"
        )

    lines += ["", "## Follow-up Candidate Table", ""]
    if grouped.empty:
        lines.append("- no candidates")
    else:
        for row in grouped.head(20).to_dict(orient="records"):
            strong_flag = "yes" if bool(row["already_current_strong"]) else "no"
            lines.append(
                "- "
                f"{row['target_theme']}: score={row['followup_candidate_score']:.4f}, "
                f"support_count={int(row['support_theme_count'])}, lag={int(row['dominant_lag_weeks'])}w, "
                f"future_up={row['avg_future_up_ratio']:.2%}, future_excess={row['avg_future_excess_return']:+.2%}, "
                f"already_current_strong={strong_flag}, supports=[{row['source_theme_list']}]"
            )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, csv_path, md_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Build theme-level 3-4 week follow-up candidate table from C-series lead-lag report.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument("--current-top-n", type=int, default=3)
    ap.add_argument("--trend-top-n", type=int, default=8)
    ap.add_argument("--min-lag", type=int, default=3)
    ap.add_argument("--max-lag", type=int, default=4)
    args = ap.parse_args()

    payload = _load_rotation_payload(args.asof)
    strong_themes, current_rows, trend_rows = _strong_themes(payload, args.current_top_n, args.trend_top_n)
    details, grouped = _build_candidate_tables(payload, strong_themes, args.min_lag, args.max_lag)
    json_path, csv_path, md_path = _write_outputs(
        args.asof, payload, strong_themes, current_rows, trend_rows, details, grouped
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "asof": args.asof,
                "strong_theme_count": len(strong_themes),
                "candidate_count": int(len(grouped)),
                "json_report": str(json_path),
                "csv_report": str(csv_path),
                "md_report": str(md_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
