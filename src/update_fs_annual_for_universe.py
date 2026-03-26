# update_fs_annual_for_universe.py ver 2026-02-02_001
import argparse
import os
import time
import sqlite3
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import requests


DART_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
REPRT_CODE_ANNUAL = "11011"  # 사업보고서


def _zfill6(x) -> str:
    return str(x).strip().zfill(6)


def _ensure_fs_annual_table(conn: sqlite3.Connection, table: str = "fs_annual"):
    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {table} (
        corp_code TEXT NOT NULL,
        bsns_year INTEGER NOT NULL,
        stock_code TEXT,
        corp_name TEXT,
        revenue REAL,
        op_income REAL,
        net_income REAL,
        assets REAL,
        liab REAL,
        equity REAL,
        op_cf REAL,
        PRIMARY KEY (corp_code, bsns_year)
    )
    """)
    conn.commit()


def _load_universe(universe_file: str, ticker_col: str) -> pd.DataFrame:
    u = pd.read_csv(universe_file)
    if ticker_col not in u.columns:
        raise ValueError(f"ticker_col not found: {ticker_col} in {list(u.columns)}")
    u[ticker_col] = u[ticker_col].apply(_zfill6)
    return u


def _load_dim_corp_listed(dart_db: str) -> pd.DataFrame:
    conn = sqlite3.connect(dart_db)
    dim = pd.read_sql_query("select stock_code, corp_code, corp_name from dim_corp_listed", conn)
    conn.close()
    dim["stock_code"] = dim["stock_code"].astype(str).str.zfill(6)
    return dim


def _dart_call(api_key: str, corp_code: str, year: int, fs_div: str, retries: int, sleep: float) -> Optional[Dict[str, Any]]:
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": REPRT_CODE_ANNUAL,
        "fs_div": fs_div,
    }
    last_err = None
    for _ in range(retries + 1):
        try:
            r = requests.get(DART_URL, params=params, timeout=30)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                time.sleep(sleep)
                continue
            data = r.json()
            # status: '000' 정상, 그 외는 없음/오류
            if str(data.get("status")) != "000":
                return None
            return data
        except Exception as e:
            last_err = str(e)
            time.sleep(sleep)
            continue
    if last_err:
        return None
    return None


def _pick_amount(items: List[Dict[str, Any]], candidates: List[Tuple[str, str]]) -> Optional[float]:
    """
    candidates: list of (account_id, account_nm_contains)
    우선순위대로 account_id 매칭, 없으면 account_nm 부분일치
    """
    # 1) account_id exact
    for acc_id, _ in candidates:
        for it in items:
            if str(it.get("account_id", "")).strip() == acc_id:
                v = it.get("thstrm_amount")
                return _to_float(v)
    # 2) account_nm contains
    for _, nm_contains in candidates:
        if not nm_contains:
            continue
        for it in items:
            nm = str(it.get("account_nm", "")).strip()
            if nm_contains in nm:
                v = it.get("thstrm_amount")
                return _to_float(v)
    return None


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        s = str(v).replace(",", "").strip()
        if s in ("", "-", "None"):
            return None
        return float(s)
    except Exception:
        return None


def _extract_fs_annual(items: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    # 계정 매핑(필요 시 후보를 더 추가해도 됨)
    revenue = _pick_amount(items, [
        ("ifrs_Revenue", "매출"),
        ("ifrs-full_Revenue", "매출"),
        ("ifrs_ProfitLoss", "수익"),  # fallback(업종에 따라 다름)
    ])
    op_income = _pick_amount(items, [
        ("ifrs_ProfitLossFromOperatingActivities", "영업이익"),
        ("ifrs-full_ProfitLossFromOperatingActivities", "영업이익"),
    ])
    net_income = _pick_amount(items, [
        ("ifrs_ProfitLoss", "당기순이익"),
        ("ifrs-full_ProfitLoss", "당기순이익"),
        ("ifrs_ProfitLossAttributableToOwnersOfParent", "당기순이익"),
    ])
    assets = _pick_amount(items, [
        ("ifrs_Assets", "자산총계"),
        ("ifrs-full_Assets", "자산총계"),
    ])
    liab = _pick_amount(items, [
        ("ifrs_Liabilities", "부채총계"),
        ("ifrs-full_Liabilities", "부채총계"),
    ])
    equity = _pick_amount(items, [
        ("ifrs_Equity", "자본총계"),
        ("ifrs-full_Equity", "자본총계"),
    ])
    op_cf = _pick_amount(items, [
        ("ifrs_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름"),
        ("ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름"),
        ("ifrs_CashFlowsFromUsedInOperatingActivities", "영업활동으로인한현금흐름"),
    ])
    return {
        "revenue": revenue,
        "op_income": op_income,
        "net_income": net_income,
        "assets": assets,
        "liab": liab,
        "equity": equity,
        "op_cf": op_cf,
    }


def upsert_fs_annual(conn: sqlite3.Connection, table: str, row: Dict[str, Any]):
    cols = list(row.keys())
    placeholders = ",".join(["?"] * len(cols))
    update_cols = [c for c in cols if c not in ("corp_code", "bsns_year")]
    update_clause = ",".join([f"{c}=excluded.{c}" for c in update_cols])
    sql = f"""
    INSERT INTO {table} ({",".join(cols)})
    VALUES ({placeholders})
    ON CONFLICT(corp_code, bsns_year) DO UPDATE SET {update_clause}
    """
    conn.execute(sql, [row[c] for c in cols])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dart-db", required=True)
    ap.add_argument("--universe-file", required=True)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--api-key", default=None, help="미지정 시 환경변수 DART_API_KEY 사용")
    ap.add_argument("--fs-table", default="fs_annual")
    ap.add_argument("--years", default="2015-2024", help="예: 2015-2024")
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--only-missing", action="store_true", help="fs_annual에 없는 종목만 수집(기본 True 권장)")
    args = ap.parse_args()

    api_key = args.api_key or os.getenv("DART_API_KEY")
    if not api_key:
        raise SystemExit("DART API key가 없습니다. --api-key 또는 환경변수 DART_API_KEY를 설정하세요.")

    y0, y1 = args.years.split("-")
    years = list(range(int(y0), int(y1) + 1))

    u = _load_universe(args.universe_file, args.ticker_col)
    dim = _load_dim_corp_listed(args.dart_db)
    m = u.merge(dim, left_on=args.ticker_col, right_on="stock_code", how="left")

    # corp_code 없는 종목 제외(상장/코드매핑 누락)
    miss_map = m[m["corp_code"].isna()][args.ticker_col].tolist()
    if miss_map:
        print(f"[WARN] corp_code mapping missing: n={len(miss_map)} | " + ",".join(miss_map[:50]))

    m = m.dropna(subset=["corp_code"]).copy()
    m["corp_code"] = m["corp_code"].astype(str)

    conn = sqlite3.connect(args.dart_db)
    _ensure_fs_annual_table(conn, args.fs_table)

    if args.only_missing:
        have = pd.read_sql_query(f"select distinct stock_code from {args.fs_table} where stock_code is not null", conn)
        have["stock_code"] = have["stock_code"].astype(str).str.zfill(6)
        before = len(m)
        m = m[~m["stock_code"].isin(set(have["stock_code"]))].copy()
        print(f"[INFO] only_missing: before={before} to_fetch={len(m)}")

    print(f"[INFO] universe rows={len(u)} | mapped={len(m)} | years={years[0]}..{years[-1]}")
    saved = 0
    failed = []

    for i, row in enumerate(m.itertuples(index=False), 1):
        ticker = getattr(row, "stock_code")
        corp_code = getattr(row, "corp_code")
        corp_name = getattr(row, "corp_name")

        # CFS 우선, 없으면 OFS
        for year in years:
            data = _dart_call(api_key, corp_code, year, "CFS", args.retries, args.sleep)
            if data is None:
                data = _dart_call(api_key, corp_code, year, "OFS", args.retries, args.sleep)

            if data is None:
                continue

            items = data.get("list", []) or []
            feats = _extract_fs_annual(items)

            # 유효값이 하나라도 있으면 저장
            if all(v is None for v in feats.values()):
                continue

            out = {
                "corp_code": corp_code,
                "bsns_year": year,
                "stock_code": ticker,
                "corp_name": corp_name,
                **feats,
            }
            upsert_fs_annual(conn, args.fs_table, out)
            saved += 1

        if i % 20 == 0:
            conn.commit()
            print(f"[INFO] progress: {i}/{len(m)} tickers | saved_rows={saved}")

        time.sleep(args.sleep)

    conn.commit()
    conn.close()
    print(f"[DONE] saved_rows={saved} (corp_year rows)")
    if failed:
        print("[FAIL] " + ",".join(failed))


if __name__ == "__main__":
    main()
