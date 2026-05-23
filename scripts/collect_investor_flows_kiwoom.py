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
DEFAULT_APPKEY_FILE = ROOT / r"config\kiwoom_54810245_appkey.txt"
DEFAULT_SECRETKEY_FILE = ROOT / r"config\kiwoom_54810245_secretkey.txt"
KIWOOM_HOST = "https://api.kiwoom.com"
TOKEN_ENDPOINT = "/oauth2/token"
INVESTOR_ENDPOINT = "/api/dostk/stkinfo"
API_ID = "ka10059"

INVESTOR_FIELD_MAP = {
    "개인": "ind_invsr",
    "외국인": "frgnr_invsr",
    "기관합계": "orgn",
    "금융투자": "fnnc_invt",
    "보험": "insrnc",
    "투신": "invtrt",
    "기타금융": "etc_fnnc",
    "은행": "bank",
    "연기금": "penfnd_etc",
    "사모": "samo_fund",
    "국가": "natn",
    "기타법인": "etc_corp",
    "기타외국인": "natfor",
}


def _read_secret(path: Path) -> str:
    value = path.read_text(encoding="utf-8-sig").strip()
    if not value:
        raise RuntimeError(f"empty key file: {path}")
    return value


def _norm_ticker(value: Any) -> str | None:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(6) if digits else None


def _normalize_date(value: str) -> str:
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _api_date(value: str) -> str:
    return _normalize_date(value).replace("-", "")


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


def _load_universe(path: Path, limit: int | None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    ticker_col = "ticker" if "ticker" in df.columns else "code" if "code" in df.columns else None
    if ticker_col is None:
        raise ValueError(f"ticker column not found: {path}")
    name_col = "name" if "name" in df.columns else "display_name" if "display_name" in df.columns else None
    out = pd.DataFrame({"ticker": df[ticker_col].map(_norm_ticker), "name": df[name_col] if name_col else None})
    out = out.dropna(subset=["ticker"]).drop_duplicates("ticker").reset_index(drop=True)
    if limit:
        out = out.head(limit)
    return out


def _get_access_token(appkey_file: Path, secretkey_file: Path) -> tuple[str, str | None]:
    appkey = _read_secret(appkey_file)
    secretkey = _read_secret(secretkey_file)
    response = requests.post(
        f"{KIWOOM_HOST}{TOKEN_ENDPOINT}",
        headers={"Content-Type": "application/json;charset=UTF-8"},
        json={"grant_type": "client_credentials", "appkey": appkey, "secretkey": secretkey},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("return_code", -1)) != 0 or not payload.get("token"):
        raise RuntimeError(f"Kiwoom token failed: return_code={payload.get('return_code')}, return_msg={payload.get('return_msg')}")
    return str(payload["token"]), payload.get("expires_dt")


def _request_investor_page(token: str, ticker: str, end: str, amt_qty_tp: str, retries: int = 3) -> tuple[list[dict[str, Any]], str, str]:
    response = None
    for attempt in range(retries + 1):
        response = requests.post(
            f"{KIWOOM_HOST}{INVESTOR_ENDPOINT}",
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "authorization": f"Bearer {token}",
                "api-id": API_ID,
                "cont-yn": "N",
                "next-key": "",
            },
            json={
                "dt": _api_date(end),
                "stk_cd": ticker,
                "amt_qty_tp": amt_qty_tp,
                "trde_tp": "0",
                "unit_tp": "1",
            },
            timeout=60,
        )
        if response.status_code != 429:
            break
        time.sleep(min(10.0, 1.5 * (attempt + 1)))
    if response is None:
        raise RuntimeError("Kiwoom request was not executed")
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("return_code", -1)) != 0:
        raise RuntimeError(f"Kiwoom {API_ID} failed: return_code={payload.get('return_code')}, return_msg={payload.get('return_msg')}")
    rows = payload.get("stk_invsr_orgn") or []
    return rows if isinstance(rows, list) else [], str(response.headers.get("cont-yn") or "N"), str(response.headers.get("next-key") or "")


def _request_investor_rows(token: str, ticker: str, end: str, amt_qty_tp: str, start: str | None, sleep: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_end = _api_date(end)
    start_norm = _normalize_date(start) if start else None
    seen: set[str] = set()
    while current_end and current_end not in seen:
        seen.add(current_end)
        page, cont_yn, next_key = _request_investor_page(token, ticker, current_end, amt_qty_tp)
        rows.extend(page)
        if start_norm and page:
            page_dates = [_normalize_date(str(row.get("dt"))) for row in page if row.get("dt")]
            if page_dates and min(page_dates) <= start_norm:
                break
        if cont_yn.upper() != "Y" or not next_key:
            break
        current_end = next_key
        if sleep > 0:
            time.sleep(sleep)
    return rows


def _rows_to_frame(ticker: str, name: str | None, amount_rows: list[dict[str, Any]], quantity_rows: list[dict[str, Any]], start: str | None, end: str) -> pd.DataFrame:
    amount_by_date = {str(row.get("dt")): row for row in amount_rows if row.get("dt")}
    quantity_by_date = {str(row.get("dt")): row for row in quantity_rows if row.get("dt")}
    start_norm = _normalize_date(start) if start else None
    end_norm = _normalize_date(end)
    records: list[dict[str, Any]] = []
    for dt in sorted(set(amount_by_date) | set(quantity_by_date)):
        try:
            trade_date = _normalize_date(dt)
        except ValueError:
            continue
        if start_norm and trade_date < start_norm:
            continue
        if trade_date > end_norm:
            continue
        amount_row = amount_by_date.get(dt, {})
        qty_row = quantity_by_date.get(dt, {})
        for investor, field in INVESTOR_FIELD_MAP.items():
            net_value_million = _safe_number(amount_row.get(field))
            records.append(
                {
                    "date": trade_date,
                    "ticker": ticker,
                    "name": name,
                    "market": "KR_STOCK",
                    "investor": investor,
                    "buy_volume": None,
                    "sell_volume": None,
                    "net_volume": _safe_number(qty_row.get(field)),
                    "buy_value": None,
                    "sell_value": None,
                    "net_value": None if net_value_million is None else net_value_million * 1_000_000.0,
                    "source": "kiwoom_rest_ka10059",
                    "collected_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
    return pd.DataFrame(records)


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


def collect_kiwoom_investor_flows(
    *,
    universe_file: Path,
    db_path: Path,
    end: str,
    start: str | None,
    appkey_file: Path,
    secretkey_file: Path,
    limit: int | None,
    sleep: float,
) -> dict[str, Any]:
    universe = _load_universe(universe_file, limit)
    token, expires_dt = _get_access_token(appkey_file, secretkey_file)
    frames = []
    errors = []
    for row in universe.to_dict(orient="records"):
        ticker = row["ticker"]
        try:
            amount_rows = _request_investor_rows(token, ticker, end, "1", start, sleep)
            if sleep > 0:
                time.sleep(sleep)
            quantity_rows = _request_investor_rows(token, ticker, end, "2", start, sleep)
            frame = _rows_to_frame(ticker, row.get("name"), amount_rows, quantity_rows, start, end)
            frames.append(frame)
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)[:300]})
        if sleep > 0:
            time.sleep(sleep)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as con:
        _init_db(con)
        saved = _upsert(con, out)
        con.commit()
    return {
        "status": "ok" if not errors else "partial",
        "universe_count": int(len(universe)),
        "rows": int(len(out)),
        "saved": saved,
        "start": None if not start else _normalize_date(start),
        "end": _normalize_date(end),
        "token_expires_dt": expires_dt,
        "errors": errors[:20],
        "error_count": len(errors),
        "db_path": str(db_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Kiwoom REST investor flow data.")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE_FILE))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--end", required=True, help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--start", default=None, help="Optional lower bound. YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--appkey-file", default=str(DEFAULT_APPKEY_FILE))
    parser.add_argument("--secretkey-file", default=str(DEFAULT_SECRETKEY_FILE))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.05)
    args = parser.parse_args()
    result = collect_kiwoom_investor_flows(
        universe_file=Path(args.universe_file),
        db_path=Path(args.db),
        end=args.end,
        start=args.start,
        appkey_file=Path(args.appkey_file),
        secretkey_file=Path(args.secretkey_file),
        limit=args.limit,
        sleep=max(0.0, float(args.sleep)),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
