# rebuild_mix_universe_and_refresh_dbs.py ver 2026-02-06_001

# 목적:
# - KRX(또는 pykrx) 기반으로 KOSPI TopN, KOSDAQ TopN 유니버스 생성
# - KOSPI TopN + KOSDAQ TopN -> MixTopK(예: 200+200=400) 유니버스 생성
# - price.db: (A) 신규티커(기존 DB에 rows=0) 는 전체구간 backfill, (B) 꼬리 결측(tail missing)은 최근 N일만 backfill
# - (옵션) regime.db 재생성
# - (옵션) fundamentals.db(월단위) 재생성/갱신 (로컬 dart_main.db를 읽는 방식; DART API 수집은 별도)
# - (옵션) *_latest.csv 별칭 파일을 생성/갱신
#
# 핵심 설계(일관성):
# - 가격/레짐은 priceready(가격 결측 제거) 기준으로 생성 가능
# - 백테스트(펀더멘털 포함)는 fundready(재무 데이터 존재) 기준으로 "Final universe used"를 통일
#
# 주의:
# - price tail 결측은 "연속 꼬리 결측"만 처리합니다(중간 결측은 이번 범위 제외).

from __future__ import annotations

import argparse
import calendar
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pandas as pd


def _to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _date_shift(s: str, days: int) -> str:
    d = _to_date(s) + timedelta(days=days)
    return d.strftime("%Y-%m-%d")


def _safe_min_date_str(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return min(a,b) as YYYY-MM-DD string; None-safe."""
    if not a and not b:
        return None
    if a and not b:
        return a
    if b and not a:
        return b
    da = _to_date(a)  # type: ignore[arg-type]
    db = _to_date(b)  # type: ignore[arg-type]
    return a if da <= db else b


def _zfill6(x: str) -> str:
    return str(x).strip().zfill(6)


def _is_month_end(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def _snap_to_month_end_for_fund(end_yyyy_mm_dd: str) -> str:
    """
    Fundamentals 월단위 스냅 규칙:
    - end가 월말이면 그대로
    - 월말이 아니면 직전 월말로 스냅(부분월 제거)
    """
    d = _to_date(end_yyyy_mm_dd)
    if _is_month_end(d):
        return end_yyyy_mm_dd
    # previous month end
    y, m = d.year, d.month - 1
    if m == 0:
        y -= 1
        m = 12
    last_day = calendar.monthrange(y, m)[1]
    return date(y, m, last_day).strftime("%Y-%m-%d")


def _find_project_root(start: Path) -> Path:
    p = start.resolve()
    for parent in [p] + list(p.parents):
        if (parent / "src").exists():
            return parent
    return Path.cwd().resolve()


def _run(cmd: List[str], cwd: Path, dry_run: bool = False) -> None:
    print("\n[RUN]", " ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _copy_as_latest(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"[LATEST] {src.name} -> {dst.name}")


def _load_universe(path: Path, ticker_col: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if ticker_col not in df.columns:
        raise KeyError(f"Universe file missing column '{ticker_col}': {path}")
    df[ticker_col] = df[ticker_col].astype(str).map(_zfill6)
    return df


def _get_price_db_max_date(db: Path, table: str) -> Optional[str]:
    if not db.exists():
        return None
    con = sqlite3.connect(str(db))
    try:
        q = f"select max(date) as max_date from {table}"
        row = con.execute(q).fetchone()
        if row and row[0]:
            return str(row[0])
        return None
    finally:
        con.close()


def _ensure_regime_table_schema(regime_db: Path, regime_table: str) -> None:
    """
    Make existing regime_history table compatible with newer build_regime_history writers.
    Older regime.db may not have columns like ret/dd/vol/created_at/updated_at.
    Only additive ALTER TABLEs (no destructive migration).
    """
    if not regime_db.exists():
        return

    con = sqlite3.connect(str(regime_db))
    try:
        row = con.execute(
            "select name from sqlite_master where type='table' and name=?",
            (regime_table,),
        ).fetchone()
        if not row:
            return

        info = con.execute(f"PRAGMA table_info({regime_table})").fetchall()
        existing = {r[1] for r in info}

        add_cols = [
            ("ret", "REAL"),
            ("dd", "REAL"),
            ("vol", "REAL"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ]
        for c, t in add_cols:
            if c not in existing:
                con.execute(f"ALTER TABLE {regime_table} ADD COLUMN {c} {t}")
        con.commit()
    finally:
        con.close()


def _filter_universe_by_fs_annual(
    dart_db: Path,
    universe_file: Path,
    ticker_col: str,
    start_year: int,
    end_year: int,
    out_file: Path,
) -> Tuple[Path, List[str], int, int]:
    df = pd.read_csv(universe_file)
    if ticker_col not in df.columns:
        raise ValueError(f"ticker_col='{ticker_col}' not found in universe columns: {list(df.columns)}")
    df[ticker_col] = df[ticker_col].astype(str).str.zfill(6)

    before = len(df)

    con = sqlite3.connect(str(dart_db))
    try:
        fs = pd.read_sql_query(
            "select distinct stock_code from fs_annual where bsns_year between ? and ?",
            con,
            params=[start_year, end_year],
        )
    finally:
        con.close()

    fs["stock_code"] = fs["stock_code"].astype(str).str.zfill(6)
    have = set(fs["stock_code"].tolist())

    missing = sorted(set(df[ticker_col]) - have)
    df2 = df[df[ticker_col].isin(have)].copy()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    df2.to_csv(out_file, index=False, encoding="utf-8-sig")
    return out_file, missing, before, len(df2)


def _price_missing_tickers(price_db: Path, price_table: str, tickers: Iterable[str], end_date: str) -> List[str]:
    tickers = sorted({_zfill6(t) for t in tickers})
    if not tickers:
        return []
    conn = sqlite3.connect(str(price_db))
    try:
        have = pd.read_sql_query(
            f"select distinct ticker from {price_table} where date=?",
            conn,
            params=[end_date],
        )
        have_set = set(have["ticker"].astype(str).map(_zfill6))
        return [t for t in tickers if t not in have_set]
    finally:
        conn.close()


def _price_any_rows_tickers(price_db: Path, price_table: str, tickers: Iterable[str]) -> List[str]:
    tickers = sorted({_zfill6(t) for t in tickers})
    if not tickers:
        return []
    conn = sqlite3.connect(str(price_db))
    try:
        found = set()
        chunk = 900
        for i in range(0, len(tickers), chunk):
            part = tickers[i : i + chunk]
            qmarks = ",".join(["?"] * len(part))
            df = pd.read_sql_query(
                f"select distinct ticker from {price_table} where ticker in ({qmarks})",
                conn,
                params=part,
            )
            found |= set(df["ticker"].astype(str).map(_zfill6))
        return [t for t in tickers if t not in found]
    finally:
        conn.close()


def _write_universe_excluding(path_in: Path, path_out: Path, ticker_col: str, drop_tickers: List[str]) -> Tuple[int, int]:
    df = _load_universe(path_in, ticker_col)
    drop = set(map(_zfill6, drop_tickers))
    before = len(df)
    out = df[~df[ticker_col].astype(str).map(_zfill6).isin(drop)].copy()
    out.to_csv(path_out, index=False, encoding="utf-8-sig")
    return before, len(out)


@dataclass
class Paths:
    project_root: Path
    universe_dir: Path
    kospi_top: Path
    kosdaq_top: Path
    mix_universe: Path
    mix_universe_priceready: Path
    mix_universe_fundready: Path


def build_paths(project_root: Path, universe_dir: Path, asof_yyyymmdd: str, kospi_topn: int, kosdaq_topn: int, mix_size: int) -> Paths:
    kospi_top = universe_dir / f"universe_top{kospi_topn}_kospi_{asof_yyyymmdd}.csv"
    kosdaq_top = universe_dir / f"universe_top{kosdaq_topn}_kosdaq_{asof_yyyymmdd}.csv"
    mix_universe = universe_dir / f"universe_mix_top{mix_size}_{asof_yyyymmdd}.csv"
    mix_universe_priceready = universe_dir / f"universe_mix_top{mix_size}_{asof_yyyymmdd}_priceready.csv"
    mix_universe_fundready = universe_dir / f"universe_mix_top{mix_size}_{asof_yyyymmdd}_fundready.csv"
    return Paths(
        project_root=project_root,
        universe_dir=universe_dir,
        kospi_top=kospi_top,
        kosdaq_top=kosdaq_top,
        mix_universe=mix_universe,
        mix_universe_priceready=mix_universe_priceready,
        mix_universe_fundready=mix_universe_fundready,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rebuild universe + refresh DBs for regime/fundamentals backtests.")

    p.add_argument("--asof", default="", help="기준일(YYYY-MM-DD). 비우면 오늘 날짜(로컬) 사용")
    p.add_argument("--update-latest", action="store_true", help="*_latest.csv 별칭 파일을 생성/갱신")
    p.add_argument("--universe-dir", default=r"D:\Quant\data\universe")

    p.add_argument("--krx-script", default=r"D:\Quant\src\collectors\universe\build_universe_krx.py")
    p.add_argument("--krx-source", default="pykrx", choices=["pykrx", "krx"])
    p.add_argument("--mix-script", default=r"D:\Quant\src\collectors\universe\build_universe_mix_200_200.py")

    p.add_argument("--kospi-topn", type=int, default=200)
    p.add_argument("--kosdaq-topn", type=int, default=200)
    p.add_argument("--mix-size", type=int, default=400)
    p.add_argument("--ticker-col", default="ticker")

    p.add_argument("--price-db", default=r"D:\Quant\data\db\price.db")
    p.add_argument("--price-table", default="prices_daily")
    p.add_argument("--price-start", default="2017-02-08")
    p.add_argument("--price-end", default=None, help="기본: --asof")
    p.add_argument("--price-script", default=r"D:\Quant\src\collectors\price\price_backfill.py")
    p.add_argument("--price-mode", choices=["missing-only", "full", "skip"], default="missing-only")
    p.add_argument("--tail-lookback-days", type=int, default=7)
    p.add_argument("--price-sleep", type=float, default=0.2)
    p.add_argument("--price-retries", type=int, default=2)

    p.add_argument("--no-regime", action="store_true")
    p.add_argument("--regime-years", type=int, default=10)
    p.add_argument("--regime-db", default=r"D:\Quant\data\db\regime.db")
    p.add_argument("--regime-table", default="regime_history")

    p.add_argument("--dart-db", default=r"D:\Quant\data\db\dart_main.db")
    p.add_argument("--dart-start-year", type=int, default=2015)
    p.add_argument("--dart-end-year", type=int, default=2024)

    p.add_argument("--no-fund", action="store_true")
    p.add_argument("--fund-script", default=r"D:\Quant\src\fundamentals\build_fundamentals_monthly.py")
    p.add_argument("--fund-out-db", default=r"D:\Quant\data\db\fundamentals.db")
    p.add_argument("--fund-out-table", default=None)
    p.add_argument("--fund-start", default="2017-02-08")
    p.add_argument("--fund-end", default=None, help="기본: --asof (단, 실행 시 월말 스냅 적용)")

    p.add_argument("--dry-run", action="store_true")

    return p.parse_args()


def main() -> None:
    args = parse_args()

    project_root = _find_project_root(Path(__file__))
    cwd = project_root

    asof = args.asof.strip() or datetime.now().strftime("%Y-%m-%d")
    asof_yyyymmdd = asof.replace("-", "")

    universe_dir = Path(args.universe_dir)
    universe_dir.mkdir(parents=True, exist_ok=True)

    price_target_end = (args.price_end or asof).strip()
    fund_target_end = (args.fund_end or asof).strip()

    paths = build_paths(project_root, universe_dir, asof_yyyymmdd, args.kospi_topn, args.kosdaq_topn, args.mix_size)
    fund_table = args.fund_out_table or f"fundamentals_monthly_mix{args.mix_size}_latest"

    price_db_max_before = _get_price_db_max_date(Path(args.price_db), args.price_table)

    print("================================================================================")
    print("[PIPELINE CONFIG]")
    print("--------------------------------------------------------------------------------")
    print(f"project_root       : {project_root}")
    print(f"asof               : {asof}")
    print(f"price_target_end   : {price_target_end}")
    print(f"price_db_max_before: {price_db_max_before}")
    print(f"fund_target_end    : {fund_target_end}")
    print(f"universe_dir       : {universe_dir}")
    print(f"krx_script         : {args.krx_script}")
    print(f"mix_script         : {args.mix_script}")
    print(f"price_db           : {args.price_db} :: {args.price_table}")
    print(f"price_mode         : {args.price_mode} (new_start={args.price_start}, target_end={price_target_end})")
    print(f"tail_lookback_days : {args.tail_lookback_days}")
    print(f"update_latest      : {args.update_latest}")
    print(f"regime_enable      : {(not args.no_regime)} (years={args.regime_years})")
    print(f"fund_enable        : {(not args.no_fund)} (out={args.fund_out_db}::{fund_table})")
    print(f"dry_run            : {args.dry_run}")
    print("================================================================================")

    # 1) Build top universes
    _run(
        [
            sys.executable,
            str(Path(args.krx_script)),
            "--market",
            "KOSPI",
            "--topn",
            str(args.kospi_topn),
            "--asof",
            asof_yyyymmdd,
            "--source",
            args.krx_source,
        ],
        cwd=cwd,
        dry_run=args.dry_run,
    )
    _run(
        [
            sys.executable,
            str(Path(args.krx_script)),
            "--market",
            "KOSDAQ",
            "--topn",
            str(args.kosdaq_topn),
            "--asof",
            asof_yyyymmdd,
            "--source",
            args.krx_source,
        ],
        cwd=cwd,
        dry_run=args.dry_run,
    )

    # 2) Mix
    _run(
        [
            sys.executable,
            str(Path(args.mix_script)),
            "--kospi-file",
            str(paths.kospi_top),
            "--kosdaq-file",
            str(paths.kosdaq_top),
            "--out",
            str(paths.mix_universe),
            "--ticker-col",
            args.ticker_col,
            "--asof",
            asof,
        ],
        cwd=cwd,
        dry_run=args.dry_run,
    )

    # 3) Price backfill + priceready universe
    final_universe_for_price_regime = paths.mix_universe  # will become priceready
    if args.price_mode != "skip" and not args.dry_run:
        mix_df = _load_universe(paths.mix_universe, args.ticker_col)
        tickers = mix_df[args.ticker_col].tolist()

        if args.price_mode == "full":
            todo_all = sorted(set(map(_zfill6, tickers)))
            _run(
                [
                    sys.executable,
                    str(Path(args.price_script)),
                    "--tickers",
                    ",".join(todo_all),
                    "--start",
                    args.price_start,
                    "--end",
                    price_target_end,
                    "--sleep",
                    str(args.price_sleep),
                    "--retries",
                    str(args.price_retries),
                    "--db",
                    args.price_db,
                ],
                cwd=cwd,
                dry_run=args.dry_run,
            )
        else:
            missing_end = _price_missing_tickers(Path(args.price_db), args.price_table, tickers, price_target_end)
            missing_any = _price_any_rows_tickers(Path(args.price_db), args.price_table, tickers)

            new_tickers = sorted(set(missing_any))
            tail_tickers = sorted(set(missing_end) - set(missing_any))

            print(
                f"[INFO] price check target_end={price_target_end} | universe={len(tickers)} | "
                f"missing_end={len(missing_end)} (tail={len(tail_tickers)} + new={len(new_tickers)})"
            )

            if new_tickers:
                _run(
                    [
                        sys.executable,
                        str(Path(args.price_script)),
                        "--tickers",
                        ",".join(new_tickers),
                        "--start",
                        args.price_start,
                        "--end",
                        price_target_end,
                        "--sleep",
                        str(args.price_sleep),
                        "--retries",
                        str(args.price_retries),
                        "--db",
                        args.price_db,
                    ],
                    cwd=cwd,
                    dry_run=args.dry_run,
                )
            else:
                print("[INFO] new ticker backfill skipped: no new tickers.")

            if tail_tickers:
                tail_start = _date_shift(price_target_end, -int(args.tail_lookback_days))
                print(f"[INFO] tail backfill range start={tail_start} end={price_target_end} (grouped)")
                _run(
                    [
                        sys.executable,
                        str(Path(args.price_script)),
                        "--tickers",
                        ",".join(tail_tickers),
                        "--start",
                        tail_start,
                        "--end",
                        price_target_end,
                        "--sleep",
                        str(args.price_sleep),
                        "--retries",
                        str(args.price_retries),
                        "--db",
                        args.price_db,
                    ],
                    cwd=cwd,
                    dry_run=args.dry_run,
                )
            else:
                print("[INFO] tail backfill skipped: no tail-missing tickers.")

        remaining = _price_missing_tickers(Path(args.price_db), args.price_table, tickers, price_target_end)
        if remaining:
            before, after = _write_universe_excluding(paths.mix_universe, paths.mix_universe_priceready, args.ticker_col, remaining)
            print(f"[WARN] priceready universe generated: before={before} after={after} (dropped missing_end={len(remaining)})")
        else:
            mix_df.to_csv(paths.mix_universe_priceready, index=False, encoding="utf-8-sig")
            print(f"[INFO] priceready universe = original. Copied -> {paths.mix_universe_priceready}")

        final_universe_for_price_regime = paths.mix_universe_priceready

    elif args.price_mode != "skip" and args.dry_run:
        print("[DRY-RUN] price backfill/priceready step would run here.")
        final_universe_for_price_regime = paths.mix_universe_priceready
    else:
        print("[INFO] price step skipped (--price-mode skip).")
        final_universe_for_price_regime = paths.mix_universe

    price_db_max_after = _get_price_db_max_date(Path(args.price_db), args.price_table)
    effective_end = _safe_min_date_str(price_target_end, price_db_max_after) or price_target_end
    print(f"[INFO] price_db_max_after={price_db_max_after} | effective_end(for regime/fund base)={effective_end}")

    # 4) Regime rebuild (priceready 기준)
    if not args.no_regime:
        _ensure_regime_table_schema(Path(args.regime_db), args.regime_table)
        _run(
            [
                sys.executable,
                "-m",
                "src.regime.build_regime_history",
                "--universe-file",
                str(final_universe_for_price_regime),
                "--ticker-col",
                args.ticker_col,
                "--price-db",
                args.price_db,
                "--years",
                str(args.regime_years),
                "--end",
                effective_end,
                "--regime-db",
                args.regime_db,
                "--regime-table",
                args.regime_table,
            ],
            cwd=cwd,
            dry_run=args.dry_run,
        )

    # 5) Fundamentals monthly (fundready 기준 + 월말 스냅)
    fundready_file: Optional[Path] = None
    fund_end_effective: Optional[str] = None

    if not args.no_fund:
        fundready_file, miss_fs, before_rows, after_rows = _filter_universe_by_fs_annual(
            dart_db=Path(args.dart_db),
            universe_file=final_universe_for_price_regime,
            ticker_col=args.ticker_col,
            start_year=int(args.dart_start_year),
            end_year=int(args.dart_end_year),
            out_file=paths.mix_universe_fundready,
        )
        if miss_fs:
            preview = ", ".join(miss_fs[:30])
            suffix = " ..." if len(miss_fs) > 30 else ""
            print(f"[WARN] fs_annual 누락 tickers={len(miss_fs)} (filtered out for fundamentals) | {preview}{suffix}")
        print(f"[INFO] fundready universe: before={before_rows} after={after_rows} -> {fundready_file}")

        # fundamentals end는 월말로 스냅(부분월 제거)
        # - 기준: effective_end (price/db 동기화된 안전 end)
        fund_end_effective = _snap_to_month_end_for_fund(effective_end)
        if fund_end_effective != effective_end:
            print(f"[INFO] fundamentals_end snapped: {effective_end} -> {fund_end_effective}")

        _run(
            [
                sys.executable,
                str(Path(args.fund_script)),
                "--incremental",
                "--dart-db",
                args.dart_db,
                "--universe-file",
                str(fundready_file),
                "--ticker-col",
                args.ticker_col,
                "--price-db",
                args.price_db,
                "--price-table",
                args.price_table,
                "--start",
                args.fund_start,
                "--end",
                fund_end_effective,
                "--out-db",
                args.fund_out_db,
                "--out-table",
                fund_table,
            ],
            cwd=cwd,
            dry_run=args.dry_run,
        )

    # 6) Latest aliases
    if args.update_latest and not args.dry_run:
        _copy_as_latest(paths.kospi_top, universe_dir / f"universe_top{args.kospi_topn}_kospi_latest.csv")
        _copy_as_latest(paths.kosdaq_top, universe_dir / f"universe_top{args.kosdaq_topn}_kosdaq_latest.csv")
        _copy_as_latest(paths.mix_universe, universe_dir / f"universe_mix_top{args.mix_size}_latest.csv")
        _copy_as_latest(final_universe_for_price_regime, universe_dir / f"universe_mix_top{args.mix_size}_latest_priceready.csv")

        # fundready latest도 생성(일관성 핵심)
        if fundready_file is not None:
            _copy_as_latest(fundready_file, universe_dir / f"universe_mix_top{args.mix_size}_latest_fundready.csv")

    # Final universe used(백테스트 기준) = fundready(가능하면), 아니면 priceready
    final_universe_used = fundready_file if fundready_file is not None else final_universe_for_price_regime

    print("\n================================================================================")
    print("[DONE] Outputs")
    print("--------------------------------------------------------------------------------")
    print(f"KOSPI top                  : {paths.kospi_top}")
    print(f"KOSDAQ top                 : {paths.kosdaq_top}")
    print(f"Mix universe               : {paths.mix_universe}")
    print(f"Mix universe (priceready)  : {paths.mix_universe_priceready}")
    print(f"Mix universe (fundready)   : {paths.mix_universe_fundready}")
    print(f"Final universe used        : {final_universe_used}")
    if fund_end_effective is not None:
        print(f"Fundamentals end (snapped) : {fund_end_effective}")
    print("================================================================================")


if __name__ == "__main__":
    main()
