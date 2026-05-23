from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports" / "db_audit"

SCAN_DIRS = [
    ROOT / "src",
    ROOT / "scripts",
    ROOT / "docs",
    ROOT / "service_platform",
    ROOT / "config",
]
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".ps1",
}
IGNORE_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "venv64",
    "reports",
    "data",
}

CORE_DB_NAMES = {
    "price.db",
    "regime.db",
    "model_research.db",
    "ai_feature_ext.db",
    "dart_main.db",
    "generated_outputs.db",
    "quant_service_detail.db",
    "i_series_research.db",
    "i_series_research_strong_rsi_raw_top30_s65.db",
    "features_s3.db",
    "i_series_operational.db",
    "valuation_ai.db",
    "ai_learning.db",
    "cseries_relationship.db",
    "fundamentals.db",
    "quant_service.db",
    "tseries_operational.db",
    "security_classification.db",
}


def _mb(size: int) -> float:
    return round(size / 1024 / 1024, 2)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _text_files() -> list[Path]:
    files: list[Path] = []
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in IGNORE_PARTS for part in path.parts):
                continue
            files.append(path)
    return files


def _reference_counts(db_names: list[str]) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {name: {"count": 0, "files": []} for name in db_names}
    files = _text_files()
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name in db_names:
            if name in text:
                refs[name]["count"] += text.count(name)
                if len(refs[name]["files"]) < 12:
                    refs[name]["files"].append(_rel(path))
    return refs


def _db_meta(path: Path, *, max_tables: int = 60) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "size_mb": _mb(path.stat().st_size),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "sqlite_ok": False,
        "page_count": None,
        "freelist_count": None,
        "page_size": None,
        "free_mb": None,
        "free_ratio": None,
        "table_count": None,
        "tables": [],
        "error": None,
    }
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as con:
            con.row_factory = sqlite3.Row
            page_count = con.execute("PRAGMA page_count").fetchone()[0]
            freelist_count = con.execute("PRAGMA freelist_count").fetchone()[0]
            page_size = con.execute("PRAGMA page_size").fetchone()[0]
            table_rows = con.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
            tables = [str(row["name"]) for row in table_rows]
            meta.update(
                {
                    "sqlite_ok": True,
                    "page_count": int(page_count),
                    "freelist_count": int(freelist_count),
                    "page_size": int(page_size),
                    "free_mb": _mb(int(freelist_count) * int(page_size)),
                    "free_ratio": round(float(freelist_count) / float(page_count), 4) if page_count else None,
                    "table_count": len(tables),
                    "tables": tables[:max_tables],
                    "table_sample_truncated": len(tables) > max_tables,
                }
            )
    except Exception as exc:  # noqa: BLE001 - audit should keep going.
        meta["error"] = str(exc)
    return meta


def _classify(path: Path, meta: dict[str, Any], refs: dict[str, Any]) -> str:
    parts = {p.lower() for p in path.parts}
    name = path.name
    ref_count = int(refs.get("count") or 0)
    if "backups" in parts or name.startswith("price_before_"):
        return "archive_backup"
    if name in CORE_DB_NAMES:
        return "core_or_active"
    if ref_count > 0:
        return "referenced_research"
    if name.startswith("i_series_research_"):
        return "research_variant_review"
    if meta.get("size_bytes", 0) == 0:
        return "empty_file_review"
    return "unreferenced_review"


def _risk_notes(path: Path, meta: dict[str, Any], refs: dict[str, Any], category: str) -> list[str]:
    notes: list[str] = []
    if category == "archive_backup":
        notes.append("backup/archive candidate; exclude from active working set")
    if category == "research_variant_review":
        notes.append("I-series experiment variant; verify reproducibility need before keeping hot")
    if category == "unreferenced_review":
        notes.append("no direct filename reference found in src/scripts/docs scan")
    if meta.get("free_ratio") and float(meta["free_ratio"]) >= 0.05:
        notes.append(f"SQLite freelist {meta['free_ratio']:.1%}; VACUUM may reduce file size")
    if meta.get("table_count") and int(meta["table_count"]) > 40:
        notes.append("many tables; inspect generated/intermediate retention")
    if refs.get("count"):
        notes.append(f"referenced {refs['count']} time(s) in code/docs")
    return notes


def build_audit(include_price: bool = False) -> dict[str, Any]:
    dbs = sorted(DATA_DIR.rglob("*.db"))
    if not include_price:
        dbs = [p for p in dbs if p.name != "price.db"]
    db_names = sorted({p.name for p in dbs})
    refs = _reference_counts(db_names)
    rows: list[dict[str, Any]] = []
    duplicate_table_map: dict[str, list[str]] = defaultdict(list)
    for path in dbs:
        meta = _db_meta(path)
        ref = refs.get(path.name, {"count": 0, "files": []})
        category = _classify(path, meta, ref)
        row = {
            **meta,
            "relative_path": _rel(path),
            "category": category,
            "reference_count": int(ref.get("count") or 0),
            "reference_files": ref.get("files") or [],
        }
        row["notes"] = _risk_notes(path, meta, ref, category)
        rows.append(row)
        for table in meta.get("tables") or []:
            duplicate_table_map[table].append(_rel(path))

    total_bytes = sum(int(row["size_bytes"]) for row in rows)
    by_category: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = by_category.setdefault(row["category"], {"count": 0, "size_mb": 0.0})
        item["count"] += 1
        item["size_mb"] += float(row["size_mb"])
    for item in by_category.values():
        item["size_mb"] = round(item["size_mb"], 2)

    duplicate_tables = {
        table: paths
        for table, paths in sorted(duplicate_table_map.items())
        if len(paths) >= 3 and not table.startswith("sqlite_")
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "include_price": include_price,
        "db_count": len(rows),
        "total_size_mb": _mb(total_bytes),
        "by_category": by_category,
        "rows": sorted(rows, key=lambda r: int(r["size_bytes"]), reverse=True),
        "duplicate_table_names_count": len(duplicate_tables),
        "duplicate_table_names_sample": dict(list(duplicate_tables.items())[:80]),
    }


def _md_table(rows: list[dict[str, Any]], *, limit: int | None = None) -> list[str]:
    use = rows[:limit] if limit else rows
    lines = [
        "| category | DB | size | refs | free | note |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in use:
        notes = "; ".join(row.get("notes") or [])[:120]
        free = "" if row.get("free_ratio") is None else f"{float(row['free_ratio']):.1%}"
        lines.append(
            f"| {row['category']} | `{row['relative_path']}` | {row['size_mb']:.2f} MB | "
            f"{row['reference_count']} | {free} | {notes} |"
        )
    return lines


def write_reports(audit: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"quant_db_inventory_audit_{stamp}.json"
    md_path = out_dir / f"QUANT_DB_INVENTORY_AUDIT_{stamp}.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = audit["rows"]
    active = [r for r in rows if r["category"] == "core_or_active"]
    review = [r for r in rows if r["category"] in {"research_variant_review", "unreferenced_review", "empty_file_review"}]
    archive = [r for r in rows if r["category"] == "archive_backup"]
    vacuum = [r for r in rows if r.get("free_ratio") is not None and float(r["free_ratio"]) >= 0.05]

    lines = [
        "# Quant DB Inventory Audit",
        "",
        f"- generated_at: {audit['generated_at']}",
        f"- include_price: {audit['include_price']}",
        f"- db_count: {audit['db_count']}",
        f"- total_size: {audit['total_size_mb']:.2f} MB",
        "",
        "## Category Summary",
        "",
        "| category | count | size |",
        "| --- | ---: | ---: |",
    ]
    for category, item in sorted(audit["by_category"].items(), key=lambda kv: kv[1]["size_mb"], reverse=True):
        lines.append(f"| {category} | {item['count']} | {item['size_mb']:.2f} MB |")

    lines.extend(
        [
            "",
            "## Active/Core DBs",
            "",
            *_md_table(active),
            "",
            "## Review Candidates",
            "",
            *_md_table(review, limit=80),
            "",
            "## Archive/Backup Candidates",
            "",
            *_md_table(archive, limit=40),
            "",
            "## VACUUM Candidates",
            "",
            *_md_table(vacuum, limit=40),
            "",
            "## Duplicate Table Name Signal",
            "",
            f"- duplicate_table_names_count: {audit['duplicate_table_names_count']}",
            "- This is a structural signal only; identical table names do not prove duplicated rows.",
            "",
            "## Recommended Next Steps",
            "",
            "1. Keep active/core DBs in place.",
            "2. Move backup/archive candidates out of the hot data folder after approval.",
            "3. For I-series research variants, select keep/reproduce/archive groups by experiment history.",
            "4. Run table-level duplicate and retention audit on `generated_outputs.db`, I-series variant DBs, and `model_research.db`.",
            "5. Only after backup is confirmed, run `VACUUM` on DBs with meaningful freelist ratios.",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only audit for Quant SQLite DB inventory.")
    parser.add_argument("--include-price", action="store_true")
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    audit = build_audit(include_price=bool(args.include_price))
    md_path, json_path = write_reports(audit, Path(args.out_dir))
    print(json.dumps({"status": "ok", "markdown": str(md_path), "json": str(json_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
