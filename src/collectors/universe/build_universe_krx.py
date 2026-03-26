# build_universe_krx.py ver 2026-03-04_002  (prev 2026-03-04_001)
"""
KRX 유니버스(마스터) CSV 생성기

핵심 목표
- 마스터(universe_krx_...)에 mcap(시가총액)을 포함
- (옵션) price.db 기준 최근 N일(active-lag-days) 내 거래된 종목만 남긴 active 마스터를 생성
- TopN(예: Top200)은 "active 마스터"에서 mcap 내림차순으로 뽑아 항상 N개 유지

출력
- data/universe/universe_krx_<market>_<asof>.csv
- (옵션) data/universe/universe_krx_<market>_<asof>_active.csv
- (topn>0) data/universe/universe_top<topn>_<market>_<asof>.csv   # active 기준으로 생성

표준 컬럼
- ticker : 6자리 문자열
- name   : 종목명
- market : KOSPI/KOSDAQ/KONEX/ALL
- mcap   : 시가총액(정수)
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


def _find_project_root(start_path: Path) -> Path:
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    return start_path


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _yyyymmdd_to_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%d")


def _normalize_ticker_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .map(lambda x: x.zfill(6))
    )


def _coerce_int_series(s: pd.Series) -> pd.Series:
    return (
        pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")
        .fillna(0)
        .astype("int64")
    )


def _standardize_master(df: pd.DataFrame, market: str) -> pd.DataFrame:
    df = df.copy()

    if "ticker" not in df.columns:
        raise RuntimeError(f"master 표준화 실패: ticker 컬럼이 없습니다. cols={list(df.columns)}")

    df["ticker"] = _normalize_ticker_series(df["ticker"])
    df = df[df["ticker"].str.match(r"^\d{6}$", na=False)].copy()

    if "name" not in df.columns:
        df["name"] = ""

    if "market" not in df.columns:
        df["market"] = market
    df["market"] = df["market"].astype(str).str.strip().replace({"": market})

    if "mcap" in df.columns:
        df["mcap"] = _coerce_int_series(df["mcap"])
        df = df[df["mcap"] > 0].copy()
    else:
        df["mcap"] = 0

    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    return df[["ticker", "name", "market", "mcap"]]


# ----------------------------
# pykrx
# ----------------------------
def _resolve_trading_day_pykrx(market: str, asof_req: str, max_back_days: int) -> str:
    try:
        from pykrx import stock
    except Exception as e:
        raise RuntimeError(f"pykrx import 실패: {e}")

    d0 = _yyyymmdd_to_date(asof_req).date()
    for i in range(0, max_back_days + 1):
        d = (d0 - timedelta(days=i)).strftime("%Y%m%d")
        try:
            lst = stock.get_market_ticker_list(d, market=market)
            if isinstance(lst, (list, tuple)) and len(lst) > 0:
                return d
        except Exception:
            continue

    raise RuntimeError(
        f"[pykrx] get_market_ticker_list가 최근 {max_back_days}일 동안 비었습니다. "
        f"requested={asof_req}, market={market}"
    )


def _build_master_pykrx(market: str, asof_req: str, max_back_days: int) -> Tuple[pd.DataFrame, str]:
    from pykrx import stock

    asof = _resolve_trading_day_pykrx(market, asof_req, max_back_days)

    # ✅ 핵심: 해당 거래일의 '공식' 티커 리스트 확보 (이 리스트와 교집합으로만 유니버스 구성)
    valid_tickers = stock.get_market_ticker_list(asof, market=market)
    if not valid_tickers:
        raise RuntimeError(f"[pykrx] ticker_list EMPTY (asof={asof}, market={market})")
    valid_set = set(str(t).zfill(6) for t in valid_tickers)

    def _cap_to_df(cap_df: pd.DataFrame) -> pd.DataFrame:
        if cap_df is None or len(cap_df) == 0:
            return pd.DataFrame(columns=["ticker", "mcap"])
        cap_df = cap_df.reset_index()
        ticker_col = cap_df.columns[0]
        cap_df = cap_df.rename(columns={ticker_col: "ticker"})
        cap_df["ticker"] = _normalize_ticker_series(cap_df["ticker"])

        mcap_col = None
        for c in cap_df.columns:
            if "시가총액" in str(c):
                mcap_col = c
                break
        if mcap_col is None:
            return pd.DataFrame(columns=["ticker", "mcap"])

        out = cap_df[["ticker", mcap_col]].rename(columns={mcap_col: "mcap"}).copy()
        out["mcap"] = _coerce_int_series(out["mcap"])
        out = out[out["ticker"].str.match(r"^\d{6}$", na=False)].copy()
        out = out[out["mcap"] > 0].copy()

        # ✅ 핵심: cap에서 나온 ticker가 ticker_list에 없으면 제거 (000010/000090 방지)
        out = out[out["ticker"].isin(valid_set)].copy()

        return out

    # cap 우선 시도 (mcap 확보)
    cap = pd.DataFrame()
    try:
        cap = stock.get_market_cap(asof, market=market)
    except Exception:
        cap = pd.DataFrame()
    cap2 = _cap_to_df(cap)

    rows = []
    if len(cap2) > 0:
        tickers = cap2["ticker"].tolist()
        cap_map = dict(zip(cap2["ticker"], cap2["mcap"]))

        for t6 in tickers:
            try:
                nm = stock.get_market_ticker_name(t6)
            except Exception:
                nm = ""
            rows.append({"ticker": t6, "name": nm, "market": market, "mcap": int(cap_map.get(t6, 0))})

        df = pd.DataFrame(rows)
        return _standardize_master(df, market), asof

    # cap이 비었으면 ticker_list 기반으로 구성
    tickers = list(valid_set)

    # cap 재시도
    cap = pd.DataFrame()
    try:
        cap = stock.get_market_cap(asof, market=market)
    except Exception:
        cap = pd.DataFrame()
    cap2 = _cap_to_df(cap)
    cap_map = dict(zip(cap2["ticker"], cap2["mcap"])) if len(cap2) > 0 else {}

    for t6 in tickers:
        try:
            nm = stock.get_market_ticker_name(t6)
        except Exception:
            nm = ""
        rows.append({"ticker": t6, "name": nm, "market": market, "mcap": int(cap_map.get(t6, 0))})

    df = pd.DataFrame(rows)
    return _standardize_master(df, market), asof


# ----------------------------
# fdr
# ----------------------------
def _build_master_fdr(market: str, asof_req: str) -> Tuple[pd.DataFrame, str]:
    import FinanceDataReader as fdr

    lst = fdr.StockListing("KRX").copy()

    col_code = next((c for c in lst.columns if str(c).lower() in ["code", "symbol", "ticker"]), None)
    col_name = next((c for c in lst.columns if str(c).lower() in ["name", "company"]), None)
    col_market = next((c for c in lst.columns if str(c).lower() in ["market", "marketid"]), None)

    col_mcap = None
    for c in lst.columns:
        if str(c).lower() in ["marcap", "marketcap", "market_cap", "mcap"]:
            col_mcap = c
            break

    if col_code is None:
        raise RuntimeError(f"[fdr] code 컬럼을 찾지 못했습니다. cols={list(lst.columns)}")

    df = pd.DataFrame()
    df["ticker"] = lst[col_code].astype(str)
    df["name"] = lst[col_name].astype(str) if col_name else ""
    df["market"] = lst[col_market].astype(str) if col_market else market
    df["mcap"] = lst[col_mcap] if col_mcap else 0

    if market != "ALL":
        df = df[df["market"].astype(str).str.upper().str.contains(market, na=False)].copy()
        df["market"] = market

    return _standardize_master(df, market), asof_req


# ----------------------------
# cache
# ----------------------------
def _pick_latest_cache_file(out_dir: Path, market: str, asof: str) -> Optional[Path]:
    patt = f"universe_krx_{market.lower()}_*.csv"
    files = sorted(out_dir.glob(patt))
    if not files:
        return None

    req = asof
    candidates = []
    for f in files:
        parts = f.stem.split("_")
        if len(parts) < 4:
            continue
        file_asof = parts[-1]
        if file_asof.isdigit() and file_asof <= req:
            candidates.append((file_asof, f))

    if candidates:
        return sorted(candidates, key=lambda x: x[0])[-1][1]
    return files[-1]


def _build_master_cache(project_root: Path, market: str, asof_req: str) -> Tuple[pd.DataFrame, str]:
    out_dir = project_root / "data" / "universe"
    f = _pick_latest_cache_file(out_dir, market, asof_req)
    if not f:
        raise RuntimeError(f"[cache] universe_krx_{market.lower()}_*.csv 캐시가 없습니다. out_dir={out_dir}")
    df = pd.read_csv(f, dtype={"ticker": "string"})
    m = re.search(r"(\d{8})$", f.stem)
    used_asof = m.group(1) if m else asof_req
    return _standardize_master(df, market), used_asof


# ----------------------------
# active filter by price.db (optional)
# ----------------------------
def _detect_price_table_and_datecol(conn: sqlite3.Connection) -> Tuple[str, str]:
    # heuristics: table that has columns ticker + (date or trade_date)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    best = None
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        cols_l = [c.lower() for c in cols]
        if "ticker" in cols_l and ("date" in cols_l or "trade_date" in cols_l):
            date_col = "date" if "date" in cols_l else "trade_date"
            best = (t, date_col)
            break
    if not best:
        raise RuntimeError(f"price.db에서 (ticker,date) 형태의 테이블을 찾지 못했습니다. tables={tables}")
    return best


def _active_tickers_from_price_db(price_db: Path, cutoff_ymd: str) -> set[str]:
    """
    cutoff_ymd(YYYY-MM-DD) 이후로 한 건이라도 데이터가 있으면 active로 간주
    """
    conn = sqlite3.connect(str(price_db))
    try:
        table, date_col = _detect_price_table_and_datecol(conn)

        q = f"""
            SELECT ticker, MAX({date_col}) AS last_dt
            FROM {table}
            GROUP BY ticker
        """
        rows = conn.execute(q).fetchall()

        active = set()
        for t, last_dt in rows:
            if last_dt is None:
                continue
            s = str(last_dt).strip()
            if len(s) == 8 and s.isdigit():
                s = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
            if s >= cutoff_ymd:
                active.add(str(t).zfill(6))
        return active
    finally:
        conn.close()


def _build_topn(df_master: pd.DataFrame, market: str, topn: int) -> pd.DataFrame:
    if topn <= 0:
        return pd.DataFrame()
    if "mcap" not in df_master.columns or df_master["mcap"].max() <= 0:
        raise RuntimeError("TopN을 만들려면 master에 mcap(>0)이 필요합니다. (pykrx 또는 cache에 mcap 포함된 파일 필요)")
    top = df_master.sort_values("mcap", ascending=False).head(topn).copy()
    top["market"] = market
    return top[["ticker", "name", "market", "mcap"]].reset_index(drop=True)


@dataclass
class BuildResult:
    master: pd.DataFrame
    top: pd.DataFrame
    used_asof: str
    source: str


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topn", type=int, default=0)
    ap.add_argument("--market", type=str, default="KOSPI", help="ALL|KOSPI|KOSDAQ|KONEX")
    ap.add_argument("--asof", type=str, default=None, help="YYYYMMDD (미지정 시 오늘)")
    ap.add_argument("--max-back-days", type=int, default=60)
    ap.add_argument("--source", type=str, default="auto", choices=["auto", "pykrx", "fdr", "cache"])
    ap.add_argument("--on-fail", type=str, default="auto", choices=["auto", "cache", "fdr", "raise"],
                    help="source 지정 후 실패 시 동작 (auto=cache→fdr, cache=cache만, fdr=fdr만, raise=즉시 예외)")

    # NEW: active filter
    ap.add_argument("--price-db", type=str, default=None, help="예: D:\\Quant\\data\\db\\price.db")
    ap.add_argument("--active-lag-days", type=int, default=0, help="예: 7 (0이면 비활성화)")

    args = ap.parse_args()

    market = args.market.upper()
    asof_req = datetime.today().strftime("%Y%m%d") if args.asof is None else str(args.asof)

    project_root = _find_project_root(Path(__file__).resolve().parent)
    out_dir = project_root / "data" / "universe"
    _ensure_dir(out_dir)

    print(f"[INFO] project_root={project_root}")
    print(f"[INFO] market={market}, requested_asof={asof_req}, source={args.source}")

    def _try_pykrx():
        try:
            return _build_master_pykrx(market, asof_req, args.max_back_days)
        except Exception as e:
            print(f"[WARN] source=pykrx 실패: {e}")
            return None

    def _try_fdr():
        try:
            return _build_master_fdr(market, asof_req)
        except Exception as e:
            print(f"[WARN] source=fdr 실패: {e}")
            return None

    def _try_cache():
        try:
            return _build_master_cache(project_root, market, asof_req)
        except Exception as e:
            print(f"[WARN] source=cache 실패: {e}")
            return None


    def _apply_on_fail(primary: str):
        # primary 소스가 실패했을 때, args.on_fail 정책에 따라 대체 소스를 시도합니다.
        # - auto : cache -> fdr
        # - cache: cache
        # - fdr  : fdr
        # - raise: 즉시 예외
        if args.on_fail == "raise":
            raise RuntimeError(f"source={primary} 지정했지만 실패했습니다. (on-fail=raise)")

        if args.on_fail == "cache":
            out2 = _try_cache()
            if out2:
                m2, a2 = out2
                return m2, a2, "cache"
            raise RuntimeError(f"source={primary} 실패 후 cache도 실패했습니다.")

        if args.on_fail == "fdr":
            out2 = _try_fdr()
            if out2:
                m2, a2 = out2
                return m2, a2, "fdr"
            raise RuntimeError(f"source={primary} 실패 후 fdr도 실패했습니다.")

        # auto: cache -> fdr
        out2 = _try_cache()
        if out2:
            m2, a2 = out2
            return m2, a2, "cache"
        out3 = _try_fdr()
        if out3:
            m3, a3 = out3
            return m3, a3, "fdr"
        raise RuntimeError(f"source={primary} 실패 후 cache/fdr 모두 실패했습니다.")

    if args.source == "pykrx":
        out = _try_pykrx()
        if out:
            master, used_asof = out
            used_source = "pykrx"
        else:
            master, used_asof, used_source = _apply_on_fail("pykrx")

    elif args.source == "fdr":
        out = _try_fdr()
        if out:
            master, used_asof = out
            used_source = "fdr"
        else:
            master, used_asof, used_source = _apply_on_fail("fdr")

    elif args.source == "cache":
        out = _try_cache()
        if out:
            master, used_asof = out
            used_source = "cache"
        else:
            master, used_asof, used_source = _apply_on_fail("cache")

    else:
        # auto: pykrx -> cache -> fdr  (mcap 안정성을 위해 cache를 fdr보다 우선)
        out = _try_pykrx()
        if out:
            master, used_asof = out
            used_source = "pykrx"
        else:
            out = _try_cache()
            if out:
                master, used_asof = out
                used_source = "cache"
            else:
                out = _try_fdr()
                if out:
                    master, used_asof = out
                    used_source = "fdr"
                else:
                    raise RuntimeError("auto 소스: pykrx/cache/fdr 모두 실패했습니다.")


    # save master (1) 실제 used_asof 파일 (정확한 스냅샷 보존)
    out_master = out_dir / f"universe_krx_{market.lower()}_{used_asof}.csv"
    master.to_csv(out_master, index=False, encoding="utf-8-sig")
    print(f"[DONE] saved: {out_master} (n={len(master)})")

    # save master (2) 요청 asof 파일도 함께 생성(다운스트림 파이프라인 호환)
    # - 예: rebuild_mix_universe_and_refresh_dbs.py가 universe_top200_kospi_<requested>.csv 를 기대함
    # - pykrx 실패로 cache를 사용해 used_asof가 과거로 밀린 경우에도, 요청 asof 이름으로 '동일 내용'을 저장
    if used_asof != asof_req:
        out_master_req = out_dir / f"universe_krx_{market.lower()}_{asof_req}.csv"
        master.to_csv(out_master_req, index=False, encoding="utf-8-sig")
        print(f"[WARN] requested_asof alias saved: {out_master_req} (alias of used_asof={used_asof}, source={used_source})")

    # optional active filter
    master_for_topn = master
    if args.price_db and args.active_lag_days and args.active_lag_days > 0:
        price_db = Path(args.price_db)
        cutoff = (_yyyymmdd_to_date(used_asof) - timedelta(days=int(args.active_lag_days))).strftime("%Y-%m-%d")
        try:
            active = _active_tickers_from_price_db(price_db, cutoff)
            before = len(master_for_topn)
            master_for_topn = master_for_topn[master_for_topn["ticker"].isin(active)].copy().reset_index(drop=True)
            after = len(master_for_topn)

            out_active = out_dir / f"universe_krx_{market.lower()}_{used_asof}_active.csv"
            master_for_topn.to_csv(out_active, index=False, encoding="utf-8-sig")
            print(f"[INFO] active-filter(price.db) applied: before={before}, after={after}, cutoff={cutoff}")
            print(f"[DONE] saved: {out_active} (n={len(master_for_topn)})")

            # 요청 asof alias도 생성 (호환성)
            if used_asof != asof_req:
                out_active_req = out_dir / f"universe_krx_{market.lower()}_{asof_req}_active.csv"
                master_for_topn.to_csv(out_active_req, index=False, encoding="utf-8-sig")
                print(f"[WARN] requested_asof active alias saved: {out_active_req} (alias of used_asof={used_asof}, source={used_source})")
        except Exception as e:
            print(f"[WARN] active-filter(price.db) 실패: {e} (active-filter 미적용)")

    # TopN
    if args.topn and args.topn > 0:
        top = _build_topn(master_for_topn, market, args.topn)
        out_top = out_dir / f"universe_top{args.topn}_{market.lower()}_{used_asof}.csv"
        top.to_csv(out_top, index=False, encoding="utf-8-sig")
        print(f"[DONE] saved: {out_top} (n={len(top)})")

        # 요청 asof alias도 생성 (다운스트림이 requested_asof 파일을 기대)
        if used_asof != asof_req:
            out_top_req = out_dir / f"universe_top{args.topn}_{market.lower()}_{asof_req}.csv"
            top.to_csv(out_top_req, index=False, encoding="utf-8-sig")
            print(f"[WARN] requested_asof top alias saved: {out_top_req} (alias of used_asof={used_asof}, source={used_source})")
    else:
        print("[INFO] topn=0 이므로 TopN 파일은 생성하지 않습니다.")

    print(f"[INFO] used_asof={used_asof}, source={used_source}")


if __name__ == "__main__":
    main()
