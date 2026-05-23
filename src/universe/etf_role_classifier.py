from __future__ import annotations

from typing import Any

import pandas as pd


ROLE_SCHEMA_VERSION = "ETF_ROLE_COMMON_V1"

TACTICAL_HEDGE_KEYWORDS = ["inverse", "short", "bear", "인버스"]
TACTICAL_LEVERAGE_KEYWORDS = ["leverage", "leveraged", "bull", "2x", "3x", "레버리지"]

DEFENSIVE_GROUPS = {"bond_short", "bond_long", "fx_usd", "commodity_gold"}
STYLE_GROUPS = {"equity_low_vol", "equity_dividend", "equity_covered_call"}

STYLE_KEYWORDS = [
    "dividend", "quality", "value", "low vol", "lowvol", "covered call", "coveredcall",
    "income", "momentum", "fundamental", "esg", "wide moat", "cash cow", "factor",
    "배당", "고배당", "저변동", "저변동성", "퀄리티", "가치", "밸류", "커버드콜", "인컴",
    "로우볼", "최소변동성", "모멘텀", "펀더멘탈", "블루칩", "우량주", "우선주", "멀티팩터",
    "대장주", "톱",
]

DEFENSIVE_KEYWORDS = [
    "bond", "treasury", "tbill", "t-bill", "cash", "money market", "sofr", "kofr",
    "cd금리", "단기채", "단기자금", "채권", "통안채", "회사채", "하이일드", "국공채",
    "물가채", "머니마켓", "특수채", "trf", "tdf", "tif", "자산배분", "주식혼합",
    "멀티에셋", "국채", "국고채", "금리", "달러", "usd", "gold", "골드", "금현물", "금선물",
]

CORE_KEYWORDS = [
    "kospi", "코스피", "kospi200", "kospi 200", "코스피200", "코스피 200", "krx100",
    "krx 100", "krx300", "krx 300", "kosdaq150", "kosdaq 150", "코스닥150", "코스닥 150",
    "msci korea", "글로벌msci", "ktop30", "top10", "top50", "s&p500", "s&p 500", "sp500",
    "nasdaq100", "nasdaq 100", "나스닥100", "나스닥 100", "dow jones", "다우존스",
    "russell2000", "russell 2000", "러셀2000", "topix100", "topix 100", "eurostoxx50",
    "유로스탁스50", "msci world", "msci emerging", "msci em", "선진국", "신흥국",
]

KR_200_PREFIXES = [
    "kodex 200", "tiger 200", "rise 200", "plus 200", "kiwoom 200", "ace 200", "sol 200",
    "hanaro 200", "trex 200", "파워 200", "won 200", "1q 200", "히어로즈 200",
]

SECTOR_THEME_KEYWORDS = [
    "ai", "bio", "china", "india", "it", "robot", "semiconductor", "battery",
    "secondary battery", "healthcare", "bank", "financial", "energy", "chemical",
    "shipbuilding", "defense", "media", "game", "internet", "reit", "real estate", "oil",
    "copper", "silver", "agriculture", "commodity", "infrastructure", "consumer",
    "transport", "insurance", "construction", "platform", "luxury", "solar", "nuclear",
    "반도체", "2차전지", "배터리", "바이오", "헬스케어", "은행", "금융", "증권", "자동차",
    "조선", "방산", "기계", "철강", "에너지", "화학", "건설", "보험", "운송", "화장품",
    "여행레저", "소비재", "경기소비재", "필수소비재", "콘텐츠", "원유", "팔라듐", "구리",
    "은선물", "농산물", "콩선물", "자원", "인프라", "의료기기", "지주회사", "농업",
    "융복합", "e커머스", "내수주", "혁신기술", "bbig", "5g", "수소", "뉴딜", "클라우드",
    "탄소", "전기", "전기차", "자율주행", "모빌리티", "친환경", "웹툰", "드라마",
    "메타버스", "기후", "골프", "플랫폼", "컬처", "워터", "r&d", "푸드", "capex",
    "미래전략", "소부장", "포스코그룹", "게임", "미디어", "인터넷", "리츠", "부동산",
    "로봇", "우주", "원자력", "원전", "전력", "태양광", "소프트웨어", "삼성그룹",
    "그룹주", "수출주", "우량업종", "중국", "차이나", "인도", "일본", "베트남", "라틴",
    "멕시코", "필리핀", "러시아", "아시아", "차이넥스트",
]

CORE_PURITY_BLOCKERS = [
    " it", "it ", "반도체", "2차전지", "배터리", "은행", "금융", "증권", "자동차", "조선",
    "방산", "기계", "철강", "에너지", "화학", "헬스케어", "바이오", "게임", "미디어",
    "리츠", "로봇", "전력",
]


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "y", "yes"}


def _contains(text: str, keywords: list[str]) -> bool:
    haystack = f" {text.lower()} "
    return any(keyword.lower() in haystack for keyword in keywords)


def _is_strict_core_name(name_l: str) -> bool:
    if _contains(name_l, CORE_PURITY_BLOCKERS):
        return False
    if _contains(name_l, CORE_KEYWORDS):
        return True
    if " 200" in name_l or name_l.endswith("200") or "200액티브" in name_l:
        return True
    return any(name_l.startswith(prefix) for prefix in KR_200_PREFIXES)


def classify_role(row: pd.Series) -> dict[str, Any]:
    name = str(row.get("name", "") or "")
    name_l = name.lower()
    group_key = str(row.get("group_key", "") or "").strip()
    asset_class = str(row.get("asset_class", "") or "").strip().lower()
    is_inverse = _to_bool(row.get("is_inverse", False)) or _contains(name_l, TACTICAL_HEDGE_KEYWORDS)
    is_leveraged = _to_bool(row.get("is_leveraged", False)) or _contains(name_l, TACTICAL_LEVERAGE_KEYWORDS)

    if is_inverse:
        return {"role_key": "TACTICAL_HEDGE", "role_confidence": 1.0, "role_reason": "inverse_or_short"}
    if is_leveraged:
        return {"role_key": "TACTICAL_LEVERAGE", "role_confidence": 1.0, "role_reason": "leveraged_directional"}
    if group_key in DEFENSIVE_GROUPS or asset_class in {"bond", "fx", "commodity"} or _contains(name_l, DEFENSIVE_KEYWORDS):
        return {"role_key": "DEFENSIVE_HEDGE", "role_confidence": 0.9, "role_reason": "defensive_asset_or_keyword"}
    if group_key in STYLE_GROUPS or _contains(name_l, STYLE_KEYWORDS):
        return {"role_key": "STYLE_FACTOR", "role_confidence": 0.88, "role_reason": "style_factor_keyword"}
    if _is_strict_core_name(name_l):
        return {"role_key": "CORE_BETA", "role_confidence": 0.85, "role_reason": "broad_beta_keyword"}
    if group_key == "equity_kr_broad":
        return {"role_key": "CORE_BETA", "role_confidence": 0.65, "role_reason": "legacy_broad_group_fallback"}
    if group_key == "equity_kr_growth" or asset_class == "equity" or _contains(name_l, SECTOR_THEME_KEYWORDS):
        reason = "sector_theme_keyword" if _contains(name_l, SECTOR_THEME_KEYWORDS) else "equity_theme_fallback"
        confidence = 0.8 if reason == "sector_theme_keyword" else 0.45
        return {"role_key": "SECTOR_THEME", "role_confidence": confidence, "role_reason": reason}
    return {"role_key": "UNCLASSIFIED", "role_confidence": 0.0, "role_reason": "insufficient_name_or_meta_signal"}


def add_purity_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["purity_issue"] = ""
    broad_not_core = (out["group_key"].fillna("") == "equity_kr_broad") & (out["role_key"] != "CORE_BETA")
    out.loc[broad_not_core, "purity_issue"] = "legacy_broad_not_core_role"
    growth_style = (out["group_key"].fillna("") == "equity_kr_growth") & (out["role_key"] == "STYLE_FACTOR")
    out.loc[growth_style, "purity_issue"] = "legacy_growth_style_split_candidate"
    low_conf = (out["role_confidence"] < 0.5) & (out["purity_issue"] == "")
    out.loc[low_conf, "purity_issue"] = "low_confidence_role"
    unclassified = out["role_key"] == "UNCLASSIFIED"
    out.loc[unclassified, "purity_issue"] = "unclassified_role"
    out["is_role_purity_exception"] = out["purity_issue"].ne("")
    return out


def add_role_classification(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ticker"] = out["ticker"].astype(str).str.strip().str.zfill(6)
    role_rows = out.apply(classify_role, axis=1, result_type="expand")
    out = pd.concat([out, role_rows], axis=1)
    out["role_schema_version"] = ROLE_SCHEMA_VERSION
    return add_purity_flags(out)


def _pick_group(df: pd.DataFrame, group_key: str, mask: pd.Series, limit: int, exclude: set[str] | None = None) -> pd.DataFrame:
    exclude = exclude or set()
    picked = df.loc[mask].copy()
    if exclude:
        picked = picked.loc[~picked["ticker"].isin(exclude)].copy()
    if picked.empty:
        return pd.DataFrame(columns=df.columns)
    picked = picked.sort_values(["liquidity_20d_value", "ticker"], ascending=[False, True]).head(limit).copy()
    picked["group_key"] = group_key
    return picked


def _name_series(df: pd.DataFrame) -> pd.Series:
    return df["name"].fillna("").astype(str)


def _name_contains(df: pd.DataFrame, pattern: str) -> pd.Series:
    return _name_series(df).str.contains(pattern, case=False, regex=True)


def _kr_broad_mask(df: pd.DataFrame) -> pd.Series:
    names = _name_series(df)
    domestic = names.str.contains("코스피|코스닥|kospi|kosdaq|krx|korea|200", case=False, regex=True)
    foreign = names.str.contains("미국|s&p|sp500|nasdaq|나스닥|다우|russell|러셀|topix|일본|유로|msci em|선진국|신흥국", case=False, regex=True)
    return domestic & ~foreign


def build_role_based_core_universe(role_df: pd.DataFrame) -> pd.DataFrame:
    df = role_df.copy()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["liquidity_20d_value"] = pd.to_numeric(df["liquidity_20d_value"], errors="coerce").fillna(0.0)
    df["min_liquidity_pass"] = df["min_liquidity_pass"].astype(str).str.lower().isin({"true", "1", "yes"})
    df["exclude_from_core"] = df["exclude_from_core"].astype(str).str.lower().isin({"true", "1", "yes"})

    base = df.loc[
        df["min_liquidity_pass"]
        & ~df["exclude_from_core"]
        & df["role_key"].ne("UNCLASSIFIED")
    ].copy()

    parts: list[pd.DataFrame] = []
    growth = _pick_group(base, "equity_kr_growth", base["role_key"].eq("SECTOR_THEME"), 3)
    growth_tickers = set(growth["ticker"].astype(str)) if not growth.empty else set()

    parts.append(_pick_group(base, "equity_kr_broad", base["role_key"].eq("CORE_BETA") & _kr_broad_mask(base), 5))
    parts.append(growth)
    parts.append(_pick_group(base, "equity_sector_momentum", base["role_key"].eq("SECTOR_THEME"), 3, exclude=growth_tickers))
    parts.append(_pick_group(base, "equity_low_vol", base["role_key"].eq("STYLE_FACTOR") & _name_contains(base, "저변동|로우볼|low.?vol|최소변동"), 1))
    parts.append(_pick_group(base, "equity_dividend", base["role_key"].eq("STYLE_FACTOR") & _name_contains(base, "배당|dividend") & ~_name_contains(base, "커버드콜|covered"), 1))
    parts.append(_pick_group(base, "equity_covered_call", base["role_key"].eq("STYLE_FACTOR") & _name_contains(base, "커버드콜|covered"), 1))
    parts.append(_pick_group(base, "bond_short", base["role_key"].eq("DEFENSIVE_HEDGE") & _name_contains(base, "cd금리|kofr|단기|통안채|머니마켓|1년금리"), 2))
    parts.append(_pick_group(base, "bond_long", base["role_key"].eq("DEFENSIVE_HEDGE") & _name_contains(base, "30년|장기|10년|중장기"), 2))
    parts.append(_pick_group(base, "fx_usd", base["role_key"].eq("DEFENSIVE_HEDGE") & _name_contains(base, "달러|usd|sofr"), 2))
    parts.append(_pick_group(base, "commodity_gold", base["role_key"].eq("DEFENSIVE_HEDGE") & _name_contains(base, "금현물|골드|금선물"), 2))
    parts.append(
        _pick_group(
            base,
            "hedge_inverse_kr",
            base["role_key"].eq("TACTICAL_HEDGE") & _name_contains(base, "코스피|코스닥|200|인버스") & ~_name_contains(base, "원유|달러|금|채권"),
            1,
        )
    )

    core = pd.concat([p for p in parts if p is not None and not p.empty], ignore_index=True)
    core = core.drop_duplicates(["group_key", "ticker"]).copy()
    if "market" not in core.columns:
        core["market"] = "ETF"
    return core.sort_values(["group_key", "liquidity_20d_value", "ticker"], ascending=[True, False, True]).reset_index(drop=True)
