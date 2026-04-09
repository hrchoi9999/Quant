import tempfile
import unittest
from pathlib import Path

from trading_sign.signal_history import SignalHistoryStore
from trading_sign.types import TimingSignalRecord


class SignalHistoryStoreTests(unittest.TestCase):
    def test_upsert_and_load_signal_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trading_sign.db"
            store = SignalHistoryStore(db_path)
            record = TimingSignalRecord(
                signal_date="2026-04-02",
                data_asof_date="2026-04-01",
                ticker="000001",
                model_code="S2",
                current_state="보유",
                security_name="테스트종목",
                latest_state_change_date="2026-03-28",
                reason_tags=["trend_ok", "accel_ok"],
                reason_summary="장기 추세와 실적 가속이 유지되었습니다.",
                entry_score=0.74,
                exit_risk_score=0.12,
                is_recommended=True,
                is_held=True,
            )

            store.upsert_records([record])
            loaded = store.load_by_date("2026-04-02", model_code="S2")

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].ticker, "000001")
            self.assertEqual(loaded[0].security_name, "테스트종목")
            self.assertEqual(loaded[0].latest_state_change_date, "2026-03-28")
            self.assertEqual(loaded[0].reason_tags, ["trend_ok", "accel_ok"])
            self.assertTrue(loaded[0].is_held)


if __name__ == "__main__":
    unittest.main()
