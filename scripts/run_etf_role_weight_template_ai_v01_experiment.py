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
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_etf_role_allocation_ai_v01_experiment import (
    MARKET_FEATURES,
    MODEL_CODE,
    QUALITY_GATE_CONFIGS,
    REPORT_DIR,
    ROLES,
    add_labels,
    apply_regime_mapping,
    build_role_sleeves,
    _load_or_build_mart,
)

TEMPLATE_MODEL_CODE = "AI-ETF-ROLE-WEIGHT-TEMPLATE-V01"
DOC_PATH = ROOT / r"docs\AI_ETF_ROLE_WEIGHT_TEMPLATE_V01_EXPERIMENT_20260511.md"
RANDOM_STATE = 42

TEMPLATES = [
    {
        "template_id": "ON_CORE_GROWTH",
        "preferred_mode": "risk_on",
        "weights": {"CORE_BETA": 0.35, "SECTOR_THEME": 0.30, "STYLE_FACTOR": 0.20, "DEFENSIVE_HEDGE": 0.10, "TACTICAL_HEDGE": 0.00, "TACTICAL_LEVERAGE": 0.05},
    },
    {
        "template_id": "ON_THEME_TILT",
        "preferred_mode": "risk_on",
        "weights": {"CORE_BETA": 0.20, "SECTOR_THEME": 0.45, "STYLE_FACTOR": 0.20, "DEFENSIVE_HEDGE": 0.05, "TACTICAL_HEDGE": 0.00, "TACTICAL_LEVERAGE": 0.10},
    },
    {
        "template_id": "ON_STYLE_BALANCED",
        "preferred_mode": "risk_on",
        "weights": {"CORE_BETA": 0.30, "SECTOR_THEME": 0.20, "STYLE_FACTOR": 0.35, "DEFENSIVE_HEDGE": 0.10, "TACTICAL_HEDGE": 0.00, "TACTICAL_LEVERAGE": 0.05},
    },
    {
        "template_id": "NEUTRAL_BALANCED",
        "preferred_mode": "neutral",
        "weights": {"CORE_BETA": 0.30, "SECTOR_THEME": 0.15, "STYLE_FACTOR": 0.25, "DEFENSIVE_HEDGE": 0.25, "TACTICAL_HEDGE": 0.05, "TACTICAL_LEVERAGE": 0.00},
    },
    {
        "template_id": "NEUTRAL_DEFENSIVE_BAR",
        "preferred_mode": "neutral",
        "weights": {"CORE_BETA": 0.20, "SECTOR_THEME": 0.10, "STYLE_FACTOR": 0.20, "DEFENSIVE_HEDGE": 0.40, "TACTICAL_HEDGE": 0.10, "TACTICAL_LEVERAGE": 0.00},
    },
    {
        "template_id": "NEUTRAL_STYLE_INCOME",
        "preferred_mode": "neutral",
        "weights": {"CORE_BETA": 0.20, "SECTOR_THEME": 0.10, "STYLE_FACTOR": 0.40, "DEFENSIVE_HEDGE": 0.25, "TACTICAL_HEDGE": 0.05, "TACTICAL_LEVERAGE": 0.00},
    },
    {
        "template_id": "OFF_DEFENSIVE",
        "preferred_mode": "risk_off",
        "weights": {"CORE_BETA": 0.10, "SECTOR_THEME": 0.05, "STYLE_FACTOR": 0.10, "DEFENSIVE_HEDGE": 0.60, "TACTICAL_HEDGE": 0.15, "TACTICAL_LEVERAGE": 0.00},
    },
    {
        "template_id": "OFF_HEDGE_TILT",
        "preferred_mode": "risk_off",
        "weights": {"CORE_BETA": 0.05, "SECTOR_THEME": 0.00, "STYLE_FACTOR": 0.05, "DEFENSIVE_HEDGE": 0.45, "TACTICAL_HEDGE": 0.45, "TACTICAL_LEVERAGE": 0.00},
    },
    {
        "template_id": "OFF_BAR_BELL",
        "preferred_mode": "risk_off",
        "weights": {"CORE_BETA": 0.15, "SECTOR_THEME": 0.05, "STYLE_FACTOR": 0.15, "DEFENSIVE_HEDGE": 0.50, "TACTICAL_HEDGE": 0.15, "TACTICAL_LEVERAGE": 0.00},
    },
]


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.replace({np.nan: None}).to_json(orient="records", force_ascii=False))


def _normalize_template(weights: dict[str, float], available: set[str]) -> dict[str, float]:
    raw = {role: max(0.0, float(weights.get(role, 0.0))) for role in ROLES if role in available}
    total = sum(raw.values())
    if total <= 0:
        n = max(1, len(available))
        return {role: (1.0 / n if role in available else 0.0) for role in ROLES}
    return {role: raw.get(role, 0.0) / total for role in ROLES}


def _date_market_features(part: pd.DataFrame) -> dict[str, Any]:
    row = part.iloc[0]
    out = {
        "signal_date": row["signal_date"],
        "regime_mode": row.get("regime_mode"),
        "market_state_label": row.get("market_state_label"),
        "volatility_regime_label": row.get("volatility_regime_label"),
    }
    for col in MARKET_FEATURES:
        if col in part.columns:
            out[col] = row.get(col)
    return out


def build_template_panel(sleeves: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date, part in sleeves.groupby("signal_date"):
        role_map = part.set_index("role_key")
        available = set(role_map.index.astype(str))
        market = _date_market_features(part)
        for spec in TEMPLATES:
            weights = _normalize_template(spec["weights"], available)
            ret = 0.0
            mdd = 0.0
            risk_adj = 0.0
            objective = 0.0
            for role, weight in weights.items():
                if weight <= 0 or role not in role_map.index:
                    continue
                row = role_map.loc[role]
                ret += weight * float(row["sleeve_fwd_ret_1m"])
                mdd += weight * float(row["sleeve_path_mdd_1m"])
                risk_adj += weight * float(row["sleeve_risk_adj_1m"])
                objective += weight * float(row["role_objective_score_v2"])
            rows.append(
                {
                    **market,
                    "template_id": spec["template_id"],
                    "preferred_mode": spec["preferred_mode"],
                    "mode_match": int(str(market["regime_mode"]) == spec["preferred_mode"]),
                    "portfolio_fwd_ret_1m": ret,
                    "portfolio_path_mdd_1m": mdd,
                    "portfolio_risk_adj_1m": risk_adj,
                    "portfolio_objective_v2": objective,
                    **{f"w_{role}": weights.get(role, 0.0) for role in ROLES},
                }
            )
    panel = pd.DataFrame(rows)
    panel["template_rank_objective"] = panel.groupby("signal_date")["portfolio_objective_v2"].rank(ascending=False, method="first")
    panel["label_best_template"] = (panel["template_rank_objective"] == 1).astype(int)
    panel["label_positive_template"] = (panel["portfolio_objective_v2"] > 0).astype(int)
    return panel


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric = [col for col in MARKET_FEATURES if col in df.columns and df[col].notna().any()]
    numeric.extend([f"w_{role}" for role in ROLES])
    numeric.append("mode_match")
    categorical = ["template_id", "preferred_mode", "regime_mode", "market_state_label", "volatility_regime_label"]
    categorical = [col for col in categorical if col in df.columns]
    return numeric, categorical


def _fit(train: pd.DataFrame, label: str) -> Pipeline:
    numeric, categorical = _feature_columns(train)
    prep = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ],
        remainder="drop",
    )
    model = GradientBoostingClassifier(n_estimators=180, learning_rate=0.04, max_depth=2, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", prep), ("model", model)])
    max_date = train["signal_date"].max()
    weight = np.ones(len(train), dtype=float)
    weight[train["signal_date"].ge(max_date - pd.DateOffset(years=2)).to_numpy()] = 2.0
    pipe.fit(train, train[label].astype(int), model__sample_weight=weight)
    return pipe


def _evaluate_policy(scored: pd.DataFrame, policy: str) -> pd.DataFrame:
    rows = []
    for date, part in scored.groupby("signal_date"):
        if policy == "mode_default_template":
            mode = str(part["regime_mode"].iloc[0])
            order = {"risk_on": "ON_CORE_GROWTH", "neutral": "NEUTRAL_BALANCED", "risk_off": "OFF_DEFENSIVE"}
            chosen = part[part["template_id"].eq(order.get(mode, "NEUTRAL_BALANCED"))]
            row = chosen.iloc[0] if not chosen.empty else part.iloc[0]
        elif policy == "ai_top1_template":
            row = part.sort_values("ai_prob_best_template", ascending=False).iloc[0]
        elif policy == "ai_prob_weighted_template":
            probs = pd.to_numeric(part["ai_prob_best_template"], errors="coerce").clip(lower=0)
            total = probs.sum()
            if total <= 0:
                probs = pd.Series(np.ones(len(part)) / len(part), index=part.index)
            else:
                probs = probs / total
            rows.append(
                {
                    "signal_date": date,
                    "policy": policy,
                    "regime_mode": part["regime_mode"].iloc[0],
                    "template_id": "prob_weighted",
                    "portfolio_fwd_ret_1m": float((part["portfolio_fwd_ret_1m"] * probs).sum()),
                    "portfolio_path_mdd_1m": float((part["portfolio_path_mdd_1m"] * probs).sum()),
                    "portfolio_risk_adj_1m": float((part["portfolio_risk_adj_1m"] * probs).sum()),
                    "portfolio_objective_v2": float((part["portfolio_objective_v2"] * probs).sum()),
                }
            )
            continue
        elif policy == "oracle_best_template":
            row = part.sort_values("portfolio_objective_v2", ascending=False).iloc[0]
        else:
            raise ValueError(policy)
        rows.append(
            {
                "signal_date": date,
                "policy": policy,
                "regime_mode": row["regime_mode"],
                "template_id": row["template_id"],
                "portfolio_fwd_ret_1m": row["portfolio_fwd_ret_1m"],
                "portfolio_path_mdd_1m": row["portfolio_path_mdd_1m"],
                "portfolio_risk_adj_1m": row["portfolio_risk_adj_1m"],
                "portfolio_objective_v2": row["portfolio_objective_v2"],
            }
        )
    return pd.DataFrame(rows)


def _summary(policy_returns: pd.DataFrame) -> pd.DataFrame:
    return (
        policy_returns.groupby("policy")
        .agg(
            rows=("signal_date", "count"),
            avg_1m_ret=("portfolio_fwd_ret_1m", "mean"),
            hit_rate=("portfolio_fwd_ret_1m", lambda s: (s > 0).mean()),
            avg_1m_mdd=("portfolio_path_mdd_1m", "mean"),
            avg_1m_risk_adj=("portfolio_risk_adj_1m", "mean"),
            avg_objective_v2=("portfolio_objective_v2", "mean"),
            worst_1m_ret=("portfolio_fwd_ret_1m", "min"),
        )
        .reset_index()
        .sort_values("avg_objective_v2", ascending=False)
    )


def run_experiment(
    asof: str,
    train_end: str,
    valid_start: str,
    top_n: int,
    regime_map: str,
    selection_mode: str,
    quality_gate: str,
    rebuild_mart: bool,
) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    suffix = f"{token}_top{top_n}_{regime_map}_{selection_mode}_{quality_gate}_template"
    mart = apply_regime_mapping(_load_or_build_mart(asof, rebuild_mart), regime_map)
    sleeves = add_labels(build_role_sleeves(mart, top_n=top_n, selection_mode=selection_mode, quality_gate=quality_gate))
    panel = build_template_panel(sleeves)
    train = panel[panel["signal_date"] <= pd.Timestamp(train_end)].copy()
    valid = panel[(panel["signal_date"] >= pd.Timestamp(valid_start)) & (panel["signal_date"] <= pd.Timestamp(asof))].copy()
    if train.empty or valid.empty or train["label_best_template"].nunique() < 2 or valid["label_best_template"].nunique() < 2:
        raise SystemExit("insufficient template training rows")
    model = _fit(train, "label_best_template")
    valid = valid.copy()
    valid["ai_prob_best_template"] = model.predict_proba(valid)[:, 1]
    top_pick = valid.sort_values(["signal_date", "ai_prob_best_template"], ascending=[True, False]).groupby("signal_date").head(1)
    auc = roc_auc_score(valid["label_best_template"], valid["ai_prob_best_template"])
    policies = pd.concat(
        [
            _evaluate_policy(valid, "mode_default_template"),
            _evaluate_policy(valid, "ai_top1_template"),
            _evaluate_policy(valid, "ai_prob_weighted_template"),
            _evaluate_policy(valid, "oracle_best_template"),
        ],
        ignore_index=True,
    )
    summary = _summary(policies)

    panel_path = REPORT_DIR / f"etf_role_weight_template_panel_{suffix}.csv"
    scored_path = REPORT_DIR / f"etf_role_weight_template_scored_{suffix}.csv"
    policy_path = REPORT_DIR / f"etf_role_weight_template_policy_returns_{suffix}.csv"
    summary_path = REPORT_DIR / f"etf_role_weight_template_policy_summary_{suffix}.csv"
    json_path = REPORT_DIR / f"etf_role_weight_template_experiment_{suffix}.json"
    md_path = REPORT_DIR / f"etf_role_weight_template_experiment_{suffix}.md"
    panel.to_csv(panel_path, index=False, encoding="utf-8-sig")
    valid.to_csv(scored_path, index=False, encoding="utf-8-sig")
    policies.to_csv(policy_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    latest = valid[valid["signal_date"].eq(valid["signal_date"].max())].sort_values("ai_prob_best_template", ascending=False)
    payload = {
        "source_name": "etf_role_weight_template_ai_v01_experiment",
        "model_code": TEMPLATE_MODEL_CODE,
        "base_role_model_code": MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "top_n": top_n,
        "regime_map": regime_map,
        "selection_mode": selection_mode,
        "quality_gate": quality_gate,
        "quality_gate_description": QUALITY_GATE_CONFIGS[quality_gate],
        "train_end": train_end,
        "valid_start": valid_start,
        "template_count": len(TEMPLATES),
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "valid_dates": int(valid["signal_date"].nunique()),
        "auc_best_template": _safe_float(auc),
        "top_pick_hit_rate": _safe_float(top_pick["label_best_template"].mean()),
        "policy_summary": _records(summary),
        "latest_template_scores": _records(latest[["signal_date", "regime_mode", "template_id", "preferred_mode", "ai_prob_best_template", "portfolio_fwd_ret_1m", "portfolio_risk_adj_1m", *[f"w_{role}" for role in ROLES]]]),
        "outputs": {
            "panel_csv": str(panel_path),
            "scored_csv": str(scored_path),
            "policy_returns_csv": str(policy_path),
            "policy_summary_csv": str(summary_path),
            "json": str(json_path),
            "md": str(md_path),
            "doc": str(DOC_PATH),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, summary)
    _write_doc(payload, summary)
    return payload


def _pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.2f}%"


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    lines = [
        f"# ETF Role Weight Template AI V01 - {payload['as_of_date']}",
        "",
        f"- AUC: {payload['auc_best_template']}",
        f"- Top pick hit rate: {payload['top_pick_hit_rate']}",
        "",
        "| policy | avg 1M ret | hit rate | avg 1M MDD | avg risk adj | avg objective | worst 1M ret |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.to_dict("records"):
        lines.append(
            f"| `{row['policy']}` | {_pct(row['avg_1m_ret'])} | {_pct(row['hit_rate'])} | {_pct(row['avg_1m_mdd'])} | "
            f"{_pct(row['avg_1m_risk_adj'])} | {_pct(row['avg_objective_v2'])} | {_pct(row['worst_1m_ret'])} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_doc(payload: dict[str, Any], summary: pd.DataFrame) -> None:
    lines = [
        "# ETF 역할 비중 Template AI V01 실험",
        "",
        "## 목적",
        "",
        "ETF 역할별 sleeve를 만든 뒤, 시장 상황에 따라 어떤 역할 비중 template이 유리한지 학습한다.",
        "",
        "## 기준 조합",
        "",
        f"- role model: `{payload['base_role_model_code']}`",
        f"- template model: `{payload['model_code']}`",
        f"- sleeve topN: `{payload['top_n']}`",
        f"- regime mapping: `{payload['regime_map']}`",
        f"- selection mode: `{payload['selection_mode']}`",
        f"- quality gate: `{payload['quality_gate']}` ({payload['quality_gate_description']})",
        "",
        "## 결과",
        "",
        f"- AUC(best template): `{payload['auc_best_template']}`",
        f"- top-pick hit rate: `{payload['top_pick_hit_rate']}`",
        "",
        "| policy | avg 1M ret | hit rate | avg 1M MDD | avg risk adj | avg objective | worst 1M ret |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.to_dict("records"):
        lines.append(
            f"| `{row['policy']}` | {_pct(row['avg_1m_ret'])} | {_pct(row['hit_rate'])} | {_pct(row['avg_1m_mdd'])} | "
            f"{_pct(row['avg_1m_risk_adj'])} | {_pct(row['avg_objective_v2'])} | {_pct(row['worst_1m_ret'])} |"
        )
    lines.extend(
        [
            "",
            "## 현재 판단",
            "",
            "이 실험은 ETF AI가 역할 선택을 넘어 역할 비중 template을 선택할 수 있는지 보는 1차 baseline이다.",
            "다음 단계에서는 template 후보군을 더 촘촘히 만들고, 시장 모드별 template pool을 분리해 검증한다.",
            "",
            "## Outputs",
            "",
            f"- `{payload['outputs']['panel_csv']}`",
            f"- `{payload['outputs']['scored_csv']}`",
            f"- `{payload['outputs']['policy_summary_csv']}`",
            f"- `{payload['outputs']['json']}`",
        ]
    )
    DOC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF role weight-template AI V01 experiment.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--regime-map", default="score_diff")
    parser.add_argument("--selection-mode", default="risk_adjusted")
    parser.add_argument("--quality-gate", default="none", choices=sorted(QUALITY_GATE_CONFIGS))
    parser.add_argument("--rebuild-mart", action="store_true")
    args = parser.parse_args()
    payload = run_experiment(
        args.asof,
        args.train_end,
        args.valid_start,
        args.top_n,
        args.regime_map,
        args.selection_mode,
        args.quality_gate,
        args.rebuild_mart,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "model_code": TEMPLATE_MODEL_CODE,
                "as_of_date": args.asof,
                "auc_best_template": payload["auc_best_template"],
                "top_pick_hit_rate": payload["top_pick_hit_rate"],
                "quality_gate": args.quality_gate,
                "best_policy": payload["policy_summary"][0] if payload["policy_summary"] else {},
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
