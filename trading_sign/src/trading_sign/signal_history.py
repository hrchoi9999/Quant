from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .types import TimingSignalRecord


@dataclass(frozen=True)
class SignalHistoryRecord:
    signal_date: str
    data_asof_date: str
    ticker: str
    security_name: str
    model_code: str
    current_state: str
    latest_state_change_date: str
    reason_tags_json: str
    reason_summary: str
    entry_score: Optional[float]
    exit_risk_score: Optional[float]
    is_recommended: int
    is_held: int
    created_at: str

    def to_signal_record(self) -> TimingSignalRecord:
        try:
            reason_tags = json.loads(self.reason_tags_json or "[]")
        except json.JSONDecodeError:
            reason_tags = []
        if not isinstance(reason_tags, list):
            reason_tags = []
        return TimingSignalRecord(
            signal_date=self.signal_date,
            data_asof_date=self.data_asof_date,
            ticker=self.ticker,
            security_name=self.security_name,
            model_code=self.model_code,
            current_state=self.current_state,
            latest_state_change_date=self.latest_state_change_date,
            reason_tags=[str(x) for x in reason_tags],
            reason_summary=self.reason_summary,
            entry_score=self.entry_score,
            exit_risk_score=self.exit_risk_score,
            is_recommended=bool(self.is_recommended),
            is_held=bool(self.is_held),
        )


class SignalHistoryStore:
    """SQLite-backed storage for historical daily timing signals."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS timing_signal_history (
                    signal_date TEXT NOT NULL,
                    data_asof_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    security_name TEXT NOT NULL DEFAULT '',
                    model_code TEXT NOT NULL,
                    current_state TEXT NOT NULL,
                    latest_state_change_date TEXT NOT NULL DEFAULT '',
                    reason_tags_json TEXT NOT NULL DEFAULT '[]',
                    reason_summary TEXT NOT NULL DEFAULT '',
                    entry_score REAL,
                    exit_risk_score REAL,
                    is_recommended INTEGER NOT NULL DEFAULT 0,
                    is_held INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (signal_date, ticker, model_code)
                )
                """
            )
            columns = {
                row[1]
                for row in con.execute("PRAGMA table_info(timing_signal_history)").fetchall()
            }
            if "security_name" not in columns:
                con.execute(
                    "ALTER TABLE timing_signal_history ADD COLUMN security_name TEXT NOT NULL DEFAULT ''"
                )
            if "latest_state_change_date" not in columns:
                con.execute(
                    "ALTER TABLE timing_signal_history ADD COLUMN latest_state_change_date TEXT NOT NULL DEFAULT ''"
                )
            con.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timing_signal_history_model_date
                ON timing_signal_history (model_code, signal_date)
                """
            )

    def upsert_records(self, records: Iterable[TimingSignalRecord]) -> None:
        rows = [
            (
                record.signal_date,
                record.data_asof_date,
                record.ticker,
                record.security_name,
                record.model_code,
                record.current_state,
                record.latest_state_change_date,
                json.dumps(record.reason_tags, ensure_ascii=True),
                record.reason_summary,
                record.entry_score,
                record.exit_risk_score,
                int(record.is_recommended),
                int(record.is_held),
            )
            for record in records
        ]
        if not rows:
            return
        self.initialize()
        with sqlite3.connect(str(self.db_path)) as con:
            con.executemany(
                """
                INSERT INTO timing_signal_history (
                    signal_date,
                    data_asof_date,
                    ticker,
                    security_name,
                    model_code,
                    current_state,
                    latest_state_change_date,
                    reason_tags_json,
                    reason_summary,
                    entry_score,
                    exit_risk_score,
                    is_recommended,
                    is_held
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_date, ticker, model_code) DO UPDATE SET
                    data_asof_date=excluded.data_asof_date,
                    security_name=excluded.security_name,
                    current_state=excluded.current_state,
                    latest_state_change_date=excluded.latest_state_change_date,
                    reason_tags_json=excluded.reason_tags_json,
                    reason_summary=excluded.reason_summary,
                    entry_score=excluded.entry_score,
                    exit_risk_score=excluded.exit_risk_score,
                    is_recommended=excluded.is_recommended,
                    is_held=excluded.is_held
                """
            ,
                rows,
            )

    def load_by_date(self, signal_date: str, model_code: Optional[str] = None) -> List[TimingSignalRecord]:
        self.initialize()
        query = """
            SELECT
                signal_date,
                data_asof_date,
                ticker,
                security_name,
                model_code,
                current_state,
                latest_state_change_date,
                reason_tags_json,
                reason_summary,
                entry_score,
                exit_risk_score,
                is_recommended,
                is_held,
                created_at
            FROM timing_signal_history
            WHERE signal_date = ?
        """
        params: list[object] = [signal_date]
        if model_code is not None:
            query += " AND model_code = ?"
            params.append(model_code)
        query += " ORDER BY model_code, ticker"
        with sqlite3.connect(str(self.db_path)) as con:
            cur = con.execute(query, params)
            rows = [SignalHistoryRecord(*row) for row in cur.fetchall()]
        return [row.to_signal_record() for row in rows]

    def load_latest_record(
        self,
        *,
        ticker: str,
        model_code: str,
        before_signal_date: Optional[str] = None,
    ) -> Optional[TimingSignalRecord]:
        self.initialize()
        query = """
            SELECT
                signal_date,
                data_asof_date,
                ticker,
                security_name,
                model_code,
                current_state,
                latest_state_change_date,
                reason_tags_json,
                reason_summary,
                entry_score,
                exit_risk_score,
                is_recommended,
                is_held,
                created_at
            FROM timing_signal_history
            WHERE ticker = ?
              AND model_code = ?
        """
        params: list[object] = [ticker, model_code]
        if before_signal_date is not None:
            query += " AND signal_date < ?"
            params.append(before_signal_date)
        query += " ORDER BY signal_date DESC LIMIT 1"
        with sqlite3.connect(str(self.db_path)) as con:
            row = con.execute(query, params).fetchone()
        if row is None:
            return None
        return SignalHistoryRecord(*row).to_signal_record()
