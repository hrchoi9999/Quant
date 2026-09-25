"""Pre-open sealed plan and next-day retrospective paper accounting.

Daily bars are never represented as a same-session quote or broker fill.
The existing forward journal is the outbox; its paper-execution key is shared
with observed-open execution so one scheduled day cannot execute twice.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from base64 import b64decode, b64encode
from decimal import Decimal
from pathlib import Path

from .quant25_forward_connection import ForwardConnection
from .quant25_incremental_selection import aware
from .quant25_observed_paper_execution import delayed_paper_execution_events
from .quant25_paper_live import PROFILE_MODEL_IDS, canonical_sha256

SCHEMA = "Q25_DELAYED_PAPER_PLAN_V1"


def _ledger_fingerprint(ledger):
    with sqlite3.connect(ledger.path) as con:
        rows = con.execute("SELECT event_id,payload_sha256 FROM ledger_events ORDER BY sequence").fetchall()
    return canonical_sha256(rows)


def _books(ledger, as_of):
    return {profile: {key: snapshot[key] for key in ("positions", "cash", "starting_capital")}
            for profile in PROFILE_MODEL_IDS
            for snapshot in [ledger.snapshot(profile, as_of=as_of)]}


def verify_stored_source_binding(daily: dict, *, confirmed_at: str | None = None) -> dict:
    """Read current stored rows once, then preserve exact replayable source bytes."""
    refs = daily.get("stored_sources")
    if not isinstance(refs, dict):
        raise ValueError("stored source paths required")
    for key in ("price_db", "collector_receipt_path", "collector_receipt_sha256",
                "security_review_path", "security_review_sha256"):
        if not isinstance(refs.get(key), str) or not refs[key].strip():
            raise ValueError("stored source reference incomplete")
    collector_raw = Path(refs["collector_receipt_path"]).read_bytes()
    review_raw = Path(refs["security_review_path"]).read_bytes()
    review = json.loads(review_raw)
    source_refs = [{**item, "raw_b64": b64encode(Path(item["path"]).read_bytes()).decode("ascii")}
                   for item in review.get("source_refs", [])]
    columns = "ticker,date,open,high,low,close,volume,source,created_at,updated_at"
    db_path = Path(refs["price_db"])
    rows = []
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")  # All requested securities share one source snapshot.
        for quote in daily["quotes"]:
            row = con.execute(f"SELECT {columns} FROM prices_daily WHERE ticker=? AND date=?",
                              (quote["ticker"], daily["asof_date"])).fetchone()
            if row is None:
                raise ValueError("stored official daily row missing")
            rows.append(dict(zip(columns.split(","), row)))
    bundle = {"status": "STORED_DB_RECEIPT_REVIEW_MATCHED_NOT_PROVIDER_PIT",
              "price_rows": rows, "collector_raw_b64": b64encode(collector_raw).decode("ascii"),
              "security_review_raw_b64": b64encode(review_raw).decode("ascii"),
              "source_refs": source_refs}
    return replay_stored_source_binding(daily, bundle, confirmed_at=confirmed_at)


def replay_stored_source_binding(daily: dict, bundle: dict, *,
                                 confirmed_at: str | None = None) -> dict:
    """Pure replay from journal bytes; does not touch mutable current price.db."""
    refs = daily["stored_sources"]
    collector_raw = b64decode(bundle["collector_raw_b64"], validate=True)
    review_raw = b64decode(bundle["security_review_raw_b64"], validate=True)
    if (hashlib.sha256(collector_raw).hexdigest() != refs["collector_receipt_sha256"]
            or hashlib.sha256(review_raw).hexdigest() != refs["security_review_sha256"]):
        raise ValueError("stored source reference hash mismatch")
    collector = json.loads(collector_raw)
    review = json.loads(review_raw)
    day = daily["asof_date"]
    if (collector.get("status") != "completed" or collector.get("source") != "krx_openapi"
            or day.replace("-", "") not in collector.get("requested_dates", [])
            or review.get("schema") != "Q25_DELAYED_SECURITY_REVIEW_V1"
            or review.get("asof_date") != day):
        raise ValueError("stored collector/review scope does not match daily date")
    if (len(bundle["source_refs"]) != len(review.get("source_refs", [])) or
            not bundle["source_refs"]):
        raise ValueError("pinned security source bytes required")
    for original, saved in zip(review["source_refs"], bundle["source_refs"]):
        if original != {k: saved[k] for k in ("path", "sha256")} or hashlib.sha256(
                b64decode(saved["raw_b64"], validate=True)).hexdigest() != saved["sha256"]:
            raise ValueError("security review source bytes changed")
    source_hashes = {item["sha256"] for item in bundle["source_refs"]}
    cycle_completed = aware(daily["collection_receipt"]["completed_at"])
    if aware(collector["completed_at"]) > cycle_completed:
        raise ValueError("collector completed after pinned collection receipt")
    if confirmed_at is not None and aware(review["reviewed_at"]) > aware(confirmed_at):
        raise ValueError("security review completed after actual confirmation")
    if len(bundle["price_rows"]) != len(daily["quotes"]):
        raise ValueError("daily row count differs from preserved source rows")
    seen = set()
    for quote, original in zip(daily["quotes"], bundle["price_rows"]):
        ticker = quote["ticker"]
        if ticker in seen or original["ticker"] != ticker or original["date"] != day:
            raise ValueError("stored price row ticker/date mismatch or duplicate")
        seen.add(ticker)
        if original["source"] != "krx_openapi":
            raise ValueError("stored price row source differs from collector")
        for field in ("open", "high", "low", "close", "volume"):
            if (original[field] is None or quote.get(field) is None or
                    Decimal(str(original[field])) != Decimal(str(quote[field]))):
                raise ValueError("daily envelope differs from stored price row")
        if canonical_sha256(original) != quote.get("daily_source_sha256"):
            raise ValueError("daily row source hash differs")
        if any(aware(original[field]) > cycle_completed for field in ("created_at", "updated_at")
               if original[field]):
            raise ValueError("stored row changed after collection receipt")
        reviewed = review.get("securities", {}).get(ticker)
        fields = ("trade_permitted_for_paper", "units_valid", "valuation_valid",
                  "event_coverage_confirmed", "unresolved_event", "rights_review")
        if (not isinstance(reviewed, dict) or
                any(reviewed.get(field) != quote.get(field) for field in fields) or
                quote.get("review_source_sha256") != refs["security_review_sha256"] or
                quote.get("rights_review", {}).get("source_sha256") not in source_hashes):
            raise ValueError("security/rights review envelope differs from pinned original")
    if bundle.get("status") != "STORED_DB_RECEIPT_REVIEW_MATCHED_NOT_PROVIDER_PIT":
        raise ValueError("stored source classification mismatch")
    return bundle


def prepare_daily_evidence(plan: dict, saved_decision: dict, *, price_db: Path,
                           collection_receipt_path: Path, collector_receipt_path: Path,
                           security_review_path: Path) -> dict:
    """Build a dated envelope from the existing read-only DB and pinned reviews."""
    if (plan.get("schema") != SCHEMA or
            canonical_sha256(saved_decision) != plan.get("decision_sha256") or
            saved_decision["selection"]["execution_date"] != plan.get("execution_date")):
        raise ValueError("producer requires the exact pre-open plan and decision")
    day = plan["execution_date"]
    receipt_raw = collection_receipt_path.read_bytes()
    receipt = json.loads(receipt_raw)
    if receipt.get("data_asof") != day:
        raise ValueError("producer receipt date differs from plan")
    review_raw = security_review_path.read_bytes()
    review = json.loads(review_raw)
    if review.get("schema") != "Q25_DELAYED_SECURITY_REVIEW_V1" or review.get("asof_date") != day:
        raise ValueError("producer review date/schema differs from plan")
    needed = {item["ticker"] for profile in saved_decision["selection"]["profiles"].values()
              for item in profile["target_positions"]}
    needed |= {item["ticker"] for book in plan["book_inputs"].values()
               for item in book["positions"]}
    columns = "ticker,date,open,high,low,close,volume,source,created_at,updated_at"
    quotes, pending = [], []
    with sqlite3.connect(price_db.as_uri() + "?mode=ro", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        for ticker in sorted(needed):
            row = con.execute(f"SELECT {columns} FROM prices_daily WHERE ticker=? AND date=?",
                              (ticker, day)).fetchone()
            reviewed = review.get("securities", {}).get(ticker)
            if row is None or not isinstance(reviewed, dict):
                pending.append(ticker)
                continue
            original = dict(zip(columns.split(","), row))
            quotes.append({"ticker": ticker, "source_kind": "OFFICIAL_DAILY_OHLCV",
                           **{k: original[k] for k in ("open", "high", "low", "close", "volume")},
                           "daily_source_sha256": canonical_sha256(original),
                           "review_source_sha256": hashlib.sha256(review_raw).hexdigest(),
                           **{k: reviewed.get(k) for k in (
                               "trade_permitted_for_paper", "units_valid", "valuation_valid",
                               "event_coverage_confirmed", "unresolved_event", "rights_review")}})
    daily = {"schema": "Q25_DELAYED_DAILY_EVIDENCE_V1", "asof_date": day,
             "classification": "STORED_DAILY_OPEN_ASSUMPTION_NOT_SAME_DAY_PIT",
             "collection_receipt": {
                 **{k: receipt[k] for k in ("cycle_id", "user_command_ref", "data_asof", "completed_at")},
                 "path": str(collection_receipt_path.resolve()),
                 "sha256": hashlib.sha256(receipt_raw).hexdigest()},
             "stored_sources": {
                 "price_db": str(price_db.resolve()),
                 "collector_receipt_path": str(collector_receipt_path.resolve()),
                 "collector_receipt_sha256": hashlib.sha256(collector_receipt_path.read_bytes()).hexdigest(),
                 "security_review_path": str(security_review_path.resolve()),
                 "security_review_sha256": hashlib.sha256(review_raw).hexdigest()},
             "quotes": quotes, "pending_tickers": pending}
    verify_stored_source_binding(daily)
    return daily


def replay_delayed_execution(plan: dict, saved_decision: dict, daily: dict, *,
                             confirmed_at: str, daily_sha256: str,
                             receipt_raw: bytes,
                             source_binding_verified: bool = False,
                             stored_source_binding: dict | None = None) -> dict:
    """Pure journal replay of the sealed plan and collection receipt bytes."""
    if plan.get("schema") != SCHEMA or plan.get("classification") != "DELAYED_PAPER_PREOPEN_PLAN_NOT_EXECUTION":
        raise ValueError("sealed delayed plan schema/classification required")
    selection = saved_decision["selection"]
    day = plan["execution_date"]
    if (selection["execution_date"] != day or
            canonical_sha256(saved_decision) != plan["decision_sha256"] or
            selection["state_sha256"] != plan["state_sha256"] or
            canonical_sha256(plan["book_inputs"]) != plan["book_inputs_sha256"] or
            not aware(saved_decision["publication_at"]) <= aware(plan["sealed_at"])
            < aware(day + "T09:00:00+09:00")):
        raise ValueError("delayed plan decision/book binding mismatch")
    if daily.get("asof_date") != day:
        raise ValueError("daily source date differs from sealed plan")
    receipt = daily.get("collection_receipt")
    if not isinstance(receipt, dict) or receipt.get("data_asof") != day:
        raise ValueError("exact-day collection receipt required")
    if hashlib.sha256(receipt_raw).hexdigest() != receipt.get("sha256"):
        raise ValueError("collection receipt raw hash mismatch")
    original_receipt = json.loads(receipt_raw)
    for field in ("cycle_id", "user_command_ref", "data_asof", "completed_at"):
        if original_receipt.get(field) != receipt.get(field):
            raise ValueError("collection receipt envelope differs from original bytes")
    close = aware(day + "T15:30:00+09:00")
    if not close < aware(receipt["completed_at"]) <= aware(confirmed_at):
        raise ValueError("collection receipt timing invalid")
    if stored_source_binding is not None:
        replay_stored_source_binding(daily, stored_source_binding, confirmed_at=confirmed_at)
    if source_binding_verified is not (stored_source_binding is not None):
        raise ValueError("stored source binding flag does not match preserved evidence")
    plan_sha = canonical_sha256(plan)
    result = delayed_paper_execution_events(
        selection, plan["book_inputs"], daily, confirmed_at=confirmed_at,
        daily_sha256=daily_sha256, plan_sha256=plan_sha,
        fee_rate=plan["fee_rate"], source_binding_verified=source_binding_verified)
    result.update(mode="DELAYED_PAPER", plan_id=plan["plan_id"],
                  plan_sha256=plan_sha, decision_sha256=plan["decision_sha256"],
                  collection_receipt=receipt,
                  collection_receipt_raw_b64=b64encode(receipt_raw).decode("ascii"),
                  daily_sha256=daily_sha256,
                  confirmed_at=confirmed_at, actual_execution=False,
                  broker_execution=False, contemporaneous_open_observation=False,
                  operational_source_binding_verified=source_binding_verified,
                  stored_source_binding=stored_source_binding,
                  provider_raw_pit_verified=False,
                  counts_as_live_sample=False)
    return result


class DelayedPaperExecution:
    def __init__(self, private_dir: Path, *, freeze_dir: Path, clock=None,
                 research_only: bool = False):
        self.connection = ForwardConnection(private_dir, freeze_dir=freeze_dir, clock=clock)
        self.research_only = research_only

    def seal(self, day: str):
        """Irrevocably bind an actual future decision and pre-open book."""
        connection = self.connection
        connection._freeze()
        ledger = connection.recover()
        opened = aware(day + "T09:00:00+09:00")
        with connection._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            key = "delayed-plan:" + day
            prior = con.execute("SELECT body FROM journal WHERE key=?", (key,)).fetchone()
            if prior:
                return json.loads(prior[0])
            sealed = aware(connection.clock())
            if sealed >= opened or sealed < ledger.config.created_at:
                raise ValueError("delayed plan must be sealed after ledger start and before future open")
            if con.execute("SELECT 1 FROM journal WHERE key=?", ("paper-execution:" + day,)).fetchone():
                raise ValueError("execution already exists for scheduled day")
            pending = con.execute(
                "SELECT key FROM journal WHERE kind='delayed_plan' AND key NOT IN "
                "(SELECT 'delayed-plan:' || substr(key,17) FROM journal WHERE kind='paper_execution')"
            ).fetchall()
            if pending:
                raise ValueError("earlier delayed plan must be confirmed or explicitly resolved")
            rows = con.execute("SELECT body FROM journal WHERE kind='decision' ORDER BY sequence DESC").fetchall()
            matches = [json.loads(row[0]) for row in rows
                       if json.loads(row[0])["selection"]["execution_date"] == day]
            if len(matches) != 1:
                raise ValueError("exactly one future captured decision required")
            saved = matches[0]
            selection = saved["selection"]
            if (selection["historical"] is not False or
                    not aware(saved["publication_at"]) <= sealed < opened or
                    aware(selection["decision_cutoff"]) >= opened):
                raise ValueError("decision/target was not fixed before open")
            books = _books(ledger, sealed.isoformat())
            plan = {
                "schema": SCHEMA, "classification": "DELAYED_PAPER_PREOPEN_PLAN_NOT_EXECUTION",
                "plan_id": key, "execution_date": day, "sealed_at": sealed.isoformat(),
                "decision_id": "decision:" + selection["decision_date"],
                "decision_sha256": canonical_sha256(saved),
                "state_sha256": selection["state_sha256"],
                "publication_at": saved["publication_at"],
                "fee_rate": str(ledger.config.fee_rate),
                "ledger_prestate_sha256": _ledger_fingerprint(ledger),
                "book_inputs": books, "book_inputs_sha256": canonical_sha256(books),
                "execution_assumption": "RETROSPECTIVE_OFFICIAL_DAILY_OPEN_NOT_CONTEMPORANEOUS",
                "actual_execution": False, "broker_execution": False,
            }
            connection._put(con, key, "delayed_plan", plan)
        return plan

    def confirm(self, day: str, source: Path, *, expected_sha256: str):
        """Use a later approved-cycle daily receipt; never forge a same-day arrival."""
        connection = self.connection
        connection._freeze()
        ledger = connection.recover()
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("daily source hash mismatch")
        daily = json.loads(raw)
        with connection._connect() as con:
            prior = con.execute("SELECT body,raw FROM journal WHERE key=?",
                                ("paper-execution:" + day,)).fetchone()
            if prior:
                if prior["raw"] != raw or json.loads(prior["body"]).get("mode") != "DELAYED_PAPER":
                    raise ValueError("execution already sealed with different evidence or mode")
                return json.loads(prior["body"])
        stored_binding = (verify_stored_source_binding(daily)
                          if daily.get("stored_sources") else None)
        if not self.research_only and stored_binding is None:
            raise ValueError("stored daily row/review source binding required for operating confirm")
        with connection._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            key = "paper-execution:" + day
            prior = con.execute("SELECT body,raw FROM journal WHERE key=?", (key,)).fetchone()
            if prior:
                if prior["raw"] != raw or json.loads(prior["body"]).get("mode") != "DELAYED_PAPER":
                    raise ValueError("execution already sealed with different evidence or mode")
                return json.loads(prior["body"])
            row = con.execute("SELECT body FROM journal WHERE key=?", ("delayed-plan:" + day,)).fetchone()
            if not row:
                raise ValueError("pre-open sealed plan required")
            plan = json.loads(row[0])
            confirmed = aware(connection.clock())
            if stored_binding is not None:
                replay_stored_source_binding(daily, stored_binding, confirmed_at=confirmed.isoformat())
            close = aware(day + "T15:30:00+09:00")
            if confirmed <= close or confirmed.tz_convert("Asia/Seoul").date() <= close.date():
                raise ValueError("next-day actual confirmation required")
            receipt = daily.get("collection_receipt")
            if not isinstance(receipt, dict) or receipt.get("data_asof") != day:
                raise ValueError("exact-day approved collection receipt required")
            for field in ("cycle_id", "user_command_ref", "path", "sha256", "completed_at"):
                if not isinstance(receipt.get(field), str) or not receipt[field].strip():
                    raise ValueError("collection receipt provenance incomplete")
            receipt_raw = Path(receipt["path"]).read_bytes()
            if hashlib.sha256(receipt_raw).hexdigest() != receipt["sha256"]:
                raise ValueError("collection receipt hash mismatch")
            if not close < aware(receipt["completed_at"]) <= confirmed:
                raise ValueError("collection completion must follow execution close and precede confirmation")
            if _ledger_fingerprint(ledger) != plan["ledger_prestate_sha256"]:
                raise ValueError("ledger changed after pre-open plan")
            rows = con.execute("SELECT body FROM journal WHERE kind='decision' ORDER BY sequence DESC").fetchall()
            matches = [json.loads(row[0]) for row in rows
                       if json.loads(row[0])["selection"]["execution_date"] == day]
            if len(matches) != 1 or canonical_sha256(matches[0]) != plan["decision_sha256"]:
                raise ValueError("sealed decision changed")
            books = _books(ledger, plan["sealed_at"])
            if canonical_sha256(books) != plan["book_inputs_sha256"]:
                raise ValueError("sealed book changed")
            result = replay_delayed_execution(
                plan, matches[0], daily, confirmed_at=confirmed.isoformat(),
                daily_sha256=expected_sha256, receipt_raw=receipt_raw,
                source_binding_verified=stored_binding is not None,
                stored_source_binding=stored_binding)
            connection._put(con, key, "paper_execution", result, raw)
        connection.recover()
        return result
