from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    canonical_sha256,
)
from src.quant2.evaluation.standard_model_export import P2StandardPeriodSource

P2_ETF_LEGACY_LOADER_POLICY_VERSION = "quant2.p2_etf_legacy_loader.v1"
P2_ETF_LEGACY_MODEL_CODES = ("S4", "S5", "S6")


class P2EtfLegacyLoaderStatus(str, Enum):
    DRAFT_READY = "DRAFT_READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class P2EtfLegacyLoaderPolicy:
    supported_model_codes: tuple[str, ...] = P2_ETF_LEGACY_MODEL_CODES
    benchmark_code: str = "KOSPI"
    exclude_execution_day_return: bool = True
    version: str = P2_ETF_LEGACY_LOADER_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.supported_model_codes != P2_ETF_LEGACY_MODEL_CODES:
            raise ContractValidationError("ETF legacy loader model scope is frozen")
        if self.benchmark_code != "KOSPI":
            raise ContractValidationError("ETF legacy loader benchmark is frozen")
        if not self.exclude_execution_day_return:
            raise ContractValidationError("execution-day legacy return must remain excluded")
        if self.version != P2_ETF_LEGACY_LOADER_POLICY_VERSION:
            raise ContractValidationError("ETF legacy loader policy version is frozen")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class P2LegacyEquityReturn:
    trading_date: date
    net_return: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.net_return) or self.net_return < -1.0:
            raise ContractValidationError("legacy equity return is invalid")


@dataclass(frozen=True)
class P2LegacyDecisionEvent:
    decision_date: date
    execution_date: date

    def __post_init__(self) -> None:
        if self.execution_date < self.decision_date:
            raise ContractValidationError("legacy ETF execution cannot precede decision")


@dataclass(frozen=True)
class P2LegacyTradeComponent:
    decision_date: date
    execution_date: date
    turnover_component: float

    def __post_init__(self) -> None:
        if self.execution_date <= self.decision_date:
            raise ContractValidationError("legacy ETF execution must follow decision date")
        if not math.isfinite(self.turnover_component) or self.turnover_component < 0.0:
            raise ContractValidationError("turnover_component must be non-negative")


@dataclass(frozen=True)
class P2BenchmarkClose:
    trading_date: date
    close: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.close) or self.close <= 0.0:
            raise ContractValidationError("benchmark close must be positive")


@dataclass(frozen=True)
class P2EtfLegacyPeriodDraft:
    decision_date: date
    execution_date: date
    return_period_end_date: date
    gross_return: float | None
    benchmark_return: float | None
    turnover_one_way: float | None
    coverage_ratio: float
    available: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.decision_date <= self.execution_date <= self.return_period_end_date:
            raise ContractValidationError("ETF legacy draft dates are invalid")
        if not math.isfinite(self.coverage_ratio) or not 0.0 <= self.coverage_ratio <= 1.0:
            raise ContractValidationError("ETF legacy coverage_ratio is invalid")
        values = (self.gross_return, self.benchmark_return, self.turnover_one_way)
        if self.available:
            if self.execution_date <= self.decision_date:
                raise ContractValidationError(
                    "available ETF legacy draft requires next-session execution"
                )
            if any(value is None for value in values):
                raise ContractValidationError("available ETF legacy draft requires values")
            if self.reason_codes:
                raise ContractValidationError("available ETF legacy draft cannot have reasons")
            if self.coverage_ratio <= 0.0:
                raise ContractValidationError("available ETF legacy draft requires coverage")
        else:
            if any(value is not None for value in values):
                raise ContractValidationError("blocked ETF legacy draft values must remain null")
            if not self.reason_codes:
                raise ContractValidationError("blocked ETF legacy draft requires reasons")


@dataclass(frozen=True)
class P2EtfLegacyLoadResult:
    model_code: str
    drafts: tuple[P2EtfLegacyPeriodDraft, ...]
    terminal_date: date
    source_data_hash: str
    status: P2EtfLegacyLoaderStatus
    periods_ready: bool
    benchmark_code: str
    operational_authorization: bool
    blocked_reason_codes: tuple[str, ...]
    policy_version: str
    policy_hash: str
    result_hash: str

    def __post_init__(self) -> None:
        if self.model_code not in P2_ETF_LEGACY_MODEL_CODES:
            raise ContractValidationError("unsupported ETF legacy loader model")
        if not self.drafts:
            raise ContractValidationError("ETF legacy loader requires period drafts")
        if tuple(item.decision_date for item in self.drafts) != tuple(
            sorted(item.decision_date for item in self.drafts)
        ):
            raise ContractValidationError("ETF legacy drafts must be decision-date sorted")
        expected_ready = all(item.available for item in self.drafts)
        if self.periods_ready is not expected_ready:
            raise ContractValidationError("ETF legacy loader readiness is inconsistent")
        expected_status = (
            P2EtfLegacyLoaderStatus.DRAFT_READY
            if expected_ready
            else P2EtfLegacyLoaderStatus.BLOCKED
        )
        if self.status is not expected_status:
            raise ContractValidationError("ETF legacy loader status is inconsistent")
        if self.operational_authorization:
            raise ContractValidationError("ETF legacy loader cannot grant operation")
        if not self.blocked_reason_codes:
            raise ContractValidationError("ETF legacy loader requires downstream blockers")
        if len(self.blocked_reason_codes) != len(set(self.blocked_reason_codes)):
            raise ContractValidationError("ETF legacy loader blockers must be unique")
        policy = P2EtfLegacyLoaderPolicy()
        if (
            self.benchmark_code != policy.benchmark_code
            or self.policy_version != policy.version
            or self.policy_hash != policy.policy_hash()
        ):
            raise ContractValidationError("ETF legacy loader policy metadata is invalid")
        _require_hash(self.source_data_hash, "source_data_hash")
        _require_hash(self.result_hash, "result_hash")
        payload = asdict(self)
        payload.pop("result_hash")
        if self.result_hash != canonical_sha256(payload):
            raise ContractValidationError("result_hash does not match ETF legacy load")


@dataclass(frozen=True)
class P2EtfPeriodChronology:
    decision_date: date
    observation_date: date
    published_at: datetime
    available_at: datetime
    ingested_at: datetime
    decision_at: datetime
    execution_at: datetime
    outcome_available_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "published_at",
            "available_at",
            "ingested_at",
            "decision_at",
            "execution_at",
            "outcome_available_at",
        ):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ContractValidationError(f"{field_name} must be timezone-aware")
        if self.decision_at.date() != self.decision_date:
            raise ContractValidationError("chronology decision date is inconsistent")


def _require_hash(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789ABCDEF" for character in value
    ):
        raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")


def _compound(values: tuple[float, ...]) -> float:
    compounded = 1.0
    for value in values:
        compounded *= 1.0 + value
    return round(compounded - 1.0, 12)


def build_etf_legacy_period_drafts(
    *,
    model_code: str,
    equity_returns: tuple[P2LegacyEquityReturn, ...],
    decision_events: tuple[P2LegacyDecisionEvent, ...],
    trade_components: tuple[P2LegacyTradeComponent, ...],
    benchmark_closes: tuple[P2BenchmarkClose, ...],
    terminal_date: date,
    policy: P2EtfLegacyLoaderPolicy | None = None,
) -> P2EtfLegacyLoadResult:
    applied_policy = policy or P2EtfLegacyLoaderPolicy()
    if model_code not in applied_policy.supported_model_codes:
        raise ContractValidationError("unsupported ETF legacy model")
    if not equity_returns or not decision_events:
        raise ContractValidationError("ETF legacy loader requires equity and decisions")
    equity_by_date = {item.trading_date: item.net_return for item in equity_returns}
    if len(equity_by_date) != len(equity_returns):
        raise ContractValidationError("legacy equity dates must be unique")
    benchmark_by_date = {item.trading_date: item.close for item in benchmark_closes}
    if len(benchmark_by_date) != len(benchmark_closes):
        raise ContractValidationError("benchmark close dates must be unique")
    grouped_trades: dict[date, list[P2LegacyTradeComponent]] = {}
    for item in trade_components:
        grouped_trades.setdefault(item.decision_date, []).append(item)
    event_by_decision = {item.decision_date: item for item in decision_events}
    if len(event_by_decision) != len(decision_events):
        raise ContractValidationError("legacy ETF decision dates must be unique")
    if not set(grouped_trades).issubset(event_by_decision):
        raise ContractValidationError("trade components require a matching decision event")
    decisions = tuple(sorted(event_by_decision))
    if terminal_date < decisions[-1]:
        raise ContractValidationError("terminal_date cannot precede last decision")
    drafts: list[P2EtfLegacyPeriodDraft] = []
    for index, decision_date in enumerate(decisions):
        event = event_by_decision[decision_date]
        components = grouped_trades.get(decision_date, [])
        if any(item.execution_date != event.execution_date for item in components):
            raise ContractValidationError("trade execution conflicts with decision event")
        execution_date = event.execution_date
        period_end = decisions[index + 1] if index + 1 < len(decisions) else terminal_date
        if execution_date > period_end:
            raise ContractValidationError("execution_date cannot exceed period end")
        period_dates = tuple(
            sorted(
                trading_date
                for trading_date in equity_by_date
                if execution_date < trading_date <= period_end
            )
        )
        reasons: set[str] = set()
        if execution_date <= decision_date:
            reasons.add("NEXT_TRADABLE_EXECUTION_UNAVAILABLE")
        if not period_dates:
            reasons.add("POST_EXECUTION_EQUITY_PERIOD_UNAVAILABLE")
        benchmark_start = benchmark_by_date.get(execution_date)
        benchmark_end = benchmark_by_date.get(period_end)
        if benchmark_start is None or benchmark_end is None:
            reasons.add("KOSPI_BENCHMARK_PERIOD_UNAVAILABLE")
        if reasons:
            drafts.append(
                P2EtfLegacyPeriodDraft(
                    decision_date=decision_date,
                    execution_date=execution_date,
                    return_period_end_date=period_end,
                    gross_return=None,
                    benchmark_return=None,
                    turnover_one_way=None,
                    coverage_ratio=0.0,
                    available=False,
                    reason_codes=tuple(sorted(reasons)),
                )
            )
            continue
        gross_return = _compound(tuple(equity_by_date[item] for item in period_dates))
        benchmark_return = round(float(benchmark_end) / float(benchmark_start) - 1.0, 12)
        turnover = round(sum(item.turnover_component for item in components), 12)
        drafts.append(
            P2EtfLegacyPeriodDraft(
                decision_date=decision_date,
                execution_date=execution_date,
                return_period_end_date=period_end,
                gross_return=gross_return,
                benchmark_return=benchmark_return,
                turnover_one_way=turnover,
                coverage_ratio=1.0,
                available=True,
                reason_codes=(),
            )
        )
    draft_tuple = tuple(drafts)
    ready = all(item.available for item in draft_tuple)
    blocked_reasons = [
        "PIT_CHRONOLOGY_NOT_MATERIALIZED",
        "STANDARD_EXPORT_NOT_RUN",
        "REAL_DATA_EVALUATION_NOT_RUN",
        "OPERATIONAL_POLICY_NOT_AUTHORIZED",
    ]
    if not ready:
        blocked_reasons.append("LEGACY_PERIOD_INPUTS_INCOMPLETE")
    source_data_hash = canonical_sha256(
        {
            "model_code": model_code,
            "equity_returns": equity_returns,
            "decision_events": decision_events,
            "trade_components": trade_components,
            "benchmark_closes": benchmark_closes,
            "terminal_date": terminal_date,
        }
    )
    payload = {
        "model_code": model_code,
        "drafts": draft_tuple,
        "terminal_date": terminal_date,
        "source_data_hash": source_data_hash,
        "status": (
            P2EtfLegacyLoaderStatus.DRAFT_READY
            if ready
            else P2EtfLegacyLoaderStatus.BLOCKED
        ),
        "periods_ready": ready,
        "benchmark_code": applied_policy.benchmark_code,
        "operational_authorization": False,
        "blocked_reason_codes": tuple(blocked_reasons),
        "policy_version": applied_policy.version,
        "policy_hash": applied_policy.policy_hash(),
    }
    return P2EtfLegacyLoadResult(
        **payload,
        result_hash=canonical_sha256(payload),
    )


def materialize_standard_period_sources(
    result: P2EtfLegacyLoadResult,
    chronologies: tuple[P2EtfPeriodChronology, ...],
) -> tuple[P2StandardPeriodSource, ...]:
    chronology_by_decision = {item.decision_date: item for item in chronologies}
    if len(chronology_by_decision) != len(chronologies):
        raise ContractValidationError("ETF period chronology decisions must be unique")
    if set(chronology_by_decision) != {item.decision_date for item in result.drafts}:
        raise ContractValidationError("ETF period chronology coverage is incomplete")
    periods: list[P2StandardPeriodSource] = []
    for draft in result.drafts:
        chronology = chronology_by_decision[draft.decision_date]
        if chronology.execution_at.date() != draft.execution_date:
            raise ContractValidationError("chronology execution date conflicts with draft")
        if chronology.outcome_available_at.date() < draft.return_period_end_date:
            raise ContractValidationError("chronology outcome precedes draft period end")
        periods.append(
            P2StandardPeriodSource(
                observation_date=chronology.observation_date,
                published_at=chronology.published_at,
                available_at=chronology.available_at,
                ingested_at=chronology.ingested_at,
                decision_at=chronology.decision_at,
                execution_at=chronology.execution_at,
                effective_trade_date=draft.execution_date,
                return_period_end_date=draft.return_period_end_date,
                outcome_available_at=chronology.outcome_available_at,
                source_return=draft.gross_return,
                benchmark_return=draft.benchmark_return,
                turnover_one_way=draft.turnover_one_way,
                coverage_ratio=draft.coverage_ratio,
                available=draft.available,
                reason_codes=draft.reason_codes,
            )
        )
    return tuple(periods)
