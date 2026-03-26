# src/tests/regression_s2_smoke.py
import sys
import math
from pathlib import Path
import pandas as pd

REQUIRED_FILES = [
    # 프로젝트에서 실제 파일명이 다를 수 있으니, stamp로 찾는 방식으로 구현
    "regime_bt_summary",
    "regime_bt_perf_windows",
    "regime_bt_equity",
    "regime_bt_snapshot",
]

def find_one(base_dir: Path, prefix: str, stamp: str) -> Path:
    # 예: regime_bt_equity_{stamp}.csv 형태를 찾는다
    candidates = sorted(base_dir.glob(f"{prefix}_{stamp}.csv"))
    if not candidates:
        raise FileNotFoundError(f"missing: {prefix}_{stamp}.csv in {base_dir}")
    return candidates[0]

def approx_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    if a is None or b is None:
        return a == b
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)

def main():
    if len(sys.argv) < 4:
        print("usage: python -m src.tests.regression_s2_smoke <golden_dir> <current_dir> <stamp>")
        sys.exit(2)

    golden_dir = Path(sys.argv[1])
    current_dir = Path(sys.argv[2])
    stamp = sys.argv[3]

    # 1) 필수 파일 존재 확인
    paths_g = {}
    paths_c = {}
    for p in REQUIRED_FILES:
        paths_g[p] = find_one(golden_dir, p, stamp)
        paths_c[p] = find_one(current_dir, p, stamp)

    # 2) Equity 마지막 값 비교 (가장 강력한 스모크)
    g_eq = pd.read_csv(paths_g["regime_bt_equity"])
    c_eq = pd.read_csv(paths_c["regime_bt_equity"])
    # 컬럼명은 프로젝트에 따라 다를 수 있어 후보를 둠
    equity_cols = [col for col in ["equity", "portfolio_value", "pv"] if col in g_eq.columns and col in c_eq.columns]
    if not equity_cols:
        raise ValueError(f"equity-like column not found in equity csv. columns={list(g_eq.columns)}")

    col = equity_cols[0]
    g_last = float(g_eq[col].iloc[-1])
    c_last = float(c_eq[col].iloc[-1])
    if not approx_equal(g_last, c_last, tol=1e-6):
        raise AssertionError(f"[FAIL] last equity mismatch: golden={g_last} current={c_last} (col={col})")

    # 3) Rebalance count 비교(holdings/ledger가 있으면 더 좋지만, equity 기반으로 대체)
    # perf_windows에서 FULL CAGR/MDD/Sharpe 비교
    g_w = pd.read_csv(paths_g["regime_bt_perf_windows"])
    c_w = pd.read_csv(paths_c["regime_bt_perf_windows"])

    # window 구분 컬럼 추정
    wcol_candidates = [x for x in ["window", "label", "period"] if x in g_w.columns and x in c_w.columns]
    if not wcol_candidates:
        # 그래도 최소한 shape 정도는 비교
        if g_w.shape != c_w.shape:
            raise AssertionError(f"[FAIL] perf_windows shape mismatch: golden={g_w.shape} current={c_w.shape}")
    else:
        wcol = wcol_candidates[0]
        # FULL 행 찾기(없으면 첫 행)
        def pick_full(df: pd.DataFrame) -> pd.Series:
            m = df[wcol].astype(str).str.upper().eq("FULL")
            return df[m].iloc[0] if m.any() else df.iloc[0]

        rg = pick_full(g_w)
        rc = pick_full(c_w)

        for metric in ["CAGR", "MDD", "Sharpe", "cagr", "mdd", "sharpe"]:
            if metric in g_w.columns and metric in c_w.columns:
                gv = float(rg[metric])
                cv = float(rc[metric])
                if not approx_equal(gv, cv, tol=1e-6):
                    raise AssertionError(f"[FAIL] {metric} mismatch (FULL): golden={gv} current={cv}")

    # 4) Snapshot 보유 종목(상위 n개) 비교
    g_s = pd.read_csv(paths_g["regime_bt_snapshot"])
    c_s = pd.read_csv(paths_c["regime_bt_snapshot"])

    # ticker 컬럼 추정
    tcol_candidates = [x for x in ["ticker", "code", "symbol"] if x in g_s.columns and x in c_s.columns]
    if tcol_candidates:
        tcol = tcol_candidates[0]
        top_n = 10
        g_top = list(g_s[tcol].astype(str).head(top_n))
        c_top = list(c_s[tcol].astype(str).head(top_n))
        if g_top != c_top:
            raise AssertionError(f"[FAIL] snapshot top{top_n} tickers mismatch:\n  golden={g_top}\n  current={c_top}")

    print("[PASS] S2 smoke regression ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())