from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    canonical_sha256,
)
from src.quant2.evaluation.input_connector import P2_REQUIRED_MODEL_CODES

P2_REAL_DATA_READINESS_POLICY_VERSION = "quant2.p2_real_data_readiness.v1"

REQUIRED_CHRONOLOGY_FIELDS = (
    "observation_date",
    "published_at",
    "available_at",
    "ingested_at",
    "decision_at",
    "execution_at",
    "effective_trade_date",
    "return_period_end_date",
    "outcome_available_at",
)
REQUIRED_HASH_FIELDS = (
    "rule_hash",
    "data_snapshot_hash",
    "universe_snapshot_hash",
)
REQUIRED_RETURN_FIELDS = (
    "gross_return",
    "turnover_one_way",
    "coverage_ratio",
)
REQUIRED_BENCHMARK_FIELDS = (
    "benchmark_code",
    "benchmark_return",
)


class P2RealDataCheck(str, Enum):
    SOURCE_ARTIFACT = "SOURCE_ARTIFACT"
    TARGET_ASOF = "TARGET_ASOF"
    COMMON_WINDOW = "COMMON_WINDOW"
    PIT_CHRONOLOGY = "PIT_CHRONOLOGY"
    HASH_PROVENANCE = "HASH_PROVENANCE"
    RETURN_AND_TURNOVER = "RETURN_AND_TURNOVER"
    BENCHMARK = "BENCHMARK"
    COST_SCENARIOS = "COST_SCENARIOS"
    EXECUTION_CONTRACT = "EXECUTION_CONTRACT"


class P2RealDataCheckStatus(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class P2RealDataReadinessStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class P2RealDataReadinessPolicy:
    required_model_codes: tuple[str, ...] = P2_REQUIRED_MODEL_CODES
    common_window_start: str = "2023-06-08"
    required_cost_bps: tuple[int, ...] = (10, 20, 30)
    required_execution_contract: str = "D_CLOSE_DECISION_NEXT_TRADABLE_SESSION"
    version: str = P2_REAL_DATA_READINESS_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.required_model_codes != P2_REQUIRED_MODEL_CODES:
            raise ContractValidationError("P2 real-data model coverage is frozen")
        _parse_date(self.common_window_start, "common_window_start")
        if self.required_cost_bps != (10, 20, 30):
            raise ContractValidationError("P2 real-data cost scenarios are frozen")
        if self.required_execution_contract != "D_CLOSE_DECISION_NEXT_TRADABLE_SESSION":
            raise ContractValidationError("P2 real-data execution contract is frozen")
        if self.version != P2_REAL_DATA_READINESS_POLICY_VERSION:
            raise ContractValidationError("P2 real-data readiness policy version is frozen")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class CsvArtifactProbeSpec:
    model_code: str
    source_path: str
    artifact_asof: str
    date_column: str

    def __post_init__(self) -> None:
        if self.model_code not in P2_REQUIRED_MODEL_CODES:
            raise ContractValidationError("unsupported P2 real-data model code")
        if not self.source_path.strip() or not self.date_column.strip():
            raise ContractValidationError("source_path and date_column are required")
        _parse_date(self.artifact_asof, "artifact_asof")


@dataclass(frozen=True)
class P2ModelArtifactEvidence:
    model_code: str
    source_path: str
    source_exists: bool
    source_sha256: str | None
    artifact_asof: str
    date_column: str
    row_count: int
    minimum_date: str | None
    maximum_date: str | None
    available_columns: tuple[str, ...]
    populated_columns: tuple[str, ...]
    observed_cost_bps: tuple[int, ...]
    observed_benchmark_codes: tuple[str, ...]
    observed_execution_contracts: tuple[str, ...]
    hash_provenance_valid: bool
    chronology_order_valid: bool | None
    probe_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.model_code not in P2_REQUIRED_MODEL_CODES:
            raise ContractValidationError("unsupported P2 artifact model code")
        _parse_date(self.artifact_asof, "artifact_asof")
        if self.row_count < 0:
            raise ContractValidationError("artifact row_count cannot be negative")
        if self.source_exists:
            _require_hash(self.source_sha256, "source_sha256")
        elif self.source_sha256 is not None or self.row_count != 0:
            raise ContractValidationError("missing artifact cannot have hash or rows")
        if (self.minimum_date is None) is not (self.maximum_date is None):
            raise ContractValidationError("artifact date range must be complete or absent")
        if self.minimum_date is not None and self.maximum_date is not None:
            minimum = _parse_date(self.minimum_date, "minimum_date")
            maximum = _parse_date(self.maximum_date, "maximum_date")
            if minimum > maximum:
                raise ContractValidationError("artifact minimum_date exceeds maximum_date")
        for field_name in (
            "available_columns",
            "populated_columns",
            "observed_benchmark_codes",
            "observed_execution_contracts",
            "probe_reason_codes",
        ):
            values = getattr(self, field_name)
            if values != tuple(sorted(set(values))):
                raise ContractValidationError(f"{field_name} must be sorted and unique")
        if not set(self.populated_columns).issubset(self.available_columns):
            raise ContractValidationError("populated_columns must exist in artifact columns")
        if self.observed_cost_bps != tuple(sorted(set(self.observed_cost_bps))):
            raise ContractValidationError("observed_cost_bps must be sorted and unique")


@dataclass(frozen=True)
class P2RealDataCheckResult:
    check: P2RealDataCheck
    status: P2RealDataCheckStatus
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status is P2RealDataCheckStatus.PASS and self.reason_codes:
            raise ContractValidationError("passing real-data check cannot have reasons")
        if self.status is P2RealDataCheckStatus.BLOCKED and not self.reason_codes:
            raise ContractValidationError("blocked real-data check requires reasons")


@dataclass(frozen=True)
class P2ModelRealDataReadiness:
    model_code: str
    source_path: str
    source_sha256: str | None
    minimum_date: str | None
    maximum_date: str | None
    checks: tuple[P2RealDataCheckResult, ...]
    status: P2RealDataReadinessStatus
    ready_for_real_data_evaluation: bool

    def __post_init__(self) -> None:
        if tuple(item.check for item in self.checks) != tuple(P2RealDataCheck):
            raise ContractValidationError("P2 model readiness checks are incomplete")
        expected_ready = all(
            item.status is P2RealDataCheckStatus.PASS for item in self.checks
        )
        if self.ready_for_real_data_evaluation is not expected_ready:
            raise ContractValidationError("P2 model readiness status is inconsistent")
        expected_status = (
            P2RealDataReadinessStatus.READY
            if expected_ready
            else P2RealDataReadinessStatus.BLOCKED
        )
        if self.status is not expected_status:
            raise ContractValidationError("P2 model readiness label is inconsistent")


@dataclass(frozen=True)
class P2RealDataReadinessMatrix:
    target_asof: str
    common_window_start: str
    models: tuple[P2ModelRealDataReadiness, ...]
    ready_model_codes: tuple[str, ...]
    blocked_model_codes: tuple[str, ...]
    status: P2RealDataReadinessStatus
    ready_for_real_data_evaluation: bool
    p2_complete: bool
    eligible_for_p3_validation: bool
    eligible_for_shadow: bool
    operational_authorization: bool
    blocked_reason_codes: tuple[str, ...]
    policy_version: str
    policy_hash: str
    matrix_hash: str

    def __post_init__(self) -> None:
        target = _parse_date(self.target_asof, "target_asof")
        common_start = _parse_date(self.common_window_start, "common_window_start")
        if self.common_window_start != P2RealDataReadinessPolicy().common_window_start:
            raise ContractValidationError("P2 readiness common window is invalid")
        if target < common_start:
            raise ContractValidationError("target_asof cannot precede common window")
        expected_codes = P2_REQUIRED_MODEL_CODES
        if tuple(item.model_code for item in self.models) != expected_codes:
            raise ContractValidationError("P2 readiness matrix model coverage is invalid")
        expected_ready_codes = tuple(
            item.model_code for item in self.models if item.ready_for_real_data_evaluation
        )
        expected_blocked_codes = tuple(
            item.model_code for item in self.models if not item.ready_for_real_data_evaluation
        )
        if (
            self.ready_model_codes != expected_ready_codes
            or self.blocked_model_codes != expected_blocked_codes
        ):
            raise ContractValidationError("P2 readiness model partitions are invalid")
        expected_ready = not expected_blocked_codes
        if self.ready_for_real_data_evaluation is not expected_ready:
            raise ContractValidationError("P2 matrix readiness is inconsistent")
        expected_status = (
            P2RealDataReadinessStatus.READY
            if expected_ready
            else P2RealDataReadinessStatus.BLOCKED
        )
        if self.status is not expected_status:
            raise ContractValidationError("P2 matrix status is inconsistent")
        if (
            self.p2_complete
            or self.eligible_for_p3_validation
            or self.eligible_for_shadow
            or self.operational_authorization
        ):
            raise ContractValidationError("readiness matrix cannot grant downstream authority")
        if self.policy_version != P2_REAL_DATA_READINESS_POLICY_VERSION:
            raise ContractValidationError("P2 readiness policy version is invalid")
        if self.policy_hash != P2RealDataReadinessPolicy().policy_hash():
            raise ContractValidationError("P2 readiness policy hash is invalid")
        if len(self.blocked_reason_codes) != len(set(self.blocked_reason_codes)):
            raise ContractValidationError("P2 readiness blocked reasons must be unique")
        required_blockers = {
            "REAL_DATA_EVALUATION_NOT_RUN",
            "PAIRED_BOOTSTRAP_NOT_RUN",
            "CLASSIFICATION_NOT_CONFIRMED",
            "P3_VALIDATION_NOT_AUTHORIZED",
            "SHADOW_NOT_AUTHORIZED",
            "OPERATIONAL_POLICY_NOT_AUTHORIZED",
        } | {
            f"MODEL_{model_code}_REAL_DATA_NOT_READY"
            for model_code in self.blocked_model_codes
        }
        if not required_blockers.issubset(self.blocked_reason_codes):
            raise ContractValidationError("P2 readiness required blocked reasons are missing")
        _require_hash(self.matrix_hash, "matrix_hash")
        payload = asdict(self)
        payload.pop("matrix_hash")
        if self.matrix_hash != canonical_sha256(payload):
            raise ContractValidationError("matrix_hash does not match readiness contents")


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} must be YYYY-MM-DD") from exc


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_hash(value: str | None, field_name: str) -> None:
    if value is None or len(value) != 64 or any(
        character not in "0123456789ABCDEF" for character in value
    ):
        raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _chronology_is_valid(row: dict[str, str]) -> bool:
    try:
        observation_date = date.fromisoformat(row["observation_date"])
        published_at = _parse_datetime(row["published_at"])
        available_at = _parse_datetime(row["available_at"])
        ingested_at = _parse_datetime(row["ingested_at"])
        decision_at = _parse_datetime(row["decision_at"])
        execution_at = _parse_datetime(row["execution_at"])
        effective_trade_date = date.fromisoformat(row["effective_trade_date"])
        return_period_end_date = date.fromisoformat(row["return_period_end_date"])
        outcome_available_at = _parse_datetime(row["outcome_available_at"])
        return (
            observation_date <= published_at.date()
            and published_at <= available_at <= ingested_at <= decision_at < execution_at
            and effective_trade_date == execution_at.date()
            and effective_trade_date <= return_period_end_date
            and return_period_end_date <= outcome_available_at.date()
            and execution_at < outcome_available_at
        )
    except (KeyError, TypeError, ValueError):
        return False


def probe_csv_artifact(
    root: Path,
    spec: CsvArtifactProbeSpec,
) -> P2ModelArtifactEvidence:
    path = root / Path(spec.source_path)
    if not path.is_file():
        return P2ModelArtifactEvidence(
            model_code=spec.model_code,
            source_path=spec.source_path.replace("\\", "/"),
            source_exists=False,
            source_sha256=None,
            artifact_asof=spec.artifact_asof,
            date_column=spec.date_column,
            row_count=0,
            minimum_date=None,
            maximum_date=None,
            available_columns=(),
            populated_columns=(),
            observed_cost_bps=(),
            observed_benchmark_codes=(),
            observed_execution_contracts=(),
            hash_provenance_valid=False,
            chronology_order_valid=None,
            probe_reason_codes=("SOURCE_ARTIFACT_NOT_FOUND",),
        )

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(sorted(reader.fieldnames or ()))
        rows.extend({key: (value or "").strip() for key, value in row.items()} for row in reader)
    populated_columns = tuple(
        sorted(column for column in columns if rows and all(row[column] for row in rows))
    )
    reasons: set[str] = set()
    parsed_dates: list[date] = []
    if spec.date_column not in columns:
        reasons.add("DATE_COLUMN_NOT_FOUND")
    else:
        for row in rows:
            value = row[spec.date_column]
            if not value:
                continue
            try:
                parsed_dates.append(date.fromisoformat(value[:10]))
            except ValueError:
                reasons.add("DATE_VALUE_INVALID")
    required_hashes_present = set(REQUIRED_HASH_FIELDS).issubset(populated_columns)
    hash_provenance_valid = bool(rows) and required_hashes_present and all(
        len(row[field]) == 64
        and all(character in "0123456789ABCDEF" for character in row[field])
        for row in rows
        for field in REQUIRED_HASH_FIELDS
    )
    chronology_fields_present = set(REQUIRED_CHRONOLOGY_FIELDS).issubset(
        populated_columns
    )
    chronology_order_valid = (
        all(_chronology_is_valid(row) for row in rows)
        if chronology_fields_present and rows
        else None
    )
    observed_costs: set[int] = set()
    for row in rows:
        value = row.get("cost_bps", "")
        if value:
            try:
                observed_costs.add(int(value))
            except ValueError:
                reasons.add("COST_BPS_VALUE_INVALID")
    return P2ModelArtifactEvidence(
        model_code=spec.model_code,
        source_path=spec.source_path.replace("\\", "/"),
        source_exists=True,
        source_sha256=_file_sha256(path),
        artifact_asof=spec.artifact_asof,
        date_column=spec.date_column,
        row_count=len(rows),
        minimum_date=min(parsed_dates).isoformat() if parsed_dates else None,
        maximum_date=max(parsed_dates).isoformat() if parsed_dates else None,
        available_columns=columns,
        populated_columns=populated_columns,
        observed_cost_bps=tuple(sorted(observed_costs)),
        observed_benchmark_codes=tuple(
            sorted({row.get("benchmark_code", "") for row in rows} - {""})
        ),
        observed_execution_contracts=tuple(
            sorted({row.get("execution_contract", "") for row in rows} - {""})
        ),
        hash_provenance_valid=hash_provenance_valid,
        chronology_order_valid=chronology_order_valid,
        probe_reason_codes=tuple(sorted(reasons)),
    )


def _check(
    check: P2RealDataCheck,
    passed: bool,
    reason_code: str,
) -> P2RealDataCheckResult:
    return P2RealDataCheckResult(
        check=check,
        status=(
            P2RealDataCheckStatus.PASS
            if passed
            else P2RealDataCheckStatus.BLOCKED
        ),
        reason_codes=() if passed else (reason_code,),
    )


def evaluate_model_real_data_readiness(
    evidence: P2ModelArtifactEvidence,
    *,
    target_asof: str,
    policy: P2RealDataReadinessPolicy | None = None,
) -> P2ModelRealDataReadiness:
    applied_policy = policy or P2RealDataReadinessPolicy()
    target = _parse_date(target_asof, "target_asof")
    common_start = _parse_date(applied_policy.common_window_start, "common_window_start")
    minimum = date.fromisoformat(evidence.minimum_date) if evidence.minimum_date else None
    maximum = date.fromisoformat(evidence.maximum_date) if evidence.maximum_date else None
    populated = set(evidence.populated_columns)
    checks = (
        _check(
            P2RealDataCheck.SOURCE_ARTIFACT,
            evidence.source_exists and evidence.row_count > 0,
            "SOURCE_ARTIFACT_UNAVAILABLE",
        ),
        _check(
            P2RealDataCheck.TARGET_ASOF,
            evidence.artifact_asof == target_asof,
            "TARGET_ASOF_MISMATCH",
        ),
        _check(
            P2RealDataCheck.COMMON_WINDOW,
            minimum is not None
            and maximum is not None
            and minimum <= common_start
            and maximum >= target,
            "COMMON_WINDOW_NOT_COVERED",
        ),
        _check(
            P2RealDataCheck.PIT_CHRONOLOGY,
            set(REQUIRED_CHRONOLOGY_FIELDS).issubset(populated)
            and evidence.chronology_order_valid is True,
            "PIT_CHRONOLOGY_NOT_PROVEN",
        ),
        _check(
            P2RealDataCheck.HASH_PROVENANCE,
            evidence.hash_provenance_valid,
            "CANONICAL_HASH_PROVENANCE_MISSING",
        ),
        _check(
            P2RealDataCheck.RETURN_AND_TURNOVER,
            set(REQUIRED_RETURN_FIELDS).issubset(populated),
            "RETURN_OR_TURNOVER_FIELDS_MISSING",
        ),
        _check(
            P2RealDataCheck.BENCHMARK,
            set(REQUIRED_BENCHMARK_FIELDS).issubset(populated)
            and bool(evidence.observed_benchmark_codes),
            "BENCHMARK_CONTRACT_MISSING",
        ),
        _check(
            P2RealDataCheck.COST_SCENARIOS,
            evidence.observed_cost_bps == applied_policy.required_cost_bps,
            "COST_SCENARIOS_10_20_30BP_MISSING",
        ),
        _check(
            P2RealDataCheck.EXECUTION_CONTRACT,
            evidence.observed_execution_contracts
            == (applied_policy.required_execution_contract,),
            "EXECUTION_CONTRACT_NOT_PROVEN",
        ),
    )
    ready = all(item.status is P2RealDataCheckStatus.PASS for item in checks)
    return P2ModelRealDataReadiness(
        model_code=evidence.model_code,
        source_path=evidence.source_path,
        source_sha256=evidence.source_sha256,
        minimum_date=evidence.minimum_date,
        maximum_date=evidence.maximum_date,
        checks=checks,
        status=(
            P2RealDataReadinessStatus.READY
            if ready
            else P2RealDataReadinessStatus.BLOCKED
        ),
        ready_for_real_data_evaluation=ready,
    )


def build_p2_real_data_readiness_matrix(
    evidence: tuple[P2ModelArtifactEvidence, ...],
    *,
    target_asof: str,
    policy: P2RealDataReadinessPolicy | None = None,
) -> P2RealDataReadinessMatrix:
    applied_policy = policy or P2RealDataReadinessPolicy()
    _parse_date(target_asof, "target_asof")
    by_model = {item.model_code: item for item in evidence}
    if len(by_model) != len(evidence) or set(by_model) != set(
        applied_policy.required_model_codes
    ):
        raise ContractValidationError(
            "P2 readiness evidence must contain each required model exactly once"
        )
    models = tuple(
        evaluate_model_real_data_readiness(
            by_model[model_code],
            target_asof=target_asof,
            policy=applied_policy,
        )
        for model_code in applied_policy.required_model_codes
    )
    ready_codes = tuple(
        item.model_code for item in models if item.ready_for_real_data_evaluation
    )
    blocked_codes = tuple(
        item.model_code for item in models if not item.ready_for_real_data_evaluation
    )
    ready = not blocked_codes
    blocked_reasons = [
        "REAL_DATA_EVALUATION_NOT_RUN",
        "PAIRED_BOOTSTRAP_NOT_RUN",
        "CLASSIFICATION_NOT_CONFIRMED",
        "P3_VALIDATION_NOT_AUTHORIZED",
        "SHADOW_NOT_AUTHORIZED",
        "OPERATIONAL_POLICY_NOT_AUTHORIZED",
    ]
    blocked_reasons.extend(
        f"MODEL_{model_code}_REAL_DATA_NOT_READY" for model_code in blocked_codes
    )
    payload = {
        "target_asof": target_asof,
        "common_window_start": applied_policy.common_window_start,
        "models": models,
        "ready_model_codes": ready_codes,
        "blocked_model_codes": blocked_codes,
        "status": (
            P2RealDataReadinessStatus.READY
            if ready
            else P2RealDataReadinessStatus.BLOCKED
        ),
        "ready_for_real_data_evaluation": ready,
        "p2_complete": False,
        "eligible_for_p3_validation": False,
        "eligible_for_shadow": False,
        "operational_authorization": False,
        "blocked_reason_codes": tuple(blocked_reasons),
        "policy_version": applied_policy.version,
        "policy_hash": applied_policy.policy_hash(),
    }
    return P2RealDataReadinessMatrix(
        **payload,
        matrix_hash=canonical_sha256(payload),
    )
