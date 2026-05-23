from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(r"D:\Quant")
DEFAULT_DB = ROOT / r"data\db\ai_feature_ext.db"
DEFAULT_UNIVERSE_FILE = ROOT / r"data\universe\universe_mix_top400_latest.csv"
NAVER_URL = "https://finance.naver.com/item/frgn.naver"


def _norm_ticker(value: Any) -> str | None:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(6) if digits else None


def _safe_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if text in {"", "-", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _load_universe(path: Path, limit: int | None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    ticker_col = "ticker" if "ticker" in df.columns else "code" if "code" in df.columns else None
    if ticker_col is None:
        raise ValueError(f"ticker column not found: {path}")
    name_col = "name" if "name" in df.columns else "display_name" if "display_name" in df.columns else None
    out = pd.DataFrame(
        {
            "ticker": df[ticker_col].map(_norm_ticker),
            "name": df[name_col] if name_col else None,
        }
    ).dropna(subset=["ticker"])
    out = out.drop_duplicates("ticker").reset_index(drop=True)
    if limit:
        out = out.head(limit)
    return out


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join([str(x) for x in col if str(x) != "nan"]).strip("_") for col in df.columns]
    else:
        df.columns = [str(col) for col in df.columns]
    return df


def _pick_flow_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    for table in tables:
        df = _flatten_columns(table.copy())
        compact_cols = "".join(df.columns)
        if "날짜" in compact_cols and "기관" in compact_cols and "외국인" in compact_cols:
            return df
    return pd.DataFrame()


def _pick_col(columns: list[str], tokens: list[str]) -> str | None:
    for col in columns:
        compact = str(col).replace(" ", "")
        if all(token in compact for token in tokens):
            return str(col)
    return None


def _fetch_ticker_page(ticker: str, page: int, session: requests.Session) -> pd.DataFrame:
    response = session.get(
        NAVER_URL,
        params={"code": ticker, "page": page},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    tables = pd.read_html(response.content, encoding="euc-kr", flavor="lxml")
    return _pick_flow_table(tables)


def _parse_ticker_flows(ticker: str, name: str | None, pages: int, session: requests.Session, sleep: float) -> pd.DataFrame:
    frames = []
    for page in range(1, pages + 1):
        table = _fetch_ticker_page(ticker, page, session)
        if table.empty:
            continue
        frames.append(table)
        if sleep > 0:
            time.sleep(sleep)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    date_col = _pick_col(list(df.columns), ["날짜"])
    close_col = _pick_col(list(df.columns), ["종가"])
    volume_col = _pick_col(list(df.columns), ["거래량"])
    inst_col = _pick_col(list(df.columns), ["기관", "순매매량"])
    foreign_col = _pick_col(list(df.columns), ["외국인", "순매매량"])
    holding_col = _pick_col(list(df.columns), ["외국인", "보유율"])
    if not date_col or not inst_col or not foreign_col:
        return pd.DataFrame()

    rows = []
    for row in df.to_dict(orient="records"):
        date_text = str(row.get(date_col) or "").strip()
        if not date_text or date_text == "nan":
            continue
        try:
            trade_date = datetime.strptime(date_text, "%Y.%m.%d").strftime("%Y-%m-%d")
        except ValueError:
            continue
        close = _safe_number(row.get(close_col)) if close_col else None
        volume = _safe_number(row.get(volume_col)) if volume_col else None
        for investor, col in (("기관합계", inst_col), ("외국인", foreign_col)):
            net_volume = _safe_number(row.get(col))
            rows.append(
                {
                    "date": trade_date,
                    "ticker": ticker,
                    "name": name,
                    "market": "KR_STOCK",
                    "investor": investor,
                    "buy_volume": None,
                    "sell_volume": None,
                    "net_volume": net_volume,
                    "buy_value": None,
                    "sell_value": None,
                    "net_value": None if net_volume is None or close is None else net_volume * close,
                    "source": "naver_finance_frgn_derived_value",
                    "collected_at": datetime.now().isoformat(timespec="seconds"),
                    "close": close,
                    "volume": volume,
                    "foreign_holding_rate": _safe_number(row.get(holding_col)) if holding_col else None,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.drop_duplicates(["date", "ticker", "investor"])


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
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS investor_flows_naver_meta_daily (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            close REAL,
            volume REAL,
            foreign_holding_rate REAL,
            source TEXT,
            collected_at TEXT,
            PRIMARY KEY (date, ticker)
        )
        """
    )


def _upsert(con: sqlite3.Connection, df: pd.DataFrame) -> tuple[int, int]:
    if df.empty:
        return 0, 0
    flow_cols = [
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
    flow_sql = f"""
        INSERT INTO investor_flows_daily ({",".join(flow_cols)})
        VALUES ({",".join(["?"] * len(flow_cols))})
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
    con.executemany(flow_sql, [tuple(row[col] for col in flow_cols) for row in df[flow_cols].to_dict(orient="records")])

    meta_cols = ["date", "ticker", "close", "volume", "foreign_holding_rate", "source", "collected_at"]
    meta = df[meta_cols].drop_duplicates(["date", "ticker"])
    meta_sql = f"""
        INSERT INTO investor_flows_naver_meta_daily ({",".join(meta_cols)})
        VALUES ({",".join(["?"] * len(meta_cols))})
        ON CONFLICT(date, ticker) DO UPDATE SET
            close=excluded.close,
            volume=excluded.volume,
            foreign_holding_rate=excluded.foreign_holding_rate,
            source=excluded.source,
            collected_at=excluded.collected_at
    """
    con.executemany(meta_sql, [tuple(row[col] for col in meta_cols) for row in meta[meta_cols].to_dict(orient="records")])
    return int(len(df)), int(len(meta))


def collect_naver_investor_flows(*, universe_file: Path, db_path: Path, pages: int, limit: int | None, sleep: float) -> dict[str, Any]:
    universe = _load_universe(universe_file, limit)
    frames = []
    errors = []
    session = requests.Session()
    for row in universe.to_dict(orient="records"):
        ticker = row["ticker"]
        try:
            frame = _parse_ticker_flows(ticker, row.get("name"), pages, session, sleep)
            frames.append(frame)
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)[:300]})
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as con:
        _init_db(con)
        saved_flows, saved_meta = _upsert(con, out)
        con.commit()
    return {
        "status": "ok" if not errors else "partial",
        "universe_count": int(len(universe)),
        "rows": int(len(out)),
        "saved_flows": saved_flows,
        "saved_meta": saved_meta,
        "pages": pages,
        "errors": errors[:20],
        "error_count": len(errors),
        "db_path": str(db_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect temporary Naver Finance investor flow data.")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE_FILE))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()
    result = collect_naver_investor_flows(
        universe_file=Path(args.universe_file),
        db_path=Path(args.db),
        pages=max(1, int(args.pages)),
        limit=args.limit,
        sleep=max(0.0, float(args.sleep)),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
