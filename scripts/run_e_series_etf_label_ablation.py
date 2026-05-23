from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_e_series_etf_mart_v2 import build_e_series_mart_v2


REPORT_DIR = ROOT / r"reports\e_series_etf"
STRATEGY_MODEL_CODE = "E-ETF-V01"
RANDOM_STATE = 42

LABEL_SPECS = [
    {
        "label": "e_label_1m_positive",
        "kind": "direction",
        "description": "1M forward return > 0",
    },
    {
        "label": "e_label_1m_drawdown_safe",
        "kind": "risk_control",
        "description": "1M forward return >= 0 and path MDD >= -5%",
    },
    {
        "label": "e_label_role_top1_1m_risk_adj",
        "kind": "sleeve_selection",
        "description": "Top 1 ETF by 1M risk-adjusted return within E-series role",
    },
    {
        "label": "e_label_role_top3_1m_risk_adj",
        "kind": "sleeve_selection",
        "description": "Top 3 ETFs by 1M risk-adjusted return within E-series role",
    },
    {
        "label": "e_label_role_top20pct_1m_risk_adj",
        "kind": "sleeve_selection",
        "description": "Top 20% ETFs by 1M risk-adjusted return within E-series role",
    },
    {
        "label": "e_label_overall_top5_1m_risk_adj",
        "kind": "portfolio_selection",
        "description": "Top 5 ETFs by 1M risk-adjusted return across all ETFs",
    },
    {
        "label": "e_label_overall_top10pct_1m_risk_adj",
        "kind": "portfolio_selection",
        "description": "Top 10% ETFs by 1M risk-adjusted return across all ETFs",
    },
]

FEATURE_MODES = {
    "E_BASELINE": {
        "prefixes": ("e_", "ret_", "vol_", "dd_", "dist_", "ma", "rsi", "liquidity_", "etf_metric_"),
        "categorical": ("e_series_role", "e_market_mode", "asset_class", "group_key", "currency_exposure"),
    },
    "E_MARKET": {
        "prefixes": (
            "e_",
            "ret_",
            "vol_",
            "dd_",
            "dist_",
            "ma",
            "rsi",
            "liquidity_",
            "etf_metric_",
            "qm_market_",
            "qm_risk_",
            "qm_flow_",
        ),
        "categorical": (
            "e_series_role",
            "e_market_mode",
            "asset_class",
            "group_key",
            "currency_exposure",
            "qm_market_market_state_label",
            "qm_risk_volatility_regime_label",
        ),
    },
    "E_ROLE_AWARE": {
        "prefixes": (
            "e_",
            "ret_",
            "vol_",
            "dd_",
            "dist_",
            "ma",
            "rsi",
            "liquidity_",
            "etf_metric_",
            "qm_market_",
            "qm_risk_",
            "qm_flow_",
            "ri_",
        ),
        "categorical": (
            "e_series_role",
            "raw_role_key",
            "role_key_derived",
            "e_market_mode",
            "asset_class",
            "group_key",
            "currency_exposure",
            "qm_market_market_state_label",
            "qm_risk_volatility_regime_label",
        ),
    },
}

LEAK_PREFIXES = ("label_", "e_label_", "fwd_", "path_mdd_", "risk_adj_")
LEAK_EXACT = {
    "signal_date",
    "feature_date",
    "ticker",
    "name",
    "strategy_family",
    "strategy_model_code",
}


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _json_value(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if pd.isna(value):
            return None
        return round(float(value), 8)
    if pd.isna(value):
        return None
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict("records")]


def _load_or_build_mart(asof: str, rebuild_mart: bool) -> pd.DataFrame:
    token = _token(asof)
    path = REPORT_DIR / f"e_series_etf_mart_v2_{token}.csv"
    if rebuild_mart or not path.exists():
        build_e_series_mart_v2(asof)
    mart = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    mart["ticker"] = mart["ticker"].astype(str).str.zfill(6)
    mart["signal_date"] = pd.to_datetime(mart["signal_date"], errors="coerce")
    return mart


def _is_leak(col: str) -> bool:
    if col in LEAK_EXACT:
        return True
    if col.startswith(LEAK_PREFIXES):
        return True
    if col.startswith("end_date_"):
        return True
    return False


def _feature_columns(df: pd.DataFrame, mode: str) -> tuple[list[str], list[str]]:
    cfg = FEATURE_MODES[mode]
    numeric: list[str] = []
    categorical: list[str] = []
    categorical_set = set(cfg["categorical"])
    for col in df.columns:
        if _is_leak(col):
            continue
        if col in categorical_set:
            categorical.append(col)
            continue
        if not col.startswith(cfg["prefixes"]):
            continue
        numeric_values = pd.to_numeric(df[col], errors="coerce")
        if numeric_values.notna().sum() == 0:
            continue
        if pd.api.types.is_numeric_dtype(df[col]) or numeric_values.notna().mean() > 0.8:
            numeric.append(col)
        else:
            categorical.append(col)
    numeric = sorted(set(numeric))
    categorical = sorted(set(categorical))
    return numeric, categorical


def _fit_model(train: pd.DataFrame, numeric: list[str], categorical: list[str]) -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            ),
        ],
        remainder="drop",
    )
    model = GradientBoostingClassifier(random_state=RANDOM_STATE, n_estimators=160, max_depth=3)
    return Pipeline([("preprocess", pre), ("model", model)]).fit(train[numeric + categorical], train["_target"])


def _evaluate(mart: pd.DataFrame, label: str, mode: str, train_end: str, valid_start: str, asof: str) -> dict[str, Any]:
    use = mart[mart[label].notna()].copy()
    use["_target"] = pd.to_numeric(use[label], errors="coerce")
    use = use[use["_target"].isin([0, 1])].copy()
    train = use[use["signal_date"] <= pd.Timestamp(train_end)].copy()
    valid = use[(use["signal_date"] >= pd.Timestamp(valid_start)) & (use["signal_date"] <= pd.Timestamp(asof))].copy()
    numeric, categorical = _feature_columns(use, mode)
    if train.empty or valid.empty or train["_target"].nunique() < 2 or valid["_target"].nunique() < 2:
        return {
            "label": label,
            "feature_mode": mode,
            "status": "insufficient_data",
            "train_rows": int(len(train)),
            "valid_rows": int(len(valid)),
            "numeric_features": len(numeric),
            "categorical_features": len(categorical),
        }
    clf = _fit_model(train, numeric, categorical)
    prob = clf.predict_proba(valid[numeric + categorical])[:, 1]
    pred = (prob >= 0.5).astype(int)
    scored = valid[["signal_date", "ticker", "name", "e_series_role", "_target"]].copy()
    scored["prob"] = prob
    scored["risk_adj_1m"] = pd.to_numeric(valid.get("risk_adj_1m"), errors="coerce")
    top1 = scored.sort_values(["signal_date", "prob"], ascending=[True, False]).groupby("signal_date").head(1)
    top3 = scored.sort_values(["signal_date", "prob"], ascending=[True, False]).groupby("signal_date").head(3)
    top5 = scored.sort_values(["signal_date", "prob"], ascending=[True, False]).groupby("signal_date").head(5)
    return {
        "label": label,
        "feature_mode": mode,
        "status": "ok",
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "valid_dates": int(valid["signal_date"].nunique()),
        "positive_rate_train": round(float(train["_target"].mean()), 6),
        "positive_rate_valid": round(float(valid["_target"].mean()), 6),
        "auc": round(float(roc_auc_score(valid["_target"], prob)), 6),
        "accuracy": round(float(accuracy_score(valid["_target"], pred)), 6),
        "top1_label_rate": round(float(top1["_target"].mean()), 6) if not top1.empty else None,
        "top3_label_rate": round(float(top3["_target"].mean()), 6) if not top3.empty else None,
        "top5_label_rate": round(float(top5["_target"].mean()), 6) if not top5.empty else None,
        "top1_avg_risk_adj_1m": round(float(top1["risk_adj_1m"].mean()), 6) if not top1.empty else None,
        "top3_avg_risk_adj_1m": round(float(top3["risk_adj_1m"].mean()), 6) if not top3.empty else None,
        "top5_avg_risk_adj_1m": round(float(top5["risk_adj_1m"].mean()), 6) if not top5.empty else None,
        "numeric_features": len(numeric),
        "categorical_features": len(categorical),
    }


def run_ablation(asof: str, train_end: str, valid_start: str, rebuild_mart: bool) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    mart = _load_or_build_mart(asof, rebuild_mart)
    rows = []
    for spec in LABEL_SPECS:
        for mode in FEATURE_MODES:
            rows.append(_evaluate(mart, spec["label"], mode, train_end, valid_start, asof))
    result = pd.DataFrame(rows)
    label_meta = pd.DataFrame(LABEL_SPECS)
    result = result.merge(label_meta, on="label", how="left")
    result = result.sort_values(["status", "auc", "top3_avg_risk_adj_1m"], ascending=[True, False, False], na_position="last")

    token = _token(asof)
    csv_path = REPORT_DIR / f"e_series_etf_label_ablation_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_label_ablation_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_label_ablation_{token}.md"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig")

    best = result[result["status"].eq("ok")].sort_values("auc", ascending=False).head(10)
    payload = {
        "status": "ok",
        "source_name": "e_series_etf_label_ablation",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "train_end": train_end,
        "valid_start": valid_start,
        "mart_rows": int(len(mart)),
        "signal_dates": int(mart["signal_date"].nunique()),
        "feature_modes": list(FEATURE_MODES.keys()),
        "labels": LABEL_SPECS,
        "best_by_auc": _records(best),
        "outputs": {
            "csv": str(csv_path),
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, result)
    return payload


def _write_markdown(path: Path, payload: dict[str, Any], result: pd.DataFrame) -> None:
    lines = [
        "# E Series ETF Label Ablation",
        "",
        f"- strategy model: `{payload['strategy_model_code']}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- train end: `{payload['train_end']}`",
        f"- valid start: `{payload['valid_start']}`",
        "",
        "## Top Results",
        "",
        "| label | mode | kind | AUC | top3 hit | top3 risk adj | valid rows |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    ok = result[result["status"].eq("ok")].sort_values("auc", ascending=False).head(12)
    for _, row in ok.iterrows():
        lines.append(
            f"| `{row['label']}` | `{row['feature_mode']}` | {row['kind']} | "
            f"{float(row['auc']):.3f} | {float(row['top3_label_rate']):.2%} | "
            f"{float(row['top3_avg_risk_adj_1m']):.2%} | {int(row['valid_rows'])} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- AUC는 label 판별력입니다.",
            "- top3 hit는 날짜별 예측 확률 상위 3개 ETF가 해당 label을 실제로 만족한 비율입니다.",
            "- top3 risk adj는 날짜별 예측 확률 상위 3개 ETF의 평균 1M risk-adjusted return입니다.",
            "- 운영 target은 AUC만 보지 않고 top3 risk-adjusted 성과와 label 의미를 함께 봅니다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E-series ETF label ablation on mart v2.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--rebuild-mart", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run_ablation(
                asof=str(args.asof),
                train_end=str(args.train_end),
                valid_start=str(args.valid_start),
                rebuild_mart=bool(args.rebuild_mart),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
