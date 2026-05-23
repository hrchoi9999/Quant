from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.dart_financials import (  # noqa: E402
    fetch_financial_statements_with_fallback,
    save_raw_financials,
)

RAW_DART_DIR = ROOT / "data" / "raw" / "dart"


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _load_universe(universe_csv: Path, ticker_col: str) -> pd.DataFrame:
    df = pd.read_csv(universe_csv, dtype={ticker_col: str})
    if ticker_col not in df.columns:
        raise ValueError(f"ticker_col '{ticker_col}' not found in {universe_csv}")
    df[ticker_col] = df[ticker_col].astype(str).str.zfill(6)
    return df[[ticker_col]].drop_duplicates().rename(columns={ticker_col: "ticker"})


def _load_ticker_to_corp(dart_db: Path) -> pd.DataFrame:
    con = _connect(dart_db)
    try:
        df = pd.read_sql_query(
            """
            SELECT corp_code, corp_name, stock_code
            FROM dim_corp_listed
            WHERE stock_code IS NOT NULL AND stock_code <> ''
            """,
            con,
        )
    finally:
        con.close()
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    return df


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text or text.lower() in {"nan", "none"}:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except Exception:
        return None


def _load_or_fetch_raw(corp_code: str, year: int, reprt_code: str) -> tuple[pd.DataFrame, str, str]:
    candidates = [
        RAW_DART_DIR / f"fs_{corp_code}_{year}_{reprt_code}_CFS.parquet",
        RAW_DART_DIR / f"fs_{corp_code}_{year}_{reprt_code}_OFS.parquet",
    ]
    for path in candidates:
        if path.exists():
            return pd.read_parquet(path), "cached", path.stem.rsplit("_", 1)[-1]

    df_raw, used_div = fetch_financial_statements_with_fallback(
        corp_code=corp_code,
        year=year,
        report_code=reprt_code,
        prefer_fs_div="CFS",
    )
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(), "no_data", used_div

    save_raw_financials(df_raw, corp_code, year, reprt_code, used_div)
    return df_raw, "fetched", used_div


def _upsert_fact_report(con: sqlite3.Connection, df_raw: pd.DataFrame, corp_code: str, year: int, reprt_code: str, fs_div: str) -> None:
    if df_raw.empty:
        return
    rcept_no = _normalize_text(df_raw.iloc[0].get("rcept_no"))
    if not rcept_no:
        return
    con.execute(
        """
        INSERT INTO fact_report (rcept_no, reprt_code, bsns_year, corp_code, fs_div, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(rcept_no) DO UPDATE SET
            reprt_code=excluded.reprt_code,
            bsns_year=excluded.bsns_year,
            corp_code=excluded.corp_code,
            fs_div=excluded.fs_div
        """,
        [
            rcept_no,
            reprt_code,
            int(year),
            corp_code,
            fs_div,
            datetime.now().isoformat(timespec="seconds"),
        ],
    )


def _iter_account_rows(df_raw: pd.DataFrame, corp_code: str, year: int, fs_div: str) -> Iterable[list[object]]:
    for _, row in df_raw.iterrows():
        rcept_no = _normalize_text(row.get("rcept_no"))
        account_id = _normalize_text(row.get("account_id")) or "-missing-account-id-"
        sj_div = _normalize_text(row.get("sj_div")) or "-missing-sj-div-"
        ord_val = row.get("ord")
        try:
            ord_int = int(ord_val) if pd.notna(ord_val) else -1
        except Exception:
            ord_int = -1

        yield [
            rcept_no,
            corp_code,
            int(year),
            fs_div,
            sj_div,
            _normalize_text(row.get("sj_nm")),
            account_id,
            _normalize_text(row.get("account_nm")),
            _normalize_text(row.get("account_detail")),
            ord_int,
            _normalize_text(row.get("currency")),
            _normalize_text(row.get("thstrm_nm")),
            _to_float(row.get("thstrm_amount")),
            _normalize_text(row.get("frmtrm_nm")),
            _to_float(row.get("frmtrm_amount")),
        ]


def _upsert_fact_fs_account(con: sqlite3.Connection, df_raw: pd.DataFrame, corp_code: str, year: int, fs_div: str) -> int:
    if df_raw.empty:
        return 0
    rows = list(_iter_account_rows(df_raw, corp_code=corp_code, year=year, fs_div=fs_div))
    con.executemany(
        """
        INSERT INTO fact_fs_account (
            rcept_no, corp_code, bsns_year, fs_div, sj_div, sj_nm,
            account_id, account_nm, account_detail, ord, currency,
            thstrm_nm, thstrm_amount, frmtrm_nm, frmtrm_amount
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rcept_no, fs_div, account_id, sj_div, ord) DO UPDATE SET
            corp_code=excluded.corp_code,
            bsns_year=excluded.bsns_year,
            sj_nm=excluded.sj_nm,
            account_nm=excluded.account_nm,
            account_detail=excluded.account_detail,
            currency=excluded.currency,
            thstrm_nm=excluded.thstrm_nm,
            thstrm_amount=excluded.thstrm_amount,
            frmtrm_nm=excluded.frmtrm_nm,
            frmtrm_amount=excluded.frmtrm_amount
        """,
        rows,
    )
    return len(rows)


def run_backfill(
    dart_db: Path,
    universe_csv: Path,
    ticker_col: str,
    year: int,
    report_codes: list[str],
    commit_every: int,
) -> None:
    universe = _load_universe(universe_csv, ticker_col=ticker_col)
    mapping = _load_ticker_to_corp(dart_db)
    targets = universe.merge(mapping, left_on="ticker", right_on="stock_code", how="left").dropna(subset=["corp_code"]).copy()

    con = _connect(dart_db)
    try:
        processed = 0
        fetched = 0
        cached = 0
        no_data = 0
        reports_upserted = 0
        accounts_upserted = 0
        failures = 0

        total = len(targets) * len(report_codes)
        print(f"[INFO] target_tickers={len(targets)} year={year} report_codes={report_codes} total_tasks={total}")

        for _, target in targets.iterrows():
            corp_code = _normalize_text(target["corp_code"])
            corp_name = _normalize_text(target["corp_name"])
            ticker = _normalize_text(target["ticker"]).zfill(6)

            for reprt_code in report_codes:
                processed += 1
                try:
                    df_raw, source, used_div = _load_or_fetch_raw(corp_code, year, reprt_code)
                    if source == "no_data" or df_raw.empty:
                        no_data += 1
                        print(f"[{processed}/{total}] {ticker} {corp_name} {year} {reprt_code} -> no_data")
                        continue

                    if source == "fetched":
                        fetched += 1
                    else:
                        cached += 1

                    _upsert_fact_report(con, df_raw, corp_code=corp_code, year=year, reprt_code=reprt_code, fs_div=used_div)
                    reports_upserted += 1
                    accounts_upserted += _upsert_fact_fs_account(con, df_raw, corp_code=corp_code, year=year, fs_div=used_div)
                    print(
                        f"[{processed}/{total}] {ticker} {corp_name} {year} {reprt_code} -> {source} {used_div} rows={len(df_raw)}"
                    )
                except Exception as exc:
                    failures += 1
                    print(f"[{processed}/{total}] {ticker} {corp_name} {year} {reprt_code} -> FAIL {exc}")

                if processed % max(1, commit_every) == 0:
                    con.commit()
                    print(
                        f"[INFO] progress processed={processed} fetched={fetched} cached={cached} no_data={no_data} "
                        f"reports={reports_upserted} accounts={accounts_upserted} fail={failures}"
                    )

        con.commit()
        print(
            f"[DONE] processed={processed} fetched={fetched} cached={cached} no_data={no_data} "
            f"reports={reports_upserted} accounts={accounts_upserted} fail={failures}"
        )
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill quarterly / semiannual DART raw files into dart_main.db fact tables.")
    parser.add_argument("--dart-db", default=str(ROOT / "data" / "db" / "dart_main.db"))
    parser.add_argument("--universe-csv", default=str(ROOT / "data" / "universe" / "universe_mix_top400_latest_fundready.csv"))
    parser.add_argument("--ticker-col", default="ticker")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--report-codes", nargs="+", default=["11012", "11013", "11014"])
    parser.add_argument("--commit-every", type=int, default=20)
    args = parser.parse_args()

    run_backfill(
        dart_db=Path(args.dart_db),
        universe_csv=Path(args.universe_csv),
        ticker_col=args.ticker_col,
        year=int(args.year),
        report_codes=[str(x) for x in args.report_codes],
        commit_every=int(args.commit_every),
    )


if __name__ == "__main__":
    main()
