from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

PROJECT_ROOT = Path(r"D:\Quant")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.quant2.operations import ai_retirement  # noqa: E402

CURRENT_DIR = PROJECT_ROOT / r"service_platform\web\public_data\current"
PUBLIC_HISTORY_DIR = PROJECT_ROOT / r"service_platform\web\public_data\history"
ADMIN_CURRENT_DIR = PROJECT_ROOT / r"service_platform\web\admin_data\current"
TRADING_SIGN_CURRENT_DIR = PROJECT_ROOT / r"trading_sign\service_platform\web\public_data\current"
DEFAULT_CRED_CANDIDATES = [
    Path(r"D:\QuantService\data\gcp\quantmarket-handoff-uploader.json"),
    PROJECT_ROOT / r"config\quant-485814-0df3dc750a8d.json",
]
DEFAULT_BUCKET = "quantservice-489808-market-analysis"

ROOT_OBJECTS = [
    "publish_manifest.json",
    "publish_manifest_user.json",
    "user_model_catalog.json",
    "user_model_snapshot_report.json",
    "user_performance_summary.json",
    "user_recent_changes.json",
    "user_model_change_history.json",
]
USER_HISTORY_OBJECTS = [
    ("user_model_performance_history.json", "user_model_performance_history.json"),
    ("user_model_holdings_history.json", "user_model_holdings_history.json"),
]
T_SERIES_OBJECT = ("quantservice_tseries_discovery.json", "tseries_discovery/current/quantservice_tseries_discovery.json")
T_SERIES_HISTORY_OBJECT = (
    "quantservice_tseries_discovery_history.json",
    "tseries_discovery/history/quantservice_tseries_discovery_history.json",
)
ADMIN_TRACKER_OBJECT = ("admin_new_entry_tracker.json", "admin/current/admin_new_entry_tracker.json")
ADMIN_INTERNAL_PERF_HISTORY_OBJECT = (
    "internal_model_performance_history.json",
    "admin/current/internal_model_performance_history.json",
)
ADMIN_INTERNAL_VALIDATION_CURRENT_OBJECT = (
    "internal_model_validation_current.json",
    "admin/current/internal_model_validation_current.json",
)
ADMIN_INTERNAL_VALIDATION_HISTORY_OBJECT = (
    "internal_model_validation_history.json",
    "admin/current/internal_model_validation_history.json",
)
ADMIN_AI_SHADOW_OBSERVATION_OBJECT = (
    "ai_shadow_observation.json",
    "admin/current/ai_shadow_observation.json",
)
ADMIN_STRATEGY_RESEARCH_OBSERVATION_OBJECT = (
    "strategy_research_observation.json",
    "admin/current/strategy_research_observation.json",
)
ADMIN_AI_LEARNING_MODELS_OBJECT = (
    "ai_learning_models_current.json",
    "admin/current/ai_learning_models_current.json",
)
ADMIN_DOWNSIDE_RISK_AI_OBJECT = (
    "downside_risk_ai_current.json",
    "admin/current/downside_risk_ai_current.json",
)
ADMIN_DOWNSIDE_RISK_AI_SHADOW_OBJECT = (
    "downside_risk_ai_shadow_tracker.json",
    "admin/current/downside_risk_ai_shadow_tracker.json",
)
ADMIN_CANDIDATE_RANK_DELTA_AI_OBJECT = (
    "candidate_rank_delta_ai_current.json",
    "admin/current/candidate_rank_delta_ai_current.json",
)
ADMIN_THEME_PERSISTENCE_AI_OBJECT = (
    "theme_persistence_ai_current.json",
    "admin/current/theme_persistence_ai_current.json",
)
ADMIN_ETF_AI_SHADOW_PORTFOLIO_OBJECT = (
    "etf_ai_shadow_portfolio_current.json",
    "admin/current/etf_ai_shadow_portfolio_current.json",
)
ADMIN_VALUATION_AI_OBJECTS = [
    ("valuation_ai_challenger_current.json", "admin/current/valuation_ai_challenger_current.json"),
    (
        "valuation_ai_challenger_shadow_performance.json",
        "admin/current/valuation_ai_challenger_shadow_performance.json",
    ),
    ("valuation_ai_shadow_monitor.json", "admin/current/valuation_ai_shadow_monitor.json"),
]
TRADING_SIGN_OBJECTS = [
    ("tradingsign_overview.json", "trading_sign/current/tradingsign_overview.json"),
    ("tradingsign_model_detail.json", "trading_sign/current/tradingsign_model_detail.json"),
    ("tradingsign_manifest.json", "trading_sign/current/tradingsign_manifest.json"),
]




# Active exact47 legacy public write block; private and Q25 paths remain separate.
LEGACY_PUBLIC_BLOCKED_OBJECTS = frozenset({
    'admin/current/admin_new_entry_tracker.json',
    'admin/current/ai_learning_models_current.json',
    'admin/current/ai_learning_overlay_monitor_current.json',
    'admin/current/ai_shadow_observation.json',
    'admin/current/candidate_rank_delta_ai_current.json',
    'admin/current/downside_risk_ai_current.json',
    'admin/current/downside_risk_ai_shadow_tracker.json',
    'admin/current/e_series_etf_mode_switch_cost_adjusted_current.json',
    'admin/current/e_series_etf_mode_switch_turnover_buffer_current.json',
    'admin/current/e_series_etf_operational_hardening_current.json',
    'admin/current/e_series_etf_operational_policy_hierarchy_current.json',
    'admin/current/e_series_etf_sleeve_portfolio_current.json',
    'admin/current/e_series_etf_sleeve_selection_current.json',
    'admin/current/e_series_etf_total_return_adjustment_current.json',
    'admin/current/etf_ai_shadow_portfolio_current.json',
    'admin/current/internal_model_performance_history.json',
    'admin/current/internal_model_validation_current.json',
    'admin/current/internal_model_validation_history.json',
    'admin/current/internal_models_ai_overlay_shadow_current.json',
    'admin/current/strategy_research_observation.json',
    'admin/current/theme_persistence_ai_current.json',
    'admin/current/valuation_ai_challenger_current.json',
    'admin/current/valuation_ai_challenger_shadow_performance.json',
    'admin/current/valuation_ai_shadow_monitor.json',
    'current/publish_manifest.json',
    'current/publish_manifest_user.json',
    'current/user_model_catalog.json',
    'current/user_model_snapshot_report.json',
    'current/user_performance_summary.json',
    'current/user_recent_changes.json',
    'history/quantservice_tseries_discovery_history.json',
    'history/user_model_holdings_history.json',
    'history/user_model_performance_history.json',
    'publish_manifest.json',
    'publish_manifest_user.json',
    'trading_sign/current/tradingsign_manifest.json',
    'trading_sign/current/tradingsign_model_detail.json',
    'trading_sign/current/tradingsign_overview.json',
    'tseries_discovery/current/quantservice_tseries_discovery.json',
    'tseries_discovery/history/quantservice_tseries_discovery_history.json',
    'user_model_catalog.json',
    'user_model_change_history.json',
    'user_model_holdings_history.json',
    'user_model_performance_history.json',
    'user_model_snapshot_report.json',
    'user_performance_summary.json',
    'user_recent_changes.json',
})

def reject_legacy_public_write(bucket, name):
    if bucket == "quantservice-489808-market-analysis" and name in LEGACY_PUBLIC_BLOCKED_OBJECTS:
        raise RuntimeError("exact legacy public destination is disabled")


def selected_legacy_objects(args):
    if args.admin_strategy_research_observation_only:
        return {ADMIN_STRATEGY_RESEARCH_OBSERVATION_OBJECT[1]}
    names = set()
    if not args.skip_user_current:
        names.update(ROOT_OBJECTS)
    if not args.skip_user_history:
        names.update(pair[1] for pair in USER_HISTORY_OBJECTS)
    if not args.skip_tseries_current:
        names.add(T_SERIES_OBJECT[1])
    if not args.skip_tseries_history:
        names.add(T_SERIES_HISTORY_OBJECT[1])
    history = {"ADMIN_INTERNAL_PERF_HISTORY_OBJECT", "ADMIN_INTERNAL_VALIDATION_HISTORY_OBJECT"}
    if not args.skip_admin_history:
        names.update(globals()[key][1] for key in history)
    if not args.skip_admin_current:
        names.update(value[1] for key, value in globals().items()
                     if key.startswith("ADMIN_") and isinstance(value, tuple) and key not in history)
        names.update(pair[1] for pair in ADMIN_VALUATION_AI_OBJECTS)
    if not args.skip_trading_sign_current:
        names.update(pair[1] for pair in TRADING_SIGN_OBJECTS)
    return {name for name in names if not ai_retirement.is_retired_object(name)}


def _resolve_cred_path(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit)
        if candidate.exists():
            return candidate
        raise SystemExit(f"credential file not found: {candidate}")
    for candidate in DEFAULT_CRED_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit("no usable credential file found for GCS publish")


def _access_token(cred_path: Path) -> str:
    creds = service_account.Credentials.from_service_account_file(
        str(cred_path), scopes=["https://www.googleapis.com/auth/devstorage.read_write"]
    )
    creds.refresh(Request())
    token = creds.token
    if not token:
        raise RuntimeError("failed to obtain access token for GCS publish")
    return token


def _upload_bytes(bucket: str, object_name: str, payload: bytes, token: str, content_type: str) -> None:
    reject_legacy_public_write(bucket, object_name)
    url = (
        f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
        f"?uploadType=media&name={quote(object_name, safe='')}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "Cache-Control": "no-cache",
    }
    response = requests.post(url, headers=headers, data=payload, timeout=120)
    if response.status_code == 409:
        patch_url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{quote(object_name, safe='')}?alt=json"
        response = requests.delete(patch_url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
        if response.status_code not in (204, 404):
            raise RuntimeError(f"failed to delete existing object {object_name}: {response.status_code} {response.text[:500]}")
        response = requests.post(url, headers=headers, data=payload, timeout=120)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"failed to upload {object_name}: {response.status_code} {response.text[:500]}")


def _upload_file(bucket: str, src: Path, object_name: str, token: str) -> None:
    content_type = mimetypes.guess_type(src.name)[0] or "application/json"
    _upload_bytes(bucket, object_name, src.read_bytes(), token, content_type)
    print(f"[OK] uploaded {src.name} -> gs://{bucket}/{object_name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish public current snapshot files to canonical GCS objects")
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--cred")
    ap.add_argument("--skip-user-current", action="store_true")
    ap.add_argument("--skip-user-history", action="store_true")
    ap.add_argument("--skip-tseries-current", action="store_true")
    ap.add_argument("--skip-tseries-history", action="store_true")
    ap.add_argument("--skip-admin-current", action="store_true")
    ap.add_argument("--skip-admin-history", action="store_true")
    ap.add_argument("--skip-trading-sign-current", action="store_true")
    ap.add_argument(
        "--admin-strategy-research-observation-only",
        action="store_true",
        help="Publish only the admin-only strategy research observation payload.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Validate and print a local plan without credentials or network.")
    ap.add_argument("--admin-bucket", help="Opt-in private admin destination (local preparation only).")
    ap.add_argument("--admin-research-object", action="append", default=[], help="Explicit research filename; repeat per selected object.")
    ap.add_argument("--public-plan", help="Opt-in pinned public12 plan; validation only unless explicitly executed.")
    ap.add_argument("--public-plan-sha256")
    ap.add_argument("--execute-public-plan", action="store_true")
    ap.add_argument("--public-result-dir")
    args = ap.parse_args()
    ai_retirement.load()

    if args.public_plan:
        import sys

        sys.path.insert(0, str(PROJECT_ROOT))
        from scripts.harness.public_publish_guard import run_cli

        run_cli(args, globals())
        return
    if args.public_plan_sha256 or args.execute_public_plan or args.public_result_dir:
        ap.error("public plan options require --public-plan")
    args.skip_tseries_current = True
    args.skip_tseries_history = True

    if args.dry_run or args.admin_bucket or args.admin_research_object:
        import sys

        sys.path.insert(0, str(PROJECT_ROOT / "quant2"))
        from src.quant2.storage.admin_publish_candidate import run_local_candidate

        run_local_candidate(args, globals())
        return

    for name in selected_legacy_objects(args):
        reject_legacy_public_write(args.bucket, name)

    cred_path = _resolve_cred_path(args.cred)
    token = _access_token(cred_path)

    if args.admin_strategy_research_observation_only:
        src_name, object_name = ADMIN_STRATEGY_RESEARCH_OBSERVATION_OBJECT
        src = ADMIN_CURRENT_DIR / src_name
        if not src.exists():
            raise SystemExit(f"missing local strategy research observation file: {src}")
        _upload_file(args.bucket, src, object_name, token)
        payload = json.loads(src.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "bucket": args.bucket,
                    "object": object_name,
                    "as_of_date": payload.get("as_of_date"),
                    "generated_at": payload.get("generated_at"),
                    "model_count": len(payload.get("models") or []),
                    "credential_path": str(cred_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not args.skip_user_current:
        for name in ROOT_OBJECTS:
            src = CURRENT_DIR / name
            if not src.exists():
                raise SystemExit(f"missing local current file: {src}")
            _upload_file(args.bucket, src, name, token)

    if not args.skip_user_history:
        for src_name, object_name in USER_HISTORY_OBJECTS:
            src = PUBLIC_HISTORY_DIR / src_name
            if not src.exists():
                raise SystemExit(f"missing local user history file: {src}")
            _upload_file(args.bucket, src, object_name, token)

    if not args.skip_tseries_current:
        src_name, object_name = T_SERIES_OBJECT
        src = CURRENT_DIR / src_name
        if not src.exists():
            raise SystemExit(f"missing local tseries current file: {src}")
        _upload_file(args.bucket, src, object_name, token)

    if not args.skip_tseries_history:
        src_name, object_name = T_SERIES_HISTORY_OBJECT
        src = PUBLIC_HISTORY_DIR / src_name
        if not src.exists():
            raise SystemExit(f"missing local tseries history file: {src}")
        _upload_file(args.bucket, src, object_name, token)

    if not args.skip_admin_current:
        src_name, object_name = ADMIN_TRACKER_OBJECT
        src = ADMIN_CURRENT_DIR / src_name
        if not src.exists():
            raise SystemExit(f"missing local admin current file: {src}")
        _upload_file(args.bucket, src, object_name, token)

    if not args.skip_admin_history:
        src_name, object_name = ADMIN_INTERNAL_PERF_HISTORY_OBJECT
        src = ADMIN_CURRENT_DIR / src_name
        if not src.exists():
            raise SystemExit(f"missing local admin history file: {src}")
        _upload_file(args.bucket, src, object_name, token)

        src_name, object_name = ADMIN_INTERNAL_VALIDATION_HISTORY_OBJECT
        src = ADMIN_CURRENT_DIR / src_name
        if src.exists():
            _upload_file(args.bucket, src, object_name, token)
        else:
            print(f"[WARN] missing optional admin internal validation history file: {src}")

    if not args.skip_admin_current:
        src_name, object_name = ADMIN_INTERNAL_VALIDATION_CURRENT_OBJECT
        src = ADMIN_CURRENT_DIR / src_name
        if src.exists():
            _upload_file(args.bucket, src, object_name, token)
        else:
            print(f"[WARN] missing optional admin internal validation current file: {src}")

        src_name, object_name = ADMIN_STRATEGY_RESEARCH_OBSERVATION_OBJECT
        src = ADMIN_CURRENT_DIR / src_name
        if src.exists():
            _upload_file(args.bucket, src, object_name, token)
        else:
            print(f"[WARN] missing optional admin strategy research observation file: {src}")

        # Legacy AI current objects remain historical files, never new uploads.

    if not args.skip_trading_sign_current:
        for src_name, object_name in TRADING_SIGN_OBJECTS:
            src = TRADING_SIGN_CURRENT_DIR / src_name
            if not src.exists():
                raise SystemExit(f"missing local trading_sign current file: {src}")
            _upload_file(args.bucket, src, object_name, token)

    manifest = json.loads((CURRENT_DIR / "publish_manifest.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "bucket": args.bucket,
        "as_of_date": manifest.get("as_of_date"),
        "generated_at": manifest.get("generated_at"),
        "published_user_current": not args.skip_user_current,
        "published_user_history": not args.skip_user_history,
        "published_tseries_current": not args.skip_tseries_current,
        "published_tseries_history": not args.skip_tseries_history,
        "published_admin_current": not args.skip_admin_current,
        "published_admin_history": not args.skip_admin_history,
        "published_admin_internal_validation_current": not args.skip_admin_current and (ADMIN_CURRENT_DIR / ADMIN_INTERNAL_VALIDATION_CURRENT_OBJECT[0]).exists(),
        "published_admin_internal_validation_history": not args.skip_admin_history and (ADMIN_CURRENT_DIR / ADMIN_INTERNAL_VALIDATION_HISTORY_OBJECT[0]).exists(),
        "published_admin_ai_shadow_observation": False,
        "published_admin_strategy_research_observation": not args.skip_admin_current and (ADMIN_CURRENT_DIR / ADMIN_STRATEGY_RESEARCH_OBSERVATION_OBJECT[0]).exists(),
        "published_admin_ai_learning_models": False,
        "published_admin_downside_risk_ai": False,
        "published_admin_downside_risk_ai_shadow": False,
        "published_admin_candidate_rank_delta_ai": False,
        "published_admin_theme_persistence_ai": False,
        "published_admin_etf_ai_shadow_portfolio": False,
        "published_admin_valuation_ai": False,
        "published_trading_sign_current": not args.skip_trading_sign_current,
        "credential_path": str(cred_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
