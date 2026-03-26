# gsheet_uploader.py ver 2026-02-09_002
"""Google Sheets uploader (service-account)

핵심
- pandas DataFrame을 Google Sheets로 업로드합니다.
- Timestamp/Datetime/NaN/numpy scalar 등을 안전 변환하여 "not JSON serializable"를 방지합니다.
- 시트 행/열이 부족하면 자동 확장합니다.

지원 모드
- mode='new_sheet'  : 같은 제목 시트가 있으면 suffix(_2, _3...)로 새 시트 생성
- mode='overwrite'  : 같은 제목 시트가 있으면 내용 Clear 후 A1부터 덮어쓰기

주의
- 본 파일은 D:\\Quant\\src\\utils\\gsheet_uploader.py 로 교체 적용을 전제로 작성되었습니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import math
import re

import pandas as pd

# google deps
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@dataclass
class GSheetConfig:
    cred_path: str
    spreadsheet_id: str
    mode: str = "new_sheet"  # 'new_sheet' | 'overwrite'
    start_cell: str = "A1"


# -------------------------
# Helpers
# -------------------------

def _col_to_a1(col_idx_1based: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA ..."""
    if col_idx_1based <= 0:
        raise ValueError("col_idx_1based must be >= 1")
    n = col_idx_1based
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _a1_range(title: str, start_cell: str, nrows: int, ncols: int) -> str:
    # start_cell like A1
    m = re.fullmatch(r"([A-Z]+)(\d+)", start_cell.strip().upper())
    if not m:
        raise ValueError(f"invalid start_cell: {start_cell}")
    start_col_letters, start_row_str = m.group(1), m.group(2)
    start_row = int(start_row_str)

    # convert letters to index
    def letters_to_idx(letters: str) -> int:
        out = 0
        for ch in letters:
            out = out * 26 + (ord(ch) - 64)
        return out

    start_col = letters_to_idx(start_col_letters)
    end_col = start_col + max(ncols, 1) - 1
    end_row = start_row + max(nrows, 1) - 1
    end_col_letters = _col_to_a1(end_col)
    return f"{title}!{start_col_letters}{start_row}:{end_col_letters}{end_row}"


def _to_cell(v):
    """Cell-safe scalar conversion."""
    if v is None:
        return ""
    # pandas NA/NaT
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass

    # Timestamp / datetime
    if isinstance(v, (pd.Timestamp,)):
        # keep date if time is midnight? still ok with isoformat
        return v.to_pydatetime().isoformat()

    # numpy scalars (avoid importing numpy explicitly)
    tname = type(v).__name__.lower()
    if "int" in tname and hasattr(v, "item"):
        try:
            return int(v.item())
        except Exception:
            pass
    if ("float" in tname or "double" in tname) and hasattr(v, "item"):
        try:
            fv = float(v.item())
            if math.isfinite(fv):
                return fv
            return ""
        except Exception:
            pass

    # python numeric
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            return ""
        return v

    # bool
    if isinstance(v, bool):
        return v

    return str(v)


def dataframe_to_values(df: pd.DataFrame, include_header: bool = True) -> List[List]:
    """Convert DataFrame to 2D list (values) suitable for Sheets API."""
    # ensure column order preserved
    df2 = df.copy()
    rows: List[List] = []
    if include_header:
        rows.append([_to_cell(c) for c in df2.columns.tolist()])

    # faster than applymap and future-proof
    for _, row in df2.iterrows():
        rows.append([_to_cell(x) for x in row.tolist()])
    return rows


# -------------------------
# Google API
# -------------------------

def build_service_from_config(cfg: GSheetConfig):
    creds = service_account.Credentials.from_service_account_file(cfg.cred_path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _get_sheet_metadata(service, spreadsheet_id: str) -> Dict:
    return service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()


def _find_sheet(meta: Dict, title: str) -> Optional[Dict]:
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == title:
            return s
    return None


def _unique_title(meta: Dict, base_title: str) -> str:
    existing = {s.get("properties", {}).get("title") for s in meta.get("sheets", [])}
    if base_title not in existing:
        return base_title
    i = 2
    while True:
        t = f"{base_title}_{i}"
        if t not in existing:
            return t
        i += 1


def _ensure_sheet(service, spreadsheet_id: str, title: str, min_rows: int, min_cols: int, mode: str) -> str:
    """Return actual sheet title (may be suffixed in new_sheet mode)."""
    meta = _get_sheet_metadata(service, spreadsheet_id)
    existing = _find_sheet(meta, title)

    if existing is None:
        # create
        add_req = {"addSheet": {"properties": {"title": title, "gridProperties": {"rowCount": max(1000, min_rows), "columnCount": max(26, min_cols)}}}}
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [add_req]},
        ).execute()
        return title

    # exists
    if mode == "new_sheet":
        new_title = _unique_title(meta, title)
        add_req = {"addSheet": {"properties": {"title": new_title, "gridProperties": {"rowCount": max(1000, min_rows), "columnCount": max(26, min_cols)}}}}
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [add_req]},
        ).execute()
        return new_title

    # overwrite: keep title, but ensure size and clear
    props = existing.get("properties", {})
    sheet_id = props.get("sheetId")
    grid = props.get("gridProperties", {})
    cur_rows = int(grid.get("rowCount", 0) or 0)
    cur_cols = int(grid.get("columnCount", 0) or 0)

    requests = []
    # expand if needed
    target_rows = max(cur_rows, min_rows, 1000)
    target_cols = max(cur_cols, min_cols, 26)
    if (target_rows != cur_rows) or (target_cols != cur_cols):
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet_id, "gridProperties": {"rowCount": target_rows, "columnCount": target_cols}},
                    "fields": "gridProperties(rowCount,columnCount)",
                }
            }
        )

    if requests:
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()

    # clear values
    service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=f"{title}", body={}).execute()
    return title


def _write_values(service, spreadsheet_id: str, range_a1: str, values: List[List]):
    body = {"values": values}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueInputOption="RAW",
        body=body,
    ).execute()


def write_dataframe(
    cfg: GSheetConfig,
    df: pd.DataFrame,
    sheet_title: str,
    *,
    include_header: bool = True,
    chunk_rows: int = 500,
) -> str:
    """Ensure sheet exists, then write df to start_cell. Return final sheet title."""
    service = build_service_from_config(cfg)

    values = dataframe_to_values(df, include_header=include_header)
    nrows = len(values)
    ncols = max((len(r) for r in values), default=0)

    final_title = _ensure_sheet(service, cfg.spreadsheet_id, sheet_title, min_rows=nrows + 5, min_cols=ncols + 2, mode=cfg.mode)

    # chunked writes (avoid request size issues)
    # Always start at cfg.start_cell
    # We'll compute ranges per chunk based on start row
    start_cell = cfg.start_cell
    m = re.fullmatch(r"([A-Z]+)(\d+)", start_cell.strip().upper())
    if not m:
        raise ValueError(f"invalid start_cell: {start_cell}")
    start_col_letters, start_row_str = m.group(1), m.group(2)
    start_row0 = int(start_row_str)

    # header+data already in values
    total = len(values)
    offset = 0
    while offset < total:
        chunk = values[offset : offset + chunk_rows]
        r1 = start_row0 + offset
        # range covers exactly chunk size
        range_a1 = _a1_range(final_title, f"{start_col_letters}{r1}", nrows=len(chunk), ncols=ncols)
        _write_values(service, cfg.spreadsheet_id, range_a1, chunk)
        offset += chunk_rows

    return final_title


# -------------------------
# High-level bundle uploader
# -------------------------

def upload_snapshot_bundle(
    cfg: Optional[GSheetConfig] = None,
    *args,
    **kwargs,
) -> Dict[str, str]:
    """Upload standard backtest artifacts into separate sheets.

    Contract (P0):
      - Preferred (stable) call style:
          upload_snapshot_bundle(cfg, prefix=..., date_yyyymmdd=..., seq=..., snapshot_df=..., ...)
      - Backward-compatible:
          - cfg may be provided as kwarg (cfg=...)
          - stamp/run_id may be provided; if prefix/date_yyyymmdd/seq are missing, we try to parse.
          - upload_frames_new_sheets alias calls are accepted.

    Returns dict {key: sheet_title}.
    """
    # --- normalize cfg ---
    if cfg is None and "cfg" in kwargs:
        cfg = kwargs.pop("cfg")
    if cfg is None and len(args) > 0:
        cfg = args[0]
        args = args[1:]
    if cfg is None or not isinstance(cfg, GSheetConfig):
        raise TypeError("upload_snapshot_bundle: missing or invalid cfg (GSheetConfig)")

    # --- normalize naming inputs ---
    prefix = kwargs.pop("prefix", None)
    date_yyyymmdd = kwargs.pop("date_yyyymmdd", None)
    seq = kwargs.pop("seq", None)

    # accept stamp/run_id for older callers
    stamp = kwargs.pop("stamp", None)
    run_id = kwargs.pop("run_id", None)

    if (prefix is None or date_yyyymmdd is None or seq is None) and (run_id or stamp):
        token = str(run_id or stamp)
        # try patterns:
        #   <prefix>_<YYYYMMDD>_<SEQ3>  (e.g., S2_20260206_001)
        m = re.fullmatch(r"([A-Za-z0-9]+)_(\d{8})_(\d{1,3})", token)
        if m:
            prefix = prefix or m.group(1)
            date_yyyymmdd = date_yyyymmdd or m.group(2)
            if seq is None:
                seq = int(m.group(3))

    # final validation (strict)
    if prefix is None or date_yyyymmdd is None or seq is None:
        raise TypeError("upload_snapshot_bundle: required args missing: prefix, date_yyyymmdd, seq")

    # dataframes
    snapshot_df = kwargs.pop("snapshot_df", None)
    trades_df = kwargs.pop("trades_df", None)
    windows_df = kwargs.pop("windows_df", None)
    trades_c_df = kwargs.pop("trades_c_df", None)
    ledger_df = kwargs.pop("ledger_df", None)

    # backward-compat flags (ignored; presence of df is authoritative)
    kwargs.pop("ledger_enabled", None)
    kwargs.pop("mode", None)

    created: Dict[str, str] = {}
    base = f"{str(prefix)}_{str(date_yyyymmdd)}_{int(seq):03d}"

    if snapshot_df is not None:
        created["snapshot"] = write_dataframe(cfg, snapshot_df, f"{base}_snapshot")
    if trades_df is not None:
        created["trades"] = write_dataframe(cfg, trades_df, f"{base}_trades")
    if windows_df is not None:
        created["windows"] = write_dataframe(cfg, windows_df, f"{base}_windows")
    if trades_c_df is not None:
        created["trades_c"] = write_dataframe(cfg, trades_c_df, f"{base}_trades_c")
    if ledger_df is not None:
        created["ledger"] = write_dataframe(cfg, ledger_df, f"{base}_ledger")

    return created



# Backward-compatible alias (older code may call this name)
upload_frames_new_sheets = upload_snapshot_bundle


if __name__ == "__main__":
    # minimal smoke test (manual)
    pass