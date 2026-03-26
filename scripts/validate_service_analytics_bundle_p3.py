from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r'D:\Quant')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.service_analytics_bundle_common import validate_common_meta

from src.analytics.service_analytics_bundle_p3 import write_bundle

REQUIRED_MODELS = {'S2', 'S3', 'S3_CORE2', 'S4', 'S5', 'S6'}


def main() -> None:
    outputs = write_bundle('2026-03-25')
    manifest = json.loads(Path(outputs['manifest']).read_text(encoding='utf-8'))
    quality = json.loads(Path(outputs['model_quality']).read_text(encoding='utf-8'))
    briefing = json.loads(Path(outputs['weekly_briefing']).read_text(encoding='utf-8'))

    validate_common_meta(quality.get('meta', {}), 'p3', ['model_quality', 'weekly_briefing'])
    if not all(v.get('exists') for v in manifest.get('file_meta', {}).values()):
        raise SystemExit('Manifest file_meta indicates missing bundle files')

    if quality.get('meta', {}).get('web_publish_enabled') is not False:
        raise SystemExit('P3 bundle must remain non-web-published')

    quality_models = {row['model_code'] for row in quality['models']}
    briefing_models = {row['model_code'] for row in briefing['models']}
    for label, models in [('model_quality', quality_models), ('weekly_briefing', briefing_models)]:
        missing = sorted(REQUIRED_MODELS - models)
        if missing:
            raise SystemExit(f'Missing models in {label}: ' + ', '.join(missing))

    if not all('quality_trend_26w' in row for row in quality['models']):
        raise SystemExit('model_quality payload missing quality_trend_26w')
    if not all('quality_checks' in row for row in quality['models']):
        raise SystemExit('model_quality payload missing quality_checks')
    if not all('turnover_avg_4w' in row.get('latest_quality', {}) for row in quality['models']):
        raise SystemExit('model_quality payload missing turnover_avg_4w')
    if not all('top5_weight' in row.get('latest_quality', {}) for row in quality['models']):
        raise SystemExit('model_quality payload missing top5_weight')
    if not all('briefing_points' in row for row in briefing['models']):
        raise SystemExit('weekly_briefing payload missing briefing_points')
    if not all('relative_strength_vs_benchmark_12w' in row.get('summary', {}) for row in briefing['models']):
        raise SystemExit('weekly_briefing payload missing relative_strength_vs_benchmark_12w')

    print(f'validated_quality_models={len(quality_models)}')
    print(f'validated_briefing_models={len(briefing_models)}')
    print('validated_service_analytics_bundle_p3=ok')


if __name__ == '__main__':
    main()
