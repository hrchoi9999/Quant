from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
OUT_DB = ROOT / r"data\db\i_series_research.db"
DEFAULT_UNIVERSE = ROOT / r"data\universe\universe_mix_top400_latest_priceready.csv"
DEFAULT_OUTDIR = ROOT / r"reports\i_series_stock_v01"


@dataclass
class BacktestMetrics:
    model_code: str
    start: str
    end: str
    rebalance_count: int
    top_n: int
    min_score: float
    selection_score: str
    regime_mode: str
    cagr: float
    total_return: float
    sharpe: float | None
    mdd: float
    avg_exposure: float
    win_rate_daily: float
    latest_holdings_count: int


HEAT_BUCKETS = ("early", "reacceleration", "overheated_watch")
QUALITY_FILTERS = (
    "none",
    "early_quality_guard_v1",
    "early_quality_guard_v2",
    "early_quality_v1",
    "early_quality_v2",
    "early_quality_v3",
)


def _read_universe(path: Path) -> pd.DataFrame:
    universe = pd.read_csv(path, dtype={"ticker": str})
    if "ticker" not in universe.columns:
        raise ValueError(f"universe file must have ticker column: {path}")
    universe["ticker"] = universe["ticker"].astype(str).str.zfill(6)
    if "name" not in universe.columns:
        universe["name"] = universe["ticker"]
    return universe.drop_duplicates("ticker").reset_index(drop=True)


def _load_prices(price_db: Path, tickers: list[str], start: str, asof: str) -> pd.DataFrame:
    placeholders = ",".join(["?"] * len(tickers))
    warmup_start = (pd.Timestamp(start) - pd.Timedelta(days=220)).strftime("%Y-%m-%d")
    with sqlite3.connect(str(price_db)) as con:
        prices = pd.read_sql_query(
            f"""
            SELECT ticker, date, open, high, low, close, volume, value
            FROM prices_daily
            WHERE ticker IN ({placeholders})
              AND date >= ?
              AND date <= ?
              AND close IS NOT NULL
            ORDER BY ticker, date
            """,
            con,
            params=[*tickers, warmup_start, asof],
            parse_dates=["date"],
        )
    if prices.empty:
        raise ValueError("no prices loaded")
    prices["ticker"] = prices["ticker"].astype(str).str.zfill(6)
    for col in ["open", "high", "low", "close", "volume", "value"]:
        prices[col] = pd.to_numeric(prices[col], errors="coerce")
    return prices.dropna(subset=["high", "low", "close"]).sort_values(["ticker", "date"]).reset_index(drop=True)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_features_one(
    frame: pd.DataFrame,
    use_liquidity_score: bool = True,
    require_conversion_base_for_buy: bool = True,
    signal_profile: str = "base",
) -> pd.DataFrame:
    frame = frame.sort_values("date").copy()
    high = frame["high"]
    low = frame["low"]
    close = frame["close"]

    conversion_9 = (high.rolling(9, min_periods=9).max() + low.rolling(9, min_periods=9).min()) / 2.0
    base_26 = (high.rolling(26, min_periods=26).max() + low.rolling(26, min_periods=26).min()) / 2.0
    span1_raw = (conversion_9 + base_26) / 2.0
    span2_raw = (high.rolling(52, min_periods=52).max() + low.rolling(52, min_periods=52).min()) / 2.0
    cloud_top = pd.concat([span1_raw, span2_raw], axis=1).max(axis=1)

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    macd_hist = macd - macd_signal

    frame["conversion_9"] = conversion_9
    frame["base_26"] = base_26
    frame["span1_raw"] = span1_raw
    frame["span2_raw"] = span2_raw
    frame["cloud_top"] = cloud_top
    frame["rsi14"] = _rsi(close, 14)
    frame["rsi14_delta_5d"] = frame["rsi14"] - frame["rsi14"].shift(5)
    frame["rsi14_delta_10d"] = frame["rsi14"] - frame["rsi14"].shift(10)
    frame["macd"] = macd
    frame["macd_signal"] = macd_signal
    frame["macd_hist"] = macd_hist
    frame["macd_hist_delta_5d"] = macd_hist - macd_hist.shift(5)
    frame["lagging_strength_26"] = close / close.shift(26) - 1.0
    frame["lagging_strength_delta_10d"] = frame["lagging_strength_26"] - frame["lagging_strength_26"].shift(10)
    frame["ret_21d"] = close.pct_change(21)
    frame["ret_63d"] = close.pct_change(63)
    frame["ret_126d"] = close.pct_change(126)
    frame["ret_252d"] = close.pct_change(252)
    frame["ret_5d"] = close.pct_change(5)
    frame["ma_20"] = close.rolling(20, min_periods=20).mean()
    frame["ma_60"] = close.rolling(60, min_periods=40).mean()
    frame["ma_120"] = close.rolling(120, min_periods=80).mean()
    frame["gap_ma20"] = close / frame["ma_20"] - 1.0
    frame["gap_ma60"] = close / frame["ma_60"] - 1.0
    frame["gap_ma120"] = close / frame["ma_120"] - 1.0
    frame["ma20_slope_20d"] = frame["ma_20"] / frame["ma_20"].shift(20) - 1.0
    frame["ma60_slope_20d"] = frame["ma_60"] / frame["ma_60"].shift(20) - 1.0
    daily_ret = close.pct_change()
    frame["realized_vol_20d"] = daily_ret.rolling(20, min_periods=15).std() * np.sqrt(252.0)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    frame["atr14_pct"] = true_range.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean() / close
    frame["drawdown_63d"] = close / high.rolling(63, min_periods=40).max() - 1.0
    frame["drawdown_126d"] = close / high.rolling(126, min_periods=80).max() - 1.0
    frame["ma_200"] = close.rolling(200, min_periods=120).mean()
    frame["gap_ma200"] = close / frame["ma_200"] - 1.0
    frame["high_252d"] = high.rolling(252, min_periods=120).max()
    frame["pct_below_52w_high"] = close / frame["high_252d"] - 1.0
    frame["gap_price_cloud"] = close / cloud_top - 1.0
    frame["gap_span1_span2"] = span1_raw / span2_raw - 1.0
    frame["gap_conversion_base"] = conversion_9 / base_26 - 1.0
    frame["gap_price_cloud_expansion_5d"] = frame["gap_price_cloud"] - frame["gap_price_cloud"].shift(5)
    frame["gap_price_cloud_expansion_10d"] = frame["gap_price_cloud"] - frame["gap_price_cloud"].shift(10)
    frame["gap_stability_10d"] = (frame["gap_price_cloud"] > 0).rolling(10, min_periods=10).mean()
    frame["cloud_width"] = (span1_raw - span2_raw).abs() / close.replace(0, np.nan)
    frame["cloud_width_expansion_10d"] = frame["cloud_width"] - frame["cloud_width"].shift(10)
    frame["ret_fwd_1w"] = close.shift(-5) / close - 1.0
    frame["ret_fwd_2w"] = close.shift(-10) / close - 1.0
    frame["ret_fwd_4w"] = close.shift(-20) / close - 1.0
    frame["ret_fwd_8w"] = close.shift(-40) / close - 1.0
    frame["ret_fwd_12w"] = close.shift(-60) / close - 1.0

    close_above_cloud = close > cloud_top
    conversion_above_base = conversion_9 > base_26
    cloud_bullish = span1_raw > span2_raw
    lagging_bullish = frame["lagging_strength_26"] > 0
    previous_above_cloud_10d = close_above_cloud.shift(1).rolling(10, min_periods=5).mean()
    cloud_breakout_10d = close_above_cloud & (previous_above_cloud_10d <= 0.3)
    cloud_reclaim_5d = close_above_cloud & (frame["gap_price_cloud"].shift(5) <= 0)
    recent_high_20 = high.shift(1).rolling(20, min_periods=10).max()
    recent_high_40 = high.shift(1).rolling(40, min_periods=20).max()
    breakout_20d = close >= recent_high_20 * 0.995
    breakout_40d = close >= recent_high_40 * 0.995
    ma5 = close.rolling(5, min_periods=5).mean()
    ma20 = close.rolling(20, min_periods=20).mean()
    pullback_reclaim_10d = (low.rolling(10, min_periods=5).min() <= cloud_top.rolling(10, min_periods=5).max() * 1.03) & (close > ma5) & (ma5 >= ma20)
    macd_hist_recovery = (frame["macd_hist_delta_5d"] > 0) & ((macd_hist > 0) | (macd_hist.shift(5) < 0))
    rsi = frame["rsi14"]
    rsi50_reclaim = (rsi >= 50) & (rsi.shift(5) < 50)
    price_near_or_above_cloud = (frame["gap_price_cloud"] >= -0.03) & (close > ma5)
    strong_initial_rsi = (
        (rsi >= 42)
        & (frame["rsi14_delta_10d"] >= 8)
        & macd_hist_recovery
        & price_near_or_above_cloud
    )

    frame["cloud_breakout_10d"] = cloud_breakout_10d
    frame["cloud_reclaim_5d"] = cloud_reclaim_5d
    frame["breakout_20d"] = breakout_20d
    frame["breakout_40d"] = breakout_40d
    frame["pullback_reclaim_10d"] = pullback_reclaim_10d
    frame["macd_hist_recovery"] = macd_hist_recovery
    frame["rsi50_reclaim"] = rsi50_reclaim
    frame["strong_initial_rsi"] = strong_initial_rsi
    frame["price_near_or_above_cloud"] = price_near_or_above_cloud

    alignment_score = (
        close_above_cloud.astype(float) * 8
        + conversion_above_base.astype(float) * 7
        + cloud_bullish.astype(float) * 7
        + lagging_bullish.astype(float) * 8
    )

    gap_score = (
        np.clip(frame["gap_price_cloud"].fillna(0) / 0.08, -1, 1) * 8
        + np.clip(frame["gap_span1_span2"].fillna(0) / 0.05, -1, 1) * 6
        + np.clip(frame["gap_conversion_base"].fillna(0) / 0.04, -1, 1) * 5
        + (frame["gap_price_cloud_expansion_10d"].fillna(0) >= 0).astype(float) * 3
        + np.clip(frame["gap_stability_10d"].fillna(0), 0, 1) * 3
    )
    gap_score = np.clip(gap_score, 0, 25)

    rsi_score = np.select(
        [
            (rsi >= 50) & (rsi <= 70),
            (rsi > 70) & (rsi <= 78),
            (rsi >= 45) & (rsi < 50),
        ],
        [18, 12, 8],
        default=0,
    )

    macd_score = (
        (macd > macd_signal).astype(float) * 9
        + (macd_hist > 0).astype(float) * 7
        + (frame["macd_hist_delta_5d"] >= 0).astype(float) * 4
    )

    liquidity_score = np.clip(np.log10(frame["value"].fillna(0).clip(lower=1)) - 8.0, 0, 1) * 7
    if not use_liquidity_score:
        liquidity_score = 0.0
    base_raw_score = alignment_score + gap_score + rsi_score + macd_score + liquidity_score
    base_score = np.clip(base_raw_score, 0, 100)

    early_price_score = (
        close_above_cloud.astype(float) * 10
        + lagging_bullish.astype(float) * 8
        + cloud_breakout_10d.astype(float) * 12
        + cloud_reclaim_5d.astype(float) * 8
        + breakout_20d.astype(float) * 8
        + breakout_40d.astype(float) * 5
        + pullback_reclaim_10d.astype(float) * 6
    )
    early_momentum_score = (
        macd_hist_recovery.astype(float) * 12
        + (frame["macd_hist_delta_5d"] > 0).astype(float) * 8
        + rsi50_reclaim.astype(float) * 9
        + np.select([(rsi >= 48) & (rsi <= 66), (rsi > 66) & (rsi <= 74)], [10, 5], default=0)
        + (frame["lagging_strength_delta_10d"] > 0).astype(float) * 8
    )
    early_gap_score = (
        np.clip(frame["gap_price_cloud"].fillna(0) / 0.06, -1, 1) * 7
        + (frame["gap_price_cloud_expansion_5d"].fillna(0) > 0).astype(float) * 5
        + (frame["cloud_width_expansion_10d"].fillna(0) >= 0).astype(float) * 4
        + cloud_bullish.astype(float) * 3
        + conversion_above_base.astype(float) * 3
    )
    early_raw_score = early_price_score + early_momentum_score + np.clip(early_gap_score, 0, 22)
    early_score = np.clip(early_raw_score, 0, 100)
    strong_rsi_price_score = (
        price_near_or_above_cloud.astype(float) * 10
        + close_above_cloud.astype(float) * 5
        + cloud_breakout_10d.astype(float) * 10
        + cloud_reclaim_5d.astype(float) * 8
        + breakout_20d.astype(float) * 7
        + breakout_40d.astype(float) * 4
        + pullback_reclaim_10d.astype(float) * 6
    )
    strong_rsi_momentum_score = (
        strong_initial_rsi.astype(float) * 18
        + np.clip(frame["rsi14_delta_10d"].fillna(0) / 12, 0, 1) * 10
        + np.clip(frame["rsi14_delta_5d"].fillna(0) / 6, 0, 1) * 6
        + macd_hist_recovery.astype(float) * 12
        + (frame["macd_hist_delta_5d"] > 0).astype(float) * 6
        + (frame["lagging_strength_delta_10d"] > 0).astype(float) * 8
    )
    strong_rsi_structure_score = (
        np.clip(frame["gap_price_cloud"].fillna(-0.10) / 0.05, -1, 1) * 6
        + (frame["gap_price_cloud_expansion_5d"].fillna(0) > 0).astype(float) * 5
        + cloud_bullish.astype(float) * 2
        + conversion_above_base.astype(float) * 2
    )
    strong_rsi_raw_score = strong_rsi_price_score + strong_rsi_momentum_score + np.clip(strong_rsi_structure_score, 0, 15)
    strong_rsi_score = np.clip(strong_rsi_raw_score, 0, 100)
    frame["i_raw_score_base"] = base_raw_score
    frame["i_raw_score_early"] = early_raw_score
    frame["i_raw_score_early_strong_rsi"] = strong_rsi_raw_score
    frame["i_score_base"] = base_score
    frame["i_score_early"] = early_score
    frame["i_score_early_strong_rsi"] = strong_rsi_score
    if signal_profile == "early":
        frame["i_raw_score"] = early_raw_score
        frame["i_score"] = early_score
    elif signal_profile == "early_strong_rsi":
        frame["i_raw_score"] = strong_rsi_raw_score
        frame["i_score"] = strong_rsi_score
    else:
        frame["i_raw_score"] = base_raw_score
        frame["i_score"] = base_score

    ret_1y = frame["ret_252d"].fillna(0.0)
    ret_3m = frame["ret_63d"].fillna(0.0)
    ret_1m = frame["ret_21d"].fillna(0.0)
    rsi_filled = frame["rsi14"].fillna(50.0)
    gap_ma200 = frame["gap_ma200"].fillna(0.0)
    pct_below_52w_high = frame["pct_below_52w_high"].fillna(-1.0)
    heat_penalty = (
        np.minimum(np.maximum(ret_1y - 0.5, 0.0) * 22.0, 35.0)
        + np.minimum(np.maximum(ret_3m - 0.3, 0.0) * 35.0, 20.0)
        + np.minimum(np.maximum(ret_1m - 0.18, 0.0) * 35.0, 10.0)
        + np.minimum(np.maximum(rsi_filled - 65.0, 0.0) * 1.4, 20.0)
        + np.minimum(np.maximum(gap_ma200 - 0.4, 0.0) * 25.0, 20.0)
        + np.where((pct_below_52w_high >= -0.03) & (ret_1y >= 0.8), 8.0, 0.0)
    )
    severe_overheat = (
        (ret_1y >= 2.0)
        | (gap_ma200 >= 1.2)
        | ((rsi_filled >= 75) & (ret_3m >= 0.35))
        | ((ret_1y >= 1.0) & (rsi_filled >= 70) & (gap_ma200 >= 0.7))
    )
    reacceleration = (
        (ret_1y >= 0.8)
        | (ret_3m >= 0.4)
        | (rsi_filled >= 70)
        | (gap_ma200 >= 0.6)
        | ((pct_below_52w_high >= -0.05) & (ret_1y >= 0.5))
    )
    frame["earlyness_score"] = np.clip(100.0 - heat_penalty, 0.0, 100.0)
    frame["heat_bucket"] = np.select(
        [severe_overheat, reacceleration],
        ["overheated_watch", "reacceleration"],
        default="early",
    )

    exit_watch = (
        (frame["gap_price_cloud"] > 0)
        & (frame["gap_price_cloud"] < frame["gap_price_cloud"].rolling(20, min_periods=10).max() * 0.45)
    ) | ((frame["macd_hist"] < 0) & (frame["macd_hist_delta_5d"] < 0))
    sell = (
        (frame["gap_price_cloud"] <= 0)
        | (frame["lagging_strength_26"] <= 0)
        | ((frame["rsi14"] < 45) & (frame["macd_hist"] < 0))
    )
    buy = (frame["i_score"] >= 75) & close_above_cloud & cloud_bullish & lagging_bullish
    if require_conversion_base_for_buy:
        buy = buy & conversion_above_base
    hold = (frame["i_score"] >= 60) & close_above_cloud & (frame["gap_stability_10d"] >= 0.6)
    if signal_profile == "early":
        buy = (
            (frame["i_score"] >= 68)
            & close_above_cloud
            & lagging_bullish
            & (
                cloud_breakout_10d
                | cloud_reclaim_5d
                | breakout_20d
                | (macd_hist_recovery & rsi50_reclaim)
            )
        )
        hold = (frame["i_score"] >= 58) & close_above_cloud & (frame["lagging_strength_delta_10d"] >= 0)
    elif signal_profile == "early_strong_rsi":
        buy = (
            (frame["i_score"] >= 68)
            & strong_initial_rsi
            & (
                cloud_breakout_10d
                | cloud_reclaim_5d
                | breakout_20d
                | pullback_reclaim_10d
                | close_above_cloud
            )
        )
        hold = (
            (frame["i_score"] >= 58)
            & price_near_or_above_cloud
            & (frame["rsi14_delta_10d"] >= 4)
            & (frame["macd_hist_delta_5d"] >= 0)
        )
    frame["i_signal"] = np.select(
        [sell, exit_watch, buy, hold],
        ["SELL", "EXIT_WATCH", "BUY", "HOLD"],
        default="NEUTRAL",
    )
    return frame


def build_features(
    prices: pd.DataFrame,
    start: str,
    use_liquidity_score: bool = True,
    require_conversion_base_for_buy: bool = True,
    signal_profile: str = "base",
) -> pd.DataFrame:
    frames = [
        _compute_features_one(
            frame,
            use_liquidity_score=use_liquidity_score,
            require_conversion_base_for_buy=require_conversion_base_for_buy,
            signal_profile=signal_profile,
        )
        for _, frame in prices.groupby("ticker", sort=False)
    ]
    features = pd.concat(frames, ignore_index=True)
    features = features.loc[features["date"] >= pd.Timestamp(start)].copy()
    return features.sort_values(["date", "ticker"]).reset_index(drop=True)


def _weekly_rebalance_dates(trading_dates: pd.Series, start: str, asof: str, weekday: int) -> list[pd.Timestamp]:
    available = pd.Series(pd.to_datetime(sorted(pd.unique(trading_dates))))
    anchors = pd.date_range(start=start, end=asof, freq="W-WED" if weekday == 2 else "W-FRI")
    dates: list[pd.Timestamp] = []
    last: pd.Timestamp | None = None
    for anchor in anchors:
        candidates = available.loc[available <= anchor]
        if candidates.empty:
            continue
        chosen = pd.Timestamp(candidates.iloc[-1])
        if last is None or chosen > last:
            dates.append(chosen)
            last = chosen
    return dates


def build_weekly_signals(features: pd.DataFrame, universe: pd.DataFrame, start: str, asof: str, weekday: int) -> pd.DataFrame:
    dates = _weekly_rebalance_dates(features["date"], start, asof, weekday)
    weekly = features.loc[features["date"].isin(dates)].copy()
    weekly = weekly.merge(universe[["ticker", "name", "market"]], on="ticker", how="left", suffixes=("", "_univ"))
    weekly["universe_rank_no"] = (
        weekly.sort_values(["date", "i_raw_score", "ticker"], ascending=[True, False, True])
        .groupby("date")
        .cumcount()
        + 1
    )
    universe_count = weekly.groupby("date")["ticker"].transform("nunique")
    weekly["universe_rank_score"] = np.where(
        universe_count > 1,
        (1.0 - (weekly["universe_rank_no"] - 1) / (universe_count - 1)) * 100.0,
        100.0,
    )
    weekly["rank_no"] = weekly["universe_rank_no"]
    return weekly.sort_values(["date", "universe_rank_no"]).reset_index(drop=True)


def build_regime_daily(features: pd.DataFrame) -> pd.DataFrame:
    work = features.copy()
    work["above_cloud"] = work["gap_price_cloud"] > 0
    work["bullish_alignment"] = (
        (work["gap_price_cloud"] > 0)
        & (work["gap_conversion_base"] > 0)
        & (work["gap_span1_span2"] > 0)
        & (work["lagging_strength_26"] > 0)
    )
    work["buy_or_hold"] = work["i_signal"].isin(["BUY", "HOLD"])
    regime = (
        work.groupby("date")
        .agg(
            universe_count=("ticker", "nunique"),
            breadth_above_cloud=("above_cloud", "mean"),
            breadth_bullish_alignment=("bullish_alignment", "mean"),
            breadth_buy_hold=("buy_or_hold", "mean"),
            median_gap_price_cloud=("gap_price_cloud", "median"),
            median_i_score=("i_score", "median"),
        )
        .reset_index()
        .sort_values("date")
    )
    return regime


def _target_exposure_from_regime(row: pd.Series | None, mode: str) -> float:
    if mode == "none":
        return 1.0
    if row is None:
        return 0.0

    breadth = float(row.get("breadth_above_cloud", 0.0) or 0.0)
    buy_hold = float(row.get("breadth_buy_hold", 0.0) or 0.0)
    median_gap = float(row.get("median_gap_price_cloud", 0.0) or 0.0)

    if mode == "conservative":
        if breadth >= 0.55 and buy_hold >= 0.18 and median_gap >= 0.01:
            return 1.0
        if breadth >= 0.45 and buy_hold >= 0.14 and median_gap >= 0.0:
            return 0.70
        if breadth >= 0.35 and buy_hold >= 0.10:
            return 0.40
        return 0.0
    if mode == "moderate":
        if breadth >= 0.45 and buy_hold >= 0.14 and median_gap >= 0.0:
            return 1.0
        if breadth >= 0.35 and buy_hold >= 0.10:
            return 0.70
        if breadth >= 0.25 and buy_hold >= 0.06:
            return 0.40
        return 0.0
    if mode == "aggressive":
        if breadth >= 0.35 and buy_hold >= 0.10:
            return 1.0
        if breadth >= 0.25 and buy_hold >= 0.06:
            return 0.80
        if breadth >= 0.15 and buy_hold >= 0.03:
            return 0.50
        return 0.0
    raise ValueError(f"unknown regime mode: {mode}")


def _apply_quality_filter(frame: pd.DataFrame, quality_filter: str) -> pd.DataFrame:
    if quality_filter == "none" or frame.empty:
        return frame
    if quality_filter not in QUALITY_FILTERS:
        raise ValueError(f"unknown quality filter: {quality_filter}")

    rsi = pd.to_numeric(frame["rsi14"], errors="coerce")
    ret_21d = pd.to_numeric(frame["ret_21d"], errors="coerce")
    ret_63d = pd.to_numeric(frame["ret_63d"], errors="coerce")
    gap_ma20 = pd.to_numeric(frame["gap_ma20"], errors="coerce")
    gap_ma60 = pd.to_numeric(frame["gap_ma60"], errors="coerce")
    ma20_slope = pd.to_numeric(frame["ma20_slope_20d"], errors="coerce")
    ma60_slope = pd.to_numeric(frame["ma60_slope_20d"], errors="coerce")
    macd_hist_delta = pd.to_numeric(frame["macd_hist_delta_5d"], errors="coerce")
    realized_vol = pd.to_numeric(frame["realized_vol_20d"], errors="coerce")
    atr14_pct = pd.to_numeric(frame["atr14_pct"], errors="coerce")
    drawdown_63d = pd.to_numeric(frame["drawdown_63d"], errors="coerce")

    if quality_filter == "early_quality_guard_v1":
        mask = (
            (rsi >= 48)
            & (rsi <= 69)
            & (ret_21d >= -0.10)
            & (gap_ma20 >= -0.08)
            & (drawdown_63d >= -0.40)
            & (realized_vol <= 1.25)
            & (atr14_pct <= 0.11)
        )
        return frame.loc[mask.fillna(False)].copy()
    if quality_filter == "early_quality_guard_v2":
        mask = (
            (rsi >= 50)
            & (rsi <= 68)
            & (ret_21d >= -0.05)
            & (ret_63d >= -0.25)
            & (gap_ma20 >= -0.05)
            & (ma20_slope >= -0.04)
            & (drawdown_63d >= -0.35)
            & (realized_vol <= 1.00)
            & (atr14_pct <= 0.09)
        )
        return frame.loc[mask.fillna(False)].copy()

    mask = (
        (rsi >= 50)
        & (rsi <= 68)
        & (gap_ma20 >= -0.02)
        & (ma20_slope >= -0.01)
        & (macd_hist_delta >= 0)
    )
    if quality_filter in {"early_quality_v2", "early_quality_v3"}:
        mask = mask & (ret_21d >= 0) & (gap_ma60 >= -0.05) & (drawdown_63d >= -0.25)
        mask = mask & (realized_vol <= 0.85) & (atr14_pct <= 0.075)
    if quality_filter == "early_quality_v3":
        mask = mask & (rsi <= 66) & (ret_63d >= -0.15) & (ma60_slope >= -0.02)
        mask = mask & (realized_vol <= 0.65) & (atr14_pct <= 0.06)
    return frame.loc[mask.fillna(False)].copy()


def _portfolio_nav(
    features: pd.DataFrame,
    signals: pd.DataFrame,
    regime_daily: pd.DataFrame,
    top_n: int,
    min_score: float,
    fee_bps: float,
    slippage_bps: float,
    regime_mode: str,
    selection_score: str,
    heat_include: set[str] | None = None,
    heat_exclude: set[str] | None = None,
    quality_filter: str = "none",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    close = features.pivot(index="date", columns="ticker", values="close").sort_index().ffill()
    daily_ret = close.pct_change().fillna(0.0)
    rebalance_dates = sorted(pd.to_datetime(signals["date"].drop_duplicates()))
    if not rebalance_dates:
        return pd.DataFrame(), pd.DataFrame()

    regime_by_date = regime_daily.set_index("date").sort_index()
    cost = (fee_bps + slippage_bps) / 10000.0
    nav = 1.0
    prev_weights: dict[str, float] = {}
    nav_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    selection_score_col = {
        "display": "i_score",
        "raw": "i_raw_score",
        "rank": "universe_rank_score",
    }[selection_score]

    for idx, reb_date in enumerate(rebalance_dates):
        day_signals = signals.loc[signals["date"] == reb_date].copy()
        regime_row = regime_by_date.loc[reb_date] if reb_date in regime_by_date.index else None
        target_exposure = _target_exposure_from_regime(regime_row, regime_mode)
        eligible = day_signals.loc[
            day_signals["i_signal"].isin(["BUY", "HOLD"]) & (day_signals["i_score"] >= min_score)
        ].copy()
        if heat_include:
            eligible = eligible.loc[eligible["heat_bucket"].isin(heat_include)].copy()
        if heat_exclude:
            eligible = eligible.loc[~eligible["heat_bucket"].isin(heat_exclude)].copy()
        eligible = _apply_quality_filter(eligible, quality_filter)
        eligible = eligible.sort_values([selection_score_col, "i_raw_score", "ticker"], ascending=[False, False, True]).head(top_n)
        if target_exposure <= 0:
            eligible = eligible.iloc[0:0].copy()
        tickers = [str(t) for t in eligible["ticker"].tolist()]
        weights = {ticker: target_exposure / len(tickers) for ticker in tickers} if tickers and target_exposure > 0 else {}
        turnover = 0.5 * sum(abs(weights.get(t, 0.0) - prev_weights.get(t, 0.0)) for t in set(weights) | set(prev_weights))
        nav *= 1.0 - turnover * cost

        for rank_no, row in enumerate(eligible.itertuples(index=False), start=1):
            holding_rows.append(
                {
                    "date": reb_date.strftime("%Y-%m-%d"),
                    "ticker": row.ticker,
                    "name": getattr(row, "name", None),
                    "rank_no": rank_no,
                    "portfolio_rank_no": rank_no,
                    "universe_rank_no": int(row.universe_rank_no),
                    "universe_rank_score": round(float(row.universe_rank_score), 6),
                    "weight": weights[str(row.ticker)],
                    "i_raw_score": round(float(row.i_raw_score), 6),
                    "i_score": round(float(row.i_score), 6),
                    "i_signal": row.i_signal,
                    "heat_bucket": getattr(row, "heat_bucket", None),
                    "earlyness_score": None if pd.isna(getattr(row, "earlyness_score", np.nan)) else round(float(row.earlyness_score), 6),
                    "quality_filter": quality_filter,
                    "rsi14": None if pd.isna(getattr(row, "rsi14", np.nan)) else round(float(row.rsi14), 6),
                    "gap_ma20": None if pd.isna(getattr(row, "gap_ma20", np.nan)) else round(float(row.gap_ma20), 6),
                    "gap_ma60": None if pd.isna(getattr(row, "gap_ma60", np.nan)) else round(float(row.gap_ma60), 6),
                    "ma20_slope_20d": None if pd.isna(getattr(row, "ma20_slope_20d", np.nan)) else round(float(row.ma20_slope_20d), 6),
                    "ma60_slope_20d": None if pd.isna(getattr(row, "ma60_slope_20d", np.nan)) else round(float(row.ma60_slope_20d), 6),
                    "realized_vol_20d": None if pd.isna(getattr(row, "realized_vol_20d", np.nan)) else round(float(row.realized_vol_20d), 6),
                    "atr14_pct": None if pd.isna(getattr(row, "atr14_pct", np.nan)) else round(float(row.atr14_pct), 6),
                    "drawdown_63d": None if pd.isna(getattr(row, "drawdown_63d", np.nan)) else round(float(row.drawdown_63d), 6),
                }
            )

        next_reb = rebalance_dates[idx + 1] if idx + 1 < len(rebalance_dates) else close.index.max()
        period_dates = close.index[(close.index >= reb_date) & (close.index <= next_reb)]
        for day in period_dates:
            if day == reb_date:
                nav_rows.append(
                    {
                        "date": day.strftime("%Y-%m-%d"),
                        "nav": nav,
                        "daily_return": 0.0,
                        "holdings_count": len(weights),
                        "exposure": sum(weights.values()) if weights else 0.0,
                        "turnover": turnover,
                        "regime_mode": regime_mode,
                    }
                )
                continue
            if weights:
                ret = float(sum(weights[t] * daily_ret.at[day, t] for t in weights if t in daily_ret.columns))
            else:
                ret = 0.0
            nav *= 1.0 + ret
            nav_rows.append(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "nav": nav,
                    "daily_return": ret,
                    "holdings_count": len(weights),
                    "exposure": sum(weights.values()) if weights else 0.0,
                    "turnover": 0.0,
                    "regime_mode": regime_mode,
                }
            )
        prev_weights = weights

    nav_df = pd.DataFrame(nav_rows).drop_duplicates("date", keep="last").sort_values("date")
    holdings_df = pd.DataFrame(holding_rows)
    return nav_df, holdings_df


def _metrics(nav_df: pd.DataFrame, top_n: int, min_score: float, selection_score: str, regime_mode: str) -> BacktestMetrics:
    work = nav_df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date")
    start_nav = float(work["nav"].iloc[0])
    end_nav = float(work["nav"].iloc[-1])
    days = max((work["date"].iloc[-1] - work["date"].iloc[0]).days, 1)
    total_return = end_nav / start_nav - 1.0
    cagr = (end_nav / start_nav) ** (365.25 / days) - 1.0
    dd = work["nav"] / work["nav"].cummax() - 1.0
    rets = pd.to_numeric(work["daily_return"], errors="coerce").fillna(0.0)
    std = float(rets.std(ddof=0))
    sharpe = None if std <= 0 else float(rets.mean() / std * np.sqrt(252))
    return BacktestMetrics(
        model_code="I-STOCK-V01",
        start=work["date"].iloc[0].strftime("%Y-%m-%d"),
        end=work["date"].iloc[-1].strftime("%Y-%m-%d"),
        rebalance_count=int((work["turnover"] > 0).sum()),
        top_n=top_n,
        min_score=float(min_score),
        selection_score=selection_score,
        regime_mode=regime_mode,
        cagr=float(cagr),
        total_return=float(total_return),
        sharpe=sharpe,
        mdd=float(dd.min()),
        avg_exposure=float(work["exposure"].mean()),
        win_rate_daily=float((rets > 0).mean()),
        latest_holdings_count=int(work["holdings_count"].iloc[-1]),
    )


def _forward_return_summary(signals: pd.DataFrame) -> pd.DataFrame:
    buckets = []
    work = signals.copy()
    work["score_bucket"] = pd.cut(
        work["i_score"],
        bins=[-0.01, 40, 55, 65, 75, 100],
        labels=["<=40", "40-55", "55-65", "65-75", "75+"],
    )
    for group_col in ["i_signal", "score_bucket", "heat_bucket"]:
        for key, frame in work.groupby(group_col, dropna=False):
            row = {"group_type": group_col, "group": str(key), "obs_n": int(len(frame))}
            for horizon in ["1w", "2w", "4w", "8w", "12w"]:
                col = f"ret_fwd_{horizon}"
                vals = pd.to_numeric(frame[col], errors="coerce").dropna()
                row[f"avg_{horizon}"] = None if vals.empty else float(vals.mean())
                row[f"win_{horizon}"] = None if vals.empty else float((vals > 0).mean())
            buckets.append(row)
    return pd.DataFrame(buckets)


def _write_sqlite(db_path: Path, tables: dict[str, pd.DataFrame]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as con:
        for table, df in tables.items():
            df.to_sql(table, con, if_exists="replace", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build I-STOCK-V01 Ichimoku/RSI/MACD research model.")
    ap.add_argument("--model-code", default="I-STOCK-V01")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--universe-csv", default=str(DEFAULT_UNIVERSE))
    ap.add_argument("--price-db", default=str(PRICE_DB))
    ap.add_argument("--out-db", default=str(OUT_DB))
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--min-score", type=float, default=65.0)
    ap.add_argument(
        "--selection-score",
        choices=["display", "raw", "rank"],
        default="display",
        help="Score used to select top N. display uses capped i_score; raw uses uncapped i_raw_score; rank uses universe percentile score.",
    )
    ap.add_argument("--rebalance-weekday", type=int, default=2)
    ap.add_argument("--fee-bps", type=float, default=5.0)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument(
        "--signal-profile",
        choices=["base", "early", "early_strong_rsi"],
        default="base",
        help="base is the original trend-confirmation profile; early targets early cloud breakouts and reclaims.",
    )
    ap.add_argument(
        "--disable-liquidity-score",
        action="store_true",
        help="Remove trading value/liquidity from I-score. Liquidity remains a universe quality concern outside this model.",
    )
    ap.add_argument(
        "--disable-buy-conversion-filter",
        action="store_true",
        help="Remove conversion_9 > base_26 from the mandatory BUY condition.",
    )
    ap.add_argument(
        "--regime-mode",
        choices=["none", "conservative", "moderate", "aggressive"],
        default="none",
        help="Universe breadth gate for portfolio exposure. none keeps the original always-invested behavior.",
    )
    ap.add_argument(
        "--heat-include",
        default=None,
        help="Comma-separated heat buckets eligible for selection: early,reacceleration,overheated_watch. Default keeps all.",
    )
    ap.add_argument(
        "--heat-exclude",
        default=None,
        help="Comma-separated heat buckets excluded from selection. Example: early.",
    )
    ap.add_argument(
        "--quality-filter",
        choices=QUALITY_FILTERS,
        default="none",
        help="Optional technical quality filter applied after heat bucket filtering.",
    )
    args = ap.parse_args()

    universe_path = Path(args.universe_csv)
    price_db = Path(args.price_db)
    out_db = Path(args.out_db)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    universe = _read_universe(universe_path)
    with sqlite3.connect(str(price_db)) as con:
        latest_price_date = con.execute("SELECT max(date) FROM prices_daily").fetchone()[0]
    asof = args.asof or latest_price_date

    prices = _load_prices(price_db, universe["ticker"].tolist(), args.start, asof)
    features = build_features(
        prices,
        args.start,
        use_liquidity_score=not args.disable_liquidity_score,
        require_conversion_base_for_buy=not args.disable_buy_conversion_filter,
        signal_profile=args.signal_profile,
    )
    signals = build_weekly_signals(features, universe, args.start, asof, args.rebalance_weekday)
    regime_daily = build_regime_daily(features)
    heat_include = set(args.heat_include.split(",")) if args.heat_include else None
    heat_exclude = set(args.heat_exclude.split(",")) if args.heat_exclude else None
    for label, buckets in {"heat_include": heat_include, "heat_exclude": heat_exclude}.items():
        if buckets and not buckets.issubset(set(HEAT_BUCKETS)):
            raise SystemExit(f"{label} contains unsupported buckets: {sorted(buckets - set(HEAT_BUCKETS))}")
    nav_df, holdings_df = _portfolio_nav(
        features,
        signals,
        regime_daily,
        args.top_n,
        args.min_score,
        args.fee_bps,
        args.slippage_bps,
        args.regime_mode,
        args.selection_score,
        heat_include,
        heat_exclude,
        args.quality_filter,
    )
    metrics = _metrics(nav_df, args.top_n, args.min_score, args.selection_score, args.regime_mode)
    metrics.model_code = args.model_code
    fwd_summary = _forward_return_summary(signals)

    run_meta = pd.DataFrame(
        [
            {
                "model_code": args.model_code,
                "asof_date": asof,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "universe_csv": str(universe_path),
                "universe_n": int(universe["ticker"].nunique()),
                "start": args.start,
                "top_n": args.top_n,
                "min_score": args.min_score,
                "selection_score": args.selection_score,
                "signal_profile": args.signal_profile,
                "regime_mode": args.regime_mode,
                "heat_include": None if heat_include is None else ",".join(sorted(heat_include)),
                "heat_exclude": None if heat_exclude is None else ",".join(sorted(heat_exclude)),
                "quality_filter": args.quality_filter,
                "use_liquidity_score": not args.disable_liquidity_score,
                "require_conversion_base_for_buy": not args.disable_buy_conversion_filter,
                "rebalance_weekday": args.rebalance_weekday,
                "fee_bps": args.fee_bps,
                "slippage_bps": args.slippage_bps,
                "notes": "I-series research model using no-lookahead Ichimoku raw spans, RSI14, and MACD 12/26/9.",
            }
        ]
    )

    keep_feature_cols = [
        "ticker", "date", "close", "volume", "value", "conversion_9", "base_26", "span1_raw", "span2_raw",
        "cloud_top", "rsi14", "rsi14_delta_5d", "rsi14_delta_10d", "macd", "macd_signal", "macd_hist", "macd_hist_delta_5d",
        "lagging_strength_26", "lagging_strength_delta_10d", "gap_price_cloud", "gap_span1_span2", "gap_conversion_base",
        "ret_5d", "ret_21d", "ret_63d", "ret_126d", "ret_252d",
        "ma_20", "ma_60", "ma_120", "ma_200",
        "gap_ma20", "gap_ma60", "gap_ma120", "gap_ma200",
        "ma20_slope_20d", "ma60_slope_20d",
        "realized_vol_20d", "atr14_pct", "drawdown_63d", "drawdown_126d",
        "high_252d", "pct_below_52w_high",
        "gap_price_cloud_expansion_5d", "gap_price_cloud_expansion_10d", "gap_stability_10d",
        "i_raw_score", "i_score", "i_signal",
        "heat_bucket", "earlyness_score",
        "i_raw_score_base", "i_raw_score_early", "i_raw_score_early_strong_rsi",
        "i_score_base", "i_score_early", "i_score_early_strong_rsi", "cloud_width", "cloud_width_expansion_10d",
        "cloud_breakout_10d", "cloud_reclaim_5d", "breakout_20d", "breakout_40d",
        "pullback_reclaim_10d", "macd_hist_recovery", "rsi50_reclaim", "strong_initial_rsi", "price_near_or_above_cloud",
        "ret_fwd_1w", "ret_fwd_2w", "ret_fwd_4w", "ret_fwd_8w", "ret_fwd_12w",
    ]
    _write_sqlite(
        out_db,
        {
            "i_stock_v01_run_meta": run_meta,
            "i_stock_v01_features_daily": features[keep_feature_cols],
            "i_stock_v01_signals_weekly": signals,
            "i_stock_v01_regime_daily": regime_daily,
            "i_stock_v01_backtest_nav": nav_df,
            "i_stock_v01_backtest_holdings": holdings_df,
            "i_stock_v01_forward_return_summary": fwd_summary,
            "i_stock_v01_backtest_summary": pd.DataFrame([asdict(metrics)]),
        },
    )

    summary_path = outdir / f"i_stock_v01_summary_{asof.replace('-', '')}.json"
    md_path = outdir / f"I_STOCK_V01_RESEARCH_SUMMARY_{asof.replace('-', '')}.md"
    payload = {"metrics": asdict(metrics), "run_meta": run_meta.iloc[0].to_dict()}
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_signals = signals.loc[signals["date"] == signals["date"].max()].copy()
    latest_top = latest_signals.sort_values(["i_raw_score", "ticker"], ascending=[False, True]).head(20)
    md = [
        f"# I-STOCK-V01 Research Summary ({asof})",
        "",
        "## Backtest",
        "",
        f"- Universe: {len(universe):,} stocks",
        f"- Start: {metrics.start}",
        f"- End: {metrics.end}",
        f"- Top N: {metrics.top_n}",
        f"- Min score: {metrics.min_score:.1f}",
        f"- Selection score: {metrics.selection_score}",
        f"- Signal profile: {args.signal_profile}",
        f"- Regime mode: {metrics.regime_mode}",
        f"- Quality filter: {args.quality_filter}",
        f"- CAGR: {metrics.cagr:.2%}",
        f"- Total return: {metrics.total_return:.2%}",
        f"- MDD: {metrics.mdd:.2%}",
        f"- Sharpe: {'n/a' if metrics.sharpe is None else f'{metrics.sharpe:.2f}'}",
        f"- Avg exposure: {metrics.avg_exposure:.2%}",
        "",
        "## Latest Top Signals",
        "",
        "| universe_rank | ticker | name | signal | raw_score | display_score | rsi14 | gap_price_cloud | lagging_strength_26 |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in latest_top.itertuples(index=False):
        md.append(
            f"| {int(row.universe_rank_no)} | {row.ticker} | {row.name} | {row.i_signal} | "
            f"{float(row.i_raw_score):.2f} | {float(row.i_score):.2f} | "
            f"{float(row.rsi14) if pd.notna(row.rsi14) else np.nan:.2f} | "
            f"{float(row.gap_price_cloud) if pd.notna(row.gap_price_cloud) else np.nan:.2%} | "
            f"{float(row.lagging_strength_26) if pd.notna(row.lagging_strength_26) else np.nan:.2%} |"
        )
    latest_holdings = holdings_df.loc[holdings_df["date"] == holdings_df["date"].max()].copy() if not holdings_df.empty else pd.DataFrame()
    if not latest_holdings.empty:
        md.append("")
        md.append("## Latest Portfolio Holdings")
        md.append("")
        md.append("| rank | ticker | name | raw_score | display_score | heat_bucket | earlyness_score | weight |")
        md.append("| ---: | --- | --- | ---: | ---: | --- | ---: | ---: |")
        for row in latest_holdings.sort_values("rank_no").itertuples(index=False):
            md.append(
                f"| {int(row.rank_no)} | {row.ticker} | {row.name} | "
                f"{float(row.i_raw_score):.2f} | {float(row.i_score):.2f} | "
                f"{getattr(row, 'heat_bucket', '')} | "
                f"{float(row.earlyness_score) if pd.notna(row.earlyness_score) else np.nan:.2f} | "
                f"{float(row.weight):.2%} |"
            )
    md.append("")
    md.append("## Stored Tables")
    md.append("")
    md.append(f"- SQLite DB: `{out_db}`")
    md.append("- `i_stock_v01_features_daily`")
    md.append("- `i_stock_v01_signals_weekly`")
    md.append("- `i_stock_v01_backtest_nav`")
    md.append("- `i_stock_v01_backtest_holdings`")
    md.append("- `i_stock_v01_forward_return_summary`")
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "asof": asof,
        "universe_n": int(len(universe)),
        "feature_rows": int(len(features)),
        "weekly_signal_rows": int(len(signals)),
        "nav_rows": int(len(nav_df)),
        "db": str(out_db),
        "summary": str(summary_path),
        "markdown": str(md_path),
        "metrics": asdict(metrics),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
