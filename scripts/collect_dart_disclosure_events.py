from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(r"D:\Quant")
DART_DB = ROOT / r"data\db\dart_main.db"
DEFAULT_DB = ROOT / r"data\db\ai_feature_ext.db"
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"


def _normalize_date(value: str) -> str:
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def _display_date(value: str) -> str:
    text = _normalize_date(value)
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _load_dart_api_key() -> str:
    load_dotenv(ROOT / ".env")
    value = os.getenv("DART_API_KEY")
    if not value:
        raise RuntimeError("DART_API_KEY is not configured in environment or D:\\Quant\\.env")
    return value.strip()


def _load_listed_corp_map() -> pd.DataFrame:
    if not DART_DB.exists():
        return pd.DataFrame(columns=["corp_code", "ticker", "corp_name"])
    with sqlite3.connect(str(DART_DB)) as con:
        df = pd.read_sql_query(
            """
            SELECT corp_code, stock_code AS ticker, corp_name
            FROM dim_corp_listed
            WHERE stock_code IS NOT NULL
              AND TRIM(stock_code) <> ''
            """,
            con,
        )
    if df.empty:
        return df
    df["corp_code"] = df["corp_code"].astype(str).str.zfill(8)
    df["ticker"] = df["ticker"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    return df.dropna(subset=["ticker"]).drop_duplicates("corp_code")


def _event_category(report_name: str) -> str:
    text = str(report_name or "")
    if any(token in text for token in ("사업보고서", "반기보고서", "분기보고서")):
        return "periodic_report"
    if "실적" in text or "잠정" in text:
        return "earnings_guidance"
    if any(token in text for token in ("주요사항보고서", "타법인", "유상증자", "무상증자", "전환사채", "신주인수권", "합병", "분할")):
        return "major_event"
    if any(token in text for token in ("대량보유", "임원", "주식등의대량보유상황보고서", "소유상황")):
        return "ownership"
    if any(token in text for token in ("불성실공시", "거래정지", "관리종목", "상장폐지")):
        return "market_watch"
    return "other_disclosure"


def _fetch_page(api_key: str, start: str, end: str, page_no: int, page_count: int) -> dict[str, Any]:
    params = {
        "crtfc_key": api_key,
        "bgn_de": _normalize_date(start),
        "end_de": _normalize_date(end),
        "page_no": page_no,
        "page_count": page_count,
    }
    response = requests.get(DART_LIST_URL, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    status = str(payload.get("status", ""))
    if status not in {"000", "013"}:
        raise RuntimeError(f"OpenDART list error: status={status}, message={payload.get('message')}")
    return payload


def _fetch_disclosures(api_key: str, start: str, end: str, page_count: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        payload = _fetch_page(api_key, start, end, page, page_count)
        if str(payload.get("status")) == "013":
            break
        rows.extend(payload.get("list") or [])
        total_pages = int(payload.get("total_page") or 1)
        page += 1
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["corp_code"] = df["corp_code"].astype(str).str.zfill(8)
    df["ticker"] = df.get("stock_code", "").astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    df["event_date"] = df["rcept_dt"].astype(str).map(_display_date)
    df["event_category"] = df["report_nm"].map(_event_category)
    df["source"] = "opendart_list_api"
    df["collected_at"] = datetime.now().isoformat(timespec="seconds")
    return df


def _init_db(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS dart_disclosure_events (
            rcept_no TEXT PRIMARY KEY,
            event_date TEXT NOT NULL,
            corp_code TEXT,
            ticker TEXT,
            corp_name TEXT,
            report_name TEXT,
            event_category TEXT,
            filer_name TEXT,
            remark TEXT,
            source TEXT,
            collected_at TEXT
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_dart_events_ticker_date ON dart_disclosure_events(ticker, event_date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_dart_events_date_category ON dart_disclosure_events(event_date, event_category)")


def _upsert(con: sqlite3.Connection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = [
        "rcept_no",
        "event_date",
        "corp_code",
        "ticker",
        "corp_name",
        "report_name",
        "event_category",
        "filer_name",
        "remark",
        "source",
        "collected_at",
    ]
    out = pd.DataFrame(
        {
            "rcept_no": df.get("rcept_no"),
            "event_date": df.get("event_date"),
            "corp_code": df.get("corp_code"),
            "ticker": df.get("ticker"),
            "corp_name": df.get("corp_name"),
            "report_name": df.get("report_nm"),
            "event_category": df.get("event_category"),
            "filer_name": df.get("flr_nm"),
            "remark": df.get("rm"),
            "source": df.get("source"),
            "collected_at": df.get("collected_at"),
        }
    )
    out = out.dropna(subset=["rcept_no", "event_date"]).drop_duplicates("rcept_no")
    sql = f"""
        INSERT INTO dart_disclosure_events ({",".join(cols)})
        VALUES ({",".join(["?"] * len(cols))})
        ON CONFLICT(rcept_no) DO UPDATE SET
            event_date=excluded.event_date,
            corp_code=excluded.corp_code,
            ticker=excluded.ticker,
            corp_name=excluded.corp_name,
            report_name=excluded.report_name,
            event_category=excluded.event_category,
            filer_name=excluded.filer_name,
            remark=excluded.remark,
            source=excluded.source,
            collected_at=excluded.collected_at
    """
    con.executemany(sql, [tuple(row.get(col) for col in cols) for row in out[cols].to_dict(orient="records")])
    return int(len(out))


def collect_dart_disclosure_events(*, start: str, end: str, db_path: Path, universe_only: bool, page_count: int) -> dict[str, Any]:
    api_key = _load_dart_api_key()
    df = _fetch_disclosures(api_key, start, end, page_count)
    listed = _load_listed_corp_map()
    if not df.empty and not listed.empty:
        df = df.merge(listed[["corp_code", "ticker", "corp_name"]], on="corp_code", how="left", suffixes=("", "_listed"))
        df["ticker"] = df["ticker_listed"].fillna(df["ticker"])
        df["corp_name"] = df["corp_name_listed"].fillna(df.get("corp_name"))
        df = df.drop(columns=[col for col in ["ticker_listed", "corp_name_listed"] if col in df.columns])
    if universe_only:
        df = df[df["ticker"].notna() & df["ticker"].astype(str).str.match(r"^\d{6}$")].copy()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as con:
        _init_db(con)
        saved = _upsert(con, df)
        con.commit()
    category_counts = df["event_category"].value_counts().to_dict() if not df.empty else {}
    return {
        "status": "ok",
        "start": _display_date(start),
        "end": _display_date(end),
        "rows": int(len(df)),
        "saved": saved,
        "category_counts": category_counts,
        "db_path": str(db_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect OpenDART disclosure events for Quant AI features.")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--all-corps", action="store_true", help="Keep non-listed/non-universe disclosures too")
    parser.add_argument("--page-count", type=int, default=100)
    args = parser.parse_args()
    result = collect_dart_disclosure_events(
        start=args.start,
        end=args.end,
        db_path=Path(args.db),
        universe_only=not args.all_corps,
        page_count=int(args.page_count),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
