# dart_financials.py ver 2025-12-11_002

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

from typing import Dict, Any, Optional
import io
import os
import zipfile
import pathlib

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
# 3. 간단한 테스트 진입점 (직접 실행 시)
# -------------------------------------------------------------------
if __name__ == "__main__":
    # 예시: 상장사 목록 일부 확인
    corps = get_corp_list()
    print(corps.head())

    # 상장사(주식코드 있는 회사) 중 하나 선택
    listed = corps[corps["stock_code"].notna() & (corps["stock_code"] != "")]
    listed = listed.reset_index(drop=True)

    # 가능하면 삼성전자(005930)를 우선 찾고, 없으면 첫 번째 상장사 사용
    target_corp = listed[listed["stock_code"] == "005930"]
    if len(target_corp) == 0:
        target_corp = listed.iloc[[0]]

    first_corp_code = target_corp["corp_code"].iloc[0]
    first_corp_name = target_corp["corp_name"].iloc[0]
    print(f"테스트 대상 회사: {first_corp_name} (corp_code={first_corp_code})")

    fs = fetch_financial_statements(first_corp_code, 2023, "11011", "CFS")
    print(fs.head())
