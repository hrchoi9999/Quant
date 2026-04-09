from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .features import build_daily_feature_snapshots_from_public_sources
from .overlay import TimingOverlay
from .signal_history import SignalHistoryStore
from .types import TimingFeatureSnapshot, TimingSignalRecord


@dataclass(frozen=True)
class DailySignalRunResult:
    model_code: str
    signal_date: str
    record_count: int
    state_counts: dict[str, int]
    records: List[TimingSignalRecord]


def default_db_path() -> Path:
    return Path(r"D:\Quant\trading_sign\data\db\trading_sign.db")


def run_daily_signal_generation(
    *,
    model_code: str,
    signal_date: str,
    snapshots: Iterable[TimingFeatureSnapshot],
    db_path: Path | None = None,
) -> DailySignalRunResult:
    history_store = SignalHistoryStore(db_path or default_db_path())
    overlay = TimingOverlay.for_model(model_code, history_store=history_store)
    records = overlay.build_daily_signal_records(
        model_code=model_code,
        snapshots=snapshots,
        persist=True,
    )
    state_counts: dict[str, int] = {}
    for record in records:
        state_counts[record.current_state] = state_counts.get(record.current_state, 0) + 1
    return DailySignalRunResult(
        model_code=str(model_code).strip().upper(),
        signal_date=signal_date,
        record_count=len(records),
        state_counts=state_counts,
        records=records,
    )


def run_daily_signal_generation_from_public_sources(
    *,
    signal_date: str,
    data_asof_date: str,
    db_path: Path | None = None,
    include_tseries: bool = True,
    market_gate_open: bool = True,
) -> List[DailySignalRunResult]:
    grouped_snapshots = build_daily_feature_snapshots_from_public_sources(
        signal_date=signal_date,
        data_asof_date=data_asof_date,
        include_tseries=include_tseries,
        market_gate_open=market_gate_open,
    )
    results: List[DailySignalRunResult] = []
    for model_code, snapshots in grouped_snapshots.items():
        results.append(
            run_daily_signal_generation(
                model_code=model_code,
                signal_date=signal_date,
                snapshots=snapshots,
                db_path=db_path,
            )
        )
    return results
