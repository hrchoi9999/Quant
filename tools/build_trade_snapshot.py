# build_trade_snapshot.py ver 2026-02-03_001
"""
목적
- holdings CSV(리밸런싱 시점의 목표 비중) + price.db(가격)로
  '종목별 보유기간 수익률(진입~청산)'을 복원해서 snapshot(=trade history) CSV를 생성합니다.
- 요구사항:
  1) 보유중이면 산출시점(end_date) 기준으로 미실현 수익률 산출
  2) 매도했으면 매도시점 기준(청산일 가격)으로 실현 수익률 산출
  3) 결과를 snapshot CSV에 포함(별도 파일로 저장하지만, 원하시면 기존 snapshot을 이 파일로 교체)

입력
- --holdings: regime_bt_holdings_*.csv (필수)
  * 필수 컬럼: rebalance_date, ticker, weight
- --price-db / --price-table: 가격 DB/테이블 (필수)
  * 필수 컬럼: date, ticker, close
- --end-date: 없으면 holdings의 마지막 rebalance_date 또는 price 마지막 date를 사용

출력
- *_trade_snapshot.csv : ticker별 트레이드(진입/청산) 행 + 마지막 미청산 행

주의
- 이 스크립트는 '리밸런싱 시점'에 포지션이 열리고/닫힌 것으로 가정합니다.
  (일중 체결/슬리피지/부분체결 등은 여기서 고려하지 않습니다.)
"""
from __future__ import annotations
import argparse
import sqlite3
import pandas as pd
import numpy as np

def read_prices(price_db: str, price_table: str) -> pd.DataFrame:
    con=sqlite3.connect(price_db)
    q=f"SELECT date, ticker, close FROM {price_table}"
    df=pd.read_sql_query(q, con)
    con.close()
    df["date"]=pd.to_datetime(df["date"])
    df["ticker"]=df["ticker"].astype(str)
    df["close"]=pd.to_numeric(df["close"], errors="coerce")
    df=df.dropna(subset=["date","ticker","close"])
    return df

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--holdings", required=True)
    ap.add_argument("--price-db", required=True)
    ap.add_argument("--price-table", default="prices_daily")
    ap.add_argument("--out", default="")
    ap.add_argument("--end-date", default="")
    args=ap.parse_args()

    h=pd.read_csv(args.holdings)
    if "rebalance_date" not in h.columns or "ticker" not in h.columns or "weight" not in h.columns:
        raise SystemExit("holdings must have rebalance_date,ticker,weight")
    h["rebalance_date"]=pd.to_datetime(h["rebalance_date"])
    h["ticker"]=h["ticker"].astype(str)
    h["weight"]=pd.to_numeric(h["weight"], errors="coerce").fillna(0.0)

    # 리밸런스별 목표비중 (ticker NaN 행은 제거)
    h=h[h["ticker"].notna()].copy()
    # weight>0 인 것만 포지션으로 간주
    h["in_pos"]=h["weight"]>0

    prices=read_prices(args.price_db, args.price_table)
    # 가격 pivot for fast lookup
    px = prices.pivot(index="date", columns="ticker", values="close").sort_index()

    # end_date
    if args.end_date:
        end_date=pd.to_datetime(args.end_date)
    else:
        end_date=max(h["rebalance_date"].max(), px.index.max())
    # 리밸런스 캘린더
    rebal_dates = sorted(h["rebalance_date"].unique())
    rebal_dates = [d for d in rebal_dates if d<=end_date]
    if not rebal_dates:
        raise SystemExit("no rebalance dates")

    # 상태: ticker -> entry_date, entry_price
    pos={}
    trades=[]

    def get_price(d, t):
        if d not in px.index or t not in px.columns:
            return np.nan
        return float(px.loc[d, t])

    # 리밸런스 순회
    prev_set=set()
    for i, d in enumerate(rebal_dates):
        cur = h[h["rebalance_date"]==d]
        cur_set=set(cur[cur["in_pos"]]["ticker"].tolist())

        # close positions: prev - cur
        to_close = prev_set - cur_set
        for t in sorted(to_close):
            if t not in pos:  # 방어
                continue
            entry_d, entry_px = pos.pop(t)
            exit_px = get_price(d, t)
            if np.isnan(entry_px) or np.isnan(exit_px):
                ret=np.nan
            else:
                ret=exit_px/entry_px - 1.0
            trades.append({
                "ticker": t,
                "status": "CLOSED",
                "entry_date": entry_d.date().isoformat(),
                "exit_date": d.date().isoformat(),
                "entry_price": entry_px,
                "exit_price": exit_px,
                "holding_days": int((d-entry_d).days),
                "return": ret,
            })

        # open positions: cur - prev
        to_open = cur_set - prev_set
        for t in sorted(to_open):
            entry_px = get_price(d, t)
            pos[t]=(d, entry_px)

        prev_set=cur_set

    # 아직 열려있는 포지션은 end_date로 평가
    for t,(entry_d, entry_px) in sorted(pos.items()):
        exit_px=get_price(end_date, t)
        if np.isnan(entry_px) or np.isnan(exit_px):
            ret=np.nan
        else:
            ret=exit_px/entry_px - 1.0
        trades.append({
            "ticker": t,
            "status": "OPEN",
            "entry_date": entry_d.date().isoformat(),
            "exit_date": end_date.date().isoformat(),
            "entry_price": entry_px,
            "exit_price": exit_px,
            "holding_days": int((end_date-entry_d).days),
            "return": ret,
        })

    out=pd.DataFrame(trades).sort_values(["status","ticker","entry_date"])
    if not args.out:
        args.out=args.holdings.replace(".csv","__trade_snapshot.csv")
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    print("[SAVE]", args.out)
    print(out.head(20).to_string(index=False))
    print("rows=",len(out), "open=",int((out.status=="OPEN").sum()), "closed=",int((out.status=="CLOSED").sum()))

if __name__=="__main__":
    main()
