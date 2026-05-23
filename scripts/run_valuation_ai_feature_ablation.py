# run_valuation_ai_feature_ablation.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.valuation_ai.common import now_ts, read_sql, write_json
from src.models.valuation_ai.config import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    FEATURE_TABLE,
    LABEL_TABLE,
    MODEL_CODE,
    OUT_DB,
    REPORT_DIR,
)
from src.models.valuation_ai.rule_score_engine import build_rule_scores


QM_MARKET_COLUMNS = [
    "qm_market_state_score",
    "qm_trend_score",
    "qm_breadth_score",
    "qm_defensive_flow_score",
    "qm_kospi_ret_1m",
    "qm_kospi_ret_3m",
    "qm_kosdaq_ret_1m",
    "qm_kosdaq_ret_3m",
    "qm_market_breadth_above_sma20",
    "qm_new_high_ratio_20d",
    "qm_new_low_ratio_20d",
    "qm_trading_value_expansion_ratio",
    "qm_risk_on_score",
    "qm_risk_off_score",
]

QM_THEME_COLUMNS = [
    "qm_theme_ret_1w",
    "qm_theme_ret_1m",
    "qm_theme_ret_3m",
    "qm_theme_momentum_score",
    "qm_theme_rotation_score",
    "qm_theme_persistence_days",
    "qm_theme_breadth_positive_ratio",
    "qm_theme_above_sma60_ratio",
    "qm_theme_trading_value_expansion_ratio",
    "qm_theme_concentration_score",
    "qm_leading_theme_rank",
    "qm_theme_mapping_confidence",
]

QM_RISK_COLUMNS = [
    "qm_risk_score",
    "qm_usdkrw_ret_1m",
    "qm_gold_proxy_ret_1m",
    "qm_bond_proxy_ret_1m",
    "qm_inverse_etf_ret_1m",
    "qm_defensive_asset_strength_score",
    "qm_market_stress_score",
    "qm_drawdown_pressure_score",
    "qm_crash_warning_flag",
]

QM_FLOW_COLUMNS = [
    "qm_foreign_net_buy_ratio",
    "qm_institution_net_buy_ratio",
    "qm_flow_concentration_score",
    "qm_smart_money_score",
    "qm_flow_context_available",
    "qm_flow_coverage_flag",
]

LOCAL_MARKET_COLUMNS = [
    col for col in FEATURE_COLUMNS if col == "market_regime" or col.startswith("market_")
]

BASE_COLUMNS = [
    col
    for col in FEATURE_COLUMNS
    if col not in set(LOCAL_MARKET_COLUMNS)
    and not col.startswith("qm_")
]


def _feature_set(name: str) -> tuple[list[str], list[str], str]:
    groups: dict[str, tuple[list[str], list[str], str]] = {
        "BASE_CORE": (
            BASE_COLUMNS,
            ["market", "sector_bucket", "theme_bucket"],
            "Core stock/ETF price, sector/theme, PIT fundamentals; no market context.",
        ),
        "LOCAL_MARKET": (
            BASE_COLUMNS + LOCAL_MARKET_COLUMNS,
            ["market", "sector_bucket", "theme_bucket", "market_regime_label"],
            "Core features plus Quant local market context.",
        ),
        "QM_MARKET": (
            BASE_COLUMNS + QM_MARKET_COLUMNS,
            ["market", "sector_bucket", "theme_bucket", "qm_market_state_label"],
            "Core features plus QuantMarket market context.",
        ),
        "QM_MARKET_RISK": (
            BASE_COLUMNS + QM_MARKET_COLUMNS + QM_RISK_COLUMNS,
            ["market", "sector_bucket", "theme_bucket", "qm_market_state_label", "qm_volatility_regime_label"],
            "Core features plus QuantMarket market and risk context.",
        ),
        "QM_MARKET_THEME": (
            BASE_COLUMNS + QM_MARKET_COLUMNS + QM_THEME_COLUMNS,
            ["market", "sector_bucket", "theme_bucket", "qm_market_state_label", "qm_quantmarket_theme_bucket"],
            "Core features plus QuantMarket market and theme context.",
        ),
        "QM_MARKET_THEME_RISK": (
            BASE_COLUMNS + QM_MARKET_COLUMNS + QM_THEME_COLUMNS + QM_RISK_COLUMNS,
            [
                "market",
                "sector_bucket",
                "theme_bucket",
                "qm_market_state_label",
                "qm_quantmarket_theme_bucket",
                "qm_volatility_regime_label",
            ],
            "Core features plus QuantMarket market, theme, and risk context.",
        ),
        "QM_FULL": (
            FEATURE_COLUMNS,
            CATEGORICAL_COLUMNS,
            "All current configured features including local market and full QuantMarket context.",
        ),
    }
    if name not in groups:
        raise KeyError(f"unknown feature set: {name}")
    return groups[name]


def _load_joined(db: Path) -> pd.DataFrame:
    features = read_sql(db, f"SELECT * FROM {FEATURE_TABLE}", parse_dates=["asof_date"])
    labels = read_sql(db, f"SELECT * FROM {LABEL_TABLE}", parse_dates=["asof_date"])
    if features.empty or labels.empty:
        raise SystemExit("features or labels are empty")
    features["ticker"] = features["ticker"].astype(str).str.zfill(6)
    labels["ticker"] = labels["ticker"].astype(str).str.zfill(6)
    return features.merge(labels, on=["asof_date", "ticker"], how="left", suffixes=("", "_label"))


def _preprocessor(df: pd.DataFrame, feature_columns: list[str], categorical_columns: list[str]) -> ColumnTransformer:
    numeric = [col for col in feature_columns if col in df.columns and df[col].notna().any()]
    categorical = [col for col in categorical_columns if col in df.columns and df[col].notna().any()]
    return ColumnTransformer(
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
        ]
    )


def _fit_regressor(train: pd.DataFrame, feature_columns: list[str], categorical_columns: list[str]) -> Pipeline:
    model = GradientBoostingRegressor(n_estimators=180, learning_rate=0.04, max_depth=3, random_state=42)
    pipe = Pipeline([("prep", _preprocessor(train, feature_columns, categorical_columns)), ("model", model)])
    pipe.fit(train, train["fwd_excess_ret_12m"].astype(float))
    return pipe


def _eval_regression(valid: pd.DataFrame, pred: np.ndarray) -> dict[str, Any]:
    target = pd.to_numeric(valid["fwd_excess_ret_12m"], errors="coerce")
    pred_s = pd.Series(pred, index=valid.index)
    ranked = valid.assign(pred=pred_s)
    top = ranked.sort_values("pred", ascending=False).head(min(30, len(ranked)))
    bottom = ranked.sort_values("pred", ascending=True).head(min(30, len(ranked)))
    return {
        "rank_ic": None if len(valid) < 5 else round(float(pred_s.rank().corr(target.rank())), 6),
        "ic": None if len(valid) < 5 else round(float(pred_s.corr(target)), 6),
        "top30_avg_excess_12m": None if top.empty else round(float(top["fwd_excess_ret_12m"].mean()), 6),
        "top30_avg_ret_12m": None if top.empty else round(float(top["fwd_ret_12m"].mean()), 6),
        "bottom30_avg_excess_12m": None if bottom.empty else round(float(bottom["fwd_excess_ret_12m"].mean()), 6),
        "top_bottom_spread_12m": None
        if top.empty or bottom.empty
        else round(float(top["fwd_excess_ret_12m"].mean() - bottom["fwd_excess_ret_12m"].mean()), 6),
        "top30_win_rate": None if top.empty else round(float((top["fwd_excess_ret_12m"] > 0).mean()), 6),
    }


def _metric_row(scored: pd.DataFrame, window: str) -> dict[str, Any]:
    valid = scored.dropna(subset=["valuation_ai_score", "fwd_excess_ret_12m"]).copy()
    if valid.empty:
        return {"window": window, "sample_count": 0}
    top = valid.sort_values("valuation_ai_score", ascending=False).head(max(1, int(len(valid) * 0.10)))
    bottom = valid.sort_values("valuation_ai_score", ascending=True).head(max(1, int(len(valid) * 0.10)))
    return {
        "window": window,
        "sample_count": int(len(valid)),
        "rank_ic_eval": round(float(valid["valuation_ai_score"].rank().corr(valid["fwd_excess_ret_12m"].rank())), 6),
        "top_decile_avg_excess_12m": round(float(top["fwd_excess_ret_12m"].mean()), 6),
        "top_decile_spread": round(float(top["fwd_excess_ret_12m"].mean() - bottom["fwd_excess_ret_12m"].mean()), 6),
        "top_decile_win_rate": round(float((top["fwd_excess_ret_12m"] > 0).mean()), 6),
    }


def _portfolio_stats(scored: pd.DataFrame, window: str, top_n: int = 30) -> dict[str, Any]:
    valid = scored.dropna(subset=["valuation_ai_score", "fwd_ret_1m"]).copy()
    if valid.empty:
        return {"window": window, "portfolio_sample_months": 0}
    returns = []
    for asof_date, month_frame in valid.groupby("asof_date"):
        selected = month_frame.sort_values("valuation_ai_score", ascending=False).head(min(top_n, len(month_frame)))
        returns.append({"asof_date": pd.Timestamp(asof_date), "portfolio_ret_1m": float(selected["fwd_ret_1m"].mean())})
    curve = pd.DataFrame(returns).sort_values("asof_date")
    monthly = pd.to_numeric(curve["portfolio_ret_1m"], errors="coerce").dropna()
    equity = (1.0 + monthly).cumprod()
    months = len(monthly)
    cagr = None if months <= 0 else float(equity.iloc[-1] ** (12.0 / months) - 1.0)
    dd = equity / equity.cummax() - 1.0
    vol = float(monthly.std()) if len(monthly) > 1 else 0.0
    sharpe = None if vol <= 0 else float(monthly.mean() / vol * np.sqrt(12))
    return {
        "window": window,
        "portfolio_sample_months": int(months),
        "portfolio_cagr": None if cagr is None else round(cagr, 6),
        "portfolio_mdd": None if dd.empty else round(float(dd.min()), 6),
        "portfolio_sharpe": None if sharpe is None else round(sharpe, 6),
        "portfolio_avg_monthly_return": None if monthly.empty else round(float(monthly.mean()), 6),
    }


def _evaluate_scored_windows(scored: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    # Forward-return labels are only available up to the latest fully observable
    # label month, not necessarily the requested current as-of date.
    end = pd.Timestamp(scored["asof_date"].max())
    windows: list[tuple[str, pd.Timestamp | None]] = [
        ("FULL", None),
        ("1Y", end - pd.DateOffset(years=1)),
        ("2Y", end - pd.DateOffset(years=2)),
        ("3Y", end - pd.DateOffset(years=3)),
        ("5Y", end - pd.DateOffset(years=5)),
    ]
    for window, start in windows:
        frame = scored if start is None else scored[scored["asof_date"] >= start]
        rows.append({**_metric_row(frame, window), **_portfolio_stats(frame, window)})
    return rows


def _run_one(
    df: pd.DataFrame,
    feature_set: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    asof: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    feature_columns, categorical_columns, description = _feature_set(feature_set)
    available_features = [col for col in feature_columns if col in df.columns]
    available_cats = [col for col in categorical_columns if col in df.columns]
    labeled = df[df["fwd_excess_ret_12m"].notna()].sort_values("asof_date").copy()
    train = labeled[labeled["asof_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["asof_date"] >= pd.Timestamp(valid_start)) & (labeled["asof_date"] <= pd.Timestamp(valid_end))].copy()
    if train.empty or valid.empty:
        raise SystemExit(f"insufficient rows for {feature_set}: train={len(train)}, valid={len(valid)}")

    model = _fit_regressor(train, available_features, available_cats)
    valid_pred = model.predict(valid)
    validation = {
        "feature_set": feature_set,
        "description": description,
        "train_start": str(train["asof_date"].min().date()),
        "train_end": str(train["asof_date"].max().date()),
        "valid_start": str(valid["asof_date"].min().date()),
        "valid_end": str(valid["asof_date"].max().date()),
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "feature_count": int(len(available_features)),
        "categorical_count": int(len(available_cats)),
        **_eval_regression(valid, valid_pred),
    }

    eval_frame = labeled[labeled["asof_date"] <= pd.Timestamp(asof)].copy()
    eval_pred = pd.Series(model.predict(eval_frame), index=eval_frame.index)
    scored = build_rule_scores(eval_frame, eval_pred)
    window_rows = _evaluate_scored_windows(scored)
    for row in window_rows:
        row["feature_set"] = feature_set
    return validation, window_rows


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.2%}"


def run_ablation(db: Path, asof: str, train_end: str, valid_start: str, valid_end: str, feature_sets: list[str]) -> dict[str, Any]:
    df = _load_joined(db)
    validations = []
    windows = []
    for feature_set in feature_sets:
        validation, window_rows = _run_one(df, feature_set, train_end, valid_start, valid_end, asof)
        validations.append(validation)
        windows.extend(window_rows)

    token = asof.replace("-", "")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    validation_df = pd.DataFrame(validations)
    window_df = pd.DataFrame(windows)
    validation_path = REPORT_DIR / f"valuation_ai_feature_ablation_validation_{token}.csv"
    window_path = REPORT_DIR / f"valuation_ai_feature_ablation_windows_{token}.csv"
    json_path = REPORT_DIR / f"valuation_ai_feature_ablation_{token}.json"
    md_path = REPORT_DIR / f"valuation_ai_feature_ablation_{token}.md"
    validation_df.to_csv(validation_path, index=False, encoding="utf-8-sig")
    window_df.to_csv(window_path, index=False, encoding="utf-8-sig")

    payload = {
        "model_code": MODEL_CODE,
        "asof_date": asof,
        "train_end": train_end,
        "valid_start": valid_start,
        "valid_end": valid_end,
        "created_at": now_ts(),
        "validation": validations,
        "windows": windows,
    }
    write_json(json_path, payload)

    full_rows = window_df[window_df["window"] == "FULL"].copy()
    one_y_rows = window_df[window_df["window"] == "1Y"].copy()
    lines = [
        f"# {MODEL_CODE} Feature Group Ablation - {asof}",
        "",
        "## Validation Holdout",
        "",
        "| feature set | features | Rank IC | Top30 excess 12M | Top30 ret 12M | Spread | Win rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in validation_df.to_dict(orient="records"):
        lines.append(
            "| {name} | {features} | {rank_ic:.3f} | {top_excess} | {top_ret} | {spread} | {win} |".format(
                name=row["feature_set"],
                features=int(row["feature_count"]),
                rank_ic=float(row["rank_ic"]),
                top_excess=_fmt_pct(row.get("top30_avg_excess_12m")),
                top_ret=_fmt_pct(row.get("top30_avg_ret_12m")),
                spread=_fmt_pct(row.get("top_bottom_spread_12m")),
                win=_fmt_pct(row.get("top30_win_rate")),
            )
        )
    lines.extend(
        [
            "",
            "## FULL Top-N Proxy",
            "",
            "| feature set | CAGR | MDD | Sharpe | Top decile excess 12M | Rank IC |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in full_rows.to_dict(orient="records"):
        lines.append(
            "| {name} | {cagr} | {mdd} | {sharpe} | {top} | {rank_ic:.3f} |".format(
                name=row["feature_set"],
                cagr=_fmt_pct(row.get("portfolio_cagr")),
                mdd=_fmt_pct(row.get("portfolio_mdd")),
                sharpe="N/A" if pd.isna(row.get("portfolio_sharpe")) else f"{float(row['portfolio_sharpe']):.3f}",
                top=_fmt_pct(row.get("top_decile_avg_excess_12m")),
                rank_ic=float(row.get("rank_ic_eval")),
            )
        )
    lines.extend(
        [
            "",
            "## 1Y Top-N Proxy",
            "",
            "| feature set | CAGR | MDD | Sharpe | Top decile excess 12M | Rank IC |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in one_y_rows.to_dict(orient="records"):
        lines.append(
            "| {name} | {cagr} | {mdd} | {sharpe} | {top} | {rank_ic:.3f} |".format(
                name=row["feature_set"],
                cagr=_fmt_pct(row.get("portfolio_cagr")),
                mdd=_fmt_pct(row.get("portfolio_mdd")),
                sharpe="N/A" if pd.isna(row.get("portfolio_sharpe")) else f"{float(row['portfolio_sharpe']):.3f}",
                top=_fmt_pct(row.get("top_decile_avg_excess_12m")),
                rank_ic=float(row.get("rank_ic_eval")),
            )
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "status": "ok",
        "validation_path": str(validation_path),
        "window_path": str(window_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "validation": validations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run feature group ablation for valuation AI.")
    parser.add_argument("--db", default=str(OUT_DB))
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--valid-end", default="2025-03-31")
    parser.add_argument(
        "--feature-sets",
        nargs="*",
        default=[
            "BASE_CORE",
            "LOCAL_MARKET",
            "QM_MARKET",
            "QM_MARKET_RISK",
            "QM_MARKET_THEME",
            "QM_MARKET_THEME_RISK",
            "QM_FULL",
        ],
    )
    args = parser.parse_args()
    result = run_ablation(
        Path(args.db),
        asof=args.asof,
        train_end=args.train_end,
        valid_start=args.valid_start,
        valid_end=args.valid_end,
        feature_sets=args.feature_sets,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
