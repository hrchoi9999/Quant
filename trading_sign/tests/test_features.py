import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from trading_sign.features import (
    build_feature_snapshots,
    load_public_model_targets,
    load_tseries_targets,
    TargetSecurity,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _seed_price_db(path: Path) -> None:
    with sqlite3.connect(str(path)) as con:
        con.execute("CREATE TABLE prices_daily (ticker TEXT, date TEXT, close REAL)")
        start = date(2025, 12, 1)
        for day in range(1, 131):
            current = start + timedelta(days=day - 1)
            dt = current.isoformat()
            con.execute("INSERT INTO prices_daily VALUES (?, ?, ?)", ("000001", dt, 100 + day))
            con.execute("INSERT INTO prices_daily VALUES (?, ?, ?)", ("000002", dt, 200 - day * 0.2))


def _seed_fund_db(path: Path) -> None:
    with sqlite3.connect(str(path)) as con:
        con.execute(
            """
            CREATE TABLE s2_fund_scores_monthly (
                date TEXT,
                ticker TEXT,
                revenue_yoy REAL,
                op_income_yoy REAL,
                growth_score REAL,
                valid_fund INTEGER
            )
            """
        )
        rows = [
            ("2025-12-31", "000001", 0.10, 0.15, 0.40, 1),
            ("2026-01-31", "000001", 0.12, 0.16, 0.45, 1),
            ("2026-02-28", "000001", 0.18, 0.20, 0.55, 1),
            ("2026-03-31", "000001", 0.28, 0.30, 0.70, 1),
            ("2025-12-31", "000002", 0.08, 0.10, 0.35, 1),
            ("2026-01-31", "000002", 0.07, 0.09, 0.34, 1),
            ("2026-02-28", "000002", 0.06, 0.08, 0.33, 1),
            ("2026-03-31", "000002", 0.05, 0.07, 0.30, 1),
        ]
        con.executemany("INSERT INTO s2_fund_scores_monthly VALUES (?, ?, ?, ?, ?, ?)", rows)


class FeatureBuilderTests(unittest.TestCase):
    def test_load_public_model_targets_merges_holdings_and_recommendations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            changes_path = Path(tmpdir) / "changes.json"
            _write_json(
                report_path,
                {
                    "reports": [
                        {
                            "service_profile": "growth",
                            "user_model_name": "성장형",
                            "allocation_items": [
                                {"security_code": "000001", "display_name": "Alpha", "asset_group": "stock"},
                                {"security_code": None, "display_name": "Cash", "asset_group": "cash"},
                            ],
                        }
                    ]
                },
            )
            _write_json(
                changes_path,
                {
                    "changes": [
                        {
                            "user_model_name": "성장형",
                            "increase_items": [{"security_code": "000001", "display_name": "Alpha"}],
                        }
                    ]
                },
            )

            targets = load_public_model_targets(report_path=report_path, changes_path=changes_path)

            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].ticker, "000001")
            self.assertTrue(targets[0].is_held)
            self.assertTrue(targets[0].is_recommended)
            self.assertEqual(targets[0].model_code, "GROWTH")

    def test_load_public_model_targets_filters_non_exposed_auto_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            changes_path = Path(tmpdir) / "changes.json"
            _write_json(
                report_path,
                {
                    "reports": [
                        {
                            "service_profile": "stable",
                            "user_model_name": "안정형",
                            "allocation_items": [
                                {"security_code": "000001", "display_name": "Alpha", "asset_group": "stock"},
                            ],
                        },
                        {
                            "service_profile": "auto",
                            "user_model_name": "자동전환형",
                            "allocation_items": [
                                {"security_code": "000002", "display_name": "Beta", "asset_group": "stock"},
                            ],
                        },
                    ]
                },
            )
            _write_json(
                changes_path,
                {
                    "changes": [
                        {
                            "user_model_name": "안정형",
                            "increase_items": [{"security_code": "000001", "display_name": "Alpha"}],
                        },
                        {
                            "user_model_name": "자동전환형",
                            "increase_items": [{"security_code": "000002", "display_name": "Beta"}],
                        },
                    ]
                },
            )

            targets = load_public_model_targets(report_path=report_path, changes_path=changes_path)

            self.assertEqual({target.model_code for target in targets}, {"STABLE"})
            self.assertNotIn("AUTO", {target.model_code for target in targets})

    def test_load_tseries_targets_reads_bucket_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tseries.json"
            _write_json(
                path,
                {
                    "models": [
                        {
                            "model_code": "T-STOCK-V01",
                            "meta": {"service_model_code": "T_STOCK_DISCOVERY", "asset_scope": "stock"},
                            "top_by_bucket": {"confirmed": [{"ticker": "000001", "name": "Alpha"}]},
                        }
                    ]
                },
            )

            targets = load_tseries_targets(tseries_path=path)

            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].model_code, "T_STOCK_DISCOVERY")
            self.assertTrue(targets[0].is_recommended)
            self.assertFalse(targets[0].is_held)

    def test_build_feature_snapshots_generates_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            price_db = Path(tmpdir) / "price.db"
            fund_db = Path(tmpdir) / "fund.db"
            _seed_price_db(price_db)
            _seed_fund_db(fund_db)

            targets = [
                TargetSecurity(
                    ticker="000001",
                    name="Alpha",
                    model_code="GROWTH",
                    service_profile="growth",
                    asset_group="stock",
                    is_recommended=True,
                    is_held=True,
                    source_channel="test",
                ),
                TargetSecurity(
                    ticker="000002",
                    name="Beta",
                    model_code="GROWTH",
                    service_profile="growth",
                    asset_group="stock",
                    is_recommended=True,
                    is_held=False,
                    source_channel="test",
                ),
            ]

            snapshots = build_feature_snapshots(
                targets=targets,
                signal_date="2026-05-10",
                data_asof_date="2026-05-10",
                price_db_path=price_db,
                fund_db_path=fund_db,
            )

            self.assertEqual(len(snapshots), 2)
            alpha = {row.ticker: row for row in snapshots}["000001"]
            self.assertTrue(alpha.close_above_ma60)
            self.assertTrue(alpha.is_currently_held)
            self.assertIsNotNone(alpha.fund_accel_score)
            self.assertIsNotNone(alpha.trend_align_score)


if __name__ == "__main__":
    unittest.main()
