# update_all_dbs_daily.py ver 2026-01-29_001

r"""
Daily DB update orchestrator:
  1) price.db  (Top200 incremental update)  -> calls existing script
  2) regime.db (build_regime_history)       -> calls existing module
  3) features.db(build_features_db)         -> calls existing script
  4) market.db (build_market_db)            -> calls existing script (rates best-effort)
  5) market_trading_daily view refresh

Usage (PowerShell):
  cd D:\Quant
  python .\src\pipelines\update_all_dbs_daily.py `
    --end 2026-01-29 `
    --universe-file .\data\universe\universe_top200_kospi_20260127.csv `
    --ticker-col ticker `
    --price-db .\data\db\price.db `
    --price-table prices_daily `
    --regime-db .\data\db\regime.db `
    --regime-table regime_history `
    --features-db .\data\db\features.db `
    --features-table features_daily `
    --market-db .\data\db\market.db `
    --market-table market_daily `
    --years 5

Notes:
- 오늘(2026-01-29) 장 종료 후라면 보통 --end 2026-01-29 로 돌리면 됩니다.
- 사용자께서 “1/27 데이터에서 업데이트”를 원하시면 --end 2026-01-27 로 주면 됩니다.
"""


from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _run(cmd: list[str]) -> None:
    print("\n" + "=" * 100)
    print("[RUN]", " ".join(cmd))
    print("=" * 100)
    subprocess.run(cmd, check=True)


def _parse_date(s: str) -> str:
    # accept YYYY-MM-DD or YYYYMMDD -> normalize to YYYY-MM-DD
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        d = datetime.strptime(s, "%Y%m%d").date()
        return d.strftime("%Y-%m-%d")
    # basic validation
    datetime.strptime(s, "%Y-%m-%d")
    return s


def _refresh_market_view(market_db: Path, view_name: str = "market_trading_daily") -> None:
    con = sqlite3.connect(str(market_db))
    try:
        cur = con.cursor()
        cur.execute(f"drop view if exists {view_name}")
        cur.execute(
            f"""
            create view {view_name} as
            select *
            from market_daily
            where kospi_close  is not null
              and kosdaq_close is not null
              and kospi200_close is not null
            """
        )
        con.commit()
    finally:
        con.close()
    print(f"[OK] refreshed view: {market_db}::{view_name}")


def _print_quick_checks(price_db: Path, regime_db: Path, features_db: Path, market_db: Path) -> None:
    def q1(db: Path, sql: str):
        con = sqlite3.connect(str(db))
        try:
            cur = con.cursor()
            return cur.execute(sql).fetchone()
        finally:
            con.close()

    # price last date (overall)
    print("[CHECK] price.db last date:", q1(price_db, "select max(date) from prices_daily"))
    # regime typeof/dist
    print("[CHECK] regime typeof dist:", q1(regime_db, "select typeof(regime), count(*) from regime_history group by 1"))
    # features last date
    print("[CHECK] features.db last date:", q1(features_db, "select max(date) from features_daily"))
    # market last date
    print("[CHECK] market.db last date:", q1(market_db, "select max(date) from market_daily"))


def main() -> None:
    ap = argparse.ArgumentParser()

    ap.add_argument("--end", type=str, default="", help="YYYY-MM-DD 또는 YYYYMMDD")
    ap.add_argument("--years", type=int, default=5, help="regime build용 lookback years")

    ap.add_argument("--universe-file", type=str, required=True)
    ap.add_argument("--ticker-col", type=str, default="ticker")

    ap.add_argument("--price-db", type=str, default=r".\data\db\price.db")
    ap.add_argument("--price-table", type=str, default="prices_daily")

    ap.add_argument("--regime-db", type=str, default=r".\data\db\regime.db")
    ap.add_argument("--regime-table", type=str, default="regime_history")

    ap.add_argument("--features-db", type=str, default=r".\data\db\features.db")
    ap.add_argument("--features-table", type=str, default="features_daily")

    ap.add_argument("--market-db", type=str, default=r".\data\db\market.db")
    ap.add_argument("--market-table", type=str, default="market_daily")

    # price updater tuning (top200 updater)
    ap.add_argument("--price-updater", type=str, default=r".\src\collectors\price\price_update_top200_daily.py")
    ap.add_argument("--db-max-lag-days", type=int, default=7)
    ap.add_argument("--price-sleep", type=float, default=0.2)
    ap.add_argument("--price-retries", type=int, default=3)

    # module/script paths
    ap.add_argument("--regime-module", type=str, default="src.regime.build_regime_history")
    ap.add_argument("--features-script", type=str, default=r".\src\features\build_features_db.py")
    ap.add_argument("--market-script", type=str, default=r".\src\market\build_market_db.py")

    args = ap.parse_args()

    if not args.end.strip():
        raise SystemExit("ERROR: --end 를 지정해 주세요. (예: --end 2026-01-29)")

    end = _parse_date(args.end)

    proj_root = Path.cwd()
    price_db = (proj_root / args.price_db).resolve()
    regime_db = (proj_root / args.regime_db).resolve()
    features_db = (proj_root / args.features_db).resolve()
    market_db = (proj_root / args.market_db).resolve()

    universe_file = (proj_root / args.universe_file).resolve()

    # 1) price update (Top200)
    _run(
        [
            sys.executable,
            str((proj_root / args.price_updater).resolve()),
            "--universe-file",
            str(universe_file),
            "--ticker-col",
            args.ticker_col,
            "--db",
            str(price_db),
            "--end",
            end,
            "--db-max-lag-days",
            str(args.db_max_lag_days),
            "--sleep",
            str(args.price_sleep),
            "--retries",
            str(args.price_retries),
        ]
    )

    # 2) regime rebuild/upsert (1y/6m/3m are handled inside build_regime_history)
    _run(
        [
            sys.executable,
            "-m",
            args.regime_module,
            "--universe-file",
            str(universe_file),
            "--ticker-col",
            args.ticker_col,
            "--price-db",
            str(price_db),
            "--price-table",
            args.price_table,
            "--years",
            str(args.years),
            "--end",
            end,
            "--regime-db",
            str(regime_db),
            "--regime-table",
            args.regime_table,
        ]
    )

    # 3) features rebuild (현재는 전체 기간 재구축 방식; 추후 "증분+롤링 윈도우"로 최적화 가능)
    _run(
        [
            sys.executable,
            str((proj_root / args.features_script).resolve()),
            "--price-db",
            str(price_db),
            "--price-table",
            args.price_table,
            "--out-db",
            str(features_db),
            "--out-table",
            args.features_table,
            "--universe-file",
            str(universe_file),
            "--ticker-col",
            args.ticker_col,
            "--start",
            "2013-10-14",
            "--end",
            end,
        ]
    )

    # 4) market rebuild (rates는 best-effort; 실패해도 indices/fx만으로 저장)
    _run(
        [
            sys.executable,
            str((proj_root / args.market_script).resolve()),
            "--out-db",
            str(market_db),
            "--out-table",
            args.market_table,
            "--start",
            "2013-10-14",
            "--end",
            end,
        ]
    )

    # 5) view refresh
    _refresh_market_view(market_db)

    # quick checks
    _print_quick_checks(price_db, regime_db, features_db, market_db)
    print("[DONE] all updates completed.")


if __name__ == "__main__":
    main()
