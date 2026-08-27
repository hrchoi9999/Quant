from __future__ import annotations

import json
from pathlib import Path

from harness_common import (
    COMMAND_MAPPING_DIR,
    ROOT,
    command_matches_blocked_pattern,
    load_stage_commands,
    load_thread_roles,
    write_json,
)

SEARCH_DIRS = ("scripts", "src", "docs", "config")
THREAD_STAGE_ROOT = {
    "WD01_QUANT_FRONT": "Quant",
    "WD02_MARKET_COLLECT": "QuantMarketData",
    "WD03_MARKET_ANALYSIS": "QuantMarket",
    "WD04_QUANT_REAR": "Quant",
    "WD05_PORTFOLIO_ANALYSIS": "QuantAnalysis",
    "WE01_QUANT_WEEKEND_PIPELINE": "Quant",
}
STAGE_KEYWORDS = {
    "WD01_QUANT_FRONT": ["daily", "pipeline", "quant", "ingest", "run_"],
    "WD02_MARKET_COLLECT": ["market", "collect", "collector", "krx", "dart", "price", "universe", "macro", "news"],
    "WD03_MARKET_ANALYSIS": ["analysis", "market_analysis", "regime", "theme", "rank", "signal"],
    "WD04_QUANT_REAR": ["daily", "pipeline", "quant", "service", "validation", "current"],
    "WD05_PORTFOLIO_ANALYSIS": ["portfolio", "allocation", "analysis", "investment_portfolio", "portfolio_pipeline", "gcs"],
    "WE01_QUANT_WEEKEND_PIPELINE": ["pipeline", "quant", "validation", "current", "research", "ai"],
}

PREFERRED_COMMANDS = {
    "WD01_QUANT_FRONT": "D:/Quant/venv64/Scripts/python.exe D:/Quant/src/quant_service/run_daily_quant_pipeline.py --asof {asof} --include-etf --data-refresh-only",
}


def source_files(base_root: Path = ROOT) -> list[Path]:
    files: list[Path] = []
    for dirname in SEARCH_DIRS:
        base = base_root / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".md", ".yaml", ".yml", ".toml", ".ps1"}:
                files.append(path)
    return files


def confidence(score: int, preferred: bool) -> str:
    if preferred:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def risk_level(stage_id: str, command: str | None) -> str:
    if not command:
        return "medium"
    if command_matches_blocked_pattern(command):
        return "critical"
    if stage_id in {"WD04_QUANT_REAR", "WE01_QUANT_WEEKEND_PIPELINE"}:
        return "high"
    return "medium"


def command_for_source(path: Path) -> str:
    if path.suffix.lower() == ".py":
        return f"python {path.name}" if path.parent == path.anchor else f"python {path.as_posix()}"
    return f"review {path.as_posix()}"


def candidates_for_stage(stage_id: str, files: list[Path]) -> list[dict[str, object]]:
    keywords = STAGE_KEYWORDS[stage_id]
    candidates: list[dict[str, object]] = []
    preferred = PREFERRED_COMMANDS.get(stage_id)
    if preferred:
        source = "docs/operations/QUANT_DAILY_RESEARCH_PIPELINE_OPERATION_20260530.md"
        if "schema" in preferred:
            source = "docs/operations/UPDATE_PIPELINE_HARNESS_20260627.md"
        candidates.append(
            {
                "command": preferred,
                "source_file": source,
                "reason": "운영 문서와 기존 1차 Harness에 명시된 command 후보",
                "risk_level": risk_level(stage_id, preferred),
                "confidence": "high",
                "notes": "후보 등록용. TASK_UPDATE_HARNESS_03에서는 execute 승인하지 않음.",
            }
        )

    scored: list[tuple[int, Path]] = []
    for path in files:
        text = f"{path.name} {path}".lower()
        score = sum(1 for keyword in keywords if keyword.lower() in text)
        if score:
            scored.append((score, path))
    for score, path in sorted(scored, key=lambda item: (-item[0], str(item[1])))[:5]:
        command = command_for_source(path)
        blocked = command_matches_blocked_pattern(command)
        candidates.append(
            {
                "command": command,
                "source_file": str(path),
                "reason": f"stage keywords matched: {score}",
                "risk_level": risk_level(stage_id, command),
                "confidence": confidence(score, preferred=False),
                "notes": f"blocked pattern matched: {blocked}" if blocked else "키워드 기반 후보. 실행 인자 확인 필요.",
            }
        )
    return candidates


def render_markdown(payload: dict[str, list[dict[str, object]]]) -> str:
    lines = ["# Stage Command Candidates", ""]
    for stage_id, rows in payload.items():
        lines.extend([f"## {stage_id}", "### Candidate Commands"])
        if not rows:
            lines.append("- none")
        for row in rows:
            lines.extend(
                [
                    f"- command: {row['command']}",
                    f"  source_file: {row['source_file']}",
                    f"  reason: {row['reason']}",
                    f"  risk_level: {row['risk_level']}",
                    f"  confidence: {row['confidence']}",
                    f"  notes: {row['notes']}",
                ]
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    stages = load_stage_commands()
    roles = load_thread_roles()
    payload = {}
    for stage_id in stages:
        thread = THREAD_STAGE_ROOT.get(stage_id, "Quant")
        base_root = Path(str((roles.get(thread) or {}).get("root") or ROOT))
        payload[stage_id] = candidates_for_stage(stage_id, source_files(base_root))
    COMMAND_MAPPING_DIR.mkdir(parents=True, exist_ok=True)
    write_json(COMMAND_MAPPING_DIR / "stage_command_candidates.json", {"stages": payload})
    (COMMAND_MAPPING_DIR / "stage_command_candidates.md").write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"status": "completed", "stage_count": len(payload), "output_dir": str(COMMAND_MAPPING_DIR)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
