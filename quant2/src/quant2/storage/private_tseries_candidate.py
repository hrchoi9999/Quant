"""Local-only supplementary mapping; no credentials, transport or activation CLI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.quant2.operations.ai_retirement import RetiredModelError, require_model_active

from .admin_publish_candidate import PRIVATE_BUCKET, CandidateError

SOURCE = (Path(__file__).resolve().parents[4]
          / "service_platform/web/public_data/current/quantservice_tseries_discovery.json")
OBJECT = "admin/current/quantservice_tseries_discovery.json"


def _nonfinite(value: str) -> None:
    raise CandidateError("non-finite JSON is not allowed")


def build_private_tseries_plan(
    *, expected_sha256: str, private_bucket: str, supplementary_opt_in: bool = False,
) -> dict:
    """Pin existing bytes without changing their dates or asserting freshness."""
    try:
        require_model_active("T-STOCK-V01")
    except RetiredModelError as exc:
        raise CandidateError(str(exc)) from None
    if supplementary_opt_in is not True or private_bucket != PRIVATE_BUCKET:
        raise CandidateError("explicit supplementary opt-in and exact private bucket required")
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)):
        raise CandidateError("lowercase SHA256 source pin required")
    try:
        raw = SOURCE.read_bytes()
    except OSError:
        raise CandidateError("existing T-series source is unavailable") from None
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise CandidateError("existing T-series source changed")
    try:
        payload = json.loads(raw.decode("utf-8-sig"), parse_constant=_nonfinite)
    except (ValueError, UnicodeError):
        raise CandidateError("existing T-series source is invalid JSON") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise CandidateError("T-series object with models list required")
    return {
        "status": "LOCAL_PLAN_ONLY_NOT_PUBLISH_AUTHORIZATION",
        "activation_status": "inactive_requires_separate_approval",
        "credentials_used": False, "network_calls": 0, "source_regenerated": False,
        "freshness_validation": "not_performed_existing_dates_preserved",
        "declared_dates": {k: payload[k] for k in ("asof", "as_of_date", "generated_at")
                           if k in payload},
        "objects": [{
            "source": str(SOURCE), "bucket": private_bucket, "object": OBJECT,
            "size_bytes": len(raw), "sha256": digest, "supplementary_opt_in": True,
            "research_opt_in": False,
            "write_contract": "live_generation_CAS_then_live_content_verification",
        }],
        "legacy_admin24_unchanged": True,
        "public_write_block_activated": False,
    }
