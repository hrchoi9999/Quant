# price_store.py ver 2025-12-30_001
"""
SQLite 기반 가격 저장소.

- DB 기본 위치: <project_root>/data/db/price.db
- 테이블: prices_daily (PK: ticker, date)

date는 'YYYY-MM-DD' 문자열로 저장합니다.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd


def _find_project_root(start_path: Path) -> Path:
    """
    파일 위치에서 상위로 올라가며 'src'와 'modules' 폴더가 함께 존재하는 경로를 프로젝트 루트로 간주.
    못 찾으면 start_path의 상위 3단계를 fallback으로 사용.
    """
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    # fallback (src/collectors/price/ 기준이면 parents[3]이 루트인 경우가 많음)
    try:
        return start_path.parents[3]
    except Exception:
        return start_path.parent


def _default_db_path() -> Path:
    env = os.getenv("QUANT_PRICE_DB")
    if env:
        return Path(env)

    here = Path(__file__).resolve()
    root = _find_project_root(here.parent)
    return root / "data" / "db" / "price.db"


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _to_datestr(d: date | datetime | str) -> str:
    if isinstance(d, str):
        # 'YYYYMMDD' 또는 'YYYY-MM-DD' 모두 허용
        s = d.strip()
        if len(s) == 8 and s.isdigit():
            return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
        return s
    if isinstance(d, datetime):
        d = d.date()
    return d.isoformat()


def _utcnow_iso() -> str:
    # 운영 편의상 ISO로 저장(로컬시간 기준이 필요하면 바꿔도 됨)
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class PriceStore:
    db_path: Path = None  # type: ignore

    def __post_init__(self) -> None:
        if self.db_path is None:
            self.db_path = _default_db_path()
        _ensure_parent_dir(self.db_path)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA foreign_keys=ON;")
        return con

    def init_schema(self) -> None:
        with self.connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS prices_daily (
                    ticker TEXT NOT NULL,
                    date   TEXT NOT NULL,
                    open   REAL,
                    high   REAL,
                    low    REAL,
                    close  REAL,
                    volume INTEGER,
                    value  REAL,
                    source TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (ticker, date)
                );
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_prices_daily_date ON prices_daily(date);")

    def get_last_date(self, ticker: str) -> Optional[date]:
        ticker = ticker.strip()
        with self.connect() as con:
            cur = con.execute(
                "SELECT MAX(date) FROM prices_daily WHERE ticker = ?;",
                (ticker,),
            )
            row = cur.fetchone()
        if not row or not row[0]:
            return None
        return datetime.strptime(row[0], "%Y-%m-%d").date()

    def upsert_prices(self, ticker: str, df: pd.DataFrame, source: str = "pykrx") -> int:
        """
        df: index=날짜(DatetimeIndex 또는 date), columns: open/high/low/close/volume/value
        이미 존재하는 (ticker,date)는 덮어씁니다.
        """
        if df is None or df.empty:
            return 0

        ticker = ticker.strip()
        now = _utcnow_iso()

        # index -> 날짜 문자열
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)

        df = df.copy()
        df["date"] = df.index.date
        df["date"] = df["date"].apply(_to_datestr)

        # 필수 컬럼 보정
        for col in ["open", "high", "low", "close", "volume", "value"]:
            if col not in df.columns:
                df[col] = None

        rows = [
            (
                ticker,
                r["date"],
                None if pd.isna(r["open"]) else float(r["open"]),
                None if pd.isna(r["high"]) else float(r["high"]),
                None if pd.isna(r["low"]) else float(r["low"]),
                None if pd.isna(r["close"]) else float(r["close"]),
                None if pd.isna(r["volume"]) else int(r["volume"]),
                None if pd.isna(r["value"]) else float(r["value"]),
                source,
                now,
                now,
            )
            for _, r in df.iterrows()
        ]

        sql = """
        INSERT INTO prices_daily
            (ticker, date, open, high, low, close, volume, value, source, created_at, updated_at)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume,
            value=excluded.value,
            source=excluded.source,
            updated_at=excluded.updated_at;
        """

        with self.connect() as con:
            con.executemany(sql, rows)
        return len(rows)

    def read_prices(
        self,
        ticker: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        ticker = ticker.strip()
        where = ["ticker = ?"]
        params = [ticker]

        if start:
            where.append("date >= ?")
            params.append(_to_datestr(start))
        if end:
            where.append("date <= ?")
            params.append(_to_datestr(end))

        sql = f"""
        SELECT date, open, high, low, close, volume, value
        FROM prices_daily
        WHERE {' AND '.join(where)}
        ORDER BY date;
        """

        with self.connect() as con:
            df = pd.read_sql_query(sql, con, params=params)

        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df
