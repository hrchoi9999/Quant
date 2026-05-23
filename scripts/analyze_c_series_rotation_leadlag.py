from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
CLASS_DB = ROOT / r"data\db\security_classification.db"
REPORT_DIR = ROOT / r"reports\c_series"

LOOKBACK_DAYS = 520
MIN_THEME_MEMBERS = 5
MIN_PAIR_OBS = 26
MAX_LAG_WEEKS = 4

GLOBAL_DEFENSIVE_THEMES = {
    "bond_cash",
    "commodity_fx",
    "inverse_leverage",
    "equity_us",
    "equity_china",
    "equity_europe",
    "equity_emerging",
    "equity_global",
    "multi_asset_allocation",
    "real_estate_reit",
}


@dataclass
class LeadLagPair:
    source_theme: str
    target_theme: str
    lag_weeks: int
    lagged_corr: float
    source_top_quartile_hit_ratio: float
    target_future_up_ratio: float
    target_future_excess_return: float
    relative_rank_handoff_rate: float
    lead_lag_score: float
    obs_count: int


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path))


def _load_theme_map(asof: str) -> pd.DataFrame:
    with _connect(CLASS_DB) as con:
        df = pd.read_sql_query(
            """
            SELECT ticker, name, asset_type, theme_bucket, theme_name_kr
            FROM security_classification_master
            WHERE asof_date = ?
              AND is_active = 1
            """,
            con,
            params=[asof],
            dtype={"ticker": str},
        )
    if df.empty:
        raise RuntimeError(f"security_classification_master is empty for asof={asof}")
    df["ticker"] = df["ticker"].str.zfill(6)
    return df


def _load_close_panel(tickers: list[str], asof: str) -> pd.DataFrame:
    with _connect(PRICE_DB) as con:
        dates = pd.read_sql_query(
            """
            SELECT DISTINCT date
            FROM prices_daily
            WHERE date <= ?
            ORDER BY date DESC
            LIMIT ?
            """,
            con,
            params=[asof, LOOKBACK_DAYS],
        )["date"].tolist()
        if not dates:
            raise RuntimeError("No prices available for rotation analysis")
        min_date = min(dates)
        placeholders = ",".join(["?"] * len(tickers))
        px = pd.read_sql_query(
            f"""
            SELECT ticker, date, close
            FROM prices_daily
            WHERE date BETWEEN ? AND ?
              AND ticker IN ({placeholders})
              AND close IS NOT NULL
            """,
            con,
            params=[min_date, asof, *tickers],
            dtype={"ticker": str},
        )
    px["ticker"] = px["ticker"].str.zfill(6)
    px["date"] = pd.to_datetime(px["date"])
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    panel = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    return panel


def _build_theme_weekly_returns(
    meta: pd.DataFrame, close_panel: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[pd.Timestamp, str]]:
    grouped_close = close_panel.groupby(pd.Grouper(freq="W-FRI"))
    weekly_close = grouped_close.last().ffill()
    weekly_ret = weekly_close.pct_change(fill_method=None)
    theme_map = meta.set_index("ticker")["theme_bucket"].to_dict()
    grouped = weekly_ret.rename(columns=theme_map).T.groupby(level=0).mean().T
    member_counts = meta.groupby("theme_bucket").size().rename("member_count").reset_index()
    week_labels: dict[pd.Timestamp, str] = {}
    for bucket_end, frame in grouped_close:
        if frame.empty:
            continue
        week_labels[pd.Timestamp(bucket_end)] = frame.index.max().strftime("%Y-%m-%d")
    return grouped, member_counts, week_labels


def _rank_frame(theme_weekly: pd.DataFrame) -> pd.DataFrame:
    return theme_weekly.rank(axis=1, ascending=False, method="average", pct=True)


def _compute_lead_lag_pairs(theme_weekly: pd.DataFrame) -> list[LeadLagPair]:
    ranks = _rank_frame(theme_weekly)
    pairs: list[LeadLagPair] = []
    themes = list(theme_weekly.columns)
    for source in themes:
        src = theme_weekly[source]
        src_rank = ranks[source]
        for target in themes:
            if source == target:
                continue
            tgt = theme_weekly[target]
            tgt_rank = ranks[target]
            best_pair: LeadLagPair | None = None
            for lag in range(1, MAX_LAG_WEEKS + 1):
                aligned = pd.concat(
                    [
                        src.rename("src"),
                        tgt.shift(-lag).rename("tgt_fwd"),
                        src_rank.rename("src_rank"),
                        tgt.shift(-lag).rename("tgt_ret_fwd"),
                        tgt_rank.shift(-lag).rename("tgt_rank_fwd"),
                    ],
                    axis=1,
                ).dropna()
                if len(aligned) < MIN_PAIR_OBS:
                    continue
                lag_corr = float(aligned["src"].corr(aligned["tgt_fwd"]))
                if np.isnan(lag_corr):
                    continue
                src_top = aligned["src_rank"] <= 0.25
                if int(src_top.sum()) < 4:
                    continue
                future_up_ratio = float((aligned.loc[src_top, "tgt_ret_fwd"] > 0).mean())
                future_excess = float(
                    aligned.loc[src_top, "tgt_ret_fwd"].mean() - aligned["tgt_ret_fwd"].mean()
                )
                handoff_rate = float((aligned.loc[src_top, "tgt_rank_fwd"] <= 0.40).mean())
                hit_ratio = float(src_top.mean())
                score = (
                    max(0.0, lag_corr) * 0.45
                    + max(0.0, future_up_ratio - 0.5) * 0.25
                    + max(0.0, future_excess) * 4.0 * 0.20
                    + max(0.0, handoff_rate - 0.5) * 0.10
                )
                pair = LeadLagPair(
                    source_theme=source,
                    target_theme=target,
                    lag_weeks=lag,
                    lagged_corr=round(lag_corr, 4),
                    source_top_quartile_hit_ratio=round(hit_ratio, 4),
                    target_future_up_ratio=round(future_up_ratio, 4),
                    target_future_excess_return=round(future_excess, 4),
                    relative_rank_handoff_rate=round(handoff_rate, 4),
                    lead_lag_score=round(score, 4),
                    obs_count=int(len(aligned)),
                )
                if best_pair is None or pair.lead_lag_score > best_pair.lead_lag_score:
                    best_pair = pair
            if best_pair and best_pair.lead_lag_score > 0:
                pairs.append(best_pair)
    pairs.sort(key=lambda row: row.lead_lag_score, reverse=True)
    return pairs


def _recent_rotation_path(
    theme_weekly: pd.DataFrame,
    week_labels: dict[pd.Timestamp, str],
    top_n: int = 3,
    weeks: int = 12,
) -> list[dict[str, Any]]:
    recent = theme_weekly.tail(weeks)
    rows: list[dict[str, Any]] = []
    for dt, row in recent.iterrows():
        top = row.sort_values(ascending=False).head(top_n)
        bottom = row.sort_values(ascending=True).head(top_n)
        rows.append(
            {
                "week_end": week_labels.get(pd.Timestamp(dt), dt.strftime("%Y-%m-%d")),
                "leaders": [
                    {"theme": theme, "weekly_return": round(float(val), 4)} for theme, val in top.items()
                ],
                "laggards": [
                    {"theme": theme, "weekly_return": round(float(val), 4)} for theme, val in bottom.items()
                ],
            }
        )
    return rows


def _theme_rotation_summary(theme_weekly: pd.DataFrame, member_counts: pd.DataFrame) -> list[dict[str, Any]]:
    ranks = _rank_frame(theme_weekly)
    summary_rows: list[dict[str, Any]] = []
    count_map = member_counts.set_index("theme_bucket")["member_count"].to_dict()
    for theme in theme_weekly.columns:
        series = theme_weekly[theme].dropna()
        if series.empty:
            continue
        rank_series = ranks[theme].dropna()
        summary_rows.append(
            {
                "theme": theme,
                "member_count": int(count_map.get(theme, 0)),
                "mean_weekly_return": round(float(series.mean()), 4),
                "last_4w_avg_return": round(float(series.tail(4).mean()), 4),
                "last_8w_avg_return": round(float(series.tail(8).mean()), 4),
                "top_quartile_weeks": int((rank_series <= 0.25).sum()),
                "bottom_quartile_weeks": int((rank_series >= 0.75).sum()),
                "rank_turnover": round(float(rank_series.diff().abs().mean()), 4),
                "volatility": round(float(series.std()), 4),
            }
        )
    summary_rows.sort(key=lambda row: row["last_4w_avg_return"], reverse=True)
    return summary_rows


def _filter_core_rotation_themes(theme_weekly: pd.DataFrame, member_counts: pd.DataFrame) -> pd.DataFrame:
    valid = member_counts.loc[
        (member_counts["member_count"] >= MIN_THEME_MEMBERS)
        & (~member_counts["theme_bucket"].isin(GLOBAL_DEFENSIVE_THEMES)),
        "theme_bucket",
    ].tolist()
    cols = [col for col in theme_weekly.columns if col in valid]
    return theme_weekly[cols].copy()


def _to_dicts(rows: list[LeadLagPair], top_n: int = 20) -> list[dict[str, Any]]:
    return [row.__dict__ for row in rows[:top_n]]


def _write_reports(asof: str, payload: dict[str, Any]) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    json_path = REPORT_DIR / f"c_series_rotation_leadlag_{token}.json"
    md_path = REPORT_DIR / f"c_series_rotation_leadlag_{token}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# C-series Rotation / Lead-Lag Analysis",
        "",
        f"- asof_date: {asof}",
        f"- generated_at: {payload['generated_at']}",
        f"- analyzed_themes_all: {payload['counts']['all_theme_count']}",
        f"- analyzed_themes_core: {payload['counts']['core_theme_count']}",
        f"- weekly_points: {payload['counts']['weekly_points']}",
        "",
        "## Recent Rotation Path (Last 12 Weeks)",
        "",
    ]
    for row in payload["recent_rotation_path"]:
        leaders = ", ".join(f"{item['theme']}({item['weekly_return']:+.2%})" for item in row["leaders"])
        laggards = ", ".join(f"{item['theme']}({item['weekly_return']:+.2%})" for item in row["laggards"])
        lines.append(f"- {row['week_end']}: leaders={leaders} / laggards={laggards}")

    lines += ["", "## Top Lead-Lag Pairs (Core Themes)", ""]
    for row in payload["core_lead_lag_top"]:
        lines.append(
            "- "
            f"{row['source_theme']} -> {row['target_theme']} "
            f"(lag={row['lag_weeks']}w, score={row['lead_lag_score']}, "
            f"lagged_corr={row['lagged_corr']}, future_up={row['target_future_up_ratio']}, "
            f"future_excess={row['target_future_excess_return']:+.2%}, handoff={row['relative_rank_handoff_rate']})"
        )

    lines += ["", "## Theme Rotation Summary (Top Last 4 Weeks)", ""]
    for row in payload["theme_rotation_summary"][:15]:
        lines.append(
            "- "
            f"{row['theme']}: 4w_avg={row['last_4w_avg_return']:+.2%}, "
            f"8w_avg={row['last_8w_avg_return']:+.2%}, top_quartile_weeks={row['top_quartile_weeks']}, "
            f"turnover={row['rank_turnover']}"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze C-series theme rotation and lead-lag structure.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    asof = args.asof
    meta = _load_theme_map(asof)
    close_panel = _load_close_panel(meta["ticker"].tolist(), asof)
    theme_weekly_all, member_counts, week_labels = _build_theme_weekly_returns(meta, close_panel)
    theme_weekly_all = theme_weekly_all.dropna(axis=1, how="all")
    theme_weekly_core = _filter_core_rotation_themes(theme_weekly_all, member_counts)

    all_pairs = _compute_lead_lag_pairs(theme_weekly_all)
    core_pairs = _compute_lead_lag_pairs(theme_weekly_core)
    rotation_summary = _theme_rotation_summary(theme_weekly_core, member_counts)
    recent_path = _recent_rotation_path(theme_weekly_core, week_labels)

    payload = {
        "asof_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "all_theme_count": int(theme_weekly_all.shape[1]),
            "core_theme_count": int(theme_weekly_core.shape[1]),
            "weekly_points": int(theme_weekly_core.shape[0]),
            "lead_lag_pairs_all": int(len(all_pairs)),
            "lead_lag_pairs_core": int(len(core_pairs)),
        },
        "recent_rotation_path": recent_path,
        "all_lead_lag_top": _to_dicts(all_pairs),
        "core_lead_lag_top": _to_dicts(core_pairs),
        "theme_rotation_summary": rotation_summary,
    }
    json_path, md_path = _write_reports(asof, payload)
    print(
        json.dumps(
            {
                "status": "ok",
                "asof": asof,
                "json_report": str(json_path),
                "md_report": str(md_path),
                **payload["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
