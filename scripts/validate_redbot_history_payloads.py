from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(r"D:\Quant")
PUBLIC_HISTORY_DIR = ROOT / r"service_platform\web\public_data\history"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"

USER_PERF = PUBLIC_HISTORY_DIR / "user_model_performance_history.json"
USER_HOLDINGS = PUBLIC_HISTORY_DIR / "user_model_holdings_history.json"
INTERNAL_PERF = ADMIN_CURRENT_DIR / "internal_model_performance_history.json"
TSERIES_HIST = PUBLIC_HISTORY_DIR / "quantservice_tseries_discovery_history.json"
INTERNAL_MODEL_CODES = {"S2", "S2_PIT_V01", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5", "S6", "I-STOCK-STRONG-RSI-V01"}
TSERIES_MODEL_CODES = {"T-STOCK-V01", "T-ETF-V01"}


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"missing history payload: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate redbot history payloads.")
    ap.add_argument("--asof", required=True)
    args = ap.parse_args()

    user_perf = _load_json(USER_PERF)
    user_holdings = _load_json(USER_HOLDINGS)
    internal_perf = _load_json(INTERNAL_PERF)
    tseries_hist = _load_json(TSERIES_HIST)

    for name, payload in [
        ("user_model_performance_history", user_perf),
        ("user_model_holdings_history", user_holdings),
        ("internal_model_performance_history", internal_perf),
        ("quantservice_tseries_discovery_history", tseries_hist),
    ]:
        _require(payload.get("as_of_date") == args.asof, f"{name} as_of_date mismatch: {payload.get('as_of_date')} != {args.asof}")
        _require(isinstance(payload.get("series"), list), f"{name} missing series[]")
        _require(bool(payload.get("generated_at")), f"{name} missing generated_at")

    perf_profiles = {row.get("service_profile") for row in user_perf["series"]}
    _require(perf_profiles == {"stable", "balanced", "growth"}, f"user perf profiles mismatch: {sorted(str(x) for x in perf_profiles)}")

    holdings_profiles = {row.get("service_profile") for row in user_holdings["series"]}
    _require(holdings_profiles == {"stable", "balanced", "growth"}, f"user holdings profiles mismatch: {sorted(str(x) for x in holdings_profiles)}")

    internal_models = {row.get("model_code") for row in internal_perf["series"]}
    _require(INTERNAL_MODEL_CODES.issubset(internal_models), f"internal performance coverage mismatch: {sorted(str(x) for x in internal_models)}")

    tseries_models = {row.get("model_code") for row in tseries_hist["series"]}
    _require(TSERIES_MODEL_CODES.issubset(tseries_models), f"tseries history coverage mismatch: {sorted(str(x) for x in tseries_models)}")

    for row in internal_perf["series"][:10]:
        for key in ("asof_date", "model_code", "cagr", "trailing_1y", "mdd_1y", "sharpe_1y", "itd_return", "metric_basis"):
            _require(key in row, f"internal performance missing key `{key}`")

    for row in tseries_hist["series"][:10]:
        _require("bucket_counts" in row, "tseries history missing bucket_counts")
        _require("performance_summary" in row, "tseries history missing performance_summary")
        _require("rolling_watchlist" in row, "tseries history missing rolling_watchlist")

    print(
        json.dumps(
            {
                "as_of_date": args.asof,
                "user_model_performance_rows": len(user_perf["series"]),
                "user_model_holdings_rows": len(user_holdings["series"]),
                "internal_model_performance_rows": len(internal_perf["series"]),
                "tseries_history_rows": len(tseries_hist["series"]),
                "status": "ok",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
