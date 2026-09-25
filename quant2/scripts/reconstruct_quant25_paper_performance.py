"""CLI for the separate Q25 retrospective paper-account reconstruction."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from src.quant2.adapters.quant25_paper_reconstruction import main  # noqa: E402

if __name__ == "__main__":
    main()
