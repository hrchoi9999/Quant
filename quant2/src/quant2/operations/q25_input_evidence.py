"""Optional required-key scope from Q25's pinned daily calendar and cohort."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from src.quant2.operations.owner_price_scope import expected_for, load_optional


def export_daily_scope(*, day: str, calendar: list[str], stocks: list[str],
                       prices: pd.DataFrame, config: dict) -> Path | None:
    directory = os.getenv("QUANT_Q25_REQUIRED_EXPORT_DIR", "").strip()
    if not directory:
        return None
    if day not in calendar or calendar != sorted(set(calendar)):
        raise ValueError("pinned Q25 calendar required for scope export")
    tickers = [str(ticker).zfill(6) for ticker in stocks]
    if not tickers or len(tickers) != len(set(tickers)):
        raise ValueError("unique declared Q25 stock cohort required")
    index = calendar.index(day)
    dates = calendar[max(0, index - 65):index + 1]
    required = [
        {"date": date, "ticker": ticker,
         "fields": ["open", "close", "volume"], "allow_nontrading": False}
        for date in dates for ticker in tickers
    ]
    observed = set(zip(prices.ticker.astype(str).str.zfill(6), prices.date.astype(str)))
    missing = [row for row in required if (row["ticker"], row["date"]) not in observed]
    owner_scope = load_optional("Q25", day)
    owner = None
    if owner_scope is not None:
        rules = {name: (66, 66, (name,)) for name in ("open", "close", "volume")}
        owner = expected_for(owner_scope, day, set(tickers), set(rules), field_rules=rules)
        owner_keys = {(row["date"], row["ticker"], tuple(sorted(row["fields"])))
                      for row in owner["required"]}
        capture_keys = {(row["date"], row["ticker"], tuple(sorted(row["fields"])))
                        for row in required}
        if owner_keys != capture_keys:
            owner["issues"].append("owner_scope_differs_from_q25_capture_scope")
            owner["ready_for_scoped_audit"] = False
    refs = {
        name: {"path": str(Path(config[name]["path"]).resolve()),
               "sha256": config[name]["sha256"]}
        for name in ("calendar", "universe", "rules", "sector", "etf_intent")
    }
    payload = {
        "schema": "Q25_DAILY_REQUIRED_PRICE_SCOPE_V1", "consumer": "Q25",
        "requested_asof": day, "target_data_asof": day,
        "calendar_basis": "pinned_explicit_confirmed_calendar",
        "candidate_basis": "pinned_daily_universe_stock_cohort",
        "window_dates": dates, "stock_tickers": tickers,
        "required": required, "missing_observed_keys": missing,
        "expected_owner_keys": owner["required"] if owner else None,
        "owner_scope_pin": owner_scope["_pin"] if owner_scope else None,
        "owner_scope_ready_for_scoped_audit": owner["ready_for_scoped_audit"] if owner else False,
        "owner_scope_issues": owner["issues"] if owner else [],
        "supported_price_fields": ["open", "close", "volume"],
        "unsupported_price_fields": ["sector_input_prices", "etf_intent_prices"],
        "historical_pit_certified": False,
        "input_refs": refs,
        "price_db": str(Path(config["price_db"]).resolve()),
        "feature_db": str(Path(config["features_db"]).resolve()),
        "halt_or_rights_exception_certified": False,
        "sector_and_holdings_price_scope_certified": False,
        "coverage_complete": False,
    }
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"required__q25__{day}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    return path
