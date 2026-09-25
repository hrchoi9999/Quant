from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from typing import Mapping

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketStage,
    MarketStructure,
    canonical_sha256,
)
from src.quant2.market_regime.pipeline import Quant2MarketPipelineResult


class EvaluationScopeRole(str, Enum):
    EVALUATION_CANDIDATE = "EVALUATION_CANDIDATE"
    ALPHA_VALIDATION = "ALPHA_VALIDATION"
    REFERENCE_VALIDATION_ONLY = "REFERENCE_VALIDATION_ONLY"
    GUARDED_CHALLENGER = "GUARDED_CHALLENGER"


MODEL_SCOPE_ROLES: dict[str, EvaluationScopeRole] = {
    "S2": EvaluationScopeRole.EVALUATION_CANDIDATE,
    "S3": EvaluationScopeRole.EVALUATION_CANDIDATE,
    "S3_CORE2": EvaluationScopeRole.EVALUATION_CANDIDATE,
    "S3_ACCEL_V01": EvaluationScopeRole.EVALUATION_CANDIDATE,
    "S4": EvaluationScopeRole.EVALUATION_CANDIDATE,
    "S5": EvaluationScopeRole.EVALUATION_CANDIDATE,
    "S6": EvaluationScopeRole.EVALUATION_CANDIDATE,
    "T-STOCK-V01": EvaluationScopeRole.ALPHA_VALIDATION,
    "T-ETF-V01": EvaluationScopeRole.REFERENCE_VALIDATION_ONLY,
    "SAI_GUARDED": EvaluationScopeRole.GUARDED_CHALLENGER,
}

P2_REQUIRED_MODEL_CODES = (
    "S2",
    "S3",
    "S3_CORE2",
    "S3_ACCEL_V01",
    "S4",
    "S5",
    "S6",
    "T-STOCK-V01",
    "T-ETF-V01",
)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware")


def _require_hash(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789ABCDEF" for character in value):
        raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")


@dataclass(frozen=True)
class EvaluationModelInput:
    run_id: str
    model_code: str
    rule_hash: str
    data_snapshot_hash: str
    universe_snapshot_hash: str
    asof_date: date
    observation_date: date
    published_at: datetime | None
    available_at: datetime
    ingested_at: datetime
    decision_at: datetime
    effective_trade_date: date
    execution_at: datetime
    return_period_end_date: date
    outcome_available_at: datetime
    benchmark_code: str
    gross_return: float | None
    benchmark_return: float | None
    turnover_one_way: float | None
    coverage_ratio: float
    available: bool
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ContractValidationError("run_id is required")
        if self.model_code not in MODEL_SCOPE_ROLES:
            raise ContractValidationError(f"unsupported P2 model_code: {self.model_code}")
        for field_name in ("rule_hash", "data_snapshot_hash", "universe_snapshot_hash"):
            _require_hash(getattr(self, field_name), field_name)
        for field_name in (
            "available_at",
            "ingested_at",
            "decision_at",
            "execution_at",
            "outcome_available_at",
        ):
            _require_aware(getattr(self, field_name), field_name)
        if self.published_at is not None:
            _require_aware(self.published_at, "published_at")
        if self.observation_date > self.available_at.date():
            raise ContractValidationError("observation_date cannot be after available_at date")
        if self.published_at is not None and self.published_at > self.available_at:
            raise ContractValidationError("published_at cannot be after available_at")
        if self.available_at > self.ingested_at:
            raise ContractValidationError("available_at cannot be after ingested_at")
        if self.ingested_at > self.decision_at:
            raise ContractValidationError("ingested_at cannot be after decision_at")
        if self.decision_at >= self.execution_at:
            raise ContractValidationError("decision_at must be before execution_at")
        if self.asof_date != self.decision_at.date():
            raise ContractValidationError("asof_date must match decision_at date")
        if self.effective_trade_date != self.execution_at.date():
            raise ContractValidationError("effective_trade_date must match execution_at date")
        if self.return_period_end_date < self.effective_trade_date:
            raise ContractValidationError("return_period_end_date cannot precede effective_trade_date")
        if self.outcome_available_at.date() < self.return_period_end_date:
            raise ContractValidationError("outcome_available_at cannot precede return_period_end_date")
        if self.outcome_available_at <= self.execution_at:
            raise ContractValidationError("outcome_available_at must be after execution_at")
        if not self.benchmark_code.strip():
            raise ContractValidationError("benchmark_code is required")
        if not math.isfinite(self.coverage_ratio) or not 0.0 <= self.coverage_ratio <= 1.0:
            raise ContractValidationError("coverage_ratio must be between 0 and 1")
        values = (self.gross_return, self.benchmark_return, self.turnover_one_way)
        if self.available:
            if any(value is None for value in values):
                raise ContractValidationError("available model input requires returns and turnover")
            if any(not math.isfinite(float(value)) for value in values):
                raise ContractValidationError("model returns and turnover must be finite")
            if float(self.gross_return) < -1.0 or float(self.benchmark_return) < -1.0:
                raise ContractValidationError("gross and benchmark returns cannot be below -100%")
            if float(self.turnover_one_way) < 0.0:
                raise ContractValidationError("turnover_one_way cannot be negative")
            if self.coverage_ratio <= 0.0:
                raise ContractValidationError("available model input requires positive coverage")
        else:
            if any(value is not None for value in values):
                raise ContractValidationError("unavailable model return values must remain null")
            if not self.reason_codes:
                raise ContractValidationError("unavailable model input requires reason_codes")

    @property
    def scope_role(self) -> EvaluationScopeRole:
        return MODEL_SCOPE_ROLES[self.model_code]


@dataclass(frozen=True)
class EvaluationBinding:
    decision_date: date
    next_execution_date: date
    model_code: str
    scope_role: EvaluationScopeRole
    market_structure: MarketStructure
    market_stage: MarketStage
    market_confidence: float
    market_payload_hash: str
    model_input: EvaluationModelInput


@dataclass(frozen=True)
class P2EvaluationPanel:
    bindings: tuple[EvaluationBinding, ...]
    required_model_codes: tuple[str, ...]
    missing_market_dates: tuple[date, ...]
    missing_model_codes_by_date: Mapping[date, tuple[str, ...]]
    ready: bool
    panel_hash: str


def build_p2_evaluation_panel(
    market_results: tuple[Quant2MarketPipelineResult, ...],
    model_inputs: tuple[EvaluationModelInput, ...],
    *,
    required_model_codes: tuple[str, ...] = P2_REQUIRED_MODEL_CODES,
) -> P2EvaluationPanel:
    if not required_model_codes:
        raise ContractValidationError("required_model_codes cannot be empty")
    if len(required_model_codes) != len(set(required_model_codes)):
        raise ContractValidationError("required_model_codes must be unique")
    unknown_required = set(required_model_codes) - set(MODEL_SCOPE_ROLES)
    if unknown_required:
        raise ContractValidationError(f"unknown required model codes: {sorted(unknown_required)}")

    market_by_date = {result.record.decision_date: result for result in market_results}
    if len(market_by_date) != len(market_results):
        raise ContractValidationError("market_results must have unique decision dates")
    model_keys = [(row.asof_date, row.model_code) for row in model_inputs]
    if len(model_keys) != len(set(model_keys)):
        raise ContractValidationError("model inputs must be unique by asof_date and model_code")

    bindings: list[EvaluationBinding] = []
    missing_market_dates: set[date] = set()
    available_models_by_date: dict[date, set[str]] = {
        decision_date: set() for decision_date in market_by_date
    }
    for row in model_inputs:
        market = market_by_date.get(row.asof_date)
        if market is None:
            missing_market_dates.add(row.asof_date)
            continue
        if row.effective_trade_date != market.next_execution_date:
            raise ContractValidationError(
                "model effective_trade_date must match market next_execution_date"
            )
        if row.available:
            available_models_by_date[row.asof_date].add(row.model_code)
        bindings.append(
            EvaluationBinding(
                decision_date=row.asof_date,
                next_execution_date=market.next_execution_date,
                model_code=row.model_code,
                scope_role=row.scope_role,
                market_structure=market.record.observed.structure,
                market_stage=market.record.observed.stage,
                market_confidence=market.record.observed.confidence_score,
                market_payload_hash=market.record.payload_hash(),
                model_input=row,
            )
        )

    missing_model_codes_by_date = {
        decision_date: tuple(
            model_code
            for model_code in required_model_codes
            if model_code not in available_models_by_date[decision_date]
        )
        for decision_date in sorted(market_by_date)
    }
    missing_model_codes_by_date = {
        decision_date: missing
        for decision_date, missing in missing_model_codes_by_date.items()
        if missing
    }
    sorted_bindings = tuple(
        sorted(bindings, key=lambda item: (item.decision_date, item.model_code))
    )
    hash_material = {
        "required_model_codes": required_model_codes,
        "bindings": [asdict(binding) for binding in sorted_bindings],
        "missing_market_dates": sorted(missing_market_dates),
        "missing_model_codes_by_date": missing_model_codes_by_date,
    }
    panel_hash = canonical_sha256(hash_material)
    ready = bool(market_by_date) and not missing_market_dates and not missing_model_codes_by_date
    return P2EvaluationPanel(
        bindings=sorted_bindings,
        required_model_codes=required_model_codes,
        missing_market_dates=tuple(sorted(missing_market_dates)),
        missing_model_codes_by_date=missing_model_codes_by_date,
        ready=ready,
        panel_hash=panel_hash,
    )
