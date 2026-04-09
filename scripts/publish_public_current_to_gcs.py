from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
from urllib.parse import quote

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

PROJECT_ROOT = Path(r"D:\Quant")
CURRENT_DIR = PROJECT_ROOT / r"service_platform\web\public_data\current"
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
]
T_SERIES_OBJECT = ("quantservice_tseries_discovery.json", "tseries_discovery/current/quantservice_tseries_discovery.json")
TRADING_SIGN_OBJECTS = [
    ("tradingsign_overview.json", "trading_sign/current/tradingsign_overview.json"),
    ("tradingsign_model_detail.json", "trading_sign/current/tradingsign_model_detail.json"),
    ("tradingsign_manifest.json", "trading_sign/current/tradingsign_manifest.json"),
]


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
    ap.add_argument("--skip-tseries-current", action="store_true")
    ap.add_argument("--skip-trading-sign-current", action="store_true")
    args = ap.parse_args()

    cred_path = _resolve_cred_path(args.cred)
    token = _access_token(cred_path)

    if not args.skip_user_current:
        for name in ROOT_OBJECTS:
            src = CURRENT_DIR / name
            if not src.exists():
                raise SystemExit(f"missing local current file: {src}")
            _upload_file(args.bucket, src, name, token)

    if not args.skip_tseries_current:
        src_name, object_name = T_SERIES_OBJECT
        src = CURRENT_DIR / src_name
        if not src.exists():
            raise SystemExit(f"missing local tseries current file: {src}")
        _upload_file(args.bucket, src, object_name, token)

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
        "published_tseries_current": not args.skip_tseries_current,
        "published_trading_sign_current": not args.skip_trading_sign_current,
        "credential_path": str(cred_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
