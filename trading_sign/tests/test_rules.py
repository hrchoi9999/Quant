import unittest

from trading_sign.config import TimingConfig
from trading_sign.entry_rules import DefaultEntryRule
from trading_sign.exit_rules import DefaultExitRule
from trading_sign.state import TickerState
from trading_sign.types import TimingFeatureSnapshot


class TimingRuleTests(unittest.TestCase):
    def test_entry_rule_allows_clean_trend_and_accel(self) -> None:
        cfg = TimingConfig()
        rule = DefaultEntryRule(config=cfg)
        state = TickerState(ticker="000001")
        snapshot = TimingFeatureSnapshot(
            ticker="000001",
            signal_date="2026-04-02",
            selected_by_upstream=True,
            close_above_ma60=True,
            ma60_above_ma120=True,
            ma60_slope_positive=True,
            market_gate_open=True,
            fund_accel_score=0.8,
            trend_align_score=0.8,
            overheat_score=0.2,
        )

        decision = rule.evaluate(snapshot, state)

        self.assertTrue(decision.allowed)
        self.assertGreaterEqual(decision.score, cfg.entry_min_score)

    def test_exit_rule_requires_persistence(self) -> None:
        cfg = TimingConfig(below_ma60_exit_weeks=2, nonpositive_ma60_slope_exit_weeks=2)
        rule = DefaultExitRule(config=cfg)
        state = TickerState(ticker="000001", in_position=True)
        snapshot = TimingFeatureSnapshot(
            ticker="000001",
            signal_date="2026-04-02",
            selected_by_upstream=True,
            close_above_ma60=False,
            ma60_above_ma120=True,
            ma60_slope_positive=False,
            market_gate_open=True,
        )

        first = rule.evaluate(snapshot, state)
        second = rule.evaluate(snapshot, state)

        self.assertFalse(first.should_exit)
        self.assertTrue(second.should_exit)
        self.assertIn("below_ma60_persistent", second.reasons)


if __name__ == "__main__":
    unittest.main()
