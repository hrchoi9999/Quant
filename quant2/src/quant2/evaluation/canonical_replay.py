from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    canonical_sha256,
)

P2_CANONICAL_REPLAY_POLICY_VERSION = "quant2.p2_canonical_replay.v1"
P2_CANONICAL_REPLAY_MODEL_CODES = ("S4", "S5", "S6")


class P2CanonicalReplayStatus(str, Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class P2CanonicalReplayPolicy:
    model_codes: tuple[str, ...] = P2_CANONICAL_REPLAY_MODEL_CODES
    universe_semantics: str = "STATIC_ASOF_CORE_REPLAY"
    event_time_semantics: str = "DATE_ONLY_D_CLOSE_TO_NEXT_TRADABLE_CLOSE"
    allow_historical_timestamp_inference: bool = False
    operational_authorization: bool = False
    version: str = P2_CANONICAL_REPLAY_POLICY_VERSION

    def __post_init__(self) -> None:
        if (
            self.model_codes != P2_CANONICAL_REPLAY_MODEL_CODES
            or self.universe_semantics != "STATIC_ASOF_CORE_REPLAY"
            or self.event_time_semantics != "DATE_ONLY_D_CLOSE_TO_NEXT_TRADABLE_CLOSE"
            or self.allow_historical_timestamp_inference
            or self.operational_authorization
            or self.version != P2_CANONICAL_REPLAY_POLICY_VERSION
        ):
            raise ContractValidationError("P2 canonical replay policy is frozen")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class P2ReplayArtifact:
    artifact_type: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        normalized = self.relative_path.replace("\\", "/")
        if (
            not self.artifact_type.strip()
            or normalized != self.relative_path
            or not normalized.strip()
            or normalized.startswith("/")
            or ":" in normalized
            or ".." in normalized.split("/")
        ):
            raise ContractValidationError("canonical replay artifact is invalid")
        _require_hash(self.sha256, "replay artifact sha256")


@dataclass(frozen=True)
class P2CanonicalReplayModelResult:
    model_code: str
    started_at: datetime
    finished_at: datetime
    output_artifacts: tuple[P2ReplayArtifact, ...]
    legacy_artifacts: tuple[P2ReplayArtifact, ...]
    output_hashes_match_legacy: bool
    period_count: int
    replay_succeeded: bool

    def __post_init__(self) -> None:
        if self.model_code not in P2_CANONICAL_REPLAY_MODEL_CODES:
            raise ContractValidationError("unsupported canonical replay model")
        _require_aware(self.started_at, "model started_at")
        _require_aware(self.finished_at, "model finished_at")
        if self.finished_at < self.started_at or self.period_count <= 0:
            raise ContractValidationError("canonical replay model timing is invalid")
        for artifacts in (self.output_artifacts, self.legacy_artifacts):
            paths = tuple(item.relative_path for item in artifacts)
            if not artifacts or paths != tuple(sorted(set(paths))):
                raise ContractValidationError("canonical replay model artifacts are invalid")
        expected_match = tuple(item.sha256 for item in self.output_artifacts) == tuple(
            item.sha256 for item in self.legacy_artifacts
        )
        if self.output_hashes_match_legacy is not expected_match:
            raise ContractValidationError("canonical replay output match flag is inconsistent")
        if self.replay_succeeded is not True:
            raise ContractValidationError("canonical replay model result requires success")


@dataclass(frozen=True)
class P2CanonicalReplayManifest:
    run_id: str
    target_start_date: date
    target_end_date: date
    replay_started_at: datetime
    inputs_loaded_at: datetime
    replay_finished_at: datetime
    code_hash: str
    rule_hash: str
    frozen_input_hash: str
    data_snapshot_manifest_hash: str
    replay_universe_hash: str
    pit_market_universe_hash: str
    input_artifacts: tuple[P2ReplayArtifact, ...]
    code_artifacts: tuple[P2ReplayArtifact, ...]
    model_results: tuple[P2CanonicalReplayModelResult, ...]
    code_version_bound: bool
    frozen_input_bound: bool
    legacy_outputs_reproduced: bool
    historical_event_timestamps_confirmed: bool
    simulation_timestamp_inference_used: bool
    pit_role_metadata_confirmed: bool
    status: P2CanonicalReplayStatus
    standard_export_ready: bool
    operational_authorization: bool
    blocked_reason_codes: tuple[str, ...]
    policy_version: str
    policy_hash: str
    manifest_hash: str

    def __post_init__(self) -> None:
        if not self.run_id.strip() or self.target_start_date > self.target_end_date:
            raise ContractValidationError("canonical replay identity is invalid")
        for field_name in ("replay_started_at", "inputs_loaded_at", "replay_finished_at"):
            _require_aware(getattr(self, field_name), field_name)
        if not self.replay_started_at <= self.inputs_loaded_at <= self.replay_finished_at:
            raise ContractValidationError("canonical replay timestamp order is invalid")
        for field_name in (
            "code_hash",
            "rule_hash",
            "frozen_input_hash",
            "data_snapshot_manifest_hash",
            "replay_universe_hash",
            "pit_market_universe_hash",
            "policy_hash",
            "manifest_hash",
        ):
            _require_hash(getattr(self, field_name), field_name)
        for artifacts in (self.input_artifacts, self.code_artifacts):
            paths = tuple(item.relative_path for item in artifacts)
            if not artifacts or paths != tuple(sorted(set(paths))):
                raise ContractValidationError("canonical replay manifest artifacts are invalid")
        model_codes = tuple(item.model_code for item in self.model_results)
        if model_codes != P2_CANONICAL_REPLAY_MODEL_CODES:
            raise ContractValidationError("canonical replay model coverage is incomplete")
        expected_reproduced = all(
            item.replay_succeeded and item.output_hashes_match_legacy
            for item in self.model_results
        )
        if self.legacy_outputs_reproduced is not expected_reproduced:
            raise ContractValidationError("canonical replay reproduction flag is inconsistent")
        complete = self.code_version_bound and self.frozen_input_bound and all(
            item.replay_succeeded for item in self.model_results
        )
        expected_status = (
            P2CanonicalReplayStatus.COMPLETE if complete else P2CanonicalReplayStatus.FAILED
        )
        if self.status is not expected_status:
            raise ContractValidationError("canonical replay status is inconsistent")
        if self.historical_event_timestamps_confirmed:
            raise ContractValidationError("canonical replay cannot confirm historical timestamps")
        if self.simulation_timestamp_inference_used:
            raise ContractValidationError("canonical replay cannot infer simulation timestamps")
        if self.pit_role_metadata_confirmed:
            raise ContractValidationError("static replay cannot confirm PIT role metadata")
        if self.standard_export_ready or self.operational_authorization:
            raise ContractValidationError("canonical replay cannot grant downstream authority")
        if not self.blocked_reason_codes:
            raise ContractValidationError("canonical replay requires downstream blockers")
        policy = P2CanonicalReplayPolicy()
        if self.policy_version != policy.version or self.policy_hash != policy.policy_hash():
            raise ContractValidationError("canonical replay policy metadata is invalid")
        payload = asdict(self)
        payload.pop("manifest_hash")
        if self.manifest_hash != canonical_sha256(payload):
            raise ContractValidationError("manifest_hash does not match canonical replay")


def _require_hash(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789ABCDEF" for character in value
    ):
        raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware")


def build_p2_canonical_replay_manifest(
    *,
    run_id: str,
    target_start_date: date,
    target_end_date: date,
    replay_started_at: datetime,
    inputs_loaded_at: datetime,
    replay_finished_at: datetime,
    code_hash: str,
    rule_hash: str,
    frozen_input_hash: str,
    data_snapshot_manifest_hash: str,
    replay_universe_hash: str,
    pit_market_universe_hash: str,
    input_artifacts: tuple[P2ReplayArtifact, ...],
    code_artifacts: tuple[P2ReplayArtifact, ...],
    model_results: tuple[P2CanonicalReplayModelResult, ...],
    policy: P2CanonicalReplayPolicy | None = None,
) -> P2CanonicalReplayManifest:
    applied_policy = policy or P2CanonicalReplayPolicy()
    sorted_inputs = tuple(sorted(input_artifacts, key=lambda item: item.relative_path))
    sorted_code = tuple(sorted(code_artifacts, key=lambda item: item.relative_path))
    ordered_models = tuple(
        sorted(model_results, key=lambda item: applied_policy.model_codes.index(item.model_code))
    )
    reproduced = all(item.output_hashes_match_legacy for item in ordered_models)
    blockers = (
        "FINAL_OUTCOME_PERIOD_UNAVAILABLE",
        "HISTORICAL_EVENT_TIMESTAMPS_UNCONFIRMED",
        "PIT_ROLE_METADATA_UNCONFIRMED",
        "STANDARD_EXPORT_NOT_RUN",
    )
    payload = {
        "run_id": run_id,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "replay_started_at": replay_started_at,
        "inputs_loaded_at": inputs_loaded_at,
        "replay_finished_at": replay_finished_at,
        "code_hash": code_hash,
        "rule_hash": rule_hash,
        "frozen_input_hash": frozen_input_hash,
        "data_snapshot_manifest_hash": data_snapshot_manifest_hash,
        "replay_universe_hash": replay_universe_hash,
        "pit_market_universe_hash": pit_market_universe_hash,
        "input_artifacts": sorted_inputs,
        "code_artifacts": sorted_code,
        "model_results": ordered_models,
        "code_version_bound": True,
        "frozen_input_bound": True,
        "legacy_outputs_reproduced": reproduced,
        "historical_event_timestamps_confirmed": False,
        "simulation_timestamp_inference_used": False,
        "pit_role_metadata_confirmed": False,
        "status": P2CanonicalReplayStatus.COMPLETE,
        "standard_export_ready": False,
        "operational_authorization": False,
        "blocked_reason_codes": blockers,
        "policy_version": applied_policy.version,
        "policy_hash": applied_policy.policy_hash(),
    }
    return P2CanonicalReplayManifest(
        **payload,
        manifest_hash=canonical_sha256(payload),
    )
