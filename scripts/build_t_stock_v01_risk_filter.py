from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = "20260331"
IN_DIR = BASE_DIR / "reports" / "model_upgrade_research" / RUN_DATE / "T_STOCK_V01_OPERATIONALIZATION"
OUT_DIR = IN_DIR
LABELS_PATH = BASE_DIR / "data" / "labels" / f"t_stock_v01_theme_labels_{RUN_DATE}.csv"


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

MCAP_FLOOR = 300_000_000_000
THEME_CAPS = {
    "defense_aero": 2,
    "semiconductor_tech": 3,
    "construction_materials": 2,
    "biotech_healthcare": 2,
    "energy_utility_infra": 2,
    "medtech_platform": 1,
    "consumer_brand": 1,
    "general_largecap": 1,
    "other": 1,
}
S2_OVERLAP = {
    "112610", "017960", "084370", "006800", "052690", "001720", "298040", "272210", "079550"
}
GRADE_ORDER = {"confirmed": 0, "near": 1, "observe": 2}


def main() -> None:
    df = pd.read_csv(IN_DIR / f"t_stock_v01_operational_candidates_{ASOF_DATE}.csv", dtype={"ticker": str})
    labels = pd.read_csv(LABELS_PATH, dtype={"ticker": str})[["ticker", "theme_bucket", "theme_name_kr"]].drop_duplicates("ticker")
    df = df.merge(labels, on="ticker", how="left")
    df["is_s2_overlap"] = df["ticker"].isin(S2_OVERLAP)
    df["is_excluded"] = pd.to_numeric(df["mcap"], errors="coerce") < MCAP_FLOOR
    df["grade_order"] = df["candidate_grade"].map(GRADE_ORDER)
    df = df.sort_values(
        ["grade_order", "is_s2_overlap", "stage2_prob", "stage1_prob", "mcap"],
        ascending=[True, False, False, False, False],
        na_position="last",
    )

    kept_rows = []
    excluded_rows = []
    cap_usage = {k: 0 for k in THEME_CAPS}

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        if bool(row_dict["is_excluded"]):
            row_dict["filter_reason"] = "mcap_floor"
            excluded_rows.append(row_dict)
            continue
        theme = row_dict["theme_bucket"]
        cap = THEME_CAPS.get(theme, 1)
        if cap_usage.get(theme, 0) >= cap:
            row_dict["filter_reason"] = f"theme_cap_{theme}"
            excluded_rows.append(row_dict)
            continue
        cap_usage[theme] = cap_usage.get(theme, 0) + 1
        row_dict["filter_reason"] = "kept"
        kept_rows.append(row_dict)

    kept = pd.DataFrame(kept_rows)
    excluded = pd.DataFrame(excluded_rows)

    keep_cols = [
        "candidate_grade", "ticker", "name", "market", "mcap", "theme_bucket", "theme_name_kr", "is_s2_overlap",
        "stage1_prob", "stage2_prob", "filter_reason"
    ]
    kept = kept[keep_cols]
    excluded = excluded[keep_cols].rename(columns={"filter_reason": "exclude_reason"})

    kept.to_csv(OUT_DIR / f"t_stock_v01_risk_filtered_candidates_{ASOF_DATE}.csv", index=False, encoding="utf-8-sig")
    excluded.to_csv(OUT_DIR / f"t_stock_v01_risk_filtered_excluded_{ASOF_DATE}.csv", index=False, encoding="utf-8-sig")
    kept[kept["candidate_grade"] == "confirmed"].to_csv(OUT_DIR / f"t_stock_v01_risk_filtered_confirmed_{ASOF_DATE}.csv", index=False, encoding="utf-8-sig")
    kept[kept["candidate_grade"] == "near"].to_csv(OUT_DIR / f"t_stock_v01_risk_filtered_near_{ASOF_DATE}.csv", index=False, encoding="utf-8-sig")
    kept[kept["candidate_grade"] == "observe"].to_csv(OUT_DIR / f"t_stock_v01_risk_filtered_observe_{ASOF_DATE}.csv", index=False, encoding="utf-8-sig")

    summary = pd.DataFrame([
        {"bucket": "input_total", "count": len(df)},
        {"bucket": "kept_total", "count": len(kept)},
        {"bucket": "kept_confirmed", "count": int((kept["candidate_grade"] == "confirmed").sum())},
        {"bucket": "kept_near", "count": int((kept["candidate_grade"] == "near").sum())},
        {"bucket": "kept_observe", "count": int((kept["candidate_grade"] == "observe").sum())},
        {"bucket": "kept_s2_overlap", "count": int((kept["is_s2_overlap"] == True).sum())},
        {"bucket": "excluded_total", "count": len(excluded)},
        {"bucket": "excluded_mcap_floor", "count": int((excluded["exclude_reason"] == "mcap_floor").sum()) if not excluded.empty else 0},
    ])
    summary.to_csv(OUT_DIR / f"t_stock_v01_risk_filter_summary_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")

    theme_summary = kept.groupby(["candidate_grade", "theme_bucket", "theme_name_kr"], as_index=False).size().rename(columns={"size": "count"})
    theme_summary.to_csv(OUT_DIR / f"t_stock_v01_risk_filter_theme_summary_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")

    md = f"""# T-STOCK-V01 Risk Filter ({ASOF_DATE})

## Rules
- market cap floor: {MCAP_FLOOR:,} KRW
- same-theme cap with S2-overlap priority inside theme
- internal theme labels: `t_stock_v01_theme_labels_{RUN_DATE}.csv`
- theme caps:
  - defense_aero: 2
  - semiconductor_tech: 3
  - construction_materials: 2
  - biotech_healthcare: 2
  - energy_utility_infra: 2
  - medtech_platform: 1
  - consumer_brand: 1
  - general_largecap: 1
  - other: 1

## Result
- input total: {len(df)}
- kept total: {len(kept)}
- kept confirmed: {int((kept['candidate_grade'] == 'confirmed').sum())}
- kept near: {int((kept['candidate_grade'] == 'near').sum())}
- kept observe: {int((kept['candidate_grade'] == 'observe').sum())}
- kept S2 overlap: {int((kept['is_s2_overlap'] == True).sum())}
- excluded total: {len(excluded)}

## Interpretation
- theme crowding is reduced without collapsing the watchlist into a single name
- mcap floor is relaxed to reflect the post-backfill candidate distribution
- the filtered set is the operational watchlist for T-STOCK-V01 before shadow tracking
"""
    (OUT_DIR / f"t_stock_v01_risk_filter_{RUN_DATE}.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
