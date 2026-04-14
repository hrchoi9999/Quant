from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import re

import numpy as np
import pandas as pd
import sqlite3

CURRENT = Path(__file__).resolve()
ROOT = next((pp for pp in [CURRENT] + list(CURRENT.parents) if (pp / 'src').exists()), CURRENT.parent)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtest.core.data import load_prices_wide
from tseries_refresh_utils import ensure_run_dir, normalize_run_date

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
PIT_UNIVERSE_CSV = Path()
OUTDIR = Path()
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"

HORIZON_STEPS = {"3M": 3, "6M": 6, "1Y": 12}
FEATURE_COLS = [
    "ret_20d", "ret_60d", "ret_120d", "ret_240d",
    "vol_20d", "vol_60d", "dd_60d", "dd_120d",
    "dist_ma20", "dist_ma60", "dist_ma120",
    "ma20_ma60_gap", "ma60_ma120_gap", "rsi20", "liquidity_20d_value",
]


def latest_pit_universe_csv() -> Path:
    base = PROJECT_ROOT / r"data\universe\etf_pit_backfill"
    pattern = re.compile(r"universe_etf_pit_monthly_\d{6}_(\d{6})\.csv$")
    matches: list[tuple[str, Path]] = []
    for path in base.glob("universe_etf_pit_monthly_*.csv"):
        match = pattern.match(path.name)
        if match:
            matches.append((match.group(1), path))
    if not matches:
        raise FileNotFoundError(f"No ETF PIT universe CSV found in {base}")
    return max(matches, key=lambda item: item[0])[1]


def calc_rsi(series: pd.Series, window: int = 20) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(window, min_periods=window).mean()
    avg_loss = loss.rolling(window, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def path_mdd(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 2:
        return float("nan")
    dd = s / s.cummax() - 1.0
    return float(dd.min())


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = pd.read_csv(PIT_UNIVERSE_CSV, dtype={"ticker": str}).copy()
    universe["ticker"] = universe["ticker"].astype(str).str.zfill(6)
    universe["selection_asof"] = pd.to_datetime(universe["selection_asof"])
    close_wide = load_prices_wide(price_db=PRICE_DB, tickers=universe["ticker"].drop_duplicates().tolist())
    close_wide.index = pd.to_datetime(close_wide.index)
    close_wide = close_wide.sort_index()
    return universe, close_wide


def build_feature_panel(universe: pd.DataFrame, close_wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = universe.groupby("ticker")
    for ticker, g in grouped:
        if ticker not in close_wide.columns:
            continue
        px = close_wide[ticker].dropna().sort_index()
        if px.empty:
            continue
        ma20 = px.rolling(20, min_periods=20).mean()
        ma60 = px.rolling(60, min_periods=60).mean()
        ma120 = px.rolling(120, min_periods=120).mean()
        ret20 = px / px.shift(20) - 1.0
        ret60 = px / px.shift(60) - 1.0
        ret120 = px / px.shift(120) - 1.0
        ret240 = px / px.shift(240) - 1.0
        vol20 = px.pct_change(fill_method=None).rolling(20, min_periods=20).std(ddof=0)
        vol60 = px.pct_change(fill_method=None).rolling(60, min_periods=60).std(ddof=0)
        dd60 = px / px.rolling(60, min_periods=20).max() - 1.0
        dd120 = px / px.rolling(120, min_periods=20).max() - 1.0
        rsi20 = calc_rsi(px, 20)
        for r in g.itertuples(index=False):
            dt = pd.Timestamp(r.selection_asof)
            if dt not in px.index:
                prior = px.index[px.index <= dt]
                if len(prior) == 0:
                    continue
                dt_use = pd.Timestamp(prior[-1])
            else:
                dt_use = dt
            rows.append({
                "signal_date": dt,
                "feature_date": dt_use,
                "ticker": ticker,
                "name": r.name,
                "asset_class": getattr(r, "asset_class", "") or "",
                "group_key": getattr(r, "group_key", "") or "",
                "currency_exposure": getattr(r, "currency_exposure", "") or "",
                "is_inverse": bool(getattr(r, "is_inverse", False)),
                "is_leveraged": bool(getattr(r, "is_leveraged", False)),
                "expanded_group": getattr(r, "expanded_group", "") or "",
                "liquidity_20d_value": float(getattr(r, "liquidity_20d_value", 0.0) or 0.0),
                "close": float(px.get(dt_use, np.nan)),
                "ret_20d": float(ret20.get(dt_use, np.nan)),
                "ret_60d": float(ret60.get(dt_use, np.nan)),
                "ret_120d": float(ret120.get(dt_use, np.nan)),
                "ret_240d": float(ret240.get(dt_use, np.nan)),
                "vol_20d": float(vol20.get(dt_use, np.nan)),
                "vol_60d": float(vol60.get(dt_use, np.nan)),
                "dd_60d": float(dd60.get(dt_use, np.nan)),
                "dd_120d": float(dd120.get(dt_use, np.nan)),
                "dist_ma20": float(px.get(dt_use, np.nan) / ma20.get(dt_use, np.nan) - 1.0) if pd.notna(ma20.get(dt_use, np.nan)) else np.nan,
                "dist_ma60": float(px.get(dt_use, np.nan) / ma60.get(dt_use, np.nan) - 1.0) if pd.notna(ma60.get(dt_use, np.nan)) else np.nan,
                "dist_ma120": float(px.get(dt_use, np.nan) / ma120.get(dt_use, np.nan) - 1.0) if pd.notna(ma120.get(dt_use, np.nan)) else np.nan,
                "ma20_ma60_gap": float(ma20.get(dt_use, np.nan) / ma60.get(dt_use, np.nan) - 1.0) if pd.notna(ma20.get(dt_use, np.nan)) and pd.notna(ma60.get(dt_use, np.nan)) else np.nan,
                "ma60_ma120_gap": float(ma60.get(dt_use, np.nan) / ma120.get(dt_use, np.nan) - 1.0) if pd.notna(ma60.get(dt_use, np.nan)) and pd.notna(ma120.get(dt_use, np.nan)) else np.nan,
                "rsi20": float(rsi20.get(dt_use, 50.0)),
            })
    return pd.DataFrame(rows)


def attach_future_labels(panel: pd.DataFrame, signal_dates: list[pd.Timestamp], close_wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    date_to_idx = {pd.Timestamp(d): i for i, d in enumerate(signal_dates)}
    out = panel.copy()
    for horizon, steps in HORIZON_STEPS.items():
        fwd_rets, fwd_mdds, end_dates = [], [], []
        for r in out.itertuples(index=False):
            dt = pd.Timestamp(r.signal_date)
            idx = date_to_idx.get(dt)
            if idx is None or idx + steps >= len(signal_dates):
                fwd_rets.append(np.nan)
                fwd_mdds.append(np.nan)
                end_dates.append(pd.NaT)
                continue
            end_dt = pd.Timestamp(signal_dates[idx + steps])
            if r.ticker not in close_wide.columns:
                fwd_rets.append(np.nan)
                fwd_mdds.append(np.nan)
                end_dates.append(pd.NaT)
                continue
            series = pd.to_numeric(close_wide[r.ticker], errors="coerce").dropna().sort_index()
            start_idx = series.index[series.index <= dt]
            end_idx = series.index[series.index <= end_dt]
            if len(start_idx) == 0 or len(end_idx) == 0:
                fwd_rets.append(np.nan)
                fwd_mdds.append(np.nan)
                end_dates.append(pd.NaT)
                continue
            start_use = pd.Timestamp(start_idx[-1])
            end_use = pd.Timestamp(end_idx[-1])
            if end_use <= start_use:
                fwd_rets.append(np.nan)
                fwd_mdds.append(np.nan)
                end_dates.append(pd.NaT)
                continue
            start_px = float(series.loc[start_use])
            end_px = float(series.loc[end_use])
            fwd_rets.append(end_px / start_px - 1.0 if start_px > 0 else np.nan)
            fwd_mdds.append(path_mdd(series.loc[start_use:end_use]))
            end_dates.append(end_use)
        out[f"fwd_ret_{horizon}"] = fwd_rets
        out[f"path_mdd_{horizon}"] = fwd_mdds
        out[f"end_date_{horizon}"] = end_dates

    bucket_frames = []
    for horizon in HORIZON_STEPS:
        work = out[["signal_date", "ticker", f"fwd_ret_{horizon}", f"path_mdd_{horizon}"]].copy()
        work = work.dropna(subset=[f"fwd_ret_{horizon}", f"path_mdd_{horizon}"]).copy()
        if work.empty:
            continue
        work["ret_pct"] = work.groupby("signal_date")[f"fwd_ret_{horizon}"].rank(method="first", pct=True)
        work["mdd_pct"] = work.groupby("signal_date")[f"path_mdd_{horizon}"].rank(method="first", pct=True)
        work["future_quality"] = 0.7 * work["ret_pct"] + 0.3 * work["mdd_pct"]
        bucket_parts = []
        for d0, g in work.groupby("signal_date"):
            g = g.sort_values(["future_quality", f"fwd_ret_{horizon}", f"path_mdd_{horizon}", "ticker"], ascending=[False, False, False, True]).copy()
            n = len(g)
            cut3 = max(1, int(math.ceil(n * 0.03)))
            cut10 = max(cut3 + 1, int(math.ceil(n * 0.10)))
            cut30 = max(cut10 + 1, int(math.ceil(n * 0.30)))
            cut50 = max(cut30 + 1, int(math.ceil(n * 0.50)))
            g["rank_num"] = range(1, n + 1)
            g["bucket"] = "OUTSIDE"
            g.loc[g["rank_num"] <= cut50, "bucket"] = "ET50_ex_ET30"
            g.loc[g["rank_num"] <= cut30, "bucket"] = "ET30_ex_ET10"
            g.loc[g["rank_num"] <= cut10, "bucket"] = "ET10_ex_ET3"
            g.loc[g["rank_num"] <= cut3, "bucket"] = "ET3"
            g["horizon"] = horizon
            bucket_parts.append(g)
        bucket_frames.append(pd.concat(bucket_parts, ignore_index=True))
    bucket_df = pd.concat(bucket_frames, ignore_index=True) if bucket_frames else pd.DataFrame()
    return out, bucket_df


def build_transition_panel(feature_df: pd.DataFrame, bucket_df: pd.DataFrame) -> pd.DataFrame:
    panels = []
    for horizon, horizon_df in bucket_df.groupby("horizon"):
        dates = sorted(pd.to_datetime(horizon_df["signal_date"]).drop_duplicates())
        next_map = {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}
        current = horizon_df.rename(columns={"bucket": "current_bucket"}).copy()
        current["next_signal_date"] = current["signal_date"].map(next_map)
        current = current[current["next_signal_date"].notna()].copy()
        nxt = horizon_df[["signal_date", "ticker", "bucket"]].rename(columns={"signal_date": "next_signal_date", "bucket": "next_bucket"})
        merged = current.merge(nxt, on=["next_signal_date", "ticker"], how="left")
        merged = merged.merge(
            feature_df[["signal_date", "ticker", "name", "asset_class", "group_key", "currency_exposure", "expanded_group"] + FEATURE_COLS],
            on=["signal_date", "ticker"],
            how="left",
        )
        merged["horizon"] = horizon
        panels.append(merged)
    out = pd.concat(panels, ignore_index=True) if panels else pd.DataFrame()
    if not out.empty:
        out["label_to_et10"] = out["next_bucket"].isin(["ET10_ex_ET3", "ET3"]).astype(int)
        out["label_to_et3"] = out["next_bucket"].eq("ET3").astype(int)
    return out


def build_transition_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (horizon, current_bucket), grp in panel.groupby(["horizon", "current_bucket"], dropna=False):
        denom = len(grp)
        counts = grp["next_bucket"].fillna("MISSING").value_counts()
        for next_bucket, cnt in counts.items():
            rows.append({
                "horizon": horizon,
                "current_bucket": current_bucket,
                "next_bucket": next_bucket,
                "count": int(cnt),
                "probability": float(cnt / denom) if denom else np.nan,
            })
    return pd.DataFrame(rows).sort_values(["horizon", "current_bucket", "probability"], ascending=[True, True, False])


def main() -> None:
    ap = argparse.ArgumentParser(description="Build ETF T-series PIT backfill feature/transition panels.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD output folder.")
    ap.add_argument("--asof", default=None, help="Accepted for interface consistency; latest available PIT universe file is used.")
    args = ap.parse_args()

    global PIT_UNIVERSE_CSV, OUTDIR
    PIT_UNIVERSE_CSV = latest_pit_universe_csv()
    OUTDIR = ensure_run_dir(normalize_run_date(args.run_date)) / "ETF_T_SERIES_PIT_BACKFILL_V1"
    OUTDIR.mkdir(parents=True, exist_ok=True)

    universe, close_wide = load_inputs()
    signal_dates = sorted(pd.to_datetime(universe["selection_asof"]).drop_duplicates().tolist())
    feature_df = build_feature_panel(universe, close_wide)
    feature_df, bucket_df = attach_future_labels(feature_df, signal_dates, close_wide)
    transition_df = build_transition_panel(feature_df, bucket_df)
    matrix_df = build_transition_matrix(transition_df) if not transition_df.empty else pd.DataFrame()

    feature_df.to_csv(OUTDIR / "etf_tseries_pit_feature_panel.csv", index=False, encoding="utf-8-sig")
    bucket_df.to_csv(OUTDIR / "etf_tseries_pit_bucket_panel.csv", index=False, encoding="utf-8-sig")
    transition_df.to_csv(OUTDIR / "etf_tseries_pit_transition_panel.csv", index=False, encoding="utf-8-sig")
    matrix_df.to_csv(OUTDIR / "etf_tseries_pit_transition_matrix.csv", index=False, encoding="utf-8-sig")

    with sqlite3.connect(RESEARCH_DB) as conn:
        feature_df.to_sql("etf_tseries_pit_feature_panel", conn, if_exists="replace", index=False)
        bucket_df.to_sql("etf_tseries_pit_bucket_panel", conn, if_exists="replace", index=False)
        transition_df.to_sql("etf_tseries_pit_transition_panel", conn, if_exists="replace", index=False)
        matrix_df.to_sql("etf_tseries_pit_transition_matrix", conn, if_exists="replace", index=False)

    lines = [
        "# ETF T-series PIT Backfill V1",
        "",
        f"- monthly universe rows: {len(universe):,}",
        f"- feature panel rows: {len(feature_df):,}",
        f"- bucket panel rows: {len(bucket_df):,}",
        f"- transition rows: {len(transition_df):,}",
        f"- first signal date: {feature_df['signal_date'].min() if not feature_df.empty else 'n/a'}",
        f"- last signal date: {feature_df['signal_date'].max() if not feature_df.empty else 'n/a'}",
    ]
    if not transition_df.empty:
        lower = transition_df[transition_df["current_bucket"].isin(["OUTSIDE", "ET50_ex_ET30", "ET30_ex_ET10"])]
        et10 = transition_df[transition_df["current_bucket"] == "ET10_ex_ET3"]
        lines.append("")
        lines.append("## Transition rates")
        lines.append(f"- lower -> ET10+: {lower['label_to_et10'].mean():.2%}" if len(lower) else "- lower -> ET10+: n/a")
        lines.append(f"- ET10 -> ET3: {et10['label_to_et3'].mean():.2%}" if len(et10) else "- ET10 -> ET3: n/a")
    (OUTDIR / "etf_tseries_pit_backfill_v1.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] feature_rows={len(feature_df)}")
    print(f"[OK] bucket_rows={len(bucket_df)}")
    print(f"[OK] transition_rows={len(transition_df)}")
    if not transition_df.empty:
        lower = transition_df[transition_df["current_bucket"].isin(["OUTSIDE", "ET50_ex_ET30", "ET30_ex_ET10"])]
        et10 = transition_df[transition_df["current_bucket"] == "ET10_ex_ET3"]
        print(f"[OK] lower_to_et10_rate={lower['label_to_et10'].mean():.6f}" if len(lower) else "[OK] lower_to_et10_rate=nan")
        print(f"[OK] et10_to_et3_rate={et10['label_to_et3'].mean():.6f}" if len(et10) else "[OK] et10_to_et3_rate=nan")


if __name__ == "__main__":
    main()
