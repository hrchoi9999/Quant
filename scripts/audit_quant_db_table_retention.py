from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_DIR = ROOT / "data" / "db"
REPORT_DIR = ROOT / "reports" / "db_audit"

DATE_COL_HINTS = (
    "date",
    "asof",
    "signal_date",
    "end_date",
    "next_signal_date",
    "feature_date",
    "created_at",
    "generated_at",
    "synced_at",
)
MODEL_COLS = ("model_code", "model", "strategy", "strategy_code")
HORIZON_COLS = ("horizon", "target")
ID_COLS = ("ticker", "code", "symbol", "asset_id", "artifact_id")
RANK_COLS = ("bucket", "feature", "filter_label", "target_label", "stage")


def _mb(size: int | float | None) -> float | None:
    if size is None:
        return None
    return round(float(size) / 1024 / 1024, 2)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def _tables(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def _columns(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = con.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    return [
        {
            "cid": int(row["cid"]),
            "name": str(row["name"]),
            "type": str(row["type"] or ""),
            "notnull": int(row["notnull"]),
            "pk": int(row["pk"]),
        }
        for row in rows
    ]


def _dbstat_sizes(con: sqlite3.Connection) -> dict[str, int]:
    try:
        rows = con.execute("SELECT name, SUM(pgsize) AS bytes FROM dbstat GROUP BY name").fetchall()
        return {str(row["name"]): int(row["bytes"] or 0) for row in rows}
    except sqlite3.DatabaseError:
        pass
    try:
        rows = con.execute("SELECT name, SUM(pgsize) AS bytes FROM temp.dbstat GROUP BY name").fetchall()
        return {str(row["name"]): int(row["bytes"] or 0) for row in rows}
    except sqlite3.DatabaseError:
        return {}


def _row_count(con: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(con.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0])
    except sqlite3.DatabaseError:
        return None


def _date_columns(columns: list[str]) -> list[str]:
    found: list[str] = []
    for col in columns:
        lower = col.lower()
        if any(hint == lower or hint in lower for hint in DATE_COL_HINTS):
            found.append(col)
    return found


def _safe_minmax_count(con: sqlite3.Connection, table: str, col: str) -> dict[str, Any] | None:
    try:
        row = con.execute(
            f"""
            SELECT
                MIN({_quote(col)}) AS min_value,
                MAX({_quote(col)}) AS max_value,
                COUNT(DISTINCT {_quote(col)}) AS distinct_count
            FROM {_quote(table)}
            WHERE {_quote(col)} IS NOT NULL
            """
        ).fetchone()
        return {
            "column": col,
            "min": row["min_value"],
            "max": row["max_value"],
            "distinct_count": int(row["distinct_count"] or 0),
        }
    except sqlite3.DatabaseError:
        return None


def _latest_rows(con: sqlite3.Connection, table: str, col: str, max_value: Any) -> int | None:
    if max_value is None:
        return None
    try:
        return int(
            con.execute(
                f"SELECT COUNT(*) FROM {_quote(table)} WHERE {_quote(col)} = ?",
                (max_value,),
            ).fetchone()[0]
        )
    except sqlite3.DatabaseError:
        return None


def _natural_key_candidates(table: str, columns: list[str]) -> list[list[str]]:
    colset = set(columns)
    candidates: list[list[str]] = []

    def add(cols: list[str]) -> None:
        if all(col in colset for col in cols) and cols not in candidates:
            candidates.append(cols)

    add(["artifact_id", "row_no"])
    add(["rel_path", "asof_date", "artifact_group", "artifact_kind"])
    add(["model_code", "horizon", "signal_date", "end_date", "ticker"])
    add(["model_code", "horizon", "signal_date", "ticker"])
    add(["model_code", "signal_date", "ticker"])
    add(["horizon", "signal_date", "ticker"])
    add(["signal_date", "ticker"])
    add(["date", "ticker"])
    add(["asof_date", "ticker"])
    add(["feature_date", "ticker"])
    add(["ticker", "date"])
    add(["horizon", "current_bucket", "next_bucket"])
    add(["horizon", "bucket", "next_bucket"])
    add(["horizon", "bucket", "feature"])
    add(["horizon", "feature"])
    add(["feature", "model_code"])
    add(["model_code", "start", "end"])

    if not candidates:
        dates = _date_columns(columns)
        ids = [col for col in ID_COLS if col in colset]
        models = [col for col in MODEL_COLS if col in colset]
        horizons = [col for col in HORIZON_COLS if col in colset]
        ranks = [col for col in RANK_COLS if col in colset]
        if dates and ids:
            add(models[:1] + horizons[:1] + [dates[0], ids[0]])
            add([dates[0], ids[0]])
        elif dates:
            add(models[:1] + horizons[:1] + [dates[0]] + ranks[:1])
            add([dates[0]] + ranks[:1])
        elif ids:
            add(models[:1] + horizons[:1] + [ids[0]] + ranks[:1])

    return [cols for cols in candidates if cols]


def _duplicate_signal(
    con: sqlite3.Connection,
    table: str,
    key_cols: list[str],
    row_count: int | None,
    max_rows: int,
) -> dict[str, Any] | None:
    if row_count is None or row_count == 0 or row_count > max_rows:
        return None
    cols_sql = ", ".join(_quote(col) for col in key_cols)
    try:
        row = con.execute(
            f"""
            SELECT
                COUNT(*) AS key_count,
                SUM(CASE WHEN n > 1 THEN 1 ELSE 0 END) AS duplicate_key_groups,
                SUM(CASE WHEN n > 1 THEN n - 1 ELSE 0 END) AS duplicate_extra_rows,
                MAX(n) AS max_group_size
            FROM (
                SELECT {cols_sql}, COUNT(*) AS n
                FROM {_quote(table)}
                GROUP BY {cols_sql}
            )
            """
        ).fetchone()
        extra = int(row["duplicate_extra_rows"] or 0)
        return {
            "key_cols": key_cols,
            "key_count": int(row["key_count"] or 0),
            "duplicate_key_groups": int(row["duplicate_key_groups"] or 0),
            "duplicate_extra_rows": extra,
            "max_group_size": int(row["max_group_size"] or 0),
            "duplicate_extra_ratio": round(extra / row_count, 6) if row_count else 0.0,
        }
    except sqlite3.DatabaseError as exc:
        return {"key_cols": key_cols, "error": str(exc)}


def _sample_fingerprint(con: sqlite3.Connection, table: str, columns: list[str], key_cols: list[str]) -> str | None:
    if not columns:
        return None
    order_cols = key_cols if key_cols else columns[:3]
    select_cols = columns[:12]
    sql = (
        f"SELECT {', '.join(_quote(col) for col in select_cols)} "
        f"FROM {_quote(table)} "
        f"ORDER BY {', '.join(_quote(col) for col in order_cols)} "
        "LIMIT 200"
    )
    try:
        digest = hashlib.sha256()
        for row in con.execute(sql):
            digest.update(json.dumps(list(row), ensure_ascii=False, default=str).encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()[:16]
    except sqlite3.DatabaseError:
        return None


def _table_audit(path: Path, table: str, con: sqlite3.Connection, table_bytes: int | None, max_dup_rows: int) -> dict[str, Any]:
    col_meta = _columns(con, table)
    col_names = [col["name"] for col in col_meta]
    row_count = _row_count(con, table)
    date_stats = [
        stat
        for col in _date_columns(col_names)
        if (stat := _safe_minmax_count(con, table, col)) is not None
    ]
    primary_date = max(date_stats, key=lambda stat: int(stat["distinct_count"] or 0), default=None)
    latest_count = _latest_rows(con, table, primary_date["column"], primary_date["max"]) if primary_date else None
    older_rows = (row_count - latest_count) if row_count is not None and latest_count is not None else None

    duplicate_checks: list[dict[str, Any]] = []
    for key_cols in _natural_key_candidates(table, col_names)[:3]:
        signal = _duplicate_signal(con, table, key_cols, row_count, max_dup_rows)
        if signal:
            duplicate_checks.append(signal)

    key_for_hash = duplicate_checks[0]["key_cols"] if duplicate_checks and "key_cols" in duplicate_checks[0] else []
    return {
        "db": path.name,
        "relative_db_path": _rel(path),
        "table": table,
        "table_bytes": table_bytes,
        "table_mb": _mb(table_bytes),
        "row_count": row_count,
        "column_count": len(col_names),
        "columns": col_names,
        "date_stats": date_stats,
        "primary_date_col": primary_date["column"] if primary_date else None,
        "primary_min": primary_date["min"] if primary_date else None,
        "primary_max": primary_date["max"] if primary_date else None,
        "primary_distinct_count": primary_date["distinct_count"] if primary_date else None,
        "latest_rows": latest_count,
        "older_rows": older_rows,
        "older_row_ratio": round(older_rows / row_count, 6) if row_count and older_rows is not None else None,
        "duplicate_checks": duplicate_checks,
        "sample_fingerprint": _sample_fingerprint(con, table, col_names, key_for_hash),
    }


def _retention_notes(row: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    table = str(row["table"]).lower()
    db = str(row["db"]).lower()
    dup_checks = row.get("duplicate_checks") or []
    primary_dup = int(dup_checks[0].get("duplicate_extra_rows") or 0) if dup_checks else 0
    if primary_dup > 0:
        notes.append(f"primary natural-key duplicate extra rows detected: {primary_dup}")
    if row.get("older_row_ratio") is not None and float(row["older_row_ratio"]) >= 0.90:
        if "latest" in table or "current" in table or "generated_outputs" in db:
            notes.append("mostly older snapshots; retention policy review")
    if table.endswith("_latest") and (row.get("primary_distinct_count") or 0) > 1:
        notes.append("latest table has multiple dates")
    if "features_daily" in table or "signals_weekly" in table or "regime_daily" in table:
        notes.append("I-series base panel; likely duplicated across experiment DB variants")
    if "summary" in table and (row.get("row_count") or 0) <= 20:
        notes.append("small summary table; keep with experiment metadata if DB is retained")
    if not row.get("date_stats"):
        notes.append("no date column detected; retention must be based on parent artifact/experiment")
    return notes


def _target_paths(include_all_i_series: bool = True) -> list[Path]:
    paths = [
        DB_DIR / "generated_outputs.db",
        DB_DIR / "model_research.db",
    ]
    if include_all_i_series:
        paths.extend(sorted(DB_DIR.glob("i_series_research_*.db")))
    return [path for path in paths if path.exists()]


def _generated_outputs_retention(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with _connect(path) as con:
            max_asof = con.execute("SELECT MAX(asof_date) FROM generated_artifact_files").fetchone()[0]
            rows = con.execute(
                """
                SELECT
                    CASE WHEN asof_date = ? THEN 'latest' ELSE 'old' END AS bucket,
                    COUNT(*) AS files,
                    SUM(file_size) AS file_size,
                    SUM(row_count) AS declared_row_count
                FROM generated_artifact_files
                GROUP BY bucket
                """,
                (max_asof,),
            ).fetchall()
            files_by_bucket = {str(row["bucket"]): dict(row) for row in rows}
            linked_rows = con.execute(
                """
                SELECT
                    CASE WHEN f.asof_date = ? THEN 'latest' ELSE 'old' END AS bucket,
                    COUNT(*) AS artifact_rows
                FROM generated_artifact_rows r
                JOIN generated_artifact_files f USING (artifact_id)
                GROUP BY bucket
                """,
                (max_asof,),
            ).fetchall()
            return {
                "max_asof": max_asof,
                "files_by_bucket": files_by_bucket,
                "artifact_rows_by_bucket": {str(row["bucket"]): dict(row) for row in linked_rows},
            }
    except sqlite3.DatabaseError as exc:
        return {"error": str(exc)}


def build_audit(max_dup_rows: int = 1_500_000) -> dict[str, Any]:
    paths = _target_paths()
    db_rows: list[dict[str, Any]] = []
    table_rows: list[dict[str, Any]] = []
    signature_map: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for path in paths:
        with _connect(path) as con:
            page_count = int(con.execute("PRAGMA page_count").fetchone()[0])
            freelist_count = int(con.execute("PRAGMA freelist_count").fetchone()[0])
            page_size = int(con.execute("PRAGMA page_size").fetchone()[0])
            sizes = _dbstat_sizes(con)
            tables = _tables(con)
            db_rows.append(
                {
                    "db": path.name,
                    "relative_path": _rel(path),
                    "size_mb": _mb(path.stat().st_size),
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                    "table_count": len(tables),
                    "page_count": page_count,
                    "freelist_count": freelist_count,
                    "free_mb": _mb(freelist_count * page_size),
                    "free_ratio": round(freelist_count / page_count, 6) if page_count else None,
                }
            )
            for table in tables:
                table_audit = _table_audit(path, table, con, sizes.get(table), max_dup_rows)
                table_audit["retention_notes"] = _retention_notes(table_audit)
                table_rows.append(table_audit)
                signature = json.dumps(
                    {
                        "table": table,
                        "columns": table_audit["columns"],
                        "row_count": table_audit["row_count"],
                        "primary_min": table_audit["primary_min"],
                        "primary_max": table_audit["primary_max"],
                        "sample_fingerprint": table_audit["sample_fingerprint"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                signature_map[hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]].append(
                    {
                        "db": path.name,
                        "table": table,
                        "row_count": table_audit["row_count"],
                        "table_mb": table_audit["table_mb"],
                    }
                )

    duplicate_signatures = {
        key: vals
        for key, vals in sorted(signature_map.items())
        if len(vals) >= 2
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "scope": [
            "data/db/generated_outputs.db",
            "data/db/model_research.db",
            "data/db/i_series_research_*.db",
        ],
        "max_duplicate_check_rows": max_dup_rows,
        "db_count": len(db_rows),
        "table_count": len(table_rows),
        "dbs": sorted(db_rows, key=lambda row: float(row["size_mb"] or 0), reverse=True),
        "tables": sorted(table_rows, key=lambda row: float(row["table_mb"] or 0), reverse=True),
        "duplicate_table_signature_count": len(duplicate_signatures),
        "duplicate_table_signatures": duplicate_signatures,
        "generated_outputs_retention": _generated_outputs_retention(DB_DIR / "generated_outputs.db"),
    }


def _dup_extra(row: dict[str, Any]) -> int:
    checks = row.get("duplicate_checks") or []
    if not checks:
        return 0
    return int(checks[0].get("duplicate_extra_rows") or 0)


def _md_table(rows: list[dict[str, Any]], headers: list[str], limit: int | None = None) -> list[str]:
    use = rows[:limit] if limit else rows
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in use:
        vals: list[str] = []
        for header in headers:
            val = row.get(header, "")
            if isinstance(val, float):
                val = f"{val:.2f}"
            vals.append(str(val).replace("\n", " ")[:160])
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def write_reports(audit: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"quant_db_table_retention_audit_{stamp}.json"
    md_path = out_dir / f"QUANT_DB_TABLE_RETENTION_AUDIT_{stamp}.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    tables = audit["tables"]
    dup_rows = [row for row in tables if _dup_extra(row) > 0]
    retention_rows = [row for row in tables if row.get("retention_notes")]
    i_base_rows = [
        row
        for row in tables
        if row["table"] in {"i_stock_v01_features_daily", "i_stock_v01_signals_weekly", "i_stock_v01_regime_daily"}
    ]
    large_rows = [row for row in tables if (row.get("table_mb") or 0) >= 50 or (row.get("row_count") or 0) >= 100_000]

    dup_sig_items = sorted(
        audit["duplicate_table_signatures"].items(),
        key=lambda kv: (len(kv[1]), sum(float(v.get("table_mb") or 0) for v in kv[1])),
        reverse=True,
    )

    lines = [
        "# Quant DB Table-Level Duplicate/Retention Audit",
        "",
        f"- generated_at: {audit['generated_at']}",
        f"- db_count: {audit['db_count']}",
        f"- table_count: {audit['table_count']}",
        f"- duplicate_table_signature_count: {audit['duplicate_table_signature_count']}",
        f"- max_duplicate_check_rows: {audit['max_duplicate_check_rows']:,}",
        "",
        "## Scope",
        "",
        "- `generated_outputs.db`",
        "- `model_research.db`",
        "- `i_series_research_*.db`",
        "",
        "## DB Summary",
        "",
        *_md_table(
            audit["dbs"],
            ["relative_path", "size_mb", "table_count", "free_mb", "free_ratio", "modified_at"],
        ),
        "",
        "## generated_outputs.db Retention Detail",
        "",
        "```json",
        json.dumps(audit.get("generated_outputs_retention"), ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## Large Tables",
        "",
        *_md_table(
            [
                {
                    "db": row["db"],
                    "table": row["table"],
                    "table_mb": row.get("table_mb"),
                    "row_count": row.get("row_count"),
                    "date_range": f"{row.get('primary_min')} ~ {row.get('primary_max')}",
                    "date_count": row.get("primary_distinct_count"),
                    "notes": "; ".join(row.get("retention_notes") or []),
                }
                for row in large_rows
            ],
            ["db", "table", "table_mb", "row_count", "date_range", "date_count", "notes"],
            limit=80,
        ),
        "",
        "## Natural-Key Duplicate Signals",
        "",
        *_md_table(
            [
                {
                    "db": row["db"],
                    "table": row["table"],
                    "row_count": row.get("row_count"),
                    "dup_extra_rows": _dup_extra(row),
                    "checks": json.dumps(row.get("duplicate_checks")[:2], ensure_ascii=False),
                }
                for row in sorted(dup_rows, key=_dup_extra, reverse=True)
            ],
            ["db", "table", "row_count", "dup_extra_rows", "checks"],
            limit=80,
        ),
        "",
        "## I-Series Repeated Base Panels",
        "",
        *_md_table(
            [
                {
                    "db": row["db"],
                    "table": row["table"],
                    "table_mb": row.get("table_mb"),
                    "row_count": row.get("row_count"),
                    "date_range": f"{row.get('primary_min')} ~ {row.get('primary_max')}",
                    "fingerprint": row.get("sample_fingerprint"),
                }
                for row in i_base_rows
            ],
            ["db", "table", "table_mb", "row_count", "date_range", "fingerprint"],
            limit=140,
        ),
        "",
        "## Duplicate Table Signatures",
        "",
        "- Same signature means same table name, same columns, same row count/date range, and same ordered sample fingerprint.",
        "- This is strong evidence of duplicated table payload, but still not a deletion instruction.",
        "",
    ]
    for key, vals in dup_sig_items[:30]:
        total_mb = sum(float(v.get("table_mb") or 0) for v in vals)
        lines.append(f"### signature `{key}` ({len(vals)} tables, {total_mb:.2f} MB)")
        for item in vals[:60]:
            lines.append(f"- `{item['db']}` / `{item['table']}`: {item.get('row_count')} rows, {item.get('table_mb')} MB")
        lines.append("")

    lines.extend(
        [
            "## Retention Interpretation",
            "",
            "1. `generated_outputs.db` is an artifact snapshot store. If web/admin only needs current outputs, keep the latest `asof_date` online and archive older artifact payloads by explicit approval.",
            "2. `model_research.db` contains active research panels and summaries. Large candidate/panel tables should be kept until each research script has a reproducible rebuild path.",
            "3. I-series variant DBs repeatedly store identical or near-identical base feature/signal/regime panels. The safer optimization is to keep one canonical base panel DB and archive variant DBs after preserving summary/nav/holdings outputs.",
            "4. No delete, move, or VACUUM was performed by this audit.",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only table-level duplicate/retention audit for selected Quant DBs.")
    parser.add_argument("--max-duplicate-check-rows", type=int, default=1_500_000)
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    audit = build_audit(max_dup_rows=args.max_duplicate_check_rows)
    md_path, json_path = write_reports(audit, Path(args.out_dir))
    print(json.dumps({"status": "ok", "markdown": str(md_path), "json": str(json_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
