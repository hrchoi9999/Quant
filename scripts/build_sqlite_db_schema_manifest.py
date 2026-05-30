from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_DIRS = [
    ROOT / "data" / "db",
    ROOT / "data" / "db_s3",
    ROOT / "trading_sign" / "data" / "db",
]
OUT_DIR = ROOT / "reports" / "data_quality" / "db_schema_manifest"

DB_ROLE_RULES = {
    "price.db": "operational_source",
    "regime.db": "operational_feature",
    "fundamentals.db": "operational_feature",
    "quant_service.db": "operational_publish",
    "quant_service_detail.db": "operational_publish_detail",
    "generated_outputs.db": "generated_output_archive",
    "model_research.db": "research_archive",
    "ai_learning.db": "ai_operational_research",
    "valuation_ai.db": "ai_operational_research",
    "tseries_operational.db": "strategy_operational",
    "i_series_operational.db": "strategy_operational",
    "trading_sign.db": "trading_sign_operational",
}


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _db_role(path: Path) -> str:
    name = path.name
    if name in DB_ROLE_RULES:
        return DB_ROLE_RULES[name]
    if "research" in name:
        return "research_archive"
    if name.startswith("features_"):
        return "feature_store"
    return "unclassified"


def _scalar(con: sqlite3.Connection, sql: str) -> Any:
    try:
        row = con.execute(sql).fetchone()
    except sqlite3.DatabaseError:
        return None
    return row[0] if row else None


def _schema_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return [
        {"type": row[0], "name": row[1], "table": row[2], "sql": row[3] or ""}
        for row in rows
    ]


def _schema_hash(rows: list[dict[str, Any]]) -> str:
    text = "\n".join(f"{row['type']}|{row['name']}|{row['table']}|{row['sql']}" for row in rows)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _table_rows(con: sqlite3.Connection, tables: list[str], include_counts: bool, max_tables: int) -> list[dict[str, Any]]:
    out = []
    for table in tables[:max_tables]:
        item: dict[str, Any] = {"table": table}
        cols = con.execute(f"PRAGMA table_info({table})").fetchall()
        item["column_count"] = len(cols)
        item["columns"] = [{"name": col[1], "type": col[2], "pk": int(col[5])} for col in cols]
        if include_counts:
            item["row_count"] = _scalar(con, f"SELECT COUNT(*) FROM {table}")
        out.append(item)
    return out


def _inspect_db(path: Path, include_counts: bool, max_tables: int) -> dict[str, Any]:
    stat = path.stat()
    item: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "role": _db_role(path),
        "size_bytes": int(stat.st_size),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "status": "ok",
    }
    if stat.st_size == 0:
        item.update({"status": "empty_file", "tables": [], "schema_hash": None})
        return item
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            schema = _schema_rows(con)
            tables = [row["name"] for row in schema if row["type"] == "table"]
            views = [row["name"] for row in schema if row["type"] == "view"]
            item.update(
                {
                    "page_count": _scalar(con, "PRAGMA page_count"),
                    "page_size": _scalar(con, "PRAGMA page_size"),
                    "freelist_count": _scalar(con, "PRAGMA freelist_count"),
                    "journal_mode": _scalar(con, "PRAGMA journal_mode"),
                    "table_count": len(tables),
                    "view_count": len(views),
                    "schema_hash": _schema_hash(schema),
                    "tables": _table_rows(con, tables, include_counts, max_tables),
                    "views": views,
                }
            )
            free_pages = item.get("freelist_count") or 0
            page_size = item.get("page_size") or 0
            item["estimated_free_bytes"] = int(free_pages) * int(page_size)
    except Exception as exc:
        item.update({"status": "error", "error": str(exc), "tables": [], "schema_hash": None})
    return item


def main() -> None:
    ap = argparse.ArgumentParser(description="Build SQLite DB schema/size manifest for Quant operation.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument("--db-dir", action="append", default=None, help="Directory containing .db files. Can be repeated.")
    ap.add_argument("--include-row-counts", action="store_true", help="Count rows per table. Use mainly for weekend/research checks.")
    ap.add_argument("--max-tables-per-db", type=int, default=200)
    args = ap.parse_args()

    db_dirs = [Path(p) for p in args.db_dir] if args.db_dir else DEFAULT_DB_DIRS
    dbs = sorted({path for db_dir in db_dirs if db_dir.exists() for path in db_dir.glob("*.db")})
    manifest = {
        "source_name": "sqlite_db_schema_manifest",
        "asof": args.asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "include_row_counts": bool(args.include_row_counts),
        "db_count": len(dbs),
        "total_size_bytes": sum(path.stat().st_size for path in dbs),
        "db_dirs": [str(path) for path in db_dirs],
        "databases": [_inspect_db(path, bool(args.include_row_counts), int(args.max_tables_per_db)) for path in dbs],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(str(args.asof))
    dated = OUT_DIR / f"sqlite_db_schema_manifest_{token}.json"
    current = OUT_DIR / "sqlite_db_schema_manifest_current.json"
    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    dated.write_text(text, encoding="utf-8")
    current.write_text(text, encoding="utf-8")
    print(json.dumps({"status": "ok", "asof": args.asof, "db_count": len(dbs), "out": str(dated)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
