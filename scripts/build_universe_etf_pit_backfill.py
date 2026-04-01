from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import sqlite3

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
OUT_UNIVERSE_DIR = PROJECT_ROOT / r"data\universe\etf_pit_backfill"
OUT_REPORT_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\ETF_PIT_BACKFILL"
OUT_UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
OUT_REPORT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = pd.Timestamp("2017-01-01")
END_DATE = pd.Timestamp("2026-03-31")
TARGET_N = 200
MIN_HISTORY_DAYS = 120
MIN_LIQUIDITY_VALUE = 2_000_000_000.0
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
        if any(k in name for k in ["미국", "나스닥", "S&P", "MSCI", "월드", "글로벌", "일본", "중국", "인도", "유럽", "필라델피아"]):
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


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(PRICE_DB) as conn:
        prices = pd.read_sql_query(
            """
            select p.ticker, p.date, p.close, p.volume, p.value, im.name
            from prices_daily p
            join instrument_master im on im.ticker = p.ticker
            where im.asset_type = 'ETF'
              and p.date >= '2013-01-01'
            """,
            conn,
        )
        meta = pd.read_sql_query(
            "select ticker, asset_class, group_key, currency_exposure, is_inverse, is_leveraged, asof from etf_meta",
            conn,
        )
        inst = pd.read_sql_query(
            "select ticker, name, asset_type, is_active, first_seen, last_seen from instrument_master where asset_type='ETF'",
            conn,
        )
    prices["ticker"] = prices["ticker"].astype(str).str.zfill(6)
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
    meta["ticker"] = meta["ticker"].astype(str).str.zfill(6)
    meta["asof"] = pd.to_datetime(meta["asof"], format="%Y%m%d", errors="coerce")
    inst["ticker"] = inst["ticker"].astype(str).str.zfill(6)
    return prices, meta, inst


def build_monthly_signal_dates(prices: pd.DataFrame) -> list[pd.Timestamp]:
    dates = pd.Series(sorted(prices["date"].drop_duplicates().tolist()))
    month_ends = dates.groupby(dates.dt.to_period("M")).max()
    signal_dates = [pd.Timestamp(d) for d in month_ends.tolist() if START_DATE <= pd.Timestamp(d) <= END_DATE]
    return signal_dates


def choose_meta_for_asof(meta: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    le = meta[meta["asof"] <= asof].copy()
    if not le.empty:
        chosen = le.sort_values(["ticker", "asof"]).groupby("ticker", as_index=False).tail(1)
    else:
        chosen = pd.DataFrame(columns=meta.columns)
    missing = sorted(set(meta["ticker"]) - set(chosen["ticker"]))
    if missing:
        fallback = meta[meta["ticker"].isin(missing)].sort_values(["ticker", "asof"]).groupby("ticker", as_index=False).head(1)
        chosen = pd.concat([chosen, fallback], ignore_index=True)
    chosen = chosen.sort_values(["ticker", "asof"]).drop_duplicates(["ticker"], keep="last")
    return chosen


def build_asof_universe(asof: pd.Timestamp, prices: pd.DataFrame, meta: pd.DataFrame, inst: pd.DataFrame) -> pd.DataFrame:
    trailing = prices[prices["date"] <= asof].copy()
    if trailing.empty:
        return pd.DataFrame()
    trailing = trailing.sort_values(["ticker", "date"]).copy()
    latest = trailing.groupby("ticker", as_index=False).tail(1).copy()
    latest = latest.rename(columns={"date": "last_trade_date", "close": "last_close", "value": "last_value"})
    hist = trailing.groupby("ticker").agg(
        first_price_date=("date", "min"),
        history_days=("date", "size"),
    ).reset_index()
    liq = trailing.groupby("ticker").tail(20).groupby("ticker", as_index=False).agg(
        liquidity_20d_value=("value", "mean"),
        liquidity_obs=("value", "size"),
    )
    chosen_meta = choose_meta_for_asof(meta, asof)

    base = latest[["ticker", "name", "last_trade_date"]].merge(hist, on="ticker", how="left")
    base = base.merge(liq, on="ticker", how="left")
    base = base.merge(chosen_meta.drop(columns=["asof"]), on="ticker", how="left")
    base = base.merge(inst[["ticker", "name"]].rename(columns={"name": "inst_name"}), on="ticker", how="left")
    base["name"] = base["name"].fillna(base["inst_name"])
    base = base.drop(columns=["inst_name"])

    base["is_inverse"] = base["is_inverse"].fillna(0).astype(int).astype(bool)
    base["is_leveraged"] = base["is_leveraged"].fillna(0).astype(int).astype(bool)
    base["currency_exposure"] = base["currency_exposure"].fillna("KRW")
    base["asset_class"] = base["asset_class"].fillna("")
    base["group_key"] = base["group_key"].fillna("")
    base["liquidity_20d_value"] = pd.to_numeric(base["liquidity_20d_value"], errors="coerce").fillna(0.0)
    base["history_days"] = pd.to_numeric(base["history_days"], errors="coerce").fillna(0).astype(int)
    base["liquidity_obs"] = pd.to_numeric(base["liquidity_obs"], errors="coerce").fillna(0).astype(int)

    eligible = base[
        (base["last_trade_date"] == asof)
        & (base["history_days"] >= MIN_HISTORY_DAYS)
        & (base["liquidity_obs"] >= 20)
        & (base["liquidity_20d_value"] >= MIN_LIQUIDITY_VALUE)
        & (~base["is_leveraged"])
        & ((~base["is_inverse"]) | (base["group_key"] == "hedge_inverse_kr"))
    ].copy()
    if eligible.empty:
        return eligible

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

    selected = selected.sort_values(["expanded_group", "liquidity_20d_value", "ticker"], ascending=[True, False, True]).reset_index(drop=True)
    selected["selection_asof"] = asof
    selected["selection_rule"] = "pit_price_anchored_liquidity_group_caps_v1"
    selected["selection_target_n"] = TARGET_N
    return selected


def main() -> None:
    prices, meta, inst = load_data()
    signal_dates = build_monthly_signal_dates(prices)
    monthly_parts = []
    summary_rows = []

    for asof in signal_dates:
        univ = build_asof_universe(asof, prices, meta, inst)
        if univ.empty:
            summary_rows.append({
                "selection_asof": asof,
                "eligible_count": 0,
                "selected_count": 0,
                "min_first_price_date": pd.NaT,
                "max_first_price_date": pd.NaT,
            })
            continue
        monthly_parts.append(univ)
        summary_rows.append({
            "selection_asof": asof,
            "eligible_count": int((prices[prices['date'] <= asof].groupby('ticker').size() >= MIN_HISTORY_DAYS).sum()),
            "selected_count": len(univ),
            "min_first_price_date": univ["first_price_date"].min(),
            "max_first_price_date": univ["first_price_date"].max(),
        })

    monthly_df = pd.concat(monthly_parts, ignore_index=True) if monthly_parts else pd.DataFrame()
    summary_df = pd.DataFrame(summary_rows).sort_values("selection_asof")

    monthly_path = OUT_UNIVERSE_DIR / "universe_etf_pit_monthly_201701_202603.csv"
    summary_path = OUT_REPORT_DIR / "etf_pit_backfill_monthly_summary_201701_202603.csv"
    coverage_path = OUT_REPORT_DIR / "etf_pit_backfill_group_coverage_201701_202603.csv"

    monthly_df.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    if not monthly_df.empty:
        coverage = monthly_df.groupby(["selection_asof", "expanded_group"], dropna=False).size().reset_index(name="count")
        coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=["selection_asof", "expanded_group", "count"]).to_csv(coverage_path, index=False, encoding="utf-8-sig")

    lines = [
        "# ETF PIT Backfill Universe Design",
        "",
        "## Goal",
        "- Build a point-in-time monthly ETF universe from 2017 for T-ETF backfill.",
        "",
        "## PIT rules",
        "- Use the last trading day of each month as `selection_asof`.",
        "- Treat `first_price_date` from `prices_daily` as the surrogate listing start.",
        "- Require a real ETF close on `selection_asof`.",
        f"- Require at least {MIN_HISTORY_DAYS} trading days of history.",
        f"- Require trailing 20-day average trading value >= {MIN_LIQUIDITY_VALUE:,.0f} KRW.",
        "- Exclude leveraged ETFs.",
        "- Allow inverse only for `hedge_inverse_kr`.",
        "- Apply the same group-cap framework used by the expanded 200 universe.",
        "",
        "## Metadata policy",
        "- Use the latest `etf_meta.asof <= selection_asof` when available.",
        "- If no historical meta exists yet, backfill with the earliest available `etf_meta` snapshot for that ticker.",
        "- This makes pre-2024 classification a surrogate PIT mapping, not a perfect historical reconstruction.",
        "",
        "## Outputs",
        f"- monthly universe: {monthly_path}",
        f"- monthly summary: {summary_path}",
        f"- group coverage: {coverage_path}",
        "",
        f"- monthly windows: {len(summary_df)}",
        f"- first selection month: {summary_df['selection_asof'].min() if not summary_df.empty else 'n/a'}",
        f"- last selection month: {summary_df['selection_asof'].max() if not summary_df.empty else 'n/a'}",
        f"- latest selected count: {int(summary_df['selected_count'].iloc[-1]) if not summary_df.empty else 0}",
    ]
    (OUT_REPORT_DIR / "etf_pit_backfill_design_20260331.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] monthly_rows={len(monthly_df)}")
    print(f"[OK] months={len(summary_df)}")
    print(f"[OK] latest_selected={int(summary_df['selected_count'].iloc[-1]) if not summary_df.empty else 0}")
    print(f"[OK] monthly_path={monthly_path}")


if __name__ == "__main__":
    main()
