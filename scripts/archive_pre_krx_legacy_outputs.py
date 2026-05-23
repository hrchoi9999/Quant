from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path


PROJECT_ROOT = Path(r"D:\Quant")
ARCHIVE_ROOT = PROJECT_ROOT / "archive" / "legacy_pre_krx"


@dataclass(frozen=True)
class ArchiveTarget:
    label: str
    source: Path
    destination: Path
    reason: str


def _count_files_and_bytes(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    count = 0
    size = 0
    for item in path.rglob("*"):
        if item.is_file():
            count += 1
            size += int(item.stat().st_size)
    return count, size


def _safe_resolve(path: Path) -> Path:
    return path.resolve(strict=False)


def _assert_safe_move(source: Path, destination: Path) -> None:
    src = _safe_resolve(source)
    dst = _safe_resolve(destination)
    root = _safe_resolve(PROJECT_ROOT)
    archive = _safe_resolve(ARCHIVE_ROOT)
    if root not in src.parents and src != root:
        raise RuntimeError(f"source is outside project root: {src}")
    if archive not in dst.parents and dst != archive:
        raise RuntimeError(f"destination is outside archive root: {dst}")
    if not source.exists():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)


def _default_targets(run_stamp: str) -> list[ArchiveTarget]:
    archive_run_root = ARCHIVE_ROOT / run_stamp
    return [
        ArchiveTarget(
            label="precheck_20260417_before",
            source=PROJECT_ROOT / r"reports\historical_rebase\precheck_20260417\before",
            destination=archive_run_root / r"reports\historical_rebase\precheck_20260417\before",
            reason="Clean pre-KRX baseline backup used for old/new model-output comparison.",
        ),
        ArchiveTarget(
            label="krx_rebase_20260417_before",
            source=PROJECT_ROOT / r"reports\historical_rebase\krx_rebase_20260417\before",
            destination=archive_run_root / r"reports\historical_rebase\krx_rebase_20260417\before",
            reason="Intermediate pre-KRX backup captured during the KRX rebase execution.",
        ),
    ]


def _write_pointer(source_parent: Path, target: ArchiveTarget, manifest_path: Path) -> None:
    source_parent.mkdir(parents=True, exist_ok=True)
    pointer = source_parent / "LEGACY_ARCHIVED_README.md"
    pointer.write_text(
        "\n".join(
            [
                "# Legacy Pre-KRX Archive Pointer",
                "",
                f"- archived_label: `{target.label}`",
                f"- archived_at: `{datetime.now().replace(microsecond=0).isoformat()}`",
                f"- archive_destination: `{target.destination}`",
                f"- archive_manifest: `{manifest_path}`",
                f"- reason: {target.reason}",
                "",
                "This folder intentionally no longer contains the pre-KRX baseline files.",
                "Use the archive destination above for audit, comparison, or rollback evidence.",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive pre-KRX legacy output bundles out of operational report paths.")
    parser.add_argument("--asof", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--execute", action="store_true", help="Move target folders into archive. Default is dry-run.")
    args = parser.parse_args()

    run_stamp = str(args.asof).replace("-", "")
    targets = _default_targets(run_stamp)
    archive_run_root = ARCHIVE_ROOT / run_stamp
    archive_run_root.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, object]] = []
    for target in targets:
        exists = target.source.exists()
        file_count, byte_count = _count_files_and_bytes(target.source)
        row = {
            **asdict(target),
            "source": str(target.source),
            "destination": str(target.destination),
            "exists": exists,
            "file_count": file_count,
            "byte_count": byte_count,
            "mode": "execute" if args.execute else "dry-run",
        }
        manifest_rows.append(row)
        if not exists:
            print(f"[SKIP] missing label={target.label} source={target.source}")
            continue
        print(f"[CANDIDATE] label={target.label} files={file_count} bytes={byte_count} source={target.source}")
        if args.execute:
            _assert_safe_move(target.source, target.destination)
            target.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target.source), str(target.destination))
            print(f"[ARCHIVED] label={target.label} destination={target.destination}")

    manifest = {
        "asof": args.asof,
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "mode": "execute" if args.execute else "dry-run",
        "archive_root": str(ARCHIVE_ROOT),
        "targets": manifest_rows,
    }
    manifest_path = archive_run_root / "archive_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.execute:
        for target in targets:
            if target.destination.exists():
                _write_pointer(target.source.parent, target, manifest_path)

    print(f"[DONE] manifest={manifest_path}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
