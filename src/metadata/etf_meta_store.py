# etf_meta_store.py ver 2026-03-17_001
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class EtfMetaStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else PROJECT_ROOT / r"data\db\price.db"
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        return con

    def init_schema(self) -> None:
        with self.connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS etf_meta (
                    ticker TEXT NOT NULL,
                    asset_class TEXT,
                    group_key TEXT,
                    currency_exposure TEXT,
                    is_inverse INTEGER,
                    is_leveraged INTEGER,
                    core_eligible INTEGER,
                    liquidity_20d_value REAL,
                    asof TEXT NOT NULL,
                    meta_source TEXT,
                    rule_version TEXT,
                    role_key TEXT,
                    role_confidence REAL,
                    role_reason TEXT,
                    role_schema_version TEXT,
                    purity_issue TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (ticker, asof)
                );
                """
            )
            existing_cols = {row[1] for row in con.execute("PRAGMA table_info(etf_meta)").fetchall()}
            migrations = {
                "role_key": "ALTER TABLE etf_meta ADD COLUMN role_key TEXT",
                "role_confidence": "ALTER TABLE etf_meta ADD COLUMN role_confidence REAL",
                "role_reason": "ALTER TABLE etf_meta ADD COLUMN role_reason TEXT",
                "role_schema_version": "ALTER TABLE etf_meta ADD COLUMN role_schema_version TEXT",
                "purity_issue": "ALTER TABLE etf_meta ADD COLUMN purity_issue TEXT",
            }
            for col, ddl in migrations.items():
                if col not in existing_cols:
                    con.execute(ddl)
            con.execute("CREATE INDEX IF NOT EXISTS idx_etf_meta_asof ON etf_meta(asof)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_etf_meta_group ON etf_meta(group_key, core_eligible)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_etf_meta_role ON etf_meta(role_key, core_eligible)")

    def upsert(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        now = _utcnow_iso()
        data = df.copy()
        defaults = {
            "asset_class": "",
            "group_key": "",
            "currency_exposure": "",
            "is_inverse": 0,
            "is_leveraged": 0,
            "core_eligible": 0,
            "liquidity_20d_value": 0.0,
            "meta_source": "",
            "rule_version": "",
            "role_key": "",
            "role_confidence": 0.0,
            "role_reason": "",
            "role_schema_version": "",
            "purity_issue": "",
        }
        for col, default in defaults.items():
            if col not in data.columns:
                data[col] = default
        data["ticker"] = data["ticker"].astype(str).str.zfill(6)
        for col in ["is_inverse", "is_leveraged", "core_eligible"]:
            data[col] = data[col].astype(bool).astype(int)
        data["liquidity_20d_value"] = pd.to_numeric(data["liquidity_20d_value"], errors="coerce").fillna(0.0)
        data["role_confidence"] = pd.to_numeric(data["role_confidence"], errors="coerce").fillna(0.0)

        rows = [
            (
                str(r.ticker),
                str(r.asset_class),
                str(r.group_key),
                str(r.currency_exposure),
                int(r.is_inverse),
                int(r.is_leveraged),
                int(r.core_eligible),
                float(r.liquidity_20d_value),
                str(r.asof),
                str(r.meta_source),
                str(r.rule_version),
                str(r.role_key),
                float(r.role_confidence),
                str(r.role_reason),
                str(r.role_schema_version),
                str(r.purity_issue),
                now,
            )
            for r in data.itertuples(index=False)
        ]
        with self.connect() as con:
            con.executemany(
                """
                INSERT INTO etf_meta
                    (ticker, asset_class, group_key, currency_exposure, is_inverse, is_leveraged, core_eligible,
                     liquidity_20d_value, asof, meta_source, rule_version,
                     role_key, role_confidence, role_reason, role_schema_version, purity_issue, updated_at)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, asof) DO UPDATE SET
                    asset_class=excluded.asset_class,
                    group_key=excluded.group_key,
                    currency_exposure=excluded.currency_exposure,
                    is_inverse=excluded.is_inverse,
                    is_leveraged=excluded.is_leveraged,
                    core_eligible=excluded.core_eligible,
                    liquidity_20d_value=excluded.liquidity_20d_value,
                    meta_source=excluded.meta_source,
                    rule_version=excluded.rule_version,
                    role_key=excluded.role_key,
                    role_confidence=excluded.role_confidence,
                    role_reason=excluded.role_reason,
                    role_schema_version=excluded.role_schema_version,
                    purity_issue=excluded.purity_issue,
                    updated_at=excluded.updated_at;
                """,
                rows,
            )
        return len(rows)

    def export_csv(self, out_path: Path, asof: str) -> Path:
        with self.connect() as con:
            df = pd.read_sql_query("SELECT * FROM etf_meta WHERE asof = ? ORDER BY group_key, ticker", con, params=[asof])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        return out_path
