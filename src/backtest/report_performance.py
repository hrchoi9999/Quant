# report_performance.py ver 2025-12-30_002
"""
백테스트 결과 CSV를 읽어서
- 핵심 성과지표(CAGR, Vol, Sharpe, MDD, 월 승률 등) 계산
- 누적 NAV 그래프 PNG 저장
- 월간 수익률 바차트 PNG 저장
- 요약 CSV 저장

출력:
- reports/metrics_<tag>.csv
- reports/equity_curve_<tag>.png
- reports/monthly_returns_<tag>.png
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


@dataclass
class Metrics:
    start: str
    end: str
    months: int
    cagr: float
    vol_annual: float
    sharpe: float
    mdd: float
    win_rate_monthly: float
    best_month: float
    worst_month: float


def _calc_mdd(nav: pd.Series) -> float:
    peak = nav.cummax()
    dd = nav / peak - 1.0
    return float(dd.min())


def calc_metrics(df: pd.DataFrame) -> Metrics:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    nav = df["nav"].astype(float)
    rets = df["ret"].astype(float)

    months = int(len(df))
    start = df["date"].iloc[0].date().isoformat()
    end = df["date"].iloc[-1].date().isoformat()

    # CAGR: 월 수익률 기반 연환산
    total = float(nav.iloc[-1] / nav.iloc[0])
    years = months / 12.0
    cagr = total ** (1 / years) - 1 if years > 0 else np.nan

    # 변동성/샤프: 월 수익률 기준 연환산(무위험 0 가정)
    vol_m = float(rets.std(ddof=1)) if months > 1 else np.nan
    vol_annual = vol_m * np.sqrt(12) if vol_m == vol_m else np.nan
    mean_m = float(rets.mean()) if months > 0 else np.nan
    sharpe = (mean_m / vol_m) * np.sqrt(12) if (vol_m and vol_m > 0) else np.nan

    mdd = _calc_mdd(nav)

    win_rate = float((rets > 0).mean()) if months > 0 else np.nan
    best = float(rets.max()) if months > 0 else np.nan
    worst = float(rets.min()) if months > 0 else np.nan

    return Metrics(
        start=start,
        end=end,
        months=months,
        cagr=float(cagr),
        vol_annual=float(vol_annual),
        sharpe=float(sharpe),
        mdd=float(mdd),
        win_rate_monthly=float(win_rate),
        best_month=float(best),
        worst_month=float(worst),
    )


def plot_equity(df: pd.DataFrame, out_png: Path) -> None:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    plt.figure()
    plt.plot(df["date"], df["nav"])
    plt.xlabel("Date")
    plt.ylabel("NAV")
    plt.title("Equity Curve")
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()


def plot_monthly_returns(df: pd.DataFrame, out_png: Path) -> None:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    plt.figure()
    plt.bar(df["date"], df["ret"])
    plt.xlabel("Date")
    plt.ylabel("Monthly Return")
    plt.title("Monthly Returns")
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity-csv", type=str, required=True, help="백테스트 결과 CSV 경로")
    ap.add_argument("--tag", type=str, default="", help="출력 파일명 태그(비우면 파일명에서 추출)")
    args = ap.parse_args()

    p = Path(args.equity_csv)
    if not p.exists():
        raise FileNotFoundError(p)

    df = pd.read_csv(p)

    # ✅ 이 프로젝트 방침: net 기준으로 리포트 (ret 없으면 ret_net을 ret로 사용)
    if "ret" not in df.columns:
        if "ret_net" in df.columns:
            df["ret"] = df["ret_net"]
        else:
            raise ValueError(f"'ret' 또는 'ret_net' 컬럼이 없습니다. columns={list(df.columns)}")

    # ✅ tag는 항상 정의되도록 (버그 수정 포인트)
    tag = args.tag.strip()
    if not tag:
        # 파일명에서 태그를 추출 (가능하면 prefix 제거)
        stem = p.stem
        tag = stem.replace("backtest_quality_equity_curve_", "")
        tag = tag.replace("backtest_quality_dynuniv_", "")

    reports_dir = p.parent
    out_metrics = reports_dir / f"metrics_{tag}.csv"
    out_eq = reports_dir / f"equity_curve_{tag}.png"
    out_mr = reports_dir / f"monthly_returns_{tag}.png"

    m = calc_metrics(df)
    pd.DataFrame([asdict(m)]).to_csv(out_metrics, index=False, encoding="utf-8-sig")

    plot_equity(df, out_eq)
    plot_monthly_returns(df, out_mr)

    print("[DONE] metrics:", out_metrics)
    print("[DONE] equity :", out_eq)
    print("[DONE] mret   :", out_mr)
    print(pd.DataFrame([asdict(m)]))


if __name__ == "__main__":
    main()
