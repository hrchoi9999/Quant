from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.universe.etf_role_classifier import add_role_classification


UNIVERSE_DIR = PROJECT_ROOT / "data" / "universe"
REPORT_ROOT = PROJECT_ROOT / "reports" / "etf_common_framework"

ROLE_KEYS = {
    "CORE_BETA",
    "STYLE_FACTOR",
    "SECTOR_THEME",
    "DEFENSIVE_HEDGE",
    "TACTICAL_LEVERAGE",
    "TACTICAL_HEDGE",
    "UNCLASSIFIED",
}

TACTICAL_HEDGE_KEYWORDS = [
    "inverse",
    "short",
    "bear",
    "인버스",
]

TACTICAL_LEVERAGE_KEYWORDS = [
    "leverage",
    "leveraged",
    "bull",
    "2x",
    "3x",
    "레버리지",
]

DEFENSIVE_GROUPS = {
    "bond_short",
    "bond_long",
    "fx_usd",
    "commodity_gold",
}

STYLE_GROUPS = {
    "equity_low_vol",
    "equity_dividend",
    "equity_covered_call",
}

STYLE_KEYWORDS = [
    "dividend",
    "quality",
    "value",
    "low vol",
    "lowvol",
    "covered call",
    "coveredcall",
    "income",
    "momentum",
    "fundamental",
    "esg",
    "wide moat",
    "cash cow",
    "factor",
    "배당",
    "고배당",
    "저변동",
    "저변동성",
    "퀄리티",
    "가치",
    "밸류",
    "커버드콜",
    "인컴",
    "로우볼",
    "최소변동성",
    "모멘텀",
    "펀더멘탈",
    "블루칩",
    "우량주",
    "우선주",
    "멀티팩터",
    "대장주",
    "톱",
]

DEFENSIVE_KEYWORDS = [
    "bond",
    "treasury",
    "tbill",
    "t-bill",
    "cash",
    "money market",
    "sofr",
    "kofr",
    "cd금리",
    "단기채",
    "단기자금",
    "채권",
    "통안채",
    "회사채",
    "하이일드",
    "국공채",
    "물가채",
    "머니마켓",
    "특수채",
    "trf",
    "tdf",
    "tif",
    "자산배분",
    "주식혼합",
    "멀티에셋",
    "국채",
    "국고채",
    "금리",
    "달러",
    "usd",
    "gold",
    "골드",
    "금현물",
    "금선물",
]

CORE_KEYWORDS = [
    "kospi",
    "코스피",
    "kospi200",
    "kospi 200",
    "코스피200",
    "코스피 200",
    "krx100",
    "krx 100",
    "krx300",
    "krx 300",
    "kosdaq150",
    "kosdaq 150",
    "코스닥150",
    "코스닥 150",
    "msci korea",
    "글로벌msci",
    "ktop30",
    "top10",
    "top50",
    "s&p500",
    "s&p 500",
    "sp500",
    "nasdaq100",
    "nasdaq 100",
    "나스닥100",
    "나스닥 100",
    "dow jones",
    "다우존스",
    "russell2000",
    "russell 2000",
    "러셀2000",
    "topix100",
    "topix 100",
    "eurostoxx50",
    "유로스탁스50",
    "msci world",
    "msci emerging",
    "msci em",
    "dax",
    "독일dax",
    "선진국",
    "신흥국",
]

KR_200_PREFIXES = [
    "kodex 200",
    "tiger 200",
    "rise 200",
    "plus 200",
    "kiwoom 200",
    "ace 200",
    "sol 200",
    "hanaro 200",
    "trex 200",
    "파워 200",
    "won 200",
    "1q 200",
    "히어로즈 200",
]

SECTOR_THEME_KEYWORDS = [
    "ai",
    "bio",
    "china",
    "india",
    "it",
    "robot",
    "semiconductor",
    "battery",
    "secondary battery",
    "healthcare",
    "bank",
    "financial",
    "energy",
    "chemical",
    "shipbuilding",
    "defense",
    "media",
    "game",
    "internet",
    "reit",
    "real estate",
    "oil",
    "copper",
    "silver",
    "agriculture",
    "commodity",
    "infrastructure",
    "consumer",
    "transport",
    "insurance",
    "construction",
    "platform",
    "luxury",
    "solar",
    "nuclear",
    "반도체",
    "2차전지",
    "배터리",
    "바이오",
    "헬스케어",
    "은행",
    "금융",
    "증권",
    "자동차",
    "조선",
    "방산",
    "기계",
    "철강",
    "에너지",
    "화학",
    "건설",
    "보험",
    "운송",
    "화장품",
    "여행레저",
    "소비재",
    "경기소비재",
    "필수소비재",
    "콘텐츠",
    "원유",
    "팔라듐",
    "구리",
    "은선물",
    "농산물",
    "콩선물",
    "자원",
    "인프라",
    "의료기기",
    "지주회사",
    "농업",
    "융복합",
    "e커머스",
    "내수주",
    "혁신기술",
    "bbig",
    "5g",
    "수소",
    "뉴딜",
    "클라우드",
    "탄소",
    "전기",
    "전기차",
    "자율주행",
    "모빌리티",
    "친환경",
    "웹툰",
    "드라마",
    "메타버스",
    "기후",
    "골프",
    "플랫폼",
    "컬처",
    "워터",
    "r&d",
    "푸드",
    "capex",
    "미래전략",
    "소부장",
    "포스코그룹",
    "게임",
    "미디어",
    "인터넷",
    "리츠",
    "부동산",
    "로봇",
    "우주",
    "원자력",
    "원전",
    "전력",
    "태양광",
    "소프트웨어",
    "삼성그룹",
    "그룹주",
    "수출주",
    "우량업종",
    "중국",
    "차이나",
    "인도",
    "일본",
    "베트남",
    "라틴",
    "멕시코",
    "필리핀",
    "러시아",
    "아시아",
    "차이넥스트",
]

CORE_PURITY_BLOCKERS = [
    " it",
    "it ",
    "반도체",
    "2차전지",
    "배터리",
    "은행",
    "금융",
    "증권",
    "자동차",
    "조선",
    "방산",
    "기계",
    "철강",
    "에너지",
    "화학",
    "헬스케어",
    "바이오",
    "게임",
    "미디어",
    "리츠",
    "로봇",
    "전력",
]


def _parse_asof(raw: str) -> str:
    return raw.replace("-", "")


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
        return {
            "role_key": "TACTICAL_HEDGE",
            "role_confidence": 1.0,
            "role_reason": "inverse_or_short",
        }
    if is_leveraged:
        return {
            "role_key": "TACTICAL_LEVERAGE",
            "role_confidence": 1.0,
            "role_reason": "leveraged_directional",
        }
    if group_key in DEFENSIVE_GROUPS or asset_class in {"bond", "fx", "commodity"} or _contains(name_l, DEFENSIVE_KEYWORDS):
        return {
            "role_key": "DEFENSIVE_HEDGE",
            "role_confidence": 0.9,
            "role_reason": "defensive_asset_or_keyword",
        }
    if group_key in STYLE_GROUPS or _contains(name_l, STYLE_KEYWORDS):
        return {
            "role_key": "STYLE_FACTOR",
            "role_confidence": 0.88,
            "role_reason": "style_factor_keyword",
        }
    if _is_strict_core_name(name_l):
        return {
            "role_key": "CORE_BETA",
            "role_confidence": 0.85,
            "role_reason": "broad_beta_keyword",
        }
    if group_key == "equity_kr_broad":
        return {
            "role_key": "CORE_BETA",
            "role_confidence": 0.65,
            "role_reason": "legacy_broad_group_fallback",
        }
    if group_key == "equity_kr_growth" or asset_class == "equity" or _contains(name_l, SECTOR_THEME_KEYWORDS):
        reason = "sector_theme_keyword" if _contains(name_l, SECTOR_THEME_KEYWORDS) else "equity_theme_fallback"
        confidence = 0.8 if reason == "sector_theme_keyword" else 0.45
        return {
            "role_key": "SECTOR_THEME",
            "role_confidence": confidence,
            "role_reason": reason,
        }
    return {
        "role_key": "UNCLASSIFIED",
        "role_confidence": 0.0,
        "role_reason": "insufficient_name_or_meta_signal",
    }


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


def latest_meta_path() -> Path:
    files = sorted(UNIVERSE_DIR.glob("etf_meta_*.csv"))
    if not files:
        raise FileNotFoundError(f"No etf_meta_*.csv found under {UNIVERSE_DIR}")
    return files[-1]


def build_review_md(
    *,
    asof: str,
    generated_at: str,
    source_path: Path,
    output_path: Path,
    report_dir: Path,
    df: pd.DataFrame,
) -> str:
    counts = df["role_key"].value_counts(dropna=False).rename_axis("role_key").reset_index(name="count")
    exception_counts = (
        df.loc[df["is_role_purity_exception"], "purity_issue"]
        .value_counts(dropna=False)
        .rename_axis("purity_issue")
        .reset_index(name="count")
    )

    def markdown_table(table_df: pd.DataFrame) -> str:
        if table_df.empty:
            return ""
        cols = list(table_df.columns)
        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        rows = []
        for _, row in table_df.iterrows():
            rows.append("| " + " | ".join(str(row[col]) for col in cols) + " |")
        return "\n".join([header, sep, *rows])

    lines = [
        f"# ETF Common Role Classification Review - {asof}",
        "",
        f"- generated_at: {generated_at}",
        f"- source: `{source_path}`",
        f"- output: `{output_path}`",
        f"- total_rows: {len(df)}",
        "",
        "## Role Counts",
        "",
        markdown_table(counts),
        "",
        "## Purity / Review Counts",
        "",
        markdown_table(exception_counts) if not exception_counts.empty else "No review exceptions.",
        "",
        "## Review Notes",
        "",
        "- This is a side-car classification. Existing `group_key` is not overwritten.",
        "- `UNCLASSIFIED` and low-confidence rows should be reviewed before role-based model promotion.",
        "- Broad-purity exceptions are the first risk area before expanding ETF model universe size.",
        "",
        "## Generated Files",
        "",
        f"- `{report_dir / 'etf_role_classification_summary.csv'}`",
        f"- `{report_dir / 'etf_broad_purity_exceptions.csv'}`",
        f"- `{report_dir / 'etf_role_low_confidence_review.csv'}`",
    ]
    return "\n".join(lines) + "\n"


def run(asof: str | None) -> None:
    asof_compact = _parse_asof(asof) if asof else ""
    source_path = UNIVERSE_DIR / f"etf_meta_{asof_compact}.csv" if asof_compact else latest_meta_path()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if not asof_compact:
        asof_compact = source_path.stem.removeprefix("etf_meta_")

    df = pd.read_csv(source_path, dtype={"ticker": "string"}).fillna("")
    df["ticker"] = df["ticker"].astype(str).str.strip().str.zfill(6)

    out = add_role_classification(df)

    output_path = UNIVERSE_DIR / f"etf_role_classification_{asof_compact}.csv"
    out.to_csv(output_path, index=False, encoding="utf-8-sig")

    report_dir = REPORT_ROOT / asof_compact
    report_dir.mkdir(parents=True, exist_ok=True)

    summary = (
        out.groupby(["role_key", "role_reason"], dropna=False)
        .agg(
            count=("ticker", "count"),
            avg_liquidity_20d_value=("liquidity_20d_value", "mean"),
            avg_history_days=("history_days", "mean"),
            review_count=("is_role_purity_exception", "sum"),
        )
        .reset_index()
        .sort_values(["role_key", "count"], ascending=[True, False])
    )
    summary.to_csv(report_dir / "etf_role_classification_summary.csv", index=False, encoding="utf-8-sig")

    exceptions = out.loc[out["is_role_purity_exception"]].copy()
    exceptions.to_csv(report_dir / "etf_broad_purity_exceptions.csv", index=False, encoding="utf-8-sig")

    low_conf = out.loc[(out["role_confidence"] < 0.5) | (out["role_key"] == "UNCLASSIFIED")].copy()
    low_conf.to_csv(report_dir / "etf_role_low_confidence_review.csv", index=False, encoding="utf-8-sig")

    generated_at = datetime.now().isoformat(timespec="seconds")
    review_md = build_review_md(
        asof=asof_compact,
        generated_at=generated_at,
        source_path=source_path,
        output_path=output_path,
        report_dir=report_dir,
        df=out,
    )
    (report_dir / "etf_role_classification_review.md").write_text(review_md, encoding="utf-8")

    print(f"source={source_path}")
    print(f"output={output_path}")
    print(f"report_dir={report_dir}")
    print(out["role_key"].value_counts(dropna=False).to_string())
    print("review_exceptions=", int(out["is_role_purity_exception"].sum()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build common ETF role classification side-car files.")
    parser.add_argument("--asof", default=None, help="ETF meta as-of date, e.g. 20260427 or 2026-04-27")
    args = parser.parse_args()
    run(args.asof)


if __name__ == "__main__":
    main()
