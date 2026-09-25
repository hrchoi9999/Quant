"""Isolated manual-collection timing candidate; no operating entry point.

Extends the existing synthetic bootstrap protocol. Command, collection and
review evidence here are synthetic fixtures, never certificates of real action.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pandas as pd

from src.evaluation.normalized_nav import ExecutionTarget

from .quant25_bootstrap_execution_candidate import BootstrapExecutionCandidate, first_open, marked
from .quant25_incremental_selection import SOURCES, aware, check_evidence
from .quant25_paper_live import PROFILE_MODEL_IDS, canonical_sha256

CONTRACT = "Q25_MANUAL_COLLECTION_TIMING_CANDIDATE_V1"
LABEL = "SYNTHETIC_TEST_ONLY"


def stamp(body):
    return marked({**body, "manual_timing_contract": CONTRACT})


def schedule(calendar, day):
    if not calendar or calendar != sorted(set(calendar)) or day not in calendar:
        raise ValueError("confirmed ordered calendar required")
    anchor = pd.Timestamp(day) + pd.Timedelta(days=(2 - pd.Timestamp(day).weekday()) % 7)
    next_anchor = anchor + pd.Timedelta(days=7)
    if calendar[-1] < next_anchor.strftime("%Y-%m-%d"):
        raise ValueError("calendar must cover next Wednesday anchor")
    if max(d for d in calendar if d <= anchor.strftime("%Y-%m-%d")) != day:
        raise ValueError("fixed weekly signal date required")
    next_signal = max(d for d in calendar if d <= next_anchor.strftime("%Y-%m-%d"))
    i = calendar.index(next_signal)
    if i + 1 >= len(calendar):
        raise ValueError("calendar lacks next rebalance open")
    return next_signal + "T15:30:00+09:00", calendar[i + 1]


def validate_collection(timing, calendar, *, checked_at):
    """Validate explicit evidence; never infer a command from a development turn."""
    if (timing.get("contract_id") != CONTRACT or timing.get("classification") != LABEL
            or timing.get("automatic_collection") is not False):
        raise ValueError("explicit synthetic manual timing contract required")
    command = timing.get("user_command", {})
    if (command.get("actor") != "USER" or command.get("action") != "COLLECT_DATA"
            or command.get("signal_date") != timing.get("signal_date")
            or not command.get("reference") or command.get("classification") != LABEL):
        raise ValueError("explicit user collection command evidence required")
    raw_hash = command.get("sha256", "")
    if raw_hash != canonical_sha256({k: v for k, v in command.items() if k != "sha256"}):
        raise ValueError("user command evidence hash required")
    day = timing["signal_date"]
    expiry, horizon = schedule(calendar, day)
    close = aware(day + "T15:30:00+09:00")
    collectible = aware(timing.get("collectible_at"))
    issued = aware(command.get("issued_at"))
    started = aware(timing.get("collection_started_at"))
    completed = aware(timing.get("collection_completed_at"))
    checked = aware(checked_at)
    # Following calendar morning is only availability evidence, never a timer.
    if collectible.tz_convert("Asia/Seoul").date() <= close.date():
        raise ValueError("post-signal collectible timestamp required")
    if not (close <= collectible <= started <= completed <= checked and close <= issued <= started):
        raise ValueError("missing, future or unordered manual collection timestamps")
    if checked >= aware(expiry):
        raise ValueError("EXPIRED_WEEKLY_SIGNAL")
    return {"expires_at": expiry, "next_rebalance": horizon}


def validate_monthly(value, calendar, *, signal_day, availability_cutoff):
    """Month selection uses signal day; receipt availability uses a separate clock."""
    if value.get("evidence_state") != LABEL:
        raise ValueError("synthetic monthly emission required; actual labels forbidden")
    month = pd.Timestamp(signal_day).to_period("M")
    current = [d for d in calendar if pd.Timestamp(d).to_period("M") == month]
    completed = month if (signal_day == max(current) and
                          calendar[-1] >= month.end_time.strftime("%Y-%m-%d")) else month - 1
    days = [d for d in calendar if pd.Timestamp(d).to_period("M") == completed]
    if not days or value.get("decision_date") != max(days):
        raise ValueError("latest completed monthly ETF intent required")
    publication = aware(value.get("published_at"))
    if not (aware(value["decision_date"] + "T15:30:00+09:00") <= publication <= aware(availability_cutoff)):
        raise ValueError("monthly publication outside availability cutoff")
    if value.get("execution_date") != calendar[calendar.index(value["decision_date"]) + 1]:
        raise ValueError("monthly reference execution mismatch")
    weights = pd.Series(value.get("weights", {}), dtype=float)
    if (weights.empty or not weights.ge(0).all() or not weights.lt(float("inf")).all()
            or abs(weights.sum() - 1) > 1e-9):
        raise ValueError("invalid monthly weights")


def validate_open(timing, calendar, evidence, *, cutoff, execution_date, next_rebalance):
    contract = validate_collection(timing, calendar, checked_at=cutoff)
    check_evidence(evidence, aware(cutoff), historical=False)
    if next_rebalance != contract["next_rebalance"]:
        raise ValueError("next regular rebalance horizon mismatch")
    if execution_date != first_open(calendar, cutoff):
        raise ValueError("first valid future open required")
    if aware(execution_date + "T09:00:00+09:00") >= aware(contract["expires_at"]):
        raise ValueError("EXPIRED_WEEKLY_SIGNAL_EXECUTION")
    return contract


def read_candidate_export(path, *, checked_at):
    """Revalidate immutable bytes and source timing before any candidate receipts."""
    path = Path(path).resolve()
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("manual_timing_contract") != CONTRACT or body.get("classification") != LABEL:
        raise ValueError("manual candidate export required")
    if set(body.get("inputs", {})) != SOURCES:
        raise ValueError("exact nine candidate inputs required")
    files = {}
    for name, item in body["inputs"].items():
        file = (path.parent / item["path"]).resolve()
        if not file.is_relative_to(path.parent):
            raise ValueError("candidate export path escapes directory")
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("candidate export hash mismatch")
        files[name] = raw
    calendar = json.loads(files["calendar"])
    timing = body["timing"]
    validate_collection(timing, calendar, checked_at=checked_at)
    check_evidence(body["inputs"], aware(body["exported_at"]), historical=False)
    if not aware(timing["collection_completed_at"]) <= aware(body["exported_at"]) <= aware(checked_at):
        raise ValueError("export timestamp outside collection/capture interval")
    validate_monthly(json.loads(files["etf_intent"]), calendar, signal_day=timing["signal_date"],
                     availability_cutoff=body["exported_at"])
    return body, files


class ManualCollectionCandidate(BootstrapExecutionCandidate):
    """Reuse journal, selector and execution engine in a separate test directory."""

    def __init__(self, root, *, freeze_dir, clock):
        if not Path(root).name.startswith("SYNTHETIC_TEST_ONLY_MANUAL"):
            raise ValueError("manual candidate isolation directory required")
        super().__init__(root, freeze_dir=freeze_dir, clock=clock)
        if self.path.exists():
            with self._connect() as con:
                if not self._record(con, "manual-contract"):
                    raise ValueError("cannot adopt an existing non-manual candidate journal")

    def seed_from_existing(self, *args, **kwargs):
        result = super().seed_from_existing(*args, **kwargs)
        with self._connect() as con:
            self._put(con, "manual-contract", "manual_contract", stamp({"contract_id": CONTRACT}))
        return result

    def candidate_decide(self, **kwargs):
        raise ValueError("manual_decide requires captured manual batch and review evidence")

    def manual_decide(self, *, batch_id, review_provider):
        """Recalculate an unsealed target on open crossing; never shift a sealed one.

        review_provider is an explicitly supplied synthetic evidence callback,
        not a collector. Missing fresh event/rights review blocks the transaction.
        """
        from .quant25_incremental_selection import select_manual_candidate

        self._freeze()
        self.recover()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            batch = self._record(con, batch_id)
            if not batch or batch.get("manual_timing_contract") != CONTRACT:
                raise ValueError("captured manual batch required")
            timing = batch["timing"]
            day = timing["signal_date"]
            key = "decision:" + day
            saved = self._record(con, key)
            if saved:
                if saved["request"] != {"batch_id": batch_id}:
                    raise ValueError("BLOCKED_STALE_TARGET: sealed decision cannot change inputs")
                return saved
            files, evidence = self._load_inputs(con, batch["receipts"])
            for name, item in batch["source_evidence"].items():
                if item["sha256"] != evidence[name]["sha256"]:
                    raise ValueError("batch/receipt hash mismatch")
            def load(name):
                return json.loads(files[name])

            def csv(name):
                return pd.read_csv(io.BytesIO(files[name]), dtype={"ticker": str})

            if not callable(review_provider):
                raise ValueError("explicit synthetic review provider required")
            calendar = load("calendar")
            _, horizon = schedule(calendar, day)
            last = con.execute("SELECT body FROM journal WHERE kind='decision' ORDER BY sequence DESC LIMIT 1").fetchone()
            if last and json.loads(last[0])["selection"]["decision_date"] >= day:
                raise ValueError("nonchronological manual decision")
            last_fill = con.execute("SELECT body FROM journal WHERE kind='paper_execution' ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = json.loads(last_fill[0])["selection"] if last_fill else None
            etf = load("etf_intent")
            intent = ExecutionTarget(**{**etf, **{k: pd.Timestamp(etf[k]) for k in
                                    ("decision_date", "published_at", "execution_date")}})
            attempts = []
            for _ in range(3):
                cutoff = aware(self.clock()).isoformat()
                execution = first_open(calendar, cutoff)
                validate_open(timing, calendar, evidence, cutoff=cutoff, execution_date=execution, next_rebalance=horizon)
                check_evidence(batch["source_evidence"], aware(cutoff), historical=False)
                review = review_provider(cutoff, execution, horizon)
                if (review.get("classification") != LABEL or not review.get("reference")
                        or review.get("rules_sha256") != evidence["rules"]["sha256"]
                        or review.get("calendar_sha256") != evidence["calendar"]["sha256"]
                        or review.get("execution_date") != execution
                        or aware(review.get("checked_at")) != aware(cutoff)
                        or aware(review.get("coverage_until")) < aware(horizon + "T09:00:00+09:00")
                        or review.get("corporate_actions_reviewed") is not True
                        or review.get("rights_reviewed") is not True
                        or review.get("trading_halts_reviewed") is not True):
                    raise ValueError("fresh event/rights horizon review required")
                state = select_manual_candidate(
                    timing=timing, execution_date=execution, decision_at=cutoff,
                    features=csv("features"), fundamentals=csv("fundamentals"), prices=csv("prices"),
                    stocks=load("universe"), calendar=calendar, day=day, next_rebalance=horizon,
                    qm=load("qm"), etf_intent=intent, sector_candidates=load("sector"), rules=load("rules"),
                    evidence=evidence, previous=previous)
                generated, published, received = (aware(self.clock()).isoformat() for _ in range(3))
                if not aware(cutoff) <= aware(generated) <= aware(published) <= aware(received):
                    raise ValueError("manual decision clock moved backward")
                validate_collection(timing, calendar, checked_at=received)
                attempts.append({"cutoff": cutoff, "execution_date": execution, "review": review,
                                 "selection_sha256": state["state_sha256"],
                                 "profile_tickers": {p: [r["ticker"] for r in value["target_positions"]]
                                                     for p, value in state["profiles"].items()},
                                 "generated_at": generated, "publication_at": published, "received_at": received})
                if first_open(calendar, received) == execution:
                    break
            else:
                raise ValueError("unsealed candidate repeatedly crossed open; fresh invocation required")
            events = [{"event_id": LABEL + ":" + key + ":" + p, "profile_id": p, "event_type": "target",
                       "occurred_at": received, "observed_at": received, "source_sha256": state["state_sha256"],
                       "arrival_provenance": {"source_ref": LABEL + ":" + key, "received_at": received},
                       "payload": {"decision_at": received, "positions": state["profiles"][p]["target_positions"],
                                   "cash_weight": state["profiles"][p]["cash_target"],
                                   "selector_provenance": stamp({"state_sha256": state["state_sha256"],
                                                                 "decision_cutoff": cutoff})}}
                      for p in PROFILE_MODEL_IDS]
            saved = stamp({"request": {"batch_id": batch_id}, "selection": state, "generated_at": generated,
                           "publication_at": published, "received_at": received, "events": events,
                           "calendar": calendar, "attempts": attempts, "timing": timing,
                           "retention_basis": "LAST_EXECUTED_CANDIDATE_TARGET_ONLY"})
            self._put(con, key, "decision", saved)
        self.recover()
        return saved
