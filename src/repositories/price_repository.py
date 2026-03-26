# price_repository.py ver 2026-03-17_001
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")


class PriceRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else PROJECT_ROOT / r"data\db\price.db"

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def get_price_universe(
        self,
        asset_type: str | None = None,
        tickers: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        where = []
        params: list[object] = []
        if asset_type:
            where.append("im.asset_type = ?")
            params.append(asset_type)
        if tickers:
            placeholders = ",".join("?" for _ in tickers)
            where.append(f"p.ticker IN ({placeholders})")
            params.extend([str(t).zfill(6) for t in tickers])
        if start:
            where.append("p.date >= ?")
            params.append(start.replace("/", "-"))
        if end:
            where.append("p.date <= ?")
            params.append(end.replace("/", "-"))
        sql = """
        SELECT p.date, p.ticker, im.name, im.asset_type, im.market,
               p.open, p.high, p.low, p.close, p.volume, p.value,
               em.asset_class, em.group_key, em.currency_exposure, em.is_inverse, em.is_leveraged
        FROM prices_daily p
        LEFT JOIN instrument_master im ON im.ticker = p.ticker
        LEFT JOIN etf_meta em ON em.ticker = p.ticker
         AND em.asof = (SELECT MAX(asof) FROM etf_meta e2 WHERE e2.ticker = p.ticker)
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.date, p.ticker"
        with self.connect() as con:
            return pd.read_sql_query(sql, con, params=params)
