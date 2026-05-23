from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from src.collectors.krx_openapi import ETF_ENDPOINT, _request, _rows, iter_bas_dd, load_api_key
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT_CANDIDATE = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / "src").exists()), CURRENT.parent)
    if str(ROOT_CANDIDATE) not in sys.path:
        sys.path.insert(0, str(ROOT_CANDIDATE))
    from src.collectors.krx_openapi import ETF_ENDPOINT, _request, _rows, iter_bas_dd, load_api_key


ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
TABLE_NAME = "etf_distributions"

TICKER_COLUMNS = ("ticker", "ISU_CD", "ISU_SRT_CD", "isuCd", "isuSrtCd", "종목코드", "단축코드")
NAME_COLUMNS = ("name", "ISU_NM", "ISU_ABBRV", "isuNm", "isuAbrv", "종목명", "한글종목명")
DATE_COLUMNS = (
    "distribution_date",
    "ex_date",
    "base_date",
    "record_date",
    "pay_date",
    "BAS_DD",
    "TRD_DD",
    "EX_DD",
    "DSTRB_DD",
    "PAY_DD",
    "REC_DD",
    "기준일",
    "거래일자",
    "분배락일",
    "분배기준일",
    "지급일",
)
AMOUNT_COLUMNS = (
    "distribution_amount",
    "distribution",
    "cash_distribution",
    "dividend_amount",
    "dividend",
    "dist_amount",
    "amount",
    "per_share_distribution",
    "DSTRB_AMT",
    "DISTRIBUTION_AMOUNT",
    "DVDN_AMT",
    "DIV_AMT",
    "CASH_DSTRB_AMT",
    "분배금",
    "현금분배금",
    "주당분배금",
    "배당금",
    "금액",
)


def _token(value: str) -> str:
    return str(value).replace("-", "")


def _date_text(value: str) -> str:
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-"}:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_existing(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    lower_map = {col.lower(): col for col in columns}
    for candidate in candidates:
        if candidate in columns:
            return candidate
        mapped = lower_map.get(candidate.lower())
        if mapped:
            return mapped
    return None


def _read_tickers(path: str, ticker_col: str) -> set[str] | None:
    if not path:
        return None
    frame = pd.read_csv(Path(path), dtype={ticker_col: "string"}, low_memory=False)
    if ticker_col not in frame.columns:
        raise ValueError(f"missing ticker column {ticker_col}: {path}")
    return {
        str(value).strip().replace(".0", "").zfill(6)
        for value in frame[ticker_col].dropna().tolist()
        if str(value).strip()
    }


def _create_table(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.execute(
            f"""
            create table if not exists {TABLE_NAME} (
                ticker text not null,
                name text,
                distribution_date text not null,
                ex_date text,
                record_date text,
                pay_date text,
                distribution_amount real not null,
                source text not null,
                source_detail text,
                fetched_at text not null,
                raw_json text,
                primary key (ticker, distribution_date, distribution_amount, source)
            )
            """
        )
        con.execute(f"create index if not exists idx_{TABLE_NAME}_date on {TABLE_NAME}(distribution_date)")
        con.execute(f"create index if not exists idx_{TABLE_NAME}_ticker_date on {TABLE_NAME}(ticker, distribution_date)")
        con.commit()


def _normalize_events(rows: list[dict[str, Any]], bas_dd: str, tickers: set[str] | None) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not rows:
        return pd.DataFrame(), {"row_count": 0, "columns": []}
    frame = pd.DataFrame(rows)
    columns = set(frame.columns)
    ticker_col = _first_existing(columns, TICKER_COLUMNS)
    name_col = _first_existing(columns, NAME_COLUMNS)
    date_col = _first_existing(columns, DATE_COLUMNS)
    amount_col = _first_existing(columns, AMOUNT_COLUMNS)
    diagnostics = {
        "row_count": int(len(frame)),
        "columns": sorted(str(col) for col in frame.columns),
        "ticker_column": ticker_col,
        "name_column": name_col,
        "date_column": date_col,
        "amount_column": amount_col,
        "date_inferred_from_query": bool(amount_col and not date_col),
    }
    if ticker_col is None or amount_col is None:
        return pd.DataFrame(), diagnostics

    out = pd.DataFrame()
    out["ticker"] = frame[ticker_col].astype(str).str.strip().str.replace(".0", "", regex=False).str.zfill(6)
    out["name"] = frame[name_col].astype(str).str.strip() if name_col else ""
    if date_col:
        out["distribution_date"] = frame[date_col].map(_iso_date)
    else:
        out["distribution_date"] = datetime.strptime(bas_dd, "%Y%m%d").date().isoformat()
    out["ex_date"] = out["distribution_date"]
    out["record_date"] = None
    out["pay_date"] = None
    out["distribution_amount"] = frame[amount_col].map(_to_number)
    out["source"] = "krx_openapi"
    out["source_detail"] = f"{ETF_ENDPOINT}?basDd={bas_dd}"
    out["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    out["raw_json"] = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    out = out.dropna(subset=["ticker", "distribution_date", "distribution_amount"])
    out = out[out["distribution_amount"].gt(0)].copy()
    if tickers is not None:
        out = out[out["ticker"].isin(tickers)].copy()
    return out, diagnostics


def _upsert_events(db_path: Path, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    cols = [
        "ticker",
        "name",
        "distribution_date",
        "ex_date",
        "record_date",
        "pay_date",
        "distribution_amount",
        "source",
        "source_detail",
        "fetched_at",
        "raw_json",
    ]
    rows = frame[cols].to_records(index=False).tolist()
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{col}=excluded.{col}" for col in cols if col not in {"ticker", "distribution_date", "distribution_amount", "source"})
    with sqlite3.connect(db_path) as con:
        con.executemany(
            f"""
            insert into {TABLE_NAME} ({",".join(cols)})
            values ({placeholders})
            on conflict(ticker, distribution_date, distribution_amount, source)
            do update set {updates}
            """,
            rows,
        )
        con.commit()
    return len(rows)


def _load_recent_table_summary(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"table_exists": False}
    with sqlite3.connect(db_path) as con:
        exists = con.execute(
            "select 1 from sqlite_master where type='table' and name=?",
            (TABLE_NAME,),
        ).fetchone()
        if not exists:
            return {"table_exists": False}
        row = con.execute(
            f"""
            select
                count(*) as rows,
                count(distinct ticker) as tickers,
                min(distribution_date) as min_date,
                max(distribution_date) as max_date,
                sum(distribution_amount) as amount_sum
            from {TABLE_NAME}
            """
        ).fetchone()
    return {
        "table_exists": True,
        "rows": int(row[0] or 0),
        "tickers": int(row[1] or 0),
        "min_date": row[2],
        "max_date": row[3],
        "amount_sum": float(row[4] or 0.0),
    }


def fetch_krx_openapi_distributions(
    *,
    start: str,
    end: str,
    api_key: str,
    tickers: set[str] | None,
    max_dates: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    frames: list[pd.DataFrame] = []
    diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    dates = iter_bas_dd(start, end)
    if max_dates > 0:
        dates = dates[-max_dates:]
    for bas_dd in dates:
        try:
            payload = _request(ETF_ENDPOINT, bas_dd, api_key)
            rows = _rows(payload)
            events, diag = _normalize_events(rows, bas_dd, tickers)
            diag["bas_dd"] = bas_dd
            diag["matched_events"] = int(len(events))
            diagnostics.append(diag)
            if not events.empty:
                frames.append(events)
        except Exception as exc:
            errors.append({"bas_dd": bas_dd, "error": f"{type(exc).__name__}: {exc}"})
    if not frames:
        return pd.DataFrame(), diagnostics, errors
    out = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["ticker", "distribution_date", "distribution_amount", "source"]
    )
    return out.sort_values(["distribution_date", "ticker"]), diagnostics, errors


def run(args: argparse.Namespace) -> dict[str, Any]:
    asof = args.asof or args.end or datetime.now().strftime("%Y-%m-%d")
    end = _date_text(args.end or asof)
    if args.start:
        start = _date_text(args.start)
    elif int(args.lookback_days) > 0:
        start_dt = datetime.strptime(end, "%Y%m%d").date() - timedelta(days=int(args.lookback_days))
        start = start_dt.strftime("%Y%m%d")
    else:
        start = end

    db_path = Path(args.db) if args.db else PRICE_DB
    _create_table(db_path)
    tickers = _read_tickers(args.tickers_file, args.ticker_col)
    inserted = 0
    events = pd.DataFrame()
    diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    try:
        api_key = load_api_key(args.api_key_file)
        events, diagnostics, errors = fetch_krx_openapi_distributions(
            start=start,
            end=end,
            api_key=api_key,
            tickers=tickers,
            max_dates=int(args.max_dates),
        )
        inserted = _upsert_events(db_path, events)
    except Exception as exc:
        errors.append({"stage": "source_setup", "error": f"{type(exc).__name__}: {exc}"})

    amount_columns = sorted({diag.get("amount_column") for diag in diagnostics if diag.get("amount_column")})
    if inserted > 0:
        status = "ok"
    elif errors and not diagnostics:
        status = "source_error"
    elif amount_columns:
        status = "no_positive_distribution_events"
    else:
        status = "no_distribution_columns_found"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    json_path = REPORT_DIR / f"e_series_etf_krx_distributions_{token}.json"
    sample_path = REPORT_DIR / f"e_series_etf_krx_distributions_sample_{token}.csv"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_krx_distributions_current.json"
    if not events.empty:
        events.head(200).to_csv(sample_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": status,
        "source_name": "krx_etf_distributions",
        "as_of_date": str(asof),
        "range": {
            "start": datetime.strptime(start, "%Y%m%d").date().isoformat(),
            "end": datetime.strptime(end, "%Y%m%d").date().isoformat(),
            "max_dates": int(args.max_dates),
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "table": {
            "db_path": str(db_path),
            "name": TABLE_NAME,
            "inserted_rows": int(inserted),
            "summary": _load_recent_table_summary(db_path),
        },
        "source_diagnostics": {
            "method": "krx_openapi_etf_daily_schema_probe",
            "endpoint": ETF_ENDPOINT,
            "ticker_filter": "all" if tickers is None else len(tickers),
            "observed_dates": len(diagnostics),
            "amount_columns_found": amount_columns,
            "latest_observed_columns": diagnostics[-1]["columns"] if diagnostics else [],
            "latest_diagnostic": diagnostics[-1] if diagnostics else None,
            "errors": errors[:20],
        },
        "outputs": {
            "json": str(json_path),
            "sample_csv": str(sample_path) if sample_path.exists() else None,
            "admin_current_json": str(admin_path),
        },
        "interpretation": (
            "KRX OpenAPI ETF daily rows are probed for cash distribution columns. "
            "If no distribution amount column exists, the standard etf_distributions table is still prepared "
            "and E-series total-return logic remains on price-return fallback."
        ),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.strict and status not in {"ok", "no_positive_distribution_events"}:
        raise SystemExit(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe and ingest KRX ETF cash distribution events into price.db.")
    parser.add_argument("--asof", default="", help="YYYY-MM-DD; used for output naming and as default end date")
    parser.add_argument("--start", default="", help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--end", default="", help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--lookback-days", default=0, type=int, help="Used only when --start is omitted")
    parser.add_argument("--max-dates", default=0, type=int, help="Limit to last N weekdays in the selected range")
    parser.add_argument("--db", default=str(PRICE_DB))
    parser.add_argument("--api-key-file", default=str(ROOT / r"config\KRX_API_Key.json"))
    parser.add_argument("--tickers-file", default=str(ROOT / r"data\universe\universe_etf_master_latest.csv"))
    parser.add_argument("--ticker-col", default="ticker")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    payload = run(args)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "as_of_date": payload["as_of_date"],
                "range": payload["range"],
                "table": payload["table"],
                "source_diagnostics": payload["source_diagnostics"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
