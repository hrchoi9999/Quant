# dart_bulk_fetch.py ver 2025-12-11_001

"""
코스피 상위 400개 종목의 2015~2024년 재무제표를
DART API로 일괄 수집하는 스크립트.

전략:
- DART corp_list + FinanceDataReader KOSPI 리스트를 이용해
  KOSPI 상장사 유니버스를 구성한다.
- 시가총액 상위 400개만 대상.
- 연도: 2015 ~ 2024
- 보고서: 사업(11011), 반기(11012), 1분기(11013), 3분기(11014)
- fs_div: 먼저 CFS(연결) 시도, 데이터 없으면 OFS(별도) 한 번 더 시도.
- 파일 캐싱:
  이미 data/raw/dart/fs_{corp_code}_{year}_{reprt_code}_{fs_div}.parquet
  파일이 존재하면 API를 다시 호출하지 않는다.
"""

from __future__ import annotations

import time
from typing import List, Tuple

import pandas as pd
import FinanceDataReader as fdr

from .dart_financials import (
    get_corp_list,
    fetch_financial_statements,
    save_raw_financials,
    RAW_DART_DIR,
)


# -----------------------------
# 1. 유니버스 구성
# -----------------------------
def get_kospi_universe(top_n: int = 400) -> pd.DataFrame:
    """
    DART corp_list + FinanceDataReader KOSPI 리스트를 이용해
    코스피 상장사 중 시가총액 상위 N개를 반환한다.

    반환 컬럼 예:
        corp_code, corp_name, stock_code, Name, Market, Marcap, ...
    """
    # 1) DART corp_list (공시 의무자 전체)
    corps = get_corp_list()

    # 2) stock_code 있는 것만 상장사로 필터링
    corps_listed = corps[
        corps["stock_code"].notna() & (corps["stock_code"] != "")
    ].copy()

    # 3) FinanceDataReader KOSPI 상장사 정보
    kospi_df = fdr.StockListing("KOSPI")  # Code, Name, Market, Marcap, ...

    # 4) 종목코드 기준으로 merge (6자리 코드)
    kospi_df["Code"] = kospi_df["Code"].astype(str).str.zfill(6)
    corps_listed["stock_code"] = corps_listed["stock_code"].astype(str).str.zfill(6)

    merged = pd.merge(
        kospi_df,
        corps_listed,
        left_on="Code",
        right_on="stock_code",
        how="inner",
        suffixes=("_fdr", "_dart"),
    )

    # 5) 시가총액 기준 정렬 후 상위 N개 선택
    if "Marcap" in merged.columns:
        merged = merged.sort_values("Marcap", ascending=False)
    merged = merged.reset_index(drop=True)

    universe = merged.head(top_n).copy()

    # 우리가 주로 쓸 컬럼만 보기 좋게 정리
    universe = universe[["Code", "Name", "Market", "Marcap", "corp_code", "corp_name"]]
    universe = universe.rename(columns={"Code": "stock_code"})
    return universe


# -----------------------------
# 2. 단일 기업 × 연도 × 보고서 조합 수집
# -----------------------------
def fetch_one_corp_one_year(
    corp_code: str,
    year: int,
    reprt_code: str,
    prefer_fs_div: str = "CFS",
    fallback_fs_div: str = "OFS",
    sleep_sec: float = 0.2,
) -> Tuple[bool, str]:
    """
    단일 회사(corp_code), 단일 연도, 단일 보고서(reprt_code)에 대해
    재무제표를 수집한다.

    우선 fs_div=prefer_fs_div(CFS)를 시도하고,
    데이터가 없으면 fs_div=fallback_fs_div(OFS)를 한 번 더 시도한다.

    이미 해당 조합의 파일이 존재하면 API 호출 없이 스킵한다.

    return:
        (성공여부, 사용된 fs_div 또는 상태 메시지)
    """
    # 1) CFS 파일이 이미 있는지 체크
    path_cfs = RAW_DART_DIR / f"fs_{corp_code}_{year}_{reprt_code}_{prefer_fs_div}.parquet"
    path_ofs = RAW_DART_DIR / f"fs_{corp_code}_{year}_{reprt_code}_{fallback_fs_div}.parquet"

    # 우선 CFS 파일이 존재하면 스킵
    if path_cfs.exists():
        return True, "CFS_skipped_cached"

    # CFS가 없는데 OFS는 있는 경우(예전에 OFS만 저장한 케이스)
    if path_ofs.exists():
        return True, "OFS_skipped_cached"

    # 2) CFS 시도
    try:
        df_cfs = fetch_financial_statements(
            corp_code=corp_code,
            year=year,
            report_code=reprt_code,
            fs_div=prefer_fs_div,
        )
    except Exception as e:
        # API 에러면 메시지 남기고 실패 처리
        return False, f"CFS_error: {e}"

    if not df_cfs.empty:
        save_raw_financials(df_cfs, corp_code, year, reprt_code, prefer_fs_div)
        time.sleep(sleep_sec)
        return True, "CFS_fetched"

    # 3) CFS 비어 있으면 OFS 시도
    try:
        df_ofs = fetch_financial_statements(
            corp_code=corp_code,
            year=year,
            report_code=reprt_code,
            fs_div=fallback_fs_div,
        )
    except Exception as e:
        return False, f"OFS_error: {e}"

    if not df_ofs.empty:
        save_raw_financials(df_ofs, corp_code, year, reprt_code, fallback_fs_div)
        time.sleep(sleep_sec)
        return True, "OFS_fetched"

    # 둘 다 비어 있음
    time.sleep(sleep_sec)
    return False, "no_data"


# -----------------------------
# 3. 메인 루프: 코스피 상위 400개 × 2015~2024 × 4보고서
# -----------------------------
def run_kospi_bulk_fetch(
    top_n: int = 400,
    start_year: int = 2015,
    end_year: int = 2024,
    reprt_codes: List[str] | None = None,
) -> None:
    """
    코스피 상위 top_n 기업에 대해
    [start_year, end_year] 구간과 reprt_codes(보고서 목록)에 대한
    재무제표를 일괄 수집한다.
    """
    if reprt_codes is None:
        reprt_codes = ["11011", "11012", "11013", "11014"]  # 사업, 반기, 1Q, 3Q

    universe = get_kospi_universe(top_n=top_n)
    print(f"[INFO] KOSPI 유니버스 구성 완료: {len(universe)}개 종목 대상")
    print(universe.head())

    corp_list = universe[["corp_code", "corp_name", "stock_code"]].to_dict(orient="records")

    total_tasks = len(corp_list) * (end_year - start_year + 1) * len(reprt_codes)
    print(f"[INFO] 총 작업 개수(회사×연도×보고서): {total_tasks}")

    done = 0
    for corp in corp_list:
        corp_code = corp["corp_code"]
        corp_name = corp["corp_name"]
        stock_code = corp["stock_code"]

        for year in range(start_year, end_year + 1):
            for reprt_code in reprt_codes:
                done += 1
                progress = f"{done}/{total_tasks}"
                try:
                    ok, status = fetch_one_corp_one_year(
                        corp_code=corp_code,
                        year=year,
                        reprt_code=reprt_code,
                        prefer_fs_div="CFS",
                        fallback_fs_div="OFS",
                        sleep_sec=0.2,
                    )
                    print(
                        f"[{progress}] {stock_code} {corp_name} "
                        f"{year} {reprt_code} => {status}"
                    )
                except Exception as e:
                    print(
                        f"[{progress}] {stock_code} {corp_name} "
                        f"{year} {reprt_code} => EXCEPTION: {e}"
                    )
                    # 심각한 에러 시, 여기는 그대로 두고 나중에 따로 확인


# -----------------------------
# 4. 엔트리 포인트
# -----------------------------
if __name__ == "__main__":
    # 오늘은 코스피만 먼저 수행
    run_kospi_bulk_fetch(
        top_n=400,
        start_year=2015,
        end_year=2024,
        reprt_codes=["11011", "11012", "11013", "11014"],
    )
