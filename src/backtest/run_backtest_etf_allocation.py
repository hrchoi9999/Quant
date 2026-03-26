from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

try:
    from src.backtest.configs.etf_allocation_config import EtfAllocationConfig, ExecutionConfig, RegimeMappingConfig
    from src.backtest.core.data import compute_daily_returns, load_prices_wide, load_regime_panel, month_end_dates, week_anchor_dates
    from src.backtest.core.etf_allocation_engine import run_etf_allocation_backtest
    from src.backtest.portfolio.etf_regime_allocator import build_regime_mode_series
    from src.repositories.instrument_repository import InstrumentRepository
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / "src").exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.backtest.configs.etf_allocation_config import EtfAllocationConfig, ExecutionConfig, RegimeMappingConfig
    from src.backtest.core.data import compute_daily_returns, load_prices_wide, load_regime_panel, month_end_dates, week_anchor_dates
    from src.backtest.core.etf_allocation_engine import run_etf_allocation_backtest
    from src.backtest.portfolio.etf_regime_allocator import build_regime_mode_series
    from src.repositories.instrument_repository import InstrumentRepository

PROJECT_ROOT = Path(r"D:\Quant")


def _today() -> str:
    return date.today().isoformat()


def _normalize_date(s: str) -> str:
    return str(s).strip().replace("/", "-")


def _load_core_universe(price_db: Path, asof: str) -> pd.DataFrame:
    repo = InstrumentRepository(price_db)
    core_df = repo.get_etf_core_universe(asof=asof)
    if core_df.empty:
        csv_path = PROJECT_ROOT / "data" / "universe" / f"universe_etf_core_{asof.replace('-', '')}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"ETF core universe not found in repository or csv: {csv_path}")
        core_df = pd.read_csv(csv_path, dtype={"ticker": "string"})
        if "market" not in core_df.columns:
            core_df["market"] = "ETF"
        if "core_eligible" not in core_df.columns:
            core_df["core_eligible"] = 1
    core_df["ticker"] = core_df["ticker"].astype(str).str.zfill(6)
    return core_df


def _build_rebalance_dates(price_index: pd.DatetimeIndex, rebalance: str, anchor_weekday: int, holiday_shift: str) -> list[pd.Timestamp]:
    if str(rebalance).upper() == "W":
        return week_anchor_dates(price_index, anchor_weekday=anchor_weekday, holiday_shift=holiday_shift)
    return month_end_dates(price_index)


def main() -> None:
    ap = argparse.ArgumentParser(description="ETF allocation backtest driven by regime mode and ETF core universe.")
    ap.add_argument("--price-db", default=str(PROJECT_ROOT / r"data\db\price.db"))
    ap.add_argument("--regime-db", default=str(PROJECT_ROOT / r"data\db\regime.db"))
    ap.add_argument("--start", default="2024-01-02")
    ap.add_argument("--end", default=_today())
    ap.add_argument("--asof", default=_today(), help="ETF core universe asof (YYYY-MM-DD)")
    ap.add_argument("--rebalance", default="M", choices=["M", "W"])
    ap.add_argument("--weekly-anchor-weekday", type=int, default=2)
    ap.add_argument("--weekly-holiday-shift", default="prev", choices=["prev", "next"])
    ap.add_argument("--regime-horizon", default="3m")
    ap.add_argument("--fallback-mode", default="neutral", choices=["risk_on", "neutral", "risk_off"])
    ap.add_argument("--force-mode", default="", choices=["", "risk_on", "neutral", "risk_off"])
    ap.add_argument("--fee-bps", type=float, default=5.0)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument("--outdir", default=str(PROJECT_ROOT / r"reports\backtest_etf_allocation"))
    args = ap.parse_args()

    price_db = Path(args.price_db)
    regime_db = Path(args.regime_db)
    start = _normalize_date(args.start)
    end = _normalize_date(args.end)
    asof = _normalize_date(args.asof)

    cfg = EtfAllocationConfig(
        rebalance=str(args.rebalance).upper(),
        regime=RegimeMappingConfig(horizon=str(args.regime_horizon), fallback_mode=str(args.fallback_mode)),
        execution=ExecutionConfig(
            fee_bps=float(args.fee_bps),
            slippage_bps=float(args.slippage_bps),
            rebalance=str(args.rebalance).upper(),
            weekly_anchor_weekday=int(args.weekly_anchor_weekday),
            weekly_holiday_shift=str(args.weekly_holiday_shift),
        ),
    )

    core_df = _load_core_universe(price_db, asof)
    tickers = core_df["ticker"].astype(str).str.zfill(6).drop_duplicates().tolist()
    close_wide = load_prices_wide(price_db=price_db, tickers=tickers, start=start, end=end)
    if close_wide.empty:
        raise RuntimeError("No ETF prices loaded for selected core universe and date range.")
    ret_wide = compute_daily_returns(close_wide).fillna(0.0)
    rebalance_dates = _build_rebalance_dates(
        close_wide.index,
        rebalance=str(args.rebalance).upper(),
        anchor_weekday=int(args.weekly_anchor_weekday),
        holiday_shift=str(args.weekly_holiday_shift),
    )

    regime_panel = load_regime_panel(
        regime_db=regime_db,
        start=start,
        end=end,
        horizons=[str(args.regime_horizon)],
    )
    regime_mode_df = build_regime_mode_series(regime_panel, cfg, force_mode=(str(args.force_mode).lower() or None))

    name_map = {str(r["ticker"]).zfill(6): str(r.get("name", "")) for r in core_df.to_dict("records")}
    market_map = {str(r["ticker"]).zfill(6): str(r.get("market", "ETF")) for r in core_df.to_dict("records")}

    result = run_etf_allocation_backtest(
        close_wide=close_wide,
        ret_wide=ret_wide,
        core_df=core_df,
        rebalance_dates=rebalance_dates,
        regime_mode_df=regime_mode_df,
        cfg=cfg,
        name_map=name_map,
        market_map=market_map,
    )

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    mode_tag = f"_{str(args.force_mode).lower()}" if str(args.force_mode).strip() else ""
    stamp = f"{asof.replace('-', '')}_{str(args.rebalance).upper()}_{start.replace('-', '')}_{end.replace('-', '')}{mode_tag}"
    summary_path = outdir / f"etf_alloc_summary_{stamp}.csv"
    equity_path = outdir / f"etf_alloc_equity_{stamp}.csv"
    weights_path = outdir / f"etf_alloc_weights_{stamp}.csv"
    trades_path = outdir / f"etf_alloc_trades_{stamp}.csv"

    result.summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    result.equity_df.to_csv(equity_path, index=False, encoding="utf-8-sig")
    result.holdings_df.to_csv(weights_path, index=False, encoding="utf-8-sig")
    result.trades_df.to_csv(trades_path, index=False, encoding="utf-8-sig")

    print(f"[OK] summary={summary_path}")
    print(f"[OK] equity={equity_path}")
    print(f"[OK] weights={weights_path}")
    print(f"[OK] trades={trades_path}")
    print(f"[OK] rebalance_dates={len(rebalance_dates)} core_tickers={len(tickers)}")


if __name__ == "__main__":
    main()
