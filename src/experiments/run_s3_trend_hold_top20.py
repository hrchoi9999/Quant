# run_s3_trend_hold_top20.py ver 2026-03-12_001
import argparse
import sqlite3
import csv
from datetime import date
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")

UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
FEATURES_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"

TABLE_PRICE = "s3_price_features_daily"
TABLE_FUND = "s3_fund_features_monthly"

OUTDIR = PROJECT_ROOT / r"reports\backtest_s3_dev"
TODAY_STR = date.today().strftime("%Y-%m-%d")


@dataclass
class Params:
    asof: str = TODAY_STR
    start: str = "2013-10-14"
    end: str = TODAY_STR
    top_n: int = 20

    weekly_anchor_weekday: int = 2  # 0=Mon ... 2=Wed (S2에서 쓰던 방식과 유사)
    min_holdings: int = 10

    # Entry 조건
    entry_require_breakout60: bool = True
    entry_require_ma_stack: bool = True   # ma60 > ma120
    entry_require_ma60_slope_pos: bool = True
    entry_mom20_pct_min: float = 0.70
    entry_fund_accel_pct_min: float = 0.60

    # Hold/Exit 조건 (상승 유지면 계속 홀드)
    exit_close_below_ma60_weeks: int = 2
    exit_ma60_slope_nonpos: bool = True

    # 스코어 가중치 (Entry 후보 랭킹)
    w_fund: float = 0.30
    w_accel: float = 0.20
    w_mom: float = 0.25
    w_vol: float = 0.10
    w_breakout: float = 0.05
    w_trend: float = 0.10  # ma60>ma120 + ma60_slope 가점


def _pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)


def _load_universe() -> pd.DataFrame:
    u = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    u["ticker"] = u["ticker"].astype(str).str.zfill(6)
    return u[["ticker", "name", "market", "mcap", "asof"]]


def _load_price_features(con: sqlite3.Connection, end: str) -> pd.DataFrame:
    q = f"""
    SELECT ticker, date, close, adv20, adv60, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope, ma120_slope
    FROM {TABLE_PRICE}
    WHERE date <= ?
    ORDER BY ticker, date
    """
    p = pd.read_sql_query(q, con, params=[end])
    p["ticker"] = p["ticker"].astype(str).str.zfill(6)
    p["date"] = p["date"].astype(str)
    return p


def _pick_latest_fund_asof(con: sqlite3.Connection, asof: str) -> pd.DataFrame:
    q = f"""
    SELECT date, ticker, available_from, growth_score, gs_delta_3m, fund_accel_score
    FROM {TABLE_FUND}
    WHERE available_from <= ?
    """
    f = pd.read_sql_query(q, con, params=[asof])
    if f.empty:
        return f

    f["ticker"] = f["ticker"].astype(str).str.zfill(6)
    f["_af"] = pd.to_datetime(f["available_from"], errors="coerce")
    f["_dt"] = pd.to_datetime(f["date"], errors="coerce")
    f = f.sort_values(["ticker", "_af", "_dt"]).groupby("ticker", as_index=False).tail(1)
    return f.drop(columns=["_af", "_dt"])


def _build_weekly_rebalance_dates(trading_dates: List[str], start: str, end: str, anchor_weekday: int) -> List[str]:
    """
    trading_dates: YYYY-MM-DD list (sorted)
    규칙: 매주 anchor_weekday(예: 수요일)에 해당하는 날짜를 찾고,
         그 날이 비거래일이면 '직전 거래일'로 이동.
    """
    # ✅ DatetimeIndex가 아니라 Series로 강제
    dts = pd.Series(pd.to_datetime(pd.Series(trading_dates).unique())).sort_values()
    dts = dts[(dts >= pd.to_datetime(start)) & (dts <= pd.to_datetime(end))]

    if len(dts) == 0:
        return []

    # 주 단위 앵커 날짜 생성 (캘린더 상)
    cal = pd.date_range(dts.min(), dts.max(), freq="D")
    anchors = cal[cal.weekday == anchor_weekday]

    rebals = []
    for a in anchors:
        # a 이전(포함) 마지막 거래일
        mask = dts <= a
        if mask.any():
            rebals.append(dts[mask].iloc[-1])

    rebals = pd.Series(rebals).dropna().drop_duplicates().sort_values()
    return rebals.dt.strftime("%Y-%m-%d").tolist()


def _score_candidates(df: pd.DataFrame, params: Params) -> pd.DataFrame:
    """
    df: universe + price(asof) + fund(asof) merged
    """
    d = df.copy()

    d["fund_level_pct"] = _pct_rank(d["growth_score"])
    d["fund_accel_pct"] = _pct_rank(d["fund_accel_score"])
    d["mom20_pct"] = _pct_rank(d["mom20"])
    d["vol_ratio_pct"] = _pct_rank(d["vol_ratio_20"])

    d["breakout60"] = d["breakout60"].fillna(0).astype(int)

    # 추세 가점
    trend_ok = (
        (d["ma60"] > d["ma120"]) &
        (d["ma60_slope"] > 0)
    )
    d["trend_bonus"] = trend_ok.astype(int)

    d["s3_score"] = (
        params.w_fund * d["fund_level_pct"].fillna(0)
        + params.w_accel * d["fund_accel_pct"].fillna(0)
        + params.w_mom * d["mom20_pct"].fillna(0)
        + params.w_vol * d["vol_ratio_pct"].fillna(0)
        + params.w_breakout * d["breakout60"]
        + params.w_trend * d["trend_bonus"]
    )
    return d


def _entry_filter(d: pd.DataFrame, params: Params) -> pd.Series:
    cond = pd.Series(True, index=d.index)

    if params.entry_require_breakout60:
        cond &= d["breakout60"].fillna(0).astype(int).eq(1)

    if params.entry_require_ma_stack:
        cond &= (d["ma60"] > d["ma120"])

    if params.entry_require_ma60_slope_pos:
        cond &= (d["ma60_slope"] > 0)

    # 퍼센타일 기준 컷
    d_scored = _score_candidates(d, params)
    cond &= (d_scored["mom20_pct"].fillna(0) >= params.entry_mom20_pct_min)
    cond &= (d_scored["fund_accel_pct"].fillna(0) >= params.entry_fund_accel_pct_min)

    return cond


def run(params: Params) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    u = _load_universe()

    con = sqlite3.connect(str(FEATURES_DB))
    try:
        p_all = _load_price_features(con, end=params.end)
    finally:
        con.close()

    if p_all.empty:
        raise RuntimeError("price features empty. Run build_s3_price_features_daily_v2.py first.")

    # 거래일 캘린더
    trading_dates = p_all["date"].dropna().unique().tolist()
    rebals = _build_weekly_rebalance_dates(trading_dates, params.start, params.end, params.weekly_anchor_weekday)
    if len(rebals) < 5:
        raise RuntimeError("rebalance dates too few. Check start/end and price coverage.")

    # ticker별 price features를 dict 형태로 빠르게 조회
    p_all["_dt"] = pd.to_datetime(p_all["date"], errors="coerce")
    p_all = p_all.sort_values(["ticker", "_dt"]).drop(columns=["_dt"])

    # 보유 상태
    holdings: Dict[str, Dict] = {}  # ticker -> {"below_ma60_streak": int, "entry_date": str}
    nav = 1.0
    nav_rows = []
    holdings_rows = []

    # rebalance loop
    for i in range(1, len(rebals)):
        prev_d = rebals[i - 1]
        d = rebals[i]

        # --- (1) 현재 날짜 기준 price snapshot (ticker별 최신 <= d)
        p = p_all[p_all["date"] <= d].copy()
        p["_dt"] = pd.to_datetime(p["date"], errors="coerce")
        p = p.sort_values(["ticker", "_dt"]).groupby("ticker", as_index=False).tail(1).drop(columns=["_dt"])

        # --- (2) 펀더멘털 snapshot (available_from<=d)
        con = sqlite3.connect(str(FEATURES_DB))
        try:
            f = _pick_latest_fund_asof(con, d)
        finally:
            con.close()

        # --- (3) universe merge + score
        df = u.merge(p, on="ticker", how="left").merge(f, on="ticker", how="left")
        df_scored = _score_candidates(df, params)

        # --- (4) EXIT: 보유 종목 점검 (상승 유지면 계속 홀드)
        to_sell = []
        for tkr in list(holdings.keys()):
            row = df_scored[df_scored["ticker"] == tkr]
            if row.empty:
                to_sell.append(tkr)
                continue

            r = row.iloc[0]
            close = r["close"]
            ma60 = r["ma60"]
            ma60_slope = r["ma60_slope"]

            # close < ma60 streak
            if pd.notna(close) and pd.notna(ma60) and close < ma60:
                holdings[tkr]["below_ma60_streak"] += 1
            else:
                holdings[tkr]["below_ma60_streak"] = 0

            exit_flag = False
            if holdings[tkr]["below_ma60_streak"] >= params.exit_close_below_ma60_weeks:
                exit_flag = True
            if params.exit_ma60_slope_nonpos and (pd.notna(ma60_slope) and ma60_slope <= 0):
                exit_flag = True

            if exit_flag:
                to_sell.append(tkr)

        for tkr in to_sell:
            holdings.pop(tkr, None)

        # --- (5) ENTRY: 부족분만큼 신규 편입
        need = params.top_n - len(holdings)
        if need > 0:
            cand = df_scored[~df_scored["ticker"].isin(holdings.keys())].copy()
            cond = _entry_filter(cand, params)
            cand = cand[cond].copy()
            cand = cand.sort_values("s3_score", ascending=False).head(need)

            for _, r in cand.iterrows():
                holdings[r["ticker"]] = {"below_ma60_streak": 0, "entry_date": d, "entry_price": float(r["close"]) if pd.notna(r.get("close", np.nan)) else np.nan}

        # 최소 보유수(너무 적으면 현금 비중 증가로 MDD 줄어듦) – PoC에서는 기록만
        cash_weight = 0.0
        if len(holdings) < params.min_holdings:
            cash_weight = 1.0 - (len(holdings) / max(params.min_holdings, 1))

        # --- (6) NAV 업데이트(주간)
        # equal-weight on held tickers (cash 비중은 수익률 0)
        held = list(holdings.keys())
        if len(held) > 0:
            prev_px = p_all[(p_all["date"] == prev_d) & (p_all["ticker"].isin(held))][["ticker", "close"]]
            curr_px = p_all[(p_all["date"] == d) & (p_all["ticker"].isin(held))][["ticker", "close"]]
            m = prev_px.merge(curr_px, on="ticker", suffixes=("_prev", "_curr"))

            if len(m) > 0:
                m["ret"] = m["close_curr"] / m["close_prev"] - 1.0
                port_ret = m["ret"].mean()
            else:
                port_ret = 0.0
        else:
            port_ret = 0.0

        nav = nav * (1.0 + (1.0 - cash_weight) * port_ret)

        nav_rows.append({"date": d, "nav": nav, "holdings": len(held), "cash_weight": cash_weight})

        # holdings snapshot 기록
        snap = df_scored[df_scored["ticker"].isin(held)].copy()
        snap["date"] = d
        snap = snap[["date","ticker","name","market","mcap","s3_score","close","ma60","ma120","ma60_slope","mom20","vol_ratio_20","breakout60","growth_score","fund_accel_score"]]
        holdings_rows.append(snap)

    nav_df = pd.DataFrame(nav_rows)
    hold_df = pd.concat(holdings_rows, ignore_index=True) if holdings_rows else pd.DataFrame()

    out_nav = OUTDIR / f"s3_nav_hold_top{params.top_n}_{params.start}_{params.end}.csv"
    out_hist = OUTDIR / f"s3_holdings_history_top{params.top_n}_{params.start}_{params.end}.csv"
    out_last = OUTDIR / f"s3_holdings_last_top{params.top_n}_{params.end}.csv"

    # --- normalize ticker as TEXT (keep leading zeros) ---
    for _df in (nav_df, hold_df):
        if "ticker" in _df.columns:
            _df["ticker"] = _df["ticker"].astype(str).str.zfill(6)

    nav_df.to_csv(out_nav, index=False, encoding="utf-8-sig")

    # history: quote all to reduce Excel auto-casting
    hold_df.to_csv(out_hist, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    # last snapshot + add per-ticker cumulative return since entry
    last_date = str(nav_df["date"].max())
    last_df = hold_df[hold_df["date"].astype(str) == last_date].drop_duplicates(["ticker"]).copy()
    last_df["ticker"] = last_df["ticker"].astype(str).str.zfill(6)

    # entry info from holdings dict (final portfolio)
    entry_date_map = {t: v.get("entry_date") for t, v in holdings.items()}
    entry_price_map = {t: v.get("entry_price") for t, v in holdings.items()}

    last_df["entry_date"] = last_df["ticker"].map(entry_date_map)
    last_df["entry_price"] = last_df["ticker"].map(entry_price_map)

    # cum return since entry: (last_close / entry_price) - 1
    last_df["cum_return_since_entry"] = np.where(
        pd.notna(last_df["entry_price"]) & (last_df["entry_price"] != 0),
        (last_df["close"].astype(float) / last_df["entry_price"].astype(float)) - 1.0,
        np.nan,
    )

    # write last (handle Excel lock)
    try:
        last_df.to_csv(out_last, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
        print(f"[OK] LAST  -> {out_last} (date={last_date}, rows={len(last_df)})")
    except PermissionError:
        ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        out_last_alt = OUTDIR / f"s3_holdings_last_top{params.top_n}_{params.end}_{ts}.csv"
        last_df.to_csv(out_last_alt, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
        print(f"[WARN] LAST file locked. Wrote -> {out_last_alt} (date={last_date}, rows={len(last_df)})")

    print(f"[OK] NAV   -> {out_nav}")
    print(f"[OK] HIST  -> {out_hist}")
    print(nav_df.tail(5).to_string(index=False))


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=Params.asof, help="signal ??? (YYYY-MM-DD)")
    ap.add_argument("--start", default=Params.start, help="???? ??? (YYYY-MM-DD)")
    ap.add_argument("--end", default=Params.end, help="???? ??? (YYYY-MM-DD)")
    ap.add_argument("--top-n", type=int, default=Params.top_n, help="?? ?? ?? ?")
    ap.add_argument("--min-holdings", type=int, default=Params.min_holdings, help="?? ?? ?? ?")
    ap.add_argument("--weekly-anchor-weekday", type=int, default=Params.weekly_anchor_weekday, help="?? ???? anchor weekday (0=Mon ... 2=Wed)")
    return ap


def _params_from_args(args: argparse.Namespace) -> Params:
    p = Params()
    p.asof = str(args.asof)
    p.start = str(args.start)
    p.end = str(args.end)
    p.top_n = int(args.top_n)
    p.min_holdings = int(args.min_holdings)
    p.weekly_anchor_weekday = int(args.weekly_anchor_weekday)
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    params = _params_from_args(args)
    run(params)
