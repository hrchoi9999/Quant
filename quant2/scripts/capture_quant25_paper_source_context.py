"""Capture independent, hash-pinned inputs from the old Q25 observation DBs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from src.quant2.adapters.quant25_paper_source_context import capture_context  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operating-root", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / "reports"):
        parser.error("output must stay under quant2/reports")
    sha = capture_context(args.operating_root, as_of=args.as_of, output=args.output)
    print(json.dumps({"path": str(args.output.resolve()), "sha256": sha}))


if __name__ == "__main__":
    main()
