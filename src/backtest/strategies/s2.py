# src/backtest/strategies/s2.py ver 2026-02-23_002
"""S2 strategy (refactor path) - legacy compatible.

Implements the legacy S2(v2) selection logic used by run_backtest_s2_v5.py:
- Fundamentals candidates from monthly view (score_rank ascending).
- Regime filter: keep tickers in good_regimes.
- Optional per-ticker SMA filter (require_above_sma).
- Optional market gate (synthetic market proxy from scope average return, hysteresis).
- Optional exit_below_sma_weeks: for held tickers, if close<SMA for N consecutive rebalance decisions, force exit.

Engine applies decisions from NEXT trading day (legacy semantics).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
import sqlite3

from src.backtest.strategies.base import Strategy, RebalanceDecision


def _z6(x: str) -> str:
    return str(x).strip().zfill(6)


def _parse_good_regimes(v) -> List[int]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [int(x) for x in v]
    s = str(v).strip().strip("[]")
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out: List[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except Exception:
            pass
    return out


def _load_fund_dates(fundamentals_db: str, fundamentals_view: str) -> List[pd.Timestamp]:
    if not fundamentals_db or not fundamentals_view:
        return []
    con = sqlite3.connect(fundamentals_db)
    try:
        q = f"SELECT DISTINCT date FROM {fundamentals_view} ORDER BY date"
        df = pd.read_sql_query(q, con)
    finally:
        con.close()
    if df.empty:
        return []
    return [pd.to_datetime(d) for d in df["date"].tolist()]


def _fund_date_asof(fund_dates: List[pd.Timestamp], asof: pd.Timestamp) -> Optional[pd.Timestamp]:
    if not fund_dates:
        return None
    lo = None
    for d in fund_dates:
        if d <= asof:
            lo = d
        else:
            break
    return lo


def load_s2_topn_candidates(
    fundamentals_db: str,
    fundamentals_view: str,
    date: pd.Timestamp,
    universe_tickers: List[str],
    top_n: int,
    max_rank: Optional[int] = None,
) -> pd.DataFrame:
    """Fetch S2 candidates for a rebalance date from the monthly view."""
    if not fundamentals_db or not fundamentals_view:
        return pd.DataFrame()

    dt = pd.to_datetime(date).strftime("%Y-%m-%d")
    tickers = [_z6(t) for t in universe_tickers]
    rank_cap = int(max_rank) if (max_rank is not None) else int(top_n)

    con = sqlite3.connect(fundamentals_db)
    try:
        ph = ",".join(["?"] * len(tickers))
        sql = f"""
            SELECT date, ticker, growth_score, score_rank
            FROM {fundamentals_view}
            WHERE date = ?
              AND score_rank <= ?
              AND ticker IN ({ph})
            ORDER BY score_rank ASC
        """
        params = [dt, rank_cap] + tickers
        df = pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()

    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df


@dataclass
class S2Config:
    fundamentals_db: str
    fundamentals_view: str
    fundamentals_asof: bool = True
    top_n: int = 30
    min_holdings: int = 1
    good_regimes: Optional[List[int]] = None
    sma_window: int = 140
    require_above_sma: bool = True
    market_gate: bool = True
    market_scope: str = "KOSPI"  # 'KOSPI' or 'ALL'
    market_sma_window: int = 60
    market_sma_mult: float = 1.02  # alias for entry_mult
    market_entry_mult: float = 1.02
    market_exit_mult: float = 1.00
    exit_below_sma_weeks: int = 2
    enable_exit_below_sma: bool = True
    market_map: Optional[Dict[str, str]] = None  # ticker->market


class StrategyS2(Strategy):
    name = "S2"

    def __init__(self, args_or_cfg: Any):
        if isinstance(args_or_cfg, S2Config):
            cfg = args_or_cfg
        else:
            a = args_or_cfg
            cfg = S2Config(
                fundamentals_db=str(getattr(a, "fundamentals_db", "")),
                fundamentals_view=str(getattr(a, "fundamentals_view", "")),
                fundamentals_asof=not bool(getattr(a, "no_fundamentals_asof", False)),
                top_n=int(getattr(a, "top_n", 30)),
                min_holdings=int(getattr(a, "min_holdings", 1)),
                good_regimes=_parse_good_regimes(getattr(a, "good_regimes", None)),
                sma_window=int(getattr(a, "sma_window", 140)),
                require_above_sma=bool(getattr(a, "require_above_sma", False)),
                market_gate=bool(getattr(a, "market_gate", False)),
                market_scope=str(getattr(a, "market_scope", "KOSPI")),
                market_sma_window=int(getattr(a, "market_sma_window", 60)),
                market_entry_mult=float(getattr(a, "market_sma_mult", getattr(a, "market_entry_mult", 1.02))),
                market_exit_mult=float(getattr(a, "market_exit_mult", 1.00)),
                exit_below_sma_weeks=int(getattr(a, "exit_below_sma_weeks", 2)),
                enable_exit_below_sma=not bool(getattr(a, "disable_exit_below_sma", False)),
                market_map=getattr(a, "_market_map", None),
            )

        self.cfg = cfg
        self.good_regimes = cfg.good_regimes or []
        self._fund_dates = _load_fund_dates(cfg.fundamentals_db, cfg.fundamentals_view)
        self._below_sma_streak: Dict[str, int] = {}
        self._last_holdings: List[str] = []
        self._market_state: bool = False  # hysteresis state
        self._last_market_diag: Dict[str, Any] = {}

    def _market_ok(self, close_wide: pd.DataFrame) -> bool:
        if not self.cfg.market_gate:
            return True

        market_map = self.cfg.market_map or {}
        cols = list(close_wide.columns)

        if self.cfg.market_scope.upper() == "KOSPI":
            # Legacy parity: universe market column is filtered via `contains("KOSPI")`, not strict equality.
            scope_cols = [
                t for t in cols
                if "KOSPI" in str(market_map.get(str(t), "")).upper()
            ]
        else:
            scope_cols = cols

        scope_cols = [t for t in scope_cols if t in close_wide.columns]
        if not scope_cols:
            scope_cols = cols

        mret = close_wide[scope_cols].pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0)
        mprice = (1.0 + mret).cumprod()
        msma = mprice.rolling(int(self.cfg.market_sma_window), min_periods=int(self.cfg.market_sma_window)).mean()

        dt = close_wide.index[-1]
        p = float(mprice.loc[dt])
        s = float(msma.loc[dt]) if pd.notna(msma.loc[dt]) else float("nan")
        if not np.isfinite(s):
            return False

        entry_mult = float(self.cfg.market_entry_mult)
        exit_mult = float(self.cfg.market_exit_mult)
        if exit_mult > entry_mult:
            exit_mult, entry_mult = entry_mult, exit_mult

        if not self._market_state:
            if p > (s * entry_mult):
                self._market_state = True
        else:
            if p < (s * exit_mult):
                self._market_state = False

        try:
            entry_th = float(s) * float(entry_mult)
            exit_th = float(s) * float(exit_mult)
        except Exception:
            entry_th, exit_th = float("nan"), float("nan")

        self._last_market_diag = {
            "market_gate": True,
            "market_scope": str(self.cfg.market_scope),
            "scope_tickers": int(len(scope_cols)),
            "market_sma_window": int(self.cfg.market_sma_window),
            "market_sma_mult": float(self.cfg.market_sma_mult),
            "market_entry_mult": float(self.cfg.market_entry_mult),
            "market_exit_mult": float(self.cfg.market_exit_mult),
            "market_price": float(p),
            "market_sma": float(s),
            "market_entry_th": float(entry_th),
            "market_exit_th": float(exit_th),
            "market_ok": bool(self._market_state),
        }
        return bool(self._market_state)

    def decide(
        self,
        *,
        asof: pd.Timestamp,
        close_wide: pd.DataFrame,
        ret_wide: pd.DataFrame,
        regime_panel: pd.DataFrame,
    ) -> RebalanceDecision:
        cfg = self.cfg
        dt = pd.to_datetime(asof)  # asof is a *decision date* (rebalance_date); execution is handled by engine on T+1

        universe_tickers = [str(c) for c in close_wide.columns]

        # Default: no forced exits. Populated only when exit-below-SMA is enabled.
        force_exit: set[str] = set()

        # Market gate -> go CASH
        if cfg.market_gate and not self._market_ok(close_wide):
            self._last_holdings = []
            return RebalanceDecision(weights=pd.Series(0.0, index=universe_tickers), meta=dict(self._last_market_diag))

        # Fundamentals as-of mapping (weekly)
        fund_dt = dt
        if cfg.fundamentals_asof:
            fd = _fund_date_asof(self._fund_dates, dt)
            if fd is not None:
                fund_dt = fd

        cand = load_s2_topn_candidates(
            fundamentals_db=cfg.fundamentals_db,
            fundamentals_view=cfg.fundamentals_view,
            date=fund_dt,
            universe_tickers=universe_tickers,
            top_n=int(cfg.top_n),
            max_rank=int(max(int(cfg.top_n)*10, int(cfg.min_holdings)*10, 300)),
        )
        # Compatibility: some revisions used `fdcand` variable name.
        if 'cand' not in locals() and 'fdcand' in locals():
            cand = fdcand

        if cand.empty:
            self._last_holdings = []
            return RebalanceDecision(weights=pd.Series(0.0, index=universe_tickers))

        # Regime row (wide -> dict)
        if dt not in regime_panel.index:
            rp = regime_panel.loc[regime_panel.index <= dt]
            if rp.empty:
                self._last_holdings = []
                return RebalanceDecision(weights=pd.Series(0.0, index=universe_tickers))
            reg_row = rp.iloc[-1]
        else:
            reg_row = regime_panel.loc[dt]
        reg_map = reg_row.to_dict()

        cand["regime"] = cand["ticker"].map(lambda t: reg_map.get(_z6(t), np.nan))

        
        # Exit-below-SMA streak for currently held tickers
        if cfg.enable_exit_below_sma and int(cfg.exit_below_sma_weeks) > 0:
            sma = close_wide.rolling(int(cfg.sma_window), min_periods=int(cfg.sma_window)).mean()
            sma_row = sma.loc[dt] if dt in sma.index else sma.iloc[-1]
            close_row = close_wide.iloc[-1]

            held = set(self._last_holdings)
            for t in held:
                t6 = _z6(t)
                p = close_row.get(t6, np.nan)
                s = sma_row.get(t6, np.nan)
                below = bool(pd.notna(p) and pd.notna(s) and float(p) < float(s))
                self._below_sma_streak[t6] = int(self._below_sma_streak.get(t6, 0) + 1) if below else 0

            force_exit = {t for t, k in self._below_sma_streak.items() if int(k) >= int(cfg.exit_below_sma_weeks)}

        # Select top_n with legacy-compatible relaxation cascade:
        # When filters are too strict and holdings collapse, relax in stages to secure min_holdings.
        #   0) regime + SMA (if enabled)
        #   1) regime only (drop SMA)
        #   2) SMA only (drop regime)
        #   3) no filters (fundamentals only)
        cand0 = cand.copy()

        # Precompute SMA condition map once (if needed)
        sma_ok_map = None
        if cfg.require_above_sma and int(cfg.sma_window) > 0:
            sma = close_wide.rolling(int(cfg.sma_window), min_periods=int(cfg.sma_window)).mean()
            sma_row = sma.loc[dt] if dt in sma.index else sma.iloc[-1]
            close_row = close_wide.iloc[-1]
            sma_ok_map = {}
            for t in cand0["ticker"].astype(str).tolist():
                t6 = _z6(t)
                p = close_row.get(t6, np.nan)
                s = sma_row.get(t6, np.nan)
                sma_ok_map[t6] = bool(pd.notna(p) and pd.notna(s) and float(p) >= float(s))

        def _apply_filters(use_regime: bool, use_sma: bool) -> pd.DataFrame:
            out = cand0
            if force_exit:
                out = out[~out["ticker"].isin(force_exit)]
            if use_regime and self.good_regimes:
                out = out[out["regime"].isin(self.good_regimes)]
            if use_sma and (sma_ok_map is not None):
                out = out[out["ticker"].map(lambda x: bool(sma_ok_map.get(_z6(x), False)))]
            return out.copy()

        steps = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]

        chosen = None
        best = None
        chosen_step = None
        for use_regime, use_sma in steps:
            c = _apply_filters(use_regime, use_sma)
            if best is None or len(c) > len(best):
                best = c
            if len(c) >= int(cfg.min_holdings):
                chosen = c
                chosen_step = f"regime={int(use_regime)}|sma={int(use_sma)}"
                break
        if chosen is None:
            chosen = best
            chosen_step = "best"

        if chosen is None or chosen.empty:
            self._last_holdings = []
            return RebalanceDecision(weights=pd.Series(0.0, index=universe_tickers))

        # Deterministic tie-break for stable replay (avoid drift on equal score_rank)
        chosen = chosen.sort_values(["score_rank", "ticker"], kind="mergesort").head(int(cfg.top_n))
        picks = chosen["ticker"].astype(str).str.zfill(6).tolist()

        # Legacy semantics: if even after relaxation we cannot reach min_holdings, go CASH.
        if len(picks) < int(cfg.min_holdings):
            picks = []

        self._last_holdings = picks

        weights = pd.Series(0.0, index=universe_tickers)
        if picks:
            w = 1.0 / float(len(picks))
            for t in picks:
                weights[_z6(t)] = w

        meta: Dict[str, Any] = {
            "strategy": "S2",
            "rebalance_date": dt,
            "fund_asof_date": fund_dt,
            "top_n": int(cfg.top_n),
            "min_holdings": int(cfg.min_holdings),
            "good_regimes": ",".join(str(x) for x in (self.good_regimes or [])),
            "sma_window": int(cfg.sma_window),
            "require_above_sma": bool(cfg.require_above_sma),
            "market_gate": bool(cfg.market_gate),
        }
        if bool(cfg.market_gate):
            meta.update(self._last_market_diag or {})

        # candidate diagnostics per ticker (for legacy-compatible holdings CSV enrichment)
        try:
            meta["cand"] = cand.set_index("ticker")[["regime", "growth_score", "score_rank"]].to_dict("index")
        except Exception:
            meta["cand"] = {}

        # selection diagnostics table (top100) for divergence root-cause
        # - includes filter flags and final selection membership
        try:
            ct = cand0.copy()
            ct["ticker"] = ct["ticker"].astype(str).str.zfill(6)
            ct["fund_asof_date"] = pd.to_datetime(fund_dt).strftime("%Y-%m-%d") if fund_dt is not None else ""
            ct["in_good_regime"] = ct["regime"].isin(self.good_regimes) if self.good_regimes else False
            if sma_ok_map is not None:
                ct["above_sma"] = ct["ticker"].map(lambda x: bool(sma_ok_map.get(_z6(x), False)))
            else:
                ct["above_sma"] = False
            ct["forced_exit"] = ct["ticker"].isin(force_exit) if force_exit else False
            picks_set = set([_z6(t) for t in (picks or [])])
            ct["selected"] = ct["ticker"].isin(picks_set)
            ct["filter_step"] = str(chosen_step or "")
            # Keep only top100 by rank for manageable output size
            ct = ct.sort_values(["score_rank", "ticker"], kind="mergesort").head(100)
            meta["cand_table"] = ct[[
                "ticker",
                "fund_asof_date",
                "growth_score",
                "score_rank",
                "regime",
                "in_good_regime",
                "above_sma",
                "forced_exit",
                "selected",
                "filter_step",
            ]].reset_index(drop=True)
        except Exception:
            meta["cand_table"] = pd.DataFrame()

        return RebalanceDecision(weights=weights, meta=meta)
