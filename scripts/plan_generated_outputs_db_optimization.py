from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "db" / "generated_outputs.db"
REPORT_DIR = ROOT / "reports" / "db_audit"


def _mb(value: int | float | None) -> float:
    return round(float(value or 0) / 1024 / 1024, 2)


def _connect_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def build_plan(retain_latest_n_asof: int = 3) -> dict[str, Any]:
    with _connect_ro(DB_PATH) as con:
        asofs = [
            str(row["asof_date"])
            for row in con.execute(
                "SELECT DISTINCT asof_date FROM generated_artifact_files WHERE asof_date IS NOT NULL ORDER BY asof_date DESC"
            )
        ]
        keep_asofs = set(asofs[:retain_latest_n_asof])
        latest_asof = asofs[0] if asofs else None
        file_rows = con.execute(
            """
            SELECT
                CASE WHEN asof_date IN ({placeholders}) THEN 'keep' ELSE 'archive' END AS action,
                COUNT(*) AS files,
                SUM(file_size) AS file_size,
                SUM(row_count) AS declared_rows
            FROM generated_artifact_files
            GROUP BY action
            """.format(placeholders=",".join("?" for _ in keep_asofs) or "NULL"),
            tuple(sorted(keep_asofs)),
        ).fetchall()
        by_action = {str(row["action"]): dict(row) for row in file_rows}
        linked_rows = con.execute(
            """
            SELECT
                CASE WHEN f.asof_date IN ({placeholders}) THEN 'keep' ELSE 'archive' END AS action,
                COUNT(*) AS artifact_rows
            FROM generated_artifact_rows r
            JOIN generated_artifact_files f USING (artifact_id)
            GROUP BY action
            """.format(placeholders=",".join("?" for _ in keep_asofs) or "NULL"),
            tuple(sorted(keep_asofs)),
        ).fetchall()
        row_by_action = {str(row["action"]): dict(row) for row in linked_rows}
        by_asof = [
            dict(row)
            for row in con.execute(
                """
                SELECT asof_date, COUNT(*) AS files, SUM(file_size) AS file_size, SUM(row_count) AS declared_rows
                FROM generated_artifact_files
                GROUP BY asof_date
                ORDER BY asof_date DESC
                """
            )
        ]
        by_group = [
            dict(row)
            for row in con.execute(
                """
                SELECT asof_date, artifact_group, artifact_kind,
                       COUNT(*) AS files, SUM(file_size) AS file_size, SUM(row_count) AS declared_rows
                FROM generated_artifact_files
                GROUP BY asof_date, artifact_group, artifact_kind
                ORDER BY asof_date DESC, artifact_group, artifact_kind
                """
            )
        ]
        page_count = int(con.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(con.execute("PRAGMA freelist_count").fetchone()[0])
        page_size = int(con.execute("PRAGMA page_size").fetchone()[0])

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(DB_PATH),
        "db_size_mb": _mb(DB_PATH.stat().st_size),
        "latest_asof": latest_asof,
        "retain_latest_n_asof": retain_latest_n_asof,
        "keep_asofs": sorted(keep_asofs, reverse=True),
        "archive_asofs": [asof for asof in asofs if asof not in keep_asofs],
        "asof_count": len(asofs),
        "by_action": by_action,
        "artifact_rows_by_action": row_by_action,
        "by_asof": by_asof,
        "by_group": by_group,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "free_mb": _mb(freelist_count * page_size),
        "free_ratio": round(freelist_count / page_count, 6) if page_count else None,
        "scope": "generated_outputs.db optimization planning only; no prune/VACUUM performed",
    }


def write_outputs(plan: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"generated_outputs_db_optimization_plan_{stamp}.json"
    md_path = out_dir / f"GENERATED_OUTPUTS_DB_OPTIMIZATION_PLAN_{stamp}.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    keep = plan["by_action"].get("keep", {})
    archive = plan["by_action"].get("archive", {})
    keep_rows = plan["artifact_rows_by_action"].get("keep", {})
    archive_rows = plan["artifact_rows_by_action"].get("archive", {})

    lines = [
        "# generated_outputs.db Optimization Plan",
        "",
        f"- generated_at: {plan['generated_at']}",
        f"- scope: {plan['scope']}",
        f"- db_size: {plan['db_size_mb']:.2f} MB",
        f"- latest_asof: {plan['latest_asof']}",
        f"- asof_count: {plan['asof_count']}",
        f"- retain_latest_n_asof: {plan['retain_latest_n_asof']}",
        f"- keep_asofs: {', '.join(plan['keep_asofs'])}",
        f"- archive_asof_count: {len(plan['archive_asofs'])}",
        f"- freelist: {plan['free_mb']:.2f} MB / {plan['free_ratio']:.2%}",
        "",
        "## Retention Summary",
        "",
        "| action | files | declared CSV rows | stored artifact rows | source file size |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| keep | {int(keep.get('files') or 0)} | {int(keep.get('declared_rows') or 0):,} | "
            f"{int(keep_rows.get('artifact_rows') or 0):,} | {_mb(keep.get('file_size')):.2f} MB |"
        ),
        (
            f"| archive | {int(archive.get('files') or 0)} | {int(archive.get('declared_rows') or 0):,} | "
            f"{int(archive_rows.get('artifact_rows') or 0):,} | {_mb(archive.get('file_size')):.2f} MB |"
        ),
        "",
        "## Asof Summary",
        "",
        "| asof | action | files | declared rows | source file size |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    keep_set = set(plan["keep_asofs"])
    for row in plan["by_asof"]:
        action = "keep" if row["asof_date"] in keep_set else "archive"
        lines.append(
            f"| {row['asof_date']} | {action} | {int(row['files'])} | {int(row['declared_rows'] or 0):,} | {_mb(row['file_size']):.2f} MB |"
        )

    lines.extend(
        [
            "",
            "## Proposed Execution After Approval",
            "",
            "1. Create a backup copy of `generated_outputs.db`.",
            "2. Delete rows linked to archive asof dates from `generated_artifact_rows` first.",
            "3. Delete archive asof rows from `generated_artifact_files`.",
            "4. Run `VACUUM` to reclaim file size.",
            "5. Rerun `sync_generated_csv_to_db.py --asof <latest>` after pipeline if needed.",
            "",
            "## Long-Term Rule",
            "",
            "- Default retention should be latest 3 asof snapshots unless a specific research audit needs longer history.",
            "- Raw CSV files and reports remain the source archive; this DB should stay query/cache oriented.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a non-destructive generated_outputs.db optimization plan.")
    parser.add_argument("--retain-latest-n-asof", type=int, default=3)
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    plan = build_plan(retain_latest_n_asof=args.retain_latest_n_asof)
    md_path, json_path = write_outputs(plan, Path(args.out_dir))
    print(json.dumps({"status": "ok", "markdown": str(md_path), "json": str(json_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
