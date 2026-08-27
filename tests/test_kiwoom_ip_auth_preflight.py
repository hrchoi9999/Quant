from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "harness" / "check_kiwoom_ip_auth.py"
SPEC = importlib.util.spec_from_file_location("check_kiwoom_ip_auth", MODULE_PATH)
assert SPEC and SPEC.loader
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


def test_preflight_passes_without_exposing_token() -> None:
    result = PREFLIGHT.run_preflight(
        asof="2026-08-26",
        token_getter=lambda: ("secret-access-token", "20260828120000"),
        investor_request=lambda *_args, **_kwargs: ([{"dt": "20260826"}], "N", ""),
        public_ip_getter=lambda _url: "203.0.113.10",
    )

    assert result["status"] == "passed"
    assert result["resume_allowed"] is True
    assert result["current_public_ip"] == "203.0.113.10"
    assert result["investor_row_count"] == 1
    assert "secret-access-token" not in str(result)


def test_preflight_classifies_8050_as_allowed_ip_update() -> None:
    def rejected_token() -> tuple[str, str | None]:
        raise RuntimeError(
            "Kiwoom token failed: return_code=3, return_msg=8050: 지정단말기 인증에 실패했습니다"
        )

    result = PREFLIGHT.run_preflight(
        asof="2026-08-26",
        token_getter=rejected_token,
        investor_request=lambda *_args, **_kwargs: ([], "N", ""),
        public_ip_getter=lambda _url: "203.0.113.20",
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "blocked_needs_kiwoom_allowed_ip_update"
    assert result["resume_allowed"] is False
    assert result["retry_policy"] == "after_user_ip_update_confirmation_once"


def test_public_ip_failure_does_not_block_valid_kiwoom_auth() -> None:
    def public_ip_failure(_url: str) -> str:
        raise TimeoutError("public IP lookup timed out")

    result = PREFLIGHT.run_preflight(
        asof="2026-08-26",
        token_getter=lambda: ("token", None),
        investor_request=lambda *_args, **_kwargs: ([], "N", ""),
        public_ip_getter=public_ip_failure,
    )

    assert result["status"] == "passed"
    assert result["current_public_ip"] is None
    assert "TimeoutError" in result["public_ip_error"]
