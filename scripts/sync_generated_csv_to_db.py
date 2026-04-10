from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(r"D:\Quant")
DEFAULT_DB = PROJECT_ROOT / r"data\db\generated_outputs.db"
DATE_TOKEN_RE = re.compile(r"(20\d{6})")

SCAN_ROOTS = (
    PROJECT_ROOT / r"data\universe",
    PROJECT_ROOT / r"reports\backtest_router",
    PROJECT_ROOT / r"reports\model_compare",
    PROJECT_ROOT / r"reports\backtest_s3_dev",
    PROJECT_ROOT / r"reports\backtest_regime_refactor",
    PROJECT_ROOT / r"reports\backtest_etf_allocation",
    PROJECT_ROOT / r"reports\redbot_user_reports",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _date_tokens(path: Path) -> list[str]:
    return DATE_TOKEN_RE.findall(path.stem)


def _asof_from_path(path: Path) -> str | None:
    tokens = _date_tokens(path)
    if not tokens:
        return None
    return f"{tokens[-1][0:4]}-{tokens[-1][4:6]}-{tokens[-1][6:8]}"


def _artifact_group(path: Path) -> str:
    rel = path.relative_to(PROJECT_ROOT)
    parts = [p.lower() for p in rel.parts]
    if parts[:2] == ["data", "universe"]:
        return "universe"
    if len(parts) >= 2 and parts[0] == "reports":
        return parts[1]
    return "other"


def _artifact_kind(path: Path) -> str:
    stem = path.stem.lower()
    for key in [
        "summary",
        "periods",
        "yearly",
        "regime",
        "cost",
        "weights",
        "trades",
        "decisions",
        "equity",
        "holdings",
        "nav",
        "snapshot",
        "compare",
    ]:
        if key in stem:
            return key
    if "universe" in stem:
        return "universe"
    return "csv"


def _is_candidate(path: Path, asof: str | None, all_dates: bool) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    name = path.name.lower()
    if "latest" in name or "current" in name:
        return False
    path_asof = _asof_from_path(path)
    if path_asof is None:
        return False
    return all_dates or path_asof == asof


def _iter_files(asof: str | None, all_dates: bool) -> Iterable[Path]:
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            if _is_candidate(path, asof, all_dates):
                yield path


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS generated_artifact_files (
            artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
            rel_path TEXT NOT NULL UNIQUE,
            asof_date TEXT,
            artifact_group TEXT NOT NULL,
            artifact_kind TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_mtime TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            column_json TEXT NOT NULL,
            synced_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS generated_artifact_rows (
            artifact_id INTEGER NOT NULL,
            row_no INTEGER NOT NULL,
            row_json TEXT NOT NULL,
            PRIMARY KEY (artifact_id, row_no),
            FOREIGN KEY (artifact_id) REFERENCES generated_artifact_files(artifact_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_generated_artifact_files_asof
            ON generated_artifact_files(asof_date, artifact_group, artifact_kind);
        CREATE INDEX IF NOT EXISTS idx_generated_artifact_rows_artifact
            ON generated_artifact_rows(artifact_id);
        """
    )


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str | None]]]:
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                columns = list(reader.fieldnames or [])
                rows = [dict(row) for row in reader]
            return columns, rows
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, f"Cannot decode {path}")


def _upsert_artifact(con: sqlite3.Connection, path: Path, max_rows: int | None) -> tuple[bool, int]:
    rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    stat = path.stat()
    digest = _sha256(path)
    row = con.execute(
        "SELECT artifact_id, sha256 FROM generated_artifact_files WHERE rel_path=?",
        (rel,),
    ).fetchone()
    if row and row[1] == digest:
        return False, 0

    columns, rows = _read_csv_rows(path)
    if max_rows is not None and len(rows) > max_rows:
        rows = rows[:max_rows]
    now = datetime.now().isoformat(timespec="seconds")
    file_mtime = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")

    if row:
        artifact_id = int(row[0])
        con.execute("DELETE FROM generated_artifact_rows WHERE artifact_id=?", (artifact_id,))
        con.execute(
            """
            UPDATE generated_artifact_files
               SET asof_date=?, artifact_group=?, artifact_kind=?, file_size=?, file_mtime=?,
                   sha256=?, row_count=?, column_json=?, synced_at=?
             WHERE artifact_id=?
            """,
            (
                _asof_from_path(path),
                _artifact_group(path),
                _artifact_kind(path),
                stat.st_size,
                file_mtime,
                digest,
                len(rows),
                json.dumps(columns, ensure_ascii=False),
                now,
                artifact_id,
            ),
        )
    else:
        cur = con.execute(
            """
            INSERT INTO generated_artifact_files
            (rel_path, asof_date, artifact_group, artifact_kind, file_size, file_mtime,
             sha256, row_count, column_json, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rel,
                _asof_from_path(path),
                _artifact_group(path),
                _artifact_kind(path),
                stat.st_size,
                file_mtime,
                digest,
                len(rows),
                json.dumps(columns, ensure_ascii=False),
                now,
            ),
        )
        artifact_id = int(cur.lastrowid)

    con.executemany(
        "INSERT INTO generated_artifact_rows (artifact_id, row_no, row_json) VALUES (?, ?, ?)",
        [
            (artifact_id, i + 1, json.dumps(row_obj, ensure_ascii=False))
            for i, row_obj in enumerate(rows)
        ],
    )
    return True, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync dated generated CSV outputs into a queryable SQLite DB.")
    parser.add_argument("--asof", default=None, help="YYYY-MM-DD. Sync files whose final date token matches this date.")
    parser.add_argument("--all", action="store_true", help="Sync all dated CSV files under configured roots.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-rows", type=int, default=None, help="Optional safety cap per artifact.")
    args = parser.parse_args()

    if not args.all and not args.asof:
        raise SystemExit("Provide --asof YYYY-MM-DD or --all")

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    files = list(_iter_files(args.asof, args.all))

    con = sqlite3.connect(str(db_path))
    try:
        _ensure_schema(con)
        updated = 0
        rows_synced = 0
        for path in files:
            changed, nrows = _upsert_artifact(con, path, args.max_rows)
            if changed:
                updated += 1
                rows_synced += nrows
                print(f"[SYNCED] rows={nrows} file={path}")
        con.commit()
    finally:
        con.close()

    print(json.dumps({
        "db": str(db_path),
        "asof": args.asof,
        "all": bool(args.all),
        "scanned_files": len(files),
        "updated_files": updated,
        "rows_synced": rows_synced,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
