# analyze_s2_sweep.py ver 2026-02-03_001
"""
S2 파라미터 스윕 결과 분석 스크립트

입력
- sweep_s2_params.py가 만든 통합 결과 CSV (s2_sweep_results_*.csv)

출력
- summary_stats_*.csv : 전체 요약 통계
- corr_numeric_*.csv : 수치형 상관행렬
- group_agg_*.csv : (rebalance, sma, top_n, mult)별 평균/중앙값
- top_*.csv : CAGR/Sharpe/MDD/Score 기준 상위 랭킹
- pareto_*.csv : CAGR vs -|MDD| 파레토 전선
- scatter_*.png : (옵션) 리밸런싱별 CAGR-MDD 산점도 (단색)

사용 예
(venv64) PS D:\Quant> python .\tools\analyze_s2_sweep.py --input .\reports\backtest_regime\sweep\s2_sweep_results_YYYYMMDD_HHMMSS.csv
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _project_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(8):
        if (cur / "src").exists() and (cur / "data").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()


def add_objective_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["mdd_abs"] = out["mdd"].abs()

    # 점수(예시): CAGR 우선 + MDD 페널티
    out["score_cagr_mdd"] = out["cagr"] - 1.5 * out["mdd_abs"]
    out["score_cagr_mdd_strict"] = out["cagr"] - 3.0 * out["mdd_abs"]

    # 점수(예시): Sharpe 우선 + MDD 페널티
    out["score_sharpe_mdd"] = out["sharpe"] - 2.0 * out["mdd_abs"]
    return out


def pareto_front(df: pd.DataFrame, x: str, y: str) -> pd.DataFrame:
    # x, y는 "클수록 좋음"이라고 가정
    d = df.sort_values([x, y], ascending=[False, False]).copy()
    best_y = -np.inf
    keep = []
    for idx, row in d.iterrows():
        if row[y] >= best_y:
            keep.append(idx)
            best_y = row[y]
    return d.loc[keep].sort_values(x, ascending=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="sweep 결과 CSV 경로")
    ap.add_argument("--outdir", default=str(Path("reports/backtest_regime/sweep_analysis")))
    ap.add_argument("--topk", type=int, default=30)
    args = ap.parse_args()

    root = _project_root(Path.cwd())
    inpath = (root / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    if not inpath.exists():
        raise FileNotFoundError(f"input not found: {inpath}")

    outdir = (root / args.outdir).resolve()
    _ensure_dir(outdir)

    df = pd.read_csv(inpath)

    # 타입 정리
    for col in ["cagr", "sharpe", "mdd", "avg_daily_ret", "vol_daily"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["sma_window", "top_n", "rebalance_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "market_sma_mult" in df.columns:
        df["market_sma_mult"] = pd.to_numeric(df["market_sma_mult"], errors="coerce")

    df = df.dropna(subset=["cagr", "mdd", "sharpe"])
    df = add_objective_scores(df)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1) 요약 통계
    summary_path = outdir / f"summary_stats_{stamp}.csv"
    df.describe(include="all").to_csv(summary_path, encoding="utf-8-sig")
    print(f"[SAVE] {summary_path}")

    # 2) 상관(수치형)
    numeric_cols = [c for c in ["sma_window", "top_n", "market_sma_mult", "cagr", "mdd", "sharpe", "vol_daily", "rebalance_count"] if c in df.columns]
    corr_path = outdir / f"corr_numeric_{stamp}.csv"
    df[numeric_cols].corr(numeric_only=True).to_csv(corr_path, encoding="utf-8-sig")
    print(f"[SAVE] {corr_path}")

    # 3) 그룹 요약(평균/중앙값)
    group_cols = [c for c in ["rebalance", "sma_window", "top_n", "market_sma_mult"] if c in df.columns]
    g = df.groupby(group_cols, dropna=False).agg(
        n=("cagr", "count"),
        cagr_mean=("cagr", "mean"),
        cagr_med=("cagr", "median"),
        mdd_mean=("mdd", "mean"),
        mdd_med=("mdd", "median"),
        sharpe_mean=("sharpe", "mean"),
        sharpe_med=("sharpe", "median"),
    ).reset_index()
    g_path = outdir / f"group_agg_{stamp}.csv"
    g.to_csv(g_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {g_path}")

    # 4) 랭킹 저장
    def save_top(sort_col: str, asc: bool, name: str) -> None:
        t = df.sort_values(sort_col, ascending=asc).head(args.topk).copy()
        p = outdir / f"top_{name}_{stamp}.csv"
        t.to_csv(p, index=False, encoding="utf-8-sig")
        print(f"[SAVE] {p}")

    save_top("cagr", False, "cagr")
    save_top("sharpe", False, "sharpe")
    save_top("mdd", False, "mdd_best")  # mdd는 -0.05 > -0.30 이므로 내림차순이 '좋음'
    save_top("score_cagr_mdd", False, "score_cagr_mdd")
    save_top("score_cagr_mdd_strict", False, "score_cagr_mdd_strict")
    save_top("score_sharpe_mdd", False, "score_sharpe_mdd")

    # 5) Pareto (CAGR vs -|MDD|)
    df["mdd_abs"] = df["mdd"].abs()
    df["mdd_neg_abs"] = -df["mdd_abs"]
    pf = pareto_front(df, x="cagr", y="mdd_neg_abs")
    pf_path = outdir / f"pareto_cagr_vs_mdd_{stamp}.csv"
    pf.to_csv(pf_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {pf_path}")

    # 6) 산점도(리밸런싱별, 단색)
    if "rebalance" in df.columns:
        for rb, d in df.groupby("rebalance"):
            fig = plt.figure()
            plt.scatter(d["mdd"], d["cagr"])
            plt.xlabel("MDD (negative)")
            plt.ylabel("CAGR")
            plt.title(f"S2 sweep: CAGR vs MDD | rebalance={rb}")
            png = outdir / f"scatter_cagr_vs_mdd_rebalance_{rb}_{stamp}.png"
            fig.savefig(png, dpi=160, bbox_inches="tight")
            plt.close(fig)
            print(f"[SAVE] {png}")

    # 7) SMA 영향(리밸런싱별 평균)
    if "sma_window" in df.columns and "rebalance" in df.columns:
        sma_tbl = df.groupby(["rebalance", "sma_window"], dropna=False).agg(
            n=("cagr", "count"),
            cagr_mean=("cagr", "mean"),
            mdd_mean=("mdd", "mean"),
            sharpe_mean=("sharpe", "mean"),
        ).reset_index()
        sma_path = outdir / f"sma_effect_{stamp}.csv"
        sma_tbl.to_csv(sma_path, index=False, encoding="utf-8-sig")
        print(f"[SAVE] {sma_path}")

    print("[INFO] analysis done.")


if __name__ == "__main__":
    main()
