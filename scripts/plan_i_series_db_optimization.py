from __future__ import annotations

import argparse
import csv
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

HOT_KEEP_DBS = {
    "i_series_operational.db": "operational admin/web payload source",
    "i_series_research.db": "overlay/review research output DB",
    "i_series_research_strong_rsi_raw_top30_s65.db": "current I-STOCK-STRONG-RSI-V01 research source used by pipeline",
}

BASE_PANEL_TABLES = {
    "i_stock_v01_features_daily",
    "i_stock_v01_signals_weekly",
    "i_stock_v01_regime_daily",
}

RESULT_TABLES = {
    "i_stock_v01_backtest_holdings",
    "i_stock_v01_backtest_nav",
    "i_stock_v01_backtest_summary",
    "i_stock_v01_forward_return_summary",
    "i_stock_v01_run_meta",
}


def _mb(size: int | float) -> float:
    return round(float(size) / 1024 / 1024, 2)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _connect_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=20)
    con.row_factory = sqlite3.Row
    return con


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


def _minmax_date(con: sqlite3.Connection, table: str) -> dict[str, Any] | None:
    cols = _columns(con, table)
    date_col = "date" if "date" in cols else ("asof_date" if "asof_date" in cols else None)
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


def _table_sample_fingerprint(con: sqlite3.Connection, table: str) -> str | None:
    cols = _columns(con, table)
    if not cols:
        return None
    order_cols = [col for col in ("date", "ticker") if col in cols] or cols[:2]
    select_cols = cols[:16]
    sql = (
        f"SELECT {', '.join(_quote(col) for col in select_cols)} "
        f"FROM {_quote(table)} "
        f"ORDER BY {', '.join(_quote(col) for col in order_cols)} "
        "LIMIT 300"
    )
    try:
        digest = hashlib.sha256()
        for row in con.execute(sql):
            digest.update(json.dumps(list(row), ensure_ascii=False, default=str).encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()[:16]
    except sqlite3.DatabaseError:
        return None


def _run_meta(con: sqlite3.Connection) -> dict[str, Any]:
    if "i_stock_v01_run_meta" not in set(_tables(con)):
        return {}
    try:
        row = con.execute("SELECT * FROM i_stock_v01_run_meta LIMIT 1").fetchone()
        return dict(row) if row else {}
    except sqlite3.DatabaseError:
        return {}


def _summary(con: sqlite3.Connection) -> dict[str, Any]:
    if "i_stock_v01_backtest_summary" not in set(_tables(con)):
        return {}
    try:
        row = con.execute("SELECT * FROM i_stock_v01_backtest_summary LIMIT 1").fetchone()
        return dict(row) if row else {}
    except sqlite3.DatabaseError:
        return {}


def _db_info(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "db": path.name,
        "relative_path": _rel(path),
        "size_bytes": path.stat().st_size,
        "size_mb": _mb(path.stat().st_size),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "tables": [],
        "table_count": 0,
        "table_rows": {},
        "date_ranges": {},
        "fingerprints": {},
        "run_meta": {},
        "summary": {},
        "error": None,
    }
    try:
        with _connect_ro(path) as con:
            tables = _tables(con)
            info["tables"] = tables
            info["table_count"] = len(tables)
            for table in tables:
                info["table_rows"][table] = _row_count(con, table)
                info["date_ranges"][table] = _minmax_date(con, table)
                if table in BASE_PANEL_TABLES:
                    info["fingerprints"][table] = _table_sample_fingerprint(con, table)
            info["run_meta"] = _run_meta(con)
            info["summary"] = _summary(con)
    except Exception as exc:  # noqa: BLE001 - planning script should keep going.
        info["error"] = str(exc)
    return info


def _classify(info: dict[str, Any]) -> tuple[str, str]:
    db = str(info["db"])
    if db in HOT_KEEP_DBS:
        return "hot_keep", HOT_KEEP_DBS[db]
    if db.startswith("i_series_research_"):
        return "archive_candidate", "research variant DB; keep report/manifest and move out of hot DB folder after approval"
    return "review", "manual review"


def build_plan() -> dict[str, Any]:
    paths = sorted(DB_DIR.glob("i_series_research*.db")) + sorted(DB_DIR.glob("i_series_operational.db"))
    seen: set[Path] = set()
    paths = [p for p in paths if not (p in seen or seen.add(p))]

    rows: list[dict[str, Any]] = []
    base_signature_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        info = _db_info(path)
        action, reason = _classify(info)
        table_set = set(info.get("tables") or [])
        base_rows = sum(int(info["table_rows"].get(table, 0) or 0) for table in BASE_PANEL_TABLES)
        result_rows = sum(int(info["table_rows"].get(table, 0) or 0) for table in RESULT_TABLES)
        row = {
            **info,
            "action": action,
            "action_reason": reason,
            "has_base_panels": bool(BASE_PANEL_TABLES & table_set),
            "has_result_tables": bool(RESULT_TABLES & table_set),
            "base_panel_rows": base_rows,
            "result_rows": result_rows,
            "model_code": (info.get("run_meta") or {}).get("model_code") or (info.get("summary") or {}).get("model_code"),
            "asof_date": (info.get("run_meta") or {}).get("asof_date"),
            "cagr": (info.get("summary") or {}).get("cagr"),
            "mdd": (info.get("summary") or {}).get("mdd"),
            "sharpe": (info.get("summary") or {}).get("sharpe"),
        }
        rows.append(row)
        for table, fp in (info.get("fingerprints") or {}).items():
            signature = json.dumps(
                {
                    "table": table,
                    "rows": info["table_rows"].get(table),
                    "date_range": info["date_ranges"].get(table),
                    "fingerprint": fp,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            base_signature_map[hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]].append(
                {
                    "db": info["db"],
                    "table": table,
                    "rows": info["table_rows"].get(table),
                    "fingerprint": fp,
                }
            )

    archive_rows = [row for row in rows if row["action"] == "archive_candidate"]
    hot_rows = [row for row in rows if row["action"] == "hot_keep"]
    duplicate_base_groups = {
        key: vals
        for key, vals in sorted(base_signature_map.items())
        if len(vals) >= 2
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "I-series DB optimization planning only; no file move/delete/VACUUM",
        "db_count": len(rows),
        "total_size_mb": _mb(sum(int(row["size_bytes"]) for row in rows)),
        "hot_keep_count": len(hot_rows),
        "hot_keep_size_mb": _mb(sum(int(row["size_bytes"]) for row in hot_rows)),
        "archive_candidate_count": len(archive_rows),
        "archive_candidate_size_mb": _mb(sum(int(row["size_bytes"]) for row in archive_rows)),
        "duplicate_base_panel_signature_count": len(duplicate_base_groups),
        "duplicate_base_panel_signatures": duplicate_base_groups,
        "rows": sorted(rows, key=lambda row: int(row["size_bytes"]), reverse=True),
    }


def _fmt_pct(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return str(value)


def write_outputs(plan: dict[str, Any], out_dir: Path) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"i_series_db_optimization_plan_{stamp}.json"
    csv_path = out_dir / f"i_series_db_optimization_manifest_{stamp}.csv"
    md_path = out_dir / f"I_SERIES_DB_OPTIMIZATION_PLAN_{stamp}.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    fieldnames = [
        "action",
        "db",
        "relative_path",
        "size_mb",
        "model_code",
        "asof_date",
        "cagr",
        "mdd",
        "sharpe",
        "base_panel_rows",
        "result_rows",
        "action_reason",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in plan["rows"]:
            writer.writerow({key: row.get(key) for key in fieldnames})

    hot = [row for row in plan["rows"] if row["action"] == "hot_keep"]
    archive = [row for row in plan["rows"] if row["action"] == "archive_candidate"]
    lines = [
        "# I-Series DB Optimization Plan",
        "",
        f"- generated_at: {plan['generated_at']}",
        f"- scope: {plan['scope']}",
        f"- db_count: {plan['db_count']}",
        f"- total_size: {plan['total_size_mb']:.2f} MB",
        f"- hot_keep: {plan['hot_keep_count']} DBs / {plan['hot_keep_size_mb']:.2f} MB",
        f"- archive_candidate: {plan['archive_candidate_count']} DBs / {plan['archive_candidate_size_mb']:.2f} MB",
        f"- duplicate_base_panel_signature_count: {plan['duplicate_base_panel_signature_count']}",
        "",
        "## Decision",
        "",
        "- 현재 운영/웹/파이프라인에 직접 필요한 DB는 hot keep으로 유지한다.",
        "- 실험 variant DB는 삭제하지 않고 archive 후보로 분리한다.",
        "- archive 전에는 manifest와 주요 summary/nav/holdings report를 보존한다.",
        "- 이 문서는 실행 계획이며 실제 이동/삭제/VACUUM은 수행하지 않았다.",
        "",
        "## Hot Keep DBs",
        "",
        "| DB | size | reason | asof | CAGR | MDD | Sharpe |",
        "| --- | ---: | --- | --- | ---: | ---: | ---: |",
    ]
    for row in hot:
        lines.append(
            f"| `{row['relative_path']}` | {row['size_mb']:.2f} MB | {row['action_reason']} | "
            f"{row.get('asof_date') or ''} | {_fmt_pct(row.get('cagr'))} | {_fmt_pct(row.get('mdd'))} | {row.get('sharpe') or ''} |"
        )

    lines.extend(
        [
            "",
            "## Archive Candidates",
            "",
            "| DB | size | asof | CAGR | MDD | Sharpe | base rows | result rows |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in archive:
        lines.append(
            f"| `{row['relative_path']}` | {row['size_mb']:.2f} MB | {row.get('asof_date') or ''} | "
            f"{_fmt_pct(row.get('cagr'))} | {_fmt_pct(row.get('mdd'))} | {row.get('sharpe') or ''} | "
            f"{row['base_panel_rows']} | {row['result_rows']} |"
        )

    lines.extend(
        [
            "",
            "## Repeated Base Panel Groups",
            "",
            "- 같은 signature는 table name, row count, date range, sample fingerprint가 같은 base panel이다.",
            "- 가장 큰 반복 저장 대상은 `i_stock_v01_features_daily`, `i_stock_v01_signals_weekly`, `i_stock_v01_regime_daily`다.",
            "",
        ]
    )
    sig_items = sorted(
        plan["duplicate_base_panel_signatures"].items(),
        key=lambda kv: (len(kv[1]), sum(int(v.get("rows") or 0) for v in kv[1])),
        reverse=True,
    )
    for key, vals in sig_items[:20]:
        lines.append(f"### `{key}` ({len(vals)} tables)")
        for item in vals[:60]:
            lines.append(f"- `{item['db']}` / `{item['table']}`: {item['rows']} rows")
        lines.append("")

    lines.extend(
        [
            "## Proposed Execution After Approval",
            "",
            "1. Create `data/db/archive/i_series_variants_YYYYMMDD/`.",
            "2. Move archive candidate DBs to that folder, preserving original filenames.",
            "3. Keep `i_series_research_strong_rsi_raw_top30_s65.db`, `i_series_research.db`, and `i_series_operational.db` in `data/db`.",
            "4. Keep generated reports under `reports/i_series_stock_v01` as experiment record.",
            "5. Do not VACUUM hot DBs unless freelist ratio becomes meaningful; current I-series freelist saving is small.",
            "",
            "## Later Structural Refactor",
            "",
            "- Refactor I-series research scripts so shared base panels are stored once in a canonical DB.",
            "- Variant runs should store only `run_meta`, `backtest_summary`, `backtest_nav`, `backtest_holdings`, and comparison outputs.",
            "- This is a code/data model change and should be done after archive cleanup.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a non-destructive I-series DB optimization plan.")
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    plan = build_plan()
    md_path, json_path, csv_path = write_outputs(plan, Path(args.out_dir))
    print(
        json.dumps(
            {"status": "ok", "markdown": str(md_path), "json": str(json_path), "manifest_csv": str(csv_path)},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
