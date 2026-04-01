from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(r'D:\Quant')
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.quant_service.read_tseries_operational import DB_PATH, build_snapshot, connect


def main() -> None:
    ap = argparse.ArgumentParser(description="Query T-series operational latest watchlist")
    ap.add_argument("--model-code", required=True, choices=["T-STOCK-V01", "T-ETF-V01"])
    ap.add_argument("--asof")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--out")
    args = ap.parse_args()

    con = connect(Path(args.db))
    try:
        snapshot = build_snapshot(con, args.model_code, args.asof)
    finally:
        con.close()

    rendered = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(str(out_path))
        return
    print(rendered)


if __name__ == "__main__":
    main()
