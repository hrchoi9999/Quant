from __future__ import annotations

import argparse
from pathlib import Path

import yaml

PROJECT_ROOT = Path(r'D:\Quant')
EXPECTED_USER_MODELS = {'ì\x95\x88ì\xa0\x95í\x98\x95', 'ê·\xa0í\x98\x95í\x98\x95', 'ì\x84±ì\x9e¥í\x98\x95', 'ì\x9e\x90ë\x8f\x99ì\xa0\x84í\x99\x98í\x98\x95'}


def main() -> None:
    ap = argparse.ArgumentParser(description='Validate user/internal model mapping files.')
    ap.add_argument('--mapping-yml', default=str(PROJECT_ROOT / 'data' / 'configs' / 'redbot_model_mapping.yml'))
    args = ap.parse_args()

    path = Path(args.mapping_yml)
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    user_models = data.get('user_models', []) or []
    internal_models = data.get('internal_models', []) or []
    service_profiles = data.get('service_profiles', []) or []

    expected_profiles = {'stable', 'balanced', 'growth', 'auto'}
    internal_names = {str(x.get('internal_model_name')) for x in internal_models}
    user_names = {str(x.get('user_model_name')) for x in user_models}
    profile_names = {str(x.get('service_profile')) for x in service_profiles}

    if user_names != EXPECTED_USER_MODELS:
        raise AssertionError(f'user model names mismatch: {sorted(user_names)}')
    if profile_names != expected_profiles:
        raise AssertionError(f'service profiles mismatch: {sorted(profile_names)}')
    for required in ['S2', 'S3', 'S4', 'S5', 'S6', 'Router']:
        if required not in internal_names:
            raise AssertionError(f'missing internal model: {required}')
    required_fields = {'user_model_name', 'service_profile', 'primary_internal_models', 'secondary_internal_models', 'description', 'risk_label', 'target_user_type'}
    for row in user_models:
        missing = required_fields - set(row.keys())
        if missing:
            raise AssertionError(f'missing fields for {row.get("user_model_name")}: {sorted(missing)}')

    print(f'[OK] mapping={path}')
    print(f'[OK] user_models={sorted(user_names)}')
    print(f'[OK] internal_models={sorted(internal_names)}')
    print(f'[OK] service_profiles={sorted(profile_names)}')


if __name__ == '__main__':
    main()
