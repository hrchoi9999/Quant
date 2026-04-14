from __future__ import annotations

import argparse
import json
from datetime import date


DISABLED_MESSAGE = (
    "Google Sheets sync has been disabled. "
    "redbot.co.kr current/remote publish is now the canonical delivery path."
)


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Deprecated no-op. Google Sheets sync is disabled.")
    ap.add_argument("--asof", default=date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--report-dir", default="")
    ap.add_argument("--gsheet-cred", default="")
    ap.add_argument("--gsheet-id", default="")
    ap.add_argument("--gsheet-mode", default="overwrite")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    print(json.dumps({
        "status": "disabled",
        "asof": args.asof,
        "message": DISABLED_MESSAGE,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
