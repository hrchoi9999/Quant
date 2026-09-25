"""Explicit public-only publish contract; default publisher behavior is unchanged."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

try:
    from .retirement_policy import require_current_object
except ImportError:
    from retirement_policy import require_current_object

BUCKET = "quantservice-489808-market-analysis"
MANIFESTS = ("trading_sign/current/tradingsign_manifest.json",
             "publish_manifest_user.json", "publish_manifest.json")
CURRENT = ("publish_manifest.json", "publish_manifest_user.json", "user_model_catalog.json",
           "user_model_snapshot_report.json", "user_performance_summary.json",
           "user_recent_changes.json", "user_model_change_history.json")
HISTORY = ("user_model_performance_history.json", "user_model_holdings_history.json")
TRADING = ("tradingsign_overview.json", "tradingsign_model_detail.json", "tradingsign_manifest.json")




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
    require_current_object(name)
    if bucket == "quantservice-489808-market-analysis" and name in LEGACY_PUBLIC_BLOCKED_OBJECTS:
        raise RuntimeError("exact legacy public destination is disabled")


class PublishGuardError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise PublishGuardError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_paths(root):
    return ({name: root / "service_platform/web/public_data/current" / name for name in CURRENT}
            | {name: root / "service_platform/web/public_data/history" / name for name in HISTORY}
            | {"trading_sign/current/" + name:
               root / "trading_sign/service_platform/web/public_data/current" / name for name in TRADING})


def load_plan(path, expected_sha256, root):
    raw = Path(path).read_bytes()
    require(digest(raw) == expected_sha256, "public plan hash mismatch")
    plan = json.loads(raw)
    require(plan["schema"] == "WD06_PUBLIC12_GENERATION_V1" and plan["bucket"] == BUCKET,
            "unsupported public scope")
    target = date.fromisoformat(plan["data_asof"])
    paths = source_paths(Path(root).resolve())
    entries = plan["entries"]
    require(len(entries) == 12 and {e["object"] for e in entries} == set(paths), "exact public12 required")
    ref = plan["remote_backup_manifest"]
    backup_raw = Path(ref["path"]).read_bytes()
    require(digest(backup_raw) == ref["sha256"], "backup manifest changed")
    backup = json.loads(backup_raw)
    require(backup["status"] == "REMOTE_READ_BACKUP_COMPLETE_NOT_PUBLISH_AUTHORIZATION"
            and backup["bucket"] == BUCKET and backup["run_id"] == plan["run_id"]
            and backup["target_data_asof"] == plan["data_asof"], "backup scope mismatch")
    require(len(backup["objects"]) == 12, "exact backup12 required")
    by_name = {e["object"]: e for e in backup["objects"]}
    require(set(by_name) == set(paths), "backup object mismatch")
    payloads = {}
    for entry in entries:
        name = entry["object"]
        old = by_name[name]
        generation = entry["expected_generation"]
        require(isinstance(generation, str) and generation.isascii() and generation.isdigit()
                and int(generation) > 0 and generation == old["generation"], "invalid generation")
        require(old["http_status"] == 200 and old["status"] == "READ_AND_BACKED_UP"
                and date.fromisoformat(old["as_of_date"]) <= target, "newer or unverified backup")
        old_bytes = Path(old["backup"]).read_bytes()
        require(digest(old_bytes) == old["sha256"] and len(old_bytes) == old["size_bytes"],
                "backup bytes changed")
        src = Path(entry["source_path"]).resolve()
        require(src == paths[name].resolve(), "source outside canonical public mapping")
        body = src.read_bytes()
        require(digest(body) == entry["sha256"] and len(body) == entry["size_bytes"], "local payload changed")
        data = json.loads(body)
        require(data.get("as_of_date", data.get("asof")) == plan["data_asof"], "local date mismatch")
        require(not data.get("visibility") == "internal", "internal payload forbidden")
        payloads[name] = body
    return plan, payloads


def metadata(response, name):
    require(response.status_code == 200, f"metadata HTTP {response.status_code}")
    data = response.json()
    require(data.get("bucket") == BUCKET and data.get("name") == name, "remote identity mismatch")
    gen = data.get("generation")
    require(isinstance(gen, str) and gen.isascii() and gen.isdigit() and int(gen) > 0,
            "invalid remote generation")
    return data


def multipart(name, payload):
    boundary = "wd06_" + uuid4().hex
    meta = json.dumps({"name": name, "contentType": "application/json", "cacheControl": "no-cache"}).encode()
    body = (b"--" + boundary.encode() + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            + meta + b"\r\n--" + boundary.encode()
            + b"\r\nContent-Type: application/json\r\n\r\n" + payload
            + b"\r\n--" + boundary.encode() + b"--\r\n")
    return body, "multipart/related; boundary=" + boundary


def execute(plan, payloads, transport, checkpoint):
    """Injected authenticated transport; no DELETE, automatic retry or rollback."""
    for entry in plan["entries"]:
        reject_legacy_public_write(BUCKET, entry["object"])
    entries = {e["object"]: e for e in plan["entries"]}
    order = sorted(set(entries) - set(MANIFESTS)) + list(MANIFESTS)
    report = {"status": "PREFLIGHT", "run_id": plan["run_id"], "data_asof": plan["data_asof"],
              "started_at": datetime.now(timezone.utc).isoformat(), "objects": [],
              "automatic_retry": False, "automatic_rollback": False, "multi_object_atomic": False,
              "remote_backup_manifest": plan["remote_backup_manifest"]}
    urls = {n: f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{quote(n, safe='')}" for n in order}

    def verify(name, generation, body):
        response = transport.get(urls[name], params={"alt": "media", "ifGenerationMatch": generation},
                                 timeout=120, allow_redirects=False)
        require(response.status_code == 200 and response.content == body, "live content verification failed")
        data = metadata(transport.get(urls[name], params={"ifGenerationMatch": generation},
                                      timeout=120, allow_redirects=False), name)
        require(data["generation"] == generation and str(data.get("size")) == str(len(body))
                and data.get("cacheControl") == "no-cache", "live metadata verification failed")

    try:
        checkpoint(report)
        # Check the entire reviewed batch before the first write, then use CAS per object.
        for name in order:
            entry = entries[name]
            require(digest(payloads[name]) == entry["sha256"], "in-memory payload changed")
            data = metadata(transport.get(urls[name], params={}, timeout=120, allow_redirects=False), name)
            require(data["generation"] == entry["expected_generation"], "current changed since backup")
        for name in order:
            if name == MANIFESTS[0]:
                for done in report["objects"]:
                    verify(done["object"], done["written_generation"], payloads[done["object"]])
            entry = entries[name]
            item = {"object": name, "source_sha256": entry["sha256"],
                    "expected_generation": entry["expected_generation"], "outcome": "attempted_unknown"}
            report["objects"].append(item)
            report["status"] = "WRITING"
            checkpoint(report)
            body, content_type = multipart(name, payloads[name])
            response = transport.post(f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o",
                                      params={"uploadType": "multipart", "ifGenerationMatch": entry["expected_generation"]},
                                      data=body, headers={"Content-Type": content_type}, timeout=120, allow_redirects=False)
            if response.status_code in (409, 412):
                item["outcome"] = "conflict_no_retry"
            require(response.status_code in (200, 201), f"conditional write HTTP {response.status_code}")
            data = response.json()
            require(data.get("bucket") == BUCKET and data.get("name") == name
                    and isinstance(data.get("generation"), str) and data["generation"].isdigit()
                    and int(data["generation"]) > int(entry["expected_generation"]), "write metadata invalid")
            item.update(written_generation=data["generation"], outcome="accepted_unverified")
            checkpoint(report)
            verify(name, data["generation"], payloads[name])
            item["outcome"] = "verified"
            checkpoint(report)
        report["status"] = "PUBLIC12_VERIFIED_AT_READ"
    except Exception as exc:
        report["status"] = "STOPPED_REQUIRES_RECONCILIATION"
        report["error"] = str(exc) if isinstance(exc, PublishGuardError) else type(exc).__name__
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint(report)
    return report


def run_cli(args, publisher):
    require(not any((args.admin_bucket, args.admin_research_object, args.admin_strategy_research_observation_only,
                         args.skip_user_current, args.skip_user_history, args.skip_tseries_current,
                         args.skip_tseries_history, args.skip_admin_current, args.skip_admin_history,
                         args.skip_trading_sign_current)), "guarded public plan cannot mix legacy flags")
    require(args.bucket == BUCKET and args.public_plan_sha256, "public plan pin required")
    require(not (args.execute_public_plan and args.dry_run), "dry-run cannot execute")
    plan, payloads = load_plan(args.public_plan, args.public_plan_sha256, publisher["PROJECT_ROOT"])
    if not args.execute_public_plan:
        print(json.dumps({"status": "VALIDATED_PUBLIC12_NOT_EXECUTED", "plan_sha256": args.public_plan_sha256,
                          "objects": 12, "credentials_used": False, "network_calls": 0}))
        return
    for name in payloads:
        reject_legacy_public_write(BUCKET, name)
    require(args.public_result_dir, "unique result directory required")
    out = Path(args.public_result_dir).resolve()
    reports = (publisher["PROJECT_ROOT"] / "reports").resolve()
    require(out.is_relative_to(reports) and out != reports, "result directory must be inside reports")
    out.mkdir(exist_ok=False)
    def checkpoint(report):
        pending = out / "publish_result.pending.json"
        pending.write_text(json.dumps(report, indent=2), encoding="utf-8")
        pending.replace(out / "publish_result.json")
    # Credentials are resolved only after the explicit execute flag and full local validation.
    checkpoint({"status": "AUTH_PENDING_NO_OBJECT_WRITES", "plan_sha256": args.public_plan_sha256})
    try:
        token = publisher["_access_token"](publisher["_resolve_cred_path"](args.cred))
    except BaseException as exc:
        checkpoint({"status": "AUTH_FAILED_NO_OBJECT_WRITES", "error_type": type(exc).__name__,
                    "plan_sha256": args.public_plan_sha256})
        raise
    with publisher["requests"].Session() as session:
        session.headers["Authorization"] = "Bearer " + token
        execute(plan, payloads, session, checkpoint)
