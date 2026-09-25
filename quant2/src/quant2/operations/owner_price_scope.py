"""Pinned, optional owner scope for generating consumer price requirements."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pandas as pd

# feature: (maximum input sessions, minimum warmup sessions, raw price fields)
SUPPORTED_FIELDS = {
    "open": (1, 1, ("open",)), "close": (1, 1, ("close",)),
    "volume": (1, 1, ("volume",)), "value_won": (1, 1, ("close", "volume")),
    "adv20": (20, 10, ("close", "volume")),
    "adv60": (60, 30, ("close", "volume")),
    "vol_ratio_20": (20, 10, ("close", "volume")),
    "mom20": (21, 21, ("close",)),
    "breakout60": (60, 30, ("close",)), "ma60": (60, 30, ("close",)),
    "ma120": (120, 60, ("close",)), "ma60_slope": (65, 35, ("close",)),
    "ma120_slope": (125, 65, ("close",)),
    "trend_up": (65, 35, ("close",)), "ma_gap_60": (60, 30, ("close",)),
}


def _day(value: str) -> str:
    if not isinstance(value, str) or pd.Timestamp(value).strftime("%Y-%m-%d") != value:
        raise ValueError("owner scope requires YYYY-MM-DD dates")
    return value


def load_optional(consumer: str, requested_asof: str) -> dict | None:
    path = os.getenv("QUANT_PRICE_OWNER_SCOPE_PATH", "").strip()
    pin = os.getenv("QUANT_PRICE_OWNER_SCOPE_SHA256", "").strip().lower()
    if not path and not pin:
        return None
    if not path or len(pin) != 64 or any(ch not in "0123456789abcdef" for ch in pin):
        raise ValueError("owner scope path and SHA256 pin required together")
    source = Path(path).resolve(strict=True)
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError("owner scope hash mismatch")
    scope = json.loads(raw)
    if (scope.get("schema") != "QUANT_PRICE_OWNER_SCOPE_V1"
            or scope.get("consumer") != consumer
            or _day(scope.get("requested_asof")) != requested_asof
            or not scope.get("consumer_purpose")):
        raise ValueError("owner scope consumer/date/purpose mismatch")
    sessions = scope.get("calendar_sessions")
    if not isinstance(sessions, list) or not sessions or sessions != sorted(set(map(_day, sessions))):
        raise ValueError("owner calendar must be sorted unique explicit sessions")
    if sessions[-1] > requested_asof:
        raise ValueError("owner calendar contains future sessions")
    if not isinstance(scope.get("candidates_by_decision"), list) or not scope["candidates_by_decision"]:
        raise ValueError("owner candidate scopes required")
    if not isinstance(scope.get("fields"), list) or not scope["fields"]:
        raise ValueError("owner field windows required")
    scope["_pin"] = {"path": str(source), "sha256": pin}
    return scope


def expected_for(scope: dict, decision_date: str, actual_tickers: set[str],
                 consumed_fields: set[str], *, field_rules: dict | None = None) -> dict:
    """Generate from owner calendar and candidates, never from observed price rows."""
    day = _day(decision_date)
    entries = [item for item in scope["candidates_by_decision"] if item.get("decision_date") == day]
    if len(entries) != 1:
        raise ValueError("one exact owner candidate scope per decision required")
    members = entries[0].get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("owner candidate members required")
    tickers = []
    for member in members:
        ticker = member.get("ticker")
        if (not isinstance(ticker, str) or re.fullmatch(r"[0-9A-Z]{6}", ticker) is None
                or not _day(member.get("valid_from")) <= day
                or (member.get("valid_through") and day > _day(member["valid_through"]))):
            raise ValueError("invalid owner candidate validity")
        tickers.append(ticker)
    if len(tickers) != len(set(tickers)):
        raise ValueError("duplicate owner candidate")
    sessions = [session for session in scope["calendar_sessions"] if session <= day]
    if not sessions or sessions[-1] != day:
        raise ValueError("owner calendar missing decision session")
    rules = field_rules or SUPPORTED_FIELDS
    fields = scope["fields"]
    declared = {item.get("name"): item for item in fields}
    if len(declared) != len(fields):
        raise ValueError("duplicate owner field")
    issues = []
    if set(tickers) != actual_tickers:
        issues.append("owner_candidate_differs_from_actual_loaded_universe")
    if not consumed_fields <= set(declared):
        issues.append("consumed_field_not_declared")
    unsupported = sorted(name for name in declared if name not in rules)
    if unsupported:
        issues.append("unsupported_owner_fields")
    requirements: dict[tuple[str, str], set[str]] = {}
    window_status = {}
    for name, item in declared.items():
        if name not in rules:
            continue
        maximum, warmup, raw_fields = rules[name]
        if maximum < 1 or warmup < 1 or warmup > maximum:
            raise ValueError(f"invalid model window: {name}")
        if (item.get("lookback_sessions") != maximum or item.get("warmup_sessions") != warmup
                or item.get("source_fields") != list(raw_fields)
                or item.get("purpose") != scope["consumer_purpose"]):
            raise ValueError(f"owner field contract mismatch: {name}")
        window = sessions[-maximum:]
        window_status[name] = {"available_sessions": len(window),
                               "lookback_sessions": maximum, "warmup_sessions": warmup,
                               "warmup_satisfied": len(window) >= warmup,
                               "full_window_satisfied": len(window) >= maximum}
        if len(window) < warmup:
            issues.append(f"warmup_insufficient:{name}")
        if len(window) < maximum:
            issues.append(f"lookback_incomplete:{name}")
        for session in window:
            for ticker in tickers:
                requirements.setdefault((session, ticker), set()).update(raw_fields)
    required = [
        {"date": session, "ticker": ticker, "fields": sorted(raw), "allow_nontrading": False}
        for (session, ticker), raw in sorted(requirements.items())
    ]
    return {"required": required, "issues": sorted(set(issues)),
            "ready_for_scoped_audit": bool(required) and not issues,
            "unsupported_fields": unsupported, "window_status": window_status,
            "owner_pin": scope["_pin"],
            "owner_calendar_certified": scope.get("calendar_certified") is True,
            "owner_historical_pit_certified": scope.get("historical_pit_certified") is True,
            "freshness_policy": scope.get("freshness_policy") or "unspecified"}
