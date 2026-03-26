from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r'D:\Quant')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.service_analytics_bundle_common import validate_common_meta

from src.analytics.service_analytics_bundle_p2 import write_bundle

REQUIRED_MODELS = {'S2', 'S3', 'S3_CORE2', 'S4', 'S5', 'S6'}


def main() -> None:
    outputs = write_bundle('2026-03-25')
    manifest = json.loads(Path(outputs['manifest']).read_text(encoding='utf-8'))
    structure = json.loads(Path(outputs['portfolio_structure']).read_text(encoding='utf-8'))
    lifecycle = json.loads(Path(outputs['holding_lifecycle']).read_text(encoding='utf-8'))

    validate_common_meta(structure.get('meta', {}), 'p2', ['portfolio_structure', 'holding_lifecycle'])
    if not all(v.get('exists') for v in manifest.get('file_meta', {}).values()):
        raise SystemExit('Manifest file_meta indicates missing bundle files')

    if structure.get('meta', {}).get('web_publish_enabled') is not False:
        raise SystemExit('P2 bundle must remain non-web-published')

    structure_models = {row['model_code'] for row in structure['models']}
    lifecycle_models = {row['model_code'] for row in lifecycle['models']}
    for label, models in [('portfolio_structure', structure_models), ('holding_lifecycle', lifecycle_models)]:
        missing = sorted(REQUIRED_MODELS - models)
        if missing:
            raise SystemExit(f'Missing models in {label}: ' + ', '.join(missing))

    if not all('asset_mix_trend_26w' in row for row in structure['models']):
        raise SystemExit('portfolio_structure payload missing asset_mix_trend_26w')
    if not all('longest_historical_holdings' in row for row in lifecycle['models']):
        raise SystemExit('holding_lifecycle payload missing longest_historical_holdings')

    print(f'validated_structure_models={len(structure_models)}')
    print(f'validated_lifecycle_models={len(lifecycle_models)}')
    print('validated_service_analytics_bundle_p2=ok')


if __name__ == '__main__':
    main()
