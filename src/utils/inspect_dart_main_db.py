# inspect_dart_main_db.py ver 2026-02-02_001
"""
DART 메인 DB(dart_main.db) 구조/내용 빠른 점검 스크립트

- 테이블 목록
- 각 테이블 스키마(PRAGMA table_info)
- 행 수
- 날짜/연도 컬럼 후보가 있으면 min/max (가능한 경우)
- 샘플 5행
- 매출/영업이익 관련 컬럼 후보 탐색(컬럼명 기반)

사용 예:
  python .\inspect_dart_main_db.py --db "D:\Quant\data\db\dart_main.db" --limit 5
"""

from __future__ import annotations

import argparse
import sqlite3
from typing import List, Tuple, Optional, Dict


def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def fetchall(con: sqlite3.Connection, q: str, params: Tuple = ()) -> List[sqlite3.Row]:
    cur = con.execute(q, params)
    return cur.fetchall()


def fetchone(con: sqlite3.Connection, q: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
    cur = con.execute(q, params)
    return cur.fetchone()


def list_tables(con: sqlite3.Connection) -> List[str]:
    rows = fetchall(
        con,
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """,
    )
    return [r["name"] for r in rows]


def table_info(con: sqlite3.Connection, table: str) -> List[Dict]:
    rows = fetchall(con, f"PRAGMA table_info({table})")
    out = []
    for r in rows:
        out.append(
            {
                "cid": r["cid"],
                "name": r["name"],
                "type": r["type"],
                "notnull": r["notnull"],
                "dflt_value": r["dflt_value"],
                "pk": r["pk"],
            }
        )
    return out


def table_count(con: sqlite3.Connection, table: str) -> int:
    r = fetchone(con, f"SELECT COUNT(*) AS n FROM {table}")
    return int(r["n"]) if r else 0


def guess_time_cols(cols: List[str]) -> List[str]:
    """
    흔히 쓰는 날짜/연도 컬럼명 후보를 찾아봅니다.
    """
    keys = [
        "date",
        "dt",
        "ymd",
        "bas_dt",
        "trade_date",
        "report_date",
        "rcept_dt",
        "bsns_year",
        "year",
        "quarter",
        "qtr",
        "reprt_code",
        "period",
        "fiscal",
    ]
    cols_l = [c.lower() for c in cols]
    hits = []
    for c, cl in zip(cols, cols_l):
        if any(k in cl for k in keys):
            hits.append(c)
    return hits


def minmax_if_possible(con: sqlite3.Connection, table: str, col: str) -> Optional[Tuple[str, str]]:
    """
    컬럼이 TEXT/INTEGER/REAL이어도 min/max를 시도합니다.
    실패하면 None.
    """
    try:
        r = fetchone(con, f"SELECT MIN({col}) AS mn, MAX({col}) AS mx FROM {table}")
        if not r:
            return None
        return (str(r["mn"]), str(r["mx"]))
    except Exception:
        return None


def sample_rows(con: sqlite3.Connection, table: str, limit: int = 5) -> List[sqlite3.Row]:
    return fetchall(con, f"SELECT * FROM {table} LIMIT {limit}")


def find_growth_cols(cols: List[str]) -> Dict[str, List[str]]:
    """
    S2에서 우선 보려는 지표(매출, 영업이익) 컬럼 후보를 '컬럼명' 기반으로 탐색합니다.
    실제 확정은 샘플/스키마를 보고 결정합니다.
    """
    patterns = {
        "revenue": ["revenue", "sales", "매출", "rev", "sale_amt", "sales_amt"],
        "op_income": ["op_income", "operating_income", "영업이익", "oper_profit", "op_profit"],
    }
    cols_l = [(c, c.lower()) for c in cols]

    hits: Dict[str, List[str]] = {"revenue": [], "op_income": []}
    for c, cl in cols_l:
        for k, pats in patterns.items():
            if any(p.lower() in cl for p in pats):
                hits[k].append(c)
    return hits


def print_table_block(con: sqlite3.Connection, table: str, limit: int) -> None:
    info = table_info(con, table)
    cols = [x["name"] for x in info]

    print("\n" + "-" * 92)
    print(f"table: {table}")
    print("schema:")
    print(" cid  name                 type       notnull  pk  dflt_value")
    for x in info:
        nm = (x["name"][:20] + "..") if len(x["name"]) > 22 else x["name"]
        tp = x["type"] or ""
        print(f"{x['cid']:>4}  {nm:<22} {tp:<10} {x['notnull']!s:<7} {x['pk']!s:<3} {str(x['dflt_value'])}")

    n = table_count(con, table)
    print(f"rows: {n:,}")

    # time col hints
    time_cols = guess_time_cols(cols)
    if time_cols:
        print(f"time-like cols: {time_cols}")
        for tc in time_cols[:5]:  # 너무 길어지지 않게 상위 5개만
            mm = minmax_if_possible(con, table, tc)
            if mm:
                print(f"  min/max {tc}: {mm[0]} .. {mm[1]}")

    # growth col hints
    growth_hits = find_growth_cols(cols)
    if growth_hits["revenue"] or growth_hits["op_income"]:
        print("growth metric col candidates:")
        if growth_hits["revenue"]:
            print(f"  revenue candidates: {growth_hits['revenue']}")
        if growth_hits["op_income"]:
            print(f"  op_income candidates: {growth_hits['op_income']}")

    # sample
    rows = sample_rows(con, table, limit=limit)
    if not rows:
        print("sample: (empty)")
        return

    print(f"sample (top {limit}):")
    # print as key=value pairs (폭 제한 대응)
    for i, r in enumerate(rows, 1):
        items = []
        for k in r.keys():
            v = r[k]
            s = str(v)
            if len(s) > 60:
                s = s[:57] + "..."
            items.append(f"{k}={s}")
        line = " | ".join(items)
        print(f"  [{i}] {line}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to dart_main.db")
    ap.add_argument("--limit", type=int, default=5, help="sample rows per table (default: 5)")
    ap.add_argument("--tables", default="", help="comma-separated table names to inspect (default: all)")
    args = ap.parse_args()

    con = connect(args.db)
    try:
        tables = list_tables(con)
        if not tables:
            print(f"[ERROR] no tables found in: {args.db}")
            return

        if args.tables.strip():
            wanted = [t.strip() for t in args.tables.split(",") if t.strip()]
            missing = [t for t in wanted if t not in tables]
            if missing:
                print(f"[WARN] requested tables not found: {missing}")
            tables = [t for t in wanted if t in tables]

        print("=" * 92)
        print(f"[dart_main] {args.db}")
        print(f"tables({len(tables)}): {tables}")

        for t in tables:
            print_table_block(con, t, limit=args.limit)

        print("\n" + "=" * 92)
        print("[DONE]")
    finally:
        con.close()


if __name__ == "__main__":
    main()
