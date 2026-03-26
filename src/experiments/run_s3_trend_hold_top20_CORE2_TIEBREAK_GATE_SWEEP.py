# run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP_2026-03-03_001.py
"""
S3 core2 + Market Gate(Breadth) SWEEP version

원본 기반:
- run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_2026-02-27_001.py

변경점(핵심):
1) CLI(argparse) 지원: breadth open/close(히스테리시스), gate 정의(use_slope), entry 컷, tag 등
2) 게이트 상태를 주간 루프에서 "상태 머신"으로 유지(채터링 방지)
3) 출력 파일에 tag를 포함해 스윕 결과가 서로 덮어쓰지 않도록 함
4) NAV에 exposure(=1-cash_weight) 컬럼 추가

주의:
- S2 환경/DB/파일은 건드리지 않습니다. (S3 전용: data\\db_s3\\features_s3.db 사용)
"""
import argparse
import csv
from datetime import date
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

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
    # run range
    asof: str = TODAY_STR
    start: str = "2013-10-14"
    end: str = TODAY_STR
    top_n: int = 20

    weekly_anchor_weekday: int = 2  # 0=Mon ... 2=Wed
    min_holdings: int = 10

    # =========================
    # Market Gate (Breadth)
    # =========================
    market_gate_enabled: bool = True

    # 히스테리시스: CLOSED -> OPEN / OPEN -> CLOSED
    market_gate_open_th: float = 0.55
    market_gate_close_th: float = 0.55  # open_th == close_th => 단일 임계값

    # breadth 정의 옵션
    market_gate_use_ma_stack: bool = True     # ma60 > ma120
    market_gate_use_slope_pos: bool = True    # ma60_slope > 0

    # =========================
    # Entry 필터
    # =========================
    entry_require_ma_stack: bool = True
    entry_require_ma60_slope_pos: bool = True
    entry_require_breakout60: bool = False
    entry_mom20_pct_min: float = 0.70
    entry_vol_ratio_pct_min: float = 0.60

    # =========================
    # Hold/Exit
    # =========================
    exit_close_below_ma60_weeks: int = 2
    exit_ma60_slope_nonpos: bool = True
    exit_ma60_slope_nonpos_weeks: int = 2

    # =========================
    # Score weights
    # =========================
    w_mom: float = 0.60
    w_vol: float = 0.40
    tie_w_fund_level: float = 0.002
    tie_w_fund_accel: float = 0.001

    # output tag
    tag: str = "core2_gate"


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
    dts = pd.Series(pd.to_datetime(pd.Series(trading_dates).unique())).sort_values()
    dts = dts[(dts >= pd.to_datetime(start)) & (dts <= pd.to_datetime(end))]
    if len(dts) == 0:
        return []

    cal = pd.date_range(dts.min(), dts.max(), freq="D")
    anchors = cal[cal.weekday == anchor_weekday]

    rebals = []
    for a in anchors:
        mask = dts <= a
        if mask.any():
            rebals.append(dts[mask].iloc[-1])

    rebals = pd.Series(rebals).dropna().drop_duplicates().sort_values()
    return rebals.dt.strftime("%Y-%m-%d").tolist()


def _score_candidates(df: pd.DataFrame, params: Params) -> pd.DataFrame:
    d = df.copy()
    d["mom20_pct"] = _pct_rank(d["mom20"])
    d["vol_ratio_pct"] = _pct_rank(d["vol_ratio_20"])
    d["fund_level_pct"] = _pct_rank(d["growth_score"])
    d["fund_accel_pct"] = _pct_rank(d["fund_accel_score"])
    d["breakout60"] = d["breakout60"].fillna(0).astype(int)

    d["core_score"] = (
        params.w_mom * d["mom20_pct"].fillna(0)
        + params.w_vol * d["vol_ratio_pct"].fillna(0)
    )
    d["tie_score"] = (
        params.tie_w_fund_level * d["fund_level_pct"].fillna(0.5)
        + params.tie_w_fund_accel * d["fund_accel_pct"].fillna(0.5)
    )
    d["s3_score"] = d["core_score"] + d["tie_score"]
    return d


def _entry_filter(d: pd.DataFrame, params: Params) -> pd.Series:
    cond = pd.Series(True, index=d.index)

    if params.entry_require_ma_stack:
        cond &= (d["ma60"] > d["ma120"])
    if params.entry_require_ma60_slope_pos:
        cond &= (d["ma60_slope"] > 0)
    if params.entry_require_breakout60:
        cond &= d["breakout60"].fillna(0).astype(int).eq(1)

    d_scored = _score_candidates(d, params)
    cond &= (d_scored["mom20_pct"].fillna(0) >= params.entry_mom20_pct_min)
    cond &= (d_scored["vol_ratio_pct"].fillna(0) >= params.entry_vol_ratio_pct_min)
    return cond


def _calc_market_breadth(df_scored: pd.DataFrame, params: Params) -> float:
    need_cols = ["ma60", "ma120", "ma60_slope"]
    ok = df_scored[need_cols].notna().all(axis=1)
    if ok.sum() == 0:
        return float("nan")

    cond = pd.Series(True, index=df_scored.index)
    if params.market_gate_use_ma_stack:
        cond &= (df_scored["ma60"] > df_scored["ma120"])
    if params.market_gate_use_slope_pos:
        cond &= (df_scored["ma60_slope"] > 0)

    return float((cond & ok).sum() / ok.sum())


def _gate_state_update(prev_open: bool, breadth: float, open_th: float, close_th: float) -> bool:
    if not np.isfinite(breadth):
        return False
    if prev_open:
        return False if breadth <= close_th else True
    return True if breadth >= open_th else False


def run(params: Params) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    u = _load_universe()

    con = sqlite3.connect(str(FEATURES_DB))
    try:
        p_all = _load_price_features(con, end=params.end)
    finally:
        con.close()

    if p_all.empty:
        raise RuntimeError("price features empty. Run build_s3_price_features_daily.py first.")

    trading_dates = p_all["date"].dropna().unique().tolist()
    rebals = _build_weekly_rebalance_dates(trading_dates, params.start, params.end, params.weekly_anchor_weekday)
    if len(rebals) < 5:
        raise RuntimeError("rebalance dates too few. Check start/end and price coverage.")

    p_all["_dt"] = pd.to_datetime(p_all["date"], errors="coerce")
    p_all = p_all.sort_values(["ticker", "_dt"]).drop(columns=["_dt"])

    holdings: Dict[str, Dict] = {}
    nav = 1.0
    nav_rows = []
    holdings_rows = []

    gate_open = True  # 초기 OPEN (초기 데이터 부족으로 과도 CLOSE 방지)

    for i in range(1, len(rebals)):
        prev_d = rebals[i - 1]
        d = rebals[i]

        p = p_all[p_all["date"] <= d].copy()
        p["_dt"] = pd.to_datetime(p["date"], errors="coerce")
        p = p.sort_values(["ticker", "_dt"]).groupby("ticker", as_index=False).tail(1).drop(columns=["_dt"])

        con = sqlite3.connect(str(FEATURES_DB))
        try:
            f = _pick_latest_fund_asof(con, d)
        finally:
            con.close()

        df = u.merge(p, on="ticker", how="left").merge(f, on="ticker", how="left")
        df_scored = _score_candidates(df, params)

        breadth = _calc_market_breadth(df_scored, params)
        if params.market_gate_enabled:
            gate_open = _gate_state_update(gate_open, breadth, params.market_gate_open_th, params.market_gate_close_th)
        else:
            gate_open = True

        # EXIT
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

            if pd.notna(close) and pd.notna(ma60) and close < ma60:
                holdings[tkr]["below_ma60_streak"] += 1
            else:
                holdings[tkr]["below_ma60_streak"] = 0

            if pd.notna(ma60_slope) and ma60_slope <= 0:
                holdings[tkr]["slope_nonpos_streak"] += 1
            else:
                holdings[tkr]["slope_nonpos_streak"] = 0

            exit_flag = False
            if holdings[tkr]["below_ma60_streak"] >= params.exit_close_below_ma60_weeks:
                exit_flag = True
            if params.exit_ma60_slope_nonpos and holdings[tkr]["slope_nonpos_streak"] >= params.exit_ma60_slope_nonpos_weeks:
                exit_flag = True

            if exit_flag:
                to_sell.append(tkr)

        for tkr in to_sell:
            holdings.pop(tkr, None)

        # ENTRY (게이트 OPEN일 때만)
        need = params.top_n - len(holdings)
        if need > 0 and gate_open:
            cand = df_scored[~df_scored["ticker"].isin(holdings.keys())].copy()
            cond = _entry_filter(cand, params)
            cand = cand[cond].copy()
            cand = cand.sort_values("s3_score", ascending=False).head(need)

            for _, r in cand.iterrows():
                holdings[r["ticker"]] = {
                    "below_ma60_streak": 0,
                    "slope_nonpos_streak": 0,
                    "entry_date": d,
                    "entry_price": float(r["close"]) if pd.notna(r.get("close", np.nan)) else np.nan,
                }

        # cash/exposure
        cash_weight = 0.0
        if len(holdings) < params.min_holdings:
            cash_weight = 1.0 - (len(holdings) / max(params.min_holdings, 1))
        exposure = 1.0 - cash_weight

        # NAV (주간)
        held = list(holdings.keys())
        port_ret = 0.0
        if len(held) > 0:
            prev_px = p_all[(p_all["date"] == prev_d) & (p_all["ticker"].isin(held))][["ticker", "close"]]
            curr_px = p_all[(p_all["date"] == d) & (p_all["ticker"].isin(held))][["ticker", "close"]]
            m = prev_px.merge(curr_px, on="ticker", suffixes=("_prev", "_curr"))
            if len(m) > 0:
                m["ret"] = m["close_curr"] / m["close_prev"] - 1.0
                port_ret = float(m["ret"].mean())

        nav = nav * (1.0 + exposure * port_ret)

        nav_rows.append(
            {
                "date": d,
                "nav": nav,
                "holdings": len(held),
                "cash_weight": cash_weight,
                "exposure": exposure,
                "gate_open": int(gate_open),
                "gate_breadth": breadth,
                "gate_open_th": params.market_gate_open_th,
                "gate_close_th": params.market_gate_close_th,
                "gate_use_slope": int(params.market_gate_use_slope_pos),
            }
        )

        snap = df_scored[df_scored["ticker"].isin(held)].copy()
        snap["date"] = d
        snap = snap[
            [
                "date","ticker","name","market","mcap",
                "s3_score","core_score","tie_score",
                "mom20","mom20_pct","vol_ratio_20","vol_ratio_pct",
                "breakout60","ma60","ma120","ma60_slope",
                "growth_score","fund_level_pct","fund_accel_score","fund_accel_pct",
                "close"
            ]
        ]
        holdings_rows.append(snap)

    nav_df = pd.DataFrame(nav_rows)
    hold_df = pd.concat(holdings_rows, ignore_index=True) if holdings_rows else pd.DataFrame()

    tag = params.tag.strip() if params.tag else "core2_gate"
    out_nav = OUTDIR / f"s3_nav_hold_top{params.top_n}_{tag}_{params.start}_{params.end}.csv"
    out_hist = OUTDIR / f"s3_holdings_history_top{params.top_n}_{tag}_{params.start}_{params.end}.csv"
    out_last = OUTDIR / f"s3_holdings_last_top{params.top_n}_{tag}_{params.end}.csv"

    for _df in (nav_df, hold_df):
        if "ticker" in _df.columns:
            _df["ticker"] = _df["ticker"].astype(str).str.zfill(6)

    nav_df.to_csv(out_nav, index=False, encoding="utf-8-sig")
    hold_df.to_csv(out_hist, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    # last snapshot + per-ticker cumulative return since entry
    last_date = str(nav_df["date"].max())
    last_df = hold_df[hold_df["date"].astype(str) == last_date].drop_duplicates(["ticker"]).copy()
    last_df["ticker"] = last_df["ticker"].astype(str).str.zfill(6)

    entry_date_map = {t: v.get("entry_date") for t, v in holdings.items()}
    entry_price_map = {t: v.get("entry_price") for t, v in holdings.items()}

    last_df["entry_date"] = last_df["ticker"].map(entry_date_map)
    last_df["entry_price"] = last_df["ticker"].map(entry_price_map)
    last_df["cum_return_since_entry"] = np.where(
        pd.notna(last_df["entry_price"]) & (last_df["entry_price"] != 0),
        (last_df["close"].astype(float) / last_df["entry_price"].astype(float)) - 1.0,
        np.nan,
    )

    try:
        last_df.to_csv(out_last, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
        print(f"[OK] LAST  -> {out_last} (date={last_date}, rows={len(last_df)})")
    except PermissionError:
        ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        out_last_alt = OUTDIR / f"s3_holdings_last_top{params.top_n}_{tag}_{params.end}_{ts}.csv"
        last_df.to_csv(out_last_alt, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
        print(f"[WARN] LAST file locked. Wrote -> {out_last_alt} (date={last_date}, rows={len(last_df)})")

    print(f"[OK] NAV   -> {out_nav}")
    print(f"[OK] HIST  -> {out_hist}")
    print(nav_df.tail(5).to_string(index=False))


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=Params.asof)
    ap.add_argument("--start", default=Params.start)
    ap.add_argument("--end", default=Params.end)
    ap.add_argument("--top-n", type=int, default=Params.top_n)
    ap.add_argument("--tag", default=Params.tag)

    ap.add_argument("--gate-enabled", type=int, default=1)
    ap.add_argument("--gate-open-th", type=float, default=Params.market_gate_open_th)
    ap.add_argument("--gate-close-th", type=float, default=Params.market_gate_close_th)
    ap.add_argument("--gate-use-slope", type=int, default=1)
    ap.add_argument("--gate-use-ma-stack", type=int, default=1)
    ap.add_argument("--min-holdings", type=int, default=Params.min_holdings)

    ap.add_argument("--entry-mom-pct-min", type=float, default=Params.entry_mom20_pct_min)
    ap.add_argument("--entry-vol-pct-min", type=float, default=Params.entry_vol_ratio_pct_min)
    return ap


def _params_from_args(args: argparse.Namespace) -> Params:
    p = Params()
    p.asof = args.asof
    p.start = args.start
    p.end = args.end
    p.top_n = int(args.top_n)
    p.tag = str(args.tag)

    p.market_gate_enabled = bool(int(args.gate_enabled))
    p.market_gate_open_th = float(args.gate_open_th)
    p.market_gate_close_th = float(args.gate_close_th)
    p.market_gate_use_slope_pos = bool(int(args.gate_use_slope))
    p.market_gate_use_ma_stack = bool(int(args.gate_use_ma_stack))

    p.min_holdings = int(args.min_holdings)

    p.entry_mom20_pct_min = float(args.entry_mom_pct_min)
    p.entry_vol_ratio_pct_min = float(args.entry_vol_pct_min)
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    params = _params_from_args(args)
    run(params)
