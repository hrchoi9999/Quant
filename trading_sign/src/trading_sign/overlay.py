from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from .config import TimingConfig
from .entry_rules import DefaultEntryRule
from .exit_rules import DefaultExitRule
from .model_profiles import ModelTimingProfile, default_profile, get_model_profile
from .signal_history import SignalHistoryStore
from .state import PortfolioState, TickerState
from .types import EntryDecision, ExitDecision, TimingFeatureSnapshot, TimingSignalRecord


STATE_ENTRY_READY = "매수"
STATE_HOLD = "보유"
STATE_WARNING = "주의"
STATE_EXIT = "매도"
STATE_COOLDOWN = "매수 대기"

TAG_REASON_TEXT = {
    "trend_and_state_ok": "장기 추세와 상태가 안정적으로 유지되고 있습니다",
    "entry_ready": "장기 추세와 가속 조건이 함께 확인됐습니다",
    "cooldown_active": "최근 이탈 이후 매수 대기 구간입니다",
    "below_ma60_warning": "종가가 60일선 아래에 있어 추세가 약해졌습니다",
    "ma60_slope_warning": "60일선 기울기가 둔화되거나 약세로 돌아섰습니다",
    "market_gate_warning": "시장 환경이 우호적이지 않아 보수적 해석이 필요합니다",
    "below_ma60_persistent": "60일선 하회가 누적돼 추세 훼손 신호가 커졌습니다",
    "ma60_slope_nonpositive_persistent": "60일선 기울기 약화가 이어져 추세 유지 신뢰도가 낮아졌습니다",
    "market_gate_closed_with_trend_break": "시장 게이트 약화와 종목 추세 훼손이 동시에 나타났습니다",
    "not_selected_by_upstream": "상위 모델의 현재 추천 목록에는 포함되지 않았습니다",
    "close_below_ma60": "종가가 60일선 위에 올라서지 못했습니다",
    "ma60_not_above_ma120": "중기 추세가 장기 추세 위로 정렬되지 않았습니다",
    "ma60_slope_not_positive": "60일선 기울기가 아직 상승 전환되지 않았습니다",
    "market_gate_closed": "시장 게이트가 닫혀 신규 진입을 보수적으로 봐야 합니다",
    "weak_fund_accel": "실적 가속 신호가 아직 충분히 강하지 않습니다",
    "overheated": "단기 과열 부담이 커 바로 진입하기엔 부담이 있습니다",
    "entry_score_below_threshold": "종합 진입 점수가 기준선에 못 미쳤습니다",
    "state_warning": "추가 확인이 필요한 경고 신호가 있습니다",
}


@dataclass
class TimingOverlay:
    """Thread-local V1 timing overlay orchestrator.

    This class is intentionally independent from the main Quant backtest engine.
    It manages ticker state and delegates stock-level decisions to entry/exit rules.
    """

    config: TimingConfig = field(default_factory=TimingConfig)
    portfolio_state: PortfolioState = field(default_factory=PortfolioState)
    ticker_states: Dict[str, TickerState] = field(default_factory=dict)
    model_profile: ModelTimingProfile = field(default_factory=default_profile)
    history_store: Optional[SignalHistoryStore] = None

    def __post_init__(self) -> None:
        self.config = self.model_profile.timing_config
        self.entry_rule = DefaultEntryRule(config=self.config)
        self.exit_rule = DefaultExitRule(config=self.config)

    @classmethod
    def for_model(
        cls,
        model_code: str,
        *,
        history_store: Optional[SignalHistoryStore] = None,
    ) -> "TimingOverlay":
        profile = get_model_profile(model_code)
        return cls(model_profile=profile, history_store=history_store)

    def get_state(self, ticker: str) -> TickerState:
        if ticker not in self.ticker_states:
            self.ticker_states[ticker] = TickerState(ticker=ticker)
        return self.ticker_states[ticker]

    def evaluate_entries(self, snapshots: Iterable[TimingFeatureSnapshot]) -> List[EntryDecision]:
        decisions: List[EntryDecision] = []
        for snapshot in snapshots:
            state = self.get_state(snapshot.ticker)
            decisions.append(self.entry_rule.evaluate(snapshot, state))
        return decisions

    def evaluate_exits(self, snapshots: Iterable[TimingFeatureSnapshot]) -> List[ExitDecision]:
        decisions: List[ExitDecision] = []
        for snapshot in snapshots:
            state = self.get_state(snapshot.ticker)
            decisions.append(self.exit_rule.evaluate(snapshot, state))
        return decisions

    def advance_rebalance(self, rebalance_date: str, market_gate_open: bool) -> None:
        self.portfolio_state.rebalance_date = rebalance_date
        self.portfolio_state.market_gate_open = market_gate_open
        for state in self.ticker_states.values():
            state.advance_rebalance()

    def mark_entry(
        self,
        ticker: str,
        *,
        signal_date: str,
        exec_date: str | None = None,
        entry_price: float | None = None,
    ) -> None:
        self.get_state(ticker).register_entry(
            signal_date=signal_date,
            exec_date=exec_date,
            entry_price=entry_price,
        )

    def mark_exit(self, ticker: str, *, signal_date: str, reason: str) -> None:
        self.get_state(ticker).register_exit(
            signal_date=signal_date,
            reason=reason,
            cooldown_weeks=self.config.cooldown_weeks_after_exit,
        )

    def build_daily_signal_records(
        self,
        *,
        model_code: str,
        snapshots: Iterable[TimingFeatureSnapshot],
        persist: bool = False,
    ) -> List[TimingSignalRecord]:
        records: List[TimingSignalRecord] = []
        normalized_model_code = str(model_code).strip().upper()
        for snapshot in snapshots:
            state = self.get_state(snapshot.ticker)
            if snapshot.is_currently_held and not state.in_position:
                # Bootstrap current portfolio names as active holdings when
                # the overlay is evaluating a live daily snapshot for the first time.
                state.in_position = True
            entry_decision = self.entry_rule.evaluate(snapshot, state)
            exit_decision = self.exit_rule.evaluate(snapshot, state)
            current_state, reason_tags, exit_risk_score = self._resolve_current_state(
                snapshot=snapshot,
                state=state,
                entry_decision=entry_decision,
                exit_decision=exit_decision,
            )
            latest_state_change_date = self._latest_state_change_date(
                ticker=snapshot.ticker,
                model_code=normalized_model_code,
                signal_date=snapshot.signal_date,
                current_state=current_state,
            )
            records.append(
                TimingSignalRecord(
                    signal_date=snapshot.signal_date,
                    data_asof_date=snapshot.data_asof_date or snapshot.signal_date,
                    ticker=snapshot.ticker,
                    security_name=snapshot.security_name or snapshot.ticker,
                    model_code=normalized_model_code,
                    current_state=current_state,
                    latest_state_change_date=latest_state_change_date,
                    reason_tags=reason_tags,
                    reason_summary=self._reason_summary(
                        current_state=current_state,
                        reason_tags=reason_tags,
                        is_recommended=bool(snapshot.selected_by_upstream),
                        is_held=bool(snapshot.is_currently_held or state.in_position),
                    ),
                    entry_score=entry_decision.score,
                    exit_risk_score=exit_risk_score,
                    is_recommended=bool(snapshot.selected_by_upstream),
                    is_held=bool(snapshot.is_currently_held or state.in_position),
                )
            )
        if persist and self.history_store is not None:
            self.history_store.upsert_records(records)
        return records

    def _latest_state_change_date(
        self,
        *,
        ticker: str,
        model_code: str,
        signal_date: str,
        current_state: str,
    ) -> str:
        if self.history_store is None:
            return signal_date
        previous = self.history_store.load_latest_record(
            ticker=ticker,
            model_code=model_code,
            before_signal_date=signal_date,
        )
        if previous is None:
            return signal_date
        if previous.current_state == current_state:
            return previous.latest_state_change_date or previous.signal_date
        return signal_date

    def _resolve_current_state(
        self,
        *,
        snapshot: TimingFeatureSnapshot,
        state: TickerState,
        entry_decision: EntryDecision,
        exit_decision: ExitDecision,
    ) -> tuple[str, List[str], Optional[float]]:
        if state.in_position:
            exit_risk_score = self._exit_risk_score(state)
            if exit_decision.should_exit:
                return STATE_EXIT, list(exit_decision.reasons), exit_risk_score
            if state.below_ma60_streak > 0 or state.nonpositive_ma60_slope_streak > 0:
                warning_reasons = self._warning_reasons(snapshot=snapshot, state=state)
                return STATE_WARNING, warning_reasons, exit_risk_score
            return STATE_HOLD, ["trend_and_state_ok"], exit_risk_score

        if state.cooldown_weeks_left > 0:
            return STATE_COOLDOWN, ["cooldown_active"], None
        if entry_decision.allowed:
            return STATE_ENTRY_READY, ["entry_ready"], None
        return STATE_WARNING, list(entry_decision.reasons), None

    def _exit_risk_score(self, state: TickerState) -> float:
        raw = 0.0
        raw += min(state.below_ma60_streak, self.config.below_ma60_exit_weeks) / max(
            self.config.below_ma60_exit_weeks, 1
        )
        raw += min(
            state.nonpositive_ma60_slope_streak,
            self.config.nonpositive_ma60_slope_exit_weeks,
        ) / max(self.config.nonpositive_ma60_slope_exit_weeks, 1)
        return min(raw / 2.0, 1.0)

    def _warning_reasons(self, *, snapshot: TimingFeatureSnapshot, state: TickerState) -> List[str]:
        reasons: List[str] = []
        if state.below_ma60_streak > 0:
            reasons.append("below_ma60_warning")
        if state.nonpositive_ma60_slope_streak > 0:
            reasons.append("ma60_slope_warning")
        if not snapshot.market_gate_open:
            reasons.append("market_gate_warning")
        return reasons or ["state_warning"]

    def _reason_summary(
        self,
        *,
        current_state: str,
        reason_tags: List[str],
        is_recommended: bool,
        is_held: bool,
    ) -> str:
        reason_texts = [TAG_REASON_TEXT.get(tag, tag.replace("_", " ")) for tag in reason_tags[:2]]

        if current_state == STATE_HOLD:
            return "중장기 추세가 유지돼 보유 기준을 충족하고 있습니다."
        if current_state == STATE_ENTRY_READY:
            return "추천 후보 중 장기 추세와 가속 조건이 확인돼 매수 기준을 충족했습니다."
        if current_state == STATE_COOLDOWN:
            return "최근 이탈 이후 매수 대기 구간이라 조금 더 확인이 필요합니다."
        if current_state == STATE_EXIT:
            if reason_texts:
                return f"추세 훼손 신호가 누적돼 매도 기준에 해당합니다. {reason_texts[0]}."
            return "추세 훼손 신호가 누적돼 매도 기준에 해당합니다."

        role_prefix = "보유 종목은" if is_held else "추천 후보는" if is_recommended else "현재 종목은"
        if reason_texts:
            joined = " ".join(f"{text}." for text in reason_texts)
            return f"{role_prefix} 추가 확인이 필요한 경고 상태입니다. {joined}"
        return f"{role_prefix} 추가 확인이 필요한 경고 상태입니다."
