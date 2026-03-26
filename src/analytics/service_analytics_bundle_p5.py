from __future__ import annotations

import json
from pathlib import Path

from src.analytics.service_analytics_bundle_common import build_common_meta, finalize_manifest

ROOT = Path(r'D:\Quant')
OUTPUT_ROOT = ROOT / 'reports' / 'service_analytics_review'


BUNDLES = {
    'p1': ['today_model_info', 'model_changes', 'model_compare'],
    'p2': ['portfolio_structure', 'holding_lifecycle'],
    'p3': ['model_quality', 'weekly_briefing'],
    'p4': ['asset_exposure_detail', 'change_impact'],
}


def _bundle_dir(asof: str, bundle: str) -> Path:
    return OUTPUT_ROOT / asof.replace('-', '') / f'{bundle}_bundle'


def _manifest_path(asof: str, bundle: str) -> Path:
    stamp = asof.replace('-', '')
    return _bundle_dir(asof, bundle) / f"bundle_manifest_{stamp}.json"


def build_bundle(asof: str) -> dict[str, object]:
    stamp = asof.replace('-', '')
    bundle_health = []
    overall_ok = True
    for bundle, pages in BUNDLES.items():
        manifest_path = _manifest_path(asof, bundle)
        exists = manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if exists else {}
        file_meta = manifest.get('file_meta', {}) if isinstance(manifest, dict) else {}
        files_ok = exists and bool(file_meta) and all(v.get('exists') for v in file_meta.values())
        bundle_ok = exists and files_ok and manifest.get('build_status') == 'ok'
        overall_ok = overall_ok and bundle_ok
        bundle_health.append({
            'bundle': bundle,
            'expected_pages': pages,
            'manifest_path': str(manifest_path),
            'manifest_exists': exists,
            'build_status': manifest.get('build_status'),
            'built_at_utc': manifest.get('built_at_utc'),
            'latest_week_end': (((manifest.get('freshness') or {}).get('latest_week_end')) if isinstance(manifest, dict) else None),
            'files_ok': files_ok,
            'schema_version': manifest.get('schema_version'),
            'bundle_version': manifest.get('bundle_version'),
        })

    meta = build_common_meta(asof, 'p5', ['admin_ops_status', 'bundle_health'])
    ops_status = {
        'overall_status': 'ok' if overall_ok else 'warn',
        'bundle_count': len(bundle_health),
        'bundles_ok': sum(1 for row in bundle_health if row['files_ok']),
        'recommendation': 'internal preview bundles are ready for admin use' if overall_ok else 'check missing bundle files or manifest status before admin review',
    }
    return {
        'meta': meta,
        'admin_ops_status': {'status': ops_status},
        'bundle_health': {'bundles': bundle_health},
    }


def write_bundle(asof: str) -> dict[str, Path]:
    data = build_bundle(asof)
    stamp = asof.replace('-', '')
    outdir = OUTPUT_ROOT / stamp / 'p5_bundle'
    outdir.mkdir(parents=True, exist_ok=True)

    manifest_path = outdir / f'bundle_manifest_{stamp}.json'
    ops_path = outdir / f'admin_ops_status_{stamp}.json'
    health_path = outdir / f'bundle_health_{stamp}.json'

    ops_path.write_text(json.dumps({'meta': data['meta'], **data['admin_ops_status']}, ensure_ascii=False, indent=2), encoding='utf-8')
    health_path.write_text(json.dumps({'meta': data['meta'], **data['bundle_health']}, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = finalize_manifest(data['meta'], {
        'admin_ops_status': ops_path,
        'bundle_health': health_path,
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    return {
        'outdir': outdir,
        'manifest': manifest_path,
        'admin_ops_status': ops_path,
        'bundle_health': health_path,
    }
