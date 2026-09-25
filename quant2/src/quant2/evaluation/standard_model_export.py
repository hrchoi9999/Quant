from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    canonical_sha256,
)
from src.quant2.evaluation.input_connector import EvaluationModelInput

P2_STANDARD_MODEL_EXPORT_POLICY_VERSION = "quant2.p2_standard_model_export.v1"
P2_STANDARD_EXPORT_MODEL_CODES = ("S2", "S4", "S5", "S6")


class P2SourceReturnSemantics(str, Enum):
    GROSS_BEFORE_COST = "GROSS_BEFORE_COST"
    NET_LINEAR_BASE_COST = "NET_LINEAR_BASE_COST"
    NET_MULTIPLICATIVE_BASE_COST = "NET_MULTIPLICATIVE_BASE_COST"


class P2StandardExportStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class P2StandardModelExportPolicy:
    supported_model_codes: tuple[str, ...] = P2_STANDARD_EXPORT_MODEL_CODES
    required_benchmark_code: str = "KOSPI"
    base_cost_bps: int = 10
    execution_contract: str = "D_CLOSE_DECISION_NEXT_TRADABLE_SESSION"
    version: str = P2_STANDARD_MODEL_EXPORT_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.supported_model_codes != P2_STANDARD_EXPORT_MODEL_CODES:
            raise ContractValidationError("P2 standard export model scope is frozen")
        if self.required_benchmark_code != "KOSPI":
            raise ContractValidationError("P2 standard export benchmark is frozen")
        if self.base_cost_bps != 10:
            raise ContractValidationError("P2 standard export base cost is frozen")
        if self.execution_contract != "D_CLOSE_DECISION_NEXT_TRADABLE_SESSION":
            raise ContractValidationError("P2 standard export execution contract is frozen")
        if self.version != P2_STANDARD_MODEL_EXPORT_POLICY_VERSION:
            raise ContractValidationError("P2 standard export policy version is frozen")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class P2SourceArtifact:
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        normalized = self.relative_path.replace("\\", "/")
        if (
            not normalized.strip()
            or normalized.startswith("/")
            or ":" in normalized
            or ".." in normalized.split("/")
        ):
            raise ContractValidationError("source artifact path must be repository-relative")
        if normalized != self.relative_path:
            raise ContractValidationError("source artifact path must use forward slashes")
        _require_hash(self.sha256, "source artifact sha256")


@dataclass(frozen=True)
class P2StandardExportManifest:
    run_id: str
    model_code: str
    rule_hash: str
    data_snapshot_hash: str
    universe_snapshot_hash: str
    source_artifacts: tuple[P2SourceArtifact, ...]
    source_return_semantics: P2SourceReturnSemantics
    benchmark_code: str
    base_cost_bps: int
    execution_contract: str
    chronology_provenance_confirmed: bool
    source_period_alignment_confirmed: bool
    operational_authorization: bool
    policy_version: str
    policy_hash: str
    manifest_hash: str

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ContractValidationError("standard export run_id is required")
        if self.model_code not in P2_STANDARD_EXPORT_MODEL_CODES:
            raise ContractValidationError("unsupported standard export model")
        for field_name in (
            "rule_hash",
            "data_snapshot_hash",
            "universe_snapshot_hash",
            "policy_hash",
            "manifest_hash",
        ):
            _require_hash(getattr(self, field_name), field_name)
        if not self.source_artifacts:
            raise ContractValidationError("standard export requires source artifacts")
        artifact_paths = tuple(item.relative_path for item in self.source_artifacts)
        if artifact_paths != tuple(sorted(set(artifact_paths))):
            raise ContractValidationError("source artifacts must be sorted and unique")
        policy = P2StandardModelExportPolicy()
        if (
            self.benchmark_code != policy.required_benchmark_code
            or self.base_cost_bps != policy.base_cost_bps
            or self.execution_contract != policy.execution_contract
            or self.policy_version != policy.version
            or self.policy_hash != policy.policy_hash()
        ):
            raise ContractValidationError("standard export manifest conflicts with policy")
        if not self.chronology_provenance_confirmed:
            raise ContractValidationError("chronology provenance must be confirmed")
        if not self.source_period_alignment_confirmed:
            raise ContractValidationError("source period alignment must be confirmed")
        if self.operational_authorization:
            raise ContractValidationError("standard export cannot grant operation")
        payload = asdict(self)
        payload.pop("manifest_hash")
        if self.manifest_hash != canonical_sha256(payload):
            raise ContractValidationError("manifest_hash does not match export manifest")


@dataclass(frozen=True)
class P2StandardPeriodSource:
    observation_date: date
    published_at: datetime
    available_at: datetime
    ingested_at: datetime
    decision_at: datetime
    execution_at: datetime
    effective_trade_date: date
    return_period_end_date: date
    outcome_available_at: datetime
    source_return: float | None
    benchmark_return: float | None
    turnover_one_way: float | None
    coverage_ratio: float
    available: bool
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "published_at",
            "available_at",
            "ingested_at",
            "decision_at",
            "execution_at",
            "outcome_available_at",
        ):
            _require_aware(getattr(self, field_name), field_name)
        if self.observation_date > self.published_at.date():
            raise ContractValidationError("observation_date cannot follow published_at")
        if not (
            self.published_at
            <= self.available_at
            <= self.ingested_at
            <= self.decision_at
            < self.execution_at
        ):
            raise ContractValidationError("standard export chronology is invalid")
        if self.effective_trade_date != self.execution_at.date():
            raise ContractValidationError("effective_trade_date must match execution_at")
        if self.return_period_end_date < self.effective_trade_date:
            raise ContractValidationError("return period cannot precede execution")
        if self.outcome_available_at.date() < self.return_period_end_date:
            raise ContractValidationError("outcome cannot precede return period end")
        if self.outcome_available_at <= self.execution_at:
            raise ContractValidationError("outcome must follow execution")
        if not math.isfinite(self.coverage_ratio) or not 0.0 <= self.coverage_ratio <= 1.0:
            raise ContractValidationError("coverage_ratio must be between 0 and 1")
        values = (self.source_return, self.benchmark_return, self.turnover_one_way)
        if self.available:
            if any(value is None for value in values):
                raise ContractValidationError("available export source requires return values")
            if any(not math.isfinite(float(value)) for value in values):
                raise ContractValidationError("standard export return values must be finite")
            if float(self.source_return) < -1.0 or float(self.benchmark_return) < -1.0:
                raise ContractValidationError("period returns cannot be below -100%")
            if float(self.turnover_one_way) < 0.0:
                raise ContractValidationError("turnover_one_way cannot be negative")
            if self.coverage_ratio <= 0.0:
                raise ContractValidationError("available source requires positive coverage")
        else:
            if any(value is not None for value in values):
                raise ContractValidationError("unavailable source values must remain null")
            if not self.reason_codes:
                raise ContractValidationError("unavailable source requires reason codes")


@dataclass(frozen=True)
class P2StandardModelExportResult:
    observations: tuple[EvaluationModelInput, ...]
    input_manifest_hash: str
    input_periods_hash: str
    status: P2StandardExportStatus
    export_ready: bool
    real_data_evaluation_run: bool
    eligible_for_p3_validation: bool
    eligible_for_shadow: bool
    operational_authorization: bool
    blocked_reason_codes: tuple[str, ...]
    policy_version: str
    policy_hash: str
    result_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "input_manifest_hash",
            "input_periods_hash",
            "policy_hash",
            "result_hash",
        ):
            _require_hash(getattr(self, field_name), field_name)
        expected_ready = bool(self.observations) and all(
            item.available for item in self.observations
        )
        if self.export_ready is not expected_ready:
            raise ContractValidationError("standard export readiness is inconsistent")
        expected_status = (
            P2StandardExportStatus.READY if expected_ready else P2StandardExportStatus.BLOCKED
        )
        if self.status is not expected_status:
            raise ContractValidationError("standard export status is inconsistent")
        if (
            self.real_data_evaluation_run
            or self.eligible_for_p3_validation
            or self.eligible_for_shadow
            or self.operational_authorization
        ):
            raise ContractValidationError("standard export cannot grant downstream authority")
        if not self.blocked_reason_codes:
            raise ContractValidationError("standard export requires downstream blockers")
        if len(self.blocked_reason_codes) != len(set(self.blocked_reason_codes)):
            raise ContractValidationError("standard export blockers must be unique")
        policy = P2StandardModelExportPolicy()
        if self.policy_version != policy.version or self.policy_hash != policy.policy_hash():
            raise ContractValidationError("standard export policy metadata is invalid")
        payload = asdict(self)
        payload.pop("result_hash")
        if self.result_hash != canonical_sha256(payload):
            raise ContractValidationError("result_hash does not match standard export")


def _require_hash(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789ABCDEF" for character in value
    ):
        raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware")


def build_standard_export_manifest(
    *,
    run_id: str,
    model_code: str,
    rule_hash: str,
    data_snapshot_hash: str,
    universe_snapshot_hash: str,
    source_artifacts: tuple[P2SourceArtifact, ...],
    source_return_semantics: P2SourceReturnSemantics,
    chronology_provenance_confirmed: bool,
    source_period_alignment_confirmed: bool,
    policy: P2StandardModelExportPolicy | None = None,
) -> P2StandardExportManifest:
    applied_policy = policy or P2StandardModelExportPolicy()
    sorted_artifacts = tuple(sorted(source_artifacts, key=lambda item: item.relative_path))
    payload = {
        "run_id": run_id,
        "model_code": model_code,
        "rule_hash": rule_hash,
        "data_snapshot_hash": data_snapshot_hash,
        "universe_snapshot_hash": universe_snapshot_hash,
        "source_artifacts": sorted_artifacts,
        "source_return_semantics": source_return_semantics,
        "benchmark_code": applied_policy.required_benchmark_code,
        "base_cost_bps": applied_policy.base_cost_bps,
        "execution_contract": applied_policy.execution_contract,
        "chronology_provenance_confirmed": chronology_provenance_confirmed,
        "source_period_alignment_confirmed": source_period_alignment_confirmed,
        "operational_authorization": False,
        "policy_version": applied_policy.version,
        "policy_hash": applied_policy.policy_hash(),
    }
    return P2StandardExportManifest(
        **payload,
        manifest_hash=canonical_sha256(payload),
    )


def _gross_return(
    source_return: float,
    turnover: float,
    manifest: P2StandardExportManifest,
) -> float:
    trading_cost = turnover * manifest.base_cost_bps / 10_000.0
    if manifest.source_return_semantics is P2SourceReturnSemantics.GROSS_BEFORE_COST:
        gross_return = source_return
    elif manifest.source_return_semantics is P2SourceReturnSemantics.NET_LINEAR_BASE_COST:
        gross_return = source_return + trading_cost
    else:
        if trading_cost >= 1.0:
            raise ContractValidationError("multiplicative trading cost must be below 100%")
        gross_return = (1.0 + source_return) / (1.0 - trading_cost) - 1.0
    if not math.isfinite(gross_return) or gross_return < -1.0:
        raise ContractValidationError("reconstructed gross_return is invalid")
    return round(gross_return, 12)


def export_standard_model_inputs(
    manifest: P2StandardExportManifest,
    periods: tuple[P2StandardPeriodSource, ...],
) -> P2StandardModelExportResult:
    if not periods:
        raise ContractValidationError("standard export requires source periods")
    sorted_periods = tuple(sorted(periods, key=lambda item: item.decision_at))
    decision_dates = tuple(item.decision_at.date() for item in sorted_periods)
    if len(decision_dates) != len(set(decision_dates)):
        raise ContractValidationError("standard export decision dates must be unique")
    observations: list[EvaluationModelInput] = []
    for period in sorted_periods:
        if period.available:
            gross_return = _gross_return(
                float(period.source_return),
                float(period.turnover_one_way),
                manifest,
            )
            benchmark_return = round(float(period.benchmark_return), 12)
            turnover = round(float(period.turnover_one_way), 12)
        else:
            gross_return = None
            benchmark_return = None
            turnover = None
        observations.append(
            EvaluationModelInput(
                run_id=manifest.run_id,
                model_code=manifest.model_code,
                rule_hash=manifest.rule_hash,
                data_snapshot_hash=manifest.data_snapshot_hash,
                universe_snapshot_hash=manifest.universe_snapshot_hash,
                asof_date=period.decision_at.date(),
                observation_date=period.observation_date,
                published_at=period.published_at,
                available_at=period.available_at,
                ingested_at=period.ingested_at,
                decision_at=period.decision_at,
                effective_trade_date=period.effective_trade_date,
                execution_at=period.execution_at,
                return_period_end_date=period.return_period_end_date,
                outcome_available_at=period.outcome_available_at,
                benchmark_code=manifest.benchmark_code,
                gross_return=gross_return,
                benchmark_return=benchmark_return,
                turnover_one_way=turnover,
                coverage_ratio=period.coverage_ratio,
                available=period.available,
                reason_codes=period.reason_codes,
            )
        )
    observation_tuple = tuple(observations)
    export_ready = all(item.available for item in observation_tuple)
    blockers = [
        "REAL_DATA_EVALUATION_NOT_RUN",
        "P3_VALIDATION_NOT_AUTHORIZED",
        "SHADOW_NOT_AUTHORIZED",
        "OPERATIONAL_POLICY_NOT_AUTHORIZED",
    ]
    if not export_ready:
        blockers.append("STANDARD_EXPORT_CONTAINS_UNAVAILABLE_PERIODS")
    policy = P2StandardModelExportPolicy()
    input_periods_hash = canonical_sha256(sorted_periods)
    payload = {
        "observations": observation_tuple,
        "input_manifest_hash": manifest.manifest_hash,
        "input_periods_hash": input_periods_hash,
        "status": (
            P2StandardExportStatus.READY
            if export_ready
            else P2StandardExportStatus.BLOCKED
        ),
        "export_ready": export_ready,
        "real_data_evaluation_run": False,
        "eligible_for_p3_validation": False,
        "eligible_for_shadow": False,
        "operational_authorization": False,
        "blocked_reason_codes": tuple(blockers),
        "policy_version": policy.version,
        "policy_hash": policy.policy_hash(),
    }
    return P2StandardModelExportResult(
        **payload,
        result_hash=canonical_sha256(payload),
    )
