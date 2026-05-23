from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
UNIVERSE_DIR = ROOT / r"data\universe"
REPORT_DIR = ROOT / r"reports\e_series_etf"

E_SERIES_MODEL_CODE = "E-ETF-V01"

STANDARD_ROLES = [
    "CORE_BETA",
    "SECTOR_THEME",
    "STYLE_FACTOR",
    "DEFENSIVE",
    "INCOME",
    "CASH_LIKE",
]

ROLE_NORMALIZATION = {
    "CORE_BETA": "CORE_BETA",
    "SECTOR_THEME": "SECTOR_THEME",
    "STYLE_FACTOR": "STYLE_FACTOR",
    "DEFENSIVE": "DEFENSIVE",
    "DEFENSIVE_HEDGE": "DEFENSIVE",
    "INCOME": "INCOME",
    "CASH_LIKE": "CASH_LIKE",
    "TACTICAL_HEDGE": "DEFENSIVE",
    "TACTICAL_LEVERAGE": "SECTOR_THEME",
}


def _norm_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).lower()


def _has(text: str, *keywords: str) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _infer_e_series_role(row: pd.Series) -> str:
    raw_role = str(row.get("raw_role_key") or "UNKNOWN")
    asset_class = str(row.get("asset_class") or "").lower()
    group_key = str(row.get("group_key") or "").lower()
    name = str(row.get("name") or "").lower()

    if "money" in group_key or "cash" in group_key or "cd" in group_key or "mmf" in group_key:
        return "CASH_LIKE"
    if "bond_short" in group_key or "short" in group_key and "bond" in group_key:
        return "CASH_LIKE"
    if asset_class == "bond" or "bond" in group_key:
        return "INCOME"
    if "dividend" in group_key or "covered_call" in group_key or "income" in group_key:
        return "INCOME"
    if "배당" in name or "커버드콜" in name or "채권" in name:
        return "INCOME"
    if asset_class in {"fx", "commodity", "hedge"}:
        return "DEFENSIVE"
    return ROLE_NORMALIZATION.get(raw_role, "STYLE_FACTOR")


def _infer_region_bucket(row: pd.Series) -> str:
    name = _norm_text(row.get("name"))
    group_key = _norm_text(row.get("group_key"))

    if _has(name, "미국", "s&p", "nasdaq", "나스닥", "다우", "필라델피아", "테슬라", "미장"):
        return "US"
    if _has(name, "차이나", "중국", "csi", "항셍", "홍콩"):
        return "CHINA"
    if _has(name, "일본", "nikkei", "topix", "엔화"):
        return "JAPAN"
    if _has(name, "인도", "india"):
        return "INDIA"
    if _has(name, "베트남", "vietnam"):
        return "VIETNAM"
    if _has(name, "유럽", "유로스탁스", "europe", "eurostoxx"):
        return "EUROPE"
    if _has(name, "글로벌", "global", "선진국", "신흥국", "msci world"):
        return "GLOBAL"
    if "equity_kr" in group_key or _has(name, "코리아", "한국", "코스피", "코스닥", "krx", "kospi"):
        return "KR"
    return "KR"


def _infer_asset_bucket(row: pd.Series) -> str:
    name = _norm_text(row.get("name"))
    asset_class = _norm_text(row.get("asset_class"))
    group_key = _norm_text(row.get("group_key"))

    if _has(name, "인버스") or bool(row.get("is_inverse")):
        return "HEDGE_INVERSE"
    if _has(name, "cd금리", "cd1년", "kofr", "머니마켓", "money market", "단기통안채", "단기자금"):
        return "CASH_RATE"
    if _has(name, "trf", "tif", "tdf", "멀티에셋", "자산배분", "주식혼합", "채권혼합"):
        return "MULTI_ASSET"
    if asset_class == "bond" or "bond" in group_key or _has(name, "채권", "국채", "국고채", "국공채", "통안채", "회사채", "특수채", "물가채", "하이일드"):
        if _has(name, "30년", "장기", "10년", "울트라", "long"):
            return "BOND_LONG"
        if _has(name, "단기", "3년", "cd금리", "cd1년", "kofr", "머니마켓", "통안채", "short"):
            return "BOND_SHORT"
        return "BOND_CORE"
    if asset_class == "fx" or _has(name, "미국달러", "달러", "usd", "sofr"):
        return "FX_USD"
    if asset_class == "commodity" or _has(name, "금현물", "골드", "금선물", "금은"):
        return "COMMODITY_GOLD"
    if _has(name, "원유", "농산물", "구리", "은선물"):
        return "COMMODITY_OTHER"
    if _has(name, "리츠", "부동산", "reit"):
        return "REIT_INFRA"
    if _has(name, "배당", "고배당", "커버드콜", "우선증권", "캐시카우"):
        region = _infer_region_bucket(row)
        return f"EQUITY_{region}"
    if asset_class == "equity" or str(row.get("e_series_role") or "") in {"CORE_BETA", "SECTOR_THEME", "STYLE_FACTOR"}:
        region = _infer_region_bucket(row)
        return f"EQUITY_{region}"
    return "OTHER"


def _infer_theme_bucket(row: pd.Series) -> str:
    name = _norm_text(row.get("name"))
    if _has(name, "반도체", "필라델피아반도체", "semiconductor"):
        return "SEMICONDUCTOR"
    if _has(name, "2차전지", "배터리", "전기차", "battery"):
        return "SECONDARY_BATTERY_EV"
    if _has(name, "ai", "로봇", "인공지능", "소프트웨어", "클라우드", "테크", "it"):
        return "AI_TECH"
    if _has(name, "자동차", "현대차", "자율주행", "모빌리티"):
        return "AUTO_MOBILITY"
    if _has(name, "바이오", "헬스", "의료", "제약"):
        return "BIO_HEALTHCARE"
    if _has(name, "은행", "증권", "보험", "금융"):
        return "FINANCIAL"
    if _has(name, "방산", "우주", "항공"):
        return "DEFENSE_AEROSPACE"
    if _has(name, "에너지", "원자력", "전력", "인프라", "수소"):
        return "ENERGY_INFRA"
    if _has(name, "엔터", "게임", "미디어", "여행", "레저", "소비", "화장품"):
        return "CONSUMER_MEDIA"
    if _has(name, "리츠", "부동산"):
        return "REIT_REAL_ESTATE"
    if _has(name, "농산물", "원유", "금", "골드"):
        return "COMMODITY"
    return "NONE"


def _infer_strategy_bucket(row: pd.Series) -> str:
    name = _norm_text(row.get("name"))
    role = str(row.get("e_series_role") or "")
    group_key = _norm_text(row.get("group_key"))

    if _has(name, "인버스") or bool(row.get("is_inverse")):
        return "INVERSE_HEDGE"
    if _has(name, "레버리지", "2x", "3x") or bool(row.get("is_leveraged")):
        return "LEVERAGED_TACTICAL"
    if _has(name, "커버드콜", "covered call"):
        return "COVERED_CALL"
    if _has(name, "배당", "고배당", "dividend"):
        return "DIVIDEND_INCOME"
    if _has(name, "저변동", "로우볼", "low vol"):
        return "LOW_VOL"
    if _has(name, "퀄리티", "quality"):
        return "QUALITY"
    if _has(name, "밸류", "value", "가치"):
        return "VALUE"
    if _has(name, "성장", "growth"):
        return "GROWTH"
    if _has(name, "cd금리", "kofr", "머니마켓", "단기통안채"):
        return "CASH_RATE"
    if _has(name, "채권", "국채", "통안채", "회사채") or "bond" in group_key:
        return "BOND_DURATION"
    if _has(name, "달러", "usd", "sofr"):
        return "FX_USD"
    if _has(name, "골드", "금현물", "금선물", "원유", "농산물"):
        return "COMMODITY"
    if role == "CORE_BETA":
        return "BROAD_BETA"
    if role == "SECTOR_THEME":
        return "SECTOR_THEME"
    if role == "STYLE_FACTOR":
        return "STYLE_FACTOR"
    if role == "INCOME":
        return "INCOME"
    if role in {"DEFENSIVE", "CASH_LIKE"}:
        return "DEFENSIVE"
    return "OTHER"


def _product_structure(row: pd.Series) -> str:
    name = str(row.get("name") or "")
    flags: list[str] = []
    if "액티브" in name:
        flags.append("ACTIVE")
    if "합성" in name:
        flags.append("SYNTHETIC")
    if "(H)" in name or "환헤지" in name:
        flags.append("HEDGED")
    if "커버드콜" in name:
        flags.append("COVERED_CALL")
    if "TDF" in name.upper():
        flags.append("TDF")
    if bool(row.get("is_leveraged")):
        flags.append("LEVERAGED")
    if bool(row.get("is_inverse")):
        flags.append("INVERSE")
    return "|".join(flags) if flags else "PLAIN"


def _add_detail_taxonomy(meta: pd.DataFrame) -> pd.DataFrame:
    out = meta.copy()
    out["e_region_bucket"] = out.apply(_infer_region_bucket, axis=1)
    out["e_asset_bucket"] = out.apply(_infer_asset_bucket, axis=1)
    out["e_strategy_bucket"] = out.apply(_infer_strategy_bucket, axis=1)
    out["e_theme_bucket"] = out.apply(_infer_theme_bucket, axis=1)
    out["e_product_structure"] = out.apply(_product_structure, axis=1)
    out["e_is_active_strategy"] = out["e_product_structure"].str.contains("ACTIVE", regex=False)
    out["e_is_synthetic"] = out["e_product_structure"].str.contains("SYNTHETIC", regex=False)
    out["e_is_currency_hedged"] = out["e_product_structure"].str.contains("HEDGED", regex=False)
    out["e_is_covered_call"] = out["e_product_structure"].str.contains("COVERED_CALL", regex=False)
    out["e_is_tdf"] = out["e_product_structure"].str.contains("TDF", regex=False)
    base_conf = pd.to_numeric(out.get("role_confidence"), errors="coerce").fillna(0.0)
    unknown_penalty = np.where(out["e_asset_bucket"].eq("OTHER") | out["e_strategy_bucket"].eq("OTHER"), 0.20, 0.0)
    theme_bonus = np.where(out["e_theme_bucket"].ne("NONE"), 0.05, 0.0)
    out["e_taxonomy_confidence"] = (base_conf + theme_bonus - unknown_penalty).clip(0, 1)
    out["e_taxonomy_review_flag"] = np.select(
        [
            out["raw_role_key"].eq("UNCLASSIFIED"),
            out["e_asset_bucket"].eq("OTHER") | out["e_strategy_bucket"].eq("OTHER"),
            out["e_taxonomy_confidence"].lt(0.50),
        ],
        ["UNCLASSIFIED_ROLE", "UNKNOWN_DETAIL_BUCKET", "LOW_CONFIDENCE"],
        default="OK",
    )
    return out


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _json_value(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if pd.isna(value):
            return None
        return round(float(value), 6)
    if pd.isna(value):
        return None
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict("records")]


def _meta_path(asof: str) -> Path:
    dated = UNIVERSE_DIR / f"etf_meta_{_token(asof)}.csv"
    if dated.exists():
        return dated
    return UNIVERSE_DIR / "etf_meta_latest.csv"


def build_taxonomy(asof: str) -> dict[str, Any]:
    path = _meta_path(asof)
    if not path.exists():
        raise SystemExit(f"missing ETF meta file: {path}")
    meta = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    meta["ticker"] = meta["ticker"].astype(str).str.zfill(6)
    meta["raw_role_key"] = meta.get("role_key", "UNKNOWN").fillna("UNKNOWN").astype(str)
    meta["e_series_role"] = meta.apply(_infer_e_series_role, axis=1)
    meta["role_standardized"] = meta["raw_role_key"].eq(meta["e_series_role"])
    meta["role_confidence"] = pd.to_numeric(meta.get("role_confidence"), errors="coerce")
    meta["is_active"] = meta.get("is_active", 1)
    meta["is_active"] = meta["is_active"].astype(str).str.lower().isin(["1", "true", "yes"])
    meta["is_inverse"] = meta.get("is_inverse", False).astype(str).str.lower().isin(["1", "true", "yes"])
    meta["is_leveraged"] = meta.get("is_leveraged", False).astype(str).str.lower().isin(["1", "true", "yes"])
    meta["liquidity_20d_value"] = pd.to_numeric(meta.get("liquidity_20d_value"), errors="coerce")
    meta = _add_detail_taxonomy(meta)

    rows = meta[
        [
            "ticker",
            "name",
            "asset_class",
            "group_key",
            "currency_exposure",
            "raw_role_key",
            "e_series_role",
            "role_confidence",
            "role_reason",
            "e_region_bucket",
            "e_asset_bucket",
            "e_strategy_bucket",
            "e_theme_bucket",
            "e_product_structure",
            "e_is_active_strategy",
            "e_is_synthetic",
            "e_is_currency_hedged",
            "e_is_covered_call",
            "e_is_tdf",
            "e_taxonomy_confidence",
            "e_taxonomy_review_flag",
            "is_active",
            "is_inverse",
            "is_leveraged",
            "liquidity_20d_value",
        ]
    ].copy()

    summary = (
        rows.groupby("e_series_role", dropna=False)
        .agg(
            etf_count=("ticker", "nunique"),
            active_count=("is_active", "sum"),
            inverse_count=("is_inverse", "sum"),
            leveraged_count=("is_leveraged", "sum"),
            covered_call_count=("e_is_covered_call", "sum"),
            synthetic_count=("e_is_synthetic", "sum"),
            review_count=("e_taxonomy_review_flag", lambda s: int((s.astype(str) != "OK").sum())),
            avg_role_confidence=("role_confidence", "mean"),
            avg_taxonomy_confidence=("e_taxonomy_confidence", "mean"),
            median_liquidity_20d_value=("liquidity_20d_value", "median"),
        )
        .reset_index()
    )
    for role in STANDARD_ROLES:
        if role not in set(summary["e_series_role"].astype(str)):
            summary = pd.concat(
                [
                    summary,
                    pd.DataFrame(
                        [
                            {
                                "e_series_role": role,
                                "etf_count": 0,
                                "active_count": 0,
                                "inverse_count": 0,
                                "leveraged_count": 0,
                                "covered_call_count": 0,
                                "synthetic_count": 0,
                                "review_count": 0,
                                "avg_role_confidence": np.nan,
                                "avg_taxonomy_confidence": np.nan,
                                "median_liquidity_20d_value": np.nan,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
    summary["role_order"] = summary["e_series_role"].map({role: i + 1 for i, role in enumerate(STANDARD_ROLES)})
    summary = summary.sort_values(["role_order", "e_series_role"]).drop(columns=["role_order"])

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    rows_path = REPORT_DIR / f"e_series_etf_role_taxonomy_{token}.csv"
    summary_path = REPORT_DIR / f"e_series_etf_role_taxonomy_summary_{token}.csv"
    detail_summary_path = REPORT_DIR / f"e_series_etf_role_taxonomy_detail_summary_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_role_taxonomy_{token}.json"
    rows.to_csv(rows_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    detail_summary = (
        rows.groupby(["e_series_role", "e_asset_bucket", "e_strategy_bucket", "e_region_bucket"], dropna=False)
        .agg(
            etf_count=("ticker", "nunique"),
            avg_taxonomy_confidence=("e_taxonomy_confidence", "mean"),
            review_count=("e_taxonomy_review_flag", lambda s: int((s.astype(str) != "OK").sum())),
        )
        .reset_index()
        .sort_values(["e_series_role", "etf_count"], ascending=[True, False])
    )
    detail_summary.to_csv(detail_summary_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_role_taxonomy",
        "strategy_model_code": E_SERIES_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "standard_roles": STANDARD_ROLES,
        "normalization": ROLE_NORMALIZATION,
        "detail_dimensions": [
            "e_region_bucket",
            "e_asset_bucket",
            "e_strategy_bucket",
            "e_theme_bucket",
            "e_product_structure",
        ],
        "summary": _records(summary),
        "detail_summary_top": _records(detail_summary.head(30)),
        "outputs": {
            "taxonomy_csv": str(rows_path),
            "summary_csv": str(summary_path),
            "detail_summary_csv": str(detail_summary_path),
            "json": str(json_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build E-series ETF role taxonomy.")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    print(json.dumps(build_taxonomy(str(args.asof)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
