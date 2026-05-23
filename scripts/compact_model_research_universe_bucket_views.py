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

BASE_SOURCE_TABLE = "universe_top_50pct_candidates"
BASE_TABLE = "universe_top_base_candidates"
THRESHOLD_TABLE = "universe_bucket_thresholds"

BASE_COLS = [
    "model_code",
    "horizon",
    "signal_date",
    "end_date",
    "ticker",
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
    {"table": "universe_top_3pct_candidates", "bucket": "top_3pct", "threshold": "top_3pct_threshold", "flag": "top_3pct_flag", "rank": "top_3pct_rank", "label": True},
    {"table": "universe_top_10pct_candidates", "bucket": "top_10pct", "threshold": "top_10pct_threshold", "flag": "top_10pct_flag", "rank": "top_10pct_rank", "label": True},
    {"table": "universe_top_30pct_candidates", "bucket": "top_30pct", "threshold": "top_30pct_threshold", "flag": "top_30pct_flag", "rank": "top_30pct_rank", "label": True},
    {"table": "universe_top_50pct_candidates", "bucket": "top_50pct", "threshold": "top_50pct_threshold", "flag": "top_50pct_flag", "rank": "top_50pct_rank", "label": True},
    {"table": "universe_top_0_10pct_candidates", "bucket": "top_0_10pct", "lower": "top_0_10pct_lower_threshold", "flag": "top_0_10pct_flag", "rank": "top_0_10pct_rank", "label": True},
    {"table": "universe_top_10_30pct_candidates", "bucket": "top_10_30pct", "upper": "top_10_30pct_upper_threshold", "lower": "top_10_30pct_lower_threshold", "flag": "top_10_30pct_flag", "rank": "top_10_30pct_rank", "label": True},
    {"table": "universe_top_30_50pct_candidates", "bucket": "top_30_50pct", "upper": "top_30_50pct_upper_threshold", "lower": "top_30_50pct_lower_threshold", "flag": "top_30_50pct_flag", "rank": "top_30_50pct_rank", "label": True},
    {"table": "universe_top_50_100pct_candidates", "bucket": "top_50_100pct", "upper": "top_50_100pct_upper_threshold", "flag": "top_50_100pct_flag", "rank": "top_50_100pct_rank", "label": True},
]


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _mb(value: int | float | None) -> float:
    return round(float(value or 0) / 1024 / 1024, 2)


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=120)
    con.row_factory = sqlite3.Row
    return con


def _objects(con: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["name"]): str(row["type"])
        for row in con.execute(
            """
            SELECT name, type
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


def _backup_db(stamp: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"model_research_before_bucket_view_compact_{stamp}.db"
    if backup.exists():
        raise SystemExit(f"Backup already exists: {backup}")
    shutil.copy2(DB_PATH, backup)
    return backup


def _preflight(con: sqlite3.Connection) -> dict[str, Any]:
    objects = _objects(con)
    missing = [spec["table"] for spec in BUCKET_SPECS if spec["table"] not in objects]
    if missing:
        raise SystemExit(f"Missing source tables/views: {missing}")
    blocked = [name for name in [BASE_TABLE, THRESHOLD_TABLE] if name in objects]
    if blocked:
        raise SystemExit(f"Compacted objects already exist: {blocked}")
    metrics = {}
    for spec in BUCKET_SPECS:
        table = str(spec["table"])
        flag = str(spec["flag"])
        metrics[table] = {"rows": _row_count(con, table), "flag_sum": _flag_sum(con, table, flag)}
    return metrics


def _threshold_select(spec: dict[str, Any]) -> str:
    table = str(spec["table"])
    bucket = str(spec["bucket"])
    threshold = f"{_quote(str(spec['threshold']))}" if "threshold" in spec else "NULL"
    lower = f"{_quote(str(spec['lower']))}" if "lower" in spec else "NULL"
    upper = f"{_quote(str(spec['upper']))}" if "upper" in spec else "NULL"
    return f"""
        SELECT
            {json.dumps(bucket)} AS bucket_name,
            model_code,
            horizon,
            date(signal_date) AS signal_date_key,
            date(end_date) AS end_date_key,
            {threshold} AS threshold,
            {lower} AS lower_threshold,
            {upper} AS upper_threshold
        FROM {_quote(table)}
        GROUP BY model_code, horizon, date(signal_date), date(end_date)
    """


def _create_base_and_thresholds(con: sqlite3.Connection) -> None:
    base_cols = ", ".join(_quote(col) for col in BASE_COLS)
    con.execute(
        f"""
        CREATE TABLE {BASE_TABLE} AS
        SELECT date(signal_date) AS signal_date_key,
               date(end_date) AS end_date_key,
               {base_cols}
        FROM {_quote(BASE_SOURCE_TABLE)}
        """
    )
    con.execute(
        f"""
        CREATE INDEX idx_{BASE_TABLE}_key
        ON {BASE_TABLE}(model_code, horizon, signal_date_key, end_date_key, ticker)
        """
    )
    con.execute(
        f"""
        CREATE INDEX idx_{BASE_TABLE}_rank
        ON {BASE_TABLE}(model_code, horizon, signal_date_key, end_date_key, composite_score DESC, ticker)
        """
    )
    threshold_union = "\nUNION ALL\n".join(_threshold_select(spec) for spec in BUCKET_SPECS)
    con.execute(
        f"""
        CREATE TABLE {THRESHOLD_TABLE} AS
        SELECT * FROM ({threshold_union})
        """
    )
    con.execute(
        f"""
        CREATE UNIQUE INDEX idx_{THRESHOLD_TABLE}_key
        ON {THRESHOLD_TABLE}(bucket_name, model_code, horizon, signal_date_key, end_date_key)
        """
    )


def _drop_sources(con: sqlite3.Connection) -> None:
    for spec in BUCKET_SPECS:
        table = str(spec["table"])
        obj_type = _objects(con).get(table)
        if obj_type == "view":
            con.execute(f"DROP VIEW {_quote(table)}")
        elif obj_type == "table":
            con.execute(f"DROP TABLE {_quote(table)}")


def _flag_expr() -> str:
    return """
        CASE
            WHEN d.threshold IS NOT NULL THEN CASE WHEN r.composite_score >= d.threshold THEN 1 ELSE 0 END
            WHEN d.lower_threshold IS NOT NULL AND d.upper_threshold IS NOT NULL THEN CASE WHEN r.composite_score >= d.lower_threshold AND r.composite_score < d.upper_threshold THEN 1 ELSE 0 END
            WHEN d.lower_threshold IS NOT NULL THEN CASE WHEN r.composite_score >= d.lower_threshold THEN 1 ELSE 0 END
            WHEN d.upper_threshold IS NOT NULL THEN CASE WHEN r.composite_score < d.upper_threshold THEN 1 ELSE 0 END
            ELSE 0
        END
    """


def _create_view(con: sqlite3.Connection, spec: dict[str, Any]) -> None:
    table = str(spec["table"])
    bucket = str(spec["bucket"])
    cols = [f"r.{_quote(col)} AS {_quote(col)}" for col in BASE_COLS]
    if "threshold" in spec:
        cols.append(f"d.threshold AS {_quote(str(spec['threshold']))}")
    if "upper" in spec:
        cols.append(f"d.upper_threshold AS {_quote(str(spec['upper']))}")
    if "lower" in spec:
        cols.append(f"d.lower_threshold AS {_quote(str(spec['lower']))}")
    cols.append(f"({_flag_expr()}) AS {_quote(str(spec['flag']))}")
    cols.append(f"r.calc_rank AS {_quote(str(spec['rank']))}")
    if spec.get("label"):
        cols.append(f"{json.dumps(bucket)} AS top_bucket_label")
    con.execute(
        f"""
        CREATE VIEW {_quote(table)} AS
        WITH ranked AS (
            SELECT b.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY b.model_code, b.horizon, b.signal_date_key, b.end_date_key
                       ORDER BY b.composite_score DESC, b.ticker
                   ) AS calc_rank
            FROM {BASE_TABLE} b
        )
        SELECT {', '.join(cols)}
        FROM ranked r
        JOIN {THRESHOLD_TABLE} d
          ON d.bucket_name = {json.dumps(bucket)}
         AND d.model_code = r.model_code
         AND d.horizon = r.horizon
         AND d.signal_date_key = r.signal_date_key
         AND d.end_date_key = r.end_date_key
        """
    )


def _create_views(con: sqlite3.Connection) -> None:
    for spec in BUCKET_SPECS:
        _create_view(con, spec)


def _validate(con: sqlite3.Connection, before: dict[str, Any]) -> dict[str, Any]:
    views = {}
    for spec in BUCKET_SPECS:
        table = str(spec["table"])
        flag = str(spec["flag"])
        views[table] = {"rows": _row_count(con, table), "flag_sum": _flag_sum(con, table, flag)}
        if views[table] != before[table]:
            raise SystemExit(f"Validation failed for {table}: before={before[table]} after={views[table]}")
    return {
        "views": views,
        "base_rows": _row_count(con, BASE_TABLE),
        "threshold_rows": _row_count(con, THRESHOLD_TABLE),
    }


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
        _create_base_and_thresholds(con)
        created = {"base_rows": _row_count(con, BASE_TABLE), "threshold_rows": _row_count(con, THRESHOLD_TABLE)}
        _drop_sources(con)
        _create_views(con)
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
        "created": created,
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
    json_path = out_dir / f"model_research_bucket_view_compact_result_{stamp}.json"
    md_path = out_dir / f"MODEL_RESEARCH_BUCKET_VIEW_COMPACT_RESULT_{stamp}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = [
        "# model_research.db Bucket View Compact Result",
        "",
        f"- generated_at: {result['generated_at']}",
        f"- status: {result['status']}",
        f"- backup: `{result['backup']}`",
        f"- source_total_rows: {sum(int(v['rows']) for v in result['source_metrics'].values()):,}",
        f"- base_rows: {result['created']['base_rows']:,}",
        f"- threshold_rows: {result['created']['threshold_rows']:,}",
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
    parser = argparse.ArgumentParser(description="Compact model_research universe_top_* tables into one base table plus compatibility views.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    result = compact(dry_run=bool(args.dry_run))
    report = None if args.dry_run else write_report(result, Path(args.out_dir))
    print(json.dumps({"result": result, "report": str(report) if report else None}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
