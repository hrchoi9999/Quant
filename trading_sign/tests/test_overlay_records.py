import tempfile
import unittest
from pathlib import Path

from trading_sign.overlay import TimingOverlay
from trading_sign.signal_history import SignalHistoryStore
from trading_sign.types import TimingFeatureSnapshot


class TimingOverlayRecordTests(unittest.TestCase):
    def test_build_daily_signal_records_persists_buy_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SignalHistoryStore(Path(tmpdir) / "trading_sign.db")
            overlay = TimingOverlay.for_model("S2", history_store=store)
            snapshots = [
                TimingFeatureSnapshot(
                    ticker="000001",
                    signal_date="2026-04-02",
                    data_asof_date="2026-04-01",
                    selected_by_upstream=True,
                    close_above_ma60=True,
                    ma60_above_ma120=True,
                    ma60_slope_positive=True,
                    market_gate_open=True,
                    fund_accel_score=0.85,
                    trend_align_score=0.80,
                    overheat_score=0.10,
                )
            ]

            records = overlay.build_daily_signal_records(
                model_code="S2",
                snapshots=snapshots,
                persist=True,
            )

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].current_state, "매수")
            self.assertIn("매수 기준", records[0].reason_summary)

            stored = store.load_by_date("2026-04-02", model_code="S2")
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].current_state, "매수")

    def test_held_position_with_persistent_break_becomes_exit_state(self) -> None:
        overlay = TimingOverlay.for_model("S3")
        overlay.mark_entry("000001", signal_date="2026-03-20")
        snapshots = [
            TimingFeatureSnapshot(
                ticker="000001",
                signal_date="2026-04-02",
                data_asof_date="2026-04-01",
                selected_by_upstream=True,
                close_above_ma60=False,
                ma60_above_ma120=True,
                ma60_slope_positive=False,
                market_gate_open=True,
                fund_accel_score=0.70,
                trend_align_score=0.40,
                overheat_score=0.20,
            ),
            TimingFeatureSnapshot(
                ticker="000001",
                signal_date="2026-04-03",
                data_asof_date="2026-04-02",
                selected_by_upstream=True,
                close_above_ma60=False,
                ma60_above_ma120=True,
                ma60_slope_positive=False,
                market_gate_open=True,
                fund_accel_score=0.70,
                trend_align_score=0.40,
                overheat_score=0.20,
            ),
        ]

        first = overlay.build_daily_signal_records(model_code="S3", snapshots=[snapshots[0]])
        second = overlay.build_daily_signal_records(model_code="S3", snapshots=[snapshots[1]])

        self.assertEqual(first[0].current_state, "주의")
        self.assertEqual(second[0].current_state, "매도")
        self.assertIn("경고 상태", first[0].reason_summary)
        self.assertIn("매도 기준에 해당합니다", second[0].reason_summary)
