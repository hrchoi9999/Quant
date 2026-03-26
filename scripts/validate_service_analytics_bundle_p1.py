from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r'D:\Quant')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.service_analytics_bundle_common import validate_common_meta

from src.analytics.service_analytics_bundle_p1 import write_bundle


REQUIRED_MODELS = {'S2', 'S3', 'S3_CORE2', 'S4', 'S5', 'S6'}


def main() -> None:
    outputs = write_bundle('2026-03-25')
    manifest = json.loads(Path(outputs['manifest']).read_text(encoding='utf-8'))
    today = json.loads(Path(outputs['today_model_info']).read_text(encoding='utf-8'))
    changes = json.loads(Path(outputs['model_changes']).read_text(encoding='utf-8'))
    compare = json.loads(Path(outputs['model_compare']).read_text(encoding='utf-8'))

    validate_common_meta(today.get('meta', {}), 'p1', ['today_model_info', 'model_changes', 'model_compare'])
    today_models = {row['model_code'] for row in today['models']}
    change_models = {row['model_code'] for row in changes['models']}
    compare_models = {row['model_code'] for row in compare['rows']}

    if not all(v.get('exists') for v in manifest.get('file_meta', {}).values()):
        raise SystemExit('Manifest file_meta indicates missing bundle files')

    if today.get('meta', {}).get('web_publish_enabled') is not False:
        raise SystemExit('P1 bundle must remain non-web-published')

    for label, models in [('today', today_models), ('changes', change_models), ('compare', compare_models)]:
        missing = sorted(REQUIRED_MODELS - models)
        if missing:
            raise SystemExit(f'Missing models in {label} payload: ' + ', '.join(missing))

    if not all('top_holdings' in row for row in today['models']):
        raise SystemExit('today_model_info payload missing top_holdings')
    if not all('summary' in row and 'items' in row for row in changes['models']):
        raise SystemExit('model_changes payload missing summary/items')
    if not all('cagr' in row and 'return_4w' in row for row in compare['rows']):
        raise SystemExit('model_compare payload missing metrics')

    print(f'validated_today_models={len(today_models)}')
    print(f'validated_change_models={len(change_models)}')
    print(f'validated_compare_models={len(compare_models)}')
    print('validated_service_analytics_bundle_p1=ok')


if __name__ == '__main__':
    main()
