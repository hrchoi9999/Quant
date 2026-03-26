# pick_top10_equity_from_pareto.py ver 2026-02-03_001
"""
Pareto 결과 CSV에서 상위 N개 조합을 뽑아
해당 조합의 equity 파일명을 자동으로 매칭/리스트업합니다.

핵심 아이디어:
- pareto_cagr_vs_mdd_*.csv 에는 각 조합의 파라미터(예: RBW, SMA100, top30, mult1.05 등)가 들어 있음
- equity 파일명도 동일한 패턴을 포함하므로, 파라미터로 파일명을 구성해 찾는다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def project_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(8):
        if (cur / "src").exists() and (cur / "data").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()


def equity_filename(row: pd.Series) -> str:
    """
    파일명 규칙(현재 run_backtest_regime_s2_v2 출력 규칙)에 맞춰 구성합니다.

    예시:
    regime_bt_equity_3m_S2_RBW_top30_GR43_SMA100_MG1_20131014_20260129.csv
    """
    horizon = str(row.get("horizon", "3m"))
    strategy = str(row.get("strategy", "S2"))

    # rebalance (M/W) -> RBM/RBW
    rb = str(row.get("rebalance", "W")).upper()
    rb_tag = "RBW" if rb == "W" else "RBM"

    top_n = int(row.get("top_n", 30))

    # good_regimes 문자열 형태 "4,3"
    gr = str(row.get("good_regimes", "4,3")).replace(",", "")
    gr_tag = f"GR{gr}"

    sma = int(row.get("sma_window", 100))

    # market_gate True/False -> MG1/MG0
    mg = row.get("market_gate", True)
    mg_tag = "MG1" if str(mg).lower() in ("true", "1") else "MG0"

    start = str(row.get("start", "2013-10-14")).replace("-", "")
    end = str(row.get("end", "2026-01-29")).replace("-", "")

    return f"regime_bt_equity_{horizon}_{strategy}_{rb_tag}_top{top_n}_{gr_tag}_SMA{sma}_{mg_tag}_{start}_{end}.csv"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pareto", required=True, help="pareto_cagr_vs_mdd_*.csv 경로")
    ap.add_argument("--reports-dir", default=r"reports/backtest_regime")
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = project_root(Path.cwd())
    pareto_path = (root / args.pareto).resolve() if not Path(args.pareto).is_absolute() else Path(args.pareto)
    if not pareto_path.exists():
        raise FileNotFoundError(pareto_path)

    rep_dir = (root / args.reports_dir).resolve()
    if not rep_dir.exists():
        raise FileNotFoundError(rep_dir)

    df = pd.read_csv(pareto_path)

    # Pareto는 이미 "좋은 순서"로 정렬돼 있다고 가정하지만,
    # 혹시 모르니 CAGR 내림차순으로 topk를 뽑습니다.
    df = df.sort_values("cagr", ascending=False).head(args.topk).copy()

    rows = []
    for _, r in df.iterrows():
        fname = equity_filename(r)
        fpath = rep_dir / fname

        # 혹시 파일명 규칙이 조금 달라졌을 수 있으니,
        # 없으면 부분일치(glob)로 재탐색
        if not fpath.exists():
            # 핵심 키워드로 좁혀 검색
            rb = "RBW" if str(r.get("rebalance", "W")).upper() == "W" else "RBM"
            topn = int(r.get("top_n", 30))
            sma = int(r.get("sma_window", 100))
            mg = "MG1" if str(r.get("market_gate", True)).lower() in ("true", "1") else "MG0"
            pattern = f"regime_bt_equity_*_{rb}_top{topn}_*SMA{sma}_{mg}_*.csv"
            candidates = list(rep_dir.glob(pattern))
            fpath = candidates[0] if candidates else fpath

        rows.append(
            dict(
                cagr=float(r.get("cagr")),
                mdd=float(r.get("mdd")),
                sharpe=float(r.get("sharpe")),
                rebalance=str(r.get("rebalance")),
                top_n=int(r.get("top_n")),
                sma_window=int(r.get("sma_window")),
                market_sma_mult=float(r.get("market_sma_mult")),
                equity_file=str(fpath),
                equity_exists=bool(Path(fpath).exists()),
            )
        )

    out_df = pd.DataFrame(rows)
    out_path = Path(args.out).resolve() if args.out else (pareto_path.parent / f"top{args.topk}_equity_files.csv")
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")

    print("[SAVE]", out_path)
    print(out_df.to_string(index=False))

    # 업로드/전달용: 존재하는 파일만 별도 출력
    ok = out_df[out_df["equity_exists"] == True]["equity_file"].tolist()
    print("\n[UPLOAD THESE FILES]")
    for p in ok:
        print(p)


if __name__ == "__main__":
    main()
