from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_GSHEET_CRED = PROJECT_ROOT / r"config\quant-485814-0df3dc750a8d.json"
DEFAULT_GSHEET_ID = "1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs"
REPORT_DIR = PROJECT_ROOT / r"reports\backtest_etf_allocation"


def _today() -> str:
    return date.today().isoformat()


def _find_latest_file(prefix: str, asof_date: str, report_dir: Path) -> Path:
    stamp = asof_date.replace("-", "")
    matches = sorted(report_dir.glob(f"{prefix}_{stamp}_*.csv"), key=lambda p: (p.stat().st_mtime, p.name))
    if not matches:
        raise FileNotFoundError(f"No report file found for prefix={prefix}, asof={asof_date}")
    return matches[-1]


def _load_latest_holdings(weights_path: Path) -> pd.DataFrame:
    df = pd.read_csv(weights_path, dtype={"ticker": str})
    if df.empty:
        raise RuntimeError(f"No rows in weights file: {weights_path}")

    date_col = "trade_date" if "trade_date" in df.columns else ("rebalance_date" if "rebalance_date" in df.columns else None)
    if date_col is None:
        raise RuntimeError(f"Weights file missing date column: {weights_path}")

    latest_date = str(df[date_col].astype(str).max())
    out = df[df[date_col].astype(str) == latest_date].copy()
    if "selected" in out.columns:
        out = out[out["selected"].astype(str).str.lower() == "true"].copy()
    if "weight" in out.columns:
        out["weight"] = pd.to_numeric(out["weight"], errors="coerce").fillna(0.0)
        out = out[out["weight"] > 0].copy()
    if "ticker" in out.columns:
        out = out[out["ticker"].fillna("").astype(str).str.strip() != ""].copy()
        out["ticker"] = out["ticker"].astype(str).str.zfill(6)

    rename_map = {
        "ticker": "ticker",
        "name": "name",
        "market": "market",
        "asset_class": "asset_class",
        "group_key": "group_key",
        "weight": "target_weight",
        "current_weight": "current_weight",
        "price": "price",
        "nav": "nav",
        "mode": "mode",
        "model": "model",
        "rebalance_date": "rebalance_date",
        "trade_date": "trade_date",
    }
    keep_cols = [c for c in rename_map.keys() if c in out.columns]
    out = out[keep_cols].rename(columns={k: v for k, v in rename_map.items() if k in keep_cols})
    out.insert(0, "signal_asof", latest_date)
    return out.sort_values(["group_key", "ticker"], na_position="last").reset_index(drop=True)


def _sync_one(model_code: str, asof_date: str, report_dir: Path, cred_path: Path, sheet_id: str, mode: str) -> dict:
    from src.utils.gsheet_uploader import GSheetConfig, write_dataframe  # type: ignore

    prefix_map = {
        "S4": "s4_alloc_weights",
        "S5": "s5_alloc_weights",
        "S6": "s6_alloc_weights",
    }
    tab_map = {
        "S4": "S4_snapshot",
        "S5": "S5_snapshot",
        "S6": "S6_snapshot",
    }
    if model_code not in prefix_map:
        raise ValueError(f"Unsupported ETF model_code: {model_code}")

    weights_path = _find_latest_file(prefix_map[model_code], asof_date, report_dir)
    df = _load_latest_holdings(weights_path)
    cfg = GSheetConfig(
        cred_path=str(cred_path),
        spreadsheet_id=str(sheet_id),
        mode=str(mode),
        start_cell="A1",
    )
    write_dataframe(cfg, df, tab_map[model_code])
    result = {
        "model_code": model_code,
        "tab": tab_map[model_code],
        "rows": int(len(df)),
        "source": str(weights_path),
        "signal_asof": str(df["signal_asof"].iloc[0]),
    }
    print(f"[OK] {model_code} synced -> {tab_map[model_code]} rows={len(df)} signal_asof={result['signal_asof']}")
    return result


def sync(asof_date: str, report_dir: Path, cred_path: Path, sheet_id: str, mode: str) -> None:
    results = []
    for model_code in ("S4", "S5", "S6"):
        results.append(_sync_one(model_code, asof_date, report_dir, cred_path, sheet_id, mode))
    print(json.dumps(results, ensure_ascii=True))


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=_today(), help="YYYY-MM-DD. Default: today")
    ap.add_argument("--report-dir", default=str(REPORT_DIR))
    ap.add_argument("--gsheet-cred", default=str(DEFAULT_GSHEET_CRED))
    ap.add_argument("--gsheet-id", default=DEFAULT_GSHEET_ID)
    ap.add_argument("--gsheet-mode", default="overwrite", choices=["overwrite", "new_sheet"])
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sync(
        asof_date=args.asof,
        report_dir=Path(args.report_dir),
        cred_path=Path(args.gsheet_cred),
        sheet_id=str(args.gsheet_id),
        mode=str(args.gsheet_mode),
    )
