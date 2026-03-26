# run_backtest_v5.py ver 2026-02-24_001
"""Entry wrapper for S2 refactor vs legacy runners.

Purpose
- Single stable entrypoint: python -m src.backtest.run_backtest_v5 ...
- Delegates to refactor runner by default.
- Can delegate to legacy runner with --delegate-legacy (kept for compatibility).

Design constraints (PROJECT_CONVENTIONS)
- Wrapper must not reject runner args: uses parse_known_args() and forwards unknown args as-is.
- No subprocess execution inside wrapper. Delegation is via import + main(argv).
- If --fee-bps / --slippage-bps are NOT provided, defaults to 5/5 (project standard: total 10 bps).
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import List


WRAPPER_ONLY_FLAGS = {"--s2-refactor", "--delegate-legacy"}


def _has_flag(argv: List[str], flag: str) -> bool:
    return any(a == flag or a.startswith(flag + "=") for a in argv)


def _ensure_default_costs(argv: List[str]) -> List[str]:
    """Inject fee/slippage defaults if user did not specify them."""
    out = list(argv)
    if not _has_flag(out, "--fee-bps"):
        out += ["--fee-bps", "5"]
    if not _has_flag(out, "--slippage-bps"):
        out += ["--slippage-bps", "5"]
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    p = argparse.ArgumentParser(add_help=True)
    p.add_argument("--s2-refactor", action="store_true", help="(compat) kept for old commands")
    p.add_argument("--delegate-legacy", action="store_true", help="delegate to legacy runner")
    args, unknown = p.parse_known_args(argv)

    # Strip wrapper-only flags from forwarded args
    forwarded = [a for a in argv if not any(a == f or a.startswith(f + "=") for f in WRAPPER_ONLY_FLAGS)]
    forwarded = _ensure_default_costs(forwarded)

    module_name = "src.backtest.run_backtest_s2_refactor_v1"
    if args.delegate_legacy:
        module_name = "src.backtest.run_backtest_s2_v5"

    mod = importlib.import_module(module_name)
    if not hasattr(mod, "main"):
        raise AttributeError(f"Delegated module {module_name} has no main(argv=None)")

    rc = mod.main(forwarded)
    return 0 if rc is None else int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
