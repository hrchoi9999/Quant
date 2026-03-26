# run_backtest_s2_refactor_v1.py ver 2026-02-24_004
"""S2 refactor runner (P1-1).

Goal:
  - Run S2 strategy using refactored engine/strategy modules.
  - Produce the SAME CSV artifact set as legacy run_backtest_s2_v5.py:
      equity, summary, holdings, ledger, snapshot, snapshot__trades, trades_C, perf_windows

Design:
  - Engine produces: equity_df(+port_ret), summary_df, holdings_df
  - Output layer (outputs/fill_bundle.py + outputs/legacy_reports.py) produces the rest.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Optional

from .core.data import (
    resolve_project_root,
    load_universe_tickers,
    load_universe_name_map,
    load_universe_market_map,
    load_prices_wide,
    compute_daily_returns,
    load_regime_panel,
    month_end_dates,
    week_anchor_dates,
)
from .core.engine import run_backtest
from .naming import RunId
from .strategies.s2 import StrategyS2
from .outputs.fill_bundle import fill_legacy_outputs
from .outputs.csv_plugin import save_csv_bundle

import pandas as pd

# NOTE: This runner must be executed as a module (python -m src.backtest.run_backtest_s2_refactor_v1)
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    raise RuntimeError(
        "This script must be run as a module. Example: cd <PROJECT_ROOT> && python -m src.backtest.run_backtest_s2_refactor_v1 ..."
    )


def _abs_path(p: str, base: Path) -> str:
    pp = Path(p)
    if pp.is_absolute():
        return str(pp)
    return str((base / pp).resolve())


def _parse_good_regimes(s: str) -> str:
    return str(s).strip() if s is not None else ""


def _load_regime_panel_compat(
    *,
    regime_db: str,
    regime_table: str,
    tickers: list[str],
    horizon: str,
    start: str,
    end: str,
) -> Optional[Any]:
    """Compatibility wrapper for core.data.load_regime_panel.

    The core API evolved across iterations:
      - keyword: horizon (single)
      - keyword: horizons (single or list/tuple)
      - some variants may not accept any horizon keyword (uses default)

    We try multiple call shapes to keep the runner stable.
    """

    base_kwargs: dict[str, Any] = dict(
        regime_db=regime_db,
        regime_table=regime_table,
        tickers=tickers,
        start=start,
        end=end,
    )

    last_err: Optional[Exception] = None
    variants = (
        {"horizons": [horizon]},
        {"horizons": (horizon,)},
        {"horizons": horizon},
        {"horizon": horizon},
        {},
    )

    def _postprocess(panel: Any) -> Any:
        """Normalize regime panel to the canonical *wide* shape expected by StrategyS2.

        StrategyS2 expects a wide frame:
          - index: DatetimeIndex (date)
          - columns: tickers
          - values: regime (or score)

        Some core variants return a long panel (date,ticker,horizon,regime,score).
        Convert long->wide when needed.
        """

        if panel is None:
            return panel

        try:
            import pandas as pd
        except Exception:
            return panel

        if not isinstance(panel, pd.DataFrame) or panel.empty:
            return panel

        cols = set(map(str, panel.columns))

        if {"date", "ticker"}.issubset(cols):
            df = panel.copy()
            if "horizon" in cols and horizon:
                try:
                    df = df[df["horizon"].astype(str) == str(horizon)]
                except Exception:
                    pass

            val_col = "regime" if "regime" in cols else ("score" if "score" in cols else None)
            if val_col is None:
                return panel

            try:
                df["date"] = pd.to_datetime(df["date"])
            except Exception:
                return panel

            try:
                wide = df.pivot(index="date", columns="ticker", values=val_col).sort_index()
                return wide
            except Exception:
                return panel

        # Already wide: enforce DatetimeIndex when possible
        try:
            if not isinstance(panel.index, pd.DatetimeIndex):
                panel = panel.copy()
                panel.index = pd.to_datetime(panel.index)
        except Exception:
            pass

        return panel

    for v in variants:
        try:
            out = load_regime_panel(**base_kwargs, **v)
            return _postprocess(out)
        except TypeError as e:
            last_err = e
            continue

    if last_err is not None:
        raise last_err
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()

    ap.add_argument("--regime-db", required=True)
    ap.add_argument("--regime-table", default="regime_history")

    ap.add_argument("--price-db", required=True)
    ap.add_argument("--price-table", default="prices_daily")

    ap.add_argument("--universe-file", required=True)
    ap.add_argument("--ticker-col", default="ticker")

    ap.add_argument("--horizon", "--primary-horizon", dest="horizon", default="3m")

    ap.add_argument("--good-regimes", default="4,3")
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--min-holdings", type=int, default=15)

    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")

    ap.add_argument("--rebalance", default="M", choices=["M", "W"])
    ap.add_argument("--weekly-anchor-weekday", type=int, default=2)
    ap.add_argument("--weekly-holiday-shift", choices=["prev", "next"], default="prev")

    ap.add_argument("--fundamentals-db", default="")
    ap.add_argument("--fundamentals-view", default="s2_fund_scores_monthly")
    ap.add_argument("--no-fundamentals-asof", action="store_true")

    ap.add_argument("--sma-window", type=int, default=140)
    ap.add_argument("--no-sma-filter", action="store_true")
    ap.add_argument("--require-above-sma", dest="no_sma_filter", action="store_false")

    ap.add_argument("--market-gate", dest="market_gate", action="store_true", default=True)
    ap.add_argument("--no-market-gate", dest="market_gate", action="store_false")
    ap.add_argument("--market-scope", default="KOSPI", choices=["KOSPI", "ALL"])
    ap.add_argument("--market-sma-window", type=int, default=60)
    ap.add_argument("--market-sma-mult", type=float, default=1.00)
    ap.add_argument("--market-exit-mult", type=float, default=1.00)

    ap.add_argument("--exit-below-sma-weeks", type=int, default=2)
    ap.add_argument("--no-exit-below-sma", action="store_true")

    ap.add_argument("--fee-bps", type=float, default=5.0)
    ap.add_argument("--slippage-bps", type=float, default=5.0)

    ap.add_argument("--snapshot-date", default="")
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--trades-lookback-years", type=int, default=6)

    ap.add_argument("--outdir", default=r".\reports\backtest_regime_refactor")

    # Google Sheets upload (optional; legacy feature parity)
    ap.add_argument('--gsheet-enable', action='store_true', help='Upload key CSV outputs to Google Sheets')
    ap.add_argument('--gsheet-cred', default=None, help='Service account json credential path')
    ap.add_argument('--gsheet-id', default=None, help='Target Google Sheet id')
    ap.add_argument('--gsheet-tab', default='snapshot', help='Base tab name for snapshot (others derive from this)')
    ap.add_argument('--gsheet-mode', default='overwrite', choices=['overwrite','append'], help='overwrite or append')
    ap.add_argument('--gsheet-ledger', action='store_true', help='Also upload ledger tab')
    ap.add_argument('--gsheet-prefix', default='S2', help='Prefix used in headers/metadata, if supported')
    args = ap.parse_args(argv)

    orig_cwd = Path.cwd()
    # NOTE: resolve_project_root() signature differs across versions (0-arg vs start_dir arg)
    try:
        project_root = Path(resolve_project_root(str(orig_cwd))).resolve()
    except TypeError:
        project_root = Path(resolve_project_root()).resolve()

    # Normalize paths before chdir
    args.regime_db = _abs_path(args.regime_db, orig_cwd)
    args.price_db = _abs_path(args.price_db, orig_cwd)
    args.universe_file = _abs_path(args.universe_file, orig_cwd)
    if args.fundamentals_db:
        args.fundamentals_db = _abs_path(args.fundamentals_db, orig_cwd)
    args.outdir = _abs_path(args.outdir, orig_cwd)

    os.chdir(project_root)

    tickers = load_universe_tickers(args.universe_file, ticker_col=args.ticker_col)

    # Normalize tickers to 6-digit strings (critical for legacy parity).
    # Many downstream components (fundamentals/regime/SMA filters) assume 6-digit tickers.
    tickers = [str(t).strip().zfill(6) for t in tickers]
    # NOTE: core.data helpers evolved across refactor iterations.
    # Some older variants returned (map, meta) while the current canonical helpers return just a dict.
    _nm = load_universe_name_map(args.universe_file, ticker_col=args.ticker_col)
    name_map = _nm[0] if isinstance(_nm, tuple) else _nm

    _mm = load_universe_market_map(args.universe_file, ticker_col=args.ticker_col)
    market_map = _mm[0] if isinstance(_mm, tuple) else _mm
    # Normalize maps to 6-digit tickers
    name_map = {str(k).strip().zfill(6): str(v) for k, v in (name_map or {}).items()}
    market_map = {str(k).strip().zfill(6): str(v).strip().upper() for k, v in (market_map or {}).items()}
    market_map["CASH"] = "CASH"

    # Broad bounds if omitted (legacy behavior: allow full DB range)
    start_s = args.start or "1900-01-01"
    end_s = args.end or "2100-01-01"

    close_wide = load_prices_wide(
        price_db=str(Path(args.price_db).resolve()),
        price_table=args.price_table,
        tickers=tickers,
        start=start_s,
        end=end_s,
    )
    close_wide = close_wide.sort_index()

    # Ensure price columns are 6-digit tickers (align with strategy/regime/fundamentals)
    close_wide.columns = [str(c).strip().zfill(6) for c in close_wide.columns]
    ret_wide = compute_daily_returns(close_wide)

    start_dt = close_wide.index.min()
    end_dt = close_wide.index.max()

    regime_panel = _load_regime_panel_compat(
        regime_db=str(Path(args.regime_db).resolve()),
        regime_table=args.regime_table,
        tickers=tickers,
        horizon=str(args.horizon),
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
    )
    if regime_panel is not None and len(regime_panel.columns):
        regime_panel.columns = [str(c).strip().zfill(6) for c in regime_panel.columns]

    dates = close_wide.index
    if str(args.rebalance).upper() == "W":
        rb_dates = week_anchor_dates(dates, anchor_weekday=int(args.weekly_anchor_weekday), holiday_shift=str(args.weekly_holiday_shift))
        rb_tag = "W"
    else:
        rb_dates = month_end_dates(dates)
        rb_tag = "M"

    # Strategy config passed via args object
    args.require_above_sma = (not bool(args.no_sma_filter))
    args._market_map = market_map
    args.market_sma_mult = float(args.market_sma_mult)
    args.market_exit_mult = float(args.market_exit_mult)
    args.disable_exit_below_sma = bool(args.no_exit_below_sma)

    strat = StrategyS2(args)

    base = run_backtest(
        close_wide=close_wide,
        ret_wide=ret_wide,
        regime_panel=regime_panel,
        rebalance_dates=rb_dates,
        strategy=strat,
        fee_bps=float(args.fee_bps),
        slippage_bps=float(args.slippage_bps),
        name_map=name_map,
        market_map=market_map,
    )

    # Guard: if holdings are empty (e.g., always cash), create a cash-only holdings history.
    if getattr(base, "holdings_df", None) is None or base.holdings_df.empty:
        base.holdings_df = pd.DataFrame({
            "rebalance_date": pd.to_datetime(rb_dates),
            "ticker": ["CASH"] * len(rb_dates),
            "weight": [1.0] * len(rb_dates),
        })

    if args.no_snapshot:
        filled = base
    else:
        snap_dt = pd.to_datetime(args.snapshot_date) if args.snapshot_date else None
        filled = fill_legacy_outputs(
            base,
            close_wide=close_wide,
            name_map=name_map,
            market_map=market_map,
            top_n=int(args.top_n),
            good_regimes=str(args.good_regimes),
            sma_window=int(args.sma_window),
            require_above_sma=bool(args.require_above_sma),
            fundamentals_view=str(args.fundamentals_view),
            fundamentals_asof=(str(args.rebalance).upper() == "W") and (not bool(args.no_fundamentals_asof)),
            market_gate=bool(args.market_gate),
            market_scope=str(args.market_scope),
            market_sma_window=int(args.market_sma_window),
            market_entry_mult=float(args.market_sma_mult),
            market_exit_mult=float(args.market_exit_mult),
            snapshot_date=snap_dt,
            trades_lookback_years=int(args.trades_lookback_years),
            windows_years=(1, 2, 3, 5),
        )

    run_id = RunId.from_parts(
        horizon=str(args.horizon),
        strategy="S2",
        weight_scheme=f"RB{rb_tag}",
        top_n=int(args.top_n),
        good_regimes=_parse_good_regimes(args.good_regimes),
        sma_window=int(args.sma_window),
        market_gate=bool(args.market_gate),
        exit_below_sma_weeks=int(args.exit_below_sma_weeks),
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
    )

    outdir = Path(args.outdir).resolve()
    bundle = {
        "summary": filled.summary_df,
        "equity": filled.equity_df,
        "holdings": filled.holdings_df,
        "ledger": filled.ledger_df,
        "snapshot": filled.snapshot_df,
        "trades": filled.trades_df,
        "trades_c": filled.trades_c_df,
        "windows": filled.windows_df,
    }

    # Optional diagnostic table (top100 candidates per rebalance)
    try:
        sel_df = None
        if hasattr(filled, "selection_df"):
            sel_df = getattr(filled, "selection_df")
        if sel_df is None and isinstance(getattr(filled, "meta", None), dict):
            sel_df = filled.meta.get("selection_df") or filled.meta.get("selection")
        if isinstance(sel_df, pd.DataFrame) and not sel_df.empty:
            bundle["selection"] = sel_df
    except Exception:
        pass

    saved = save_csv_bundle(outdir=outdir, prefix_map={
        "ledger": "regime_bt_ledger",
        "snapshot": "regime_bt_snapshot",
        "trades": "regime_bt_snapshot__trades",
        "trades_c": "regime_bt_trades_C",
        "windows": "regime_bt_perf_windows",
        "summary": "regime_bt_summary",
        "equity": "regime_bt_equity",
        "holdings": "regime_bt_holdings",
        "selection": "regime_bt_selection",
    }, stamp=run_id.stamp, bundle=bundle)



    # Force-write selection CSV (some save_csv_bundle implementations skip empty/unknown keys)
    try:
        sel_df2 = bundle.get("selection")
        if isinstance(sel_df2, pd.DataFrame):
            sel_path = outdir / f"regime_bt_selection_{run_id.stamp}.csv"
            # Write even if empty (header-only) to make presence explicit.
            sel_df2.to_csv(sel_path, index=False, encoding="utf-8-sig")
            saved["selection"] = str(sel_path)
    except Exception as e:
        print(f"[WARN] selection csv write failed: {e}")

    # Optional: upload CSV bundle to Google Sheets
    if getattr(args, "gsheet_enable", False):
        if not getattr(args, "gsheet_cred", None) or not getattr(args, "gsheet_id", None):
            raise ValueError("--gsheet-enable requires --gsheet-cred and --gsheet-id")

        try:
            from .outputs import gsheet_plugin as gsheet_mod
        except Exception:  # pragma: no cover
            from src.backtest.outputs import gsheet_plugin as gsheet_mod  # type: ignore

        base = getattr(args, "gsheet_tab", "snapshot")
        tab_snapshot = base
        tab_windows = f"{base}_windows"
        tab_trades = f"{base}_trades"
        tab_selection = f"{base}_selection"
        tab_ledger = f"{base}_ledger"

        gsheet_mod.upload_gsheet_bundle(
            snapshot_path=saved.get("snapshot", ""),
            windows_path=saved.get("windows", ""),
            trades_path=saved.get("trades", ""),
            ledger_path=(saved.get("ledger", "") if getattr(args, "gsheet_ledger", False) else None),
            selection_path=saved.get("selection", ""),
            cred_path=args.gsheet_cred,
            sheet_id=args.gsheet_id,
            tab_snapshot=tab_snapshot,
            tab_windows=tab_windows,
            tab_trades=tab_trades,
            tab_ledger=tab_ledger,
            tab_selection=tab_selection,
            mode=args.gsheet_mode,
            prefix=getattr(args, "gsheet_prefix", "S2"),
        )

    # Minimal log (stdout)
    print("[SAVE]")
    for k, pp in saved.items():
        print(f"  {k}: {pp}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
