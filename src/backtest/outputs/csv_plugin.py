# csv_plugin.py ver 2026-02-11_001
"""
CSV output plugin.

This module supports BOTH call styles that exist in the repo:

NEW (preferred):
    save_csv_bundle(outdir, prefix_map, stamp, bundle)

LEGACY (backward compatible):
    save_csv_bundle(result, run_id, outdir, save_ledger=True)

Only actually written files are returned (and should be logged by the caller).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Mapping

import pandas as pd


def _safe_save(df: Optional[pd.DataFrame], path: Path) -> bool:
    if df is None:
        return False
    if not isinstance(df, pd.DataFrame) or df.empty:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path.exists()


def _save_bundle_new(
    outdir: Path,
    prefix_map: Mapping[str, str],
    stamp: str,
    bundle: Mapping[str, Optional[pd.DataFrame]],
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, prefix in prefix_map.items():
        df = bundle.get(key)
        # Legacy compatibility:
        # - trades file is named: regime_bt_snapshot_{stamp}__trades.csv
        #   (NOT regime_bt_snapshot__trades_{stamp}.csv)
        if key == "trades":
            p = outdir / f"regime_bt_snapshot_{stamp}__trades.csv"
        else:
            p = outdir / f"{prefix}_{stamp}.csv"
        if _safe_save(df, p):
            out[key] = str(p)
    return out


def _bundle_from_result(result: Any) -> Dict[str, Optional[pd.DataFrame]]:
    """
    Extract canonical dfs from a BacktestResult-like object.
    Accepts:
      - dict-like { 'summary': df, ... } OR { 'summary_df': df, ... }
      - object with attributes summary_df/snapshot_df/...
    """
    def _get(obj: Any, *names: str):
        for n in names:
            if isinstance(obj, dict) and n in obj:
                return obj.get(n)
            if hasattr(obj, n):
                return getattr(obj, n)
        return None

    meta = _get(result, "meta")
    sel_df = None
    try:
        if isinstance(meta, dict):
            sel_df = meta.get("selection") or meta.get("selection_df")
    except Exception:
        sel_df = None

    return {
        "summary": _get(result, "summary", "summary_df"),
        "snapshot": _get(result, "snapshot", "snapshot_df"),
        "equity": _get(result, "equity", "equity_df"),
        "holdings": _get(result, "holdings", "holdings_df"),
        "ledger": _get(result, "ledger", "ledger_df"),
        "trades": _get(result, "trades", "trades_df"),
        "trades_c": _get(result, "trades_c", "trades_c_df"),
        "windows": _get(result, "windows", "windows_df"),
        "selection": _get(result, "selection", "selection_df") or sel_df,
    }


def _default_prefix_map() -> Dict[str, str]:
    return {
        "ledger": "regime_bt_ledger",
        "snapshot": "regime_bt_snapshot",
        # trades file historically uses snapshot prefix + __trades suffix
        "trades": "regime_bt_snapshot__trades",
        "trades_c": "regime_bt_trades_C",
        "windows": "regime_bt_perf_windows",
        "summary": "regime_bt_summary",
        "equity": "regime_bt_equity",
        "holdings": "regime_bt_holdings",
        "selection": "regime_bt_selection",
    }


def save_csv_bundle(*args, **kwargs) -> Dict[str, str]:
    """
    Backward compatible dispatcher.

    NEW signature:
      save_csv_bundle(outdir: Path, prefix_map: Mapping[str,str], stamp: str, bundle: Mapping[str, Optional[pd.DataFrame]])

    LEGACY signature:
      save_csv_bundle(result, run_id, outdir, save_ledger=True)
        - run_id is expected to have .stamp
        - save_ledger is accepted but ledger is saved only if present
    """
    # If caller uses keyword names from NEW signature
    if "outdir" in kwargs and "prefix_map" in kwargs and "stamp" in kwargs and "bundle" in kwargs:
        outdir = Path(kwargs["outdir"])
        prefix_map = kwargs["prefix_map"]
        stamp = str(kwargs["stamp"])
        bundle = kwargs["bundle"]
        return _save_bundle_new(outdir, prefix_map, stamp, bundle)

    # If caller passes NEW positional signature (outdir, prefix_map, stamp, bundle)
    if len(args) == 4 and isinstance(args[0], (str, Path)) and isinstance(args[2], str):
        outdir = Path(args[0])
        prefix_map = args[1]
        stamp = str(args[2])
        bundle = args[3]
        return _save_bundle_new(outdir, prefix_map, stamp, bundle)

    # Legacy signature (result, run_id, outdir, save_ledger=True)
    if len(args) >= 3:
        result = args[0]
        run_id = args[1]
        outdir = Path(args[2])
        stamp = getattr(run_id, "stamp", None) or str(run_id)

        bundle = _bundle_from_result(result)
        prefix_map = _default_prefix_map()
        # optional legacy kwarg (ignored for now but accepted)
        _ = kwargs.get("save_ledger", None)

        return _save_bundle_new(outdir, prefix_map, str(stamp), bundle)

    raise TypeError("save_csv_bundle() received unsupported arguments. Update caller or use the new signature.")
