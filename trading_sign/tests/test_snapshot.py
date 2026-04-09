import json
import tempfile
import unittest
from pathlib import Path

from trading_sign.pipeline import DailySignalRunResult
from trading_sign.snapshot import write_current_snapshots
from trading_sign.types import TimingSignalRecord


class SnapshotTests(unittest.TestCase):
    def test_write_current_snapshots_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "current"
            results = [
                DailySignalRunResult(
                    model_code="STABLE",
                    signal_date="2026-04-02",
                    record_count=1,
                    state_counts={"매수": 1},
                    records=[
                        TimingSignalRecord(
                            signal_date="2026-04-02",
                            data_asof_date="2026-04-01",
                            ticker="000001",
                            security_name="알파",
                            model_code="STABLE",
                            current_state="매수",
                            latest_state_change_date="2026-04-02",
                            is_recommended=True,
                        )
                    ],
                )
            ]

            write_current_snapshots(output_dir, results)

            overview = json.loads((output_dir / "tradingsign_overview.json").read_text(encoding="utf-8"))
            detail = json.loads((output_dir / "tradingsign_model_detail.json").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "tradingsign_manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(overview["summary"]["signal_count"], 1)
            self.assertEqual(overview["summary"]["state_order"][0], "매수")
            self.assertEqual(detail["models"][0]["ui_block"]["title"], "전일 종가 기준 일간 신호")
            self.assertEqual(detail["models"][0]["ui_block"]["sections"][0]["section_key"], "recommended")
            self.assertEqual(
                detail["models"][0]["ui_block"]["sections"][0]["signals"][0]["security_name"],
                "알파",
            )
            self.assertEqual(manifest["files"][0], "tradingsign_overview.json")

    def test_write_current_snapshots_rejects_auto_in_public_model_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "current"
            results = [
                DailySignalRunResult(
                    model_code="AUTO",
                    signal_date="2026-04-02",
                    record_count=1,
                    state_counts={"보유": 1},
                    records=[
                        TimingSignalRecord(
                            signal_date="2026-04-02",
                            data_asof_date="2026-04-01",
                            ticker="000001",
                            security_name="알파",
                            model_code="AUTO",
                            current_state="보유",
                            latest_state_change_date="2026-04-02",
                            is_held=True,
                        )
                    ],
                )
            ]

            with self.assertRaisesRegex(ValueError, "AUTO"):
                write_current_snapshots(output_dir, results)

    def test_public_model_set_matches_three_public_models_plus_two_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "current"
            results = []
            for model_code in (
                "STABLE",
                "BALANCED",
                "GROWTH",
                "T_STOCK_DISCOVERY",
                "T_ETF_DISCOVERY",
            ):
                results.append(
                    DailySignalRunResult(
                        model_code=model_code,
                        signal_date="2026-04-02",
                        record_count=1,
                        state_counts={"주의": 1},
                        records=[
                            TimingSignalRecord(
                                signal_date="2026-04-02",
                                data_asof_date="2026-04-01",
                                ticker="000001",
                                security_name="알파",
                                model_code=model_code,
                                current_state="주의",
                                latest_state_change_date="2026-04-02",
                                is_recommended=True,
                            )
                        ],
                    )
                )

            write_current_snapshots(output_dir, results)
            overview = json.loads((output_dir / "tradingsign_overview.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {row["model_code"] for row in overview["models"]},
                {"STABLE", "BALANCED", "GROWTH", "T_STOCK_DISCOVERY", "T_ETF_DISCOVERY"},
            )
            self.assertNotIn("AUTO", {row["model_code"] for row in overview["models"]})


if __name__ == "__main__":
    unittest.main()
