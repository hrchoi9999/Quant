from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(r"D:\Quant")
PAYLOAD_PATH = ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate admin new entry tracker payload.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    if not PAYLOAD_PATH.exists():
        raise SystemExit(f"missing payload: {PAYLOAD_PATH}")
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    if payload.get("as_of_date") != args.asof:
        raise SystemExit(f"as_of_date mismatch: expected {args.asof}, got {payload.get('as_of_date')}")
    for key in ("user_models", "internal_models", "tseries_models"):
        if key not in payload or not isinstance(payload[key], list):
            raise SystemExit(f"missing list payload: {key}")
    print(
        json.dumps(
            {
                "asof": payload.get("as_of_date"),
                "user_rows": len(payload.get("user_models", [])),
                "internal_rows": len(payload.get("internal_models", [])),
                "tseries_rows": len(payload.get("tseries_models", [])),
                "validated_file": str(PAYLOAD_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
