from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(r"D:\Quant")
TRADING_SIGN_CURRENT_DIR = PROJECT_ROOT / r"trading_sign\service_platform\web\public_data\current"
REQUIRED_FILES = [
    "tradingsign_overview.json",
    "tradingsign_model_detail.json",
    "tradingsign_manifest.json",
]


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid json: {path} ({exc})") from exc


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate trading_sign current snapshot files.")
    ap.add_argument("--asof", required=True, help="Expected signal/current date (YYYY-MM-DD)")
    args = ap.parse_args()

    expected_asof = str(args.asof)
    missing = [name for name in REQUIRED_FILES if not (TRADING_SIGN_CURRENT_DIR / name).exists()]
    if missing:
        raise SystemExit(f"missing trading_sign current files: {', '.join(missing)}")

    overview = _load_json(TRADING_SIGN_CURRENT_DIR / "tradingsign_overview.json")
    detail = _load_json(TRADING_SIGN_CURRENT_DIR / "tradingsign_model_detail.json")
    manifest = _load_json(TRADING_SIGN_CURRENT_DIR / "tradingsign_manifest.json")

    for label, payload in (("overview", overview), ("detail", detail), ("manifest", manifest)):
        asof = str(payload.get("asof") or "")
        if asof != expected_asof:
            raise SystemExit(f"trading_sign {label} asof mismatch: expected {expected_asof}, got {asof}")

    models = overview.get("models")
    if not isinstance(models, list) or not models:
        raise SystemExit("trading_sign overview models missing or empty")

    detail_models = detail.get("models")
    if not isinstance(detail_models, list) or not detail_models:
        raise SystemExit("trading_sign detail models missing or empty")

    if len(models) != len(detail_models):
        raise SystemExit(
            f"trading_sign model count mismatch: overview={len(models)} detail={len(detail_models)}"
        )

    summary = overview.get("summary") or {}
    model_count = int(summary.get("model_count") or 0)
    if model_count <= 0:
        raise SystemExit("trading_sign summary model_count must be > 0")

    files = manifest.get("files")
    if not isinstance(files, list) or sorted(files) != sorted(REQUIRED_FILES):
        raise SystemExit("trading_sign manifest files list is invalid")

    print(
        json.dumps(
            {
                "asof": expected_asof,
                "model_count": model_count,
                "signal_count": int(summary.get("signal_count") or 0),
                "validated_files": REQUIRED_FILES,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
