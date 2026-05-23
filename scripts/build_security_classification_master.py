from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
OUT_DB = ROOT / r"data\db\security_classification.db"
SCHEMA = ROOT / r"src\quant_service\schema_security_classification.sql"
STOCK_UNIVERSE = ROOT / r"data\universe\universe_mix_top400_latest.csv"
ETF_UNIVERSE = ROOT / r"data\universe\universe_etf_master_latest.csv"
CACHE_DIR = ROOT / r"data\classification"
REPORT_DIR = ROOT / r"reports\c_series"


THEME_NAME_KR = {
    "semiconductor_tech": "반도체/전자부품",
    "electronics_it": "IT/전자",
    "software_platform": "소프트웨어/플랫폼",
    "biotech_healthcare": "바이오/헬스케어",
    "finance_holdings": "금융/지주",
    "bank_insurance": "은행/보험/증권",
    "construction_materials": "건설/소재",
    "energy_utility_infra": "에너지/전력/인프라",
    "battery_chemical": "2차전지/화학",
    "auto_mobility": "자동차/모빌리티",
    "shipbuilding_defense": "조선/방산/항공",
    "steel_machinery": "철강/기계",
    "consumer_food": "음식료/소비재",
    "consumer_retail": "유통/리테일",
    "media_game_entertainment": "미디어/게임/엔터",
    "telecom": "통신",
    "logistics_transport": "운송/물류",
    "holding_company": "지주회사",
    "real_estate_reit": "부동산/리츠",
    "equity_kr_broad": "국내 대표지수",
    "equity_kr_growth": "국내 성장/섹터",
    "equity_us": "미국 주식",
    "equity_china": "중국/홍콩 주식",
    "equity_europe": "유럽 주식",
    "equity_emerging": "신흥국/지역 주식",
    "equity_global": "글로벌 주식",
    "style_factor_dividend": "스타일/배당/밸류업",
    "group_holdings": "그룹주/지주 테마",
    "multi_asset_allocation": "멀티에셋/TDF",
    "bond_cash": "채권/현금성",
    "commodity_fx": "원자재/환율",
    "inverse_leverage": "인버스/레버리지",
    "etf_other": "기타 ETF",
    "other": "기타",
}


def _normalize_ticker(value: Any) -> str:
    return str(value).strip().replace(".0", "").zfill(6)


def _contains(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def classify_stock_theme(name: str, sector: str, industry: str) -> str:
    text = f"{name} {sector} {industry}"
    if _contains(text, ["반도체", "웨이퍼", "디스플레이", "전자부품", "FPD", "OLED", "LED", "PCB"]):
        return "semiconductor_tech"
    if _contains(text, ["소프트웨어", "플랫폼", "인터넷", "데이터", "클라우드", "보안", "IT서비스"]):
        return "software_platform"
    if _contains(text, ["전자", "통신 및 방송 장비", "컴퓨터", "전기장비", "정밀기기", "광학"]):
        return "electronics_it"
    if _contains(text, ["의약", "제약", "바이오", "의료", "헬스케어", "진단", "병원", "신약", "치료제", "항암", "CAR-T", "유전체", "저분자", "siRNA", "대사성질환", "알레르기", "소화기질환"]):
        return "biotech_healthcare"
    if _contains(text, ["은행", "보험", "증권", "금융", "카드", "캐피탈"]):
        return "bank_insurance"
    if _contains(text, ["지주", "홀딩스", "기타 금융업"]):
        return "holding_company"
    if _contains(text, ["건설", "시멘트", "콘크리트", "건축", "토목", "부동산", "리츠", "나무제품", "PB", "MDF", "마루", "창호", "도어"]):
        return "construction_materials"
    if _contains(text, ["전기", "가스", "전력", "에너지", "발전", "풍력", "태양광", "원자력", "인프라"]):
        return "energy_utility_infra"
    if _contains(text, ["화학", "전지", "배터리", "2차전지", "석유", "정유", "소재", "플라스틱"]):
        return "battery_chemical"
    if _contains(text, ["자동차", "모빌리티", "차량", "타이어", "부품"]):
        return "auto_mobility"
    if _contains(text, ["조선", "선박", "방산", "항공", "우주", "무기", "국방"]):
        return "shipbuilding_defense"
    if _contains(text, ["철강", "금속", "기계", "장비", "공작", "산업용"]):
        return "steel_machinery"
    if _contains(text, ["음식", "식품", "음료", "화장품", "생활용품", "섬유", "의복", "담배", "홍삼"]):
        return "consumer_food"
    if _contains(text, ["소매", "유통", "도매", "백화점", "편의점", "홈쇼핑", "전자상거래", "숙박", "리조트", "호텔", "골프장", "스키장"]):
        return "consumer_retail"
    if _contains(text, ["게임", "영화", "방송", "음악", "엔터", "광고", "콘텐츠", "미디어", "오디오물", "음반", "연예", "오락", "카지노"]):
        return "media_game_entertainment"
    if _contains(text, ["통신", "무선", "유선"]):
        return "telecom"
    if _contains(text, ["운송", "물류", "항공운송", "해운", "창고"]):
        return "logistics_transport"
    return "other"


def classify_etf_theme(name: str, asset_class: str, group_key: str, is_inverse: int, is_leveraged: int) -> str:
    text = f"{name} {asset_class} {group_key}"
    if int(is_inverse or 0) or int(is_leveraged or 0) or _contains(text, ["인버스", "레버리지", "2X", "선물인버스"]):
        return "inverse_leverage"
    if _contains(text, ["TDF", "TRF", "주식혼합", "멀티에셋", "하이인컴", "자산배분", "2060", "2050", "2040", "2030"]):
        return "multi_asset_allocation"
    if _contains(text, ["통안채", "국공채", "국고채", "국채", "물가채", "특수채", "전단채", "채권", "회사채", "단기", "CD", "머니마켓", "KOFR", "금리"]):
        return "bond_cash"
    if _contains(text, ["원유", "금", "은", "구리", "농산물", "콩", "팔라듐", "탄소배출권", "달러", "환율", "FX"]):
        return "commodity_fx"
    if _contains(text, ["반도체", "HBM", "AI반도체", "파운드리", "SK하이닉스"]):
        return "semiconductor_tech"
    if _contains(text, ["중공업", "철강", "기계", "기계장비", "설비투자", "CAPEX", "로봇"]):
        return "steel_machinery"
    if _contains(text, ["미국", "S&P", "나스닥", "NASDAQ", "다우", "테슬라", "엔비디아", "TSMC", "마이크로소프트", "구글", "애플"]):
        return "equity_us"
    if _contains(text, ["중국", "차이나", "CSI", "HSCEI", "항셍", "심천", "과창판", "STAR50", "태양광CSI"]):
        return "equity_china"
    if _contains(text, ["유럽", "유로스탁스", "독일", "DAX"]):
        return "equity_europe"
    if _contains(text, ["일본", "인도", "베트남", "필리핀", "러시아", "멕시코", "라틴", "아시아", "신흥국", "MSCI EM"]):
        return "equity_emerging"
    if _contains(text, ["글로벌", "선진국", "월드"]):
        return "equity_global"
    if _contains(text, ["삼성그룹", "LG그룹", "현대차그룹", "5대그룹", "그룹주", "그룹섹터", "포스코그룹"]):
        return "group_holdings"
    if _contains(text, ["코리아밸류업", "밸류업", "주주가치", "주주환원", "배당", "고배당", "배당귀족", "가치주", "밸류", "퀄리티", "모멘텀", "로우볼", "저변동", "최소변동성", "멀티팩터", "우선주", "블루칩", "ESG", "사회책임", "수출주", "내수주", "우량주", "우량가치", "우량업종", "셀렉트밸류"]):
        return "style_factor_dividend"
    if _contains(text, ["리츠", "부동산"]):
        return "real_estate_reit"
    if _contains(text, ["반도체", "AI", "IT", "테크", "인터넷", "소프트웨어", "파운드리", "SK하이닉스", "전력설비투자"]):
        return "semiconductor_tech"
    if _contains(text, ["BBIG", "메타버스", "플랫폼", "e커머스", "뉴딜디지털", "디지털", "혁신기술", "R&D", "이노베이션", "5G", "네트워크", "미래전략기술", "포스트IPO"]):
        return "software_platform"
    if _contains(text, ["2차전지", "배터리", "전기차", "화학", "소재", "친환경차", "전기&수소차"]):
        return "battery_chemical"
    if _contains(text, ["바이오", "헬스케어", "의료", "일라이릴리"]):
        return "biotech_healthcare"
    if _contains(text, ["은행", "금융", "보험", "증권"]):
        return "bank_insurance"
    if _contains(text, ["신재생", "친환경에너지", "클린에너지", "수소", "태양광", "ESS", "기후변화", "탄소효율", "원자력", "전력설비", "전력", "에너지"]):
        return "energy_utility_infra"
    if _contains(text, ["방산", "우주", "항공", "UAM", "조선", "해운"]):
        return "shipbuilding_defense"
    if _contains(text, ["중공업", "철강", "기계", "기계장비", "설비투자", "CAPEX", "로봇"]):
        return "steel_machinery"
    if _contains(text, ["건설", "건축", "인프라"]):
        return "construction_materials"
    if _contains(text, ["자동차", "모빌리티", "자율주행"]):
        return "auto_mobility"
    if _contains(text, ["K콘텐츠", "콘텐츠", "미디어", "웹툰", "드라마", "KPOP", "K-POP", "엔터", "컬처", "게임"]):
        return "media_game_entertainment"
    if _contains(text, ["화장품", "뷰티", "여행", "레저", "골프", "경기소비재", "필수소비재", "경기방어", "푸드", "농업", "소비"]):
        return "consumer_retail"
    if _contains(text, ["운송", "물류"]):
        return "logistics_transport"
    if _contains(text, ["지주회사", "지주"]):
        return "holding_company"
    if _contains(text, ["200", "코스피", "KOSPI", "KRX100", "KRX300", "KTOP30", "TOP10", "TOP5", "Top10", "Top5", "KEDI혁신기업", "베스트일레븐"]):
        return "equity_kr_broad"
    if _contains(text, ["액티브", "성장", "중소형", "주도업종", "대장장이"]):
        return "equity_kr_growth"
    if str(asset_class or "").lower() in {"bond", "cash"}:
        return "bond_cash"
    if str(asset_class or "").lower() == "commodity":
        return "commodity_fx"
    if str(group_key or "").startswith("equity_kr"):
        return str(group_key)
    return "etf_other"


def _load_krx_desc(asof: str, refresh: bool) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"krx_desc_listing_{asof.replace('-', '')}.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, dtype={"Code": str})
    import FinanceDataReader as fdr

    df = fdr.StockListing("KRX-DESC")
    df["Code"] = df["Code"].map(_normalize_ticker)
    df.to_csv(cache, index=False, encoding="utf-8-sig")
    return df


def _load_etf_meta() -> pd.DataFrame:
    with sqlite3.connect(str(PRICE_DB)) as con:
        df = pd.read_sql_query(
            """
            SELECT ticker, asset_class, group_key, is_inverse, is_leveraged, liquidity_20d_value
            FROM etf_meta
            """,
            con,
            dtype={"ticker": str},
        )
    if df.empty:
        return df
    df["ticker"] = df["ticker"].map(_normalize_ticker)
    return df


def _base_stock_name(name: Any) -> str:
    text = str(name or "").strip()
    for suffix in ["2우B", "3우B", "1우", "우B", "우"]:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(OUT_DB))
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    return con


def main() -> None:
    ap = argparse.ArgumentParser(description="Build stock/ETF industry and theme classification master for C-series.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument("--refresh-krx-desc", action="store_true")
    args = ap.parse_args()
    asof = args.asof
    started = datetime.now().isoformat(timespec="seconds")

    stock = pd.read_csv(STOCK_UNIVERSE, dtype={"ticker": str})
    stock["ticker"] = stock["ticker"].map(_normalize_ticker)
    stock["asset_type"] = "STOCK"

    etf = pd.read_csv(ETF_UNIVERSE, dtype={"ticker": str})
    etf["ticker"] = etf["ticker"].map(_normalize_ticker)
    etf = etf.loc[etf.get("is_active", 1).astype(int) == 1].copy()
    etf["asset_type"] = "ETF"
    etf["market"] = "ETF"
    stock_etf_overlap = sorted(set(stock["ticker"]) & set(etf["ticker"]))
    if stock_etf_overlap:
        stock = stock.loc[~stock["ticker"].isin(stock_etf_overlap)].copy()

    krx_desc = _load_krx_desc(asof, args.refresh_krx_desc)
    krx_desc["Code"] = krx_desc["Code"].map(_normalize_ticker)
    name_sector = (
        krx_desc.dropna(subset=["Sector"])
        .drop_duplicates("Name")
        .set_index("Name")[["Sector", "Industry"]]
        .to_dict(orient="index")
    )
    stock = stock.merge(
        krx_desc[["Code", "Sector", "Industry", "ListingDate", "Region"]].rename(columns={"Code": "ticker"}),
        on="ticker",
        how="left",
    )
    missing = stock["Sector"].isna() | (stock["Sector"].astype(str).str.strip() == "")
    for idx, row in stock.loc[missing].iterrows():
        base_name = _base_stock_name(row.get("name"))
        matched = name_sector.get(base_name)
        if matched:
            stock.at[idx, "Sector"] = matched.get("Sector")
            stock.at[idx, "Industry"] = matched.get("Industry")
    stock["sector_raw"] = stock["Sector"]
    stock["industry_raw"] = stock["Industry"]
    stock["asset_class"] = None
    stock["group_key"] = None
    stock["sector_bucket"] = stock.apply(lambda r: classify_stock_theme(r.get("name"), r.get("Sector"), r.get("Industry")), axis=1)
    stock["theme_bucket"] = stock["sector_bucket"]
    stock["theme_name_kr"] = stock["theme_bucket"].map(THEME_NAME_KR).fillna("기타")
    stock["source"] = "krx_desc_listing"
    stock["source_quality"] = stock["Sector"].map(lambda x: "official_sector" if pd.notna(x) and str(x).strip() else "missing_sector")
    stock["confidence_score"] = stock["source_quality"].map({"official_sector": 0.85, "missing_sector": 0.25}).fillna(0.25)
    stock["is_active"] = 1

    etf_meta = _load_etf_meta()
    etf = etf.merge(etf_meta, on="ticker", how="left")
    etf["sector_raw"] = None
    etf["industry_raw"] = None
    etf["sector_bucket"] = etf.apply(
        lambda r: classify_etf_theme(r.get("name"), r.get("asset_class"), r.get("group_key"), r.get("is_inverse", 0), r.get("is_leveraged", 0)),
        axis=1,
    )
    etf["theme_bucket"] = etf["sector_bucket"]
    etf["theme_name_kr"] = etf["theme_bucket"].map(THEME_NAME_KR).fillna("기타 ETF")
    etf["source"] = "etf_meta_name_rule"
    etf["source_quality"] = etf["group_key"].map(lambda x: "meta_plus_name_rule" if pd.notna(x) and str(x).strip() else "name_rule_only")
    etf["confidence_score"] = etf["source_quality"].map({"meta_plus_name_rule": 0.75, "name_rule_only": 0.55}).fillna(0.55)
    etf["is_active"] = etf.get("is_active", 1).astype(int)

    cols = [
        "ticker", "name", "asset_type", "market", "sector_raw", "industry_raw", "asset_class", "group_key",
        "sector_bucket", "theme_bucket", "theme_name_kr", "source", "source_quality", "confidence_score", "is_active",
    ]
    out = pd.concat([stock[cols], etf[cols]], ignore_index=True).drop_duplicates("ticker", keep="first")
    out.insert(0, "asof_date", asof)
    out["updated_at"] = datetime.now().isoformat(timespec="seconds")

    missing_sector = int(((out["asset_type"] == "STOCK") & (out["sector_raw"].isna() | (out["sector_raw"].astype(str).str.strip() == ""))).sum())
    source_summary = {
        "stock_source": "FinanceDataReader KRX-DESC corpList Sector/Industry",
        "etf_source": "price.db etf_meta + name rule",
        "stock_rows": int((out["asset_type"] == "STOCK").sum()),
        "etf_rows": int((out["asset_type"] == "ETF").sum()),
        "missing_stock_sector": missing_sector,
        "stock_etf_overlap_prefer_etf": stock_etf_overlap,
        "theme_counts": out["theme_bucket"].value_counts().to_dict(),
    }
    run_id = f"SECURITY_CLASSIFICATION:{asof}"
    con = _connect()
    try:
        con.execute("DELETE FROM security_classification_master WHERE asof_date=?", (asof,))
        out.to_sql("security_classification_master", con, if_exists="append", index=False)
        con.execute("DELETE FROM security_classification_runs WHERE run_id=?", (run_id,))
        con.execute(
            """
            INSERT INTO security_classification_runs (
              run_id, asof_date, status, stock_universe_count, etf_universe_count, classified_count,
              missing_sector_count, source_summary_json, started_at, finished_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                asof,
                "success",
                int(len(stock)),
                int(len(etf)),
                int(len(out)),
                missing_sector,
                json.dumps(source_summary, ensure_ascii=False),
                started,
                datetime.now().isoformat(timespec="seconds"),
                "Prerequisite classification master for C-series relationship analysis.",
            ),
        )
        con.commit()
    finally:
        con.close()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    out.to_csv(REPORT_DIR / f"security_classification_master_{token}.csv", index=False, encoding="utf-8-sig")
    (REPORT_DIR / f"security_classification_summary_{token}.json").write_text(json.dumps(source_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"db": str(OUT_DB), "asof": asof, **source_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
