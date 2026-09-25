"""Allowlisted private projection of recorded, provisional paper reconstruction."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .quant25_paper_live import PROFILE_DISPLAY_NAMES, PROFILE_MODEL_IDS, canonical_sha256

SCHEMA = "q25_reconstructed_mock_view_v1"
MANIFEST_SCHEMA = "q25_reconstructed_mock_view_manifest_v1"
CLASSIFICATION = "retrospective_reconstruction_not_live"
STATUS = "PROVISIONAL_SOURCE_REVIEW_PENDING"
WARNINGS = ["HISTORICAL_INPUT_AVAILABILITY_UNVERIFIED", "CORPORATE_ACTION_COVERAGE_INCOMPLETE",
            "CASH_DISTRIBUTIONS_EXCLUDED"]
REPORTS = Path(__file__).resolve().parents[3] / "reports"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(value):
    require(isinstance(value, (str, int, float, Decimal)) and not isinstance(value, bool), "invalid number")
    parsed = Decimal(str(value))
    require(parsed.is_finite(), "non-finite number")
    return parsed


def money(value):
    return format(value, "f")


def close(a, b):
    require(abs(number(a) - number(b)) <= Decimal("1e-12"), "accounting mismatch")


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "timezone required")
    return result


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def project(report, prices, *, source_manifest_sha256, generated_at):
    require(isinstance(source_manifest_sha256, str) and len(source_manifest_sha256) == 64 and
            all(c in "0123456789abcdef" for c in source_manifest_sha256), "invalid source pin")
    require(report["classification"] == CLASSIFICATION and report["schema"] ==
            "q25_retrospective_paper_reconstruction_v1", "wrong reconstruction classification")
    require(report["source_verification_status"] == "PROVISIONAL_NOT_VERIFIED_LIVE", "unsupported status")
    require(report["model_start_date"] == "2026-09-07", "approved start changed")
    require(timestamp(report["price_snapshot_read_at"]) <= timestamp(report["generated_at"])
            <= timestamp(generated_at), "invalid generation chronology")
    require(date.fromisoformat(report["valuation_end_date"]) <=
            timestamp(report["price_snapshot_read_at"]).astimezone(timezone(timedelta(hours=9))).date(),
            "valuation after recorded price read")
    capital = number(report["starting_capital_krw_per_profile"])
    require(capital == Decimal("100000000") and number(report["fee_rate"]) == Decimal(".002"),
            "unapproved capital or fee")
    require(set(report["profiles"]) == set(PROFILE_MODEL_IDS), "exact profiles required")
    quotes = {}
    for row in prices:
        key = row["date"], row["ticker"]
        require(key not in quotes, "duplicate price")
        require(number(row["open"]) > 0 and number(row["close"]) > 0, "invalid price")
        quotes[key] = row
    trades = defaultdict(list)
    for trade in report["trades"]:
        require(trade["profile_id"] in PROFILE_MODEL_IDS, "unknown trade profile")
        trades[trade["profile_id"], trade["date"]].append(trade)
    daily = defaultdict(list)
    for row in report["daily"]:
        require(row["profile_id"] in PROFILE_MODEL_IDS, "unknown daily profile")
        daily[row["profile_id"]].append(row)
    require(set(daily) == set(PROFILE_MODEL_IDS), "three populated profiles required")
    models, expected_days, consumed_trades = [], None, 0
    for profile in PROFILE_MODEL_IDS:
        rows = daily[profile]
        days = [row["date"] for row in rows]
        require(days == sorted(set(days)) and days[0] == report["model_start_date"] and
                days[-1] == report["valuation_end_date"], "invalid evaluation dates")
        for day in days:
            date.fromisoformat(day)
        require(expected_days is None or days == expected_days, "profile date mismatch")
        expected_days = days
        cash, previous, peak, mdd, total_fees = capital, capital, capital, Decimal(0), Decimal(0)
        shares, series, positions, count = {}, [], [], 0
        for row in rows:
            day = row["date"]
            require(row["classification"] == CLASSIFICATION and row["valuation_status"] == STATUS and
                    row["verified_live_nav_krw"] is None and row["verified_live_return_percent"] is None,
                    "provisional values cannot be promoted")
            fee_today = Decimal(0)
            for trade in trades[profile, day]:
                ticker, quantity = trade["ticker"], trade["quantity"]
                require(type(quantity) is int and quantity > 0, "invalid trade units")
                price = number(quotes[day, ticker]["open"])
                gross, fee = price * quantity, price * quantity * Decimal(".002")
                close(trade["open"], price)
                close(trade["gross_krw"], gross)
                close(trade["fee_krw"], fee)
                before = shares.get(ticker, 0)
                if trade["side"] == "BUY":
                    cash -= gross + fee
                    shares[ticker] = before + quantity
                else:
                    require(trade["side"] == "SELL" and before >= quantity, "invalid sale")
                    cash += gross - fee
                    shares[ticker] = before - quantity
                require(cash >= 0, "negative cash")
                fee_today += fee
                count += 1
            positions, seen, nav = [], set(), cash
            for p in row["positions"]:
                ticker, quantity = p["ticker"], p["quantity"]
                require(isinstance(ticker, str) and len(ticker) == 6 and ticker.isdigit()
                        and ticker not in seen and type(quantity) is int and quantity > 0,
                        "invalid or duplicate position")
                seen.add(ticker)
                require(shares.get(ticker) == quantity, "holdings differ from trades")
                price = number(quotes[day, ticker]["close"])
                value = price * quantity
                close(p["close"], price)
                close(p["market_value_krw"], value)
                nav += value
                positions.append({"ticker": ticker, "quantity": quantity, "close": money(price),
                                  "market_value_krw": money(value)})
            require(seen == {t for t, n in shares.items() if n} and len(seen) <= 30, "holding set mismatch")
            require(nav > 0, "invalid NAV")
            peak = max(peak, nav)
            drawdown = (nav / peak - 1) * 100
            mdd = min(mdd, drawdown)
            daily_return, cumulative = (nav / previous - 1) * 100, (nav / capital - 1) * 100
            for field, expected in {"cash_krw": cash, "candidate_nav_krw": nav,
                                    "fees_krw": fee_today, "candidate_return_percent": daily_return,
                                    "candidate_cumulative_return_percent": cumulative,
                                    "candidate_drawdown_percent": drawdown,
                                    "candidate_max_drawdown_percent": mdd}.items():
                close(row[field], expected)
            series.append({"date": day, "nav_krw": money(nav), "return_percent": money(daily_return),
                           "cumulative_return_percent": money(cumulative), "drawdown_percent": money(drawdown)})
            previous, total_fees = nav, total_fees + fee_today
        summary = report["profiles"][profile]
        require(summary["evaluated_days"] == len(rows) and summary["verified_live_performance"] is None,
                "invalid profile summary")
        close(summary["candidate_final_nav_krw"], previous)
        close(summary["candidate_cumulative_return_percent"], series[-1]["cumulative_return_percent"])
        close(summary["candidate_max_drawdown_percent"], mdd)
        consumed_trades += count
        models.append({"profile_id": profile, "model_id": PROFILE_MODEL_IDS[profile],
                       "display_name": PROFILE_DISPLAY_NAMES[profile], "initial_capital_krw": money(capital),
                       "nav_krw": money(previous), "cash_krw": money(cash),
                       "cumulative_return_percent": series[-1]["cumulative_return_percent"],
                       "max_drawdown_percent": money(mdd), "total_fees_krw": money(total_fees),
                       "assumed_trade_count": count, "valuation_days": len(rows),
                       "positions": positions, "series": series})
    require(consumed_trades == len(report["trades"]), "trade outside evaluation dates")
    payload = {"schema_version": SCHEMA, "generated_at": generated_at,
               "source_generated_at": report["generated_at"], "price_snapshot_read_at": report["price_snapshot_read_at"],
               "evaluation_start": report["model_start_date"], "evaluation_end": report["valuation_end_date"],
               "classification": CLASSIFICATION, "valuation_status": STATUS, "public_eligible": False,
               "verified_live_samples": 0, "source_manifest_sha256": source_manifest_sha256,
               "warnings": WARNINGS, "models": models}
    payload["output_hash"] = canonical_sha256(payload)
    return payload


def export_view(run_dir: Path, *, expected_manifest_sha256: str, output_dir: Path):
    run_dir, output_dir = Path(run_dir).resolve(), Path(output_dir).resolve()
    require(output_dir.is_relative_to(REPORTS.resolve()) and not output_dir.exists(), "new private reports output required")
    raw_manifest = (run_dir / "manifest.json").read_bytes()
    require(hashlib.sha256(raw_manifest).hexdigest() == expected_manifest_sha256, "manifest SHA mismatch")
    manifest = json.loads(raw_manifest, object_pairs_hook=unique)
    require(manifest["schema"] == "q25_retrospective_paper_manifest_v1" and
            manifest["classification"] == CLASSIFICATION, "wrong source manifest")
    require(set(manifest["files"]) == {"reconstruction.json", "decisions.json", "price_rows.json"}, "unexpected source files")
    sources = {}
    for name, expected in manifest["files"].items():
        raw = (run_dir / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, "source SHA mismatch")
        sources[name] = json.loads(raw, object_pairs_hook=unique)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = project(sources["reconstruction.json"], sources["price_rows.json"],
                      source_manifest_sha256=expected_manifest_sha256, generated_at=generated_at)
    require((run_dir / "manifest.json").read_bytes() == raw_manifest, "manifest changed during export")
    for name, expected in manifest["files"].items():
        require(hashlib.sha256((run_dir / name).read_bytes()).hexdigest() == expected, "source changed during export")
    output_dir.mkdir(parents=True, exist_ok=False)
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    (output_dir / "payload.json").write_bytes(raw)
    exported = {"schema_version": MANIFEST_SCHEMA, "generated_at": generated_at,
                "payload": {"file": "payload.json", "sha256": hashlib.sha256(raw).hexdigest()},
                "output_hash": payload["output_hash"]}
    (output_dir / "manifest.json").write_text(json.dumps(exported, indent=2) + "\n", encoding="utf-8")
    return payload
