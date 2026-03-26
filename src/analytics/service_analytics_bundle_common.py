from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(r'D:\Quant')
ANALYTICS_DB = ROOT / 'data' / 'db' / 'service_analytics.db'


def _read_one(conn: sqlite3.Connection, query: str) -> object:
    return conn.execute(query).fetchone()[0]


def build_common_meta(asof: str, bundle: str, pages: list[str]) -> dict[str, object]:
    built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    analytics_db_mtime = datetime.fromtimestamp(ANALYTICS_DB.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z') if ANALYTICS_DB.exists() else None
    freshness = {
        'asof': asof,
        'analytics_db_path': str(ANALYTICS_DB),
        'analytics_db_mtime_utc': analytics_db_mtime,
        'latest_week_end': None,
        'latest_change_week_end': None,
        'latest_quality_week_end': None,
    }
    source_counts: dict[str, int] = {}
    if ANALYTICS_DB.exists():
        conn = sqlite3.connect(ANALYTICS_DB)
        try:
            for table in [
                'analytics_model_run_overview',
                'analytics_model_weekly_snapshot',
                'analytics_model_asset_mix_weekly',
                'analytics_model_change_log',
                'analytics_model_quality_weekly',
            ]:
                try:
                    source_counts[table] = int(_read_one(conn, f'SELECT COUNT(*) FROM {table}'))
                except Exception:
                    source_counts[table] = 0
            try:
                freshness['latest_week_end'] = pd.to_datetime(_read_one(conn, "SELECT MAX(week_end) FROM analytics_model_weekly_snapshot"), errors='coerce').strftime('%Y-%m-%d')
            except Exception:
                freshness['latest_week_end'] = None
            try:
                freshness['latest_change_week_end'] = pd.to_datetime(_read_one(conn, "SELECT MAX(week_end) FROM analytics_model_change_log"), errors='coerce').strftime('%Y-%m-%d')
            except Exception:
                freshness['latest_change_week_end'] = None
            try:
                freshness['latest_quality_week_end'] = pd.to_datetime(_read_one(conn, "SELECT MAX(week_end) FROM analytics_model_quality_weekly"), errors='coerce').strftime('%Y-%m-%d')
            except Exception:
                freshness['latest_quality_week_end'] = None
        finally:
            conn.close()

    return {
        'asof': asof,
        'internal_preview_only': True,
        'web_publish_enabled': False,
        'bundle': bundle,
        'pages': pages,
        'bundle_version': 'analytics-preview-v5',
        'schema_version': '2026-03-26',
        'built_at_utc': built_at,
        'source_counts': source_counts,
        'freshness': freshness,
    }


def finalize_manifest(meta: dict[str, object], files: dict[str, Path]) -> dict[str, object]:
    manifest = dict(meta)
    file_meta: dict[str, dict[str, object]] = {}
    file_map: dict[str, str] = {}
    for key, path in files.items():
        file_map[key] = str(path)
        digest = hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else None
        file_meta[key] = {
            'path': str(path),
            'exists': path.exists(),
            'size_bytes': path.stat().st_size if path.exists() else None,
            'md5': digest,
        }
    manifest['files'] = file_map
    manifest['file_meta'] = file_meta
    manifest['build_status'] = 'ok' if all(v['exists'] for v in file_meta.values()) else 'error'
    return manifest


def validate_common_meta(meta: dict[str, object], bundle: str, pages: list[str]) -> None:
    required = ['asof', 'internal_preview_only', 'web_publish_enabled', 'bundle', 'pages', 'bundle_version', 'schema_version', 'built_at_utc', 'freshness']
    missing = [k for k in required if k not in meta]
    if missing:
        raise SystemExit('Missing common meta keys: ' + ', '.join(missing))
    if meta.get('bundle') != bundle:
        raise SystemExit(f'Unexpected bundle in meta: {meta.get("bundle")}')
    if list(meta.get('pages') or []) != pages:
        raise SystemExit('Unexpected pages in meta')
    if meta.get('internal_preview_only') is not True:
        raise SystemExit('internal_preview_only must be true')
    if meta.get('web_publish_enabled') is not False:
        raise SystemExit('web_publish_enabled must be false')
