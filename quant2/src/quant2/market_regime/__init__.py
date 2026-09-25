"""Quant 2.0 market-regime scoring components."""

from src.quant2.contracts.market_overlays import OverlayInputs
from src.quant2.market_regime.confidence import (
    CONFIDENCE_POLICY_VERSION,
    ConfidencePolicy,
    ConfidenceResult,
    calculate_regime_confidence,
)
from src.quant2.market_regime.overlays import (
    OBSERVED_ASSEMBLY_VERSION,
    OVERLAY_POLICY_VERSION,
    MarketOverlayResult,
    ObservedAssemblyResult,
    OverlayPolicy,
    assemble_observed_market_state,
    calculate_market_overlays,
)
from src.quant2.market_regime.pipeline import (
    Quant2MarketPipelineResult,
    run_quant2_market_regime,
)
from src.quant2.market_regime.scoring import (
    SCORING_RULE_VERSION,
    RegimeScoreResult,
    RegimeScoringPolicy,
    score_market_regime,
)
from src.quant2.market_regime.short_term_shock import (
    SHORT_TERM_SHOCK_POLICY_VERSION,
    ShortTermShockPolicy,
    ShortTermShockResult,
    calculate_short_term_shock,
)
from src.quant2.market_regime.standardization import (
    STANDARDIZATION_VERSION,
    ExpandingZScorePolicy,
    RawFeatureObservation,
    StandardizationStatus,
    StandardizedObservation,
    expanding_zscore,
)
from src.quant2.market_regime.technical_indicators import (
    calculate_market_technical_history,
    calculate_market_technical_snapshot,
)
from src.quant2.market_regime.transition import (
    TRANSITION_POLICY_VERSION,
    RegimeTransitionState,
    TransitionDecision,
    TransitionPolicy,
    apply_regime_transition,
)
from src.quant2.market_regime.trend_transition import (
    TREND_TRANSITION_RULE_VERSION,
    TrendTransitionPolicy,
    attach_trend_transition_signal,
    build_trend_transition_signal,
)

__all__ = [
    "CONFIDENCE_POLICY_VERSION",
    "ConfidencePolicy",
    "ConfidenceResult",
    "ExpandingZScorePolicy",
    "MarketOverlayResult",
    "OBSERVED_ASSEMBLY_VERSION",
    "OVERLAY_POLICY_VERSION",
    "ObservedAssemblyResult",
    "OverlayInputs",
    "OverlayPolicy",
    "Quant2MarketPipelineResult",
    "RawFeatureObservation",
    "RegimeScoreResult",
    "RegimeScoringPolicy",
    "RegimeTransitionState",
    "SCORING_RULE_VERSION",
    "STANDARDIZATION_VERSION",
    "SHORT_TERM_SHOCK_POLICY_VERSION",
    "StandardizationStatus",
    "StandardizedObservation",
    "ShortTermShockPolicy",
    "ShortTermShockResult",
    "TRANSITION_POLICY_VERSION",
    "TransitionDecision",
    "TransitionPolicy",
    "TREND_TRANSITION_RULE_VERSION",
    "TrendTransitionPolicy",
    "apply_regime_transition",
    "attach_trend_transition_signal",
    "build_trend_transition_signal",
    "assemble_observed_market_state",
    "calculate_regime_confidence",
    "calculate_market_overlays",
    "calculate_short_term_shock",
    "calculate_market_technical_history",
    "calculate_market_technical_snapshot",
    "expanding_zscore",
    "score_market_regime",
    "run_quant2_market_regime",
]
