"""Inactive, single-month extraction of the frozen etf_events('M') calculation.

No seed replay, operating entry point, receipt, schedule, or publication activation.
The frozen cadence source stays byte-identical. Its per-date availability,
selection and S6 allocation logic is reused here without its historical loop.
All emitted objects are SYNTHETIC_TEST_ONLY and cannot be actual publications.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.configs.s6_defensive_config import S6DefensiveConfig
from src.backtest.portfolio.s6_defensive_allocator import allocate_s6_defensive
from src.quant2.adapters.quant25_paper_live import validate_freeze_bundle
from src.quant2.evaluation.quant25_cadence import valid_weights

CLASSIFICATION = "SYNTHETIC_TEST_ONLY"
STATE_SCHEMA = "q25_explicit_previous_month_target_v1"
INITIAL_SCHEMA = "q25_explicit_uninvested_cash_candidate_v1"
SOURCE_NAMES = {"quant25_cadence.py", "s6_defensive_config.py", "s6_defensive_allocator.py"}
GATES = (
    "first_operating_month_not_approved",
    "initial_operating_target_state_not_approved",
    "late_input_execution_policy_not_approved",
)


def _now():
    return datetime.now(timezone(timedelta(hours=9)))


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("explicit canonical decision date required")
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is not None or stamp.strftime("%Y-%m-%d") != value:
        raise ValueError("canonical session date required")
    return value


def _check_weights(weights, meta):
    if not isinstance(weights, dict) or any(
        isinstance(w, bool) or not isinstance(w, (int, float)) for w in weights.values()
    ):
        raise ValueError("explicit numeric previous/target weights required")
    valid_weights(weights)
    if not set(weights) <= set(meta.ticker) | {"CASH"}:
        raise ValueError("target outside frozen 14 ETF universe")
    if len([t for t, w in weights.items() if t != "CASH" and w > 0]) > 5:
        raise ValueError("maximum five core ETFs")
    inverse = set(meta.loc[meta.is_inverse.eq(1), "ticker"])
    if sum(weights.get(t, 0) for t in inverse) > S6DefensiveConfig().bounds.inverse_cap + 1e-9:
        raise ValueError("frozen inverse cap exceeded")


def _single_date(prices, meta, calendar, day, previous):
    """Frozen cadence per-date calculation; previous target is NOT actual holdings."""
    selected = prices.loc[prices.ticker.isin(meta.ticker) & prices.date.le(day)].copy()
    if selected.duplicated(["date", "ticker"]).any():
        raise ValueError("duplicate price keys")
    # A whole missing session cannot shorten the lookback silently.
    sessions = [d for d in calendar if d <= day][-21:]
    if len(sessions) < 21 or not set(sessions) <= set(selected.date):
        raise ValueError("incomplete 21-session history")
    if not set(selected.date) <= set(calendar):
        raise ValueError("prices outside explicit calendar")
    for field in ("open", "close", "volume", "value"):
        selected[field] = pd.to_numeric(selected[field], errors="raise")
        if np.isinf(selected[field]).any():
            raise ValueError("infinite price input")
    dates = sorted(selected.date.unique())
    close = selected.pivot(index="date", columns="ticker", values="close").reindex(dates)
    value = selected.pivot(index="date", columns="ticker", values="value").reindex(dates)
    close.index = pd.to_datetime(close.index)
    value.index = pd.to_datetime(value.index)
    quotes = selected.set_index(["date", "ticker"])
    stamp = pd.Timestamp(day)
    px, activity = close.loc[:stamp].tail(21), value.loc[:stamp].tail(20)
    valid = px.columns[(px.notna() & np.isfinite(px) & px.gt(0)).all() & activity.notna().all() & activity.gt(0).all()]

    def usable(ticker):
        try:
            quote = quotes.loc[(day, ticker), ["open", "close", "volume"]].astype(float)
            return bool(np.isfinite(quote).all() and quote.gt(0).all())
        except KeyError:
            return False

    held = {t for t, w in previous.items() if t != "CASH" and w > 0}
    locked = sorted(t for t in held if not usable(t))
    if locked:
        raise ValueError("held_etf_quote_unusable:" + ",".join(locked))
    tradable = {t for t in valid if usable(t)}
    core = meta.loc[meta.ticker.isin(tradable)].copy()
    core["liquidity_20d_value"] = core.ticker.map(activity.mean())
    cfg = S6DefensiveConfig()
    core = core.loc[core.group_key.ne(cfg.signals.market_group) | core.ticker.eq("069500")]
    if "069500" not in set(core.ticker):
        raise ValueError("fixed_market_proxy_signal_unavailable")
    alloc = allocate_s6_defensive(
        core_df=core,
        close_wide=close,
        ret_wide=close.pct_change(fill_method=None),
        asof=stamp,
        cfg=cfg,
        available_tickers=sorted(tradable),
    )
    weights = {k: float(v) for k, v in alloc.weights.items() if v > 0}
    _check_weights(weights, meta)
    return weights, alloc.diagnostics


class InactiveMonthlyETFCandidate:
    """Read-only calculation from explicitly hashed files; no operating mode."""

    def __init__(self, *, freeze_dir, clock=None, calculation_revision=None, calculation_revision_sha256=None):
        self.clock = clock or _now
        self.freeze = validate_freeze_bundle(Path(freeze_dir))
        self.calculation = _single_date
        self.revision_metadata = {}
        self.revision_sources = {}
        if (calculation_revision is None) != (calculation_revision_sha256 is None):
            raise ValueError('Calculation revision ID and hash must be supplied together')
        if calculation_revision is not None:
            from src.quant2.operations.etf_revision import calculator, read_revision
            revision = read_revision(calculation_revision, calculation_revision_sha256, self.freeze)
            self.calculation = calculator(_single_date, revision)
            self.revision_sources = {str(Path(__file__).resolve().parents[4] / p): h for p, h in revision['source_hashes'].items()}
            self.revision_metadata = {'calculation_revision': calculation_revision,
                                      'calculation_revision_sha256': calculation_revision_sha256}

        self.sources = {
            p: h for p, h in self.freeze["manifest"]["source_hashes"].items() if Path(p).name in SOURCE_NAMES
        }
        if {Path(p).name for p in self.sources} != SOURCE_NAMES:
            raise ValueError("frozen calculation source references incomplete")
        for path, digest in self.sources.items():
            if _hash(Path(path).read_bytes()) != digest:
                raise ValueError("frozen calculation source changed")
        refs = [
            (p, h)
            for p, h in self.freeze["execution_contract"]["source_hashes"].items()
            if p.replace("\\", "/").endswith("/etf_meta.csv")
        ]
        if len(refs) != 1:
            raise ValueError("one frozen metadata source required")
        path, self.metadata_sha256 = refs[0]
        raw = (Path(__file__).resolve().parents[4] / path).read_bytes()
        if _hash(raw) != self.metadata_sha256:
            raise ValueError("frozen metadata changed")
        self.meta = pd.read_csv(io.BytesIO(raw), dtype={"ticker": str})
        if len(self.meta) != 14 or self.meta.ticker.nunique() != 14 or "069500" not in set(self.meta.ticker):
            raise ValueError("frozen 14 ETF metadata required")

    def calculate_values(
        self, *, decision_date, prices_path, calendar_path, previous_target_state_path, expected_input_hashes,
        state_classification=CLASSIFICATION,
    ):
        day = _day(decision_date)
        paths = {"prices": prices_path, "calendar": calendar_path, "previous_target_state": previous_target_state_path}
        if not isinstance(expected_input_hashes, dict) or set(expected_input_hashes) != set(paths):
            raise ValueError("explicit hashes for all three inputs required")
        inputs = {}
        for key, path in paths.items():
            if path is None:
                raise ValueError("previous state/inputs cannot default to cash or a historical seed")
            raw = Path(path).read_bytes()
            if _hash(raw) != expected_input_hashes[key]:
                raise ValueError("input hash mismatch:" + key)
            inputs[key] = raw
        calendar = json.loads(inputs["calendar"])
        if not isinstance(calendar, list) or calendar != sorted(set(calendar)):
            raise ValueError("explicit ordered unique calendar required")
        if any(_day(d) != d for d in calendar) or day not in calendar:
            raise ValueError("decision session absent")
        month = pd.Timestamp(day).to_period("M")
        monthly = [d for d in calendar if pd.Timestamp(d).to_period("M") == month]
        if calendar[-1] <= month.end_time.strftime("%Y-%m-%d") or day != max(monthly):
            raise ValueError("completed month-end and next confirmed session required")
        reference_execution = calendar[calendar.index(day) + 1]
        previous = json.loads(inputs["previous_target_state"])
        if not isinstance(previous, dict) or previous.get("schema") not in {STATE_SCHEMA, INITIAL_SCHEMA}:
            raise ValueError("explicit previous month target state required; initial policy unresolved")
        if previous.get("classification") != state_classification:
            raise ValueError("explicit previous state classification mismatch")
        initial = previous["schema"] == INITIAL_SCHEMA
        previous_day = None if initial else _day(previous.get("decision_date"))
        if initial:
            if (previous.get("weights") != {"CASH": 1.0} or previous.get("uninvested") is not True
                    or previous.get("previous_target_exists") is not False
                    or previous.get("decision_date") is not None
                    or not previous.get("existing_config_sha256")):
                raise ValueError("explicit uninvested cash evidence required; no invented previous target")
            now = pd.Timestamp(self.clock()).tz_convert("Asia/Seoul")
            ends = {}
            for session in calendar:
                ends[pd.Timestamp(session).to_period("M")] = session
            eligible = [d for period, d in ends.items()
                        if calendar[-1] > period.end_time.strftime("%Y-%m-%d")
                        and pd.Timestamp(d + "T15:30:00+09:00") <= now]
            if not eligible or day != max(eligible):
                raise ValueError("bootstrap requires latest completed monthly data")
        else:
            prior_month = [d for d in calendar if pd.Timestamp(d).to_period("M") == month - 1]
            if not prior_month or previous_day != max(prior_month):
                raise ValueError("immediately preceding month target required; no implicit initial state")
        _check_weights(previous.get("weights"), self.meta)
        if self.clock() < datetime.fromisoformat(day + "T15:30:00+09:00"):
            raise ValueError("decision close has not occurred")
        prices = pd.read_csv(io.BytesIO(inputs["prices"]), dtype={"date": str, "ticker": str})
        if not {"date", "ticker", "open", "close", "volume", "value"} <= set(prices):
            raise ValueError("required price columns missing")
        if any(_day(d) != d for d in prices.date.unique()):
            raise ValueError("canonical price dates required")
        weights, diagnostics = self.calculation(prices, self.meta, calendar, day, previous["weights"])
        return {
            "decision_date": day,
            "previous_target_decision_date": previous_day,
            "initial_branch": "EXPLICIT_UNINVESTED_CASH_CANDIDATE" if initial else "PREVIOUS_MONTH_TARGET",
            "reference_execution_date": reference_execution,
            "weights": weights, "diagnostics": diagnostics,
            "generation_input_sha256": dict(expected_input_hashes),
            "metadata_sha256": self.metadata_sha256,
            "producer_source_hashes": {**self.sources, **self.revision_sources},
            **self.revision_metadata,
            "freeze_id": self.freeze["freeze_id"],
            "freeze_manifest_sha256": self.freeze["freeze_manifest_sha256"],
            "execution_contract_sha256": self.freeze["execution_contract_sha256"],
        }

    def calculate(self, **kwargs):
        values = self.calculate_values(**kwargs)
        generated = self.clock()
        # This is only candidate emission time, not an actual producer publication.
        published = self.clock()
        if published < generated:
            raise ValueError("runtime clock moved backward")
        return {
            **values,
            "schema": "q25_inactive_monthly_candidate_v1",
            "classification": CLASSIFICATION,
            "active": False,
            "actual_publication": False,
            "semantics": "UNSCALED_MONTHLY_TARGET_NOT_HOLDINGS",
            "execution_date": None,
            "generated_at": generated.isoformat(),
            "published_at": published.isoformat(),
            "publication_time_basis": "RUNTIME_CANDIDATE_EMISSION_ONLY_NOT_ACTUAL_PUBLICATION",
            "late_for_reference_execution": published
            >= datetime.fromisoformat(values["reference_execution_date"] + "T09:00:00+09:00"),
            "activation_blockers": list(GATES),
            "candidate_source_sha256": _hash(Path(__file__).read_bytes()),
            "historical_receipt_inferred": False,
            "counts_as_live_sample": False,
        }
