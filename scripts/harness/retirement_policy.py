"""Harness binding to the owner-maintained permanent AI retirement policy."""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "quant2" / "src"))
from quant2.operations.ai_retirement import (  # noqa: E402
    is_retired_model,
    is_retired_object,
    load,
    require_current_object,
)

# Reviewed training entrypoints whose names do not carry the common AI prefixes.
# Keep exact names: S3 strategy, shared ETF marts and separate SAI research survive.
RETIRED_TRAINING_SCRIPTS = frozenset({
    "train_s3_two_stage_models.py",
    "build_etf_two_stage_tuned_pit_candidates.py",
    "build_etf_tseries_pit_strict_walkforward.py",
    "run_etf_role_allocation_ai_v01_experiment.py",
    "run_etf_role_weight_template_ai_v01_experiment.py",
})
RETIRED_TRAINING_MODULES = frozenset({
    "src.models.valuation_ai.train_model",
    *("scripts." + name[:-3] for name in RETIRED_TRAINING_SCRIPTS),
})


def _exact_training_entrypoint(command: str) -> str | None:
    # posix=False preserves Windows backslashes; quotes are removed per token only.
    try:
        tokens = [token.strip("\"'").lower() for token in shlex.split(command, posix=False)]
    except ValueError:
        return "malformed_command"
    for index, token in enumerate(tokens):
        normalized = token.replace("\\", "/")
        if normalized.rsplit("/", 1)[-1] in RETIRED_TRAINING_SCRIPTS:
            return normalized
        if (normalized == "src/models/valuation_ai/train_model.py"
                or normalized.endswith("/src/models/valuation_ai/train_model.py")):
            return normalized
        module = (tokens[index + 1] if token == "-m" and index + 1 < len(tokens)
                  else token[2:] if token.startswith("-m") else "")
        if module in RETIRED_TRAINING_MODULES:
            return module
    return None


def retired_model(code: str) -> bool:
    load()
    return is_retired_model(code)


def command_retirement_reason(command: str) -> str | None:
    """Reject obsolete direct entrypoints even in old approved command mappings."""
    load()
    exact = _exact_training_entrypoint(command)
    if exact:
        return f"quant1_ai_retired:{exact}"
    if "--include-ai-research" in command.lower():
        return "quant1_ai_retired:include-ai-research"
    scripts = re.findall(r"([\w-]+\.py)\b", command.lower())
    for name in scripts:
        if (name.startswith(("run_t_stock_", "run_t_etf_", "build_t_stock_", "build_t_etf_",
                             "train_t_stock_", "train_t_etf_",
                             "build_ai_", "train_ai_", "run_ai_", "run_etf_ai_",
                             "build_etf_ai_",
                             "rebuild_growth_valuation_ai_"))
                or is_retired_object(re.sub(r"^(build|run|train)_", "", name))
                or any(x in name for x in ("valuation_ai", "downside_risk_ai",
                                          "candidate_rank_delta_ai", "theme_persistence_ai"))):
            return f"quant1_ai_retired:{name}"
    return None


__all__ = ["command_retirement_reason", "retired_model", "require_current_object"]
