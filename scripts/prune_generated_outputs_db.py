from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "db" / "generated_outputs.db"
BACKUP_DIR = ROOT / "data" / "db" / "backups"
REPORT_DIR = ROOT / "reports" / "db_audit"


def _mb(value: int | float | None) -> float:
    return round(float(value or 0) / 1024 / 1024, 2)


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=60)
    con.row_factory = sqlite3.Row
    return con


def _fetch_state(con: sqlite3.Connection, keep_asofs: set[str]) -> dict[str, Any]:
    all_asofs = [
        str(row["asof_date"])
        for row in con.execute(
            "SELECT DISTINCT asof_date FROM generated_artifact_files WHERE asof_date IS NOT NULL ORDER BY asof_date DESC"
        )
    ]
    placeholders = ",".join("?" for _ in keep_asofs) or "NULL"
    params = tuple(sorted(keep_asofs))
    file_rows = con.execute(
        f"""
        SELECT
            CASE WHEN asof_date IN ({placeholders}) THEN 'keep' ELSE 'prune' END AS action,
            COUNT(*) AS files,
            SUM(file_size) AS file_size,
            SUM(row_count) AS declared_rows
        FROM generated_artifact_files
        GROUP BY action
        """,
        params,
    ).fetchall()
    linked_rows = con.execute(
        f"""
        SELECT
            CASE WHEN f.asof_date IN ({placeholders}) THEN 'keep' ELSE 'prune' END AS action,
            COUNT(*) AS artifact_rows
        FROM generated_artifact_rows r
        JOIN generated_artifact_files f USING (artifact_id)
        GROUP BY action
        """,
        params,
    ).fetchall()
    by_action = {str(row["action"]): dict(row) for row in file_rows}
    rows_by_action = {str(row["action"]): dict(row) for row in linked_rows}
    total_files = int(con.execute("SELECT COUNT(*) FROM generated_artifact_files").fetchone()[0])
    total_rows = int(con.execute("SELECT COUNT(*) FROM generated_artifact_rows").fetchone()[0])
    return {
        "asofs": all_asofs,
        "by_action": by_action,
        "artifact_rows_by_action": rows_by_action,
        "total_files": total_files,
        "total_rows": total_rows,
    }


def _latest_asofs(con: sqlite3.Connection, retain_latest_n_asof: int) -> list[str]:
    rows = con.execute(
        """
        SELECT DISTINCT asof_date
        FROM generated_artifact_files
        WHERE asof_date IS NOT NULL
        ORDER BY asof_date DESC
        LIMIT ?
        """,
        (retain_latest_n_asof,),
    ).fetchall()
    return [str(row["asof_date"]) for row in rows]


def _backup_db(db_path: Path, backup_dir: Path, stamp: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"generated_outputs_before_prune_{stamp}.db"
    if backup_path.exists():
        raise SystemExit(f"Backup already exists: {backup_path}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def prune(retain_latest_n_asof: int, *, dry_run: bool = False) -> dict[str, Any]:
    if retain_latest_n_asof < 1:
        raise SystemExit("--retain-latest-n-asof must be >= 1")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    size_before = DB_PATH.stat().st_size
    backup_path: Path | None = None

    with _connect(DB_PATH) as con:
        keep_asofs = set(_latest_asofs(con, retain_latest_n_asof))
        if not keep_asofs:
            raise SystemExit("No asof snapshots found in generated_outputs.db")
        before = _fetch_state(con, keep_asofs)
        prune_files = int((before["by_action"].get("prune") or {}).get("files") or 0)
        prune_rows = int((before["artifact_rows_by_action"].get("prune") or {}).get("artifact_rows") or 0)
        if dry_run:
            return {
                "status": "dry_run",
                "db": str(DB_PATH),
                "retain_latest_n_asof": retain_latest_n_asof,
                "keep_asofs": sorted(keep_asofs, reverse=True),
                "before": before,
                "would_prune_files": prune_files,
                "would_prune_artifact_rows": prune_rows,
                "size_before_mb": _mb(size_before),
            }

    backup_path = _backup_db(DB_PATH, BACKUP_DIR, stamp)

    with _connect(DB_PATH) as con:
        keep_asofs = set(_latest_asofs(con, retain_latest_n_asof))
        before = _fetch_state(con, keep_asofs)
        placeholders = ",".join("?" for _ in keep_asofs)
        params = tuple(sorted(keep_asofs))
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("BEGIN")
        con.execute(
            f"""
            DELETE FROM generated_artifact_rows
            WHERE artifact_id IN (
                SELECT artifact_id
                FROM generated_artifact_files
                WHERE asof_date NOT IN ({placeholders})
                   OR asof_date IS NULL
            )
            """,
            params,
        )
        deleted_rows = int(con.execute("SELECT changes()").fetchone()[0])
        con.execute(
            f"""
            DELETE FROM generated_artifact_files
            WHERE asof_date NOT IN ({placeholders})
               OR asof_date IS NULL
            """,
            params,
        )
        deleted_files = int(con.execute("SELECT changes()").fetchone()[0])
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    size_after_delete = DB_PATH.stat().st_size
    with _connect(DB_PATH) as con:
        con.execute("VACUUM")
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        after = _fetch_state(con, keep_asofs)
    size_after_vacuum = DB_PATH.stat().st_size

    result = {
        "status": "ok",
        "db": str(DB_PATH),
        "backup": str(backup_path),
        "retain_latest_n_asof": retain_latest_n_asof,
        "keep_asofs": sorted(keep_asofs, reverse=True),
        "before": before,
        "after": after,
        "deleted_files": deleted_files,
        "deleted_artifact_rows": deleted_rows,
        "size_before_mb": _mb(size_before),
        "size_after_delete_mb": _mb(size_after_delete),
        "size_after_vacuum_mb": _mb(size_after_vacuum),
        "reclaimed_mb": _mb(size_before - size_after_vacuum),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return result


def write_report(result: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"GENERATED_OUTPUTS_DB_PRUNE_RESULT_{stamp}.md"
    json_path = out_dir / f"generated_outputs_db_prune_result_{stamp}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    before_keep = result["before"]["by_action"].get("keep", {})
    before_prune = result["before"]["by_action"].get("prune", {})
    after_keep = result["after"]["by_action"].get("keep", {})
    after_prune = result["after"]["by_action"].get("prune", {})
    before_keep_rows = result["before"]["artifact_rows_by_action"].get("keep", {})
    before_prune_rows = result["before"]["artifact_rows_by_action"].get("prune", {})
    after_keep_rows = result["after"]["artifact_rows_by_action"].get("keep", {})
    after_prune_rows = result["after"]["artifact_rows_by_action"].get("prune", {})

    lines = [
        "# generated_outputs.db Prune Result",
        "",
        f"- generated_at: {result['generated_at']}",
        f"- status: {result['status']}",
        f"- backup: `{result['backup']}`",
        f"- keep_asofs: {', '.join(result['keep_asofs'])}",
        f"- deleted_files: {result['deleted_files']:,}",
        f"- deleted_artifact_rows: {result['deleted_artifact_rows']:,}",
        f"- size_before: {result['size_before_mb']:.2f} MB",
        f"- size_after_delete: {result['size_after_delete_mb']:.2f} MB",
        f"- size_after_vacuum: {result['size_after_vacuum_mb']:.2f} MB",
        f"- reclaimed: {result['reclaimed_mb']:.2f} MB",
        "",
        "## Before/After",
        "",
        "| state | action | files | declared rows | artifact rows |",
        "| --- | --- | ---: | ---: | ---: |",
        f"| before | keep | {int(before_keep.get('files') or 0):,} | {int(before_keep.get('declared_rows') or 0):,} | {int(before_keep_rows.get('artifact_rows') or 0):,} |",
        f"| before | prune | {int(before_prune.get('files') or 0):,} | {int(before_prune.get('declared_rows') or 0):,} | {int(before_prune_rows.get('artifact_rows') or 0):,} |",
        f"| after | keep | {int(after_keep.get('files') or 0):,} | {int(after_keep.get('declared_rows') or 0):,} | {int(after_keep_rows.get('artifact_rows') or 0):,} |",
        f"| after | prune | {int(after_prune.get('files') or 0):,} | {int(after_prune.get('declared_rows') or 0):,} | {int(after_prune_rows.get('artifact_rows') or 0):,} |",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune generated_outputs.db old artifact snapshots after making a backup.")
    parser.add_argument("--retain-latest-n-asof", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    result = prune(args.retain_latest_n_asof, dry_run=bool(args.dry_run))
    report = None if args.dry_run else write_report(result, Path(args.out_dir))
    print(json.dumps({"result": result, "report": str(report) if report else None}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
