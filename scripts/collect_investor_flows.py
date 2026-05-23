from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pykrx import stock

ROOT = Path(r"D:\Quant")
DEFAULT_DB = ROOT / r"data\db\ai_feature_ext.db"
DEFAULT_UNIVERSE_FILES = [
    ROOT / r"data\universe\universe_top200_kospi_latest.csv",
    ROOT / r"data\universe\universe_top200_kosdaq_latest.csv",
]

INVESTORS = ("개인", "외국인", "기관합계", "금융투자", "보험", "투신", "사모", "은행", "연기금", "기타법인")
MARKETS = ("KOSPI", "KOSDAQ")


def _normalize_date(value: str) -> str:
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return datetime.strptime(text, "%Y%m%d").strftime("%Y-%m-%d")


def _api_date(value: str) -> str:
    return _normalize_date(value).replace("-", "")


def _iter_weekdays(start: str, end: str) -> list[str]:
    start_dt = pd.Timestamp(_normalize_date(start))
    end_dt = pd.Timestamp(_normalize_date(end))
    if start_dt > end_dt:
        raise ValueError(f"start must be <= end: {start} > {end}")
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start_dt, end_dt, freq="B")]


def _norm_ticker(value: Any) -> str | None:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(6) if digits else None


def _load_universe(files: list[Path]) -> pd.DataFrame:
    frames = []
    for path in files:
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str)
        ticker_col = "ticker" if "ticker" in df.columns else "code" if "code" in df.columns else None
        if ticker_col is None:
            continue
        df["ticker"] = df[ticker_col].map(_norm_ticker)
        df["market"] = df.get("market", "").astype(str).str.upper()
        frames.append(df[["ticker", "market"]].dropna())
    if not frames:
        return pd.DataFrame(columns=["ticker", "market"])
    out = pd.concat(frames, ignore_index=True).drop_duplicates("ticker")
    out = out[out["market"].isin(MARKETS)]
    return out


def _safe_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text in {"", "-", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _pick_col(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {str(col).replace(" ", ""): str(col) for col in columns}
    for cand in candidates:
        key = cand.replace(" ", "")
        if key in normalized:
            return normalized[key]
    for col in columns:
        compact = str(col).replace(" ", "")
        if any(cand.replace(" ", "") in compact for cand in candidates):
            return str(col)
    return None


def _fetch_market_investor(start: str, end: str, market: str, investor: str) -> pd.DataFrame:
    raw = stock.get_market_net_purchases_of_equities_by_ticker(_api_date(start), _api_date(end), market=market, investor=investor)
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.reset_index()
    ticker_col = _pick_col(list(df.columns), ["티커", "종목코드", "ticker", "index"])
    name_col = _pick_col(list(df.columns), ["종목명", "name"])
    buy_vol_col = _pick_col(list(df.columns), ["매수거래량"])
    sell_vol_col = _pick_col(list(df.columns), ["매도거래량"])
    net_vol_col = _pick_col(list(df.columns), ["순매수거래량"])
    buy_val_col = _pick_col(list(df.columns), ["매수거래대금"])
    sell_val_col = _pick_col(list(df.columns), ["매도거래대금"])
    net_val_col = _pick_col(list(df.columns), ["순매수거래대금"])
    rows = []
    for row in df.to_dict(orient="records"):
        ticker = _norm_ticker(row.get(ticker_col)) if ticker_col else None
        if not ticker:
            continue
        rows.append(
            {
                "date": _normalize_date(end),
                "ticker": ticker,
                "name": None if not name_col else row.get(name_col),
                "market": market,
                "investor": investor,
                "buy_volume": _safe_number(row.get(buy_vol_col)) if buy_vol_col else None,
                "sell_volume": _safe_number(row.get(sell_vol_col)) if sell_vol_col else None,
                "net_volume": _safe_number(row.get(net_vol_col)) if net_vol_col else None,
                "buy_value": _safe_number(row.get(buy_val_col)) if buy_val_col else None,
                "sell_value": _safe_number(row.get(sell_val_col)) if sell_val_col else None,
                "net_value": _safe_number(row.get(net_val_col)) if net_val_col else None,
                "source": "pykrx_krx_investor_net_purchase",
                "collected_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
    return pd.DataFrame(rows)


def _init_db(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS investor_flows_daily (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            name TEXT,
            market TEXT NOT NULL,
            investor TEXT NOT NULL,
            buy_volume REAL,
            sell_volume REAL,
            net_volume REAL,
            buy_value REAL,
            sell_value REAL,
            net_value REAL,
            source TEXT,
            collected_at TEXT,
            PRIMARY KEY (date, ticker, investor)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_investor_flows_ticker_date ON investor_flows_daily(ticker, date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_investor_flows_date_investor ON investor_flows_daily(date, investor)")


def _upsert(con: sqlite3.Connection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = [
        "date",
        "ticker",
        "name",
        "market",
        "investor",
        "buy_volume",
        "sell_volume",
        "net_volume",
        "buy_value",
        "sell_value",
        "net_value",
        "source",
        "collected_at",
    ]
    sql = f"""
        INSERT INTO investor_flows_daily ({",".join(cols)})
        VALUES ({",".join(["?"] * len(cols))})
        ON CONFLICT(date, ticker, investor) DO UPDATE SET
            name=excluded.name,
            market=excluded.market,
            buy_volume=excluded.buy_volume,
            sell_volume=excluded.sell_volume,
            net_volume=excluded.net_volume,
            buy_value=excluded.buy_value,
            sell_value=excluded.sell_value,
            net_value=excluded.net_value,
            source=excluded.source,
            collected_at=excluded.collected_at
    """
    con.executemany(sql, [tuple(row[col] for col in cols) for row in df[cols].to_dict(orient="records")])
    return int(len(df))


def collect_investor_flows(
    *,
    start: str,
    end: str,
    db_path: Path,
    universe_files: list[Path],
    investors: tuple[str, ...] = INVESTORS,
) -> dict[str, Any]:
    universe = _load_universe(universe_files)
    wanted = set(universe["ticker"].tolist())
    frames = []
    errors: list[dict[str, str]] = []
    for bas_date in _iter_weekdays(start, end):
        for market in MARKETS:
            for investor in investors:
                try:
                    frame = _fetch_market_investor(bas_date, bas_date, market, investor)
                    if wanted and not frame.empty:
                        frame = frame[frame["ticker"].isin(wanted)].copy()
                    frames.append(frame)
                except Exception as exc:
                    errors.append({"date": bas_date, "market": market, "investor": investor, "error": str(exc)[:300]})
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as con:
        _init_db(con)
        saved = _upsert(con, out)
        con.commit()
    return {
        "status": "ok" if not errors else "partial",
        "start": _normalize_date(start),
        "end": _normalize_date(end),
        "rows": int(len(out)),
        "saved": saved,
        "universe_count": int(len(wanted)),
        "errors": errors,
        "db_path": str(db_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect KRX investor flow data for Quant AI features.")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--universe-file", action="append", default=None)
    parser.add_argument("--investor", action="append", default=None)
    args = parser.parse_args()
    files = [Path(p) for p in args.universe_file] if args.universe_file else DEFAULT_UNIVERSE_FILES
    investors = tuple(args.investor) if args.investor else INVESTORS
    result = collect_investor_flows(start=args.start, end=args.end, db_path=Path(args.db), universe_files=files, investors=investors)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
