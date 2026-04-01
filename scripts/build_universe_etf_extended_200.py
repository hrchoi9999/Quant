from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
ASOF = "20260331"
META_CSV = PROJECT_ROOT / r"data\universe\etf_meta_20260317.csv"
OUTDIR = PROJECT_ROOT / r"data\universe"
REPORT_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\ETF_UNIVERSE_200"
OUTDIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_N = 200
GROUP_CAPS = {
    "equity_kr_broad": 25,
    "equity_kr_growth": 35,
    "equity_global_broad": 35,
    "equity_theme_other": 30,
    "equity_income_defensive": 15,
    "bond_short": 15,
    "bond_long": 15,
    "commodity_gold": 5,
    "commodity_other": 5,
    "fx_usd": 8,
    "hedge_inverse_kr": 7,
    "other": 5,
}


def infer_group(row: pd.Series) -> str:
    raw_g = row.get("group_key")
    g = "" if pd.isna(raw_g) else str(raw_g).strip()
    if g:
        if g in {"equity_dividend", "equity_low_vol", "equity_covered_call"}:
            return "equity_income_defensive"
        return g

    raw_asset = row.get("asset_class")
    asset = "" if pd.isna(raw_asset) else str(raw_asset).strip().lower()
    name = str(row.get("name") or "")

    if asset == "bond":
        if any(k in name for k in ["단기", "CD", "KOFR", "머니마켓", "통안채", "국고채3년", "회사채단기"]):
            return "bond_short"
        return "bond_long"
    if asset == "commodity":
        if any(k in name for k in ["금", "골드"]):
            return "commodity_gold"
        return "commodity_other"
    if asset == "fx":
        return "fx_usd"
    if asset == "hedge":
        return "hedge_inverse_kr"
    if asset == "equity":
        if any(k in name for k in ["고배당", "배당", "저변동성", "커버드콜"]):
            return "equity_income_defensive"
        if any(k in name for k in ["미국", "나스닥", "S&P", "MSCI", "월드", "글로벌", "일본", "중국", "인도", "유럽", "반도체나스닥", "필라델피아"]):
            return "equity_global_broad"
        if any(k in name for k in ["코스피", "200", "KRX100", "TOP10", "블루칩"]):
            return "equity_kr_broad"
        return "equity_theme_other"

    if any(k in name for k in ["달러", "USD", "SOFR"]):
        return "fx_usd"
    if any(k in name for k in ["금", "골드", "은선물", "원유"]):
        return "commodity_gold" if ("금" in name or "골드" in name) else "commodity_other"
    if any(k in name for k in ["국채", "채권", "CD", "KOFR", "머니마켓", "단기자금"]):
        return "bond_short" if any(k in name for k in ["CD", "KOFR", "머니마켓", "단기", "통안채", "3년"]) else "bond_long"
    if any(k in name for k in ["인버스"]):
        return "hedge_inverse_kr"
    if any(k in name for k in ["미국", "나스닥", "S&P", "MSCI", "월드", "글로벌", "일본", "중국", "인도", "유럽"]):
        return "equity_global_broad"
    if any(k in name for k in ["배당", "저변동성", "커버드콜"]):
        return "equity_income_defensive"
    if any(k in name for k in ["반도체", "AI", "로봇", "방산", "조선", "원자력", "2차전지", "전력", "자동차", "은행", "증권"]):
        return "equity_theme_other"
    if any(k in name for k in ["코스피", "코스닥", "200", "KRX100"]):
        return "equity_kr_broad"
    return "other"


def main() -> None:
    df = pd.read_csv(META_CSV, dtype={"ticker": str}).copy()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["liquidity_20d_value"] = pd.to_numeric(df["liquidity_20d_value"], errors="coerce").fillna(0.0)
    df["min_liquidity_pass"] = df["min_liquidity_pass"].fillna(False).astype(bool)
    df["is_inverse"] = df["is_inverse"].fillna(False).astype(bool)
    df["is_leveraged"] = df["is_leveraged"].fillna(False).astype(bool)
    df["exclude_from_core"] = df.get("exclude_from_core", False)
    if "exclude_from_core" in df.columns:
        df["exclude_from_core"] = df["exclude_from_core"].fillna(False).astype(bool)
    else:
        df["exclude_from_core"] = False

    eligible = df[
        df["is_active"].fillna(0).astype(int).eq(1)
        & df["min_liquidity_pass"]
        & (~df["is_leveraged"])
        & ((~df["is_inverse"]) | df["group_key"].fillna("").eq("hedge_inverse_kr"))
    ].copy()
    eligible["expanded_group"] = eligible.apply(infer_group, axis=1)
    eligible = eligible.sort_values(["expanded_group", "liquidity_20d_value", "ticker"], ascending=[True, False, True]).reset_index(drop=True)

    selected_parts = []
    selected_tickers: set[str] = set()
    for group, cap in GROUP_CAPS.items():
        sub = eligible[(eligible["expanded_group"] == group) & (~eligible["ticker"].isin(selected_tickers))].copy()
        pick = sub.head(cap).copy()
        selected_parts.append(pick)
        selected_tickers.update(pick["ticker"].tolist())

    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else pd.DataFrame(columns=eligible.columns)
    if len(selected) < TARGET_N:
        remainder = eligible[~eligible["ticker"].isin(selected_tickers)].copy()
        remainder = remainder.sort_values(["liquidity_20d_value", "ticker"], ascending=[False, True])
        fill = remainder.head(TARGET_N - len(selected)).copy()
        selected = pd.concat([selected, fill], ignore_index=True)
        selected_tickers.update(fill["ticker"].tolist())

    core20_path = PROJECT_ROOT / r"data\universe\universe_etf_core_20260325.csv"
    core20 = pd.read_csv(core20_path, dtype={"ticker": str})
    core20["ticker"] = core20["ticker"].astype(str).str.zfill(6)
    core_missing = eligible[eligible["ticker"].isin(core20["ticker"]) & (~eligible["ticker"].isin(selected_tickers))].copy()
    if not core_missing.empty:
        selected = pd.concat([selected, core_missing], ignore_index=True)
        selected_tickers.update(core_missing["ticker"].tolist())
    if len(selected) > TARGET_N:
        removable = selected[~selected["ticker"].isin(core20["ticker"])].sort_values(["liquidity_20d_value", "ticker"], ascending=[True, True])
        drop_n = len(selected) - TARGET_N
        drop_tickers = set(removable.head(drop_n)["ticker"].tolist())
        selected = selected[~selected["ticker"].isin(drop_tickers)].copy()

    selected = selected.sort_values(["expanded_group", "liquidity_20d_value", "ticker"], ascending=[True, False, True]).reset_index(drop=True)
    selected["expanded_universe_type"] = "ETF_EXTENDED_200"
    selected["selection_rule"] = "liquidity_plus_group_caps_core20_forced"
    selected["selection_asof"] = ASOF
    selected["is_in_core20"] = selected["ticker"].isin(core20["ticker"])

    out_csv = OUTDIR / f"universe_etf_extended_200_{ASOF}.csv"
    selected.to_csv(out_csv, index=False, encoding="utf-8-sig")

    summary = selected.groupby("expanded_group", dropna=False).agg(
        count=("ticker", "size"),
        avg_liquidity_20d_value=("liquidity_20d_value", "mean"),
        min_liquidity_20d_value=("liquidity_20d_value", "min"),
        max_liquidity_20d_value=("liquidity_20d_value", "max"),
        core20_overlap=("is_in_core20", "sum"),
    ).reset_index().sort_values(["count", "avg_liquidity_20d_value"], ascending=[False, False])
    summary.to_csv(REPORT_DIR / f"etf_extended_200_summary_{ASOF}.csv", index=False, encoding="utf-8-sig")
    selected[["ticker","name","asset_class","group_key","expanded_group","liquidity_20d_value","is_in_core20"]].to_csv(
        REPORT_DIR / f"etf_extended_200_snapshot_{ASOF}.csv", index=False, encoding="utf-8-sig"
    )

    lines = [
        "# ETF Extended Universe 200",
        "",
        f"- asof: {ASOF}",
        f"- source meta: {META_CSV}",
        f"- eligible ETFs after liquidity / leverage / inverse filter: {len(eligible)}",
        f"- selected ETFs: {len(selected)}",
        f"- core20 overlap: {int(selected['is_in_core20'].sum())}",
        "",
        "## Selection rule",
        "- primary key: 20-day average trading value",
        "- exclude leveraged ETFs",
        "- allow inverse only for `hedge_inverse_kr`",
        "- keep asset-group balance with caps, then fill remainder by liquidity",
        "",
        f"- output csv: {out_csv}",
    ]
    (REPORT_DIR / f"etf_extended_200_design_{ASOF}.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] eligible={len(eligible)} selected={len(selected)} core20_overlap={int(selected['is_in_core20'].sum())}")
    print(f"[OK] out_csv={out_csv}")


if __name__ == "__main__":
    main()
