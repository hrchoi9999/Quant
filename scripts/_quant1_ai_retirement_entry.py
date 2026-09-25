"""Guard legacy AI command-line entrypoints without importing their pipelines."""

import sys
from pathlib import Path


def reject_retired(model_code: str) -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from src.quant2.operations.ai_retirement import require_model_active

    require_model_active(model_code)
