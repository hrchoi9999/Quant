from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.service_analytics_bundle_common import validate_common_meta
from src.analytics.service_analytics_bundle_p4 import write_bundle

REQUIRED_MODELS = {'S2', 'S3', 'S3_CORE2', 'S4', 'S5', 'S6'}


def main() -> None:
    outputs = write_bundle('2026-03-25')
    manifest = json.loads(Path(outputs['manifest']).read_text(encoding='utf-8'))
    exposure = json.loads(Path(outputs['asset_exposure_detail']).read_text(encoding='utf-8'))
    impact = json.loads(Path(outputs['change_impact']).read_text(encoding='utf-8'))

    validate_common_meta(exposure.get('meta', {}), 'p4', ['asset_exposure_detail', 'change_impact'])
    if not all(v.get('exists') for v in manifest.get('file_meta', {}).values()):
        raise SystemExit('Manifest file_meta indicates missing bundle files')

    if exposure.get('meta', {}).get('web_publish_enabled') is not False:
        raise SystemExit('P4 bundle must remain non-web-published')

    exposure_models = {row['model_code'] for row in exposure['models']}
    impact_models = {row['model_code'] for row in impact['models']}
    for label, models in [('asset_exposure_detail', exposure_models), ('change_impact', impact_models)]:
        missing = sorted(REQUIRED_MODELS - models)
        if missing:
            raise SystemExit(f'Missing models in {label}: ' + ', '.join(missing))

    if not all('latest_asset_detail' in row for row in exposure['models']):
        raise SystemExit('asset_exposure_detail payload missing latest_asset_detail')
    if not all('latest_change_activity' in row for row in impact['models']):
        raise SystemExit('change_impact payload missing latest_change_activity')
    if not all('impact_summary' in row for row in impact['models']):
        raise SystemExit('change_impact payload missing impact_summary')

    print(f'validated_exposure_models={len(exposure_models)}')
    print(f'validated_impact_models={len(impact_models)}')
    print('validated_service_analytics_bundle_p4=ok')


if __name__ == '__main__':
    main()
