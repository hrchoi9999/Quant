from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from scripts.fetch_krx_etf_distributions import _create_table, _upsert_events
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT_CANDIDATE = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / "scripts").exists()), CURRENT.parent)
    if str(ROOT_CANDIDATE) not in sys.path:
        sys.path.insert(0, str(ROOT_CANDIDATE))
    from scripts.fetch_krx_etf_distributions import _create_table, _upsert_events


ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
TABLE_NAME = "etf_distributions"

KODEX_NOTICE_LIST_URL = "https://www.samsungfund.com/etf/lounge/notice.do"
KODEX_NOTICE_VIEW_URL = "https://www.samsungfund.com/etf/lounge/notice-view.do?no={notice_no}"
TIGER_OVERALL_DISTRIBUTION_URL = "https://investments.miraeasset.com/tigeretf/ko/distribution/overall/list.do"
TIGER_OVERALL_DISTRIBUTION_AJAX_URL = "https://investments.miraeasset.com/tigeretf/ko/distribution/overall/list.ajax"
SOL_FUND_LIST_URL = "https://www.soletf.com/api/common/searchByEtfNameOrFilter"
SOL_DIVIDEND_URL = "https://www.soletf.com/api/etf/pds/dividend/{fund_code}"
ACE_FUND_LIST_URL = "https://papi.aceetf.co.kr/api/funds"
ACE_DIVIDEND_URL = "https://papi.aceetf.co.kr/api/funds/{fund_code}/dividend"

TICKER_COLUMNS = ("ticker", "종목코드", "단축코드", "ISU_CD", "ISU_SRT_CD", "isuCd", "isuSrtCd", "code")
NAME_COLUMNS = ("name", "종목명", "상품명", "ETF명", "ISU_NM", "ISU_ABBRV", "isuNm", "fund_name")
DATE_COLUMNS = ("distribution_date", "ex_date", "base_date", "record_date", "pay_date", "지급기준일", "분배기준일", "기준일", "실지급일", "지급일", "date")
PAY_DATE_COLUMNS = ("pay_date", "실지급일", "지급일")
AMOUNT_COLUMNS = ("distribution_amount", "분배금", "주당분배금", "주당분배금(원)", "현금분배금", "배당금", "amount", "dividend", "cash_distribution")


def _token(value: str) -> str:
    return str(value).replace("-", "")


def _to_number(value: Any) -> float | None:
    text = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _date_from_yyyymmdd(value: Any) -> str | None:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if len(text) != 8:
        return _date_text(str(value or ""))
    try:
        return datetime(int(text[:4]), int(text[4:6]), int(text[6:8])).date().isoformat()
    except ValueError:
        return None


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _date_text(value: str) -> str | None:
    text = _clean_text(value)
    compact_match = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", text)
    if compact_match:
        year, month, day = compact_match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            pass
    match = re.search(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            pass
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _ticker_text(value: str) -> str | None:
    match = re.search(r"\b[0-9A-Z]{6}\b", str(value or "").strip())
    if not match:
        return None
    return match.group(0).zfill(6)


def _flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            " ".join(str(part).strip() for part in col if str(part).strip() and not str(part).startswith("Unnamed"))
            for col in out.columns
        ]
    else:
        out.columns = [str(col).strip() for col in out.columns]
    out.columns = [re.sub(r"\s+", " ", str(col)).strip() for col in out.columns]
    return out


def _first_existing(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    lower_map = {col.lower(): col for col in columns}
    compact_map = {re.sub(r"[\s()]", "", col).lower(): col for col in columns}
    for candidate in candidates:
        if candidate in columns:
            return candidate
        mapped = lower_map.get(candidate.lower())
        if mapped:
            return mapped
        compact = re.sub(r"[\s()]", "", candidate).lower()
        mapped = compact_map.get(compact)
        if mapped:
            return mapped
    return None


def _normalize_etf_name(value: Any) -> str:
    text = _clean_text(value)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\bETF\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", "", text)
    return text.upper()


def _read_universe(path: str, ticker_col: str) -> pd.DataFrame:
    if not path:
        return pd.DataFrame(columns=["ticker", "name", "provider"])
    frame = pd.read_csv(Path(path), dtype={ticker_col: "string"}, low_memory=False)
    if ticker_col not in frame.columns:
        raise ValueError(f"missing ticker column {ticker_col}: {path}")
    if "name" not in frame.columns:
        frame["name"] = ""
    out = frame[[ticker_col, "name"]].rename(columns={ticker_col: "ticker"}).copy()
    out["ticker"] = out["ticker"].astype(str).str.strip().str.replace(".0", "", regex=False).str.zfill(6)
    out["name"] = out["name"].map(_clean_text)
    out["provider"] = out["name"].str.extract(r"^(KODEX|TIGER|ACE|SOL|RISE|PLUS|KIWOOM|HANARO|WON|UNICORN)", expand=False).fillna("OTHER")
    out["name_key"] = out["name"].map(_normalize_etf_name)
    return out.drop_duplicates("ticker")


def _map_name_to_ticker(name: Any, universe: pd.DataFrame) -> str | None:
    ticker = _ticker_text(str(name or ""))
    if ticker:
        return ticker
    if universe.empty:
        return None
    key = _normalize_etf_name(name)
    if not key:
        return None
    exact = universe[universe["name_key"].eq(key)]
    if len(exact) == 1:
        return str(exact.iloc[0]["ticker"]).zfill(6)
    contains = universe[universe["name_key"].map(lambda item: bool(item) and (item in key or key in item))]
    if len(contains) == 1:
        return str(contains.iloc[0]["ticker"]).zfill(6)
    return None


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return session


def _fetch_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text


def _find_kodex_distribution_notices(session: requests.Session, pages: int, max_notices: int) -> list[dict[str, Any]]:
    notices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, max(1, pages) + 1):
        url = KODEX_NOTICE_LIST_URL if page == 1 else f"{KODEX_NOTICE_LIST_URL}?pageIndex={page}"
        soup = BeautifulSoup(_fetch_text(session, url), "html.parser")
        for link in soup.select('a[href*="notice-view.do?no="]'):
            href = str(link.get("href") or "")
            match = re.search(r"no=(\d+)", href)
            if not match:
                continue
            notice_no = match.group(1)
            if notice_no in seen:
                continue
            title = _clean_text(link.select_one("h3").get_text(" ", strip=True) if link.select_one("h3") else link.get_text(" ", strip=True))
            if "분배금" not in title or "공지" not in title:
                continue
            date_node = link.select_one(".date")
            notice_date = _date_text(date_node.get_text(" ", strip=True) if date_node else "")
            seen.add(notice_no)
            notices.append(
                {
                    "notice_no": notice_no,
                    "title": title,
                    "notice_date": notice_date,
                    "url": urljoin(KODEX_NOTICE_LIST_URL, href),
                }
            )
            if len(notices) >= max_notices:
                return notices
    return notices


def _parse_kodex_notice(session: requests.Session, notice: dict[str, Any], tickers: set[str] | None) -> pd.DataFrame:
    html = _fetch_text(session, KODEX_NOTICE_VIEW_URL.format(notice_no=notice["notice_no"]))
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [_clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            ticker = _ticker_text(cells[0])
            if not ticker:
                continue
            amount = _to_number(cells[-1])
            if amount is None or amount <= 0:
                continue
            if tickers is not None and ticker not in tickers:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "name": cells[1] if len(cells) > 1 else "",
                    "distribution_date": notice.get("notice_date"),
                    "ex_date": notice.get("notice_date"),
                    "record_date": None,
                    "pay_date": None,
                    "distribution_amount": amount,
                    "source": "issuer_kodex_notice",
                    "source_detail": notice["url"],
                    "fetched_at": datetime.now().isoformat(timespec="seconds"),
                    "raw_json": json.dumps(
                        {
                            "notice_no": notice["notice_no"],
                            "title": notice["title"],
                            "notice_date": notice.get("notice_date"),
                            "cells": cells,
                            "date_quality": "notice_date_proxy",
                        },
                        ensure_ascii=False,
                    ),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame()
    frame = frame.dropna(subset=["ticker", "distribution_date", "distribution_amount"])
    return frame.drop_duplicates(["ticker", "distribution_date", "distribution_amount", "source"])


def _normalize_event_frame(
    frame: pd.DataFrame,
    *,
    provider: str,
    source: str,
    source_detail: str,
    universe: pd.DataFrame,
    tickers: set[str] | None,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    work = _flatten_columns(frame)
    columns = set(work.columns)
    ticker_col = _first_existing(columns, TICKER_COLUMNS)
    name_col = _first_existing(columns, NAME_COLUMNS)
    date_col = _first_existing(columns, DATE_COLUMNS)
    pay_date_col = _first_existing(columns, PAY_DATE_COLUMNS)
    amount_col = _first_existing(columns, AMOUNT_COLUMNS)
    if date_col is None or amount_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    if ticker_col:
        out["ticker"] = work[ticker_col].map(lambda value: _ticker_text(str(value)) or str(value).strip().replace(".0", "").zfill(6))
    elif name_col:
        out["ticker"] = work[name_col].map(lambda value: _map_name_to_ticker(value, universe))
    else:
        return pd.DataFrame()
    out["name"] = work[name_col].map(_clean_text) if name_col else ""
    out["distribution_date"] = work[date_col].map(_date_text)
    out["ex_date"] = out["distribution_date"]
    out["record_date"] = out["distribution_date"]
    out["pay_date"] = work[pay_date_col].map(_date_text) if pay_date_col else None
    out["distribution_amount"] = work[amount_col].map(_to_number)
    out["source"] = source
    out["source_detail"] = source_detail
    out["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    out["raw_json"] = [
        json.dumps({"provider": provider, "source": source_detail, "row": row}, ensure_ascii=False, default=str)
        for row in work.to_dict("records")
    ]
    out = out.dropna(subset=["ticker", "distribution_date", "distribution_amount"])
    out = out[out["distribution_amount"].gt(0)].copy()
    if tickers is not None:
        out = out[out["ticker"].isin(tickers)].copy()
    if out.empty:
        return pd.DataFrame()
    return out.drop_duplicates(["ticker", "distribution_date", "distribution_amount", "source"])


def _parse_tiger_ajax(
    session: requests.Session,
    universe: pd.DataFrame,
    tickers: set[str] | None,
    *,
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    request_count = 0
    months_with_rows = 0
    headers = {"X-Requested-With": "XMLHttpRequest", "Referer": TIGER_OVERALL_DISTRIBUTION_URL}
    for year in range(int(start_year), int(end_year) + 1):
        for month in range(1, 13):
            request_count += 1
            response = session.get(
                TIGER_OVERALL_DISTRIBUTION_AJAX_URL,
                params={
                    "pageIndex": 1,
                    "firstIndex": 0,
                    "listCnt": 500,
                    "selectYear": str(year),
                    "selectMonth": f"{month:02d}",
                },
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            month_rows = 0
            for tr in soup.find_all("tr"):
                cells = [_clean_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                if len(cells) < 7:
                    continue
                ticker = _ticker_text(cells[0])
                name_node = tr.select_one("p.title")
                name = _clean_text(name_node.get_text(" ", strip=True) if name_node else cells[0])
                if not ticker:
                    ticker = _map_name_to_ticker(name, universe)
                amount = _to_number(cells[4])
                record_date = _date_text(cells[2])
                if not ticker or amount is None or amount <= 0 or not record_date:
                    continue
                if tickers is not None and ticker not in tickers:
                    continue
                rows.append(
                    {
                        "ticker": ticker,
                        "name": name,
                        "distribution_date": record_date,
                        "ex_date": record_date,
                        "record_date": record_date,
                        "pay_date": _date_text(cells[3]),
                        "distribution_amount": amount,
                        "source": "issuer_tiger_ajax",
                        "source_detail": TIGER_OVERALL_DISTRIBUTION_AJAX_URL,
                        "fetched_at": datetime.now().isoformat(timespec="seconds"),
                        "raw_json": json.dumps(
                            {"year": year, "month": month, "cells": cells},
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )
                month_rows += 1
            if month_rows:
                months_with_rows += 1
    frame = pd.DataFrame(rows)
    summary = {"requests": request_count, "months_with_rows": months_with_rows, "rows": int(len(frame))}
    if frame.empty:
        return pd.DataFrame(), summary
    return frame.drop_duplicates(["ticker", "distribution_date", "distribution_amount", "source"]), summary


def _parse_tiger_overall(session: requests.Session, universe: pd.DataFrame, tickers: set[str] | None) -> pd.DataFrame:
    html = _fetch_text(session, TIGER_OVERALL_DISTRIBUTION_URL)
    frames = pd.read_html(StringIO(html))
    parsed: list[pd.DataFrame] = []
    for frame in frames:
        normalized = _normalize_event_frame(
            frame,
            provider="tiger",
            source="issuer_tiger_overall",
            source_detail=TIGER_OVERALL_DISTRIBUTION_URL,
            universe=universe,
            tickers=tickers,
        )
        if not normalized.empty:
            parsed.append(normalized)
    return pd.concat(parsed, ignore_index=True).drop_duplicates(["ticker", "distribution_date", "distribution_amount", "source"]) if parsed else pd.DataFrame()


def _provider_tickers(universe: pd.DataFrame, provider: str, tickers: set[str] | None) -> set[str]:
    if universe.empty:
        return tickers or set()
    provider_set = set(universe.loc[universe["provider"].eq(provider), "ticker"].astype(str).str.zfill(6).tolist())
    if tickers is not None:
        provider_set &= tickers
    return provider_set


def _parse_sol_api(session: requests.Session, universe: pd.DataFrame, tickers: set[str] | None, sleep_seconds: float = 0.0) -> tuple[pd.DataFrame, dict[str, Any]]:
    sol_tickers = _provider_tickers(universe, "SOL", tickers)
    sol_session = requests.Session()
    sol_session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.soletf.com/ko/fund",
        }
    )
    response = sol_session.post(SOL_FUND_LIST_URL, data={"viewCount": 500}, timeout=30)
    response.raise_for_status()
    funds = response.json().get("items") or []
    rows: list[dict[str, Any]] = []
    fund_count = 0
    dividend_fund_count = 0
    fund_errors: list[dict[str, Any]] = []
    for fund in funds:
        ticker = _ticker_text(fund.get("ETF_CD6"))
        fund_code = str(fund.get("FUND_CD") or "").strip()
        name = _clean_text(fund.get("Name") or fund.get("ETF_NAME") or "")
        if not ticker or not fund_code or (sol_tickers and ticker not in sol_tickers):
            continue
        fund_count += 1
        detail = SOL_DIVIDEND_URL.format(fund_code=fund_code)
        try:
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            sol_session.headers.update({"Referer": f"https://www.soletf.com/ko/fund/etf/{fund_code}"})
            div_response = sol_session.get(detail, timeout=30)
            div_response.raise_for_status()
        except Exception as exc:
            fund_errors.append({"ticker": ticker, "fund_code": fund_code, "error": f"{type(exc).__name__}: {exc}"})
            continue
        payload = div_response.json()
        items = payload.get("items") or []
        if items:
            dividend_fund_count += 1
        for item in items:
            amount = _to_number(item.get("DIVIDEND_PRI"))
            record_date = _date_from_yyyymmdd(item.get("WORK_DT"))
            if amount is None or amount <= 0 or not record_date:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "name": name or _clean_text(payload.get("fundName")),
                    "distribution_date": record_date,
                    "ex_date": record_date,
                    "record_date": record_date,
                    "pay_date": _date_from_yyyymmdd(item.get("DIVIDEND_DT")),
                    "distribution_amount": amount,
                    "source": "issuer_sol_api",
                    "source_detail": detail,
                    "fetched_at": datetime.now().isoformat(timespec="seconds"),
                    "raw_json": json.dumps({"fund": fund, "item": item}, ensure_ascii=False, default=str),
                }
            )
    frame = pd.DataFrame(rows)
    summary = {
        "funds_checked": fund_count,
        "funds_with_dividends": dividend_fund_count,
        "rows": int(len(frame)),
        "fund_errors": fund_errors[:20],
    }
    if frame.empty:
        return pd.DataFrame(), summary
    return (
        frame.drop_duplicates(["ticker", "distribution_date", "distribution_amount", "source"]),
        summary,
    )


def _parse_ace_api(session: requests.Session, universe: pd.DataFrame, tickers: set[str] | None, sleep_seconds: float = 0.0) -> tuple[pd.DataFrame, dict[str, Any]]:
    ace_tickers = _provider_tickers(universe, "ACE", tickers)
    response = session.get(ACE_FUND_LIST_URL, params={"page": 1, "size": 500}, timeout=30)
    response.raise_for_status()
    funds = response.json().get("data") or []
    rows: list[dict[str, Any]] = []
    fund_count = 0
    dividend_fund_count = 0
    ace_session = requests.Session()
    ace_session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Origin": "https://www.aceetf.co.kr",
            "Referer": "https://www.aceetf.co.kr/fund",
        }
    )
    for fund in funds:
        badge = fund.get("badge") or {}
        ticker = _ticker_text(badge.get("stockCode") or "")
        fund_code = str(fund.get("fundCd") or "").strip()
        name = _clean_text(fund.get("fundNm") or "")
        if not ticker or not fund_code or (ace_tickers and ticker not in ace_tickers):
            continue
        fund_count += 1
        detail = ACE_DIVIDEND_URL.format(fund_code=fund_code)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        div_response = ace_session.get(detail, params={"page": 1, "size": 200}, timeout=30)
        div_response.raise_for_status()
        payload = div_response.json()
        items = payload.get("dividendList") or []
        if items:
            dividend_fund_count += 1
        for item in items:
            amount = _to_number(item.get("dividend_PRI"))
            record_date = _date_from_yyyymmdd(item.get("std_DT"))
            if amount is None or amount <= 0 or not record_date:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "distribution_date": record_date,
                    "ex_date": record_date,
                    "record_date": record_date,
                    "pay_date": _date_from_yyyymmdd(item.get("dividend_DT")),
                    "distribution_amount": amount,
                    "source": "issuer_ace_api",
                    "source_detail": detail,
                    "fetched_at": datetime.now().isoformat(timespec="seconds"),
                    "raw_json": json.dumps({"fund": fund, "item": item}, ensure_ascii=False, default=str),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(), {"funds_checked": fund_count, "funds_with_dividends": dividend_fund_count, "rows": 0}
    return (
        frame.drop_duplicates(["ticker", "distribution_date", "distribution_amount", "source"]),
        {"funds_checked": fund_count, "funds_with_dividends": dividend_fund_count, "rows": int(len(frame))},
    )


def _read_distribution_csvs(paths: list[str], csv_dir: str, universe: pd.DataFrame, tickers: set[str] | None) -> tuple[list[pd.DataFrame], list[str]]:
    found: list[str] = []
    candidates = [Path(path) for path in paths if path]
    if csv_dir:
        base = Path(csv_dir)
        if base.exists():
            candidates.extend(sorted(base.glob("*.csv")))
    frames: list[pd.DataFrame] = []
    for path in candidates:
        if not path.exists():
            continue
        found.append(str(path))
        frame = pd.read_csv(path, dtype=str, low_memory=False)
        normalized = _normalize_event_frame(
            frame,
            provider="csv",
            source=f"issuer_csv_{path.stem}",
            source_detail=str(path),
            universe=universe,
            tickers=tickers,
        )
        if not normalized.empty:
            frames.append(normalized)
    return frames, found


def _table_summary(db_path: Path) -> dict[str, Any]:
    with sqlite3.connect(db_path) as con:
        row = con.execute(
            f"""
            select count(*), count(distinct ticker), min(distribution_date), max(distribution_date),
                   sum(distribution_amount)
            from {TABLE_NAME}
            """
        ).fetchone()
        by_source = pd.read_sql_query(
            f"""
            select source, count(*) as rows, count(distinct ticker) as tickers,
                   min(distribution_date) as min_date, max(distribution_date) as max_date
            from {TABLE_NAME}
            group by source
            order by rows desc
            """,
            con,
        )
        recent = pd.read_sql_query(
            f"""
            select ticker, name, distribution_date, distribution_amount, source
            from {TABLE_NAME}
            order by distribution_date desc, ticker
            limit 20
            """,
            con,
        )
    return {
        "rows": int(row[0] or 0),
        "tickers": int(row[1] or 0),
        "min_date": row[2],
        "max_date": row[3],
        "amount_sum": float(row[4] or 0.0),
        "by_source": by_source.to_dict("records"),
        "recent_sample": recent.to_dict("records"),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    asof = str(args.asof or datetime.now().date().isoformat())
    db_path = Path(args.db)
    _create_table(db_path)
    universe = _read_universe(args.tickers_file, args.ticker_col)
    tickers = set(universe["ticker"].astype(str).str.zfill(6).tolist()) if not universe.empty else None
    providers = {item.strip().lower() for item in str(args.providers).split(",") if item.strip()}
    session = _session()
    frames: list[pd.DataFrame] = []
    diagnostics: dict[str, Any] = {
        "provider_universe_counts": universe["provider"].value_counts().to_dict() if not universe.empty else {},
    }
    errors: list[dict[str, Any]] = []

    if "kodex" in providers:
        try:
            notices = _find_kodex_distribution_notices(session, int(args.kodex_pages), int(args.max_notices))
            diagnostics["kodex_notices"] = notices
            for notice in notices:
                try:
                    frame = _parse_kodex_notice(session, notice, tickers)
                    if not frame.empty:
                        frames.append(frame)
                except Exception as exc:
                    errors.append({"provider": "kodex", "notice_no": notice.get("notice_no"), "error": f"{type(exc).__name__}: {exc}"})
        except Exception as exc:
            errors.append({"provider": "kodex", "stage": "notice_list", "error": f"{type(exc).__name__}: {exc}"})

    if "tiger" in providers:
        try:
            end_year = datetime.fromisoformat(asof).year
            frame, summary = _parse_tiger_ajax(
                session,
                universe,
                tickers,
                start_year=int(args.tiger_start_year),
                end_year=end_year,
            )
            diagnostics["tiger_ajax"] = summary
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            errors.append({"provider": "tiger", "stage": "overall_distribution_ajax", "error": f"{type(exc).__name__}: {exc}"})

    if "sol" in providers:
        try:
            frame, summary = _parse_sol_api(session, universe, tickers, float(args.provider_sleep))
            diagnostics["sol_api"] = summary
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            errors.append({"provider": "sol", "stage": "dividend_api", "error": f"{type(exc).__name__}: {exc}"})

    if "ace" in providers:
        try:
            frame, summary = _parse_ace_api(session, universe, tickers, float(args.provider_sleep))
            diagnostics["ace_api"] = summary
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            errors.append({"provider": "ace", "stage": "dividend_api", "error": f"{type(exc).__name__}: {exc}"})

    if "csv" in providers or args.csv_file:
        try:
            csv_frames, found_csvs = _read_distribution_csvs(args.csv_file or [], args.csv_dir, universe, tickers)
            diagnostics["csv_files_found"] = found_csvs
            frames.extend(csv_frames)
        except Exception as exc:
            errors.append({"provider": "csv", "stage": "read_csv", "error": f"{type(exc).__name__}: {exc}"})

    events = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    inserted = _upsert_events(db_path, events) if not events.empty else 0
    status = "ok" if inserted > 0 else ("source_error" if errors and not frames else "no_events")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    json_path = REPORT_DIR / f"e_series_etf_issuer_distributions_{token}.json"
    sample_path = REPORT_DIR / f"e_series_etf_issuer_distributions_sample_{token}.csv"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_issuer_distributions_current.json"
    if not events.empty:
        events.head(300).to_csv(sample_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": status,
        "source_name": "issuer_etf_distributions",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "providers": sorted(providers),
        "inserted_rows": int(inserted),
        "event_rows_collected": int(len(events)),
        "event_tickers_collected": int(events["ticker"].nunique()) if not events.empty else 0,
        "date_quality": "provider_specific_or_csv_date",
        "table": {
            "db_path": str(db_path),
            "name": TABLE_NAME,
            "summary": _table_summary(db_path),
        },
        "diagnostics": diagnostics,
        "errors": errors[:30],
        "outputs": {
            "json": str(json_path),
            "sample_csv": str(sample_path) if sample_path.exists() else None,
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ETF cash distributions from issuer pages into price.db.")
    parser.add_argument("--asof", default="")
    parser.add_argument("--providers", default="kodex")
    parser.add_argument("--db", default=str(PRICE_DB))
    parser.add_argument("--tickers-file", default=str(ROOT / r"data\universe\universe_etf_master_latest.csv"))
    parser.add_argument("--ticker-col", default="ticker")
    parser.add_argument("--kodex-pages", type=int, default=1)
    parser.add_argument("--max-notices", type=int, default=5)
    parser.add_argument("--tiger-start-year", type=int, default=2020)
    parser.add_argument("--csv-dir", default=str(ROOT / r"data\etf_distributions"))
    parser.add_argument("--csv-file", action="append", default=[])
    parser.add_argument("--provider-sleep", type=float, default=0.6)
    args = parser.parse_args()
    payload = run(args)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "as_of_date": payload["as_of_date"],
                "providers": payload["providers"],
                "inserted_rows": payload["inserted_rows"],
                "event_tickers_collected": payload["event_tickers_collected"],
                "table_summary": payload["table"]["summary"],
                "outputs": payload["outputs"],
                "errors": payload["errors"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
