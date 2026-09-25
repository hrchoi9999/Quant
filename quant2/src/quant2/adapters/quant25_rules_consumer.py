"""OS-only date-precision corrections; frozen research interval code is unchanged."""

import hashlib
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pandas as pd

from src.quant2.evaluation.quant25_event_exclusion import announced_overlap as frozen_overlap
from src.quant2.evaluation.quant25_market_calibration import aware

NON_CASH_RIGHTS = {"EXTRAORDINARY_GENERAL_MEETING_VOTING", "SMALL_SCALE_MERGER_OBJECTION"}


def _date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("canonical date precision required")
    return value


def _key(row):
    return str(row["ticker"]), row.get("event_id", row["source_hash"])


def append_release_correction(rules_path, patch_path, *, patch_sha256):
    """Keep all original rows and append one exactly matched observed revision."""
    raw = Path(patch_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != patch_sha256:
        raise ValueError("correction patch hash mismatch")
    patch = json.loads(raw)
    original_raw = Path(rules_path).read_bytes()
    if (patch.get("schema") != "q25_isolated_rule_correction_patch_v1"
            or patch.get("apply_to_operating_rules") is not False
            or hashlib.sha256(original_raw).hexdigest() != patch["original_rules"]["sha256"]):
        raise ValueError("exact original rules revision required")
    original = json.loads(original_raw)
    candidate = deepcopy(original)
    for correction in patch["patches"]:
        match = correction["match"]["original_rule"]
        matches = [r for r in original if r == match]
        if (len(matches) != 1 or correction["ticker"] != match["ticker"]
                or tuple(correction["match"]["consumer_group_key"]) != _key(match)
                or correction["operation"] != "CLOSE_HISTORICAL_HALT_AT_OFFICIAL_RELEASE_DATE"
                or correction.get("effective_until_timestamp") is not None):
            raise ValueError("one exact same-source halt match and date-only correction required")
        source = correction["source"]
        if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("correction official source hash mismatch")
        observed = correction["observed_at"]
        if (source["observed_at"] != observed or correction["known_at_for_new_observation"] != observed
                or aware(observed) < aware(match["known_at"])):
            raise ValueError("actual correction observation time required")
        end_date = _date(correction["verified_effective_until_date"])
        if end_date <= aware(match["effective_from"]).tz_convert("Asia/Seoul").date().isoformat():
            raise ValueError("invalid date-precision release interval")
        candidate.append({
            **match, "event_id": _key(match)[1], "source_hash": source["sha256"],
            "known_at": observed, "effective_until": None, "effective_until_date": end_date,
            "end_precision": "DATE", "end_semantics": "OFFICIAL_RELEASE_REGULAR_SESSION_DATE",
            "correction": {
                "original_rule": deepcopy(match), "match_source_hash": match["source_hash"],
                "original_rules_sha256": patch["original_rules"]["sha256"], "patch_sha256": patch_sha256,
                "source": deepcopy(source), "observed_at": observed,
                "verified_effective_until_date": end_date,
                "announcement_local": correction.get("announcement_local"),
                "intraday_release_time": None, "past_live_evidence": False,
            },
        })
    return candidate


def release_precedes_execution(release_date, execution_at):
    """Date interval boundary only; caller must separately enforce observation time."""
    release = _date(release_date)
    execution = aware(execution_at).tz_convert("Asia/Seoul")
    execution_date = execution.date().isoformat()
    if release == execution_date and execution != execution.normalize() + pd.Timedelta(hours=9):
        raise ValueError("date-only release does not establish preopen or intraday tradability")
    return release <= execution_date


def announced_overlap(rules, decision_at, execution_at, next_rebalance_at):
    """Release by local trading date without synthesizing an end timestamp.

    Only the exact known event group is removed. Other halts and coverage gates
    remain independent. Release-day evaluation is for the regular 09:00 open;
    this is the execution contract, not an inferred announcement/release time.
    """
    if not any("effective_until_date" in row for row in rules):
        return frozen_overlap(rules, decision_at, execution_at, next_rebalance_at)
    # Preserve the frozen validator's identity/chronology/same-time conflict checks.
    frozen_overlap(rules, decision_at, execution_at, next_rebalance_at)
    decision, execution = aware(decision_at), aware(execution_at).tz_convert("Asia/Seoul")
    latest = {}
    for row in rules:
        if "effective_until_date" in row:
            correction = row.get("correction", {})
            original = correction.get("original_rule", {})
            end_date = _date(row["effective_until_date"])
            if (row.get("effective_until") is not None or row.get("end_precision") != "DATE"
                    or row.get("end_semantics") != "OFFICIAL_RELEASE_REGULAR_SESSION_DATE"
                    or original not in rules or _key(row) != _key(original)
                    or row["known_at"] != correction.get("observed_at")
                    or row["known_at"] != correction.get("source", {}).get("observed_at")
                    or end_date != correction.get("verified_effective_until_date")
                    or row["source_hash"] != correction.get("source", {}).get("sha256")
                    or row["effective_from"] != original.get("effective_from")
                    or end_date <= aware(row["effective_from"]).tz_convert("Asia/Seoul").date().isoformat()):
                raise ValueError("date-precision correction lineage mismatch")
        if aware(row["known_at"]) <= decision:
            key = _key(row)
            if key not in latest or aware(row["known_at"]) >= aware(latest[key]["known_at"]):
                latest[key] = row
    ended = set()
    for key, row in latest.items():
        release = row.get("effective_until_date")
        if release is not None and release_precedes_execution(release, execution):
            ended.add(key)
    return frozen_overlap([r for r in rules if _key(r) not in ended], decision_at, execution_at, next_rebalance_at)


def non_cash_record_dates(supplement, *, observed_asof):
    """Consume explicit voting/objection purposes without creating cash claims."""
    records = []
    for company in supplement["records"]:
        for action in company["known_actions"]:
            if action["event_type"] != "RECORD_DATE_PURPOSE_RESOLVED":
                continue
            facts, source = action["facts"], action["source"]
            if aware(source["observed_at"]) > aware(observed_asof):
                continue
            if (facts.get("right_type") not in NON_CASH_RIGHTS
                    or facts.get("cash_dividend_or_distribution_inferred") is not False):
                raise ValueError("explicit non-cash record-date purpose required")
            if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("record-date source hash mismatch")
            _date(facts["record_date"])
            records.append({
                "ticker": company["ticker"], "event_type": action["event_type"],
                "entitlement_type": "NON_FINANCIAL_RIGHT", "right_type": facts["right_type"],
                "facts": deepcopy(facts), "source": deepcopy(source),
                "cash_ledger_eligible": False, "cash_amount": None, "units": None,
                "requires_eligibility_review_if_selected_or_held": True,
            })
    return records
