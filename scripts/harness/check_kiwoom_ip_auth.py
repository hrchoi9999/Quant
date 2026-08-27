from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

KST = timezone(timedelta(hours=9))
DEFAULT_QUANTMARKET_ROOT = Path(os.getenv("QUANTMARKET_ROOT", r"D:\QuantMarket"))
DEFAULT_PUBLIC_IP_URL = "https://api.ipify.org?format=json"
KIWOOM_MANAGEMENT_URL = "https://openapi.kiwoom.com/"


def _today_kst() -> str:
    return datetime.now(tz=KST).date().isoformat()


def fetch_public_ip(url: str = DEFAULT_PUBLIC_IP_URL) -> str:
    request = Request(url, headers={"User-Agent": "Quant-Harness-Kiwoom-Preflight/1.0"})
    with urlopen(request, timeout=15) as response:
        text = response.read().decode("utf-8").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    return str(payload.get("ip") or "").strip()


def classify_auth_error(error: str) -> str:
    normalized = error.lower()
    if "8050" in normalized or "지정단말기 인증" in error:
        return "blocked_needs_kiwoom_allowed_ip_update"
    if "token failed" in normalized or "401" in normalized or "403" in normalized:
        return "blocked_kiwoom_auth_error"
    if "network error" in normalized or "timed out" in normalized or "timeout" in normalized:
        return "blocked_kiwoom_network"
    return "blocked_kiwoom_preflight_failed"


def _load_quantmarket_calls(
    quantmarket_root: Path,
) -> tuple[Callable[..., tuple[str, str | None]], Callable[..., tuple[list[dict[str, Any]], str, str]]]:
    root = str(quantmarket_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    from src.quantmarket_market.kiwoom_investor_flow_collector import (  # noqa: PLC0415
        _request_investor_page,
    )
    from src.quantmarket_market.kiwoom_rest import get_access_token  # noqa: PLC0415

    return get_access_token, _request_investor_page


def run_preflight(
    *,
    asof: str,
    ticker: str = "005930",
    quantmarket_root: Path = DEFAULT_QUANTMARKET_ROOT,
    public_ip_url: str = DEFAULT_PUBLIC_IP_URL,
    skip_public_ip: bool = False,
    token_getter: Callable[..., tuple[str, str | None]] | None = None,
    investor_request: Callable[..., tuple[list[dict[str, Any]], str, str]] | None = None,
    public_ip_getter: Callable[[str], str] = fetch_public_ip,
) -> dict[str, Any]:
    checked_at = datetime.now(tz=KST).replace(microsecond=0).isoformat()
    public_ip = None
    public_ip_error = None
    if not skip_public_ip:
        try:
            public_ip = public_ip_getter(public_ip_url) or None
        except Exception as exc:  # Public IP evidence is useful but not an auth gate.
            public_ip_error = f"{type(exc).__name__}: {exc}"[:300]

    try:
        if token_getter is None or investor_request is None:
            token_getter, investor_request = _load_quantmarket_calls(quantmarket_root)
        token, expires_dt = token_getter()
        rows, continuation, _next_key = investor_request(
            token,
            ticker,
            asof,
            "1",
            retries=0,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        reason = classify_auth_error(error)
        return {
            "source_name": "kiwoom_ip_auth_preflight",
            "status": "blocked",
            "reason": reason,
            "checked_at": checked_at,
            "asof": asof,
            "ticker": ticker,
            "current_public_ip": public_ip,
            "public_ip_error": public_ip_error,
            "token_ok": False,
            "investor_query_ok": False,
            "resume_allowed": False,
            "retry_policy": "after_user_ip_update_confirmation_once",
            "management_url": KIWOOM_MANAGEMENT_URL,
            "error": error,
        }

    return {
        "source_name": "kiwoom_ip_auth_preflight",
        "status": "passed",
        "reason": None,
        "checked_at": checked_at,
        "asof": asof,
        "ticker": ticker,
        "current_public_ip": public_ip,
        "public_ip_error": public_ip_error,
        "token_ok": bool(token),
        "token_expires_dt": expires_dt,
        "investor_query_ok": True,
        "investor_row_count": len(rows),
        "continuation": continuation,
        "resume_allowed": True,
        "retry_policy": "not_required",
        "management_url": KIWOOM_MANAGEMENT_URL,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Kiwoom allowed-IP/token preflight for WD02."
    )
    parser.add_argument("--asof", default=_today_kst(), help="YYYY-MM-DD")
    parser.add_argument("--ticker", default="005930")
    parser.add_argument("--quantmarket-root", type=Path, default=DEFAULT_QUANTMARKET_ROOT)
    parser.add_argument("--public-ip-url", default=DEFAULT_PUBLIC_IP_URL)
    parser.add_argument("--skip-public-ip", action="store_true")
    parser.add_argument("--report-path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_preflight(
        asof=args.asof,
        ticker=args.ticker,
        quantmarket_root=args.quantmarket_root,
        public_ip_url=args.public_ip_url,
        skip_public_ip=args.skip_public_ip,
    )
    if args.report_path:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
