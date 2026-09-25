from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from src.quant2.contracts.market_features import AxisFeatureSnapshot, MarketFeatureSnapshot
from src.quant2.contracts.market_overlays import OverlayInputs
from src.quant2.contracts.market_regime import (
    ConfidenceLevel,
    ContractValidationError,
    ForecastLabel,
    MarketAxis,
    MarketForecast,
    MarketReasonCode,
    MarketScope,
    MarketStage,
    MarketStructure,
    ObservedMarketState,
    PrimaryTransitionLabel,
    ProbabilityStatus,
    RiskAppetite,
    ShortTermPriceShock,
    SourceAvailability,
    TransitionState,
    VolatilityState,
    canonical_sha256,
)

QUANTMARKET_HANDOFF_VERSION = "quant2.market_context_handoff.v1"
QUANTMARKET_HANDOFF_VERSION_V2 = "quant2.market_context_handoff.v2"
SUPPORTED_HANDOFF_VERSIONS = frozenset(
    {QUANTMARKET_HANDOFF_VERSION, QUANTMARKET_HANDOFF_VERSION_V2}
)


def _required(mapping: Mapping[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ContractValidationError(f"missing required handoff field: {key}")
    return mapping[key]


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be an object")
    return value


def _date(value: Any, field_name: str) -> date:
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(f"{field_name} must be an ISO date") from exc
    return parsed


def _datetime(value: Any, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(f"{field_name} must be an ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware")
    return parsed


def _optional_datetime(value: Any, field_name: str) -> datetime | None:
    return None if value is None else _datetime(value, field_name)


def _optional_date(value: Any, field_name: str) -> date | None:
    return None if value is None else _date(value, field_name)


def _reason_codes(value: Any, field_name: str) -> tuple[MarketReasonCode, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractValidationError(f"{field_name} must be an array")
    try:
        return tuple(MarketReasonCode(str(code)) for code in value)
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} contains an unknown reason code") from exc


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be boolean")
    return value


def _source(value: Any, index: int) -> SourceAvailability:
    row = _mapping(value, f"sources[{index}]")
    prefix = f"sources[{index}]"
    return SourceAvailability(
        source_code=str(_required(row, "source_code")),
        available=_boolean(_required(row, "available"), f"{prefix}.available"),
        coverage_ratio=float(_required(row, "coverage_ratio")),
        observation_date=_optional_date(row.get("observation_date"), f"{prefix}.observation_date"),
        published_at=_optional_datetime(row.get("published_at"), f"{prefix}.published_at"),
        available_at=_optional_datetime(row.get("available_at"), f"{prefix}.available_at"),
        ingested_at=_optional_datetime(row.get("ingested_at"), f"{prefix}.ingested_at"),
        staleness_days=None if row.get("staleness_days") is None else int(row["staleness_days"]),
        source_snapshot_hash=row.get("source_snapshot_hash"),
        reason_codes=_reason_codes(row.get("reason_codes", []), f"{prefix}.reason_codes"),
    )


def _axis(axis: MarketAxis, value: Any) -> AxisFeatureSnapshot:
    row = _mapping(value, f"axes.{axis.value}")
    available = _boolean(_required(row, "available"), f"axes.{axis.value}.available")
    raw_score = row.get("raw_score")
    normalized_score = row.get("normalized_score")
    source_codes = _required(row, "source_codes")
    if not isinstance(source_codes, (list, tuple)):
        raise ContractValidationError(f"axes.{axis.value}.source_codes must be an array")
    return AxisFeatureSnapshot(
        axis=axis,
        available=available,
        raw_score=None if raw_score is None else float(raw_score),
        normalized_score=None if normalized_score is None else float(normalized_score),
        coverage_ratio=float(_required(row, "coverage_ratio")),
        freshness_ratio=float(_required(row, "freshness_ratio")),
        staleness_days=None if row.get("staleness_days") is None else int(row["staleness_days"]),
        source_codes=tuple(str(code) for code in source_codes),
        reason_codes=_reason_codes(row.get("reason_codes", []), f"axes.{axis.value}.reason_codes"),
    )


def _forecast(value: Any, information_cutoff_at: datetime) -> MarketForecast:
    row = _mapping(value, "forecast_20d")
    available = _boolean(_required(row, "available"), "forecast_20d.available")
    reason_codes = _reason_codes(row.get("reason_codes", []), "forecast_20d.reason_codes")
    if not available:
        forbidden_values = (
            row.get("label"),
            row.get("probability"),
            row.get("confidence_score"),
            row.get("confidence_level"),
            row.get("source_snapshot_hash"),
        )
        if any(value is not None for value in forbidden_values):
            raise ContractValidationError("unavailable forecast values must remain null")
        return MarketForecast(
            horizon_days=20,
            available=False,
            label=None,
            probability=None,
            confidence_score=None,
            confidence_level=None,
            source_snapshot_hash=None,
            reason_codes=reason_codes,
        )

    if not _boolean(_required(row, "pit_validated"), "forecast_20d.pit_validated"):
        raise ContractValidationError("available 20d forecast must be PIT validated")
    immature_target_count = int(_required(row, "immature_target_count"))
    if immature_target_count != 0:
        raise ContractValidationError("available 20d forecast requires immature_target_count=0")
    training_cutoff = _datetime(_required(row, "training_cutoff"), "forecast_20d.training_cutoff")
    max_target_available_at = _datetime(
        _required(row, "max_target_available_at"),
        "forecast_20d.max_target_available_at",
    )
    if max_target_available_at > training_cutoff:
        raise ContractValidationError("forecast max_target_available_at exceeds training_cutoff")
    if training_cutoff > information_cutoff_at:
        raise ContractValidationError("forecast training_cutoff exceeds information cutoff")
    try:
        label = ForecastLabel(str(_required(row, "label")))
    except ValueError as exc:
        raise ContractValidationError("forecast_20d.label is invalid") from exc
    return MarketForecast(
        horizon_days=20,
        available=True,
        label=label,
        probability=float(_required(row, "probability")),
        confidence_score=float(_required(row, "confidence_score")),
        confidence_level=_confidence_level(_required(row, "confidence_level")),
        source_snapshot_hash=str(_required(row, "source_snapshot_hash")),
        reason_codes=reason_codes,
    )


def _confidence_level(value: Any) -> ConfidenceLevel:
    try:
        return ConfidenceLevel(str(value))
    except ValueError as exc:
        raise ContractValidationError("forecast_20d.confidence_level is invalid") from exc


def _canonical_observed(
    value: Any,
    snapshot: MarketFeatureSnapshot,
) -> ObservedMarketState:
    row = _mapping(value, "canonical_market_state")
    raw_probabilities = _mapping(
        _required(row, "stage_probabilities"),
        "canonical_market_state.stage_probabilities",
    )
    if set(raw_probabilities) != {stage.value for stage in MarketStage}:
        raise ContractValidationError(
            "canonical_market_state.stage_probabilities must contain all eight stages"
        )
    try:
        structure = MarketStructure(str(_required(row, "observed_structure")))
        stage = MarketStage(str(_required(row, "observed_stage")))
        probability_status = ProbabilityStatus(str(_required(row, "probability_status")))
        risk_appetite = RiskAppetite(str(_required(row, "risk_appetite")))
        volatility_state = VolatilityState(str(_required(row, "volatility_state")))
        transition = TransitionState(str(_required(row, "transition")))
        price_shock = ShortTermPriceShock(str(_required(row, "short_term_price_shock")))
        primary_transition_label = PrimaryTransitionLabel(
            str(_required(row, "primary_transition_label"))
        )
        confidence_level = ConfidenceLevel(
            str(_required(row, "observed_regime_confidence_level"))
        )
    except ValueError as exc:
        raise ContractValidationError("canonical_market_state contains an invalid enum") from exc

    raw_axis_scores = {axis.axis.value: axis.raw_score for axis in snapshot.axes}
    normalized_axis_scores = {
        axis.axis.value: axis.normalized_score for axis in snapshot.axes
    }
    return ObservedMarketState(
        structure=structure,
        stage=stage,
        stage_probabilities={
            market_stage: float(raw_probabilities[market_stage.value])
            for market_stage in MarketStage
        },
        probability_status=probability_status,
        risk_appetite=risk_appetite,
        volatility_state=volatility_state,
        transition=transition,
        short_term_price_shock=price_shock,
        shock_flag=_boolean(
            _required(row, "shock_flag"),
            "canonical_market_state.shock_flag",
        ),
        shock_reason_codes=_reason_codes(
            row.get("shock_reason_codes", []),
            "canonical_market_state.shock_reason_codes",
        ),
        upward_transition_probability=float(
            _required(row, "upward_transition_probability")
        ),
        downward_transition_probability=float(
            _required(row, "downward_transition_probability")
        ),
        continuation_probability=float(_required(row, "continuation_probability")),
        primary_transition_label=primary_transition_label,
        primary_transition_probability=float(
            _required(row, "primary_transition_probability")
        ),
        transition_confidence=float(_required(row, "transition_confidence")),
        confidence_score=float(_required(row, "observed_regime_confidence")),
        confidence_level=confidence_level,
        raw_axis_scores=raw_axis_scores,
        normalized_axis_scores=normalized_axis_scores,
        reason_codes=_reason_codes(
            _required(row, "reason_codes"),
            "canonical_market_state.reason_codes",
        ),
    )


@dataclass(frozen=True)
class QuantMarketAdapterResult:
    handoff_version: str
    source_snapshot_id: str
    producer_rule_version: str
    producer_rule_hash: str
    generated_at: datetime
    next_execution_date: date
    snapshot: MarketFeatureSnapshot
    overlay_inputs: OverlayInputs
    canonical_observed: ObservedMarketState | None
    forecasts: tuple[MarketForecast, ...]
    input_payload_hash: str


def adapt_quantmarket_handoff(payload: Mapping[str, Any]) -> QuantMarketAdapterResult:
    handoff_version = str(_required(payload, "handoff_version"))
    if handoff_version not in SUPPORTED_HANDOFF_VERSIONS:
        raise ContractValidationError(
            f"unsupported QuantMarket handoff_version: {handoff_version}"
        )
    if str(_required(payload, "producer")) != "QuantMarket":
        raise ContractValidationError("handoff producer must be QuantMarket")

    decision_date = _date(_required(payload, "decision_date"), "decision_date")
    market_data_asof = _date(_required(payload, "market_data_asof"), "market_data_asof")
    information_cutoff_at = _datetime(
        _required(payload, "information_cutoff_at"),
        "information_cutoff_at",
    )
    generated_at = _datetime(_required(payload, "generated_at"), "generated_at")
    next_execution_date = _date(
        _required(payload, "next_execution_date"),
        "next_execution_date",
    )
    if generated_at < information_cutoff_at:
        raise ContractValidationError("generated_at cannot be before information cutoff")
    if next_execution_date <= decision_date:
        raise ContractValidationError("next_execution_date must be after decision_date")

    source_snapshot_id = str(_required(payload, "source_snapshot_id"))
    producer_rule_version = str(_required(payload, "rule_version"))
    producer_rule_hash = str(_required(payload, "rule_hash"))
    if not source_snapshot_id.strip() or not producer_rule_version.strip():
        raise ContractValidationError("source_snapshot_id and rule_version are required")
    if len(producer_rule_hash) != 64 or any(
        character not in "0123456789ABCDEF" for character in producer_rule_hash
    ):
        raise ContractValidationError("rule_hash must be uppercase SHA-256 hex")

    raw_sources = _required(payload, "sources")
    if not isinstance(raw_sources, (list, tuple)):
        raise ContractValidationError("sources must be an array")
    sources = tuple(_source(value, index) for index, value in enumerate(raw_sources))

    raw_axes = _mapping(_required(payload, "axes"), "axes")
    if set(raw_axes) != {axis.value for axis in MarketAxis}:
        raise ContractValidationError("axes must contain exactly four canonical market axes")
    axes = tuple(_axis(axis, raw_axes[axis.value]) for axis in MarketAxis)
    market_scope = MarketScope(str(_required(payload, "market_scope")))
    snapshot = MarketFeatureSnapshot(
        market_scope=market_scope,
        decision_date=decision_date,
        market_data_asof=market_data_asof,
        information_cutoff_at=information_cutoff_at,
        axes=axes,
        sources=sources,
    )

    raw_overlay = _mapping(_required(payload, "overlay_inputs"), "overlay_inputs")
    if handoff_version == QUANTMARKET_HANDOFF_VERSION_V2:
        directional_values = {
            field_name: float(_required(raw_overlay, field_name))
            for field_name in (
                "return_1d",
                "return_3d",
                "return_5d",
                "return_zscore_1d",
                "return_zscore_3d",
                "return_zscore_5d",
            )
        }
    else:
        directional_values = {
            field_name: None
            for field_name in (
                "return_1d",
                "return_3d",
                "return_5d",
                "return_zscore_1d",
                "return_zscore_3d",
                "return_zscore_5d",
            )
        }
    overlay_inputs = OverlayInputs(
        decision_date=decision_date,
        volatility_zscore=float(_required(raw_overlay, "volatility_zscore")),
        drawdown_5d=float(_required(raw_overlay, "drawdown_5d")),
        drawdown_20d=float(_required(raw_overlay, "drawdown_20d")),
        fx_move_5d=None if raw_overlay.get("fx_move_5d") is None else float(raw_overlay["fx_move_5d"]),
        credit_spread_zscore=(
            None
            if raw_overlay.get("credit_spread_zscore") is None
            else float(raw_overlay["credit_spread_zscore"])
        ),
        **directional_values,
    )
    canonical_observed = (
        _canonical_observed(
            _required(payload, "canonical_market_state"),
            snapshot,
        )
        if handoff_version == QUANTMARKET_HANDOFF_VERSION_V2
        else None
    )
    forecasts = (_forecast(_required(payload, "forecast_20d"), information_cutoff_at),)

    return QuantMarketAdapterResult(
        handoff_version=handoff_version,
        source_snapshot_id=source_snapshot_id,
        producer_rule_version=producer_rule_version,
        producer_rule_hash=producer_rule_hash,
        generated_at=generated_at,
        next_execution_date=next_execution_date,
        snapshot=snapshot,
        overlay_inputs=overlay_inputs,
        canonical_observed=canonical_observed,
        forecasts=forecasts,
        input_payload_hash=canonical_sha256(payload),
    )
