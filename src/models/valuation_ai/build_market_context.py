# build_market_context.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .common import norm_ticker, now_ts, read_sql, write_table
from .config import (
    CLASSIFICATION_DB,
    DEFAULT_UNIVERSE,
    MARKET_CONTEXT_DAILY_TABLE,
    MARKET_CONTEXT_MONTHLY_TABLE,
    OUT_DB,
    PRICE_DB,
    REGIME_DB,
    REPORT_DIR,
)


MARKET_SCOPES = ["ALL", "KOSPI", "KOSDAQ"]


def _load_universe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ticker": str})
    df["ticker"] = df["ticker"].map(norm_ticker)
    return df.dropna(subset=["ticker"]).drop_duplicates("ticker")


def _load_classification() -> pd.DataFrame:
    if not CLASSIFICATION_DB.exists():
        return pd.DataFrame(columns=["ticker", "market"])
    df = read_sql(
        CLASSIFICATION_DB,
        """
        SELECT ticker, market
        FROM security_classification_master
        WHERE is_active = 1
        """,
    )
    if df.empty:
        return pd.DataFrame(columns=["ticker", "market"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df.drop_duplicates("ticker", keep="last")


def _attach_market(universe: pd.DataFrame) -> pd.DataFrame:
    cls = _load_classification()
    out = universe[["ticker", "name", "market"]].copy() if "market" in universe.columns else universe[["ticker", "name"]].copy()
    if "market" not in out.columns:
        out["market"] = None
    if not cls.empty:
        out = out.merge(cls, on="ticker", how="left", suffixes=("", "_cls"))
        out["market"] = out["market"].fillna(out.get("market_cls"))
    out["market"] = out["market"].fillna("UNKNOWN")
    out["market_scope"] = np.where(out["market"].isin(["KOSPI", "KOSDAQ"]), out["market"], "ALL")
    return out[["ticker", "name", "market", "market_scope"]].drop_duplicates("ticker")


def _load_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(tickers))
    start_ts = (pd.Timestamp(start) - pd.Timedelta(days=520)).strftime("%Y-%m-%d")
    df = read_sql(
        PRICE_DB,
        f"""
        SELECT ticker, date, close
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND date BETWEEN ? AND ?
          AND close IS NOT NULL
        ORDER BY ticker, date
        """,
        [*tickers, start_ts, end],
        parse_dates=["date"],
    )
    if df.empty:
        raise SystemExit("no prices loaded for market context")
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["ticker", "date", "close"])


def _load_regime(tickers: list[str], start: str, end: str, horizon: str) -> pd.DataFrame:
    if not REGIME_DB.exists() or not tickers:
        return pd.DataFrame(columns=["ticker", "date", "regime_score", "regime", "regime_ret", "regime_dd", "regime_vol"])
    placeholders = ",".join(["?"] * len(tickers))
    try:
        df = read_sql(
            REGIME_DB,
            f"""
            SELECT ticker, date, score AS regime_score, regime, ret AS regime_ret, dd AS regime_dd, vol AS regime_vol
            FROM regime_history
            WHERE ticker IN ({placeholders})
              AND horizon = ?
              AND date BETWEEN ? AND ?
            """,
            [*tickers, horizon, start, end],
            parse_dates=["date"],
        )
    except Exception:
        return pd.DataFrame(columns=["ticker", "date", "regime_score", "regime", "regime_ret", "regime_dd", "regime_vol"])
    if df.empty:
        return df
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in ["regime_score", "regime", "regime_ret", "regime_dd", "regime_vol"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["ticker", "date"])


def _price_daily_features(prices: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ticker, g in prices.groupby("ticker", sort=False):
        g = g.sort_values("date").copy()
        close = g["close"]
        g["ret_1m"] = close.pct_change(20)
        g["ret_3m"] = close.pct_change(60)
        g["ret_6m"] = close.pct_change(126)
        daily_ret = close.pct_change()
        g["vol_20d"] = daily_ret.rolling(20, min_periods=10).std()
        peak_60 = close.rolling(60, min_periods=20).max()
        g["mdd_3m"] = (close / peak_60 - 1.0).rolling(60, min_periods=20).min()
        sma60 = close.rolling(60, min_periods=20).mean()
        sma120 = close.rolling(120, min_periods=40).mean()
        g["above_sma60"] = (close > sma60).astype(float)
        g["above_sma120"] = (close > sma120).astype(float)
        g["ret_pos_1m"] = (g["ret_1m"] > 0).astype(float)
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def _scope_frames(frame: pd.DataFrame) -> pd.DataFrame:
    all_frame = frame.copy()
    all_frame["market_scope"] = "ALL"
    market_frame = frame[frame["market_scope"].isin(["KOSPI", "KOSDAQ"])].copy()
    return pd.concat([all_frame, market_frame], ignore_index=True, sort=False)


def _regime_label(score: float | None, bullish_pct: float | None, bearish_pct: float | None) -> str:
    if score is None or pd.isna(score):
        return "unknown"
    if score >= 0.68 and (bullish_pct or 0) >= 0.45:
        return "strong_up"
    if score >= 0.58:
        return "up"
    if score <= 0.32 and (bearish_pct or 0) >= 0.45:
        return "strong_down"
    if score <= 0.42:
        return "down"
    return "neutral"


def build_market_context(
    universe: Path,
    start: str,
    end: str,
    out_db: Path = OUT_DB,
    regime_horizon: str = "3m",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    uni = _attach_market(_load_universe(universe))
    tickers = sorted(uni["ticker"].dropna().unique().tolist())
    price_features = _price_daily_features(_load_prices(tickers, start, end))
    price_features = price_features.merge(uni[["ticker", "market_scope"]], on="ticker", how="left")
    price_scoped = _scope_frames(price_features)
    price_ctx = (
        price_scoped.groupby(["date", "market_scope"], as_index=False)
        .agg(
            market_ret_1m=("ret_1m", "median"),
            market_ret_3m=("ret_3m", "median"),
            market_ret_6m=("ret_6m", "median"),
            market_vol_20d=("vol_20d", "median"),
            market_mdd_3m=("mdd_3m", "median"),
            market_breadth_ret_pos_1m=("ret_pos_1m", "mean"),
            market_breadth_above_sma60=("above_sma60", "mean"),
            market_breadth_above_sma120=("above_sma120", "mean"),
            market_context_price_count=("ticker", "nunique"),
        )
    )

    regime = _load_regime(tickers, start, end, regime_horizon)
    if not regime.empty:
        regime = regime.merge(uni[["ticker", "market_scope"]], on="ticker", how="left")
        regime_scoped = _scope_frames(regime)
        regime_scoped["is_bullish"] = (regime_scoped["regime"] >= 3).astype(float)
        regime_scoped["is_bearish"] = (regime_scoped["regime"] <= 1).astype(float)
        regime_scoped["is_neutral"] = (regime_scoped["regime"] == 2).astype(float)
        regime_ctx = (
            regime_scoped.groupby(["date", "market_scope"], as_index=False)
            .agg(
                market_regime_score=("regime_score", "mean"),
                market_regime=("regime", "mean"),
                market_regime_bullish_pct=("is_bullish", "mean"),
                market_regime_bearish_pct=("is_bearish", "mean"),
                market_regime_neutral_pct=("is_neutral", "mean"),
                market_context_regime_count=("ticker", "nunique"),
            )
        )
    else:
        regime_ctx = pd.DataFrame(columns=["date", "market_scope"])

    daily = price_ctx.merge(regime_ctx, on=["date", "market_scope"], how="left")
    daily = daily[daily["date"].between(pd.Timestamp(start), pd.Timestamp(end))].copy()
    daily["market_regime_label"] = [
        _regime_label(score, bull, bear)
        for score, bull, bear in zip(
            daily.get("market_regime_score"),
            daily.get("market_regime_bullish_pct"),
            daily.get("market_regime_bearish_pct"),
            strict=False,
        )
    ]
    daily["market_context_available"] = (
        daily["market_context_price_count"].fillna(0).gt(0)
        & daily.get("market_regime_score", pd.Series(index=daily.index, dtype=float)).notna()
    ).astype(int)
    daily["regime_horizon"] = regime_horizon
    daily["asof_date"] = daily["date"].dt.strftime("%Y-%m-%d")
    daily["month"] = daily["date"].dt.to_period("M").astype(str)
    daily["created_at"] = now_ts()

    monthly = daily.sort_values(["market_scope", "date"]).groupby(["market_scope", "month"], as_index=False).tail(1).copy()

    write_table(out_db, MARKET_CONTEXT_DAILY_TABLE, daily)
    write_table(out_db, MARKET_CONTEXT_MONTHLY_TABLE, monthly)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = end.replace("-", "")
    daily.to_csv(REPORT_DIR / f"valuation_market_context_daily_{token}.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(REPORT_DIR / f"valuation_market_context_monthly_{token}.csv", index=False, encoding="utf-8-sig")
    return daily, monthly


def main() -> None:
    parser = argparse.ArgumentParser(description="Build market context mart for valuation AI.")
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--start", default="2017-01-01")
    parser.add_argument("--end", required=True)
    parser.add_argument("--out-db", default=str(OUT_DB))
    parser.add_argument("--regime-horizon", default="3m")
    args = parser.parse_args()
    daily, monthly = build_market_context(Path(args.universe), args.start, args.end, Path(args.out_db), args.regime_horizon)
    print(
        {
            "status": "ok",
            "daily_rows": int(len(daily)),
            "monthly_rows": int(len(monthly)),
            "start": args.start,
            "end": args.end,
            "out_db": args.out_db,
        }
    )


if __name__ == "__main__":
    main()
