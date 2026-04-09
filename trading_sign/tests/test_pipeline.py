import tempfile
import unittest
from pathlib import Path

from trading_sign.pipeline import run_daily_signal_generation
from trading_sign.signal_history import SignalHistoryStore
from trading_sign.types import TimingFeatureSnapshot


class DailyPipelineTests(unittest.TestCase):
    def test_run_daily_signal_generation_returns_counts_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trading_sign.db"
            result = run_daily_signal_generation(
                model_code="S2",
                signal_date="2026-04-02",
                db_path=db_path,
                snapshots=[
                    TimingFeatureSnapshot(
                        ticker="000001",
                        signal_date="2026-04-02",
                        data_asof_date="2026-04-01",
                        selected_by_upstream=True,
                        close_above_ma60=True,
                        ma60_above_ma120=True,
                        ma60_slope_positive=True,
                        market_gate_open=True,
                        fund_accel_score=0.80,
                        trend_align_score=0.75,
                        overheat_score=0.20,
                    ),
                    TimingFeatureSnapshot(
                        ticker="000002",
                        signal_date="2026-04-02",
                        data_asof_date="2026-04-01",
                        selected_by_upstream=True,
                        close_above_ma60=False,
                        ma60_above_ma120=False,
                        ma60_slope_positive=False,
                        market_gate_open=True,
                        fund_accel_score=0.30,
                        trend_align_score=0.20,
                        overheat_score=0.40,
                    ),
                ],
            )

            self.assertEqual(result.record_count, 2)
            self.assertEqual(result.state_counts.get("매수"), 1)
            self.assertEqual(result.state_counts.get("주의"), 1)

            store = SignalHistoryStore(db_path)
            stored = store.load_by_date("2026-04-02", model_code="S2")
            self.assertEqual(len(stored), 2)


if __name__ == "__main__":
    unittest.main()
