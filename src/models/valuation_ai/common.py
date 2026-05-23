# common.py ver 2026-05-06_001
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def norm_ticker(value: Any) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(6) if digits else None


def read_sql(db: Path, sql: str, params: tuple[Any, ...] | list[Any] | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    with sqlite3.connect(str(db)) as con:
        df = pd.read_sql_query(sql, con, params=params or [])
    for col in parse_dates or []:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def write_table(db: Path, table: str, df: pd.DataFrame, if_exists: str = "replace") -> None:
    ensure_parent(db)
    with sqlite3.connect(str(db)) as con:
        df.to_sql(table, con, if_exists=if_exists, index=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def percentile_rank(series: pd.Series) -> pd.Series:
    return series.rank(pct=True, method="average")


def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    return num.where(den.ne(0)).div(den.where(den.ne(0)))
