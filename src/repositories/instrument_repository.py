# instrument_repository.py ver 2026-03-17_001
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")


class InstrumentRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else PROJECT_ROOT / r"data\db\price.db"

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def get_instruments(self, asset_type: str | None = None, active_only: bool = True) -> pd.DataFrame:
        where = []
        params: list[object] = []
        if asset_type:
            where.append("asset_type = ?")
            params.append(asset_type)
        if active_only:
            where.append("is_active = 1")
        sql = "SELECT ticker, name, asset_type, market, is_active, first_seen, last_seen, asof, source FROM instrument_master"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY asset_type, ticker"
        with self.connect() as con:
            return pd.read_sql_query(sql, con, params=params)

    def get_etf_core_universe(self, asof: str | None = None, group_key: str | None = None) -> pd.DataFrame:
        target_asof = asof.replace("-", "") if asof else None
        params: list[object] = []
        if target_asof is None:
            with self.connect() as con:
                row = con.execute("SELECT MAX(asof) FROM etf_meta").fetchone()
            target_asof = str(row[0]) if row and row[0] else ""
        sql = """
        SELECT im.ticker, im.name, im.asset_type, im.market, im.is_active, im.asof,
               em.asset_class, em.group_key, em.currency_exposure, em.is_inverse,
               em.is_leveraged, em.core_eligible, em.liquidity_20d_value
        FROM etf_meta em
        JOIN instrument_master im ON im.ticker = em.ticker
        WHERE em.asof = ? AND em.core_eligible = 1
        """
        params.append(target_asof)
        if group_key:
            sql += " AND em.group_key = ?"
            params.append(group_key)
        sql += " ORDER BY em.group_key, em.liquidity_20d_value DESC, em.ticker"
        with self.connect() as con:
            return pd.read_sql_query(sql, con, params=params)
