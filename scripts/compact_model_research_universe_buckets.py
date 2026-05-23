from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "db" / "model_research.db"
BACKUP_DIR = ROOT / "data" / "db" / "backups"
REPORT_DIR = ROOT / "reports" / "db_audit"

KEY_COLS = [
    "model_code",
    "horizon",
    "signal_date",
    "end_date",
    "ticker",
]

COMMON_VALUE_COLS = [
    "selected",
    "score",
    "fwd_ret",
    "path_mdd",
    "name",
    "market",
    "return_pct_rank",
    "mdd_pct_rank",
    "composite_score",
]

BUCKET_SPECS = [
    {
        "table": "universe_top_3pct_candidates",
        "bucket": "top_3pct",
        "threshold": "top_3pct_threshold",
        "flag": "top_3pct_flag",
        "rank": "top_3pct_rank",
        "top_bucket_label": True,
    },
    {
        "table": "universe_top_10pct_candidates",
        "bucket": "top_10pct",
        "threshold": "top_10pct_threshold",
        "flag": "top_10pct_flag",
        "rank": "top_10pct_rank",
        "top_bucket_label": True,
    },
    {
        "table": "universe_top_30pct_candidates",
        "bucket": "top_30pct",
        "threshold": "top_30pct_threshold",
        "flag": "top_30pct_flag",
        "rank": "top_30pct_rank",
        "top_bucket_label": True,
    },
    {
        "table": "universe_top_50pct_candidates",
        "bucket": "top_50pct",
        "threshold": "top_50pct_threshold",
        "flag": "top_50pct_flag",
        "rank": "top_50pct_rank",
        "top_bucket_label": True,
    },
    {
        "table": "universe_top_0_10pct_candidates",
        "bucket": "top_0_10pct",
        "lower_threshold": "top_0_10pct_lower_threshold",
        "flag": "top_0_10pct_flag",
        "rank": "top_0_10pct_rank",
        "top_bucket_label": True,
    },
    {
        "table": "universe_top_10_30pct_candidates",
        "bucket": "top_10_30pct",
        "upper_threshold": "top_10_30pct_upper_threshold",
        "lower_threshold": "top_10_30pct_lower_threshold",
        "flag": "top_10_30pct_flag",
        "rank": "top_10_30pct_rank",
        "top_bucket_label": True,
    },
    {
        "table": "universe_top_30_50pct_candidates",
        "bucket": "top_30_50pct",
        "upper_threshold": "top_30_50pct_upper_threshold",
        "lower_threshold": "top_30_50pct_lower_threshold",
        "flag": "top_30_50pct_flag",
        "rank": "top_30_50pct_rank",
        "top_bucket_label": True,
    },
    {
        "table": "universe_top_50_100pct_candidates",
        "bucket": "top_50_100pct",
        "upper_threshold": "top_50_100pct_upper_threshold",
        "flag": "top_50_100pct_flag",
        "rank": "top_50_100pct_rank",
        "top_bucket_label": True,
    },
    {
        "table": "universe_top_decile_candidates",
        "bucket": "top_decile",
        "threshold": "top_decile_threshold",
        "flag": "top_decile_flag",
        "rank": "top_decile_rank",
        "top_bucket_label": False,
    },
]


def _mb(value: int | float | None) -> float:
    return round(float(value or 0) / 1024 / 1024, 2)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=120)
    con.row_factory = sqlite3.Row
    return con


def _table_names(con: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            """
        )
    }


def _row_count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0])


def _flag_sum(con: sqlite3.Connection, table: str, flag_col: str) -> int:
    return int(con.execute(f"SELECT COALESCE(SUM({_quote(flag_col)}), 0) FROM {_quote(table)}").fetchone()[0] or 0)


def _base_join_clause(alias: str = "b", other: str = "m") -> str:
    return " AND ".join(f"{alias}.{_quote(col)} = {other}.{_quote(col)}" for col in KEY_COLS)


def _backup_db(stamp: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"model_research_before_universe_bucket_compact_{stamp}.db"
    if backup.exists():
        raise SystemExit(f"Backup already exists: {backup}")
    shutil.copy2(DB_PATH, backup)
    return backup


def _preflight(con: sqlite3.Connection) -> dict[str, Any]:
    names = _table_names(con)
    missing = [spec["table"] for spec in BUCKET_SPECS if spec["table"] not in names]
    if missing:
        raise SystemExit(f"Missing source tables: {missing}")
    existing_new = [name for name in ["universe_bucket_candidate_base", "universe_bucket_membership"] if name in names]
    if existing_new:
        raise SystemExit(f"Compacted tables already exist: {existing_new}")
    metrics = {}
    for spec in BUCKET_SPECS:
        table = spec["table"]
        flag_col = str(spec["flag"])
        metrics[table] = {
            "rows": _row_count(con, table),
            "flag_sum": _flag_sum(con, table, flag_col),
        }
    return metrics


def _create_compact_tables(con: sqlite3.Connection) -> None:
    key_cols_sql = ", ".join(_quote(col) for col in KEY_COLS)
    union_sql = "\nUNION\n".join(f"SELECT {key_cols_sql} FROM {_quote(spec['table'])}" for spec in BUCKET_SPECS)
    con.execute(
        f"""
        CREATE TABLE universe_bucket_candidate_base AS
        SELECT ROW_NUMBER() OVER (
            ORDER BY model_code, horizon, signal_date, end_date, ticker
        ) AS base_id,
               {key_cols_sql}
        FROM ({union_sql})
        """
    )
    con.execute(
        """
        CREATE UNIQUE INDEX idx_universe_bucket_candidate_base_key
            ON universe_bucket_candidate_base(model_code, horizon, signal_date, end_date, ticker)
        """
    )
    con.execute(
        """
        CREATE TABLE universe_bucket_membership (
            base_id INTEGER NOT NULL,
            bucket_name TEXT NOT NULL,
            selected INTEGER,
            score REAL,
            fwd_ret REAL,
            path_mdd REAL,
            name TEXT,
            market TEXT,
            return_pct_rank REAL,
            mdd_pct_rank REAL,
            composite_score REAL,
            threshold REAL,
            lower_threshold REAL,
            upper_threshold REAL,
            bucket_flag INTEGER,
            bucket_rank REAL,
            top_bucket_label TEXT,
            PRIMARY KEY (bucket_name, base_id)
        )
        """
    )
    con.execute("CREATE INDEX idx_universe_bucket_membership_base ON universe_bucket_membership(base_id)")


def _insert_bucket_memberships(con: sqlite3.Connection) -> None:
    join_clause = _base_join_clause("b", "src")
    common_value_select = ",\n                   ".join(f"src.{_quote(col)} AS {_quote(col)}" for col in COMMON_VALUE_COLS)
    for spec in BUCKET_SPECS:
        threshold_expr = f"src.{_quote(str(spec['threshold']))}" if "threshold" in spec else "NULL"
        lower_expr = f"src.{_quote(str(spec['lower_threshold']))}" if "lower_threshold" in spec else "NULL"
        upper_expr = f"src.{_quote(str(spec['upper_threshold']))}" if "upper_threshold" in spec else "NULL"
        label_expr = "src.top_bucket_label" if spec.get("top_bucket_label") else "NULL"
        sql = f"""
            INSERT INTO universe_bucket_membership
            (base_id, bucket_name, {', '.join(_quote(col) for col in COMMON_VALUE_COLS)}, threshold, lower_threshold, upper_threshold, bucket_flag, bucket_rank, top_bucket_label)
            SELECT b.base_id,
                   ? AS bucket_name,
                   {common_value_select},
                   {threshold_expr} AS threshold,
                   {lower_expr} AS lower_threshold,
                   {upper_expr} AS upper_threshold,
                   src.{_quote(str(spec['flag']))} AS bucket_flag,
                   src.{_quote(str(spec['rank']))} AS bucket_rank,
                   {label_expr} AS top_bucket_label
            FROM {_quote(str(spec['table']))} src
            JOIN universe_bucket_candidate_base b
              ON {join_clause}
        """
        con.execute(sql, (spec["bucket"],))


def _drop_source_tables(con: sqlite3.Connection) -> None:
    for spec in BUCKET_SPECS:
        con.execute(f"DROP TABLE {_quote(str(spec['table']))}")


def _create_compat_views(con: sqlite3.Connection) -> None:
    base_cols_select = ", ".join(f"b.{_quote(col)} AS {_quote(col)}" for col in KEY_COLS)
    common_cols_select = ", ".join(f"m.{_quote(col)} AS {_quote(col)}" for col in COMMON_VALUE_COLS)
    for spec in BUCKET_SPECS:
        table = str(spec["table"])
        bucket = str(spec["bucket"])
        cols = [base_cols_select, common_cols_select]
        if "threshold" in spec:
            cols.append(f"m.threshold AS {_quote(str(spec['threshold']))}")
        if "upper_threshold" in spec:
            cols.append(f"m.upper_threshold AS {_quote(str(spec['upper_threshold']))}")
        if "lower_threshold" in spec:
            cols.append(f"m.lower_threshold AS {_quote(str(spec['lower_threshold']))}")
        cols.append(f"m.bucket_flag AS {_quote(str(spec['flag']))}")
        cols.append(f"m.bucket_rank AS {_quote(str(spec['rank']))}")
        if spec.get("top_bucket_label"):
            cols.append("m.top_bucket_label AS top_bucket_label")
        con.execute(
            f"""
            CREATE VIEW {_quote(table)} AS
            SELECT {', '.join(cols)}
            FROM universe_bucket_candidate_base b
            JOIN universe_bucket_membership m
              ON b.base_id = m.base_id
            WHERE m.bucket_name = {json.dumps(bucket)}
            """
        )


def _validate(con: sqlite3.Connection, before: dict[str, Any]) -> dict[str, Any]:
    after = {}
    for spec in BUCKET_SPECS:
        table = str(spec["table"])
        flag_col = str(spec["flag"])
        after[table] = {
            "rows": _row_count(con, table),
            "flag_sum": _flag_sum(con, table, flag_col),
        }
        if after[table] != before[table]:
            raise SystemExit(f"Validation failed for {table}: before={before[table]} after={after[table]}")
    base_count = _row_count(con, "universe_bucket_candidate_base")
    membership_count = _row_count(con, "universe_bucket_membership")
    return {"views": after, "base_rows": base_count, "membership_rows": membership_count}


def compact(*, dry_run: bool = False) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    size_before = DB_PATH.stat().st_size
    with _connect(DB_PATH) as con:
        before = _preflight(con)
    if dry_run:
        return {
            "status": "dry_run",
            "db": str(DB_PATH),
            "size_before_mb": _mb(size_before),
            "source_metrics": before,
            "source_total_rows": sum(int(v["rows"]) for v in before.values()),
        }

    backup = _backup_db(stamp)
    with _connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        before = _preflight(con)
        _create_compact_tables(con)
        _insert_bucket_memberships(con)
        compact_counts = {
            "base_rows": _row_count(con, "universe_bucket_candidate_base"),
            "membership_rows": _row_count(con, "universe_bucket_membership"),
        }
        _drop_source_tables(con)
        _create_compat_views(con)
        after = _validate(con, before)
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    size_after_rewrite = DB_PATH.stat().st_size
    with _connect(DB_PATH) as con:
        con.execute("VACUUM")
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        final = _validate(con, before)
    size_after_vacuum = DB_PATH.stat().st_size
    return {
        "status": "ok",
        "db": str(DB_PATH),
        "backup": str(backup),
        "source_metrics": before,
        "compact_counts": compact_counts,
        "after_validation": after,
        "final_validation": final,
        "size_before_mb": _mb(size_before),
        "size_after_rewrite_mb": _mb(size_after_rewrite),
        "size_after_vacuum_mb": _mb(size_after_vacuum),
        "reclaimed_mb": _mb(size_before - size_after_vacuum),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def write_report(result: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"model_research_universe_bucket_compact_result_{stamp}.json"
    md_path = out_dir / f"MODEL_RESEARCH_UNIVERSE_BUCKET_COMPACT_RESULT_{stamp}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = [
        "# model_research.db Universe Bucket Compact Result",
        "",
        f"- generated_at: {result['generated_at']}",
        f"- status: {result['status']}",
        f"- backup: `{result['backup']}`",
        f"- source_total_rows: {sum(int(v['rows']) for v in result['source_metrics'].values()):,}",
        f"- base_rows: {result['compact_counts']['base_rows']:,}",
        f"- membership_rows: {result['compact_counts']['membership_rows']:,}",
        f"- size_before: {result['size_before_mb']:.2f} MB",
        f"- size_after_rewrite: {result['size_after_rewrite_mb']:.2f} MB",
        f"- size_after_vacuum: {result['size_after_vacuum_mb']:.2f} MB",
        f"- reclaimed: {result['reclaimed_mb']:.2f} MB",
        "",
        "## Compatibility Views",
        "",
        "| view | rows | flag sum |",
        "| --- | ---: | ---: |",
    ]
    for table, metrics in result["final_validation"]["views"].items():
        lines.append(f"| `{table}` | {int(metrics['rows']):,} | {int(metrics['flag_sum']):,} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact repeated universe_top_* candidate tables in model_research.db.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    result = compact(dry_run=bool(args.dry_run))
    report = None if args.dry_run else write_report(result, Path(args.out_dir))
    print(json.dumps({"result": result, "report": str(report) if report else None}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
