from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(description="Safe no-op echo command for harness execution tests.")
    ap.add_argument("--message", required=True)
    args = ap.parse_args()
    print(f"SAFE_ECHO_OK: {args.message}")


if __name__ == "__main__":
    main()
