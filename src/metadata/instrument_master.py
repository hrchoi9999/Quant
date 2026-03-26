# instrument_master.py ver 2026-03-17_002
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class InstrumentMasterStore:
    REQUIRED_COLUMNS = {
        "ticker": "TEXT PRIMARY KEY",
        "name": "TEXT",
        "asset_type": "TEXT NOT NULL",
        "market": "TEXT",
        "is_active": "INTEGER NOT NULL DEFAULT 1",
        "first_seen": "TEXT",
        "last_seen": "TEXT",
        "asof": "TEXT",
        "source": "TEXT",
        "updated_at": "TEXT",
    }

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else PROJECT_ROOT / r"data\db\price.db"
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        return con

    def _table_exists(self, con: sqlite3.Connection) -> bool:
        row = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='instrument_master'").fetchone()
        return bool(row)

    def _existing_columns(self, con: sqlite3.Connection) -> set[str]:
        return {row[1] for row in con.execute("PRAGMA table_info(instrument_master)").fetchall()}

    def init_schema(self) -> None:
        with self.connect() as con:
            if not self._table_exists(con):
                con.execute(
                    """
                    CREATE TABLE instrument_master (
                        ticker TEXT PRIMARY KEY,
                        name TEXT,
                        asset_type TEXT NOT NULL,
                        market TEXT,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        first_seen TEXT,
                        last_seen TEXT,
                        asof TEXT,
                        source TEXT,
                        updated_at TEXT
                    );
                    """
                )
            else:
                existing = self._existing_columns(con)
                for col, ddl in self.REQUIRED_COLUMNS.items():
                    if col not in existing and col != "ticker":
                        con.execute(f"ALTER TABLE instrument_master ADD COLUMN {col} {ddl}")
            con.execute("CREATE INDEX IF NOT EXISTS idx_instrument_master_asset_type ON instrument_master(asset_type, is_active)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_instrument_master_market ON instrument_master(market)")

    def upsert(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        now = _utcnow_iso()
        data = df.copy()
        for col in ["ticker", "name", "asset_type", "market", "first_seen", "last_seen", "asof", "source"]:
            if col not in data.columns:
                data[col] = ""
        if "is_active" not in data.columns:
            data["is_active"] = 1
        data["ticker"] = data["ticker"].astype(str).str.zfill(6)
        data["is_active"] = pd.to_numeric(data["is_active"], errors="coerce").fillna(1).astype(int)

        rows = [
            (
                str(r.ticker),
                str(r.name),
                str(r.asset_type),
                str(r.market),
                int(r.is_active),
                str(r.first_seen),
                str(r.last_seen),
                str(r.asof),
                str(r.source),
                now,
            )
            for r in data.itertuples(index=False)
        ]
        with self.connect() as con:
            con.executemany(
                """
                INSERT INTO instrument_master
                    (ticker, name, asset_type, market, is_active, first_seen, last_seen, asof, source, updated_at)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name=excluded.name,
                    asset_type=excluded.asset_type,
                    market=excluded.market,
                    is_active=excluded.is_active,
                    first_seen=COALESCE(instrument_master.first_seen, excluded.first_seen),
                    last_seen=excluded.last_seen,
                    asof=excluded.asof,
                    source=excluded.source,
                    updated_at=excluded.updated_at;
                """,
                rows,
            )
        return len(rows)

    def export_csv(self, out_path: Path) -> Path:
        with self.connect() as con:
            df = pd.read_sql_query("SELECT * FROM instrument_master ORDER BY asset_type, ticker", con)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        return out_path
