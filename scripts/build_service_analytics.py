from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.service_analytics_builder import SERVICE_ANALYTICS_DB, persist_service_analytics


def main() -> None:
    counts = persist_service_analytics()
    print(f"service_analytics_db={SERVICE_ANALYTICS_DB}")
    for table, count in counts.items():
        print(f"{table}={count}")


if __name__ == "__main__":
    main()
