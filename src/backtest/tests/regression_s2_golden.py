# regression_s2_golden.py ver 2026-02-11_001
from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd

# --- helpers for fixture (golden) management ---------------------------------

def _ensure_dir(path: Path) -> None:
    """Ensure path exists and is a directory.
    If a file exists at the path, rename it and then create a directory.
    """
    if path.exists() and path.is_file():
        bak = path.with_name(path.name + ".FILE.bak")
        if bak.exists():
            bak = path.with_name(path.name + f".FILE.{os.getpid()}.bak")
        path.rename(bak)
    path.mkdir(parents=True, exist_ok=True)


def _sync_golden(golden_dir: Path, current_dir: Path, stamp: str) -> list[Path]:
    """Copy required fixture CSVs from current_dir to golden_dir for the given stamp."""
    _ensure_dir(golden_dir)
    copied: list[Path] = []
    names = [
        f"regime_bt_ledger_{stamp}.csv",
        f"regime_bt_snapshot_{stamp}.csv",
        f"regime_bt_snapshot_{stamp}__trades.csv",
        f"regime_bt_trades_C_{stamp}.csv",
        f"regime_bt_perf_windows_{stamp}.csv",
        f"regime_bt_summary_{stamp}.csv",
        f"regime_bt_equity_{stamp}.csv",
        f"regime_bt_holdings_{stamp}.csv",
    ]
    for name in names:
        src = current_dir / name
        if not src.exists():
            raise FileNotFoundError(f"[sync] missing in current-dir: {src}")
        dst = golden_dir / name
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied

# -----------------------------------------------------------------------------


# Snapshot columns that are informational only; ignore in regression.
IGNORE_SNAPSHOT_COLS = {'name'}



NUM_TOL = 1e-10  # float 허용오차(필요시 CLI로 조정)


@dataclass
class CompareResult:
    ok: bool
    messages: List[str]
    diff_paths: Dict[str, str]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path)


def _find_one(dirpath: Path, prefix: str, stamp: str) -> Path:
    """
    Find exactly one file: <prefix>_{stamp}.csv under dirpath
    Example: regime_bt_summary_{stamp}.csv
    """
    cand = dirpath / f"{prefix}_{stamp}.csv"
    if cand.exists():
        return cand

    # fallback: glob
    matches = list(dirpath.glob(f"{prefix}_{stamp}.csv"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        raise FileNotFoundError(f"Not found: {prefix}_{stamp}.csv in {dirpath}")
    raise RuntimeError(f"Multiple matches for {prefix}_{stamp}.csv in {dirpath}: {matches}")


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    # normalize column names
    df.columns = [c.strip() for c in df.columns]

    # normalize common date columns
    for c in ["date", "start", "end", "snapshot_date", "buy_date", "sell_date"]:
        if c in df.columns:
            # keep as string in CSV comparison to avoid timezone issues
            df[c] = df[c].astype(str)

    # normalize tickers
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)

    return df


def _diff_numeric(a: pd.DataFrame, b: pd.DataFrame, tol: float) -> List[str]:
    """Compare numeric-like columns with tolerance.

    - Skips non-numeric columns safely.
    - Treats boolean as numeric (False=0, True=1) to avoid numpy boolean subtract errors.
    - Coerces object columns to numeric when possible.
    """
    msgs: List[str] = []
    common_cols = [c for c in a.columns if c in b.columns]
    for c in common_cols:
        if c == "issue":
            continue

        s1 = a[c]
        s2 = b[c]

        # Convert booleans to int early
        if pd.api.types.is_bool_dtype(s1) or pd.api.types.is_bool_dtype(s2):
            s1n = s1.astype("int64")
            s2n = s2.astype("int64")
        else:
            # If numeric already, keep. Otherwise attempt coercion.
            if pd.api.types.is_numeric_dtype(s1) and pd.api.types.is_numeric_dtype(s2):
                s1n, s2n = s1, s2
            else:
                s1n = pd.to_numeric(s1, errors="coerce")
                s2n = pd.to_numeric(s2, errors="coerce")

        # If still all-NaN for both, it's not a numeric column; skip.
        if s1n.isna().all() and s2n.isna().all():
            continue

        # Align indexes to avoid label mismatch
        s1n, s2n = s1n.align(s2n, join="inner")
        if len(s1n) == 0:
            continue

        diff = (s1n - s2n).abs()
        max_abs = float(diff.max(skipna=True)) if diff.notna().any() else 0.0
        if max_abs > tol:
            msgs.append(f"[NUM] col={c} max_abs_diff={max_abs:g} tol={tol:g}")
    return msgs


def compare_summary(
    golden: pd.DataFrame,
    current: pd.DataFrame,
    tol: float,
) -> Tuple[bool, List[str], pd.DataFrame]:
    msgs: List[str] = []

    g = _coerce_types(golden.copy())
    c = _coerce_types(current.copy())

    # Drop informational-only columns (e.g., name) from snapshot comparison.
    for col in sorted(list(IGNORE_SNAPSHOT_COLS)):
        if col in g.columns:
            g = g.drop(columns=[col])
        if col in c.columns:
            c = c.drop(columns=[col])

    # summary는 보통 1행. 행 수가 다르면 즉시 fail.
    if len(g) != len(c):
        msgs.append(f"[SUMMARY] row_count mismatch golden={len(g)} current={len(c)}")
        return False, msgs, pd.DataFrame()

    # 컬럼 비교
    g_cols = set(g.columns)
    c_cols = set(c.columns)
    if g_cols != c_cols:
        missing = sorted(list(g_cols - c_cols))
        extra = sorted(list(c_cols - g_cols))
        if missing:
            msgs.append(f"[SUMMARY] missing_cols in current: {missing}")
        if extra:
            msgs.append(f"[SUMMARY] extra_cols in current: {extra}")

    # 공통 컬럼만 비교
    cols = [col for col in g.columns if col in c.columns]
    g2 = g[cols].copy()
    c2 = c[cols].copy()

    # 문자열/비숫자 exact
    for col in cols:
        if not (pd.api.types.is_numeric_dtype(g2[col]) and pd.api.types.is_numeric_dtype(c2[col])):
            neq = (g2[col].astype(str) != c2[col].astype(str))
            if bool(neq.any()):
                msgs.append(f"[SUMMARY] mismatch in non-numeric col={col}")

    # 숫자 tolerance
    msgs.extend(_diff_numeric(g2, c2, tol))

    ok = len(msgs) == 0
    diff_df = pd.DataFrame({"issue": msgs})
    return ok, msgs, diff_df


def compare_snapshot(
    golden: pd.DataFrame,
    current: pd.DataFrame,
    tol: float,
) -> Tuple[bool, List[str], pd.DataFrame]:
    """
    snapshot은 ticker를 키로 정렬/정합 후 비교합니다.

    - golden/current의 ticker set이 다를 수 있으므로, 비교는 공통 ticker 교집합에서 수행합니다.
    - ticker set mismatch는 별도 메시지로 기록합니다.
    """
    msgs: List[str] = []

    g = _coerce_types(golden.copy())
    c = _coerce_types(current.copy())

    key = "ticker"
    if key not in g.columns or key not in c.columns:
        msgs.append("[SNAPSHOT] missing 'ticker' column")
        return False, msgs, pd.DataFrame()

    # 컬럼 비교(스키마)
    g_cols = set(g.columns)
    c_cols = set(c.columns)
    if g_cols != c_cols:
        missing = sorted(list(g_cols - c_cols))
        extra = sorted(list(c_cols - g_cols))
        if missing:
            msgs.append(f"[SNAPSHOT] missing_cols in current: {missing}")
        if extra:
            msgs.append(f"[SNAPSHOT] extra_cols in current: {extra}")

    cols = [col for col in g.columns if col in c.columns]
    g2 = g[cols].copy()
    c2 = c[cols].copy()

    # ticker 중복 처리 (있으면 비교가 불안정하므로 경고 후 첫 행 유지)
    g2[key] = g2[key].astype(str)
    c2[key] = c2[key].astype(str)

    if g2[key].duplicated().any():
        dups = g2.loc[g2[key].duplicated(), key].astype(str).unique().tolist()
        msgs.append(f"[SNAPSHOT] duplicated tickers in golden (keeping first): {dups[:20]}")
        g2 = g2.drop_duplicates(subset=[key], keep="first")

    if c2[key].duplicated().any():
        dups = c2.loc[c2[key].duplicated(), key].astype(str).unique().tolist()
        msgs.append(f"[SNAPSHOT] duplicated tickers in current (keeping first): {dups[:20]}")
        c2 = c2.drop_duplicates(subset=[key], keep="first")

    # ticker set 비교
    g_set = set(g2[key])
    c_set = set(c2[key])
    if g_set != c_set:
        msgs.append(
            "[SNAPSHOT] ticker_set mismatch: "
            f"missing_in_current={sorted(list(g_set - c_set))[:20]} "
            f"extra_in_current={sorted(list(c_set - g_set))[:20]}"
        )

    # 비교는 공통 ticker에서만 수행(인덱스 정합)
    gA = g2.set_index(key).sort_index()
    cA = c2.set_index(key).sort_index()
    common = gA.index.intersection(cA.index)
    if len(common) == 0:
        msgs.append("[SNAPSHOT] no common tickers between golden/current")
        ok = False
        diff_df = pd.DataFrame({"issue": msgs})
        return ok, msgs, diff_df

    gA = gA.loc[common]
    cA = cA.loc[common]

    # 비숫자 exact (공통 ticker 기준)
    for col in cols:
        if col == key:
            continue
        is_num = pd.api.types.is_numeric_dtype(gA[col]) and pd.api.types.is_numeric_dtype(cA[col])
        if not is_num:
            gs = gA[col].astype(str)
            cs = cA[col].astype(str)
            neq = (gs.values != cs.values)
            if bool(neq.any()):
                msgs.append(f"[SNAPSHOT] mismatch in non-numeric col={col}")

    # 숫자 tolerance (공통 ticker 기준)
    msgs.extend(_diff_numeric(gA.reset_index(), cA.reset_index(), tol))

    ok = len(msgs) == 0
    diff_df = pd.DataFrame({"issue": msgs})
    return ok, msgs, diff_df


def run(stamp: str, golden_dir: Path, current_dir: Path, artifacts_dir: Path, tol: float) -> CompareResult:
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    g_sum = _find_one(golden_dir, "regime_bt_summary", stamp)
    g_snp = _find_one(golden_dir, "regime_bt_snapshot", stamp)
    c_sum = _find_one(current_dir, "regime_bt_summary", stamp)
    c_snp = _find_one(current_dir, "regime_bt_snapshot", stamp)

    golden_summary = _read_csv(g_sum)
    current_summary = _read_csv(c_sum)
    golden_snapshot = _read_csv(g_snp)
    current_snapshot = _read_csv(c_snp)

    ok1, msgs1, diff1 = compare_summary(golden_summary, current_summary, tol)
    ok2, msgs2, diff2 = compare_snapshot(golden_snapshot, current_snapshot, tol)

    diff_paths: Dict[str, str] = {}
    if not diff1.empty:
        p = artifacts_dir / f"diff_summary_{stamp}.csv"
        diff1.to_csv(p, index=False, encoding="utf-8-sig")
        diff_paths["summary"] = str(p)
    if not diff2.empty:
        p = artifacts_dir / f"diff_snapshot_{stamp}.csv"
        diff2.to_csv(p, index=False, encoding="utf-8-sig")
        diff_paths["snapshot"] = str(p)

    ok = ok1 and ok2
    msgs = msgs1 + msgs2
    return CompareResult(ok=ok, messages=msgs, diff_paths=diff_paths)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp", required=True, help="Run stamp in filenames (e.g., 3m_S2_RBW_top30_..._20131014_20260206)")
    ap.add_argument("--golden-dir", required=True, help="Directory containing golden summary/snapshot CSV")
    ap.add_argument("--current-dir", required=True, help="Directory containing current summary/snapshot CSV")
    ap.add_argument(
        "--sync-golden",
        dest="sync_golden",
        action="store_true",
        help="If set, copy current CSVs into golden-dir before comparing",
    )
    ap.add_argument("--artifacts-dir", default=str(Path(__file__).resolve().parent / "_artifacts"), help="Diff outputs directory")
    ap.add_argument("--tol", type=float, default=NUM_TOL, help="Numeric tolerance for comparisons")
    args = ap.parse_args()

    if args.sync_golden:
        copied = _sync_golden(Path(args.golden_dir), Path(args.current_dir), args.stamp)
        print(f"[SYNC] copied {len(copied)} files into golden-dir")

    res = run(
        stamp=args.stamp,
        golden_dir=Path(args.golden_dir),
        current_dir=Path(args.current_dir),
        artifacts_dir=Path(args.artifacts_dir),
        tol=args.tol,
    )

    if res.ok:
        print(f"[PASS] golden regression matched for stamp={args.stamp}")
        return

    print(f"[FAIL] golden regression mismatch for stamp={args.stamp}")
    for m in res.messages:
        print(" -", m)
    if res.diff_paths:
        print("[DIFF FILES]")
        for k, v in res.diff_paths.items():
            print(f" - {k}: {v}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
