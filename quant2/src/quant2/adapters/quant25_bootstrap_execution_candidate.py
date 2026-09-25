"""Explicitly isolated bootstrap/delayed-open candidate. No operating entry point.

The existing monthly calculator, nine-input receipts, selector, funding solver
and append-only forward outbox/ledger are reused. All clocks in tests are
synthetic; no actual publication or receipt is certified by this module.
"""

from __future__ import annotations

import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path

import pandas as pd

from src.evaluation.normalized_nav import ExecutionTarget, next_open_after_publication

from .quant25_etf_intent_connection import SEMANTICS, _digest, _read
from .quant25_forward_connection import ForwardConnection, _encode
from .quant25_incremental_selection import CANDIDATE_CONTRACT, aware, select_decision
from .quant25_monthly_etf_candidate import INITIAL_SCHEMA, STATE_SCHEMA, InactiveMonthlyETFCandidate
from .quant25_observed_paper_execution import paper_execution_events
from .quant25_paper_ledger import Quant25PaperLedger
from .quant25_paper_live import PROFILE_MODEL_IDS, canonical_sha256

LABEL = "SYNTHETIC_TEST_ONLY"


def marked(body):
    return {
        **body,
        "classification": LABEL,
        "candidate_contract": CANDIDATE_CONTRACT,
        "approval_status": "NOT_APPROVED",
        "active": False,
        "actual_publication": False,
        "actual_receipt": False,
        "public_eligible": False,
        "scheduler_registered": False,
        "counts_as_live_sample": False,
    }


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class DeferredInputReviewRequired(ValueError):
    """Block time-shifting a sealed target without a fresh input review contract."""

    def __init__(self, selection, requested_day):
        self.detail = marked({
            "status": "BLOCKED_STALE_TARGET", "new_input_review_required": True,
            "reason": "DEFERRED_OPEN_REQUIRES_FRESH_INPUT_REVIEW",
            "decision_state_sha256": selection["state_sha256"],
            "original_execution_date": selection["execution_date"], "requested_execution_date": requested_day,
            "required_review": ["corporate_actions", "trading_halts", "current_input_provenance"],
            "execution_journal_written": False,
        })
        super().__init__("SYNTHETIC_TEST_ONLY: BLOCKED_STALE_TARGET; deferred open requires fresh input review")


def first_open(calendar, ready_at):
    if not calendar or calendar != sorted(set(calendar)):
        raise ValueError("confirmed ordered calendar required")
    return next_open_after_publication(aware(ready_at), pd.DatetimeIndex(calendar)).strftime("%Y-%m-%d")


class BootstrapExecutionCandidate(ForwardConnection):
    """Test-only facade; its separate directory and config must both be marked."""

    def __init__(self, root, *, freeze_dir, clock):
        if not Path(root).resolve().name.startswith(LABEL):
            raise ValueError("SYNTHETIC_TEST_ONLY directory required")
        super().__init__(Path(root), freeze_dir=Path(freeze_dir), clock=clock)
        if self.path.exists():
            with self._connect() as con:
                row = con.execute("SELECT body FROM journal WHERE key='config'").fetchone()
            if not row or json.loads(row[0]).get("candidate_contract") != CANDIDATE_CONTRACT:
                raise ValueError("cannot adopt an actual or unmarked observation journal")

    @staticmethod
    def _put(con, key, kind, body, raw=None):
        ForwardConnection._put(con, key, kind, marked(body), raw)

    def initialize(self, **kwargs):
        raise ValueError("reuse existing configuration via seed_from_existing; no new operating initialization")

    def seed_from_existing(self, config_path, *, expected_sha256):
        _, existing = _read(config_path, expected_sha256)
        if (
            existing.get("classification") != "PRIVATE_OBSERVATION_NOT_INVESTED"
            or existing.get("capital_per_profile") != "100000000"
            or existing.get("fee_rate") != "0.002"
            or existing.get("actual_fills_created") is not False
            or existing.get("public_eligible") is not False
            or existing.get("scheduler_registered") is not False
        ):
            raise ValueError("existing uninvested configuration required")
        clock = self.clock
        self.clock = lambda: existing["observation_started_at"]
        try:
            ForwardConnection.initialize(
                self,
                starting_capital=existing["capital_per_profile"],
                fee_rate=existing["fee_rate"],
                approval_ref=existing["approval_ref"],
            )
        finally:
            self.clock = clock
        with self._connect() as con:
            self._put(
                con,
                "candidate-config-source",
                "candidate_config_source",
                {"sha256": expected_sha256, "existing_config": existing},
            )
        return self.status()

    def status(self):
        return marked(super().status())

    def recover(self):
        """A valid zero-turnover candidate seals an empty outbox, not a fake fill."""
        ledger = Quant25PaperLedger.open(self.root / "paper_accounting.sqlite3")
        with self._connect() as con:
            rows = con.execute(
                "SELECT body FROM journal WHERE kind IN ('decision','accounting','paper_execution') ORDER BY sequence"
            ).fetchall()
        for row in rows:
            events = json.loads(row[0])["events"]
            if events:
                ledger.append_events(events)
        return ledger

    def capture(self, name, path, *, expected_sha256):
        return marked(super().capture(name, path, expected_sha256=expected_sha256))

    def decide(self, **kwargs):
        raise ValueError("candidate_decide required; ordinary path remains unchanged")

    def execute_observed_open(self, *args, **kwargs):
        raise ValueError("candidate_execute required; ordinary path remains unchanged")

    def _record(self, con, key):
        row = con.execute("SELECT body FROM journal WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def emit_monthly(self, day, prices_path, calendar_path, *, prices_sha256, calendar_sha256):
        """Explicit CASH bootstrap or linked preceding monthly target, never holdings."""
        self._freeze()
        ledger = self.recover()
        request = {"day": day, "prices_sha256": _digest(prices_sha256), "calendar_sha256": _digest(calendar_sha256)}
        if digest(prices_path) != prices_sha256 or digest(calendar_path) != calendar_sha256:
            raise ValueError("monthly input hash mismatch")
        key = "candidate-monthly:" + day
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            saved = self._record(con, key)
            if saved:
                if saved["request"] != request:
                    raise ValueError("monthly candidate already sealed")
                return saved
            rows = con.execute("SELECT body FROM journal WHERE kind='candidate_monthly' ORDER BY sequence").fetchall()
            if rows:
                previous = json.loads(rows[-1][0])
                state = {
                    "schema": STATE_SCHEMA,
                    "classification": LABEL,
                    "decision_date": previous["candidate"]["decision_date"],
                    "weights": previous["candidate"]["weights"],
                    "previous_candidate_sha256": previous["candidate_sha256"],
                }
            else:
                if any(ledger.snapshot(p)["positions"] for p in PROFILE_MODEL_IDS) or ledger.event_count():
                    raise ValueError("bootstrap requires uninvested empty candidate books")
                config = self._record(con, "candidate-config-source")
                state = {
                    "schema": INITIAL_SCHEMA,
                    "classification": LABEL,
                    "weights": {"CASH": 1.0},
                    "decision_date": None,
                    "uninvested": True,
                    "previous_target_exists": False,
                    "existing_config_sha256": config["sha256"],
                }
            state_path = self.root / ("monthly-state-" + day + ".json")
            state_path.write_text(_encode(state), encoding="utf-8")
            engine = InactiveMonthlyETFCandidate(freeze_dir=self.freeze_dir, clock=lambda: aware(self.clock()))
            candidate = marked(
                engine.calculate(
                    decision_date=day,
                    prices_path=prices_path,
                    calendar_path=calendar_path,
                    previous_target_state_path=state_path,
                    expected_input_hashes={
                        "prices": prices_sha256,
                        "calendar": calendar_sha256,
                        "previous_target_state": digest(state_path),
                    },
                )
            )
            result = marked(
                {
                    "request": request,
                    "candidate": candidate,
                    "candidate_sha256": canonical_sha256(candidate),
                    "previous_state": state,
                }
            )
            self._put(con, key, "candidate_monthly", result)
        return result

    def receive_monthly(self, day):
        """Bind new synthetic emission to the ordinary nine-input receipt protocol.

        The actual-publication receiver is intentionally not invoked: a candidate
        must never be labelled ACTUAL_PRODUCER_PUBLICATION to pass its guards.
        """
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            binding_key = "candidate-monthly-received:" + day
            binding = self._record(con, binding_key)
            if binding:
                return self._record(con, binding["receipt_id"])
            saved = self._record(con, "candidate-monthly:" + day)
            if not saved or canonical_sha256(saved["candidate"]) != saved["candidate_sha256"]:
                raise ValueError("sealed monthly candidate required")
            monthly = saved["candidate"]
            received = aware(self.clock())
            if not (
                aware(day + "T15:30:00+09:00")
                <= aware(monthly["generated_at"])
                <= aware(monthly["published_at"])
                <= received
            ):
                raise ValueError("candidate emission/receipt chronology violation")
            target = {
                "model_code": "S6_REFERENCE",
                "decision_date": day,
                "published_at": monthly["published_at"],
                "execution_date": monthly["reference_execution_date"],
                "run_id": CANDIDATE_CONTRACT,
                "weights": monthly["weights"],
                "evidence_state": LABEL,
            }
            raw = _encode(target).encode("utf-8")
            target_hash = hashlib.sha256(raw).hexdigest()
            receipt_id = "receipt:etf_intent:" + target_hash
            record = marked(
                {
                    "receipt_id": receipt_id,
                    "source": "etf_intent",
                    "sha256": target_hash,
                    "source_path": "SYNTHETIC_TEST_ONLY:monthly:" + day,
                    "arrived_at": received.isoformat(),
                    "available_at": received.isoformat(),
                    "provider_available_at": monthly["published_at"],
                    "availability_basis": "SYNTHETIC_CANDIDATE_EMISSION_RECEIPT",
                    "semantics": SEMANTICS,
                    "historical_receipt_inferred": False,
                    "monthly_candidate_sha256": saved["candidate_sha256"],
                }
            )
            self._put(con, receipt_id, "receipt", record, raw)
            self._put(
                con,
                binding_key,
                "candidate_monthly_received",
                {"receipt_id": receipt_id, "candidate_sha256": saved["candidate_sha256"]},
            )
        return record

    def candidate_decide(self, *, day, next_rebalance, receipts):
        self._freeze()
        self.recover()
        request = {"day": day, "next_rebalance": next_rebalance, "receipts": receipts}
        key = "decision:" + day
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            saved = self._record(con, key)
            if saved:
                if saved["request"] != request:
                    raise ValueError("candidate decision already sealed")
                return saved
            files, evidence = self._load_inputs(con, receipts)
            bindings = [
                json.loads(r[0])["receipt_id"]
                for r in con.execute("SELECT body FROM journal WHERE kind='candidate_monthly_received'")
            ]
            if receipts["etf_intent"] not in bindings:
                raise ValueError("new candidate monthly emission binding required")
            monthly_targets = [
                json.loads(r[0])["candidate"]
                for r in con.execute("SELECT body FROM journal WHERE kind='candidate_monthly'")
            ]
            monthly_day = json.loads(files["etf_intent"])["decision_date"]
            monthly_target = next(m for m in monthly_targets if m["decision_date"] == monthly_day)
            if monthly_target["initial_branch"] == "EXPLICIT_UNINVESTED_CASH_CANDIDATE" and aware(
                day + "T15:30:00+09:00"
            ) < aware(monthly_target["generated_at"]):
                raise ValueError("bootstrap must precede a subsequent scheduled weekly signal")
            last = con.execute(
                "SELECT body FROM journal WHERE kind='decision' ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if last and json.loads(last[0])["selection"]["decision_date"] >= day:
                raise ValueError("nonchronological candidate decision")
            last_fill = con.execute(
                "SELECT body FROM journal WHERE kind='paper_execution' ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = json.loads(last_fill[0])["selection"] if last_fill else None

            def load(name):
                return json.loads(files[name])

            def csv(name):
                return pd.read_csv(io.BytesIO(files[name]), dtype={"ticker": str})

            features, prices, calendar = csv("features"), csv("prices"), load("calendar")
            if set(features.date.astype(str)) != {day} or prices.date.max() != day:
                raise ValueError("scheduled signal-day features and prices required")
            etf = load("etf_intent")
            etf = ExecutionTarget(
                **{**etf, **{k: pd.Timestamp(etf[k]) for k in ("decision_date", "published_at", "execution_date")}}
            )
            cutoff = aware(self.clock()).isoformat()
            execution = first_open(calendar, cutoff)
            state = select_decision(
                features=features,
                fundamentals=csv("fundamentals"),
                prices=prices,
                stocks=load("universe"),
                calendar=calendar,
                day=day,
                next_rebalance=next_rebalance,
                qm=load("qm"),
                etf_intent=etf,
                sector_candidates=load("sector"),
                rules=load("rules"),
                evidence=evidence,
                previous=previous,
                historical=False,
                decision_at=cutoff,
                candidate_timing={
                    "contract_id": CANDIDATE_CONTRACT,
                    "classification": LABEL,
                    "execution_date": execution,
                },
            )
            generated, published, received = (aware(self.clock()).isoformat() for _ in range(3))
            if not (aware(cutoff) <= aware(generated) <= aware(published) <= aware(received)):
                raise ValueError("candidate decision clock moved backward")
            if first_open(calendar, received) != execution:
                raise ValueError("generation crossed open; new candidate calculation required")
            events = []
            for p in PROFILE_MODEL_IDS:
                targets = state["profiles"][p]
                events.append(
                    {
                        "event_id": "SYNTHETIC_TEST_ONLY:" + key + ":" + p,
                        "profile_id": p,
                        "event_type": "target",
                        "occurred_at": received,
                        "observed_at": received,
                        "source_sha256": state["state_sha256"],
                        "arrival_provenance": {"source_ref": "SYNTHETIC_TEST_ONLY:" + key, "received_at": received},
                        "payload": {
                            "decision_at": received,
                            "positions": targets["target_positions"],
                            "cash_weight": targets["cash_target"],
                            "selector_provenance": marked(
                                {"state_sha256": state["state_sha256"], "decision_cutoff": cutoff}
                            ),
                        },
                    }
                )
            saved = marked(
                {
                    "request": request,
                    "selection": state,
                    "generated_at": generated,
                    "publication_at": published,
                    "received_at": received,
                    "events": events,
                    "calendar": calendar,
                    "retention_basis": "LAST_EXECUTED_CANDIDATE_TARGET_ONLY",
                }
            )
            self._put(con, key, "decision", saved)
        self.recover()
        return saved

    def defer_open(self, day, *, reason):
        if reason not in {"OPEN_EVIDENCE_UNAVAILABLE", "INPUT_NOT_READY"}:
            raise ValueError("explicit missing-input reason required")
        now = aware(self.clock())
        if now < aware(day + "T09:00:00+09:00"):
            raise ValueError("cannot declare a future open missed")
        with self._connect() as con:
            if self._record(con, "paper-execution:" + day):
                raise ValueError("already executed open cannot be deferred")
            key = "candidate-deferred-open:" + day
            prior = self._record(con, key)
            if prior:
                return prior
            result = marked({"day": day, "reason": reason, "observed_at": now.isoformat()})
            self._put(con, key, "candidate_deferred_open", result)
        return result

    def candidate_execute(self, day, source, *, expected_sha256):
        self._freeze()
        ledger = self.recover()
        raw, quote = _read(source, expected_sha256)
        opened = aware(day + "T09:00:00+09:00")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            key = "paper-execution:" + day
            prior = self._record(con, key)
            if prior:
                if prior["quote_sha256"] != expected_sha256:
                    raise ValueError("candidate execution already sealed")
                return prior
            all_decisions = [json.loads(r[0]) for r in con.execute("SELECT body FROM journal WHERE kind='decision'")]
            executions = [
                json.loads(r[0]) for r in con.execute("SELECT body FROM journal WHERE kind='paper_execution'")
            ]
            done = {r["decision_id"] for r in executions} | {
                d for r in executions for d in r["superseded_decision_ids"]
            }
            available = [
                r
                for r in all_decisions
                if "decision:" + r["selection"]["decision_date"] not in done and aware(r["received_at"]) < opened
            ]
            valid = [r for r in available if r["selection"]["execution_date"] <= day < r["selection"]["next_rebalance"]]
            if not valid:
                raise ValueError("no valid unexecuted candidate before this open")
            saved = max(valid, key=lambda r: r["selection"]["decision_date"])
            state = deepcopy(saved["selection"])
            if day not in saved["calendar"]:
                raise ValueError("execution outside confirmed calendar")
            deferred = {
                json.loads(r[0])["day"]
                for r in con.execute("SELECT body FROM journal WHERE kind='candidate_deferred_open'")
            }
            earlier = [d for d in saved["calendar"] if first_open(saved["calendar"], saved["received_at"]) <= d < day]
            if not set(earlier) <= deferred:
                raise ValueError("earlier available open was not explicitly deferred")
            if day in deferred:
                raise ValueError("deferred open cannot later be backfilled")
            if day != state["execution_date"]:
                raise DeferredInputReviewRequired(state, day)
            original_hash = state.pop("state_sha256")
            state.update(execution_date=day, source_decision_sha256=original_hash)
            state["state_sha256"] = canonical_sha256(state)
            received = aware(self.clock()).isoformat()
            snapshots = {p: ledger.snapshot(p, as_of=opened.isoformat()) for p in PROFILE_MODEL_IDS}
            result = paper_execution_events(
                state,
                snapshots,
                quote,
                received_at=received,
                quote_sha256=expected_sha256,
                fee_rate=ledger.config.fee_rate,
            )
            for event in result["events"]:
                event["event_id"] = "SYNTHETIC_TEST_ONLY:" + event["event_id"]
                event["arrival_provenance"]["source_ref"] = (
                    "SYNTHETIC_TEST_ONLY:" + event["arrival_provenance"]["source_ref"]
                )
                if "execution_evidence" in event["payload"]:
                    event["payload"]["execution_evidence"].update(marked({}))
            result = marked(
                {
                    **result,
                    "selection": state,
                    "decision_id": "decision:" + state["decision_date"],
                    "quote_sha256": expected_sha256,
                    "funding_snapshot_as_of": opened.isoformat(),
                    "superseded_decision_ids": [
                        "decision:" + r["selection"]["decision_date"]
                        for r in available
                        if r["selection"]["decision_date"] < state["decision_date"]
                    ],
                }
            )
            self._put(con, key, "paper_execution", result, raw)
        self.recover()
        return result
