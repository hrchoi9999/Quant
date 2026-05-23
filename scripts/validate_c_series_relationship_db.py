from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(r"D:\Quant")
C_DB = ROOT / r"data\db\cseries_relationship.db"
REPORT_DIR = ROOT / r"reports\c_series"


def scalar(con: sqlite3.Connection, sql: str, params: tuple = ()) -> object:
    row = con.execute(sql, params).fetchone()
    return row[0] if row else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate C-series relationship DB outputs.")
    ap.add_argument("--asof", required=True)
    args = ap.parse_args()
    asof = args.asof
    failures: list[str] = []
    checks: list[dict[str, object]] = []
    con = sqlite3.connect(str(C_DB))
    try:
        return_rows = int(scalar(con, "SELECT COUNT(*) FROM c_return_series WHERE asof_date=?", (asof,)) or 0)
        edge_rows = int(scalar(con, "SELECT COUNT(*) FROM c_relationship_edges WHERE asof_date=?", (asof,)) or 0)
        overlay_rows = int(scalar(con, "SELECT COUNT(*) FROM c_model_overlay_scores WHERE asof_date=?", (asof,)) or 0)
        theme_rows = int(scalar(con, "SELECT COUNT(*) FROM c_theme_return_series WHERE asof_date=?", (asof,)) or 0)
        run_status = scalar(con, "SELECT status FROM c_runs WHERE asof_date=? AND model_code='C-REL-V01' ORDER BY created_at DESC LIMIT 1", (asof,))
        relation_counts = dict(
            con.execute(
                "SELECT relation_type, COUNT(*) FROM c_relationship_edges WHERE asof_date=? GROUP BY relation_type",
                (asof,),
            ).fetchall()
        )
        overlay_counts = dict(
            con.execute(
                "SELECT scope, COUNT(*) FROM c_model_overlay_scores WHERE asof_date=? GROUP BY scope",
                (asof,),
            ).fetchall()
        )
        missing_confidence = int(
            scalar(
                con,
                "SELECT COUNT(*) FROM c_relationship_edges WHERE asof_date=? AND relationship_confidence_score IS NULL",
                (asof,),
            )
            or 0
        )
    finally:
        con.close()

    expected = {
        "return_rows_min": 500,
        "theme_rows_min": 3,
        "edge_rows_min": 1000,
        "overlay_rows_min": 1,
    }
    if run_status != "success":
        failures.append("run_status")
    if return_rows < expected["return_rows_min"]:
        failures.append("return_rows")
    if theme_rows < expected["theme_rows_min"]:
        failures.append("theme_rows")
    if edge_rows < expected["edge_rows_min"]:
        failures.append("edge_rows")
    if overlay_rows < expected["overlay_rows_min"]:
        failures.append("overlay_rows")
    if missing_confidence:
        failures.append("missing_confidence")
    if not {"Positive", "Negative", "Neutral"}.intersection(relation_counts):
        failures.append("relation_type_counts")

    checks.extend(
        [
            {"name": "run_status", "status": "pass" if run_status == "success" else "fail", "detail": run_status},
            {"name": "return_rows", "status": "pass" if return_rows >= expected["return_rows_min"] else "fail", "detail": return_rows},
            {"name": "theme_rows", "status": "pass" if theme_rows >= expected["theme_rows_min"] else "fail", "detail": theme_rows},
            {"name": "edge_rows", "status": "pass" if edge_rows >= expected["edge_rows_min"] else "fail", "detail": edge_rows},
            {"name": "overlay_rows", "status": "pass" if overlay_rows >= expected["overlay_rows_min"] else "fail", "detail": overlay_rows},
            {"name": "relation_counts", "status": "pass", "detail": relation_counts},
            {"name": "overlay_counts", "status": "pass", "detail": overlay_counts},
            {"name": "missing_confidence", "status": "pass" if missing_confidence == 0 else "fail", "detail": missing_confidence},
        ]
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "status": "pass" if not failures else "fail",
        "asof": asof,
        "failures": failures,
        "checks": checks,
    }
    token = asof.replace("-", "")
    report = REPORT_DIR / f"c_series_v01_validation_{token}.json"
    report.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**out, "report": str(report)}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
