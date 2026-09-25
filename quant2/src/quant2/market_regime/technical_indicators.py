from __future__ import annotations

from datetime import date, datetime
from typing import Sequence

from src.quant2.contracts.market_regime import ContractValidationError, MarketScope, canonical_sha256
from src.quant2.contracts.market_technical_features import (
    MIN_RAW_OBSERVATIONS,
    MarketCloseObservation,
    TechnicalFeatureStatus,
    TechnicalIndicatorSnapshot,
)


def _rolling_mean(values: Sequence[float], window: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        if index + 1 >= window:
            result[index] = running / window
    return result


def _ema(values: Sequence[float], span: int, min_periods: int) -> list[float | None]:
    alpha = 2.0 / (span + 1.0)
    result: list[float | None] = []
    state: float | None = None
    for index, value in enumerate(values):
        state = value if state is None else alpha * value + (1.0 - alpha) * state
        result.append(state if index + 1 >= min_periods else None)
    return result


def _ema_optional(values: Sequence[float | None], span: int, min_periods: int) -> list[float | None]:
    alpha = 2.0 / (span + 1.0)
    result: list[float | None] = []
    state: float | None = None
    count = 0
    for value in values:
        if value is None:
            result.append(None)
            continue
        state = value if state is None else alpha * value + (1.0 - alpha) * state
        count += 1
        result.append(state if count >= min_periods else None)
    return result


def _ratio_gap(
    numerator: Sequence[float | None], denominator: Sequence[float | None]
) -> list[float | None]:
    return [
        None if left is None or right is None else left / right - 1.0
        for left, right in zip(numerator, denominator)
    ]


def _delta(values: Sequence[float | None], lag: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(lag, len(values)):
        current = values[index]
        previous = values[index - lag]
        if current is not None and previous is not None:
            result[index] = current - previous
    return result


def _rsi_wilder(values: Sequence[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result

    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    def rsi(gain: float, loss: float) -> float:
        if loss == 0.0:
            return 50.0 if gain == 0.0 else 100.0
        if gain == 0.0:
            return 0.0
        relative_strength = gain / loss
        return 100.0 - 100.0 / (1.0 + relative_strength)

    result[period] = rsi(average_gain, average_loss)
    for index in range(period + 1, len(values)):
        average_gain = ((period - 1) * average_gain + gains[index - 1]) / period
        average_loss = ((period - 1) * average_loss + losses[index - 1]) / period
        result[index] = rsi(average_gain, average_loss)
    return result


def _validate_and_select(
    observations: Sequence[MarketCloseObservation],
    *,
    information_cutoff_at: datetime,
    decision_date: date | None,
) -> tuple[MarketCloseObservation, ...]:
    if information_cutoff_at.tzinfo is None or information_cutoff_at.utcoffset() is None:
        raise ContractValidationError("information_cutoff_at must be timezone-aware")
    if not observations:
        return ()
    scopes = {observation.market_scope for observation in observations}
    if len(scopes) != 1:
        raise ContractValidationError("technical observations must use one market_scope")
    dates = [observation.observation_date for observation in observations]
    if len(dates) != len(set(dates)):
        raise ContractValidationError("technical observations contain duplicate observation_date")
    selected = [
        observation
        for observation in observations
        if observation.available_at <= information_cutoff_at
        and (decision_date is None or observation.observation_date <= decision_date)
    ]
    return tuple(sorted(selected, key=lambda observation: observation.observation_date))


def calculate_market_technical_history(
    observations: Sequence[MarketCloseObservation],
    *,
    information_cutoff_at: datetime,
    decision_date: date | None = None,
) -> tuple[TechnicalIndicatorSnapshot, ...]:
    selected = _validate_and_select(
        observations,
        information_cutoff_at=information_cutoff_at,
        decision_date=decision_date,
    )
    if not selected:
        return ()

    closes = [float(observation.close) for observation in selected]
    sma5 = _rolling_mean(closes, 5)
    sma20 = _rolling_mean(closes, 20)
    sma60 = _rolling_mean(closes, 60)
    gap_5_20 = _ratio_gap(sma5, sma20)
    gap_20_60 = _ratio_gap(sma20, sma60)
    rsi14 = _rsi_wilder(closes)
    ema12 = _ema(closes, 12, 12)
    ema26 = _ema(closes, 26, 26)
    macd_line = [
        None if fast is None or slow is None else fast - slow
        for fast, slow in zip(ema12, ema26)
    ]
    macd_signal = _ema_optional(macd_line, 9, 9)
    macd_histogram = [
        None if line is None or signal is None else line - signal
        for line, signal in zip(macd_line, macd_signal)
    ]
    gap_5_20_deltas = {lag: _delta(gap_5_20, lag) for lag in (1, 3, 5)}
    gap_20_60_deltas = {lag: _delta(gap_20_60, lag) for lag in (1, 3, 5)}
    rsi14_deltas = {lag: _delta(rsi14, lag) for lag in (1, 3, 5)}
    macd_histogram_deltas = {lag: _delta(macd_histogram, lag) for lag in (1, 3, 5)}

    snapshots: list[TechnicalIndicatorSnapshot] = []
    source_chain_hash: str | None = None
    for index, observation in enumerate(selected):
        source_chain_hash = canonical_sha256(
            {
                "previous_source_snapshot_hash": source_chain_hash,
                "observation": observation.to_payload(),
            }
        )
        values = {
            "sma5": sma5[index],
            "sma20": sma20[index],
            "sma60": sma60[index],
            "gap_5_20": gap_5_20[index],
            "gap_20_60": gap_20_60[index],
            "gap_5_20_delta_1d": gap_5_20_deltas[1][index],
            "gap_5_20_delta_3d": gap_5_20_deltas[3][index],
            "gap_5_20_delta_5d": gap_5_20_deltas[5][index],
            "gap_20_60_delta_1d": gap_20_60_deltas[1][index],
            "gap_20_60_delta_3d": gap_20_60_deltas[3][index],
            "gap_20_60_delta_5d": gap_20_60_deltas[5][index],
            "rsi14": rsi14[index],
            "rsi14_delta_1d": rsi14_deltas[1][index],
            "rsi14_delta_3d": rsi14_deltas[3][index],
            "rsi14_delta_5d": rsi14_deltas[5][index],
            "macd_line_12_26": macd_line[index],
            "macd_signal_9": macd_signal[index],
            "macd_histogram": macd_histogram[index],
            "macd_histogram_delta_1d": macd_histogram_deltas[1][index],
            "macd_histogram_delta_3d": macd_histogram_deltas[3][index],
            "macd_histogram_delta_5d": macd_histogram_deltas[5][index],
        }
        ready = index + 1 >= MIN_RAW_OBSERVATIONS and all(
            value is not None for value in values.values()
        )
        snapshots.append(
            TechnicalIndicatorSnapshot(
                market_scope=observation.market_scope,
                observation_date=observation.observation_date,
                available_at=observation.available_at,
                raw_observation_count=index + 1,
                values=values,
                status=(
                    TechnicalFeatureStatus.READY
                    if ready
                    else TechnicalFeatureStatus.INSUFFICIENT_HISTORY
                ),
                reason_codes=() if ready else ("INSUFFICIENT_RAW_HISTORY",),
                source_snapshot_hash=source_chain_hash,
            )
        )
    return tuple(snapshots)


def calculate_market_technical_snapshot(
    observations: Sequence[MarketCloseObservation],
    *,
    market_scope: MarketScope,
    decision_date: date,
    information_cutoff_at: datetime,
) -> TechnicalIndicatorSnapshot | None:
    history = calculate_market_technical_history(
        observations,
        information_cutoff_at=information_cutoff_at,
        decision_date=decision_date,
    )
    if not history:
        return None
    if history[-1].market_scope is not market_scope:
        raise ContractValidationError("requested market_scope does not match observations")
    return history[-1]
