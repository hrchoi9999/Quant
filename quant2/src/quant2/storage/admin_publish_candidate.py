"""Inactive publishing candidate: local plans and injectable, conditional private IO.

No credential lookup, cloud client or default transport is provided here.
The canonical CLI remains dry-run only for this candidate pending activation approval.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import quote

from src.quant2.operations.ai_retirement import is_retired_object
from src.quant2.operations.ai_retirement import load as retirement_policy

PUBLIC_BUCKET = "quantservice-489808-market-analysis"
PRIVATE_BUCKET = "quantservice-489808-private-admin"
SUPPLEMENTARY_OBJECTS = frozenset({"quantservice_tseries_discovery.json"})
RESEARCH_OBJECTS = frozenset({
    "e_series_etf_sleeve_selection_current.json",
    "e_series_etf_sleeve_portfolio_current.json",
    "e_series_etf_mode_switch_cost_adjusted_current.json",
    "e_series_etf_mode_switch_turnover_buffer_current.json",
    "e_series_etf_operational_hardening_current.json",
    "e_series_etf_operational_policy_hierarchy_current.json",
    "e_series_etf_total_return_adjustment_current.json",
    "ai_learning_overlay_monitor_current.json",
    "internal_models_ai_overlay_shadow_current.json",
})
ADMIN_OPTIONAL_KEYS = (
    "ADMIN_INTERNAL_VALIDATION_CURRENT_OBJECT",
    "ADMIN_AI_SHADOW_OBSERVATION_OBJECT",
    "ADMIN_STRATEGY_RESEARCH_OBSERVATION_OBJECT",
    "ADMIN_AI_LEARNING_MODELS_OBJECT",
    "ADMIN_DOWNSIDE_RISK_AI_OBJECT",
    "ADMIN_DOWNSIDE_RISK_AI_SHADOW_OBJECT",
    "ADMIN_CANDIDATE_RANK_DELTA_AI_OBJECT",
    "ADMIN_THEME_PERSISTENCE_AI_OBJECT",
    "ADMIN_ETF_AI_SHADOW_PORTFOLIO_OBJECT",
)
PRIVATE_STANDARD_NAMES = frozenset({
    "admin_new_entry_tracker.json", "internal_model_performance_history.json",
    "internal_model_validation_current.json", "internal_model_validation_history.json",
    "ai_shadow_observation.json", "strategy_research_observation.json",
    "ai_learning_models_current.json", "downside_risk_ai_current.json",
    "downside_risk_ai_shadow_tracker.json", "candidate_rank_delta_ai_current.json",
    "theme_persistence_ai_current.json", "etf_ai_shadow_portfolio_current.json",
    "valuation_ai_challenger_current.json", "valuation_ai_challenger_shadow_performance.json",
    "valuation_ai_shadow_monitor.json",
})


class CandidateError(RuntimeError):
    def __init__(self, reason: str, evidence: dict | None = None):
        super().__init__(reason)
        self.evidence = dict(evidence or {}, error=reason)


def _reject_constant(value: str) -> None:
    raise CandidateError(f"non-finite JSON constant: {value}")


def build_plan(args: Any, config: dict) -> dict:
    """Mirror the legacy selections without invoking any publisher function."""
    if args.bucket != PUBLIC_BUCKET:
        raise CandidateError("public destination must remain the canonical public bucket")
    if args.admin_bucket not in (None, PRIVATE_BUCKET):
        raise CandidateError("invalid private admin destination")
    research = args.admin_research_object
    retirement_policy()
    if any(is_retired_object(name) for name in research):
        raise CandidateError("Quant 1.0 AI research/current publishing retired")
    if len(research) != len(set(research)) or set(research) - RESEARCH_OBJECTS:
        raise CandidateError("research names must be unique explicit allowlist entries")
    if research and (not args.admin_bucket or args.skip_admin_current
                     or args.admin_strategy_research_observation_only):
        raise CandidateError("research requires private admin opt-in and enabled admin current")
    admin_bucket = args.admin_bucket or args.bucket
    objects: list[dict] = []
    skipped: list[str] = []
    retired_skipped: list[str] = []

    def add(directory: str, pair: tuple[str, str], required: bool = True,
            research_entry: bool = False) -> None:
        name, object_name = pair
        if is_retired_object(name) or is_retired_object(object_name):
            retired_skipped.append(object_name)
            return
        path = config[directory] / name
        is_admin = directory == "ADMIN_CURRENT_DIR"
        bucket = admin_bucket if is_admin else args.bucket
        if is_admin and bucket == PRIVATE_BUCKET:
            required = True
        if is_admin != object_name.startswith("admin/current/"):
            raise CandidateError("admin/public namespace mismatch")
        if is_admin and name not in PRIVATE_STANDARD_NAMES | RESEARCH_OBJECTS:
            raise CandidateError("unregistered admin name")
        if not path.is_file():
            if required:
                raise CandidateError(f"missing required input: {path}")
            skipped.append(str(path))
            return
        raw = path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
        except (ValueError, UnicodeError, CandidateError) as exc:
            raise CandidateError(f"invalid JSON input: {path} ({type(exc).__name__})") from None
        if not isinstance(payload, (dict, list)):
            raise CandidateError(f"invalid JSON payload shape: {path}")
        objects.append({
            "source": str(path), "bucket": bucket, "object": object_name,
            "required": required, "research_opt_in": research_entry,
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "declared_asof": payload.get("as_of_date", payload.get("asof"))
            if isinstance(payload, dict) else None,
            "write_contract": "live_generation_CAS_then_live_content_verification"
            if bucket == PRIVATE_BUCKET else "unchanged_legacy_public_publisher",
        })

    if args.admin_strategy_research_observation_only:
        add("ADMIN_CURRENT_DIR", config["ADMIN_STRATEGY_RESEARCH_OBSERVATION_OBJECT"])
    else:
        if not args.skip_user_current:
            for name in config["ROOT_OBJECTS"]:
                add("CURRENT_DIR", (name, name))
        if not args.skip_user_history:
            for pair in config["USER_HISTORY_OBJECTS"]:
                add("PUBLIC_HISTORY_DIR", pair)
        if not args.skip_tseries_current:
            add("CURRENT_DIR", config["T_SERIES_OBJECT"])
        if not args.skip_tseries_history:
            add("PUBLIC_HISTORY_DIR", config["T_SERIES_HISTORY_OBJECT"])
        if not args.skip_admin_current:
            add("ADMIN_CURRENT_DIR", config["ADMIN_TRACKER_OBJECT"])
        if not args.skip_admin_history:
            add("ADMIN_CURRENT_DIR", config["ADMIN_INTERNAL_PERF_HISTORY_OBJECT"])
            add("ADMIN_CURRENT_DIR", config["ADMIN_INTERNAL_VALIDATION_HISTORY_OBJECT"], False)
        if not args.skip_admin_current:
            for key in ADMIN_OPTIONAL_KEYS:
                add("ADMIN_CURRENT_DIR", config[key], False)
            for pair in config["ADMIN_VALUATION_AI_OBJECTS"]:
                add("ADMIN_CURRENT_DIR", pair, False)
            for name in research:
                add("ADMIN_CURRENT_DIR", (name, f"admin/current/{name}"), research_entry=True)
        if not args.skip_trading_sign_current:
            for pair in config["TRADING_SIGN_OBJECTS"]:
                add("TRADING_SIGN_CURRENT_DIR", pair)
    if not objects:
        raise CandidateError("empty publish selection")
    return {
        "schema_version": "quant_admin_publish_plan_v1",
        "retired_objects_skipped": retired_skipped,
        "status": "LOCAL_PLAN_ONLY_NOT_PUBLISH_AUTHORIZATION",
        "activation_status": "inactive_requires_separate_approval",
        "credential_resolution": False, "network_calls": 0,
        "writer_identity": "unverified", "freshness_validation": "not_performed",
        "object_count": len(objects), "objects": objects, "skipped_optional": skipped,
        "research_selected": sorted(research), "batch_atomic": False,
    }


def run_local_candidate(args: Any, config: dict) -> None:
    plan = build_plan(args, config)
    if not args.dry_run:
        raise CandidateError("private candidate inactive; only --dry-run is allowed")
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def _generation(metadata: dict, bucket: str, name: str) -> str:
    if metadata.get("bucket") != bucket or metadata.get("name") != name:
        raise CandidateError("remote object identity mismatch")
    gen = metadata.get("generation")
    if not isinstance(gen, str) or not gen.isascii() or not gen.isdigit() or int(gen) <= 0:
        raise CandidateError("missing or invalid remote generation")
    return gen


def conditional_private_upload(
    entry: dict, payload: bytes, transport: Any, *, expected_generation: str | None = None,
    supplementary_opt_in: bool = False,
) -> dict:
    """Mock-tested candidate primitive; caller injects transport, never authenticates here.

    Every response is fail-closed. No DELETE, retry, rollback or archive-version GET.
    Failures after POST can mean the write succeeded: evidence forbids blind retries.
    """
    bucket, name = entry["bucket"], entry["object"]
    retirement_policy()
    if is_retired_object(name):
        raise CandidateError("Quant 1.0 AI current publishing retired")
    basename = name.removeprefix("admin/current/")
    if (bucket != PRIVATE_BUCKET or not name.startswith("admin/current/")
            or basename not in PRIVATE_STANDARD_NAMES | RESEARCH_OBJECTS | SUPPLEMENTARY_OBJECTS):
        raise CandidateError("private destination or object is outside allowlist")
    if basename in SUPPLEMENTARY_OBJECTS and (
        supplementary_opt_in is not True or entry.get("supplementary_opt_in") is not True
    ):
        raise CandidateError("supplementary object lacks explicit opt-in")
    if basename in RESEARCH_OBJECTS and entry.get("research_opt_in") is not True:
        raise CandidateError("research object lacks explicit opt-in")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != entry["sha256"] or len(payload) != entry["size_bytes"]:
        raise CandidateError("input changed after plan")
    object_url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{quote(name, safe='')}"
    upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
    evidence: dict[str, Any] = {
        "bucket": bucket, "object": name, "sha256": digest, "size_bytes": len(payload),
        "post_attempted": False, "write_outcome": "not_attempted",
        "verified": False, "retry_allowed": False, "delete_attempted": False,
    }
    try:
        response = transport.get(object_url, params={}, timeout=120, allow_redirects=False)
        if response.status_code == 404:
            prior = "0"
        elif response.status_code == 200:
            prior = _generation(response.json(), bucket, name)
        else:
            raise CandidateError(f"metadata HTTP {response.status_code}")
        evidence["expected_generation"] = prior
        if expected_generation is not None and prior != expected_generation:
            raise CandidateError("remote current changed after backup")
        evidence["post_attempted"] = True
        evidence["write_outcome"] = "unknown"
        response = transport.post(
            upload_url, params={"uploadType": "media", "name": name, "ifGenerationMatch": prior},
            data=payload, headers={"Content-Type": "application/json"},
            timeout=120, allow_redirects=False,
        )
        if response.status_code not in (200, 201):
            if response.status_code in (409, 412):
                evidence["write_outcome"] = "conflict"
            raise CandidateError(f"conditional upload HTTP {response.status_code}")
        evidence["write_outcome"] = "accepted_not_yet_verified"
        uploaded = response.json()
        generation = _generation(uploaded, bucket, name)
        evidence["uploaded_generation"] = generation
        if generation == prior or str(uploaded.get("size")) != str(len(payload)):
            raise CandidateError("upload metadata generation/size mismatch")
        # No generation selector: verify live current, not a retained archived version.
        response = transport.get(
            object_url, params={"alt": "media", "ifGenerationMatch": generation},
            timeout=120, allow_redirects=False,
        )
        if response.status_code != 200:
            raise CandidateError(f"live content verification HTTP {response.status_code}")
        observed = hashlib.sha256(response.content).hexdigest()
        evidence["observed_sha256"] = observed
        if observed != digest or len(response.content) != len(payload):
            raise CandidateError("stored content mismatch")
        response = transport.get(
            object_url, params={"ifGenerationMatch": generation}, timeout=120, allow_redirects=False,
        )
        if response.status_code != 200:
            raise CandidateError(f"final live metadata HTTP {response.status_code}")
        current = response.json()
        if (_generation(current, bucket, name) != generation
                or str(current.get("size")) != str(len(payload))):
            raise CandidateError("final live generation/size mismatch")
        evidence.update(verified=True, write_outcome="verified_live_at_read",
                        verified_generation=generation)
        return evidence
    except CandidateError as exc:
        raise CandidateError(str(exc), evidence) from None
    except Exception as exc:
        # Do not leak response bodies, request headers or tokens into audit evidence.
        raise CandidateError(f"transport_or_response_error:{type(exc).__name__}", evidence) from None
