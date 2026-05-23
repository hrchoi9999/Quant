from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests


PROJECT_ROOT = Path(r"D:\Quant")
DEFAULT_KEY_PATH = PROJECT_ROOT / r"config\KRX_API_Key.json"
BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"

STOCK_ENDPOINTS = {
    "KOSPI": "/sto/stk_bydd_trd",
    "KOSDAQ": "/sto/ksq_bydd_trd",
}
ETF_ENDPOINT = "/etp/etf_bydd_trd"
INDEX_ENDPOINTS = {
    "KOSPI": "/idx/kospi_dd_trd",
    "KOSDAQ": "/idx/kosdaq_dd_trd",
}


def normalize_bas_dd(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid basDd: {value}")
    return text


def iter_bas_dd(start: str, end: str) -> list[str]:
    start_dt = datetime.strptime(normalize_bas_dd(start), "%Y%m%d").date()
    end_dt = datetime.strptime(normalize_bas_dd(end), "%Y%m%d").date()
    if start_dt > end_dt:
        raise ValueError("start must be <= end")
    out: list[str] = []
    current = start_dt
    while current <= end_dt:
        if current.weekday() < 5:
            out.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return out


def load_api_key(path: str | Path | None = None, env_name: str = "KRX_OPENAPI_KEY") -> str:
    env_value = os.environ.get(env_name)
    if env_value:
        return env_value.strip()

    key_path = Path(path) if path else DEFAULT_KEY_PATH
    raw = key_path.read_text(encoding="utf-8-sig").strip()
    try:
        payload = json.loads(raw)
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("AUTH_KEY", "auth_key", "api_key", "API_KEY", "key", "KRX_OPENAPI_KEY"):
                value = payload.get(key)
                if value:
                    return str(value).strip()
    except json.JSONDecodeError:
        pass

    match = re.search(r"[A-Fa-f0-9]{40,}", raw)
    if match:
        return match.group(0).strip()
    if raw:
        return raw.strip().strip('"').strip("'")
    raise RuntimeError(f"empty KRX API key file: {key_path}")


def _request(path: str, bas_dd: str, api_key: str) -> dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}{path}",
        params={"basDd": normalize_bas_dd(bas_dd)},
        headers={"AUTH_KEY": api_key},
        timeout=60,
    )
    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"KRX OpenAPI non-JSON response: status={response.status_code}, head={response.text[:300]}") from exc
    if response.status_code != 200:
        raise RuntimeError(f"KRX OpenAPI failed: status={response.status_code}, payload={payload}")
    if payload.get("respCode"):
        raise RuntimeError(f"KRX OpenAPI error: payload={payload}")
    return payload


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("OutBlock_1") or payload.get("output") or payload.get("data") or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _to_number(value: Any) -> float | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_number(value)
    if number is None:
        return None
    return int(number)


def _daily_rows_to_price_frame(rows: list[dict[str, Any]], bas_dd: str) -> pd.DataFrame:
    out = []
    trade_date = datetime.strptime(normalize_bas_dd(bas_dd), "%Y%m%d")
    for row in rows:
        ticker = str(row.get("ISU_CD") or "").strip().zfill(6)
        if not ticker.isdigit() or len(ticker) != 6:
            continue
        out.append(
            {
                "ticker": ticker,
                "date": trade_date,
                "open": _to_number(row.get("TDD_OPNPRC")),
                "high": _to_number(row.get("TDD_HGPRC")),
                "low": _to_number(row.get("TDD_LWPRC")),
                "close": _to_number(row.get("TDD_CLSPRC")),
                "volume": _to_int(row.get("ACC_TRDVOL")),
                "value": _to_number(row.get("ACC_TRDVAL")),
                "name": str(row.get("ISU_NM") or "").strip(),
                "market": str(row.get("MKT_NM") or "").strip(),
                "mcap": _to_number(row.get("MKTCAP")),
                "list_shares": _to_number(row.get("LIST_SHRS")),
            }
        )
    return pd.DataFrame(out)


def fetch_stock_daily(market: str, bas_dd: str, api_key: str | None = None) -> pd.DataFrame:
    market = market.upper()
    if market not in STOCK_ENDPOINTS:
        raise ValueError(f"unsupported stock market: {market}")
    key = api_key or load_api_key()
    payload = _request(STOCK_ENDPOINTS[market], bas_dd, key)
    frame = _daily_rows_to_price_frame(_rows(payload), bas_dd)
    if not frame.empty:
        frame["market"] = market
    return frame


def fetch_all_stock_daily(bas_dd: str, api_key: str | None = None) -> pd.DataFrame:
    key = api_key or load_api_key()
    frames = [fetch_stock_daily(market, bas_dd, key) for market in ["KOSPI", "KOSDAQ"]]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_etf_daily(bas_dd: str, api_key: str | None = None) -> pd.DataFrame:
    key = api_key or load_api_key()
    payload = _request(ETF_ENDPOINT, bas_dd, key)
    rows = _rows(payload)
    frame = _daily_rows_to_price_frame(rows, bas_dd)
    if frame.empty:
        return frame

    frame["market"] = "ETF"
    raw_extra = []
    trade_date = datetime.strptime(normalize_bas_dd(bas_dd), "%Y%m%d")
    for row in rows:
        ticker = str(row.get("ISU_CD") or "").strip().zfill(6)
        if not ticker.isdigit() or len(ticker) != 6:
            continue
        raw_extra.append(
            {
                "ticker": ticker,
                "date": trade_date,
                "nav": _to_number(row.get("NAV")),
                "aum": _to_number(row.get("INVSTASST_NETASST_TOTAMT")),
                "underlying_index_name": str(row.get("IDX_IND_NM") or "").strip(),
                "underlying_index_level": _to_number(row.get("OBJ_STKPRC_IDX")),
                "underlying_index_change": _to_number(row.get("CMPPREVDD_IDX")),
                "underlying_index_return_pct": _to_number(row.get("FLUC_RT_IDX")),
                "etf_return_pct": _to_number(row.get("FLUC_RT")),
            }
        )
    extra = pd.DataFrame(raw_extra)
    if extra.empty:
        return frame
    frame = frame.merge(extra, on=["ticker", "date"], how="left")
    frame["premium_discount"] = frame["close"] / frame["nav"] - 1.0
    return frame


def fetch_index_daily(series: str, bas_dd: str, api_key: str | None = None) -> pd.DataFrame:
    series = series.upper()
    if series not in INDEX_ENDPOINTS:
        raise ValueError(f"unsupported index series: {series}")
    key = api_key or load_api_key()
    payload = _request(INDEX_ENDPOINTS[series], bas_dd, key)
    return pd.DataFrame(_rows(payload))


def price_frame_to_store_frame(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    sub = frame.loc[frame["ticker"].astype(str).str.zfill(6) == str(ticker).zfill(6)].copy()
    if sub.empty:
        return pd.DataFrame()
    sub = sub.sort_values("date")
    sub.index = pd.to_datetime(sub["date"])
    for col in ["open", "high", "low", "close", "volume", "value"]:
        if col not in sub.columns:
            sub[col] = None
    return sub[["open", "high", "low", "close", "volume", "value"]]


def stock_daily_to_universe(frame: pd.DataFrame, market: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "name", "market", "mcap"])
    out = frame[["ticker", "name", "mcap"]].copy()
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["market"] = market.upper()
    out["mcap"] = pd.to_numeric(out["mcap"], errors="coerce").fillna(0).astype("int64")
    out = out[out["mcap"] > 0].drop_duplicates("ticker")
    return out[["ticker", "name", "market", "mcap"]].reset_index(drop=True)
