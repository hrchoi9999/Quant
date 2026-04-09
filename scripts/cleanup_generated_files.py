from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(r"D:\Quant")
ARCHIVE_ROOT = PROJECT_ROOT / "archive" / "generated_retention"


@dataclass(frozen=True)
class CleanupRule:
    name: str
    root: Path
    retention_days: int


RULES: tuple[CleanupRule, ...] = (
    CleanupRule("universe_snapshots", PROJECT_ROOT / r"data\universe", 30),
    CleanupRule("user_reports", PROJECT_ROOT / r"reports\redbot_user_reports", 45),
    CleanupRule("backtest_router", PROJECT_ROOT / r"reports\backtest_router", 60),
    CleanupRule("model_compare", PROJECT_ROOT / r"reports\model_compare", 60),
    CleanupRule("backtest_s3_dev", PROJECT_ROOT / r"reports\backtest_s3_dev", 60),
    CleanupRule("backtest_regime_refactor", PROJECT_ROOT / r"reports\backtest_regime_refactor", 60),
    CleanupRule("backtest_etf_allocation", PROJECT_ROOT / r"reports\backtest_etf_allocation", 60),
    CleanupRule("service_analytics_review", PROJECT_ROOT / r"reports\service_analytics_review", 21),
)


DATE_TOKEN_RE = re.compile(r"(20\d{6})")


def _extract_asof_from_name(path: Path) -> date | None:
    tokens = DATE_TOKEN_RE.findall(path.stem)
    if not tokens:
        return None
    for token in reversed(tokens):
        try:
            return datetime.strptime(token, "%Y%m%d").date()
        except ValueError:
            continue
    return None


def _is_protected(path: Path) -> bool:
    name = path.name.lower()
    if any(token in name for token in ("latest", "current", "manifest")):
        return True
    if "public_data" in {part.lower() for part in path.parts}:
        return True
    return False


def _iter_candidate_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (p for p in root.rglob("*") if p.is_file())


def _archive_target(run_stamp: str, path: Path) -> Path:
    rel = path.relative_to(PROJECT_ROOT)
    return ARCHIVE_ROOT / run_stamp / rel


def main() -> None:
    ap = argparse.ArgumentParser(description="Archive old generated files with dated filenames.")
    ap.add_argument("--asof", default=date.today().strftime("%Y-%m-%d"), help="Reference date for retention cutoff.")
    ap.add_argument("--execute", action="store_true", help="Move files into archive. Default is dry-run.")
    ap.add_argument("--write-manifest", action="store_true", help="Write a JSON manifest under the archive run directory.")
    args = ap.parse_args()

    asof = datetime.strptime(args.asof, "%Y-%m-%d").date()
    run_stamp = asof.strftime("%Y%m%d")
    summary: list[dict[str, object]] = []
    total_candidates = 0
    total_archived = 0

    for rule in RULES:
        archived_for_rule = 0
        scanned = 0
        for path in _iter_candidate_files(rule.root):
            scanned += 1
            if _is_protected(path):
                continue
            dated = _extract_asof_from_name(path)
            if dated is None:
                continue
            age_days = (asof - dated).days
            if age_days <= rule.retention_days:
                continue
            total_candidates += 1
            target = _archive_target(run_stamp, path)
            print(
                f"[CANDIDATE] rule={rule.name} age_days={age_days} "
                f"retention={rule.retention_days} file={path}"
            )
            if args.execute:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(target))
                archived_for_rule += 1
                total_archived += 1
                print(f"[ARCHIVED] -> {target}")
        summary.append(
            {
                "rule": rule.name,
                "root": str(rule.root),
                "retention_days": rule.retention_days,
                "scanned_files": scanned,
                "archived_files": archived_for_rule,
            }
        )

    manifest = {
        "asof": args.asof,
        "mode": "execute" if args.execute else "dry-run",
        "archive_root": str(ARCHIVE_ROOT),
        "candidate_count": total_candidates,
        "archived_count": total_archived,
        "rules": summary,
    }

    if args.write_manifest:
        manifest_path = ARCHIVE_ROOT / run_stamp / "cleanup_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] manifest={manifest_path}")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
