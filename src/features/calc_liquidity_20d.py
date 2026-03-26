# calc_liquidity_20d.py ver 2026-03-17_002
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def calc_liquidity_20d(price_db: Path, tickers: list[str], asof: str, min_liquidity_20d: float) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["ticker", "liquidity_20d_value", "history_days", "min_liquidity_pass"])

    parts = []
    chunk_size = 200
    with sqlite3.connect(str(price_db)) as con:
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            sql = f"""
            WITH ranked AS (
                SELECT
                    ticker,
                    date,
                    value,
                    ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                FROM prices_daily
                WHERE ticker IN ({placeholders})
                  AND date <= ?
            )
            SELECT
                ticker,
                AVG(value) AS liquidity_20d_value,
                COUNT(*) AS history_days
            FROM ranked
            WHERE rn <= 20
            GROUP BY ticker
            """
            params = tuple(chunk) + (asof,)
            part = pd.read_sql_query(sql, con, params=params)
            if not part.empty:
                parts.append(part)

    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["ticker", "liquidity_20d_value", "history_days"])
    if out.empty:
        out = pd.DataFrame({"ticker": tickers})
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["liquidity_20d_value"] = pd.to_numeric(out.get("liquidity_20d_value"), errors="coerce").fillna(0.0)
    out["history_days"] = pd.to_numeric(out.get("history_days"), errors="coerce").fillna(0).astype(int)
    out["min_liquidity_pass"] = (out["history_days"] >= 20) & (out["liquidity_20d_value"] >= float(min_liquidity_20d))
    return out[["ticker", "liquidity_20d_value", "history_days", "min_liquidity_pass"]]
