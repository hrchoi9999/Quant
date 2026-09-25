"""Private input capture and crash-recoverable connection to the frozen selector.

No scheduler, broker, operating database writes or public publisher is invoked.
Receipt timestamps come from this process, never from historical file mtimes.
"""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.evaluation.normalized_nav import ExecutionTarget

from .quant25_incremental_selection import SOURCES, aware, select_decision
from .quant25_monthly_start_contract import resolved_receipt
from .quant25_observed_paper_execution import paper_execution_events
from .quant25_paper_ledger import Quant25PaperLedger
from .quant25_paper_live import (
    FREEZE_ID,
    PROFILE_MODEL_IDS,
    build_inactive_dry_run_bundle,
    canonical_sha256,
    file_sha256,
    validate_freeze_bundle,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def evaluation_period_status(as_of, *, reconstructed_days=()):
    """Report approved windows, never infer returns from configuration or cash.

    This connection has no accepted performance-evidence reader yet. Every live
    calendar date remains explicitly unverified; snapshots are not NAV evidence.
    """
    policy_path = Path(__file__).resolve().parents[3] / "config/quant25_evaluation_periods.json"
    raw = policy_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != "b6ad440b049ec753dfffc9960136debeb8e2a728d3d41d5020a8a0f51485e366":
        raise ValueError("evaluation-period policy differs from approved contract")
    policy = json.loads(raw)
    day = aware(as_of).tz_convert("Asia/Seoul").strftime("%Y-%m-%d")
    end = policy["backtest"]["end_date_inclusive"]
    start = policy["live_evaluation"]["start_date_inclusive"]
    period = ("backtest" if day <= end else
              "between_evaluation_windows" if day < start else "live_evaluation")
    evidence_status = {"backtest": "backtest_not_recomputed",
                       "between_evaluation_windows": "outside_evaluation_windows",
                       "live_evaluation": "live_window_unverified"}[period]
    reconstructed = set(reconstructed_days)
    coverage = [{"date": d.strftime("%Y-%m-%d"),
                 "status": ("retrospective_reconstruction_not_live"
                            if d.strftime("%Y-%m-%d") in reconstructed else "live_window_unverified"),
                 "return": None, "verified_prior_close_nav": False,
                 "counts_as_live_sample": False}
                for d in pd.date_range(start, day, freq="D")]
    return {
        "policy_path": str(policy_path), "policy_sha256": digest,
        "backtest_end_inclusive": end, "live_window_start_inclusive": start,
        "report_asof": day,
        "period": period,
        "coverage_basis": "calendar_dates_not_confirmed_trading_sessions",
        "backtest_extension_executed": False, "performance_evidence_reader_connected": False,
        "profiles": {p: {"first_verified_performance_date": None,
                          "verified_live_samples": 0, "return": None,
                          "status": evidence_status,
                          "missing_evidence": policy["live_evaluation"]["required_evidence"]
                          + ["verified_prior_close_nav"], "coverage": coverage}
                     for p in policy["profiles"]},
        "backdated_decisions_created": False, "public_eligible": False,
    }


class ForwardConnection:
    """Append-only receipt/decision outbox; existing ledger handles accounting."""

    def __init__(self, root: Path, *, freeze_dir: Path, clock=None):
        self.root = root.resolve()
        quant_root = Path(__file__).resolve().parents[3]
        if not self.root.is_relative_to(quant_root / "reports"):
            raise ValueError("private quant2/reports directory required")
        self.freeze_dir = freeze_dir.resolve()
        self.clock = clock or _now
        self.path = self.root / "forward_receipts.sqlite3"

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA synchronous=FULL")
        return con

    @staticmethod
    def _put(con, key, kind, body, raw=None):
        encoded = _encode(body)
        prior = con.execute("SELECT * FROM journal WHERE key=?", (key,)).fetchone()
        if prior:
            if prior["body"] != encoded or prior["kind"] != kind or prior["raw"] != raw:
                raise ValueError("immutable journal key conflict")
            return
        con.execute("INSERT INTO journal(key,kind,body,raw) VALUES(?,?,?,?)", (key, kind, encoded, raw))

    def initialize(self, *, starting_capital, fee_rate, approval_ref):
        if not str(approval_ref).strip():
            raise ValueError("private observation approval reference required")
        freeze = self._freeze()
        self.root.mkdir(parents=True, exist_ok=True)
        ledger_path = self.root / "paper_accounting.sqlite3"
        if ledger_path.exists():
            ledger = Quant25PaperLedger.open(ledger_path)
            if (ledger.config.starting_capital != Decimal(str(starting_capital))
                    or ledger.config.fee_rate != Decimal(str(fee_rate))):
                raise ValueError("existing capital/cost contract differs")
        else:
            ledger = Quant25PaperLedger.create(
                ledger_path, freeze_id=FREEZE_ID, starting_capital=starting_capital,
                currency="KRW", fee_rate=fee_rate, created_at=self.clock())
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS journal (
                    sequence INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL, body TEXT NOT NULL, raw BLOB);
                CREATE TRIGGER IF NOT EXISTS journal_no_update BEFORE UPDATE ON journal
                    BEGIN SELECT RAISE(ABORT, 'append-only'); END;
                CREATE TRIGGER IF NOT EXISTS journal_no_delete BEFORE DELETE ON journal
                    BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            """)
            self._put(con, "config", "config", {
                "freeze_id": FREEZE_ID, "freeze_manifest_sha256": freeze["freeze_manifest_sha256"],
                "execution_contract_sha256": freeze["execution_contract_sha256"],
                "capital_per_profile": str(ledger.config.starting_capital), "fee_rate": str(fee_rate),
                "approval_ref": approval_ref, "observation_started_at": ledger.config.created_at.isoformat(),
                "classification": "PRIVATE_OBSERVATION_NOT_INVESTED", "public_eligible": False,
                "scheduler_registered": False, "actual_fills_created": False,
            })
        return self.status()

    def _freeze(self):
        freeze = validate_freeze_bundle(self.freeze_dir)
        if self.path.is_file():
            with self._connect() as con:
                exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='journal'").fetchone()
                config = con.execute("SELECT body FROM journal WHERE key='config'").fetchone() if exists else None
                if config:
                    pinned = json.loads(config[0])
                    if any(pinned[key] != freeze[key] for key in ("freeze_manifest_sha256", "execution_contract_sha256")):
                        raise ValueError("session freeze contract changed")
        for source, digest in freeze["manifest"]["source_hashes"].items():
            if source.endswith(".py") and file_sha256(Path(source)) != digest:
                raise ValueError(f"frozen engine source changed: {source}")
        return freeze

    def capture(self, name, path: Path, *, expected_sha256):
        if name not in SOURCES:
            raise ValueError("unknown frozen input source")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256:
            raise ValueError("source hash mismatch")
        from .quant25_input_timing import reject_preparation
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            value = None
        reject_preparation(value)
        key = f"receipt:{name}:{digest}"
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prior = con.execute("SELECT body FROM journal WHERE key=?", (key,)).fetchone()
            if prior:
                return resolved_receipt(con, json.loads(prior[0]))
            received = aware(self.clock()).isoformat()
            record = {
                "receipt_id": key, "source": name, "sha256": digest,
                "source_path": str(path.resolve()), "arrived_at": received,
                "available_at": received, "availability_basis": "FIRST_OBSERVED_LOCAL_BYTES",
                "provider_available_at": None, "historical_receipt_inferred": False,
            }
            self._put(con, key, "receipt", record, raw)
        return record

    def _load_inputs(self, con, receipts):
        if set(receipts) != SOURCES:
            raise ValueError("all nine receipt IDs required")
        files, evidence = {}, {}
        for name, key in receipts.items():
            row = con.execute("SELECT * FROM journal WHERE key=? AND kind='receipt'", (key,)).fetchone()
            if row is None:
                raise ValueError("unrecorded receipt")
            record = json.loads(row["body"])
            record = resolved_receipt(con, record)
            if record["source"] != name or hashlib.sha256(row["raw"]).hexdigest() != record["sha256"]:
                raise ValueError("receipt source or bytes mismatch")
            files[name], evidence[name] = row["raw"], record
        return files, evidence

    def _last_executed_target(self, con, *, day):
        """Reconcile verified target applications, keeping residual holdings separate."""
        row = con.execute("SELECT key,sequence,body,raw FROM journal WHERE kind='paper_execution' "
                          "ORDER BY sequence DESC LIMIT 1").fetchone()
        if row is None:
            return None, None
        selection, binding = self._verified_execution_target(con, row, day=day)
        if not selection.get("event_materiality"):
            return selection, binding
        profiles = {p: {} for p in PROFILE_MODEL_IDS}
        rows = con.execute("SELECT key,sequence,body,raw FROM journal WHERE kind='paper_execution' "
                           "ORDER BY sequence").fetchall()
        for record in rows:
            target, source = self._verified_execution_target(con, record, day=day)
            execution = json.loads(record["body"])
            audits = {a["profile_id"]: a for a in execution["audit"]}
            for profile, positions in target["profiles"].items():
                wanted = {r["ticker"]: r for r in positions["target_positions"]}
                application = audits[profile].get("target_application")
                deferred = set(application["deferred_tickers"]) if application else set()
                applied = set(application["applied_target_tickers"]) if application else set(wanted)
                profiles[profile] = {t: ref for t, ref in profiles[profile].items() if t in deferred}
                profiles[profile].update({t: {"target": wanted[t], "source": source} for t in applied})
        # This is a transient retention view. Never overwrite or relabel the
        # original decision; each retained ticker still names that exact source.
        original = selection["state_sha256"]
        reconciliation = {"schema": "Q25_VERIFIED_PROFILE_RETENTION_V1",
                          "source_state_sha256": original, "profiles": profiles}
        selection = {**selection, "retention_reconciliation": reconciliation}
        selection.pop("state_sha256")
        selection["state_sha256"] = canonical_sha256(selection)
        return selection, {**binding, "profile_target_sources": profiles,
                           "retention_view_sha256": selection["state_sha256"]}

    def _verified_execution_target(self, con, row, *, day):
        execution = json.loads(row["body"])
        if execution.get("mode") == "DELAYED_PAPER":
            from base64 import b64decode

            from .quant25_delayed_paper_execution import replay_delayed_execution

            plan_row = con.execute("SELECT key,sequence,body FROM journal WHERE key=? AND kind='delayed_plan'",
                                   (execution.get("plan_id"),)).fetchone()
            # The plan stores the decision identity; never infer it from a date.
            if plan_row is None:
                raise ValueError("delayed execution has no sealed plan")
            plan = json.loads(plan_row["body"])
            target = con.execute("SELECT key,sequence,body FROM journal WHERE key=? AND kind='decision'",
                                 (plan["decision_id"],)).fetchone()
            if (target is None or target["sequence"] >= plan_row["sequence"]
                    or plan_row["sequence"] >= row["sequence"] or row["raw"] is None
                    or row["key"] != "paper-execution:" + plan["execution_date"]
                    or hashlib.sha256(row["raw"]).hexdigest() != execution.get("daily_sha256")
                    or canonical_sha256(plan) != execution.get("plan_sha256")
                    or plan["execution_date"] > day):
                raise ValueError("delayed execution plan/source chronology mismatch")
            saved = json.loads(target["body"])
            config = json.loads(con.execute("SELECT body FROM journal WHERE key='config'").fetchone()[0])
            if (plan["fee_rate"] != config["fee_rate"] or
                    canonical_sha256(saved) != plan["decision_sha256"]):
                raise ValueError("delayed execution fee/decision proof mismatch")
            replay = replay_delayed_execution(
                plan, saved, json.loads(row["raw"]), confirmed_at=execution["confirmed_at"],
                daily_sha256=execution["daily_sha256"],
                receipt_raw=b64decode(execution["collection_receipt_raw_b64"], validate=True),
                source_binding_verified=execution["operational_source_binding_verified"],
                stored_source_binding=execution.get("stored_source_binding"))
            if replay != execution:
                raise ValueError("delayed execution journal replay mismatch")
            return saved["selection"], {
                "decision_id": plan["decision_id"], "state_sha256": plan["state_sha256"],
                "execution_date": plan["execution_date"], "publication_at": plan["publication_at"],
                "verified_at": execution["confirmed_at"], "mode": "DELAYED_PAPER",
                "plan_sha256": execution["plan_sha256"], "execution_journal_key": row["key"],
            }
        binding = execution.get("decision_binding", {})
        target = con.execute("SELECT key,sequence,body FROM journal WHERE key=? AND kind='decision'",
                             (binding.get("decision_id"),)).fetchone()
        if target is None or target["sequence"] >= row["sequence"]:
            raise ValueError("last execution has no verified target binding")
        saved = json.loads(target["body"])
        selection = saved["selection"]
        expected = {
            "decision_id": "decision:" + selection["decision_date"],
            "state_sha256": selection["state_sha256"], "execution_date": selection["execution_date"],
            "publication_at": saved["publication_at"],
            "quote_sha256": hashlib.sha256(row["raw"]).hexdigest() if row["raw"] is not None else None,
            "verified_at": binding.get("verified_at"),
        }
        if (not saved.get("input_timing") or binding != expected or expected["quote_sha256"] is None
                or target["key"] != expected["decision_id"]
                or row["key"] != "paper-execution:" + expected["execution_date"]
                or canonical_sha256({k: v for k, v in selection.items() if k != "state_sha256"}) != selection["state_sha256"]
                or selection["decision_date"] >= day or selection["execution_date"] > day
                or not aware(expected["publication_at"]) < aware(expected["execution_date"] + "T09:00:00+09:00")
                <= aware(binding.get("verified_at"))
                or len(execution.get("audit", [])) != len(PROFILE_MODEL_IDS)
                or {a.get("profile_id") for a in execution.get("audit", [])} != set(PROFILE_MODEL_IDS)
                or any(e["payload"].get("execution_evidence", {}).get("target_sha256") != selection["state_sha256"]
                       for e in execution.get("events", []) if e["event_type"] == "paper_fill")):
            raise ValueError("last execution target provenance mismatch")
        if selection.get("event_materiality"):
            books = execution.get("book_inputs")
            if (execution.get("profile_execution_schema") != "Q25_PARTIAL_SECURITY_EXECUTION_V1"
                    or not isinstance(books, dict) or canonical_sha256(books) != execution.get("book_inputs_sha256")):
                raise ValueError("partial security execution input proof missing")
            config = json.loads(con.execute("SELECT body FROM journal WHERE key='config'").fetchone()[0])
            replay = paper_execution_events(selection, books, json.loads(row["raw"]),
                                           received_at=binding["verified_at"], quote_sha256=expected["quote_sha256"],
                                           fee_rate=config["fee_rate"])
            if any(replay[k] != execution.get(k) for k in ("events", "audit", "event_materiality")):
                raise ValueError("partial security target application proof mismatch")
        return selection, {**binding, "execution_journal_key": row["key"]}

    def decide(self, *, day, next_rebalance, receipts, manual_timing=None, review_provider=None):
        from .quant25_input_timing import reject_preparation
        reject_preparation(receipts)
        reject_preparation(manual_timing)
        from .quant25_input_timing import (
            collection_context,
            opted_in,
            validity,
            verify_capture_binding,
            verify_coverage,
        )
        use_manual = opted_in(manual_timing)
        if use_manual:
            manual_timing = json.loads(_encode(manual_timing))
            collection_context(manual_timing, signal_day=day, checked_at=self.clock(), root=self.root)
        self._freeze()
        ledger = self.recover()
        request = {"day": day, "next_rebalance": next_rebalance, "receipts": receipts}
        if use_manual:
            request["manual_timing"] = manual_timing
        key = f"decision:{day}"
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prior = con.execute("SELECT body FROM journal WHERE key=?", (key,)).fetchone()
            if prior:
                saved = json.loads(prior[0])
                if saved["request"] != request:
                    raise ValueError("decision already sealed with different inputs")
                return saved
            files, evidence = self._load_inputs(con, receipts)
            def load(name):
                return json.loads(files[name])

            def csv(name):
                return pd.read_csv(io.BytesIO(files[name]), dtype={"ticker": str})
            features, prices = csv("features"), csv("prices")
            if set(features["date"].astype(str)) != {day} or prices["date"].max() != day:
                raise ValueError("same-decision-day features and prices required")
            etf = load("etf_intent")
            monthly_target = dict(etf)
            etf = ExecutionTarget(**{
                k: pd.Timestamp(evidence["etf_intent"].get("provider_available_at") or etf[k])
                if k == "published_at" else pd.Timestamp(etf[k]) if k in ("decision_date", "execution_date") else etf[k]
                for k in ("model_code", "decision_date", "published_at", "execution_date", "run_id", "weights", "evidence_state")
            })
            latest = con.execute("SELECT body FROM journal WHERE kind='decision' ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = json.loads(latest[0])["selection"] if latest else None
            retention_source = None
            if use_manual:
                if previous is not None and previous["decision_date"] >= day:
                    raise ValueError("nonchronological manual decision")
                previous, retention_source = self._last_executed_target(con, day=day)
            timing = manual_timing if use_manual else None
            attempts = []
            reviewed_after = None
            for _ in range(3 if use_manual else 1):
                decision_at = aware(self.clock()).isoformat()
                if retention_source and aware(retention_source["verified_at"]) > aware(decision_at):
                    raise ValueError("previous execution was verified after decision cutoff")
                if use_manual:
                    from .quant25_input_timing import consumer_opted_in, verify_consumer_receipts
                    from .quant25_monthly_evidence import verify_received_monthly
                    verify_capture_binding(timing, receipts, evidence, cutoff=decision_at)
                    if consumer_opted_in(timing):
                        verify_consumer_receipts(timing, evidence, cutoff=decision_at, root=self.root)
                    context = validity(timing, load("calendar"), signal_day=day, cutoff=decision_at,
                                       next_rebalance=next_rebalance, root=self.root)
                    if reviewed_after is not None:
                        if not callable(review_provider):
                            raise ValueError("fresh event/rights review required after open crossing")
                        # Provider supplies a new pinned review, never a new cycle.
                        timing = {**timing, "event_coverage": review_provider(
                            decision_at, context["execution_date"], next_rebalance)}
                    monthly = verify_received_monthly(
                        monthly_target, timing.get("monthly_evidence"), signal_day=day,
                        checked_at=decision_at, observation_root=self.root, availability_cutoff=decision_at)
                    if monthly["receipt_id"] != receipts["etf_intent"] or monthly != evidence["etf_intent"]:
                        raise ValueError("actual monthly receipt does not match captured journal")
                    coverage_scope = set(load("universe")) | (set(monthly_target["weights"]) - {"CASH"})
                    coverage_scope |= {c["ticker"] for c in load("sector")}
                    verify_coverage(timing, evidence=evidence, stocks=coverage_scope, calendar=load("calendar"),
                                    cutoff=decision_at, execution=context["execution_date"], horizon=next_rebalance,
                                    reviewed_after=reviewed_after)
                state = select_decision(
                    features=features, fundamentals=csv("fundamentals"), prices=prices,
                    stocks=load("universe"), calendar=load("calendar"), day=day, next_rebalance=next_rebalance,
                    qm=load("qm"), etf_intent=etf, sector_candidates=load("sector"), rules=load("rules"),
                    evidence=evidence, previous=previous, historical=False, decision_at=decision_at,
                    **({"manual_timing": timing} if use_manual else {}))
                publication_at = aware(self.clock()).isoformat()
                if use_manual:
                    if aware(publication_at) < aware(decision_at):
                        raise ValueError("publication clock moved backward")
                    validity(timing, load("calendar"), signal_day=day, cutoff=publication_at,
                             next_rebalance=next_rebalance, root=self.root)
                    attempts.append({"decision_at": decision_at, "publication_at": publication_at,
                                     "execution_date": state["execution_date"],
                                     "event_coverage": timing["event_coverage"]})
                if aware(publication_at) < aware(state["execution_date"] + "T09:00:00+09:00"):
                    break
                if not use_manual:
                    raise ValueError("selection finished after execution window")
                reviewed_after = publication_at
            else:
                raise ValueError("unsealed selection repeatedly crossed open")
            if state.get("event_materiality"):
                from .quant25_event_materiality import held_profile_restrictions
                snapshots = {p: ledger.snapshot(p, as_of=publication_at) for p in PROFILE_MODEL_IDS}
                protected_profiles = held_profile_restrictions(state["event_materiality"], snapshots)
                state["event_materiality"]["held_profile_restrictions"] = protected_profiles
                for profile, restriction in protected_profiles.items():
                    state["profiles"][profile]["restricted_order_tickers"] = restriction["held_tickers"]
                if retention_source is not None:
                    retention_source["recorded_books_at_decision"] = {
                        p: {"positions": s["positions"], "cash": s["cash"], "as_of": s["as_of"]}
                        for p, s in snapshots.items()}
                state.pop("state_sha256")
                state["state_sha256"] = canonical_sha256(state)
            events = [{
                "event_id": key + ":" + profile, "profile_id": profile, "event_type": "target",
                "occurred_at": decision_at, "observed_at": publication_at,
                "source_sha256": state["state_sha256"],
                "arrival_provenance": {"source_ref": key, "received_at": publication_at},
                "payload": state,
            } for profile in PROFILE_MODEL_IDS]
            if use_manual:
                # Reuse the existing generic target envelope. Keep the complete
                # selector and its TEST_ONLY/actual provenance in the journal;
                # never relabel synthetic selection to satisfy a ledger guard.
                for event in events:
                    profile = event["profile_id"]
                    event["occurred_at"] = publication_at
                    event["payload"] = {
                        "decision_at": publication_at,
                        "positions": state["profiles"][profile]["target_positions"],
                        "cash_weight": state["profiles"][profile]["cash_target"],
                        "selector_provenance": {"state_sha256": state["state_sha256"],
                                                "classification": state["classification"],
                                                "input_timing_context": state["input_timing_context"]},
                    }
                    ledger._normalize_event(event)
            saved = {"request": request, "selection": state, "publication_at": publication_at,
                     "events": events, "classification": "PRIVATE_CAPTURED_TARGETS_NOT_FILLS"}
            if use_manual:
                saved.update(input_timing=timing, timing_attempts=attempts,
                             retention_basis="LAST_VERIFIED_EXECUTED_TARGET_ONLY",
                             retention_source=retention_source, target_is_actual_holdings=False)
                if context["evidence_mode"] == "SYNTHETIC_TEST_ONLY":
                    saved.update(classification="SYNTHETIC_TEST_ONLY", actual_publication=False,
                                 actual_receipt=False)
            self._put(con, key, "decision", saved)
        self.recover()
        return saved

    def recover(self):
        """Replay the durable outbox; ledger event IDs make crash retries harmless."""
        ledger = Quant25PaperLedger.open(self.root / "paper_accounting.sqlite3")
        with self._connect() as con:
            rows = con.execute("SELECT body FROM journal WHERE kind IN ('decision','accounting','paper_execution') ORDER BY sequence").fetchall()
        for row in rows:
            events = json.loads(row[0])["events"]
            if events:
                ledger.append_events(events)
        return ledger

    def execute_observed_open(self, day, source: Path, *, expected_sha256):
        self._freeze()
        ledger = self.recover()
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("observed quote hash mismatch")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM journal WHERE key=?", ("delayed-plan:" + day,)).fetchone():
                raise ValueError("scheduled day is reserved by a sealed delayed plan")
            key = "paper-execution:" + day
            prior = con.execute("SELECT body,raw FROM journal WHERE key=?", (key,)).fetchone()
            if prior:
                if prior["raw"] != raw:
                    raise ValueError("execution already sealed with different quotes")
                return json.loads(prior["body"])
            rows = con.execute("SELECT body FROM journal WHERE kind='decision' ORDER BY sequence DESC").fetchall()
            matches = [json.loads(row[0]) for row in rows if json.loads(row[0])["selection"]["execution_date"] == day]
            if len(matches) != 1:
                if any(json.loads(row[0]).get("input_timing") for row in rows):
                    raise ValueError("BLOCKED_STALE_TARGET: sealed manual target cannot shift execution date")
                raise ValueError("exactly one captured target required for this open")
            saved = matches[0]
            if aware(saved["publication_at"]) >= aware(day + "T09:00:00+09:00"):
                raise ValueError("target was not published before open")
            received = aware(self.clock()).isoformat()
            # Late quote observation must not fund an earlier open with later rights.
            opened = day + "T09:00:00+09:00"
            snapshots = {p: ledger.snapshot(p, as_of=opened) for p in PROFILE_MODEL_IDS}
            result = paper_execution_events(saved["selection"], snapshots, json.loads(raw),
                                            received_at=received, quote_sha256=expected_sha256,
                                            fee_rate=ledger.config.fee_rate)
            if saved["selection"].get("event_materiality"):
                books = {p: {k: s[k] for k in ("positions", "cash", "starting_capital")}
                         for p, s in snapshots.items()}
                result.update(profile_execution_schema="Q25_PARTIAL_SECURITY_EXECUTION_V1",
                              book_inputs=books, book_inputs_sha256=canonical_sha256(books))
            if saved.get("input_timing"):
                result["decision_binding"] = {
                    "decision_id": "decision:" + saved["selection"]["decision_date"],
                    "state_sha256": saved["selection"]["state_sha256"], "execution_date": day,
                    "publication_at": saved["publication_at"], "quote_sha256": expected_sha256,
                    "verified_at": received,
                }
                result["target_is_actual_holdings"] = False
                if saved["input_timing"]["evidence_mode"] == "SYNTHETIC_TEST_ONLY":
                    result.update(classification="SYNTHETIC_TEST_ONLY", actual_execution=False)
            self._put(con, key, "paper_execution", result, raw)
        self.recover()
        return result

    def record_accounting(self, *, event_id, profile_id, event_type, occurred_at, source: Path):
        """Record supplied execution/valuation/rights evidence, never invent a fill."""
        if event_type not in {"fill", "nonfill", "mark", "rights"}:
            raise ValueError("unsupported accounting event")
        raw = source.read_bytes()
        payload = json.loads(raw)
        ledger = self.recover()
        key = "accounting:" + event_id
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prior = con.execute("SELECT body,raw FROM journal WHERE key=?", (key,)).fetchone()
            if prior:
                saved = json.loads(prior["body"])
                old = saved["events"][0]
                if (prior["raw"] != raw or old["event_type"] != event_type
                        or old["profile_id"] != profile_id or aware(old["occurred_at"]) != aware(occurred_at)):
                    raise ValueError("accounting evidence identity conflict")
                return saved
            observed = aware(self.clock()).isoformat()
            event = {
                "event_id": key, "profile_id": profile_id, "event_type": event_type,
                "occurred_at": occurred_at, "observed_at": observed,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "arrival_provenance": {"source_ref": str(source.resolve()), "received_at": observed},
                "payload": payload,
            }
            ledger._normalize_event(event)
            # Preflight the existing transactional balance/chronology checks.
            with ledger._connect() as check:
                normalized = ledger._normalize_event(event)
                ledger._validate_observation_order(check, normalized)
                ledger._validate_transition(check, normalized)
            saved = {"events": [event]}
            self._put(con, key, "accounting", saved, raw)
        self.recover()
        return saved

    def qs_preview(self, day):
        """Persist the existing QS contract preview; it is not a serving release."""
        ledger = self.recover()
        with self._connect() as con:
            row = con.execute("SELECT body FROM journal WHERE key=?", (f"decision:{day}",)).fetchone()
            if row is None:
                raise ValueError("no captured decision")
            saved = json.loads(row[0])
            state = saved["selection"]
            generated = aware(self.clock()).isoformat()
            requests = []
            for profile, model in PROFILE_MODEL_IDS.items():
                snap = ledger.snapshot(profile, as_of=generated)
                if snap["nav_status"] != "pass":
                    raise ValueError("unconfirmed or stale actual valuation")
                # Valuation is not proof of tradability. Unknown trading state
                # blocks executable intent but does not erase existing holdings.
                actual = [{"ticker": p["ticker"], "asset_type": p["asset_type"],
                           "units": float(p["units"]), "mark_price": float(p["mark_price"]),
                           "tradability_state": "UNKNOWN"} for p in snap["positions"]]
                latest_rights = {}
                for event in snap["rights"]:
                    right = event["payload"]
                    latest_rights[right["right_id"]] = event
                cash_rights = []
                for event in latest_rights.values():
                    right = event["payload"]
                    if right["entitlement_type"] != "CASH":
                        continue
                    cash_rights.append({
                        "right_id": right["right_id"], "ticker": right["ticker"],
                        "status": {"UNKNOWN": "UNKNOWN", "CONFIRMED_NOT_RECEIVED": "PENDING_CONFIRMED",
                                   "RECEIVED": "RECEIVED"}[right["status"]],
                        "amount_krw": float(right["cash_amount"]) if right["cash_amount"] is not None else None,
                        "payment_date": aware(event["occurred_at"]).date().isoformat()
                        if right["status"] == "RECEIVED" else None,
                        "evidence": right["evidence"],
                    })
                requests.append({
                    "mode": "isolated_dry_run", "visibility": "internal", "profile_id": profile,
                    "model_id": model, "run_id": f"private-preview-{day}",
                    "data_asof": state["market_observation_date"],
                    "input_available_at": max((aware(r["arrived_at"]) for r in state["input_evidence"].values())).isoformat(),
                    "decision_at": state["decision_cutoff"], "generated_at": generated,
                    "execution_at": state["execution_date"] + "T09:00:00+09:00",
                    "source_input_hashes": {k: r["sha256"] for k, r in state["input_evidence"].items()},
                    "market_regime": state["regime"], "target_positions": state["profiles"][profile]["target_positions"],
                    "actual_positions": actual, "cash_krw": float(snap["cash"]), "cash_entitlements": cash_rights,
                    "unresolved_events": [{"reason": "ACTUAL_TRADABILITY_UNCONFIRMED", "ticker": p["ticker"]}
                                          for p in snap["positions"]]
                    + [{"reason": "RECORDED_NONFILL", "event": e} for e in snap["nonfills"]],
                })
            bundle = build_inactive_dry_run_bundle(requests, freeze_dir=self.freeze_dir)
            self._put(con, "qs-preview:" + bundle["run"]["output_hash"], "qs_preview", bundle)
        return bundle

    def status(self):
        ledger = self.recover()
        with self._connect() as con:
            counts = dict(con.execute("SELECT kind,COUNT(*) FROM journal GROUP BY kind").fetchall())
            config = json.loads(con.execute("SELECT body FROM journal WHERE key='config'").fetchone()[0])
        return {"config": config, "journal_counts": counts, "ledger_event_count": ledger.event_count(),
                "profiles": {p: ledger.snapshot(p, as_of=self.clock()) for p in PROFILE_MODEL_IDS},
                "evaluation_periods": evaluation_period_status(self.clock()),
                "performance_status": "NOT_ESTABLISHED", "public_eligible": False}
