from __future__ import annotations

from datetime import date
from pathlib import Path
import re


PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_ROOT = PROJECT_ROOT / "reports" / "model_upgrade_research"


def normalize_run_date(value: str | None) -> str:
    if value:
        text = str(value).strip()
        if re.fullmatch(r"\d{8}", text):
            return text
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text.replace("-", "")
        raise ValueError(f"Unsupported run date format: {value}")
    return date.today().strftime("%Y%m%d")


def normalize_asof_date(value: str | None) -> str:
    if value:
        text = str(value).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text
        if re.fullmatch(r"\d{8}", text):
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        raise ValueError(f"Unsupported asof format: {value}")
    return date.today().strftime("%Y-%m-%d")


def run_dir(run_date: str) -> Path:
    return RESEARCH_ROOT / normalize_run_date(run_date)


def ensure_run_dir(run_date: str) -> Path:
    path = run_dir(run_date)
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_research_subdir(relative_parts: str) -> Path:
    matches: list[Path] = []
    for child in RESEARCH_ROOT.iterdir():
        if not child.is_dir() or not re.fullmatch(r"\d{8}", child.name):
            continue
        candidate = child / relative_parts
        if candidate.exists():
            matches.append(candidate)
    if not matches:
        raise FileNotFoundError(f"No research subdir found for {relative_parts}")
    return max(matches, key=lambda p: next(part.name for part in [p] + list(p.parents) if re.fullmatch(r"\d{8}", part.name)))


def latest_asof_from_dir(src_dir: Path, pattern: str) -> str:
    candidates: list[str] = []
    regex = re.compile(pattern)
    for path in src_dir.iterdir():
        match = regex.match(path.name)
        if match:
            candidates.append(match.group(1))
    if not candidates:
        raise FileNotFoundError(f"No matching files for {pattern} in {src_dir}")
    return max(candidates)


def latest_file_by_regex(src_dir: Path, pattern: str) -> Path:
    candidates: list[tuple[str, Path]] = []
    regex = re.compile(pattern)
    for path in src_dir.iterdir():
        match = regex.match(path.name)
        if match:
            candidates.append((match.group(1), path))
    if not candidates:
        raise FileNotFoundError(f"No matching files for {pattern} in {src_dir}")
    return max(candidates, key=lambda item: item[0])[1]


def latest_backtest_file(src_dir: Path, pattern: str) -> Path:
    return latest_file_by_regex(src_dir, pattern)
