from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.service_analytics_bundle_p4 import write_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description='Build service analytics P4 preview bundle')
    parser.add_argument('--asof', default='2026-03-25')
    args = parser.parse_args()

    outputs = write_bundle(args.asof)
    for key, value in outputs.items():
        print(f'{key}={value}')


if __name__ == '__main__':
    main()
