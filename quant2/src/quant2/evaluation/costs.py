from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketStage,
    MarketStructure,
    canonical_sha256,
)
from src.quant2.evaluation.input_connector import (
    EvaluationScopeRole,
    P2EvaluationPanel,
)

COST_POLICY_VERSION = "quant2.evaluation_cost.v1"


@dataclass(frozen=True)
class CostPolicy:
    fee_bps: int = 5
    slippage_bps: int = 5
    sensitivity_total_bps: tuple[int, ...] = (10, 20, 30)
    version: str = COST_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise ContractValidationError("fee_bps and slippage_bps cannot be negative")
        if not self.sensitivity_total_bps:
            raise ContractValidationError("sensitivity_total_bps cannot be empty")
        if tuple(sorted(set(self.sensitivity_total_bps))) != self.sensitivity_total_bps:
            raise ContractValidationError("sensitivity_total_bps must be sorted and unique")
        if any(value <= 0 for value in self.sensitivity_total_bps):
            raise ContractValidationError("cost sensitivity values must be positive")
        if self.fee_bps + self.slippage_bps not in self.sensitivity_total_bps:
            raise ContractValidationError("base fee plus slippage must be in sensitivity_total_bps")
        if not self.version.strip():
            raise ContractValidationError("cost policy version is required")

    @property
    def base_total_bps(self) -> int:
        return self.fee_bps + self.slippage_bps

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class CostAdjustedObservation:
    decision_date: date
    model_code: str
    scope_role: EvaluationScopeRole
    ranking_eligible: bool
    market_structure: MarketStructure
    market_stage: MarketStage
    market_confidence: float
    effective_trade_date: date
    return_period_end_date: date
    outcome_available_at: datetime
    benchmark_code: str
    cost_bps: int
    gross_return: float | None
    trading_cost: float | None
    net_return: float | None
    benchmark_return: float | None
    gross_excess_return: float | None
    net_excess_return: float | None
    turnover_one_way: float | None
    coverage_ratio: float
    available: bool
    reason_codes: tuple[str, ...]
    model_rule_hash: str
    market_payload_hash: str

    def __post_init__(self) -> None:
        if self.cost_bps <= 0:
            raise ContractValidationError("cost_bps must be positive")
        if self.outcome_available_at.tzinfo is None or self.outcome_available_at.utcoffset() is None:
            raise ContractValidationError("outcome_available_at must be timezone-aware")
        if self.return_period_end_date < self.effective_trade_date:
            raise ContractValidationError("return_period_end_date cannot precede effective_trade_date")
        if self.outcome_available_at.date() < self.return_period_end_date:
            raise ContractValidationError("outcome_available_at cannot precede return_period_end_date")
        if not self.benchmark_code.strip():
            raise ContractValidationError("benchmark_code is required")
        if not math.isfinite(self.market_confidence) or not 0.0 <= self.market_confidence <= 1.0:
            raise ContractValidationError("market_confidence must be between 0 and 1")
        if not math.isfinite(self.coverage_ratio) or not 0.0 <= self.coverage_ratio <= 1.0:
            raise ContractValidationError("coverage_ratio must be between 0 and 1")
        values = (
            self.gross_return,
            self.trading_cost,
            self.net_return,
            self.benchmark_return,
            self.gross_excess_return,
            self.net_excess_return,
            self.turnover_one_way,
        )
        if self.available:
            if any(value is None for value in values):
                raise ContractValidationError("available cost observation requires all return values")
            if any(not math.isfinite(float(value)) for value in values):
                raise ContractValidationError("cost-adjusted return values must be finite")
            if float(self.trading_cost) < 0.0 or float(self.turnover_one_way) < 0.0:
                raise ContractValidationError("trading cost and turnover cannot be negative")
            if (
                float(self.gross_return) < -1.0
                or float(self.net_return) < -1.0
                or float(self.benchmark_return) < -1.0
            ):
                raise ContractValidationError("single-period returns cannot be below -100%")
            if not math.isclose(
                float(self.gross_return) - float(self.trading_cost),
                float(self.net_return),
                abs_tol=1e-12,
            ):
                raise ContractValidationError("net_return must equal gross_return minus trading_cost")
            if not math.isclose(
                float(self.gross_return) - float(self.benchmark_return),
                float(self.gross_excess_return),
                abs_tol=1e-12,
            ):
                raise ContractValidationError("gross_excess_return arithmetic is invalid")
            if not math.isclose(
                float(self.net_return) - float(self.benchmark_return),
                float(self.net_excess_return),
                abs_tol=1e-12,
            ):
                raise ContractValidationError("net_excess_return arithmetic is invalid")
        else:
            if any(value is not None for value in values):
                raise ContractValidationError("unavailable cost observation values must remain null")
            if not self.reason_codes:
                raise ContractValidationError("unavailable cost observation requires reason_codes")
        expected_ranking_eligible = self.scope_role is EvaluationScopeRole.EVALUATION_CANDIDATE
        if self.ranking_eligible is not expected_ranking_eligible:
            raise ContractValidationError("ranking_eligible conflicts with scope role")
        for field_name in ("model_rule_hash", "market_payload_hash"):
            value = getattr(self, field_name)
            if len(value) != 64 or any(character not in "0123456789ABCDEF" for character in value):
                raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")


@dataclass(frozen=True)
class CostSensitivityResult:
    observations: tuple[CostAdjustedObservation, ...]
    input_panel_hash: str
    input_panel_ready: bool
    evaluation_ready: bool
    policy_version: str
    policy_hash: str
    result_hash: str


def _rounded(value: float) -> float:
    return round(value, 12)


def evaluate_cost_sensitivity(
    panel: P2EvaluationPanel,
    *,
    policy: CostPolicy | None = None,
) -> CostSensitivityResult:
    applied_policy = policy or CostPolicy()
    observations: list[CostAdjustedObservation] = []
    for binding in panel.bindings:
        row = binding.model_input
        ranking_eligible = binding.scope_role is EvaluationScopeRole.EVALUATION_CANDIDATE
        for cost_bps in applied_policy.sensitivity_total_bps:
            if not row.available:
                observations.append(
                    CostAdjustedObservation(
                        decision_date=binding.decision_date,
                        model_code=binding.model_code,
                        scope_role=binding.scope_role,
                        ranking_eligible=ranking_eligible,
                        market_structure=binding.market_structure,
                        market_stage=binding.market_stage,
                        market_confidence=binding.market_confidence,
                        effective_trade_date=row.effective_trade_date,
                        return_period_end_date=row.return_period_end_date,
                        outcome_available_at=row.outcome_available_at,
                        benchmark_code=row.benchmark_code,
                        cost_bps=cost_bps,
                        gross_return=None,
                        trading_cost=None,
                        net_return=None,
                        benchmark_return=None,
                        gross_excess_return=None,
                        net_excess_return=None,
                        turnover_one_way=None,
                        coverage_ratio=row.coverage_ratio,
                        available=False,
                        reason_codes=row.reason_codes,
                        model_rule_hash=row.rule_hash,
                        market_payload_hash=binding.market_payload_hash,
                    )
                )
                continue

            gross_return = float(row.gross_return)
            benchmark_return = float(row.benchmark_return)
            turnover = float(row.turnover_one_way)
            trading_cost = turnover * cost_bps / 10_000.0
            net_return = gross_return - trading_cost
            observations.append(
                CostAdjustedObservation(
                    decision_date=binding.decision_date,
                    model_code=binding.model_code,
                    scope_role=binding.scope_role,
                    ranking_eligible=ranking_eligible,
                    market_structure=binding.market_structure,
                    market_stage=binding.market_stage,
                    market_confidence=binding.market_confidence,
                    effective_trade_date=row.effective_trade_date,
                    return_period_end_date=row.return_period_end_date,
                    outcome_available_at=row.outcome_available_at,
                    benchmark_code=row.benchmark_code,
                    cost_bps=cost_bps,
                    gross_return=_rounded(gross_return),
                    trading_cost=_rounded(trading_cost),
                    net_return=_rounded(net_return),
                    benchmark_return=_rounded(benchmark_return),
                    gross_excess_return=_rounded(gross_return - benchmark_return),
                    net_excess_return=_rounded(net_return - benchmark_return),
                    turnover_one_way=_rounded(turnover),
                    coverage_ratio=row.coverage_ratio,
                    available=True,
                    reason_codes=row.reason_codes,
                    model_rule_hash=row.rule_hash,
                    market_payload_hash=binding.market_payload_hash,
                )
            )

    sorted_observations = tuple(
        sorted(
            observations,
            key=lambda item: (item.decision_date, item.model_code, item.cost_bps),
        )
    )
    policy_hash = applied_policy.policy_hash()
    result_hash = canonical_sha256(
        {
            "input_panel_hash": panel.panel_hash,
            "policy_hash": policy_hash,
            "observations": [asdict(item) for item in sorted_observations],
        }
    )
    evaluation_ready = panel.ready and bool(sorted_observations) and all(
        observation.available for observation in sorted_observations
    )
    return CostSensitivityResult(
        observations=sorted_observations,
        input_panel_hash=panel.panel_hash,
        input_panel_ready=panel.ready,
        evaluation_ready=evaluation_ready,
        policy_version=applied_policy.version,
        policy_hash=policy_hash,
        result_hash=result_hash,
    )
