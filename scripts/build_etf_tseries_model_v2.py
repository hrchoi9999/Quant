from __future__ import annotations

import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CURRENT = Path(__file__).resolve()
ROOT = next((pp for pp in [CURRENT] + list(CURRENT.parents) if (pp / "src").exists()), CURRENT.parent)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtest.core.data import load_prices_wide

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
ETF_UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_etf_extended_200_20260331.csv"
ETF_REPORT_DIR = PROJECT_ROOT / r"reports\backtest_etf_allocation"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\ETF_T_SERIES_V2"
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
ASOF_DATE = pd.Timestamp("2026-03-31")
HORIZON_STEPS = {"3M": 3, "6M": 6, "1Y": 12}
TRAIN_SPLIT = 0.7
PRED_WEIGHTS = {"3M": 0.5, "6M": 0.3, "1Y": 0.2}
NUMERIC_FEATURES = [
    "ret_20d", "ret_60d", "ret_120d", "ret_240d",
    "vol_20d", "vol_60d", "dd_60d", "dd_120d",
    "dist_ma20", "dist_ma60", "dist_ma120",
    "ma20_ma60_gap", "ma60_ma120_gap", "rsi20", "liquidity_20d_value",
]
CAT_FEATURES = [
    "asset_class", "group_key", "currency_exposure", "is_inverse", "is_leveraged"
]


def _latest_file(pattern: str) -> Path:
    files = sorted(ETF_REPORT_DIR.glob(pattern), key=lambda p: (p.stat().st_mtime, p.name))
    if not files:
        raise FileNotFoundError(pattern)
    return files[-1]


def _load_signal_dates() -> list[pd.Timestamp]:
    s4_path = _latest_file("s4_alloc_weights_*_M_20230608_20260325.csv")
    df = pd.read_csv(s4_path, dtype={"ticker": str})
    dates = sorted(pd.to_datetime(df["trade_date"].dropna().unique()).tolist())
    return [pd.Timestamp(d) for d in dates]


def _calc_rsi(series: pd.Series, window: int = 20) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(window, min_periods=window).mean()
    avg_loss = loss.rolling(window, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def _path_mdd(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 2:
        return float("nan")
    dd = s / s.cummax() - 1.0
    return float(dd.min())


def _build_feature_panel(universe: pd.DataFrame, signal_dates: list[pd.Timestamp], close_wide: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for ticker in universe["ticker"].tolist():
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
        rsi20 = _calc_rsi(px, 20)
        base = universe.loc[universe["ticker"] == ticker].iloc[0].to_dict()
        for dt in signal_dates:
            if dt not in px.index:
                prior = px.index[px.index <= dt]
                if len(prior) == 0:
                    continue
                dt_use = pd.Timestamp(prior[-1])
            else:
                dt_use = pd.Timestamp(dt)
            row = {
                "signal_date": pd.Timestamp(dt),
                "feature_date": dt_use,
                "ticker": ticker,
                "name": base.get("name", ""),
                "asset_class": base.get("asset_class", ""),
                "group_key": base.get("group_key", ""),
                "currency_exposure": base.get("currency_exposure", ""),
                "is_inverse": bool(base.get("is_inverse", False)),
                "is_leveraged": bool(base.get("is_leveraged", False)),
                "liquidity_20d_value": float(base.get("liquidity_20d_value", 0.0) or 0.0),
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
            }
            rows.append(row)
    return pd.DataFrame(rows)


def _attach_future_labels(panel: pd.DataFrame, signal_dates: list[pd.Timestamp], close_wide: pd.DataFrame) -> pd.DataFrame:
    date_to_idx = {pd.Timestamp(d): i for i, d in enumerate(signal_dates)}
    out = panel.copy()
    for horizon, steps in HORIZON_STEPS.items():
        fwd_rets = []
        fwd_mdds = []
        end_dates = []
        for r in out.itertuples(index=False):
            dt = pd.Timestamp(r.signal_date)
            idx = date_to_idx.get(dt)
            if idx is None or idx + steps >= len(signal_dates):
                fwd_rets.append(np.nan)
                fwd_mdds.append(np.nan)
                end_dates.append(pd.NaT)
                continue
            end_dt = pd.Timestamp(signal_dates[idx + steps])
            series = close_wide.get(r.ticker)
            if series is None:
                fwd_rets.append(np.nan)
                fwd_mdds.append(np.nan)
                end_dates.append(pd.NaT)
                continue
            series = pd.to_numeric(series, errors="coerce").dropna().sort_index()
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
            fwd_mdds.append(_path_mdd(series.loc[start_use:end_use]))
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
    bucket_df = pd.concat(bucket_frames, ignore_index=True)
    return out, bucket_df


def _build_model_pipeline() -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
        ]
    )
    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    return Pipeline([("pre", pre), ("clf", clf)])


def _time_split(dates: list[pd.Timestamp]) -> tuple[list[pd.Timestamp], list[pd.Timestamp]]:
    cut_idx = max(1, int(len(dates) * TRAIN_SPLIT))
    if cut_idx >= len(dates):
        cut_idx = len(dates) - 1
    return dates[:cut_idx], dates[cut_idx:]


def _eval_topn(pred_df: pd.DataFrame, top_ratio: float) -> tuple[float, float, float, float]:
    rows = []
    for d0, g in pred_df.groupby("signal_date"):
        ranked = g.sort_values(["pred_prob", "ticker"], ascending=[False, True]).copy()
        top_n = max(1, int(math.ceil(len(ranked) * top_ratio)))
        top = ranked.head(min(top_n, len(ranked))).copy()
        pos_n = int(g["label"].sum())
        hits = int(top["label"].sum())
        base = float(g["label"].mean()) if len(g) else 0.0
        precision = float(top["label"].mean()) if len(top) else 0.0
        capture = float(hits / pos_n) if pos_n else np.nan
        lift = float(precision / base) if base else np.nan
        rows.append((precision, capture, lift, base))
    arr = np.array(rows, dtype=float) if rows else np.empty((0, 4))
    if arr.size == 0:
        return (np.nan, np.nan, np.nan, np.nan)
    return tuple(np.nanmean(arr[:, i]) for i in range(4))


def _train_and_eval(panel: pd.DataFrame, bucket_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[tuple[str, str], Pipeline], pd.DataFrame]:
    summary_rows: list[dict] = []
    models: dict[tuple[str, str], Pipeline] = {}
    latest_rows: list[pd.DataFrame] = []
    latest_date = panel["signal_date"].max()
    latest_panel = panel[panel["signal_date"] == latest_date].copy()

    for horizon in HORIZON_STEPS:
        h_bucket = bucket_df[bucket_df["horizon"] == horizon][["signal_date", "ticker", "bucket"]].copy()
        h_panel = panel.merge(h_bucket, on=["signal_date", "ticker"], how="inner")
        h_panel = h_panel.dropna(subset=NUMERIC_FEATURES).copy()
        if h_panel.empty:
            continue
        dates = sorted(pd.to_datetime(h_panel["signal_date"]).drop_duplicates())
        if len(dates) < 10:
            continue
        train_dates, test_dates = _time_split(dates)
        for target_name, top_ratio, label_fn in [
            ("ET10", 0.10, lambda s: s.isin(["ET3", "ET10_ex_ET3"])),
            ("ET3", 0.03, lambda s: s.eq("ET3")),
        ]:
            df = h_panel.copy()
            df["label"] = label_fn(df["bucket"]).astype(int)
            train_df = df[df["signal_date"].isin(train_dates)].copy()
            test_df = df[df["signal_date"].isin(test_dates)].copy()
            if train_df["label"].nunique() < 2 or test_df["label"].nunique() < 2:
                continue
            pipe = _build_model_pipeline()
            pipe.fit(train_df[NUMERIC_FEATURES + CAT_FEATURES], train_df["label"])
            prob = pipe.predict_proba(test_df[NUMERIC_FEATURES + CAT_FEATURES])[:, 1]
            auc = roc_auc_score(test_df["label"], prob)
            pred_df = test_df[["signal_date", "ticker", "name", "bucket", "label"]].copy()
            pred_df["pred_prob"] = prob
            precision, capture, lift, base = _eval_topn(pred_df, top_ratio)
            summary_rows.append({
                "horizon": horizon,
                "target": target_name,
                "test_auc": auc,
                "avg_precision": precision,
                "avg_capture": capture,
                "avg_lift": lift,
                "avg_base_rate": base,
                "top_ratio": top_ratio,
                "train_windows": len(train_dates),
                "test_windows": len(test_dates),
            })
            full_df = df.copy()
            full_pipe = _build_model_pipeline()
            full_pipe.fit(full_df[NUMERIC_FEATURES + CAT_FEATURES], full_df["label"])
            models[(horizon, target_name)] = full_pipe
            latest_pred = latest_panel.copy()
            latest_pred[f"prob_{target_name.lower()}_{horizon.lower()}"] = full_pipe.predict_proba(latest_pred[NUMERIC_FEATURES + CAT_FEATURES])[:, 1]
            latest_rows.append(latest_pred[["signal_date", "ticker", "name", f"prob_{target_name.lower()}_{horizon.lower()}"]])
    latest_merge = latest_panel[["signal_date", "ticker", "name", "asset_class", "group_key", "currency_exposure"]].copy()
    for df in latest_rows:
        latest_merge = latest_merge.merge(df, on=["signal_date", "ticker", "name"], how="left")
    return pd.DataFrame(summary_rows), models, latest_merge


def _load_model_weights(prefix: str) -> pd.DataFrame:
    path = _latest_file(f"{prefix}_alloc_weights_*_M_20230608_20260325.csv")
    df = pd.read_csv(path, dtype={"ticker": str})
    df["ticker"] = df["ticker"].fillna("").astype(str).str.zfill(6)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df[(df["selected"].astype(bool)) & (df["ticker"].ne("CASH")) & (pd.to_numeric(df["weight"], errors="coerce").fillna(0.0) > 0.0)].copy()
    return df[["trade_date", "ticker", "name", "weight"]]


def _evaluate_s456(bucket_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model, prefix in [("S4", "s4"), ("S5", "s5"), ("S6", "s6")]:
        sel = _load_model_weights(prefix)
        for horizon in HORIZON_STEPS:
            lab = bucket_df[bucket_df["horizon"] == horizon][["signal_date", "ticker", "bucket"]].copy()
            merged = sel.merge(lab, left_on=["trade_date", "ticker"], right_on=["signal_date", "ticker"], how="left")
            for target_name, label_fn in [
                ("ET10", lambda s: s.isin(["ET3", "ET10_ex_ET3"])),
                ("ET3", lambda s: s.eq("ET3")),
            ]:
                target = merged.copy()
                target["hit"] = label_fn(target["bucket"]).astype(int)
                win_rows = []
                for d0, g in target.groupby("trade_date"):
                    positives = int(label_fn(lab.loc[lab["signal_date"] == d0, "bucket"]).sum())
                    if len(g) == 0:
                        continue
                    hits = int(g["hit"].sum())
                    precision = float(g["hit"].mean())
                    capture = float(hits / positives) if positives else np.nan
                    base_rate = float(positives / max(1, len(lab.loc[lab["signal_date"] == d0, "ticker"].unique())))
                    lift = float(precision / base_rate) if base_rate else np.nan
                    win_rows.append((precision, capture, lift, base_rate, len(g)))
                if not win_rows:
                    continue
                arr = np.array(win_rows, dtype=float)
                rows.append({
                    "model": model,
                    "horizon": horizon,
                    "target": target_name,
                    "avg_precision": float(np.nanmean(arr[:, 0])),
                    "avg_capture": float(np.nanmean(arr[:, 1])),
                    "avg_lift": float(np.nanmean(arr[:, 2])),
                    "avg_base_rate": float(np.nanmean(arr[:, 3])),
                    "avg_selected_n": float(np.nanmean(arr[:, 4])),
                    "windows": int(len(arr)),
                })
    return pd.DataFrame(rows)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(ETF_UNIVERSE_CSV, dtype={"ticker": str})
    universe["ticker"] = universe["ticker"].astype(str).str.zfill(6)
    signal_dates = _load_signal_dates()
    close_wide = load_prices_wide(price_db=PRICE_DB, tickers=universe["ticker"].tolist(), start="2023-01-01", end="2026-03-31")
    panel = _build_feature_panel(universe, signal_dates, close_wide)
    panel, bucket_df = _attach_future_labels(panel, signal_dates, close_wide)
    summary_df, models, latest_df = _train_and_eval(panel, bucket_df)
    compare_df = _evaluate_s456(bucket_df)

    for col in [c for c in latest_df.columns if c.startswith("prob_")]:
        latest_df[col] = pd.to_numeric(latest_df[col], errors="coerce").fillna(0.0)
    latest_df["score_et10"] = (
        latest_df.get("prob_et10_3m", 0.0) * PRED_WEIGHTS["3M"]
        + latest_df.get("prob_et10_6m", 0.0) * PRED_WEIGHTS["6M"]
        + latest_df.get("prob_et10_1y", 0.0) * PRED_WEIGHTS["1Y"]
    )
    latest_df["score_et3"] = (
        latest_df.get("prob_et3_3m", 0.0) * PRED_WEIGHTS["3M"]
        + latest_df.get("prob_et3_6m", 0.0) * PRED_WEIGHTS["6M"]
        + latest_df.get("prob_et3_1y", 0.0) * PRED_WEIGHTS["1Y"]
    )
    latest_df["discovery_score"] = 0.6 * latest_df["score_et10"] + 0.4 * latest_df["score_et3"]
    latest_rank = latest_df.sort_values(["discovery_score", "score_et3", "score_et10", "ticker"], ascending=[False, False, False, True]).reset_index(drop=True)
    n = len(latest_rank)
    cut3 = max(1, int(math.ceil(n * 0.03)))
    cut10 = max(cut3 + 1, int(math.ceil(n * 0.10)))
    cut30 = max(cut10 + 1, int(math.ceil(n * 0.30)))
    cut50 = max(cut30 + 1, int(math.ceil(n * 0.50)))

    panel.to_csv(OUTDIR / "etf_tseries_feature_panel.csv", index=False, encoding="utf-8-sig")
    bucket_df.to_csv(OUTDIR / "etf_tseries_bucket_panel.csv", index=False, encoding="utf-8-sig")
    summary_df.to_csv(OUTDIR / "etf_tseries_model_summary.csv", index=False, encoding="utf-8-sig")
    compare_df.to_csv(OUTDIR / "etf_tseries_vs_s456_accuracy.csv", index=False, encoding="utf-8-sig")
    latest_rank.to_csv(OUTDIR / "etf_tseries_latest_full_rank_2026-03-31.csv", index=False, encoding="utf-8-sig")
    latest_rank.head(cut3).to_csv(OUTDIR / "etf_tseries_predicted_top3_2026-03-31.csv", index=False, encoding="utf-8-sig")
    latest_rank.head(cut10).to_csv(OUTDIR / "etf_tseries_predicted_top10_2026-03-31.csv", index=False, encoding="utf-8-sig")
    latest_rank.head(cut30).to_csv(OUTDIR / "etf_tseries_predicted_top30_2026-03-31.csv", index=False, encoding="utf-8-sig")
    latest_rank.head(cut50).to_csv(OUTDIR / "etf_tseries_predicted_top50_2026-03-31.csv", index=False, encoding="utf-8-sig")

    try:
        with pd.ExcelWriter(OUTDIR / "etf_tseries_pack_2026-03-31.xlsx") as writer:
            summary_df.to_excel(writer, sheet_name="model_summary", index=False)
            compare_df.to_excel(writer, sheet_name="vs_s456", index=False)
            latest_rank.to_excel(writer, sheet_name="latest_rank", index=False)
            latest_rank.head(cut10).to_excel(writer, sheet_name="top10", index=False)
    except Exception:
        pass

    import sqlite3
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        panel.to_sql("etf_tseries_feature_panel", con, if_exists="replace", index=False)
        bucket_df.to_sql("etf_tseries_bucket_panel", con, if_exists="replace", index=False)
        summary_df.to_sql("etf_tseries_model_summary", con, if_exists="replace", index=False)
        compare_df.to_sql("etf_tseries_vs_s456_accuracy", con, if_exists="replace", index=False)
        latest_rank.to_sql("etf_tseries_latest_rank", con, if_exists="replace", index=False)
    finally:
        con.close()

    lines = [
        "# ETF T-series Model V1",
        "",
        "- purpose: ETF core universe transition-based discovery model",
        "- universe: `D:/Quant/data/universe/universe_etf_extended_200_20260331.csv` (200 ETFs)",
        "- cadence: monthly trade dates from S4/S5/S6 allocation history",
        "- labels: ETF-T buckets from actual future 3M/6M/1Y return + path MDD",
        "- model: logistic regression for `ET10` and `ET3` by horizon",
        "",
        "## Latest predicted snapshots (2026-03-26)",
        f"- predicted Top3 count: {cut3}",
        f"- predicted Top10 count: {cut10}",
        f"- predicted Top30 count: {cut30}",
        f"- predicted Top50 count: {cut50}",
        "",
        "## Outputs",
        f"- {OUTDIR / 'etf_tseries_model_summary.csv'}",
        f"- {OUTDIR / 'etf_tseries_vs_s456_accuracy.csv'}",
        f"- {OUTDIR / 'etf_tseries_latest_full_rank_2026-03-31.csv'}",
    ]
    (OUTDIR / "etf_tseries_model_v2.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] outdir={OUTDIR}")
    print(f"[OK] latest_rank_n={len(latest_rank)} top3_n={cut3} top10_n={cut10}")


if __name__ == "__main__":
    main()
