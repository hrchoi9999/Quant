from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from src.quant2.adapters.quantmarket import (
    QuantMarketAdapterResult,
    adapt_quantmarket_handoff,
)
from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketRegimeRecord,
    canonical_sha256,
)
from src.quant2.contracts.market_technical_features import TechnicalIndicatorSnapshot
from src.quant2.market_regime.confidence import ConfidenceResult, calculate_regime_confidence
from src.quant2.market_regime.overlays import (
    ObservedAssemblyResult,
    assemble_observed_market_state,
)
from src.quant2.market_regime.scoring import RegimeScoreResult, score_market_regime
from src.quant2.market_regime.transition import (
    RegimeTransitionState,
    TransitionDecision,
    apply_regime_transition,
)
from src.quant2.market_regime.trend_transition import attach_trend_transition_signal


@dataclass(frozen=True)
class Quant2MarketPipelineResult:
    adapter: QuantMarketAdapterResult
    scoring: RegimeScoreResult | None
    confidence: ConfidenceResult | None
    transition: TransitionDecision | None
    assembly: ObservedAssemblyResult | None
    record: MarketRegimeRecord
    next_execution_date: date
    observed_source: str
    diagnostic_stage_agreement: bool | None
    diagnostic_shock_agreement: bool | None
    trend_transition_payload_hash: str | None
    result_hash: str

    def to_payload(self) -> dict[str, Any]:
        local_diagnostic = None
        if self.assembly is not None:
            local_diagnostic = {
                "observed_stage": self.assembly.observed.stage.value,
                "short_term_price_shock": (
                    self.assembly.observed.short_term_price_shock.value
                ),
                "stage_agreement": self.diagnostic_stage_agreement,
                "shock_agreement": self.diagnostic_shock_agreement,
            }
        return {
            "input_payload_hash": self.adapter.input_payload_hash,
            "source_snapshot_id": self.adapter.source_snapshot_id,
            "producer_rule_version": self.adapter.producer_rule_version,
            "producer_rule_hash": self.adapter.producer_rule_hash,
            "decision_date": self.record.decision_date.isoformat(),
            "next_execution_date": self.next_execution_date.isoformat(),
            "observed_source": self.observed_source,
            "local_diagnostic": local_diagnostic,
            "trend_transition_payload_hash": self.trend_transition_payload_hash,
            "market_regime": self.record.to_payload(),
            "market_regime_payload_hash": self.record.payload_hash(),
            "result_hash": self.result_hash,
        }


def run_quant2_market_regime(
    handoff_payload: Mapping[str, Any],
    *,
    previous_state: RegimeTransitionState | None = None,
    technical_snapshot: TechnicalIndicatorSnapshot | None = None,
) -> Quant2MarketPipelineResult:
    adapter = adapt_quantmarket_handoff(handoff_payload)
    feature_snapshot = adapter.snapshot
    if technical_snapshot is not None:
        feature_snapshot = attach_trend_transition_signal(
            feature_snapshot, technical_snapshot
        )
    canonical_observed = adapter.canonical_observed
    local_diagnostic_available = any(axis.available for axis in feature_snapshot.axes)
    if not local_diagnostic_available and canonical_observed is None:
        raise ContractValidationError(
            "legacy v1 handoff requires at least one available local scoring axis"
        )
    if local_diagnostic_available:
        scoring = score_market_regime(feature_snapshot)
        transition = apply_regime_transition(previous_state, scoring)
        confidence = calculate_regime_confidence(
            feature_snapshot,
            stage_score_margin=scoring.stage_score_margin,
            signal_alignment=scoring.signal_alignment,
            state_persistence_days=transition.state.days_in_state,
        )
        assembly = assemble_observed_market_state(
            feature_snapshot,
            scoring,
            confidence,
            transition,
            adapter.overlay_inputs,
        )
    else:
        scoring = None
        transition = None
        confidence = None
        assembly = None
    if canonical_observed is None:
        assert assembly is not None
        observed = assembly.observed
        observed_source = "Quant.local_legacy_v1"
        diagnostic_stage_agreement = None
        diagnostic_shock_agreement = None
        record_rule_version = (
            f"{assembly.rule_version}|producer:{adapter.producer_rule_version}"
        )
        record_rule_hash = canonical_sha256(
            {
                "assembly_rule_hash": assembly.rule_hash,
                "producer_rule_version": adapter.producer_rule_version,
                "producer_rule_hash": adapter.producer_rule_hash,
            }
        )
    else:
        observed = canonical_observed
        observed_source = "QuantMarket.canonical_v2"
        diagnostic_stage_agreement = (
            assembly.observed.stage is observed.stage if assembly is not None else None
        )
        diagnostic_shock_agreement = (
            assembly.observed.short_term_price_shock is observed.short_term_price_shock
            if assembly is not None
            else None
        )
        record_rule_version = adapter.producer_rule_version
        record_rule_hash = adapter.producer_rule_hash
    record = MarketRegimeRecord(
        market_scope=adapter.snapshot.market_scope,
        decision_date=adapter.snapshot.decision_date,
        market_data_asof=adapter.snapshot.market_data_asof,
        information_cutoff_at=adapter.snapshot.information_cutoff_at,
        generated_at=adapter.generated_at,
        observed=observed,
        forecasts=adapter.forecasts,
        sources=adapter.snapshot.sources,
        rule_version=record_rule_version,
        rule_hash=record_rule_hash,
    )
    hash_material = {
        "input_payload_hash": adapter.input_payload_hash,
        "next_execution_date": adapter.next_execution_date,
        "market_regime_payload_hash": record.payload_hash(),
        "local_diagnostic_rule_hash": assembly.rule_hash if assembly is not None else None,
        "local_diagnostic_stage": assembly.observed.stage if assembly is not None else None,
        "local_diagnostic_short_term_price_shock": (
            assembly.observed.short_term_price_shock if assembly is not None else None
        ),
        "trend_transition_payload_hash": (
            feature_snapshot.trend_transition.payload_hash()
            if feature_snapshot.trend_transition is not None
            else None
        ),
    }
    result_hash = canonical_sha256(hash_material)
    return Quant2MarketPipelineResult(
        adapter=adapter,
        scoring=scoring,
        confidence=confidence,
        transition=transition,
        assembly=assembly,
        record=record,
        next_execution_date=adapter.next_execution_date,
        observed_source=observed_source,
        diagnostic_stage_agreement=diagnostic_stage_agreement,
        diagnostic_shock_agreement=diagnostic_shock_agreement,
        trend_transition_payload_hash=hash_material["trend_transition_payload_hash"],
        result_hash=result_hash,
    )
