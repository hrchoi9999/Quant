# compare_outputs_legacy_vs_refactor.py ver 2026-02-19_002
"""
Compare legacy vs refactor output CSVs for a given stamp.

What it prints (per file):
- existence in A/B
- shape (rows, cols)
- column diffs (missing/extra)
- optional: key-based sample diff (if key columns exist)

Usage examples (PowerShell):
  cd D:\Quant\src\backtest\tests

  python .\compare_outputs_legacy_vs_refactor.py `
    --stamp 3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206 `
    --legacy-dir D:\Quant\reports\backtest_regime_refactor_legacy `
    --refactor-dir D:\Quant\reports\backtest_regime_refactor_refactor

Optional:
  --write-csv  (writes a summary csv into --outdir)
  --outdir D:\Quant\reports\diff_reports
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd


@dataclass
class FileReport:
    filename: str
    legacy_exists: bool
    refactor_exists: bool
    legacy_rows: Optional[int] = None
    legacy_cols: Optional[int] = None
    refactor_rows: Optional[int] = None
    refactor_cols: Optional[int] = None
    cols_missing_in_refactor: Optional[List[str]] = None
    cols_extra_in_refactor: Optional[List[str]] = None
    legacy_path: Optional[str] = None
    refactor_path: Optional[str] = None


def _read_csv(path: Path) -> pd.DataFrame:
    # keep defaults simple; add encoding fallback if needed later
    return pd.read_csv(path)


def _shape_cols(path: Path) -> Tuple[Tuple[int, int], List[str]]:
    df = _read_csv(path)
    return df.shape, list(df.columns)


def _print_list(title: str, items: List[str], limit: int = 50) -> None:
    if not items:
        print(f"{title}: []")
        return
    head = items[:limit]
    suffix = "" if len(items) <= limit else f" ... (+{len(items) - limit} more)"
    print(f"{title}: {head}{suffix}")


def build_filenames(stamp: str) -> List[str]:
    return [
        f"regime_bt_equity_{stamp}.csv",
        f"regime_bt_holdings_{stamp}.csv",
        f"regime_bt_ledger_{stamp}.csv",
        f"regime_bt_perf_windows_{stamp}.csv",
        f"regime_bt_snapshot_{stamp}.csv",
        f"regime_bt_snapshot_{stamp}__trades.csv",
        f"regime_bt_summary_{stamp}.csv",
        f"regime_bt_trades_C_{stamp}.csv",
    ]


def compare_one(fn: str, legacy_dir: Path, refactor_dir: Path) -> FileReport:
    pa = legacy_dir / fn
    pb = refactor_dir / fn
    ra = pa.exists()
    rb = pb.exists()

    rep = FileReport(
        filename=fn,
        legacy_exists=ra,
        refactor_exists=rb,
        legacy_path=str(pa),
        refactor_path=str(pb),
    )

    if not (ra and rb):
        return rep

    (r_a, c_a), cols_a = _shape_cols(pa)
    (r_b, c_b), cols_b = _shape_cols(pb)

    rep.legacy_rows, rep.legacy_cols = r_a, c_a
    rep.refactor_rows, rep.refactor_cols = r_b, c_b

    sa = set(cols_a)
    sb = set(cols_b)
    rep.cols_missing_in_refactor = sorted(sa - sb)
    rep.cols_extra_in_refactor = sorted(sb - sa)

    return rep


def print_report(rep: FileReport) -> None:
    print("=" * 100)
    print(rep.filename)

    if not rep.legacy_exists or not rep.refactor_exists:
        print(f"legacy exists: {rep.legacy_exists} | refactor exists: {rep.refactor_exists}")
        print(f"legacy path : {rep.legacy_path}")
        print(f"refactor path: {rep.refactor_path}")
        return

    print(f"legacy  shape: ({rep.legacy_rows}, {rep.legacy_cols}) | {rep.legacy_path}")
    print(f"refactor shape: ({rep.refactor_rows}, {rep.refactor_cols}) | {rep.refactor_path}")

    _print_list("cols missing in refactor", rep.cols_missing_in_refactor or [])
    _print_list("cols extra in refactor  ", rep.cols_extra_in_refactor or [])


def to_summary_df(reports: List[FileReport]) -> pd.DataFrame:
    rows = []
    for r in reports:
        rows.append(
            {
                "filename": r.filename,
                "legacy_exists": r.legacy_exists,
                "refactor_exists": r.refactor_exists,
                "legacy_rows": r.legacy_rows,
                "legacy_cols": r.legacy_cols,
                "refactor_rows": r.refactor_rows,
                "refactor_cols": r.refactor_cols,
                "missing_cols_in_refactor": ",".join(r.cols_missing_in_refactor or []),
                "extra_cols_in_refactor": ",".join(r.cols_extra_in_refactor or []),
                "legacy_path": r.legacy_path,
                "refactor_path": r.refactor_path,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stamp", required=True)
    p.add_argument("--legacy-dir", required=True)
    p.add_argument("--refactor-dir", required=True)
    p.add_argument("--write-csv", action="store_true", help="Write summary CSV")
    p.add_argument("--outdir", default=".", help="Where to write summary CSV (if --write-csv)")
    args = p.parse_args()

    legacy_dir = Path(args.legacy_dir).expanduser().resolve()
    refactor_dir = Path(args.refactor_dir).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()

    if not legacy_dir.exists():
        raise FileNotFoundError(f"legacy-dir not found: {legacy_dir}")
    if not refactor_dir.exists():
        raise FileNotFoundError(f"refactor-dir not found: {refactor_dir}")

    files = build_filenames(args.stamp)
    reports = [compare_one(fn, legacy_dir, refactor_dir) for fn in files]

    for rep in reports:
        print_report(rep)

    # Short aggregate
    print("\n" + "=" * 100)
    ok = sum(1 for r in reports if r.legacy_exists and r.refactor_exists)
    miss = len(reports) - ok
    print(f"[SUMMARY] files compared: {ok}/{len(reports)} | missing in either side: {miss}")
    # highlight biggest row gaps (only if both exist)
    gaps = []
    for r in reports:
        if r.legacy_exists and r.refactor_exists and r.legacy_rows is not None and r.refactor_rows is not None:
            gaps.append((abs(r.legacy_rows - r.refactor_rows), r.filename, r.legacy_rows, r.refactor_rows))
    gaps.sort(reverse=True)
    if gaps:
        top = gaps[:5]
        print("[TOP ROW GAPS]")
        for g, fn, ra, rb in top:
            print(f"  {fn}: legacy_rows={ra}, refactor_rows={rb}, gap={g}")

    if args.write_csv:
        outdir.mkdir(parents=True, exist_ok=True)
        df = to_summary_df(reports)
        outpath = outdir / f"diff_summary_{args.stamp}.csv"
        df.to_csv(outpath, index=False, encoding="utf-8-sig")
        print(f"\n[WRITE] {outpath}")


if __name__ == "__main__":
    main()