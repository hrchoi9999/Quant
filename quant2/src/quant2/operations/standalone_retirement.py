"""Explicit standalone-model retirement, independent of shared allocation code."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = ROOT / 'config/standalone_model_retirement.json'


def load():
    if not CONTRACT_PATH.exists():
        if CONTRACT_PATH.with_suffix('.activated').exists():
            raise FileNotFoundError('Activated standalone contract missing')
        return None
    body = json.loads(CONTRACT_PATH.read_bytes())
    if body.get('contract_version') != 'standalone_model_retirement_v1' or body.get('namespace') != 'internal_standalone_models':
        raise ValueError('Unknown standalone lifecycle')
    marker = CONTRACT_PATH.with_suffix('.activated')
    if body.get('enabled') is False:
        if marker.exists() or body.get('retired_at') is not None:
            raise ValueError('Invalid standalone disabled state')
        return None
    if body.get('enabled') is not True or body.get('retired_model_codes') != ['S6']:
        raise ValueError('Exact standalone S6 retirement required')
    if datetime.fromisoformat(body['retired_at']).tzinfo is None:
        raise ValueError('Actual timezone cutover time required')
    return body


def active(model_code):
    return model_code != 'S6' or load() is None


def require_active(model_code):
    if not active(model_code):
        raise ValueError('S6 standalone retired; shared Q25 allocator and archived history remain available')


def project_admin(payload):
    """Remove exact S6 rows from current sections while keeping pinned history."""
    import copy

    contract = load()
    if not contract:
        return payload
    result = copy.deepcopy(payload)
    def clean(value):
        if isinstance(value, list):
            return [clean(row) for row in value if not isinstance(row, dict) or row.get('model_code') != 'S6']
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value
    # Only operating sections; legacy3 archived history is left byte-for-value intact.
    for key in ['internal_models', 'summary', 'weekly_rankings', 'model_performance_summary',
                'actual_live_performance_summary']:
        if key in result:
            result[key] = clean(result[key])
    result['standalone_lifecycle'] = {k: contract[k] for k in
        ['contract_version', 'namespace', 'enabled', 'retired_at', 'retired_model_codes']}
    if 'non_ai_admin' in result:
        from src.quant_service.non_ai_scope import admin_preserved_hash

        result['non_ai_admin']['preserved_sections_sha256'] = admin_preserved_hash(result)
    return result


def archived(contract, kind):
    ref = contract['artifacts'][kind]
    path = Path(ref['archive_path']).resolve()
    if not path.is_relative_to(Path(contract['archive_root']).resolve()):
        raise ValueError('Standalone archive boundary')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ref['sha256']:
        raise ValueError('Standalone archive changed')
    return json.loads(data)
