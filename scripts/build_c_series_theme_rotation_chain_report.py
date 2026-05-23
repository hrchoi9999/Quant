from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from analyze_c_series_rotation_leadlag import (
    _build_theme_weekly_returns,
    _compute_lead_lag_pairs,
    _filter_core_rotation_themes,
    _load_close_panel,
    _load_theme_map,
)


ROOT = Path(r"D:\Quant")
CLASS_DB = ROOT / r"data\db\security_classification.db"
C_DB = ROOT / r"data\db\cseries_relationship.db"
REPORT_DIR = ROOT / r"reports\c_series"


def _load_followup_payload(asof: str) -> dict[str, Any]:
    path = REPORT_DIR / f"c_series_theme_followup_candidates_{asof.replace('-', '')}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing followup payload: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _strong_theme_order(followup_payload: dict[str, Any]) -> list[str]:
    current = [row["source_theme"] for row in followup_payload["strong_theme_definition"]["current_week_leaders"]]
    trend = [row["source_theme"] for row in followup_payload["strong_theme_definition"]["recent_trend_leaders"]]
    return list(dict.fromkeys(current + trend))


def _load_member_frame(asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(CLASS_DB)) as con_cls, sqlite3.connect(str(C_DB)) as con_c:
        base = pd.read_sql_query(
            """
            SELECT ticker, name, asset_type, theme_bucket, theme_name_kr
            FROM security_classification_master
            WHERE asof_date = ?
              AND is_active = 1
            """,
            con_cls,
            params=[asof],
            dtype={"ticker": str},
        )
        stats = pd.read_sql_query(
            """
            SELECT ticker, weekly_return, liquidity_20d_value, close
            FROM c_return_series
            WHERE asof_date = ?
            """,
            con_c,
            params=[asof],
            dtype={"ticker": str},
        )
    base["ticker"] = base["ticker"].str.zfill(6)
    stats["ticker"] = stats["ticker"].str.zfill(6)
    out = base.merge(stats, on="ticker", how="left")
    out["weekly_return"] = pd.to_numeric(out["weekly_return"], errors="coerce")
    out["liquidity_20d_value"] = pd.to_numeric(out["liquidity_20d_value"], errors="coerce")
    return out


def _pick_pairs(
    source_theme: str,
    pairs_by_source: dict[str, list[dict[str, Any]]],
    excluded: set[str],
    top_n: int,
    allow_fallback: bool = True,
) -> list[dict[str, Any]]:
    rows = pairs_by_source.get(source_theme, [])
    picked = [row for row in rows if row["target_theme"] not in excluded][:top_n]
    if picked or not allow_fallback:
        return picked
    return rows[:top_n]


def _theme_metric_map(followup_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = followup_payload["strong_theme_definition"]["recent_trend_leaders"]
    return {row["source_theme"]: row for row in rows}


def _current_leader_map(followup_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = followup_payload["strong_theme_definition"]["current_week_leaders"]
    return {row["source_theme"]: row for row in rows}


def _build_chain_rows(
    strong_themes: list[str],
    pairs_by_source: dict[str, list[dict[str, Any]]],
    trend_map: dict[str, dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    top_followups: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    strong_set = set(strong_themes)
    for source in strong_themes:
        first_layer = _pick_pairs(source, pairs_by_source, strong_set | {source}, top_followups, allow_fallback=False)
        if not first_layer:
            first_layer = _pick_pairs(source, pairs_by_source, {source}, top_followups, allow_fallback=True)
        for first in first_layer:
            follow = first["target_theme"]
            second_layer = _pick_pairs(follow, pairs_by_source, {source, follow}, 1, allow_fallback=True)
            second = second_layer[0] if second_layer else None
            row = {
                "current_theme": source,
                "current_latest_week_return": current_map.get(source, {}).get("latest_week_return"),
                "current_last_4w_avg_return": trend_map.get(source, {}).get("last_4w_avg_return"),
                "current_last_8w_avg_return": trend_map.get(source, {}).get("last_8w_avg_return"),
                "followup_theme": follow,
                "followup_lag_weeks": first["lag_weeks"],
                "followup_lead_lag_score": first["lead_lag_score"],
                "followup_future_up_ratio": first["target_future_up_ratio"],
                "followup_future_excess_return": first["target_future_excess_return"],
                "followup_is_current_strong": follow in strong_set,
                "next_theme": second["target_theme"] if second else None,
                "next_lag_weeks": second["lag_weeks"] if second else None,
                "next_lead_lag_score": second["lead_lag_score"] if second else None,
                "next_future_up_ratio": second["target_future_up_ratio"] if second else None,
                "next_future_excess_return": second["target_future_excess_return"] if second else None,
            }
            rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["followup_is_current_strong", "followup_lead_lag_score", "next_lead_lag_score"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def _build_member_sections(
    member_df: pd.DataFrame,
    chain_df: pd.DataFrame,
    top_members: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if chain_df.empty:
        return pd.DataFrame(), []
    themes: list[str] = []
    for col in ["current_theme", "followup_theme", "next_theme"]:
        vals = chain_df[col].dropna().tolist()
        themes.extend(vals)
    ordered_themes = list(dict.fromkeys(themes))

    full_rows: list[pd.DataFrame] = []
    sections: list[dict[str, Any]] = []
    for theme in ordered_themes:
        sub = member_df.loc[member_df["theme_bucket"] == theme].copy()
        if sub.empty:
            continue
        sub = sub.sort_values(
            ["asset_type", "liquidity_20d_value", "weekly_return", "ticker"],
            ascending=[True, False, False, True],
        )
        full_rows.append(sub.assign(report_theme=theme))
        rep = sub.head(top_members).copy()
        rep["weekly_return"] = rep["weekly_return"].round(4)
        rep["liquidity_20d_value"] = rep["liquidity_20d_value"].round(0)
        sections.append(
            {
                "theme": theme,
                "theme_name_kr": rep["theme_name_kr"].iloc[0],
                "member_count": int(len(sub)),
                "representatives": rep[
                    ["ticker", "name", "asset_type", "weekly_return", "liquidity_20d_value"]
                ].to_dict(orient="records"),
            }
        )
    full_df = pd.concat(full_rows, ignore_index=True) if full_rows else pd.DataFrame()
    return full_df, sections


def _write_outputs(
    asof: str,
    chain_df: pd.DataFrame,
    member_full_df: pd.DataFrame,
    member_sections: list[dict[str, Any]],
) -> tuple[Path, Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    csv_path = REPORT_DIR / f"c_series_theme_rotation_chain_{token}.csv"
    json_path = REPORT_DIR / f"c_series_theme_rotation_chain_{token}.json"
    md_path = REPORT_DIR / f"c_series_theme_rotation_chain_{token}.md"

    if not chain_df.empty:
        chain_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(csv_path, index=False, encoding="utf-8-sig")

    member_csv_path = REPORT_DIR / f"c_series_theme_rotation_chain_members_{token}.csv"
    if not member_full_df.empty:
        member_full_df.to_csv(member_csv_path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(member_csv_path, index=False, encoding="utf-8-sig")

    payload = {
        "asof_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "chain_rows": chain_df.to_dict(orient="records"),
        "member_sections": member_sections,
        "member_csv": str(member_csv_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# C-series Theme Rotation Chain",
        "",
        f"- asof_date: {asof}",
        f"- generated_at: {payload['generated_at']}",
        f"- chain_row_count: {len(chain_df)}",
        f"- member_csv: {member_csv_path}",
        "",
        "## Rotation Chain Table",
        "",
    ]
    if chain_df.empty:
        lines.append("- no chain rows")
    else:
        for row in chain_df.to_dict(orient="records"):
            cur_latest = row["current_latest_week_return"]
            cur_4w = row["current_last_4w_avg_return"]
            next_lag = row["next_lag_weeks"]
            next_score = row["next_lead_lag_score"]
            cur_latest_text = "n/a" if pd.isna(cur_latest) else f"{cur_latest:+.2%}"
            cur_4w_text = "n/a" if pd.isna(cur_4w) else f"{cur_4w:+.2%}"
            next_lag_text = "" if pd.isna(next_lag) else str(int(next_lag))
            next_score_text = "" if pd.isna(next_score) else f"{next_score:.4f}"
            lines.append(
                "- "
                f"{row['current_theme']} "
                f"(latest={cur_latest_text}, 4w={cur_4w_text}) "
                f"-> {row['followup_theme']} "
                f"(lag={int(row['followup_lag_weeks'])}w, score={row['followup_lead_lag_score']:.4f}, "
                f"future_up={row['followup_future_up_ratio']:.2%}, future_excess={row['followup_future_excess_return']:+.2%}) "
                f"-> {row['next_theme'] or '-'} "
                f"(lag={next_lag_text}w, score={next_score_text})"
            )

    lines += ["", "## Theme Members", ""]
    for section in member_sections:
        lines.append(f"### {section['theme']} ({section['theme_name_kr']}, members={section['member_count']})")
        lines.append("")
        for rep in section["representatives"]:
            wr = rep["weekly_return"]
            wr_text = "n/a" if pd.isna(wr) else f"{wr:+.2%}"
            liq = rep["liquidity_20d_value"]
            liq_text = "n/a" if pd.isna(liq) else f"{liq:,.0f}"
            lines.append(
                f"- {rep['ticker']} {rep['name']} [{rep['asset_type']}] weekly={wr_text}, liquidity20d={liq_text}"
            )
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, json_path, md_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Build theme rotation chain report with theme member lists.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument("--top-followups", type=int, default=2)
    ap.add_argument("--top-members", type=int, default=12)
    args = ap.parse_args()

    followup_payload = _load_followup_payload(args.asof)
    strong_themes = _strong_theme_order(followup_payload)

    meta = _load_theme_map(args.asof)
    close_panel = _load_close_panel(meta["ticker"].tolist(), args.asof)
    theme_weekly_all, member_counts, _week_labels = _build_theme_weekly_returns(meta, close_panel)
    theme_weekly_core = _filter_core_rotation_themes(theme_weekly_all.dropna(axis=1, how="all"), member_counts)
    core_pairs = _compute_lead_lag_pairs(theme_weekly_core)
    pairs_by_source: dict[str, list[dict[str, Any]]] = {}
    for pair in core_pairs:
        pairs_by_source.setdefault(pair.source_theme, []).append(pair.__dict__)

    trend_map = _theme_metric_map(followup_payload)
    current_map = _current_leader_map(followup_payload)
    chain_df = _build_chain_rows(
        strong_themes=strong_themes,
        pairs_by_source=pairs_by_source,
        trend_map=trend_map,
        current_map=current_map,
        top_followups=args.top_followups,
    )

    member_df = _load_member_frame(args.asof)
    member_full_df, member_sections = _build_member_sections(member_df, chain_df, args.top_members)
    csv_path, json_path, md_path = _write_outputs(args.asof, chain_df, member_full_df, member_sections)

    print(
        json.dumps(
            {
                "status": "ok",
                "asof": args.asof,
                "chain_rows": int(len(chain_df)),
                "theme_count_in_report": int(len(member_sections)),
                "csv_report": str(csv_path),
                "json_report": str(json_path),
                "md_report": str(md_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
