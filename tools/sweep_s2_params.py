# sweep_s2_params.py ver 2026-02-03_001
"""
S2 파라미터 스윕 자동 실행 스크립트

목적
- run_backtest_regime_s2_v2.py 를 여러 파라미터 조합으로 반복 실행
- 각 실행에서 생성된 summary CSV를 모아 1개의 결과 테이블로 저장

스윕 그리드(요청 반영)
- sma_window: 60~150 step 10 (10개)
- top_n: 20 / 30 / 50 (3개)

추가(기존 설계 유지)
- rebalance: M / W (2개)
- market_sma_mult: 1.00 / 1.05 / 1.10 (3개)

총 실행 수: 10 * 3 * 2 * 3 = 180회

사용법(예: D:\Quant 루트에서)
(venv64) PS D:\Quant> python .\tools\sweep_s2_params.py

옵션
- --dry-run : 실제 실행 없이 커맨드만 출력
- --max-runs N : 일부만 테스트로 돌리고 싶을 때
- --rebalance-list W : 주간만
- --mult-list 1.05 : 멀티플 하나만
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _project_root(start: Path) -> Path:
    """D:\Quant 루트 추정"""
    cur = start.resolve()
    for _ in range(8):
        if (cur / "src").exists() and (cur / "data").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()


def _run_one(cmd: List[str], cwd: Path, timeout_sec: int) -> Tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
    )
    return proc.returncode, proc.stdout


def _extract_summary_path(stdout: str) -> Optional[str]:
    # Example: [SAVE] D:\Quant\reports\backtest_regime\regime_bt_summary_...
    m = re.findall(r"\[SAVE\]\s+(.*regime_bt_summary_.*\.csv)\s*$", stdout, flags=re.MULTILINE)
    return m[-1].strip() if m else None


def _load_summary_csv(path_str: str) -> pd.DataFrame:
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"summary csv not found: {p}")
    df = pd.read_csv(p)
    df["_summary_path"] = str(p)
    return df


def build_cmd(
    python_exe: str,
    runner: Path,
    common_args: Dict[str, str],
    rebalance: str,
    sma_window: int,
    top_n: int,
    market_sma_mult: float,
) -> List[str]:
    cmd = [
        python_exe,
        str(runner),
        "--strategy", "S2",
        "--rebalance", rebalance,
        "--horizon", common_args["horizon"],
        "--universe-file", common_args["universe_file"],
        "--ticker-col", common_args["ticker_col"],
        "--price-db", common_args["price_db"],
        "--price-table", common_args["price_table"],
        "--regime-db", common_args["regime_db"],
        "--regime-table", common_args["regime_table"],
        "--fundamentals-db", common_args["fundamentals_db"],
        "--fundamentals-view", common_args["fundamentals_view"],
    ]

    if common_args.get("market_gate", "1") == "1":
        cmd.append("--market-gate")

    # 스윕 대상 파라미터
    cmd += ["--sma-window", str(sma_window)]
    cmd += ["--market-sma-window", str(sma_window)]
    cmd += ["--market-sma-mult", f"{market_sma_mult:.2f}"]
    cmd += ["--top-n", str(top_n)]

    # 비용 고정(필요 시 변경 가능)
    cmd += ["--fee-bps", str(common_args["fee_bps"])]
    cmd += ["--slippage-bps", str(common_args["slippage_bps"])]

    return cmd


def main() -> None:
    ap = argparse.ArgumentParser()

    ap.add_argument("--python-exe", default=sys.executable)
    ap.add_argument("--runner", default=str(Path("src/backtest/run_backtest_regime_s2_v2.py")))

    ap.add_argument("--horizon", default="3m")
    ap.add_argument("--universe-file", default=str(Path("data/universe/universe_mix_top400_20260129_fundready.csv")))
    ap.add_argument("--ticker-col", default="ticker")

    ap.add_argument("--price-db", default=str(Path("data/db/price.db")))
    ap.add_argument("--price-table", default="prices_daily")
    ap.add_argument("--regime-db", default=str(Path("data/db/regime.db")))
    ap.add_argument("--regime-table", default="regime_history")

    ap.add_argument("--fundamentals-db", default=str(Path("data/db/fundamentals.db")))
    ap.add_argument("--fundamentals-view", default="vw_s2_top30_monthly")

    ap.add_argument("--market-gate", action="store_true", default=True)
    ap.add_argument("--fee-bps", type=float, default=10.0)
    ap.add_argument("--slippage-bps", type=float, default=10.0)

    # 스윕 범위(요청 반영)
    ap.add_argument("--sma-min", type=int, default=60)
    ap.add_argument("--sma-max", type=int, default=150)
    ap.add_argument("--sma-step", type=int, default=10)
    ap.add_argument("--topn-list", nargs="+", type=int, default=[20, 30, 50])
    ap.add_argument("--rebalance-list", nargs="+", type=str, default=["M", "W"])
    ap.add_argument("--mult-list", nargs="+", type=float, default=[1.00, 1.05, 1.10])

    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-runs", type=int, default=0)  # 0이면 전체
    ap.add_argument("--timeout-sec", type=int, default=60 * 60)

    ap.add_argument("--outdir", default=str(Path("reports/backtest_regime/sweep")))
    ap.add_argument("--outfile", default="", help="비우면 자동 파일명")
    args = ap.parse_args()

    root = _project_root(Path.cwd())
    runner = (root / args.runner).resolve()
    if not runner.exists():
        raise FileNotFoundError(f"runner not found: {runner}")

    common_args = dict(
        horizon=args.horizon,
        universe_file=str((root / args.universe_file).resolve()),
        ticker_col=args.ticker_col,
        price_db=str((root / args.price_db).resolve()),
        price_table=args.price_table,
        regime_db=str((root / args.regime_db).resolve()),
        regime_table=args.regime_table,
        fundamentals_db=str((root / args.fundamentals_db).resolve()),
        fundamentals_view=args.fundamentals_view,
        market_gate="1" if args.market_gate else "0",
        fee_bps=str(args.fee_bps),
        slippage_bps=str(args.slippage_bps),
    )

    sma_values = list(range(args.sma_min, args.sma_max + 1, args.sma_step))

    combos: List[Tuple[str, int, int, float]] = []
    for rb in args.rebalance_list:
        for sma in sma_values:
            for topn in args.topn_list:
                for mult in args.mult_list:
                    combos.append((rb, sma, topn, float(mult)))

    if args.max_runs and args.max_runs > 0:
        combos = combos[: args.max_runs]

    outdir = (root / args.outdir).resolve()
    _ensure_dir(outdir)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = args.outfile.strip() or f"s2_sweep_results_{stamp}.csv"
    outpath = (outdir / outfile).resolve()

    meta = dict(
        created_at=datetime.now().isoformat(timespec="seconds"),
        root=str(root),
        runner=str(runner),
        grid=dict(
            sma_values=sma_values,
            topn_list=args.topn_list,
            rebalance_list=args.rebalance_list,
            mult_list=args.mult_list,
        ),
        common_args=common_args,
    )
    (outdir / f"s2_sweep_meta_{stamp}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[INFO] root={root}")
    print(f"[INFO] runner={runner}")
    print(f"[INFO] total_runs={len(combos)}")
    print(f"[INFO] outpath={outpath}")

    rows_out: List[pd.DataFrame] = []
    errors: List[Dict[str, str]] = []

    for i, (rb, sma, topn, mult) in enumerate(combos, start=1):
        cmd = build_cmd(
            python_exe=args.python_exe,
            runner=runner,
            common_args=common_args,
            rebalance=rb,
            sma_window=sma,
            top_n=topn,
            market_sma_mult=mult,
        )

        print(f"\n[{i:03d}/{len(combos):03d}] rb={rb} sma={sma} top_n={topn} mult={mult:.2f}")

        if args.dry_run:
            print(" ".join(cmd))
            continue

        rc, out = _run_one(cmd, cwd=root, timeout_sec=args.timeout_sec)
        summary_path = _extract_summary_path(out)

        if rc != 0 or not summary_path:
            errors.append(
                dict(
                    idx=str(i),
                    rb=str(rb),
                    sma=str(sma),
                    top_n=str(topn),
                    mult=f"{mult:.2f}",
                    returncode=str(rc),
                    summary_path=str(summary_path or ""),
                    tail=out[-2000:],
                )
            )
            print("[WARN] run failed or summary not found.")
            continue

        try:
            df = _load_summary_csv(summary_path)
            df["rebalance"] = rb
            df["sma_window"] = sma
            df["top_n"] = topn
            df["market_sma_mult"] = mult
            rows_out.append(df)
            print(f"[OK] summary={summary_path}")
        except Exception as e:
            errors.append(
                dict(
                    idx=str(i),
                    rb=str(rb),
                    sma=str(sma),
                    top_n=str(topn),
                    mult=f"{mult:.2f}",
                    returncode=str(rc),
                    summary_path=str(summary_path),
                    tail=f"load_summary_error: {e}",
                )
            )
            print(f"[WARN] summary load failed: {e}")

    if args.dry_run:
        print("\n[DRY-RUN] done.")
        return

    if rows_out:
        all_df = pd.concat(rows_out, ignore_index=True)
        all_df.to_csv(outpath, index=False, encoding="utf-8-sig")
        print(f"\n[SAVE] {outpath}")

    if errors:
        err_path = outdir / f"s2_sweep_errors_{stamp}.csv"
        pd.DataFrame(errors).to_csv(err_path, index=False, encoding="utf-8-sig")
        print(f"[SAVE] {err_path}")
        print(f"[INFO] errors={len(errors)}")

    print("[INFO] sweep done.")


if __name__ == "__main__":
    main()
