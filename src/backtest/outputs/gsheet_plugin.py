# src/backtest/outputs/gsheet_plugin.py ver 2026-02-24_010
"""
Google Sheet upload plugin.

Goal: be resilient to API drift in src.utils.gsheet_uploader by providing an internal
upload path via Google Sheets API when uploader helpers are missing.

Supported call styles:
1) upload_gsheet_bundle(snapshot_path=..., cred_path=..., sheet_id=..., tab=..., mode=..., ...)
2) upload_gsheet_bundle(result=..., run_id=..., cfg=...)  # best-effort, if result contains paths
3) upload_snapshot_bundle(...) alias

This module intentionally avoids hard dependency on src.utils.gsheet_uploader.upload_frame().
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import os


# ----------------------------
# Internal Sheets API uploader
# ----------------------------

def _col_to_a1(col_idx_0: int) -> str:
    """0-based column index to Excel/Sheets column letters."""
    n = col_idx_0 + 1
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def _a1_range(tab: str, nrows: int, ncols: int, start_cell: str = "A1") -> str:
    # Only supports A1 start for now (good enough for this project).
    start_cell = (start_cell or "A1").upper()
    if start_cell != "A1":
        # Keep simple; advanced offsets can be added later.
        start_cell = "A1"
    end_col = _col_to_a1(max(ncols - 1, 0))
    end_row = max(nrows, 1)
    return f"{_sheet_ref(tab)}!A1:{end_col}{end_row}"


def _sheet_ref(tab: str) -> str:
    """Return A1-safe sheet reference (always quoted)."""
    safe = (tab or "").replace("'", "''")
    return f"'{safe}'"


def _ensure_tab_exists(*, svc, sheet_id: str, tab: str) -> None:
    """Create a sheet(tab) if it doesn't exist.

    Missing tabs frequently surface as:
      "Unable to parse range: <tab>!A1:..."
    """
    tab = str(tab)
    sheet = svc.spreadsheets()
    meta = sheet.get(spreadsheetId=sheet_id, fields="sheets(properties(title))").execute()
    titles = {s["properties"]["title"] for s in meta.get("sheets", []) if s.get("properties")}
    if tab in titles:
        return

    req = {"requests": [{"addSheet": {"properties": {"title": tab}}}]}
    sheet.batchUpdate(spreadsheetId=sheet_id, body=req).execute()

def _upload_via_google_api(
    *,
    cred_path: str,
    sheet_id: str,
    tab: str,
    df: pd.DataFrame,
    mode: str = "overwrite",
    start_cell: str = "A1",
    include_header: bool = True,
) -> None:
    """
    Upload dataframe to Google Sheet using googleapiclient.
    mode:
      - overwrite: clear tab then write
      - append: append rows (does not clear)
    """
    mode = (mode or "overwrite").lower()

    # Lazy imports so base backtest runs even when google deps are absent.
    from google.oauth2 import service_account  # type: ignore
    from googleapiclient.discovery import build  # type: ignore

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_file(cred_path, scopes=scopes)
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Ensure tab exists to prevent "Unable to parse range" errors.
    _ensure_tab_exists(svc=svc, sheet_id=sheet_id, tab=tab)

    # Prepare values
    values = []
    if include_header:
        values.append([str(c) for c in df.columns.tolist()])
    # Convert NaN to empty string for sheets
    for row in df.itertuples(index=False, name=None):
        values.append(["" if (x is None or (isinstance(x, float) and pd.isna(x)) or pd.isna(x)) else x for x in row])

    sheet = svc.spreadsheets()
    if mode == "overwrite":
        # Clear the tab (best effort)
        try:
            sheet.values().clear(spreadsheetId=sheet_id, range=f"{_sheet_ref(tab)}").execute()
        except Exception:
            # Some APIs require explicit A1 ranges; ignore and proceed to update.
            pass
        rng = _a1_range(tab, nrows=len(values), ncols=len(values[0]) if values else len(df.columns), start_cell=start_cell)
        sheet.values().update(
            spreadsheetId=sheet_id,
            range=rng,
            valueInputOption="RAW",
            body={"values": values},
        ).execute()
    elif mode == "append":
        rng = f"{_sheet_ref(tab)}!A1"
        sheet.values().append(
            spreadsheetId=sheet_id,
            range=rng,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values[1:] if include_header else values},
        ).execute()
    else:
        raise ValueError(f"Unsupported gsheet mode: {mode!r} (use overwrite|append)")


def _upload_frame(
    *,
    cred_path: str,
    sheet_id: str,
    tab: str,
    df: pd.DataFrame,
    mode: str = "overwrite",
    start_cell: str = "A1",
    include_header: bool = True,
) -> None:
    """
    Prefer src.utils.gsheet_uploader helpers if they exist; otherwise use internal API uploader.
    """
    try:
        from src.utils import gsheet_uploader as uploader  # type: ignore
        # Try common helper names
        for fn_name in ("upload_frame", "upload_df", "upload_dataframe", "write_frame", "write_df", "upsert_frame"):
            fn = getattr(uploader, fn_name, None)
            if callable(fn):
                # Try calling with flexible kwargs
                try:
                    return fn(
                        cred_path=cred_path,
                        sheet_id=sheet_id,
                        tab=tab,
                        df=df,
                        mode=mode,
                        start_cell=start_cell,
                        include_header=include_header,
                    )
                except TypeError:
                    # Try alternative parameter names
                    try:
                        return fn(cred_path, sheet_id, tab, df, mode)  # type: ignore[misc]
                    except TypeError:
                        try:
                            return fn(cred_path=cred_path, spreadsheet_id=sheet_id, worksheet=tab, dataframe=df, mode=mode)  # type: ignore[misc]
                        except TypeError:
                            # Fall back to internal
                            break
    except Exception:
        pass

    return _upload_via_google_api(
        cred_path=cred_path,
        sheet_id=sheet_id,
        tab=tab,
        df=df,
        mode=mode,
        start_cell=start_cell,
        include_header=include_header,
    )


# ----------------------------
# Public API
# ----------------------------

def upload_gsheet_bundle(*args: Any, **kwargs: Any) -> None:
    """
    Upload snapshot bundle to Google Sheet.

    Keyword-based call (preferred):
      upload_gsheet_bundle(
        snapshot_path="...csv",
        cred_path="...json",
        sheet_id="...",
        tab="S2_snapshot",
        mode="overwrite",
        ledger_path="...csv" (optional),
        trades_path="...csv" (optional),
        selection_path="...csv" (optional),
        prefix="S2" (optional),
      )

    Legacy call:
      upload_gsheet_bundle(result=<BacktestResult>, run_id="...", cfg=dict(...))
      (best-effort; will look for paths in cfg or result attributes)
    """
    # If called in legacy positional style, try to extract cfg/result
    if args and not kwargs:
        # Expect (result, run_id, cfg) or similar
        if len(args) >= 3 and isinstance(args[2], dict):
            kwargs = dict(args[2])  # cfg
            kwargs.setdefault("result", args[0])
            kwargs.setdefault("run_id", args[1])
        else:
            raise TypeError("upload_gsheet_bundle() called with unsupported positional arguments")

    # Normalize keys
    snapshot_path = kwargs.get("snapshot_path") or kwargs.get("snapshot_csv") or kwargs.get("snapshot")
    cred_path = kwargs.get("cred_path") or kwargs.get("gsheet_cred") or kwargs.get("credential_path")
    sheet_id = kwargs.get("sheet_id") or kwargs.get("gsheet_id") or kwargs.get("spreadsheet_id")
    tab = kwargs.get("tab") or kwargs.get("gsheet_tab") or "S2_snapshot"
    mode = kwargs.get("mode") or kwargs.get("gsheet_mode") or "overwrite"
    prefix = kwargs.get("prefix") or kwargs.get("gsheet_prefix") or ""

    ledger_path = kwargs.get("ledger_path") or kwargs.get("ledger_csv")
    trades_path = kwargs.get("trades_path") or kwargs.get("trades_csv") or kwargs.get("trade_path")
    selection_path = kwargs.get("selection_path") or kwargs.get("selection_csv")
    windows_path = kwargs.get("windows_path") or kwargs.get("perf_windows_path") or kwargs.get("perf_windows_csv")

    # Best-effort from cfg/result
    result = kwargs.get("result")
    if snapshot_path is None and result is not None:
        for attr in ("snapshot_path", "snapshot_csv", "snapshot_file"):
            if hasattr(result, attr):
                snapshot_path = getattr(result, attr)
                break

    if not (snapshot_path and cred_path and sheet_id):
        raise ValueError(
            "Missing required gsheet parameters. Need snapshot_path, cred_path, sheet_id "
            f"(got snapshot_path={bool(snapshot_path)}, cred_path={bool(cred_path)}, sheet_id={bool(sheet_id)})"
        )

    snapshot_path = str(snapshot_path)

    # Derive perf-windows path from snapshot path if not provided
    if not windows_path:
        try:
            sp = snapshot_path
            if "regime_bt_snapshot_" in sp:
                cand = sp.replace("regime_bt_snapshot_", "regime_bt_perf_windows_", 1)
                if os.path.exists(cand):
                    windows_path = cand
        except Exception:
            windows_path = None

    cred_path = str(cred_path)
    sheet_id = str(sheet_id)

    # Upload snapshot
    df_snapshot = pd.read_csv(snapshot_path)
    _upload_frame(cred_path=cred_path, sheet_id=sheet_id, tab=str(tab), df=df_snapshot, mode=str(mode), include_header=True)

    # Optional additional tabs
    def _tab_name(base: str, suffix: str) -> str:
        if prefix:
            return f"{prefix}_{suffix}"
        return f"{base}_{suffix}"

    if ledger_path:
        df_ledger = pd.read_csv(str(ledger_path))
        _upload_frame(cred_path=cred_path, sheet_id=sheet_id, tab=_tab_name(str(tab), "ledger"), df=df_ledger, mode=str(mode), include_header=True)

    if trades_path:
        df_trades = pd.read_csv(str(trades_path))
        _upload_frame(cred_path=cred_path, sheet_id=sheet_id, tab=_tab_name(str(tab), "trades"), df=df_trades, mode=str(mode), include_header=True)

    if selection_path:
        df_sel = pd.read_csv(str(selection_path))
        _upload_frame(cred_path=cred_path, sheet_id=sheet_id, tab=_tab_name(str(tab), "selection"), df=df_sel, mode=str(mode), include_header=True)

    if windows_path:
        df_win = pd.read_csv(str(windows_path))
        _upload_frame(cred_path=cred_path, sheet_id=sheet_id, tab=_tab_name(str(tab), "windows"), df=df_win, mode=str(mode), include_header=True)


def upload_snapshot_bundle(*args: Any, **kwargs: Any) -> None:
    """Compatibility alias."""
    return upload_gsheet_bundle(*args, **kwargs)
