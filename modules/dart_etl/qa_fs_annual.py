# qa_fs_annual.py ver 2025-12-30_001
"""
DART 연간 재무 테이블(fs_annual) QA(품질 점검) 스크립트

- DB 기본 위치: <project_root>/data/db/dart_main.db (환경변수 DART_DB_PATH로 override 가능)
- 출력: <project_root>/reports/qa_fs_annual_YYYYMMDD.csv

주요 기능
1) fs_annual 테이블 존재 확인
2) 컬럼 자동 매칭(매출/영업이익/순이익/자산/부채/자본/CFO)
3) 결측 비율, 이상치 룰(자산=부채 등) 탐지
4) 샘플 기업(삼성전자 포함) 상세 레코드 요약
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


def _find_project_root(start_path: Path) -> Path:
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    return start_path


def _default_dart_db_path() -> Path:
    env = os.getenv("DART_DB_PATH")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    root = _find_project_root(here.parent)
    return root / "data" / "db" / "dart_main.db"


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _utcnow_tag() -> str:
    return datetime.utcnow().strftime("%Y%m%d")


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name=?;",
        (table,),
    )
    return cur.fetchone() is not None


def _get_columns(con: sqlite3.Connection, table: str) -> List[str]:
    cur = con.execute(f"PRAGMA table_info({table});")
    cols = [r[1] for r in cur.fetchall()]
    return cols


def _normalize(s: str) -> str:
    return s.lower().replace(" ", "").replace("-", "").replace("_", "")


def _pick_col(columns: List[str], candidates: List[str]) -> Optional[str]:
    """
    columns: 실제 컬럼명 리스트
    candidates: 후보 키워드 리스트(정규화 비교)
    """
    norm_map = {_normalize(c): c for c in columns}
    for cand in candidates:
        key = _normalize(cand)
        if key in norm_map:
            return norm_map[key]
    # 부분매칭(약하게)
    for c in columns:
        nc = _normalize(c)
        for cand in candidates:
            if _normalize(cand) in nc:
                return c
    return None


@dataclass
class FsAnnualSchema:
    table: str
    corp_code: str
    bsns_year: str
    fs_div: Optional[str]
    revenue: Optional[str]
    op_income: Optional[str]
    net_income: Optional[str]
    assets: Optional[str]
    liab: Optional[str]
    equity: Optional[str]
    cfo: Optional[str]


def infer_schema(con: sqlite3.Connection, table: str = "fs_annual") -> FsAnnualSchema:
    cols = _get_columns(con, table)

    corp_code = _pick_col(cols, ["corp_code", "corpcode"])
    bsns_year = _pick_col(cols, ["bsns_year", "year", "fiscal_year", "bsnsyear"])

    # 선택 컬럼들
    fs_div = _pick_col(cols, ["fs_div", "fsdiv", "cfs_ofs", "consolidated"])

    revenue = _pick_col(cols, ["revenue", "sales", "net_sales", "sale", "매출", "매출액"])
    op_income = _pick_col(cols, ["op_income", "operating_income", "영업이익", "영업손익"])
    net_income = _pick_col(cols, ["net_income", "profit", "당기순이익", "당기손익", "순이익"])

    assets = _pick_col(cols, ["assets", "asset_total", "자산", "자산총계"])
    liab = _pick_col(cols, ["liab", "liabilities", "부채", "부채총계"])
    equity = _pick_col(cols, ["equity", "자본", "자본총계"])

    cfo = _pick_col(cols, ["cfo", "operating_cash_flow", "영업활동현금흐름", "영업활동현금흐름액"])

    if corp_code is None or bsns_year is None:
        raise RuntimeError(
            f"[SCHEMA] 필수 컬럼 매칭 실패: corp_code={corp_code}, bsns_year={bsns_year}. "
            f"실제 컬럼={cols}"
        )

    return FsAnnualSchema(
        table=table,
        corp_code=corp_code,
        bsns_year=bsns_year,
        fs_div=fs_div,
        revenue=revenue,
        op_income=op_income,
        net_income=net_income,
        assets=assets,
        liab=liab,
        equity=equity,
        cfo=cfo,
    )


def load_sample(con: sqlite3.Connection, schema: FsAnnualSchema, limit: int = 200000) -> pd.DataFrame:
    """
    전체를 다 읽기엔 무거울 수 있으니 limit를 둡니다.
    (일반적으로 상장사 연간데이터면 수십만행 이하로 관리 가능)
    """
    cols = [schema.corp_code, schema.bsns_year]
    if schema.fs_div:
        cols.append(schema.fs_div)
    for x in [schema.revenue, schema.op_income, schema.net_income, schema.assets, schema.liab, schema.equity, schema.cfo]:
        if x:
            cols.append(x)

    col_sql = ", ".join([f'"{c}"' for c in cols])
    sql = f"""
    SELECT {col_sql}
    FROM "{schema.table}"
    LIMIT {int(limit)};
    """
    df = pd.read_sql_query(sql, con)
    return df


def compute_qa(df: pd.DataFrame, schema: FsAnnualSchema) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    반환:
      - qa_summary: 컬럼별 결측/기본 통계
      - colmap: logical_name -> actual_column
    """
    colmap = {
        "corp_code": schema.corp_code,
        "bsns_year": schema.bsns_year,
        "fs_div": schema.fs_div or "",
        "revenue": schema.revenue or "",
        "op_income": schema.op_income or "",
        "net_income": schema.net_income or "",
        "assets": schema.assets or "",
        "liab": schema.liab or "",
        "equity": schema.equity or "",
        "cfo": schema.cfo or "",
    }

    # 숫자 컬럼은 numeric으로 강제 변환(문자/콤마 대비)
    numeric_cols = [schema.revenue, schema.op_income, schema.net_income, schema.assets, schema.liab, schema.equity, schema.cfo]
    for c in numeric_cols:
        if c and c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 기본 QA
    rows = []
    for logical, actual in colmap.items():
        if not actual or actual not in df.columns:
            rows.append(
                {
                    "field": logical,
                    "column": actual or "(missing)",
                    "exists": False,
                    "null_ratio": None,
                    "min": None,
                    "max": None,
                    "mean": None,
                }
            )
            continue

        s = df[actual]
        null_ratio = float(s.isna().mean())
        if pd.api.types.is_numeric_dtype(s):
            rows.append(
                {
                    "field": logical,
                    "column": actual,
                    "exists": True,
                    "null_ratio": null_ratio,
                    "min": None if s.dropna().empty else float(s.min()),
                    "max": None if s.dropna().empty else float(s.max()),
                    "mean": None if s.dropna().empty else float(s.mean()),
                }
            )
        else:
            rows.append(
                {
                    "field": logical,
                    "column": actual,
                    "exists": True,
                    "null_ratio": null_ratio,
                    "min": None,
                    "max": None,
                    "mean": None,
                }
            )

    qa_summary = pd.DataFrame(rows)

    return qa_summary, colmap


def anomaly_flags(df: pd.DataFrame, schema: FsAnnualSchema) -> pd.DataFrame:
    """
    자주 터지는 매핑/피벗 오류 탐지용 경고 플래그.
    """
    out = df[[schema.corp_code, schema.bsns_year]].copy()
    if schema.fs_div and schema.fs_div in df.columns:
        out["fs_div"] = df[schema.fs_div]

    def _get(c: Optional[str]) -> pd.Series:
        if not c or c not in df.columns:
            return pd.Series([pd.NA] * len(df))
        return df[c]

    assets = _get(schema.assets)
    liab = _get(schema.liab)
    equity = _get(schema.equity)
    revenue = _get(schema.revenue)
    op_income = _get(schema.op_income)
    net_income = _get(schema.net_income)

    out["flag_assets_eq_liab"] = (assets.notna() & liab.notna() & (assets == liab))
    out["flag_assets_eq_equity"] = (assets.notna() & equity.notna() & (assets == equity))
    out["flag_liab_eq_equity"] = (liab.notna() & equity.notna() & (liab == equity))
    out["flag_assets_le_0"] = assets.notna() & (assets <= 0)
    out["flag_revenue_le_0"] = revenue.notna() & (revenue <= 0)

    # 경고성(절대오류는 아님)
    out["warn_op_eq_net"] = (op_income.notna() & net_income.notna() & (op_income == net_income))

    # flag count
    flag_cols = [c for c in out.columns if c.startswith("flag_") or c.startswith("warn_")]
    out["flags_total"] = out[flag_cols].sum(axis=1).astype(int)

    return out


def main() -> None:
    db_path = _default_dart_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"DART DB 파일이 없습니다: {db_path}")

    with _connect(db_path) as con:
        table = "fs_annual"
        if not _table_exists(con, table):
            raise RuntimeError(f"'{table}' 테이블/뷰가 DB에 없습니다. DB={db_path}")

        schema = infer_schema(con, table=table)
        df = load_sample(con, schema, limit=300000)

    qa_summary, colmap = compute_qa(df, schema)
    flags = anomaly_flags(df, schema)

    # 샘플(삼성전자 corp_code = 00126380, 있으면 5개만)
    sample_corp_code = "00126380"
    sample = flags[flags[schema.corp_code] == sample_corp_code].sort_values(schema.bsns_year).tail(10)

    # 요약 집계
    top_flags = (
        flags[flags["flags_total"] > 0]
        .groupby("flags_total")
        .size()
        .reset_index(name="count")
        .sort_values("flags_total", ascending=False)
    )

    # 출력
    here = Path(__file__).resolve()
    root = _find_project_root(here.parent)
    out_dir = root / "reports"
    _ensure_parent_dir(out_dir / "dummy.txt")

    out_path = out_dir / f"qa_fs_annual_{_utcnow_tag()}.csv"

    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write("# fs_annual QA report\n")
        f.write(f"# db_path={db_path}\n")
        f.write(f"# table={schema.table}\n")
        f.write("# column_map(logical->actual)\n")
        for k, v in colmap.items():
            if v:
                f.write(f"#   {k} -> {v}\n")
        f.write("\n")

    # 섹션별로 append
    qa_summary.to_csv(out_path, mode="a", index=False, encoding="utf-8-sig")
    with open(out_path, "a", encoding="utf-8-sig") as f:
        f.write("\n# anomaly_summary(flags_total -> count)\n")
    top_flags.to_csv(out_path, mode="a", index=False, encoding="utf-8-sig")

    with open(out_path, "a", encoding="utf-8-sig") as f:
        f.write("\n# sample_records(corp_code=00126380)\n")
    sample.to_csv(out_path, mode="a", index=False, encoding="utf-8-sig")

    print(f"[DONE] QA report saved: {out_path}")


if __name__ == "__main__":
    main()
