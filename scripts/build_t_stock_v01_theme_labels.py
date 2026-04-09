from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = "20260331"
IN_DIR = BASE_DIR / "reports" / "model_upgrade_research" / RUN_DATE / "T_STOCK_V01_OPERATIONALIZATION"
OUT_DIR = BASE_DIR / "data" / "labels"
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR = IN_DIR


def latest_asof_from_dir(src_dir: Path, pattern: str) -> str:
    candidates: list[str] = []
    regex = re.compile(pattern)
    for p in src_dir.iterdir():
        m = regex.match(p.name)
        if m:
            candidates.append(m.group(1))
    if not candidates:
        raise FileNotFoundError(f"No matching files for {pattern} in {src_dir}")
    return max(candidates)

ASOF_DATE = latest_asof_from_dir(IN_DIR, r"t_stock_v01_operational_candidates_(\d{4}-\d{2}-\d{2})\.csv")

THEME_NAME_KR = {
    "defense_aero": "방산/항공우주",
    "semiconductor_tech": "반도체/전자부품",
    "construction_materials": "건설/소재",
    "biotech_healthcare": "바이오/헬스케어",
    "energy_utility_infra": "에너지/전력/인프라",
    "medtech_platform": "의료기기/플랫폼",
    "consumer_brand": "소비재/브랜드",
    "general_largecap": "대형주/플랫폼",
    "other": "기타",
}


def classify_theme(name: str) -> str:
    name = str(name)
    if any(k in name for k in ["LIG", "한화에어로", "한화시스템", "한화오션", "현대로템", "SNT", "한국항공우주"]):
        return "defense_aero"
    if any(k in name for k in ["반도체", "유진테크", "이수페타", "삼성전자", "SK스퀘어", "기가비스", "선익시스템", "성호전자"]):
        return "semiconductor_tech"
    if any(k in name for k in ["대우건설", "삼표시멘트", "시멘트", "건설"]):
        return "construction_materials"
    if any(k in name for k in ["현대바이오", "알지노믹스", "메지온", "현대ADM"]):
        return "biotech_healthcare"
    if any(k in name for k in ["한화솔루션", "보성파워텍", "씨에스윈드", "GS건설", "한전기술", "한국전력", "효성"]):
        return "energy_utility_infra"
    if any(k in name for k in ["씨어스테크놀로지"]):
        return "medtech_platform"
    if any(k in name for k in ["삼양식품", "코스맥스", "한국콜마", "아모레", "롯데관광"]):
        return "consumer_brand"
    if "크래프톤" in name:
        return "general_largecap"
    return "other"


def main() -> None:
    df = pd.read_csv(IN_DIR / f"t_stock_v01_operational_candidates_{ASOF_DATE}.csv", dtype={"ticker": str})
    df["theme_bucket"] = df["name"].apply(classify_theme)
    df["theme_name_kr"] = df["theme_bucket"].map(THEME_NAME_KR)
    df["label_source"] = "internal_rule_v2"
    df["label_scope"] = "t_stock_v01_operational_candidates"
    df["asof_date"] = ASOF_DATE

    label_cols = [
        "asof_date", "ticker", "name", "market", "theme_bucket", "theme_name_kr",
        "label_source", "label_scope"
    ]
    labels = df[label_cols].sort_values(["theme_bucket", "market", "ticker"])
    labels.to_csv(OUT_DIR / f"t_stock_v01_theme_labels_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")

    summary = labels.groupby(["theme_bucket", "theme_name_kr", "market"], as_index=False).size().rename(columns={"size": "count"})
    summary.to_csv(REPORT_DIR / f"t_stock_v01_theme_labels_summary_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")

    md = f"""# T-STOCK-V01 Internal Theme Labels ({ASOF_DATE})

## Purpose
- Separate stock theme labeling from the risk filter.
- Use an internal, rule-based theme map for `T-STOCK-V01` operational candidates.

## Scope
- label source: `internal_rule_v2`
- label scope: `t_stock_v01_operational_candidates`
- covered names: `{len(labels)}`

## Theme Buckets
- `defense_aero`: 방산/항공우주
- `semiconductor_tech`: 반도체/전자부품
- `construction_materials`: 건설/소재
- `biotech_healthcare`: 바이오/헬스케어
- `energy_utility_infra`: 에너지/전력/인프라
- `medtech_platform`: 의료기기/플랫폼
- `consumer_brand`: 소비재/브랜드
- `general_largecap`: 대형주/플랫폼
- `other`: 기타

## Notes
- This is not an official sector/industry master.
- It is an internal labeling layer for T-series operational risk control and reporting.
"""
    (REPORT_DIR / f"t_stock_v01_theme_labels_{RUN_DATE}.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
