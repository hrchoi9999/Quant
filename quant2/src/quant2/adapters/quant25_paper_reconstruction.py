"""Separate, hindsight Q25 paper-account reconstruction; never writes OS sources."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

from .quant25_daily_valuation_sources import _owner_coverage
from .quant25_live_source_connection import (
    _journal,
    audit_forward_sources,
)
from .quant25_paper_live import canonical_sha256, file_sha256
from .quant25_paper_source_context import load_context

ROOT = Path(__file__).resolve().parents[3]

SCHEMA = "q25_retrospective_paper_reconstruction_v1"
CLASSIFICATION = "retrospective_reconstruction_not_live"
CAPITAL = Decimal("100000000")
FEE_RATE = Decimal("0.002")
PRICE_COLUMNS = ("ticker", "date", "open", "high", "low", "close", "volume",
                 "value", "source", "created_at", "updated_at")


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _money(value: Decimal) -> str:
    return format(value, "f")


def _dec(value: object) -> Decimal:
    result = Decimal(str(value))
    _require(result.is_finite(), "non-finite number")
    return result


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _completed_asof(path: Path, expected_sha256: str) -> str:
    _require(file_sha256(path) == expected_sha256.lower(), "completion receipt SHA mismatch")
    receipt = _read_json(path)
    _require(receipt.get("overall_task_complete") is True and
             isinstance(receipt.get("final_completed_asof"), str),
             "data cycle is not completed")
    day = receipt["final_completed_asof"]
    _require(len(day) == 10 and datetime.fromisoformat(day).date().isoformat() == day,
             "invalid completed data_asof")
    return day


def _prior_bundle(root: Path, expected_sha256: str) -> tuple[dict, list[dict], list[dict]]:
    _require(root.resolve().is_relative_to(ROOT / "reports"), "prior run outside reports")
    manifest_path = root / "manifest.json"
    _require(file_sha256(manifest_path) == expected_sha256.lower(), "prior manifest SHA mismatch")
    manifest = _read_json(manifest_path)
    _require(manifest.get("schema") == "q25_retrospective_paper_manifest_v1" and
             manifest.get("classification") == CLASSIFICATION, "wrong prior manifest")
    _require(set(manifest.get("files", {})) ==
             {"price_rows.json", "decisions.json", "reconstruction.json"},
             "prior manifest file list changed")
    for name, digest in manifest["files"].items():
        _require(file_sha256(root / name) == digest, "prior file SHA mismatch: " + name)
    result = _read_json(root / "reconstruction.json")
    rows = _read_json(root / "price_rows.json")
    decisions = _read_json(root / "decisions.json")
    _require(result["schema"] == SCHEMA and result["classification"] == CLASSIFICATION and
             result["generated_at"] == manifest["generated_at"] and
             canonical_sha256(rows) == result["source_hashes"]["price_rows_sha256"],
             "prior run source pin mismatch")
    return result, rows, decisions


def _unchanged_economic_prices(saved_rows: list[dict], current_rows: list[dict]) -> None:
    current = {(row["ticker"], row["date"]): row for row in current_rows}
    for saved in saved_rows:
        key = saved["ticker"], saved["date"]
        _require(key in current, "historical price row disappeared: " + str(key))
        row = current[key]
        for field in ("open", "high", "low", "close", "volume", "value"):
            same = (row[field] is None and saved[field] is None) or (
                row[field] is not None and saved[field] is not None and
                _dec(row[field]) == _dec(saved[field]))
            _require(same,
                     "historical price economic value changed; correction run required: " + str(key))
        _require(row["source"] == saved["source"],
                 "historical price source changed; correction run required: " + str(key))


def _price_rows(db: Path, tickers: list[str], dates: list[str]) -> list[dict]:
    _require(tickers and dates, "empty price scope")
    uri = db.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        query = ("SELECT " + ",".join(PRICE_COLUMNS) + " FROM prices_daily "
                 "WHERE ticker IN (" + ",".join("?" for _ in tickers) + ") "
                 "AND date IN (" + ",".join("?" for _ in dates) + ") "
                 "ORDER BY ticker,date")
        rows = [dict(zip(PRICE_COLUMNS, row)) for row in con.execute(query, tickers + dates)]
    finally:
        con.close()
    return rows


def _price_map(rows: list[dict]) -> dict[tuple[str, str], dict]:
    result = {}
    for row in rows:
        key = row["ticker"], row["date"]
        _require(key not in result, "duplicate price key")
        _require(row["source"] == "krx_openapi" and
                 all(_dec(row[name]) > 0 for name in ("open", "high", "low", "close")) and
                 int(row["volume"]) > 0, "unusable price row")
        _require(_dec(row["low"]) <= _dec(row["open"]) <= _dec(row["high"]) and
                 _dec(row["low"]) <= _dec(row["close"]) <= _dec(row["high"]),
                 "OHLC order invalid")
        result[key] = row
    return result


def _snapshot_weights(baseline: dict) -> dict[str, dict[str, Decimal]]:
    result = {}
    for model in baseline["models"]:
        account = model["actual_portfolio"]
        nav = _dec(account["nav"])
        _require(nav > 0 and account["nav_equation_status"] == "pass", "bad 9/4 NAV")
        weights = {position["ticker"]: _dec(position["market_value"]) / nav
                   for position in account["positions"]}
        _require(len(weights) == len(account["positions"]), "duplicate initial holding")
        _require(abs(sum(weights.values()) + _dec(account["cash"]) / nav - 1)
                 < Decimal("1e-9"), "initial account not balanced")
        result[model["profile_id"]] = weights
    return result


def _target_weights(decision: dict, profile_id: str) -> dict[str, Decimal]:
    profile = decision["profiles"][profile_id]
    positions = profile["target_positions"]
    weights = {row["ticker"]: _dec(row["target_weight"]) for row in positions}
    _require(len(weights) == len(positions), "duplicate target holding")
    _require(abs(sum(weights.values()) + _dec(profile["cash_target"]) - 1)
             < Decimal("1e-9"), "target account not balanced")
    return weights


def _rebalance(shares: dict[str, int], cash: Decimal, weights: dict[str, Decimal],
               prices: dict[str, Decimal], *, profile: str, day: str,
               source: str, eligible: dict[str, bool] | None = None) -> tuple[Decimal, list[dict], list[dict]]:
    """At the day's open, sell excess first and buy whole shares with 20bp fee."""
    nav_before = cash + sum(Decimal(count) * prices[ticker] for ticker, count in shares.items())
    _require(nav_before > 0 and Decimal(0) <= sum(weights.values()) <= 1,
             "invalid pretrade NAV or target weights")
    desired = {ticker: int((nav_before * weight / prices[ticker]).to_integral_value(rounding=ROUND_DOWN))
               for ticker, weight in weights.items() if weight > 0}
    trades, nonfills = [], []
    for ticker in sorted(set(shares) | set(desired)):
        before = shares.get(ticker, 0)
        after = desired.get(ticker, 0)
        if after >= before:
            continue
        quantity = before - after
        gross = Decimal(quantity) * prices[ticker]
        fee = gross * FEE_RATE
        cash += gross - fee
        shares[ticker] = after
        trades.append({"date": day, "profile_id": profile, "source": source,
                       "ticker": ticker, "side": "SELL", "quantity": quantity,
                       "open": _money(prices[ticker]), "gross_krw": _money(gross),
                       "fee_krw": _money(fee)})
    for ticker in sorted(desired):
        quantity = desired[ticker] - shares.get(ticker, 0)
        if quantity <= 0:
            continue
        if eligible is not None and shares.get(ticker, 0) == 0 and eligible.get(ticker) is not True:
            nonfills.append({"date": day, "profile_id": profile, "source": source,
                             "ticker": ticker, "side": "BUY", "requested_quantity": quantity,
                             "reason": "FRESH_ENTRY_INELIGIBLE"})
            continue
        affordable = int((cash / (prices[ticker] * (1 + FEE_RATE))).to_integral_value(rounding=ROUND_DOWN))
        if affordable < quantity:
            nonfills.append({"date": day, "profile_id": profile, "source": source,
                             "ticker": ticker, "side": "BUY",
                             "requested_quantity": quantity - affordable,
                             "reason": "INSUFFICIENT_CASH_AFTER_FEES"})
        quantity = min(quantity, affordable)
        if quantity <= 0:
            continue
        gross = Decimal(quantity) * prices[ticker]
        fee = gross * FEE_RATE
        cash -= gross + fee
        shares[ticker] = shares.get(ticker, 0) + quantity
        trades.append({"date": day, "profile_id": profile, "source": source,
                       "ticker": ticker, "side": "BUY", "quantity": quantity,
                       "open": _money(prices[ticker]), "gross_krw": _money(gross),
                       "fee_krw": _money(fee)})
    _require(cash >= 0 and all(quantity >= 0 for quantity in shares.values()),
             "negative cash or position")
    for ticker in list(shares):
        if shares[ticker] == 0:
            del shares[ticker]
    return cash, trades, nonfills


def reconstruct(baseline: dict, decisions: list[dict], rows: list[dict],
                sessions: list[str], *, completed_data_asof: str | None = None
                ) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    prices = _price_map(rows)
    weights = _snapshot_weights(baseline)
    by_day = {decision["execution_date"]: decision for decision in decisions}
    accounts = {profile: {"shares": {}, "cash": CAPITAL, "previous_nav": CAPITAL,
                          "peak_nav": CAPITAL, "max_drawdown": Decimal(0)}
                for profile in weights}
    daily, trades, nonfills, missing = [], [], [], []
    for day in sessions:
        if completed_data_asof is not None and day > completed_data_asof:
            missing.append({"date": day, "reason": "awaiting_manual_refresh", "tickers": []})
            break
        required = set()
        for account in accounts.values():
            required.update(account["shares"])
        if day == sessions[0]:
            for target in weights.values():
                required.update(target)
        if day in by_day:
            for profile in weights:
                required.update(_target_weights(by_day[day], profile))
        absent = sorted(ticker for ticker in required if (ticker, day) not in prices)
        if absent:
            reason = ("required_price_missing_within_completed_asof"
                      if completed_data_asof is not None else "required_price_missing")
            missing.append({"date": day, "reason": reason, "tickers": absent})
            break
        current = {ticker: prices[ticker, day] for ticker in required}
        open_prices = {ticker: _dec(row["open"]) for ticker, row in current.items()}
        close_prices = {ticker: _dec(row["close"]) for ticker, row in current.items()}
        for profile, account in accounts.items():
            source = None
            target = None
            eligibility = None
            if day == sessions[0]:
                source = "RESEARCH_0904_SNAPSHOT_IMPORT"
                target = weights[profile]
            elif day in by_day:
                decision = by_day[day]
                _require(datetime.fromisoformat(decision["publication_at"]) <
                         datetime.fromisoformat(day + "T09:00:00+09:00"),
                         "decision published after assumed open")
                source = decision["decision_id"]
                target = _target_weights(decision, profile)
                eligibility = {row["ticker"]: row["fresh_entry_eligible"]
                               for row in decision["profiles"][profile]["target_positions"]}
            day_trades = []
            day_nonfills = []
            if target is not None:
                account["cash"], day_trades, day_nonfills = _rebalance(
                    account["shares"], account["cash"], target, open_prices,
                    profile=profile, day=day, source=source, eligible=eligibility)
                trades.extend(day_trades)
                nonfills.extend(day_nonfills)
            nav = account["cash"] + sum(Decimal(quantity) * close_prices[ticker]
                                        for ticker, quantity in account["shares"].items())
            previous = account["previous_nav"]
            account["peak_nav"] = max(account["peak_nav"], nav)
            drawdown = (nav / account["peak_nav"] - 1) * 100
            account["max_drawdown"] = min(account["max_drawdown"], drawdown)
            daily.append({"date": day, "profile_id": profile,
                          "classification": CLASSIFICATION,
                          "valuation_status": "PROVISIONAL_SOURCE_REVIEW_PENDING",
                          "candidate_nav_krw": _money(nav),
                          "cash_krw": _money(account["cash"]),
                          "candidate_return_percent": _money((nav / previous - 1) * 100),
                          "candidate_cumulative_return_percent": _money((nav / CAPITAL - 1) * 100),
                          "candidate_drawdown_percent": _money(drawdown),
                          "candidate_max_drawdown_percent": _money(account["max_drawdown"]),
                          "verified_live_nav_krw": None,
                          "verified_live_return_percent": None,
                          "fees_krw": _money(sum((_dec(t["fee_krw"]) for t in day_trades), Decimal(0))),
                          "positions": [{"ticker": ticker, "quantity": quantity,
                                         "close": _money(close_prices[ticker]),
                                         "market_value_krw": _money(Decimal(quantity) * close_prices[ticker])}
                                        for ticker, quantity in sorted(account["shares"].items())],
                          "cash_rights_policy": "PRICE_ONLY_CASH_DISTRIBUTIONS_EXCLUDED",
                          "decision_ref": source,
                          "price_row_hashes": {ticker: canonical_sha256(row)
                                               for ticker, row in sorted(current.items())}})
            account["previous_nav"] = nav
    return daily, trades, nonfills, missing


def _verify_extension(prior: dict, daily: list[dict], trades: list[dict],
                      nonfills: list[dict], missing: list[dict]) -> None:
    last = prior["valuation_end_date"]
    _require([d for d in daily if d["date"] <= last] == prior["daily"] and
             [t for t in trades if t["date"] <= last] == prior["trades"] and
             [n for n in nonfills if n["date"] <= last] == prior["nonfills"],
             "prior trades, holdings or valuations changed; correction run required")
    _require(not any(m["reason"] == "required_price_missing_within_completed_asof"
                     for m in missing), "required price missing inside completed data_asof")
    _require(any(d["date"] > last for d in daily), "no evaluated new day")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "inventory", "price-db", "policy", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--operating-root", type=Path,
                        help="Explicit original-observation audit/migration input")
    source.add_argument("--source-context", type=Path,
                        help="Pinned independent inputs for paper valuation")
    parser.add_argument("--source-context-sha256")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--resume-manifest-sha256")
    parser.add_argument("--completion-receipt", type=Path)
    parser.add_argument("--completion-receipt-sha256")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    _require(out.is_relative_to(ROOT / "reports"), "output must stay under quant2/reports")
    _require(not out.exists() or not any(out.iterdir()), "output directory already has files")
    baseline = _read_json(args.baseline)
    inventory = _read_json(args.inventory)
    _require(file_sha256(args.baseline) == inventory["baseline_sha256"], "baseline SHA changed")
    _require(inventory["classification"] == "RECONSTRUCTION_INPUT_INVENTORY_NOT_LIVE",
             "wrong inventory")
    policy = _read_json(args.policy)
    _require(policy["live_evaluation"]["start_date_inclusive"] == "2026-09-07" and
             policy["backtest"]["end_date_inclusive"] == "2026-09-04", "policy boundary mismatch")
    if args.source_context:
        _require(args.source_context_sha256, "source context requires SHA pin")
        audit, owner_results = load_context(args.source_context, args.source_context_sha256,
                                           as_of=args.as_of)
    else:
        _require(not args.source_context_sha256, "context SHA requires --source-context")
        audit = audit_forward_sources(args.operating_root, as_of=args.as_of)
        journal, journal_rows, journal_hash = _journal(
            args.operating_root / "forward_receipts.sqlite3")
        journal.close()
        _require(journal_hash == audit["journal_content_sha256"], "journal changed after audit")
        owner_results = _owner_coverage(journal_rows, audit)
    decisions = audit["verified_decisions"]
    saved_decisions = [(i["key"], i["state_sha256"], i["execution_date"])
                       for i in inventory["decisions"]]
    current_decisions = [(d["decision_id"], d["state_sha256"], d["execution_date"])
                         for d in decisions]
    _require(current_decisions[:len(saved_decisions)] == saved_decisions and
             (args.resume_from is not None or len(current_decisions) == len(saved_decisions)),
             "decision pins changed")
    sessions = [day for day in audit["calendar"]["sessions"] if day >= "2026-09-07"]
    prior = None
    if args.resume_from is not None:
        _require(args.resume_manifest_sha256 and args.completion_receipt and
                 args.completion_receipt_sha256, "resume requires prior and completion SHA pins")
        prior, previous_rows, previous_decisions = _prior_bundle(
            args.resume_from, args.resume_manifest_sha256)
        _require(prior["source_hashes"]["baseline_sha256"] == file_sha256(args.baseline) and
                 prior["source_hashes"]["policy_sha256"] == file_sha256(args.policy) and
                 prior["source_hashes"]["inventory_sha256"] == file_sha256(args.inventory),
                 "prior baseline, policy or inventory changed")
        _require(decisions[:len(previous_decisions)] == previous_decisions and
                 all(d["execution_date"] > prior["valuation_end_date"]
                     for d in decisions[len(previous_decisions):]),
                 "prior decision changed or backdated decision added")
        completed_data_asof = _completed_asof(args.completion_receipt,
                                              args.completion_receipt_sha256)
        receipt_classification = _read_json(args.completion_receipt).get("classification")
        _require(completed_data_asof > prior["valuation_end_date"] and
                 completed_data_asof <= datetime.fromisoformat(args.as_of).date().isoformat(),
                 "no new completed data_asof after prior run")
        dates = [day for day in sessions if prior["valuation_end_date"] < day <= completed_data_asof]
        _require(dates, "no new trading session in completed data_asof")
        tickers = sorted(set(inventory["tickers"]) |
                         {p["ticker"] for d in decisions for profile in d["profiles"].values()
                          for p in profile["target_positions"]})
    else:
        _require(not any((args.resume_manifest_sha256, args.completion_receipt,
                          args.completion_receipt_sha256)), "completion pins require --resume-from")
        completed_data_asof = max(inventory["available_price_dates"])
        dates = inventory["available_price_dates"]
        tickers = inventory["tickers"]
        receipt_classification = None
    price_snapshot_read_at = datetime.now(timezone.utc).isoformat()
    if prior is not None:
        old_tickers = sorted({row["ticker"] for row in previous_rows})
        old_dates = sorted({row["date"] for row in previous_rows})
        current_old_rows = _price_rows(args.price_db, old_tickers, old_dates)
        _unchanged_economic_prices(previous_rows, current_old_rows)
    new_rows = _price_rows(args.price_db, tickers, dates)
    before_rows = previous_rows + new_rows if prior is not None else new_rows
    price_map = _price_map(before_rows)
    if prior is None:
        _require(len(before_rows) == inventory["price_rows"] and
                 not inventory["union_grid_missing"] and all((ticker, day) in price_map
                 for ticker in tickers for day in dates), "price grid changed")
    daily, trades, nonfills, missing = reconstruct(
        baseline, decisions, before_rows, sessions, completed_data_asof=completed_data_asof)
    if prior is not None:
        _verify_extension(prior, daily, trades, nonfills, missing)
    after_rows = _price_rows(args.price_db, tickers, dates)
    _require(new_rows == after_rows, "price source changed during reconstruction")
    if prior is not None:
        _unchanged_economic_prices(previous_rows,
                                   _price_rows(args.price_db, old_tickers, old_dates))
    if args.source_context:
        _require(file_sha256(args.source_context) == args.source_context_sha256.lower(),
                 "source context changed during reconstruction")
    else:
        after_audit = audit_forward_sources(args.operating_root, as_of=args.as_of)
        _require((audit["ledger_content_sha256"], audit["journal_content_sha256"]) ==
                 (after_audit["ledger_content_sha256"], after_audit["journal_content_sha256"]),
                 "operating source changed during reconstruction")
    generated_at = datetime.now(timezone.utc).isoformat()
    owner_review = []
    for decision in decisions:
        owner = owner_results[decision["state_sha256"]]
        owner_review.append({"decision_id": decision["decision_id"],
                             "status": owner["status"], "scope_start": owner.get("from"),
                             "scope_end_exclusive": owner.get("until"),
                             "requested_tickers_in_scope": len(set(tickers) & owner.get("scope", set())),
                             "requested_tickers_with_warning": sorted(set(tickers) & set(owner.get("warnings", {}))),
                             "coverage_sha256": owner.get("coverage_sha256"),
                             "review_sha256": owner.get("review_sha256"),
                             "reason": owner.get("reason")})
    summaries = {}
    for model in baseline["models"]:
        profile = model["profile_id"]
        latest = next((row for row in reversed(daily) if row["profile_id"] == profile), None)
        summaries[profile] = {"evaluated_days": sum(row["profile_id"] == profile for row in daily),
                              "candidate_final_nav_krw": latest["candidate_nav_krw"] if latest else None,
                              "candidate_cumulative_return_percent": latest["candidate_cumulative_return_percent"] if latest else None,
                              "candidate_max_drawdown_percent": latest["candidate_max_drawdown_percent"] if latest else None,
                              "verified_live_performance": None}
    output_classification = ("SYNTHETIC_TEST_ONLY" if receipt_classification == "SYNTHETIC_TEST_ONLY"
                             else CLASSIFICATION)
    result = {"schema": SCHEMA, "classification": output_classification,
              "generated_at": generated_at, "journal_audit_as_of": audit["as_of"],
              "valuation_requested_as_of": args.as_of,
              "decision_source_kind": ("PINNED_CONTEXT" if args.source_context else
                                       "ORIGINAL_OBSERVATION_AUDIT"),
              "price_snapshot_read_at": price_snapshot_read_at,
              "completed_data_asof": completed_data_asof,
              "completion_receipt_classification": receipt_classification,
              "resume_from_manifest_sha256": args.resume_manifest_sha256 if prior else None,
              "completion_receipt_sha256": (args.completion_receipt_sha256 if prior else None),
              "prior_prefix_verified": prior is not None,
              "model_start_date": "2026-09-07", "valuation_end_date": daily[-1]["date"] if daily else None,
              "starting_capital_krw_per_profile": _money(CAPITAL), "fee_rate": _money(FEE_RATE),
              "trading_assumption": "scheduled open, whole shares, sells before buys, no slippage",
              "source_limitations": ["historical input availability not authenticated",
                                     "price rows are current DB snapshots, not raw provider PIT",
                                     "cash dividends excluded; unit-changing actions not independently certified",
                                     "owner coverage is not a no-event proof for all dates"],
              "source_verification_status": ("SYNTHETIC_TEST_ONLY" if
                                             output_classification == "SYNTHETIC_TEST_ONLY" else
                                             "PROVISIONAL_NOT_VERIFIED_LIVE"),
              "owner_review": owner_review,
              "missing_sessions": missing,
              "profiles": summaries,
              "source_hashes": {"baseline_sha256": file_sha256(args.baseline),
                                "inventory_sha256": file_sha256(args.inventory),
                                "policy_sha256": file_sha256(args.policy),
                                "source_context_sha256": args.source_context_sha256,
                                "ledger_logical_sha256": audit["ledger_content_sha256"],
                                "journal_logical_sha256": audit["journal_content_sha256"],
                                "price_rows_sha256": canonical_sha256(before_rows)},
              "daily": daily, "trades": trades, "nonfills": nonfills}
    out.mkdir(parents=True, exist_ok=True)
    for name, obj in (("price_rows.json", before_rows), ("decisions.json", decisions),
                      ("reconstruction.json", result)):
        path = out / name
        with path.open("x", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            fh.write("\n")
    manifest = {"schema": "q25_retrospective_paper_manifest_v1",
                "classification": output_classification, "generated_at": generated_at,
                "files": {name: file_sha256(out / name) for name in
                          ("price_rows.json", "decisions.json", "reconstruction.json")}}
    with (out / "manifest.json").open("x", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    print(json.dumps({"output": str(out), "days": len(daily) // len(baseline["models"]),
                      "trades": len(trades), "nonfills": len(nonfills), "missing": missing,
                      "manifest_sha256": file_sha256(out / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
