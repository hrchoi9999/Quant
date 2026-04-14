from __future__ import annotations

import argparse
from pathlib import Path
import re
import pandas as pd

from tseries_refresh_utils import ensure_run_dir, normalize_run_date

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = ""
IN_DIR = Path()
LOOKBACK_WINDOWS = 3
COOLING_WINDOWS = 2
BUCKET_RANK = {"confirmed": 0, "near": 1, "observe": 2}
STATE_RANK = {"active": 0, "new": 1, "cooling": 2}
TIER_RANK = {"core": 0, "monitor": 1}


def _latest_watchlist_files() -> list[tuple[pd.Timestamp, Path]]:
    items: list[tuple[pd.Timestamp, Path]] = []
    pattern = re.compile(r"etf_tseries_pit_latest_watchlist_(\d{4}-\d{2}-\d{2})\.csv$")
    for path in IN_DIR.glob("etf_tseries_pit_latest_watchlist_*.csv"):
        m = pattern.match(path.name)
        if not m:
            continue
        items.append((pd.Timestamp(m.group(1)), path))
    return sorted(items, key=lambda x: x[0])


def _load_history(files: list[tuple[pd.Timestamp, Path]]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for asof_ts, path in files:
        df = pd.read_csv(path, dtype={"ticker": str})
        if df.empty:
            continue
        df = df.rename(columns={"candidate_grade": "candidate_bucket"})
        df["asof_date"] = asof_ts.strftime("%Y-%m-%d")
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    hist = pd.concat(frames, ignore_index=True)
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    hist["asof_date"] = pd.to_datetime(hist["asof_date"])
    hist["bucket_rank"] = hist["candidate_bucket"].map(lambda v: BUCKET_RANK.get(str(v), 9))
    return hist


def _consecutive_count(frame: pd.DataFrame, ordered_dates: list[pd.Timestamp]) -> int:
    dates = set(frame["asof_date"].tolist())
    count = 0
    for dt in reversed(ordered_dates):
        if dt in dates:
            count += 1
        else:
            break
    return count


def main() -> None:
    ap = argparse.ArgumentParser(description="Build ETF T-series PIT rolling watchlist.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD run folder.")
    ap.add_argument("--asof", default=None, help="Accepted for interface consistency; latest watchlist history is used.")
    args = ap.parse_args()

    global RUN_DATE, IN_DIR
    RUN_DATE = normalize_run_date(args.run_date)
    IN_DIR = ensure_run_dir(RUN_DATE) / "ETF_T_SERIES_OPERATIONALIZATION_PIT"

    files = _latest_watchlist_files()
    if not files:
        raise SystemExit("no etf latest watchlist files found")

    history = _load_history(files)
    latest_dates = [dt for dt, _ in files][-LOOKBACK_WINDOWS:]
    current_asof = latest_dates[-1]
    recent = history.loc[history["asof_date"].isin(latest_dates)].copy()
    cooling_dates = [dt for dt, _ in files][-(LOOKBACK_WINDOWS + COOLING_WINDOWS):]
    cooling_hist = history.loc[history["asof_date"].isin(cooling_dates)].copy()

    rows: list[dict] = []
    for ticker, grp in cooling_hist.groupby("ticker", sort=False):
        grp = grp.sort_values(["asof_date", "bucket_rank"]).drop_duplicates(subset=["asof_date"], keep="first")
        recent_grp = recent.loc[recent["ticker"] == ticker].sort_values(["asof_date", "bucket_rank"]).drop_duplicates(subset=["asof_date"], keep="first")
        current_row = recent_grp.loc[recent_grp["asof_date"] == current_asof]
        is_current = not current_row.empty
        appearances_recent = int(recent_grp["asof_date"].nunique())
        consecutive_current = _consecutive_count(recent_grp, latest_dates) if is_current else 0
        best_row = recent_grp.sort_values(["bucket_rank", "asof_date"]).iloc[0]
        last_seen = grp["asof_date"].max()
        prev_seen = grp["asof_date"].sort_values().iloc[-2] if len(grp) >= 2 else pd.NaT
        if is_current:
            state = "new" if appearances_recent == 1 else "active"
            base_row = current_row.iloc[0]
        else:
            previous_windows = latest_dates[-COOLING_WINDOWS-1:-1] if len(latest_dates) > 1 else []
            if last_seen not in previous_windows:
                continue
            state = "cooling"
            base_row = grp.sort_values("asof_date").iloc[-1]
        tier = "core" if int(best_row["bucket_rank"]) <= 1 else "monitor"
        rows.append({
            "model_code": "T-ETF-V01",
            "asof_date": current_asof.strftime("%Y-%m-%d"),
            "watch_status": state,
            "watch_tier": tier,
            "is_current": int(is_current),
            "current_bucket": None if not is_current else str(base_row.get("candidate_bucket", "")),
            "best_bucket_recent": str(best_row.get("candidate_bucket", "")),
            "appearances_recent": appearances_recent,
            "consecutive_current": consecutive_current,
            "last_seen_asof": pd.Timestamp(last_seen).strftime("%Y-%m-%d"),
            "prev_seen_asof": None if pd.isna(prev_seen) else pd.Timestamp(prev_seen).strftime("%Y-%m-%d"),
            "ticker": ticker,
            "name": base_row.get("name"),
            "asset_class": base_row.get("asset_class"),
            "group_key": base_row.get("group_key"),
            "theme_bucket": base_row.get("theme_bucket"),
            "liquidity_20d_value": base_row.get("liquidity_20d_value"),
            "stage1_prob": base_row.get("stage1_prob"),
            "stage2_prob": base_row.get("stage2_prob"),
        })

    latest = pd.DataFrame(rows)
    if latest.empty:
        latest = pd.DataFrame(columns=[
            "model_code","asof_date","watch_status","watch_tier","is_current","current_bucket","best_bucket_recent",
            "appearances_recent","consecutive_current","last_seen_asof","prev_seen_asof","ticker","name","asset_class",
            "group_key","theme_bucket","liquidity_20d_value","stage1_prob","stage2_prob"
        ])
    else:
        latest["state_rank"] = latest["watch_status"].map(lambda v: STATE_RANK.get(str(v), 9))
        latest["tier_rank"] = latest["watch_tier"].map(lambda v: TIER_RANK.get(str(v), 9))
        latest = latest.sort_values(["tier_rank", "state_rank", "stage2_prob", "stage1_prob", "ticker"], ascending=[True, True, False, False, True], na_position="last")
        latest = latest.drop(columns=["state_rank", "tier_rank"])

    summary = []
    for state in ["active", "new", "cooling"]:
        frame = latest.loc[latest["watch_status"] == state]
        summary.append({"bucket": state, "count": int(len(frame))})
    for tier in ["core", "monitor"]:
        frame = latest.loc[latest["watch_tier"] == tier]
        summary.append({"bucket": f"tier_{tier}", "count": int(len(frame))})
    summary_df = pd.DataFrame(summary)

    latest.to_csv(IN_DIR / f"etf_tseries_pit_rolling_watchlist_{current_asof.strftime('%Y-%m-%d')}.csv", index=False, encoding="utf-8-sig")
    summary_df.to_csv(IN_DIR / f"etf_tseries_pit_rolling_watchlist_summary_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")
    md = f"""# T-ETF-V01 Rolling Watchlist ({current_asof.strftime('%Y-%m-%d')})\n\n- lookback windows: {LOOKBACK_WINDOWS}\n- cooling windows: {COOLING_WINDOWS}\n- active: {int((latest['watch_status'] == 'active').sum()) if not latest.empty else 0}\n- new: {int((latest['watch_status'] == 'new').sum()) if not latest.empty else 0}\n- cooling: {int((latest['watch_status'] == 'cooling').sum()) if not latest.empty else 0}\n"""
    (IN_DIR / f"etf_tseries_pit_rolling_watchlist_{RUN_DATE}.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
