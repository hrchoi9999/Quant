from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "db" / "model_research.db"
REPORT_DIR = ROOT / "reports" / "db_audit"
SCAN_DIRS = [ROOT / "scripts", ROOT / "src", ROOT / "docs"]

UNIVERSE_BUCKET_TABLES = {
    "universe_top_3pct_candidates",
    "universe_top_10pct_candidates",
    "universe_top_30pct_candidates",
    "universe_top_50pct_candidates",
    "universe_top_0_10pct_candidates",
    "universe_top_10_30pct_candidates",
    "universe_top_30_50pct_candidates",
    "universe_top_50_100pct_candidates",
    "universe_top_decile_candidates",
}

KNOWN_PRIMARY_KEYS = {
    "s3_two_stage_validation_selected": ["model_code", "horizon", "signal_date", "ticker"],
    "t3_model_filter_capture_examples": ["model_code", "horizon", "ticker", "filter_label", "target_label"],
}


def _connect_ro() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _mb(value: int | float | None) -> float:
    return round(float(value or 0) / 1024 / 1024, 2)


def _tables(con: sqlite3.Connection) -> list[str]:
    return [
        str(row["name"])
        for row in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    ]


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in con.execute(f"PRAGMA table_info({_quote(table)})")]


def _row_count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0])


def _date_range(con: sqlite3.Connection, table: str, cols: list[str]) -> dict[str, Any] | None:
    date_col = "signal_date" if "signal_date" in cols else ("asof_date" if "asof_date" in cols else ("date" if "date" in cols else None))
    if not date_col:
        return None
    row = con.execute(
        f"""
        SELECT MIN({_quote(date_col)}) AS min_date,
               MAX({_quote(date_col)}) AS max_date,
               COUNT(DISTINCT {_quote(date_col)}) AS date_count
        FROM {_quote(table)}
        """
    ).fetchone()
    return {
        "date_col": date_col,
        "min_date": row["min_date"],
        "max_date": row["max_date"],
        "date_count": int(row["date_count"] or 0),
    }


def _primary_duplicate(con: sqlite3.Connection, table: str, cols: list[str], row_count: int) -> dict[str, Any] | None:
    key = KNOWN_PRIMARY_KEYS.get(table)
    if not key or not all(col in cols for col in key):
        return None
    cols_sql = ", ".join(_quote(col) for col in key)
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
        "key": key,
        "key_count": int(row["key_count"] or 0),
        "duplicate_key_groups": int(row["duplicate_key_groups"] or 0),
        "duplicate_extra_rows": extra,
        "duplicate_extra_ratio": round(extra / row_count, 6) if row_count else 0.0,
        "max_group_size": int(row["max_group_size"] or 0),
    }


def _reference_files(table: str) -> list[str]:
    refs: list[str] = []
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".sql", ".txt"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if table in text:
                try:
                    refs.append(str(path.relative_to(ROOT)))
                except ValueError:
                    refs.append(str(path))
            if len(refs) >= 12:
                return refs
    return refs


def _category(table: str, rows: int, max_date: Any) -> tuple[str, str]:
    if table in UNIVERSE_BUCKET_TABLES:
        return "consolidate_candidate", "same base universe panel repeated across percentile/band tables"
    if table in KNOWN_PRIMARY_KEYS:
        return "dedupe_review", "primary-key duplicate check required before rewrite"
    if table.startswith("etf_tseries_") or table.startswith("etf_"):
        return "legacy_etf_research_review", "legacy ETF T-series research table; compare with new ETF AI track before keeping hot"
    if table.startswith("s3_two_stage_") or table.startswith("s3_bucket_") or table.startswith("s3_lower_") or table.startswith("s3_t10_"):
        return "derived_rebuildable_review", "derived S3 research table; keep until rebuild script path is verified"
    if rows >= 100_000:
        return "large_research_review", "large research panel; check whether it is reproducible from upstream tables"
    if max_date and str(max_date) < "2026-04":
        return "stale_research_review", "older research table; archive after confirming no active dependency"
    return "keep_review", "small/current research output"


def build_plan() -> dict[str, Any]:
    with _connect_ro() as con:
        tables = _tables(con)
        table_rows = []
        for table in tables:
            cols = _columns(con, table)
            rows = _row_count(con, table)
            dates = _date_range(con, table, cols)
            max_date = dates.get("max_date") if dates else None
            category, reason = _category(table, rows, max_date)
            table_rows.append(
                {
                    "table": table,
                    "category": category,
                    "reason": reason,
                    "row_count": rows,
                    "column_count": len(cols),
                    "date_col": dates.get("date_col") if dates else None,
                    "min_date": dates.get("min_date") if dates else None,
                    "max_date": max_date,
                    "date_count": dates.get("date_count") if dates else None,
                    "duplicate_signal": _primary_duplicate(con, table, cols, rows),
                    "reference_files": _reference_files(table),
                }
            )

    by_category: dict[str, dict[str, int]] = {}
    for row in table_rows:
        item = by_category.setdefault(row["category"], {"table_count": 0, "row_count": 0})
        item["table_count"] += 1
        item["row_count"] += int(row["row_count"])

    universe_rows = [row for row in table_rows if row["table"] in UNIVERSE_BUCKET_TABLES]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(DB_PATH),
        "db_size_mb": _mb(DB_PATH.stat().st_size),
        "table_count": len(table_rows),
        "total_rows": sum(int(row["row_count"]) for row in table_rows),
        "by_category": by_category,
        "universe_bucket_table_count": len(universe_rows),
        "universe_bucket_total_rows": sum(int(row["row_count"]) for row in universe_rows),
        "universe_bucket_unique_base_estimate_rows": max((int(row["row_count"]) for row in universe_rows), default=0),
        "tables": sorted(table_rows, key=lambda row: int(row["row_count"]), reverse=True),
        "scope": "model_research.db optimization planning only; no table rewrite/drop/VACUUM performed",
    }


def write_outputs(plan: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"model_research_db_optimization_plan_{stamp}.json"
    md_path = out_dir / f"MODEL_RESEARCH_DB_OPTIMIZATION_PLAN_{stamp}.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    duplicate_rows = [row for row in plan["tables"] if row.get("duplicate_signal") and row["duplicate_signal"].get("duplicate_extra_rows")]
    universe_repetition = plan["universe_bucket_total_rows"] - plan["universe_bucket_unique_base_estimate_rows"]
    lines = [
        "# model_research.db Optimization Plan",
        "",
        f"- generated_at: {plan['generated_at']}",
        f"- scope: {plan['scope']}",
        f"- db_size: {plan['db_size_mb']:.2f} MB",
        f"- table_count: {plan['table_count']}",
        f"- total_rows: {plan['total_rows']:,}",
        f"- universe_bucket_tables: {plan['universe_bucket_table_count']}",
        f"- universe_bucket_total_rows: {plan['universe_bucket_total_rows']:,}",
        f"- universe_bucket_repetition_estimate_rows: {universe_repetition:,}",
        "",
        "## Category Summary",
        "",
        "| category | tables | rows |",
        "| --- | ---: | ---: |",
    ]
    for category, item in sorted(plan["by_category"].items(), key=lambda kv: kv[1]["row_count"], reverse=True):
        lines.append(f"| {category} | {item['table_count']} | {item['row_count']:,} |")

    lines.extend(
        [
            "",
            "## Main Repetition Issue",
            "",
            "- `universe_top_*_candidates` 계열은 같은 universe/date/model/horizon base panel을 percentile/band별 테이블로 반복 저장한다.",
            "- 장기 구조는 하나의 long table에 `bucket_label`, `lower_threshold`, `upper_threshold`, `bucket_flag`, `bucket_rank`를 컬럼으로 두는 방식이 적합하다.",
            "- 기존 분석 스크립트가 이 테이블들을 직접 참조하므로 즉시 drop보다는 compatibility view 또는 migration period가 필요하다.",
            "",
            "## Duplicate Review",
            "",
            "| table | rows | duplicate extra rows | key | interpretation |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in duplicate_rows:
        sig = row["duplicate_signal"]
        interpretation = "true duplicate likely" if row["table"] == "s3_two_stage_validation_selected" else "target_label dimension should be included; current key is not unique by design"
        lines.append(
            f"| `{row['table']}` | {row['row_count']:,} | {int(sig['duplicate_extra_rows']):,} | "
            f"`{', '.join(sig['key'])}` | {interpretation} |"
        )

    lines.extend(
        [
            "",
            "## Large / Consolidation Candidate Tables",
            "",
            "| category | table | rows | date range | refs |",
            "| --- | --- | ---: | --- | ---: |",
        ]
    )
    for row in plan["tables"]:
        if row["category"] in {"consolidate_candidate", "large_research_review", "derived_rebuildable_review", "legacy_etf_research_review"} and row["row_count"] >= 10_000:
            lines.append(
                f"| {row['category']} | `{row['table']}` | {row['row_count']:,} | "
                f"{row.get('min_date') or ''} ~ {row.get('max_date') or ''} | {len(row.get('reference_files') or [])} |"
            )

    lines.extend(
        [
            "",
            "## Proposed Execution After Approval",
            "",
            "1. Do not drop `universe_top_*` tables immediately; scripts still reference them.",
            "2. Add a consolidated long-form builder for universe bucket candidates.",
            "3. Update dependent scripts to read the long table or compatibility views.",
            "4. After dependency migration, archive/drop repeated wide bucket tables and VACUUM.",
            "5. Fix `s3_two_stage_validation_selected` duplicate generation or dedupe on write.",
            "6. Treat legacy ETF T-series tables as archive candidates after ETF AI track owns the new ETF research mart.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a non-destructive model_research.db optimization plan.")
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    plan = build_plan()
    md_path, json_path = write_outputs(plan, Path(args.out_dir))
    print(json.dumps({"status": "ok", "markdown": str(md_path), "json": str(json_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
