from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\Quant")
CURRENT_DIR = ROOT / "service_platform" / "web" / "public_data" / "current"


def _load_json(name: str, default: Any) -> Any:
    path = CURRENT_DIR / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class SnapshotProvider:
    def load_manifest(self) -> dict[str, Any]:
        return _load_json("publish_manifest.json", {})

    def load_catalog(self) -> dict[str, Any]:
        return _load_json("user_model_catalog.json", {"models": []})

    def load_today_payload(self) -> dict[str, Any]:
        payload = _load_json("user_model_snapshot_report.json", None)
        if payload is not None:
            return payload
        return _load_json("user_recommendation_report.json", {"reports": []})

    def load_performance_payload(self) -> dict[str, Any]:
        return _load_json("user_performance_summary.json", {"models": []})

    def load_changes_payload(self) -> dict[str, Any]:
        return _load_json("user_recent_changes.json", {"changes": []})

    def load_home_payload(self) -> dict[str, Any]:
        return {
            "catalog": self.load_catalog(),
            "performance": self.load_performance_payload(),
            "manifest": self.load_manifest(),
        }

    def load_recommendation_by_profile(self, service_profile: str) -> dict[str, Any]:
        payload = self.load_today_payload()
        reports = payload.get("reports", [])
        for report in reports:
            if report.get("service_profile") == service_profile:
                return {
                    "as_of_date": payload.get("as_of_date"),
                    "generated_at": payload.get("generated_at"),
                    "current_market_regime": payload.get("current_market_regime"),
                    "report": report,
                }
        return {
            "as_of_date": payload.get("as_of_date"),
            "generated_at": payload.get("generated_at"),
            "current_market_regime": payload.get("current_market_regime"),
            "report": None,
        }
