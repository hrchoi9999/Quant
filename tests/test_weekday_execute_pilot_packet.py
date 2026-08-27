from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("prepare_weekday_execute_pilot_packet", HARNESS_DIR / "prepare_weekday_execute_pilot_packet.py")
assert SPEC is not None
PACKET = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PACKET)


def test_weekday_packet_keeps_weekday_only_scope() -> None:
    payload = PACKET.build_packet("2026-06-27", "test_weekday_packet")

    assert payload["cycle_type"] == "weekday"
    assert payload["execute_candidates"] == []
    assert payload["deferred_stages"] == [
        "WD02_MARKET_COLLECT",
        "WD03_MARKET_ANALYSIS",
        "WD04_QUANT_REAR",
        "WD05_PORTFOLIO_ANALYSIS",
        "WD06_PRE_GCS_PUBLISH",
    ]
    assert payload["safety"]["weekday_weekend_combined_run_forbidden"] is True
