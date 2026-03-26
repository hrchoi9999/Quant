from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.service_analytics_bundle_common import validate_common_meta
from src.analytics.service_analytics_bundle_p5 import write_bundle


def main() -> None:
    outputs = write_bundle('2026-03-25')
    manifest = json.loads(Path(outputs['manifest']).read_text(encoding='utf-8'))
    ops = json.loads(Path(outputs['admin_ops_status']).read_text(encoding='utf-8'))
    health = json.loads(Path(outputs['bundle_health']).read_text(encoding='utf-8'))

    validate_common_meta(ops.get('meta', {}), 'p5', ['admin_ops_status', 'bundle_health'])
    if not all(v.get('exists') for v in manifest.get('file_meta', {}).values()):
        raise SystemExit('Manifest file_meta indicates missing P5 files')
    if 'status' not in ops:
        raise SystemExit('P5 admin_ops_status missing status')
    if 'bundles' not in health:
        raise SystemExit('P5 bundle_health missing bundles')
    if len(health['bundles']) < 4:
        raise SystemExit('P5 bundle_health missing prior bundle records')

    print(f'validated_ops_bundles={len(health["bundles"])}')
    print('validated_service_analytics_bundle_p5=ok')


if __name__ == '__main__':
    main()
