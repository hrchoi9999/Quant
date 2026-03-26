# build_universe_etf_core.py ver 2026-03-17_003
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    from src.features.calc_liquidity_20d import calc_liquidity_20d
    from src.universe.etf_classifier import classify_etfs, default_rule_paths, load_overrides, load_rules
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / "src").exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.features.calc_liquidity_20d import calc_liquidity_20d
    from src.universe.etf_classifier import classify_etfs, default_rule_paths, load_overrides, load_rules

PROJECT_ROOT = Path(r"D:\Quant")


def _latest_master(universe_dir: Path) -> Path:
    latest = universe_dir / "universe_etf_master_latest.csv"
    if latest.exists():
        return latest
    candidates = sorted(universe_dir.glob("universe_etf_master_*.csv"))
    if not candidates:
        raise FileNotFoundError("No ETF master universe found.")
    return candidates[-1]


def _normalize_asof(s: str) -> str:
    return str(s).strip().replace("-", "")


def _derive_asof_from_path(path: Path) -> str:
    stem = path.stem
    if stem.endswith("latest"):
        df = pd.read_csv(path, nrows=1)
        if "asof" in df.columns and not df.empty:
            return _normalize_asof(str(df.iloc[0]["asof"]))
    part = stem.split("_")[-1]
    return _normalize_asof(part)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build ETF core universe CSV and meta CSV.")
    ap.add_argument("--asof", default="", help="YYYYMMDD or YYYY-MM-DD. Defaults to master CSV asof")
    ap.add_argument("--master-csv", default="")
    ap.add_argument("--price-db", default=str(PROJECT_ROOT / r"data\db\price.db"))
    ap.add_argument("--rules-yml", default="")
    ap.add_argument("--overrides-csv", default="")
    ap.add_argument("--outdir", default=str(PROJECT_ROOT / r"data\universe"))
    args = ap.parse_args()

    universe_dir = PROJECT_ROOT / "data" / "universe"
    master_csv = Path(args.master_csv) if args.master_csv else _latest_master(universe_dir)
    asof = _normalize_asof(args.asof) if args.asof else _derive_asof_from_path(master_csv)
    rules_path_default, overrides_path_default = default_rule_paths()
    rules_path = Path(args.rules_yml) if args.rules_yml else rules_path_default
    overrides_path = Path(args.overrides_csv) if args.overrides_csv else overrides_path_default
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    master_df = pd.read_csv(master_csv, dtype={"ticker": "string"})
    rules = load_rules(rules_path)
    overrides = load_overrides(overrides_path)
    meta_df = classify_etfs(master_df, rules, overrides)

    liq_df = calc_liquidity_20d(
        price_db=Path(args.price_db),
        tickers=meta_df["ticker"].astype(str).tolist(),
        asof=f"{asof[0:4]}-{asof[4:6]}-{asof[6:8]}",
        min_liquidity_20d=float(rules["defaults"].get("min_liquidity_20d", 100000000)),
    )
    meta_df = meta_df.merge(liq_df, on="ticker", how="left")
    meta_df["liquidity_20d_value"] = pd.to_numeric(meta_df["liquidity_20d_value"], errors="coerce").fillna(0.0)
    meta_df["history_days"] = pd.to_numeric(meta_df["history_days"], errors="coerce").fillna(0).astype(int)
    meta_df["min_liquidity_pass"] = meta_df["min_liquidity_pass"].astype("boolean").fillna(False).astype(bool)
    meta_df["asof"] = asof

    candidate_df = meta_df[
        meta_df["min_liquidity_pass"]
        & meta_df["group_key"].astype(str).ne("")
        & (~meta_df["exclude_from_core"])
        & (~meta_df["is_leveraged"])
        & ((~meta_df["is_inverse"]) | (meta_df["group_key"] == "hedge_inverse_kr"))
    ].copy()

    top_k = rules["defaults"].get("top_k_by_group", {})
    core_parts = []
    for group_key, sub in candidate_df.groupby("group_key"):
        limit = int(top_k.get(group_key, 1))
        picked = sub.sort_values(["liquidity_20d_value", "ticker"], ascending=[False, True]).head(limit).copy()
        core_parts.append(picked)
    core_df = pd.concat(core_parts, ignore_index=True) if core_parts else pd.DataFrame(columns=candidate_df.columns)

    core_cols = [
        "ticker",
        "name",
        "asset_type",
        "asset_class",
        "group_key",
        "currency_exposure",
        "is_inverse",
        "is_leveraged",
        "liquidity_20d_value",
        "min_liquidity_pass",
        "asof",
    ]
    core_df = core_df.sort_values(["group_key", "liquidity_20d_value", "ticker"], ascending=[True, False, True]).reset_index(drop=True)
    core_df[core_cols].to_csv(outdir / f"universe_etf_core_{asof}.csv", index=False, encoding="utf-8-sig")
    meta_df.to_csv(outdir / f"etf_meta_{asof}.csv", index=False, encoding="utf-8-sig")

    print(f"[INFO] master_csv={master_csv}")
    print(f"[INFO] rules={rules_path}")
    print(f"[INFO] overrides={overrides_path}")
    print(f"[INFO] meta_rows={len(meta_df)}")
    print(f"[INFO] core_rows={len(core_df)}")
    print(f"[INFO] core_csv={outdir / f'universe_etf_core_{asof}.csv'}")
    print(f"[INFO] meta_csv={outdir / f'etf_meta_{asof}.csv'}")


if __name__ == "__main__":
    main()
