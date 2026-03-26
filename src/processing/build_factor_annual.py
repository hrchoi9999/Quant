# build_factor_annual.py ver 2025-12-30_001
"""
DART fs_annual(연간 재무) -> 연간 팩터(ROE, 영업이익률) 생성

- 입력: <project_root>/data/db/dart_main.db 의 fs_annual (+ dim_corp가 있으면 stock_code 매핑)
- 출력: <project_root>/data/processed/factor_annual.(parquet|csv)

룩어헤드 방지를 위해, 연간 재무(YYYY)는 다음 해 3/31부터 유효(effective_date)로 설정합니다.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

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


def _normalize(s: str) -> str:
    return s.lower().replace(" ", "").replace("-", "").replace("_", "")


def _pick_col(columns: list[str], candidates: list[str]) -> Optional[str]:
    norm_map = {_normalize(c): c for c in columns}
    for cand in candidates:
        key = _normalize(cand)
        if key in norm_map:
            return norm_map[key]
    for c in columns:
        nc = _normalize(c)
        for cand in candidates:
            if _normalize(cand) in nc:
                return c
    return None


def _get_columns(con: sqlite3.Connection, table: str) -> list[str]:
    cur = con.execute(f"PRAGMA table_info({table});")
    return [r[1] for r in cur.fetchall()]


def main() -> None:
    db_path = _default_dart_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"DART DB 파일이 없습니다: {db_path}")

    with _connect(db_path) as con:
        if not _table_exists(con, "fs_annual"):
            raise RuntimeError("fs_annual 테이블/뷰가 없습니다.")

        fs_cols = _get_columns(con, "fs_annual")

        corp_code = _pick_col(fs_cols, ["corp_code", "corpcode"])
        bsns_year = _pick_col(fs_cols, ["bsns_year", "year", "fiscal_year"])
        fs_div = _pick_col(fs_cols, ["fs_div", "cfs_ofs"])

        revenue = _pick_col(fs_cols, ["revenue", "sales", "매출", "매출액"])
        op_income = _pick_col(fs_cols, ["op_income", "operating_income", "영업이익", "영업손익"])
        net_income = _pick_col(fs_cols, ["net_income", "profit", "당기순이익", "당기손익", "순이익"])
        equity = _pick_col(fs_cols, ["equity", "자본", "자본총계"])

        if corp_code is None or bsns_year is None:
            raise RuntimeError(f"필수 컬럼 매칭 실패: corp_code={corp_code}, bsns_year={bsns_year}")

        # dim_corp가 있으면 stock_code(6자리) 매핑
        has_dim_corp = _table_exists(con, "dim_corp")
        stock_code_col = None
        if has_dim_corp:
            dim_cols = _get_columns(con, "dim_corp")
            stock_code_col = _pick_col(dim_cols, ["stock_code", "stockcode", "종목코드"])

        # SELECT 구성
        select_cols = [f'f."{corp_code}" AS corp_code', f'f."{bsns_year}" AS bsns_year']
        if fs_div:
            select_cols.append(f'f."{fs_div}" AS fs_div')

        if revenue:
            select_cols.append(f'f."{revenue}" AS revenue')
        else:
            select_cols.append("NULL AS revenue")

        if op_income:
            select_cols.append(f'f."{op_income}" AS op_income')
        else:
            select_cols.append("NULL AS op_income")

        if net_income:
            select_cols.append(f'f."{net_income}" AS net_income')
        else:
            select_cols.append("NULL AS net_income")

        if equity:
            select_cols.append(f'f."{equity}" AS equity')
        else:
            select_cols.append("NULL AS equity")

        if has_dim_corp and stock_code_col:
            select_cols.append(f'd."{stock_code_col}" AS ticker')
            sql = f"""
            SELECT {", ".join(select_cols)}
            FROM fs_annual f
            LEFT JOIN dim_corp d
              ON d.corp_code = f."{corp_code}"
            """
        else:
            select_cols.append("NULL AS ticker")
            sql = f"""
            SELECT {", ".join(select_cols)}
            FROM fs_annual f
            """

        df = pd.read_sql_query(sql, con)

    # 타입 정리
    df["bsns_year"] = pd.to_numeric(df["bsns_year"], errors="coerce").astype("Int64")
    for c in ["revenue", "op_income", "net_income", "equity"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # ticker 정리(6자리)
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        df.loc[df["ticker"].isin(["None", "nan", "NaN", ""]), "ticker"] = pd.NA
        df["ticker"] = df["ticker"].apply(lambda x: x.zfill(6) if isinstance(x, str) and x.isdigit() else x)

    # 팩터 계산
    # ROE = net_income / equity
    df["roe"] = df["net_income"] / df["equity"]
    # 영업이익률 = op_income / revenue
    df["op_margin"] = df["op_income"] / df["revenue"]

    # 유효일(룩어헤드 방지용): YYYY년 실적은 (YYYY+1)-03-31부터
    def _eff_date(y: int) -> str:
        if y is None:
            return None  # type: ignore
        return f"{int(y)+1}-03-31"

    df["effective_date"] = df["bsns_year"].apply(lambda y: _eff_date(int(y)) if pd.notna(y) else pd.NA)
    df["effective_date"] = pd.to_datetime(df["effective_date"], errors="coerce")

    # 최소한의 품질 필터(필요 시 강화)
    # equity/revenue가 0 또는 음수면 팩터 왜곡 → NA 처리
    df.loc[df["equity"].notna() & (df["equity"] <= 0), "roe"] = pd.NA
    df.loc[df["revenue"].notna() & (df["revenue"] <= 0), "op_margin"] = pd.NA

    # 저장
    here = Path(__file__).resolve()
    root = _find_project_root(here.parent)
    out_dir = root / "data" / "processed"
    _ensure_parent_dir(out_dir / "dummy.txt")

    out_parquet = out_dir / "factor_annual.parquet"
    out_csv = out_dir / "factor_annual.csv"

    # parquet 우선, 불가하면 csv
    try:
        df.to_parquet(out_parquet, index=False)
        print(f"[DONE] saved: {out_parquet}")
    except Exception as e:
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"[WARN] parquet 저장 실패({e}). 대신 CSV 저장: {out_csv}")


if __name__ == "__main__":
    main()
