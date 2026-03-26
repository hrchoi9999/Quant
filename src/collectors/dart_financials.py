# dart_financials.py ver 2026-02-02_001

"""
DART에서 국내 상장사 재무제표/공시 데이터를 수집하는 모듈.

역할:
- 상장사 목록(corp_code, 종목코드 등) 조회 및 캐시 저장
- 특정 연도/보고서 유형 재무제표 수집
  (재무상태표, 손익계산서, 현금흐름표 등 – DART fnlttSinglAcntAll API 사용)
- 원본 데이터를 data/raw/dart/ 경로에 저장 (Parquet)

※ 보안상 API Key는 .env 파일의 DART_API_KEY 환경변수에서 읽어온다.
"""

from __future__ import annotations

from typing import Dict, Any, Optional, Iterable, Tuple, List
import io
import os
import zipfile
import pathlib
import time
import argparse
import sqlite3

import pandas as pd
import requests
from dotenv import load_dotenv
import xml.etree.ElementTree as ET


# -------------------------------------------------------------------
# 경로 및 상수 정의
# -------------------------------------------------------------------
ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
RAW_DART_DIR = ROOT_DIR / "data" / "raw" / "dart"
RAW_DART_DIR.mkdir(parents=True, exist_ok=True)

CORP_LIST_PARQUET = RAW_DART_DIR / "corp_list.parquet"

DART_BASE_URL = "https://opendart.fss.or.kr/api"
DART_CORP_CODE_URL = f"{DART_BASE_URL}/corpCode.xml"          # 상장사 코드
DART_FNLTT_SINGLE_URL = f"{DART_BASE_URL}/fnlttSinglAcntAll.json"  # 단일회사 전체 재무제표


# -------------------------------------------------------------------
# 유틸: API 키 로딩
# -------------------------------------------------------------------
def get_dart_api_key() -> str:
    """환경변수(.env)에서 DART_API_KEY를 읽어온다.

    .env 파일 예:
        DART_API_KEY=...
    """
    # .env 로드 (여러 번 호출해도 문제 없음)
    load_dotenv()
    key = os.getenv("DART_API_KEY")
    if not key:
        raise RuntimeError(
            "DART_API_KEY 환경변수가 설정되어 있지 않습니다. "
            ".env 파일에 DART_API_KEY=... 형태로 추가해 주세요."
        )
    return key


# -------------------------------------------------------------------
# 1. 상장사 목록 조회
# -------------------------------------------------------------------
def _download_corp_list_xml() -> bytes:
    """DART에서 corpCode.zip을 받아서, 내부 XML 파일의 raw bytes를 반환."""
    api_key = get_dart_api_key()
    params = {"crtfc_key": api_key}
    resp = requests.get(DART_CORP_CODE_URL, params=params, timeout=30)
    resp.raise_for_status()

    # 응답은 ZIP 형식의 바이너리
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # 일반적으로 'CORPCODE.xml' 하나만 들어 있음
        # 정확한 이름을 모르더라도 첫 번째 XML 파일을 사용
        xml_name = None
        for name in zf.namelist():
            if name.lower().endswith(".xml"):
                xml_name = name
                break
        if xml_name is None:
            raise RuntimeError("corpCode.zip 안에서 XML 파일을 찾지 못했습니다.")

        with zf.open(xml_name) as f:
            xml_bytes = f.read()

    return xml_bytes


def get_corp_list(force_refresh: bool = False) -> pd.DataFrame:
    """상장사 목록(corp_code, corp_name, stock_code, modify_date 등)을 반환한다.

    - 기본적으로 data/raw/dart/corp_list.parquet 를 캐시로 사용
    - force_refresh=True 이면 무조건 DART에서 다시 받아온다.
    """
    if CORP_LIST_PARQUET.exists() and not force_refresh:
        return pd.read_parquet(CORP_LIST_PARQUET)

    xml_bytes = _download_corp_list_xml()

    # XML 파싱
    root = ET.fromstring(xml_bytes.decode("utf-8"))
    rows = []
    for el in root.findall("list"):
        rows.append(
            {
                "corp_code": el.findtext("corp_code"),
                "corp_name": el.findtext("corp_name"),
                "stock_code": el.findtext("stock_code"),  # 상장 종목코드(비상장일 경우 공백)
                "modify_date": el.findtext("modify_date"),
            }
        )

    df = pd.DataFrame(rows)
    # 정렬: 상장사만 우선(주식코드 있는 것)
    df = df.sort_values(["stock_code", "corp_name"], na_position="last").reset_index(drop=True)

    CORP_LIST_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CORP_LIST_PARQUET, index=False)

    return df


# -------------------------------------------------------------------
# 2. 재무제표 조회 (fnlttSinglAcntAll)
# -------------------------------------------------------------------
def fetch_financial_statements(
    corp_code: str,
    year: int,
    report_code: str = "11011",
    fs_div: str = "CFS",
) -> pd.DataFrame:
    """단일 기업(corp_code)의 특정 연도/보고서 유형 재무제표를 DataFrame으로 반환.

    DART fnlttSinglAcntAll API 사용.

    파라미터:
        corp_code : DART에서 부여한 회사 고유 코드 (corp_list에서 가져옴)
        year      : 사업연도 (예: 2023)
        report_code :
            - '11011' : 사업보고서(연간)
            - '11012' : 반기보고서
            - '11013' : 1분기보고서
            - '11014' : 3분기보고서
        fs_div :
            - 'CFS' : 연결재무제표
            - 'OFS' : 별도재무제표

    반환:
        재무제표 항목별 DataFrame (DART에서 내려주는 list 그대로를 테이블화)
    """
    api_key = get_dart_api_key()

    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": report_code,
        "fs_div": fs_div,
    }

    resp = requests.get(DART_FNLTT_SINGLE_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    status = data.get("status")
    msg = data.get("message", "")

    # 000 : 정상
    if status == "000":
        items = data.get("list", [])
        if not items:
            return pd.DataFrame()
        return pd.DataFrame(items)

    # 013 : 조회된 데이터 없음 → 에러로 보지 말고 빈 DF 반환
    if status == "013":
        # 예: 해당 연도에 아직 공시가 없거나, 해당 회사 유형상 재무제표 미제공 등
        return pd.DataFrame()

    # 그 외 코드는 진짜 에러로 처리
    raise RuntimeError(f"DART fnlttSinglAcntAll 오류 (status={status}): {msg}")

def save_raw_financials(
    df: pd.DataFrame,
    corp_code: str,
    year: int,
    report_code: str,
    fs_div: str = "CFS",
) -> pathlib.Path:
    """수집한 재무제표를 data/raw/dart/ 아래 파일로 저장하고 경로를 반환한다.

    파일명 예:
        fs_00126380_2023_11011_CFS.parquet
    """
    RAW_DART_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"fs_{corp_code}_{year}_{report_code}_{fs_div}.parquet"
    path = RAW_DART_DIR / filename
    df.to_parquet(path, index=False)
    return path


# -------------------------------------------------------------------
# 2-b. fs_annual(요약 재무지표) 추출/DB 적재 유틸
# -------------------------------------------------------------------

def _to_float(x: Any) -> Optional[float]:
    """DART가 내려주는 금액 필드를 float으로 변환."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return None
    # 쉼표/공백 제거
    s = s.replace(",", "").replace(" ", "")
    # 괄호 음수 처리: (123) -> -123
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except Exception:
        return None


def _pick_first_amount(df: pd.DataFrame) -> Optional[float]:
    """필터링된 df에서 thstrm_amount 우선으로 첫 값을 뽑는다."""
    if df is None or df.empty:
        return None
    # ord가 있으면 우선순위로 사용
    if "ord" in df.columns:
        df = df.sort_values("ord", kind="stable")
    # thstrm_amount가 가장 일반적
    for col in ["thstrm_amount", "thstrm_amount " , "thstrm_amount\t", "thstrm_amount\n", "thstrm_amount\r", "thstrm_amount\f"]:
        if col in df.columns:
            v = _to_float(df.iloc[0][col])
            if v is not None:
                return v
    # fallback: amount로 끝나는 컬럼
    amt_cols = [c for c in df.columns if c.endswith("amount")]
    for c in amt_cols:
        v = _to_float(df.iloc[0][c])
        if v is not None:
            return v
    return None


def extract_fs_annual_metrics(df_raw: pd.DataFrame) -> Dict[str, Optional[float]]:
    """fnlttSinglAcntAll 원본 DF에서 fs_annual 핵심 지표를 추출한다.

    목표 컬럼:
      - revenue, op_income, net_income, assets, liab, equity, op_cf

    주의:
      - 회사/연도/보고서에 따라 계정명이 다르므로 account_id + account_nm(한글) 모두로 휴리스틱 매칭.
      - 매칭 실패 시 None 반환.
    """
    if df_raw is None or df_raw.empty:
        return {
            "revenue": None,
            "op_income": None,
            "net_income": None,
            "assets": None,
            "liab": None,
            "equity": None,
            "op_cf": None,
        }

    d = df_raw.copy()
    # 표준화
    for c in ["account_id", "account_nm", "sj_div"]:
        if c in d.columns:
            d[c] = d[c].astype(str)

    def _f(sj_div: str, id_keys: Iterable[str], nm_keys: Iterable[str]) -> pd.DataFrame:
        x = d
        if "sj_div" in x.columns and sj_div:
            x = x[x["sj_div"].astype(str).str.upper() == sj_div.upper()]
        cond = pd.Series(False, index=x.index)
        if "account_id" in x.columns:
            for k in id_keys:
                cond |= x["account_id"].str.contains(k, case=False, na=False)
        if "account_nm" in x.columns:
            for k in nm_keys:
                cond |= x["account_nm"].str.contains(k, case=False, na=False)
        return x[cond]

    # 손익계산서(IS)
    revenue = _pick_first_amount(
        _f(
            "IS",
            id_keys=[
                "Revenue",
                "revenue",
                "ifrs-full_Revenue",
                "ifrs_Revenue",
                "ifrs-full_Sales",
            ],
            nm_keys=["매출", "수익"],
        )
    )
    op_income = _pick_first_amount(
        _f(
            "IS",
            id_keys=[
                "OperatingProfit",
                "OperatingIncome",
                "ifrs-full_ProfitLossFromOperatingActivities",
                "ifrs-full_OperatingProfitLoss",
            ],
            nm_keys=["영업이익", "영업손익"],
        )
    )
    net_income = _pick_first_amount(
        _f(
            "IS",
            id_keys=[
                "ProfitLoss",
                "NetIncome",
                "ifrs-full_ProfitLoss",
                "ifrs-full_ProfitLossAttributableToOwnersOfParent",
            ],
            nm_keys=["당기순이익", "순이익", "지배기업소유주지분"],
        )
    )

    # 재무상태표(BS)
    assets = _pick_first_amount(
        _f(
            "BS",
            id_keys=["Assets", "ifrs-full_Assets"],
            nm_keys=["자산총계", "자산 합계", "자산"],
        )
    )
    liab = _pick_first_amount(
        _f(
            "BS",
            id_keys=["Liabilities", "ifrs-full_Liabilities"],
            nm_keys=["부채총계", "부채 합계", "부채"],
        )
    )
    equity = _pick_first_amount(
        _f(
            "BS",
            id_keys=["Equity", "ifrs-full_Equity"],
            nm_keys=["자본총계", "자본 합계", "자본"],
        )
    )

    # 현금흐름표(CF)
    op_cf = _pick_first_amount(
        _f(
            "CF",
            id_keys=[
                "NetCashFlowsFromUsedInOperatingActivities",
                "CashFlowsFromUsedInOperatingActivities",
                "OperatingActivities",
            ],
            nm_keys=["영업활동", "영업활동현금흐름", "영업활동으로", "영업활동에"],
        )
    )

    return {
        "revenue": revenue,
        "op_income": op_income,
        "net_income": net_income,
        "assets": assets,
        "liab": liab,
        "equity": equity,
        "op_cf": op_cf,
    }


def fetch_financial_statements_with_fallback(
    corp_code: str,
    year: int,
    report_code: str = "11011",
    prefer_fs_div: str = "CFS",
) -> Tuple[pd.DataFrame, str]:
    """CFS 우선(또는 prefer_fs_div)으로 조회 후 비면 OFS로 fallback."""
    prefer = prefer_fs_div.upper().strip() or "CFS"
    first = prefer
    second = "OFS" if first == "CFS" else "CFS"
    df1 = fetch_financial_statements(corp_code, year, report_code, first)
    if df1 is not None and not df1.empty:
        return df1, first
    df2 = fetch_financial_statements(corp_code, year, report_code, second)
    return df2, second


def ensure_fs_annual_table(conn: sqlite3.Connection, table: str = "fs_annual") -> None:
    """fs_annual 테이블이 없으면 생성(있으면 유지)."""
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            corp_code   TEXT    NOT NULL,
            bsns_year   INTEGER NOT NULL,
            stock_code  TEXT,
            corp_name   TEXT,
            revenue     REAL,
            op_income   REAL,
            net_income  REAL,
            assets      REAL,
            liab        REAL,
            equity      REAL,
            op_cf       REAL,
            PRIMARY KEY (corp_code, bsns_year)
        );
        """
    )
    conn.commit()


def upsert_fs_annual(
    conn: sqlite3.Connection,
    row: Dict[str, Any],
    table: str = "fs_annual",
) -> None:
    """(corp_code, bsns_year) PK 기준 UPSERT."""
    cols = [
        "corp_code",
        "bsns_year",
        "stock_code",
        "corp_name",
        "revenue",
        "op_income",
        "net_income",
        "assets",
        "liab",
        "equity",
        "op_cf",
    ]
    vals = [row.get(c) for c in cols]
    placeholders = ",".join(["?"] * len(cols))
    updates = ",".join([f"{c}=excluded.{c}" for c in cols if c not in {"corp_code", "bsns_year"}])
    sql = (
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(corp_code, bsns_year) DO UPDATE SET {updates};"
    )
    conn.execute(sql, vals)


def _load_universe_tickers(path: str, ticker_col: str = "ticker") -> pd.DataFrame:
    u = pd.read_csv(path)
    if ticker_col not in u.columns:
        raise ValueError(f"universe CSV에 '{ticker_col}' 컬럼이 없습니다. columns={list(u.columns)}")
    u[ticker_col] = u[ticker_col].astype(str).str.zfill(6)
    return u


def _load_stockcode_to_corpcode(dart_db: str) -> pd.DataFrame:
    conn = sqlite3.connect(dart_db)
    dim = pd.read_sql_query(
        "select stock_code, corp_code, corp_name, modify_date from dim_corp_listed",
        conn,
    )
    conn.close()
    dim["stock_code"] = dim["stock_code"].astype(str).str.zfill(6)
    return dim


def update_fs_annual_for_universe(
    dart_db: str,
    universe_file: str,
    ticker_col: str = "ticker",
    out_table: str = "fs_annual",
    start_year: int = 2015,
    end_year: int = 2024,
    report_code: str = "11011",
    prefer_fs_div: str = "CFS",
    only_market: Optional[str] = None,
    only_missing: bool = True,
    sleep: float = 0.15,
    retries: int = 2,
    commit_every: int = 20,
) -> None:
    """유니버스 기반으로 DART fnlttSinglAcntAll을 호출해 dart_db::fs_annual을 채운다.

    - only_market: 유니버스에 market 컬럼이 있으면 KOSPI/KOSDAQ 필터 가능
    - only_missing: (stock_code, bsns_year) 조합이 fs_annual에 이미 있으면 스킵
    """
    u = _load_universe_tickers(universe_file, ticker_col)
    if only_market and "market" in u.columns:
        u = u[u["market"].astype(str).str.upper() == only_market.upper()].copy()

    dim = _load_stockcode_to_corpcode(dart_db)
    m = u.merge(dim, left_on=ticker_col, right_on="stock_code", how="left")
    missing_map = m[m["corp_code"].isna()][ticker_col].tolist()
    if missing_map:
        print(f"[WARN] dim_corp_listed 매핑 누락 tickers={len(missing_map)} | {', '.join(missing_map[:30])}")
    m = m.dropna(subset=["corp_code"]).copy()

    conn = sqlite3.connect(dart_db)
    ensure_fs_annual_table(conn, out_table)

    # 이미 존재하는 (corp_code, bsns_year) 세트 로딩(옵션)
    existing: set = set()
    if only_missing:
        ex = pd.read_sql_query(f"select corp_code, bsns_year from {out_table}", conn)
        existing = set(zip(ex["corp_code"].astype(str), ex["bsns_year"].astype(int)))

    years = list(range(int(start_year), int(end_year) + 1))
    print(f"[INFO] universe_rows={len(u)} mapped={len(m)} | years={years[0]}..{years[-1]} | only_market={only_market} | only_missing={only_missing}")

    done = 0
    saved = 0
    skipped = 0
    fail = 0

    for _, r in m.iterrows():
        stock_code = str(r[ticker_col]).zfill(6)
        corp_code = str(r["corp_code"]).strip()
        corp_name = str(r.get("corp_name", "") or "")

        for y in years:
            key = (corp_code, int(y))
            if only_missing and key in existing:
                skipped += 1
                continue

            attempt = 0
            ok = False
            last_err = None
            while attempt <= retries and not ok:
                try:
                    df_raw, used_div = fetch_financial_statements_with_fallback(
                        corp_code=corp_code,
                        year=int(y),
                        report_code=report_code,
                        prefer_fs_div=prefer_fs_div,
                    )
                    metrics = extract_fs_annual_metrics(df_raw)
                    row = {
                        "corp_code": corp_code,
                        "bsns_year": int(y),
                        "stock_code": stock_code,
                        "corp_name": corp_name,
                        **metrics,
                    }
                    upsert_fs_annual(conn, row, out_table)
                    ok = True
                    saved += 1
                    existing.add(key)
                except Exception as e:
                    last_err = e
                    attempt += 1
                    if attempt <= retries:
                        time.sleep(max(0.2, sleep))

            if not ok:
                fail += 1
                print(f"[WARN] FAIL stock={stock_code} corp={corp_code} year={y} err={last_err}")

            done += 1
            if sleep:
                time.sleep(max(0.0, float(sleep)))

            if done % max(1, int(commit_every)) == 0:
                conn.commit()
                print(f"[INFO] progress done={done} saved={saved} skipped={skipped} fail={fail}")

    conn.commit()
    conn.close()
    print(f"[DONE] done={done} saved={saved} skipped={skipped} fail={fail} -> {dart_db}::{out_table}")


# -------------------------------------------------------------------
# 3. 간단한 테스트 진입점 (직접 실행 시)
# -------------------------------------------------------------------
def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DART 재무제표 수집/요약지표(fs_annual) 적재")
    sub = p.add_subparsers(dest="cmd")

    p1 = sub.add_parser("corp-list", help="DART corpCode.xml 다운로드 후 상장사 목록(parquet) 갱신")
    p1.add_argument("--force", action="store_true", help="캐시가 있어도 강제로 재다운로드")

    p2 = sub.add_parser("fetch-raw", help="특정 corp_code/연도/보고서의 원본 재무제표를 parquet로 저장")
    p2.add_argument("--corp-code", required=True)
    p2.add_argument("--year", type=int, required=True)
    p2.add_argument("--report-code", default="11011")
    p2.add_argument("--fs-div", default="CFS")

    p3 = sub.add_parser("update-fs-annual", help="유니버스 기반으로 dart_db::fs_annual(요약) 채우기")
    p3.add_argument("--dart-db", required=True, help="예: D:\\Quant\\data\\db\\dart_main.db")
    p3.add_argument("--universe-file", required=True, help="유니버스 CSV")
    p3.add_argument("--ticker-col", default="ticker")
    p3.add_argument("--out-table", default="fs_annual")
    p3.add_argument("--start-year", type=int, default=2015)
    p3.add_argument("--end-year", type=int, default=2024)
    p3.add_argument("--report-code", default="11011", help="사업보고서=11011")
    p3.add_argument("--prefer-fs-div", default="CFS", help="CFS 우선 후 OFS fallback")
    p3.add_argument("--only-market", default=None, help="유니버스에 market 컬럼이 있을 때 KOSPI/KOSDAQ 필터")
    p3.add_argument("--include-existing", action="store_true", help="기존 fs_annual이 있어도 덮어쓰며 재수집")
    p3.add_argument("--sleep", type=float, default=0.15)
    p3.add_argument("--retries", type=int, default=2)
    p3.add_argument("--commit-every", type=int, default=20)

    return p


def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_argparser()
    args = parser.parse_args(argv)

    # args 없이 실행하면 "간단 테스트" (기존 동작 유지)
    if not args.cmd:
        corps = get_corp_list()
        print(corps.head())

        listed = corps[corps["stock_code"].notna() & (corps["stock_code"] != "")].reset_index(drop=True)
        target_corp = listed[listed["stock_code"] == "005930"]
        if len(target_corp) == 0:
            target_corp = listed.iloc[[0]]
        first_corp_code = target_corp["corp_code"].iloc[0]
        first_corp_name = target_corp["corp_name"].iloc[0]
        print(f"테스트 대상 회사: {first_corp_name} (corp_code={first_corp_code})")
        fs = fetch_financial_statements(first_corp_code, 2023, "11011", "CFS")
        print(fs.head())
        return

    if args.cmd == "corp-list":
        df = get_corp_list(force_download=bool(args.force))
        print(f"[DONE] corp_list rows={len(df)} -> {CORP_LIST_PARQUET}")
        return

    if args.cmd == "fetch-raw":
        df = fetch_financial_statements(args.corp_code, int(args.year), args.report_code, args.fs_div)
        path = save_raw_financials(df, args.corp_code, int(args.year), args.report_code, args.fs_div)
        print(f"[DONE] saved -> {path}")
        return

    if args.cmd == "update-fs-annual":
        update_fs_annual_for_universe(
            dart_db=args.dart_db,
            universe_file=args.universe_file,
            ticker_col=args.ticker_col,
            out_table=args.out_table,
            start_year=int(args.start_year),
            end_year=int(args.end_year),
            report_code=args.report_code,
            prefer_fs_div=args.prefer_fs_div,
            only_market=args.only_market,
            only_missing=not bool(args.include_existing),
            sleep=float(args.sleep),
            retries=int(args.retries),
            commit_every=int(args.commit_every),
        )
        return

    raise SystemExit(f"unknown cmd: {args.cmd}")


if __name__ == "__main__":
    main()
