# scan_quant_repo.py ver 2026-02-05_001
"""
D:\Quant 레포 전체 파일 리스트 생성 + 데이터 업데이트 관련 .py 후보 자동 식별

출력:
- <out_dir>\quant_file_list.csv
- <out_dir>\quant_py_candidates.csv
- <out_dir>\quant_tree.txt
"""

from __future__ import annotations

import csv
import datetime as dt
import os
from pathlib import Path

ROOT_DEFAULT = r"D:\Quant"

# 업데이트/ETL/빌드 관련 후보를 잡기 위한 키워드들
KEYWORDS = [
    "price.db", "prices_daily", "build_price", "update_price", "download_price",
    "regime.db", "regime_history", "build_regime", "update_regime",
    "fundamentals.db", "s2_fund_scores_monthly", "fund_scores", "dart", "fundamental",
    "universe", "top400", "kospi", "kosdaq", "market",
    "etl", "pipeline", "ingest", "refresh", "rebuild",
]

# 너무 큰 폴더는 제외(필요 시 수정)
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".pytest_cache",
    "venv", "venv64", ".venv", "node_modules",
    "reports", "logs", "data",  # 데이터/결과 폴더가 너무 크면 제외하는 게 보통 유리합니다.
}


def should_skip_dir(dir_name: str) -> bool:
    dn = dir_name.lower()
    return dn in {d.lower() for d in EXCLUDE_DIRS}


def safe_read_text(p: Path, max_bytes: int = 600_000) -> str:
    try:
        # 파일이 너무 크면 앞부분만 읽습니다.
        with p.open("rb") as f:
            b = f.read(max_bytes)
        return b.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def main(root: str = ROOT_DEFAULT) -> None:
    root_path = Path(root)
    if not root_path.exists():
        raise SystemExit(f"[ERROR] root not found: {root_path}")

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = root_path / "_scan_outputs" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    file_list_csv = out_dir / "quant_file_list.csv"
    py_candidates_csv = out_dir / "quant_py_candidates.csv"
    tree_txt = out_dir / "quant_tree.txt"

    all_rows = []
    py_rows = []

    # 1) Walk
    for cur, dirs, files in os.walk(root_path):
        # prune dirs
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        cur_path = Path(cur)
        rel_dir = cur_path.relative_to(root_path)

        for fn in files:
            p = cur_path / fn
            try:
                stat = p.stat()
                size = stat.st_size
                mtime = dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
            except Exception:
                size = -1
                mtime = ""

            ext = p.suffix.lower()
            all_rows.append([str(rel_dir), fn, ext, size, mtime])

            # 2) .py 후보 스캔
            if ext == ".py":
                text = safe_read_text(p)
                hit = []
                low = text.lower()
                for kw in KEYWORDS:
                    if kw.lower() in low:
                        hit.append(kw)

                # 파일명 자체도 힌트가 됩니다.
                name_hint = fn.lower()
                name_score = 0
                for h in ["build", "update", "refresh", "etl", "ingest", "download", "make_", "gen_"]:
                    if h in name_hint:
                        name_score += 1

                score = len(hit) * 10 + name_score  # 단순 가중치
                if score > 0:
                    py_rows.append([
                        score,
                        str(rel_dir / fn),
                        ",".join(sorted(set(hit))),
                    ])

    # 3) Write file list CSV
    with file_list_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rel_dir", "file_name", "ext", "size_bytes", "mtime_local"])
        w.writerows(all_rows)

    # 4) Write py candidates CSV (score desc)
    py_rows.sort(key=lambda x: x[0], reverse=True)
    with py_candidates_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["score", "py_path", "matched_keywords"])
        w.writerows(py_rows)

    # 5) Tree (가독용)
    # 깊이 3까지만 간단 트리로 출력
    lines = []
    max_depth = 3
    for rel_dir, fn, ext, size, mtime in all_rows:
        rel = Path(rel_dir) / fn if rel_dir != "." else Path(fn)
        if len(rel.parts) <= max_depth:
            lines.append(str(rel))
    lines = sorted(set(lines))
    with tree_txt.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    print(f"[OK] file list  : {file_list_csv}")
    print(f"[OK] py cand    : {py_candidates_csv}")
    print(f"[OK] tree (<=3) : {tree_txt}")
    print(f"[INFO] scanned root: {root_path}")
    print(f"[INFO] excluded dirs: {sorted(EXCLUDE_DIRS)}")


if __name__ == "__main__":
    main()
