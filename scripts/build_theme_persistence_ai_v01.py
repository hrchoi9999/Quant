from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
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

from src.quant_market.market_handoff import context_dir, market_context_frame

QM_CONTEXT_DIR = context_dir()
REPORT_DIR = ROOT / r"reports\theme_persistence_ai_v01"
MODEL_DIR = ROOT / r"data\models\theme_persistence_ai"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
AI_OVERLAY_DIR = ROOT / r"reports\ai_overlay_v01"

MODEL_CODE = "AI-THEME-PERSISTENCE-V01"
MODEL_NAME_KO = "테마지속성AI"
RANDOM_STATE = 42
FWD_STEPS_1M = 20

KEY_COLUMNS = {
    "asof_date",
    "quant_theme_bucket",
    "quantmarket_theme_bucket",
    "theme_name_kr",
    "generated_at",
    "feature_version",
    "schema_version",
}
LABEL_COLUMNS = {
    "future_asof_date",
    "future_theme_ret_1m",
    "future_theme_momentum_score",
    "future_leading_theme_rank",
    "rank_change_1m",
    "label_theme_continue_1m",
    "label_theme_fade_1m",
}
CONTEXT_METADATA_COLUMNS = {"schema_version", "feature_version", "generated_at", "source_quality", "flow_source_start_date"}


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _prefix_context(df: pd.DataFrame, prefix: str, keys: set[str]) -> pd.DataFrame:
    out = df.drop(columns=[col for col in CONTEXT_METADATA_COLUMNS if col in df.columns], errors="ignore").copy()
    rename = {col: f"{prefix}{col}" for col in out.columns if col not in keys}
    return out.rename(columns=rename)


def _join_qm_market_risk_flow_context(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    handoff = market_context_frame(scope="ALL", date_col="asof_date", prefix="qm_market_")
    if not handoff.empty:
        handoff["asof_date"] = pd.to_datetime(handoff["asof_date"], errors="coerce")
        return out.merge(handoff, on="asof_date", how="left")

    market_path = QM_CONTEXT_DIR / "market_context_daily_current.csv"
    if market_path.exists():
        market = pd.read_csv(market_path, low_memory=False)
        market["asof_date"] = pd.to_datetime(market["asof_date"], errors="coerce")
        market = market[market["market_scope"].astype(str).eq("ALL")].copy()
        market = _prefix_context(market.drop(columns=["market_scope"], errors="ignore"), "qm_market_", {"asof_date"})
        out = out.merge(market, on="asof_date", how="left")

    risk_path = QM_CONTEXT_DIR / "risk_context_daily_current.csv"
    if risk_path.exists():
        risk = pd.read_csv(risk_path, low_memory=False)
        risk["asof_date"] = pd.to_datetime(risk["asof_date"], errors="coerce")
        risk = _prefix_context(risk, "qm_risk_", {"asof_date"})
        out = out.merge(risk, on="asof_date", how="left")

    flow_path = QM_CONTEXT_DIR / "flow_context_daily_current.csv"
    if flow_path.exists():
        flow = pd.read_csv(flow_path, low_memory=False)
        flow["asof_date"] = pd.to_datetime(flow["asof_date"], errors="coerce")
        flow = flow[flow["market_scope"].astype(str).eq("ALL")].copy()
        flow = _prefix_context(flow.drop(columns=["market_scope"], errors="ignore"), "qm_flow_", {"asof_date"})
        out = out.merge(flow, on="asof_date", how="left")
    return out


def _ai_overlay_training_mart_path(asof: str | None = None) -> Path | None:
    if asof:
        path = AI_OVERLAY_DIR / f"ai_overlay_training_mart_{asof.replace('-', '')}.csv"
        if path.exists():
            return path
    paths = [
        path
        for path in AI_OVERLAY_DIR.glob("ai_overlay_training_mart_*.csv")
        if path.stem.replace("ai_overlay_training_mart_", "").isdigit()
    ]
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def _join_theme_quality_features(df: pd.DataFrame, asof: str | None = None) -> pd.DataFrame:
    path = _ai_overlay_training_mart_path(asof)
    if path is None:
        raise SystemExit(f"missing AI overlay training mart under: {AI_OVERLAY_DIR}")

    mart = pd.read_csv(path, low_memory=False)
    if "event_date" not in mart.columns or "theme_bucket" not in mart.columns:
        raise SystemExit(f"AI overlay mart missing event_date/theme_bucket columns: {path}")

    mart["event_date"] = pd.to_datetime(mart["event_date"], errors="coerce")
    mart = mart[mart["event_date"].notna() & mart["theme_bucket"].notna()].copy()
    if "asset_type" in mart.columns:
        mart = mart[~mart["asset_type"].astype(str).str.upper().eq("ETF")].copy()

    numeric_cols = [
        "rank_no",
        "score",
        "weight",
        "stage1_prob",
        "stage2_prob",
        "universe_rank_no",
        "universe_rank_score",
        "display_score",
        "model_overlap_count",
        "overlap_user_count",
        "overlap_internal_count",
        "overlap_tseries_count",
        "ret_5d",
        "ret_10d",
        "ret_20d",
        "ret_60d",
        "vol_20d",
        "mdd_20d",
        "trading_value_20d",
        "confidence_score",
        "annual_revenue_yoy",
        "annual_op_income_yoy",
        "half_revenue_yoy",
        "half_op_income_yoy",
        "q_revenue_yoy",
        "q_op_income_yoy",
        "q_revenue_yoy_delta_1q",
        "q_op_income_yoy_delta_1q",
        "pit_growth_score",
        "positive_relation_count",
        "negative_relation_count",
        "theme_support_score",
        "etf_support_score",
        "hedge_risk_score",
        "cluster_concentration_score",
        "c_overlay_score",
        "kiwoom_foreign_net_volume_5d",
        "kiwoom_foreign_net_volume_20d",
        "kiwoom_foreign_net_value_5d",
        "kiwoom_foreign_net_value_20d",
        "kiwoom_foreign_net_buy_days_20d",
        "kiwoom_foreign_net_buy_streak",
        "kiwoom_institution_net_volume_5d",
        "kiwoom_institution_net_volume_20d",
        "kiwoom_institution_net_value_5d",
        "kiwoom_institution_net_value_20d",
        "kiwoom_institution_net_buy_days_20d",
        "kiwoom_institution_net_buy_streak",
        "dart_events_30d",
        "dart_events_90d",
        "dart_major_events_90d",
        "dart_earnings_events_90d",
        "dart_ownership_events_90d",
        "dart_market_watch_events_90d",
        "dart_days_since_last_event",
    ]
    for col in numeric_cols:
        if col in mart.columns:
            mart[col] = pd.to_numeric(mart[col], errors="coerce")

    agg_spec: dict[str, tuple[str, str]] = {
        "tq_candidate_count": ("ticker", "nunique"),
        "tq_row_count": ("ticker", "size"),
    }
    if "scope_key" in mart.columns:
        agg_spec["tq_scope_count"] = ("scope_key", "nunique")
    if "model_id" in mart.columns:
        agg_spec["tq_model_count"] = ("model_id", "nunique")

    avg_cols = [col for col in numeric_cols if col in mart.columns]
    agg_spec.update({f"tq_avg_{col}": (col, "mean") for col in avg_cols})
    if "rank_no" in mart.columns:
        agg_spec["tq_min_rank_no"] = ("rank_no", "min")
    if "dart_major_events_90d" in mart.columns:
        agg_spec["tq_sum_dart_major_events_90d"] = ("dart_major_events_90d", "sum")

    quality = (
        mart.groupby(["event_date", "theme_bucket"], as_index=False)
        .agg(**agg_spec)
        .rename(columns={"event_date": "asof_date", "theme_bucket": "quant_theme_bucket"})
    )
    out = df.copy()
    return out.merge(quality, on=["asof_date", "quant_theme_bucket"], how="left")


def _add_acceleration_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["quant_theme_bucket", "asof_date"]).copy()
    groups = out["quant_theme_bucket"]
    base_cols = [
        "theme_momentum_score",
        "theme_rotation_score",
        "theme_ret_1w",
        "theme_ret_1m",
        "theme_breadth_positive_ratio",
        "theme_above_sma60_ratio",
        "theme_trading_value_expansion_ratio",
        "theme_concentration_score",
        "leading_theme_rank",
    ]
    for col in base_cols:
        if col not in out.columns:
            continue
        series = pd.to_numeric(out[col], errors="coerce")
        shifted_5d = series.groupby(groups).shift(5)
        shifted_10d = series.groupby(groups).shift(10)
        ma5 = series.groupby(groups).transform(lambda s: s.rolling(5, min_periods=2).mean())
        ma20 = series.groupby(groups).transform(lambda s: s.rolling(20, min_periods=5).mean())
        out[f"{col}_delta_5d"] = series - shifted_5d
        out[f"{col}_delta_10d"] = series - shifted_10d
        out[f"{col}_ma5"] = ma5
        out[f"{col}_ma20"] = ma20
        out[f"{col}_ma5_vs_ma20"] = ma5 - ma20
    if "leading_theme_rank_delta_5d" in out.columns:
        out["leading_theme_rank_improvement_5d"] = -out["leading_theme_rank_delta_5d"]
    if "leading_theme_rank_delta_10d" in out.columns:
        out["leading_theme_rank_improvement_10d"] = -out["leading_theme_rank_delta_10d"]
    if {"theme_momentum_score_delta_5d", "theme_rotation_score_delta_5d"}.issubset(out.columns):
        out["theme_momentum_rotation_accel_5d"] = out["theme_momentum_score_delta_5d"] + out["theme_rotation_score_delta_5d"]
    if {"theme_breadth_positive_ratio_delta_5d", "theme_trading_value_expansion_ratio_delta_5d"}.issubset(out.columns):
        out["theme_participation_accel_5d"] = out["theme_breadth_positive_ratio_delta_5d"] + out["theme_trading_value_expansion_ratio_delta_5d"]
    return out


def _read_theme_context(
    *,
    include_qm_context: bool = False,
    include_acceleration: bool = False,
    include_theme_quality: bool = False,
    quality_asof: str | None = None,
) -> pd.DataFrame:
    path = QM_CONTEXT_DIR / "theme_context_daily_quant_bucket_current.csv"
    if not path.exists():
        raise SystemExit(f"missing QuantMarket theme context: {path}")
    df = pd.read_csv(path, low_memory=False)
    df["asof_date"] = pd.to_datetime(df["asof_date"], errors="coerce")
    df = df[df["asof_date"].notna() & df["quant_theme_bucket"].notna()].copy()
    df = df.sort_values(["quant_theme_bucket", "asof_date"]).drop_duplicates(["quant_theme_bucket", "asof_date"], keep="last")
    if include_acceleration:
        df = _add_acceleration_features(df)
    if include_qm_context:
        df = _join_qm_market_risk_flow_context(df)
    if include_theme_quality:
        df = _join_theme_quality_features(df, quality_asof)
    return _add_labels(df)


def _add_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    group = out.groupby("quant_theme_bucket", group_keys=False)
    out["future_asof_date"] = group["asof_date"].shift(-FWD_STEPS_1M)
    out["future_theme_ret_1m"] = group["theme_ret_1m"].shift(-FWD_STEPS_1M)
    out["future_theme_momentum_score"] = group["theme_momentum_score"].shift(-FWD_STEPS_1M)
    out["future_leading_theme_rank"] = group["leading_theme_rank"].shift(-FWD_STEPS_1M)
    out["rank_change_1m"] = pd.to_numeric(out["leading_theme_rank"], errors="coerce") - pd.to_numeric(
        out["future_leading_theme_rank"], errors="coerce"
    )

    future_ret = pd.to_numeric(out["future_theme_ret_1m"], errors="coerce")
    future_momentum = pd.to_numeric(out["future_theme_momentum_score"], errors="coerce")
    future_rank = pd.to_numeric(out["future_leading_theme_rank"], errors="coerce")
    rank_change = pd.to_numeric(out["rank_change_1m"], errors="coerce")
    has_future = future_ret.notna() & future_momentum.notna() & future_rank.notna()

    continue_hit = future_rank <= 5
    fade_hit = rank_change <= -3
    out["label_theme_continue_1m"] = np.where(has_future, continue_hit.astype(int), np.nan)
    out["label_theme_fade_1m"] = np.where(has_future, fade_hit.astype(int), np.nan)
    return out


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    for col in df.columns:
        if col in KEY_COLUMNS or col in LABEL_COLUMNS or col.startswith("future_") or col.startswith("label_"):
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
            numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _split(df: pd.DataFrame, label: str, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[label].notna()].sort_values("asof_date").copy()
    train = labeled[labeled["asof_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["asof_date"] >= pd.Timestamp(valid_start)) & (labeled["asof_date"] <= pd.Timestamp(valid_end))].copy()
    return train, valid


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
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
        ],
        remainder="drop",
    )


def _sample_weight(train: pd.DataFrame) -> np.ndarray:
    max_date = train["asof_date"].max()
    cutoff = max_date - pd.DateOffset(years=1)
    weight = np.ones(len(train), dtype=float)
    weight[train["asof_date"].ge(cutoff).to_numpy()] = 3.0
    return weight


def _fit(train: pd.DataFrame, label: str, numeric: list[str], categorical: list[str]) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=180, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    pipe.fit(train, train[label].astype(int), model__sample_weight=_sample_weight(train))
    return pipe


def _eval(valid: pd.DataFrame, prob: np.ndarray, label: str) -> dict[str, Any]:
    scored = valid.copy()
    scored["prob"] = prob
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    return {
        "auc": _safe_float(roc_auc_score(valid[label].astype(int), prob)) if valid[label].nunique() >= 2 else None,
        "top30_label_rate": _safe_float(top[label].mean()) if not top.empty else None,
        "bottom30_label_rate": _safe_float(bottom[label].mean()) if not bottom.empty else None,
        "top30_future_theme_ret_1m": _safe_float(pd.to_numeric(top.get("future_theme_ret_1m"), errors="coerce").mean()) if not top.empty else None,
        "bottom30_future_theme_ret_1m": _safe_float(pd.to_numeric(bottom.get("future_theme_ret_1m"), errors="coerce").mean()) if not bottom.empty else None,
        "top30_future_rank": _safe_float(pd.to_numeric(top.get("future_leading_theme_rank"), errors="coerce").mean()) if not top.empty else None,
    }


def _current_rows(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    cutoff = pd.Timestamp(asof)
    current = df[df["asof_date"] <= cutoff].copy()
    if current.empty:
        current = df.copy()
    return current.sort_values("asof_date").drop_duplicates(["quant_theme_bucket"], keep="last").copy()


def _theme_tag(row: pd.Series) -> str:
    continue_prob = _safe_float(row.get("theme_continue_prob"))
    fade_prob = _safe_float(row.get("theme_fade_prob"))
    score = _safe_float(row.get("theme_persistence_score"))
    if fade_prob is not None and fade_prob >= 0.70:
        return "theme_fade_risk"
    if (fade_prob is not None and fade_prob >= 0.45) or (score is not None and score <= -0.10):
        return "theme_fade_watch"
    if continue_prob is not None and continue_prob >= 0.75 and score is not None and score >= 0.40:
        return "theme_persist_strong"
    if continue_prob is not None and continue_prob >= 0.45 and score is not None and score >= 0.15:
        return "theme_persist_watch"
    return "theme_neutral"


def _json_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (int, float, np.floating)):
        return _safe_float(value)
    if pd.isna(value):
        return None
    return value


def _rows(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict(orient="records")]


def build_theme_persistence_ai(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    mart = _read_theme_context(include_qm_context=False)
    labels = ["label_theme_continue_1m", "label_theme_fade_1m"]
    numeric: list[str] = []
    categorical: list[str] = []
    models: dict[str, Pipeline] = {}
    evaluations: list[dict[str, Any]] = []
    for label in labels:
        train, valid = _split(mart, label, train_end, valid_start, asof)
        if train.empty or valid.empty or train[label].nunique() < 2 or valid[label].nunique() < 2:
            raise SystemExit(f"insufficient rows/classes for {label}: train={len(train)}, valid={len(valid)}")
        if not numeric and not categorical:
            numeric, categorical = _feature_columns(train)
        model = _fit(train, label, numeric, categorical)
        models[label] = model
        prob = model.predict_proba(valid)[:, 1]
        evaluations.append(
            {
                "label": label,
                "head": "continue" if "continue" in label else "fade",
                "training_weight": "recent_1y_x3",
                "train_rows": int(len(train)),
                "valid_rows": int(len(valid)),
                "train_positive_rate": _safe_float(train[label].mean()),
                "valid_positive_rate": _safe_float(valid[label].mean()),
                **_eval(valid, prob, label),
            }
        )

    token = asof.replace("-", "")
    model_version = f"{MODEL_CODE}_{token}_001"
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"{model_version}.joblib"
    tmp_path = model_path.with_name(f"{model_path.name}.tmp")
    joblib.dump(
        {
            "model_code": MODEL_CODE,
            "model_name_ko": MODEL_NAME_KO,
            "model_version": model_version,
            "numeric_features": numeric,
            "categorical_features": categorical,
            "feature_mode": "BASE",
            "models": models,
            "label_horizon_steps": FWD_STEPS_1M,
        },
        tmp_path,
    )
    tmp_path.replace(model_path)

    current = _current_rows(mart, asof)
    current["theme_continue_prob"] = models["label_theme_continue_1m"].predict_proba(current)[:, 1]
    current["theme_fade_prob"] = models["label_theme_fade_1m"].predict_proba(current)[:, 1]
    current["theme_persistence_score"] = current["theme_continue_prob"] - current["theme_fade_prob"]
    current["theme_persistence_tag"] = current.apply(_theme_tag, axis=1)
    current["model_code"] = MODEL_CODE
    current["model_name_ko"] = MODEL_NAME_KO
    current["model_version"] = model_version
    current["as_of_model_date"] = asof

    keep_cols = [
        "model_code",
        "model_name_ko",
        "model_version",
        "as_of_model_date",
        "asof_date",
        "quant_theme_bucket",
        "quantmarket_theme_bucket",
        "theme_name_kr",
        "theme_ret_1w",
        "theme_ret_1m",
        "theme_ret_3m",
        "theme_momentum_score",
        "theme_rotation_score",
        "theme_persistence_days",
        "theme_breadth_positive_ratio",
        "theme_above_sma60_ratio",
        "theme_trading_value_expansion_ratio",
        "theme_concentration_score",
        "leading_theme_rank",
        "mapping_confidence",
        "theme_continue_prob",
        "theme_fade_prob",
        "theme_persistence_score",
        "theme_persistence_tag",
    ]
    current_out = current[[col for col in keep_cols if col in current.columns]].sort_values("theme_persistence_score", ascending=False)
    tag_counts = current_out.groupby("theme_persistence_tag", as_index=False).size().rename(columns={"size": "count"})

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    detail_path = REPORT_DIR / f"theme_persistence_ai_current_scores_{token}.csv"
    eval_path = REPORT_DIR / f"theme_persistence_ai_eval_{token}.json"
    md_path = REPORT_DIR / f"theme_persistence_ai_eval_{token}.md"
    current_json_path = ADMIN_CURRENT_DIR / "theme_persistence_ai_current.json"
    current_out.to_csv(detail_path, index=False, encoding="utf-8-sig")

    payload = {
        "source_name": "theme_persistence_ai_current",
        "schema_version": "1.0",
        "visibility": "admin_only",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "model_version": model_version,
        "model_role": "theme_persistence_shadow",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "feature_mode": "BASE",
        "market_context_source": "QuantMarket handoff primary ridge calibration 20d",
        "optimization_priority": "return_first",
        "target": {
            "continue": "20 trading sessions later: leading theme rank <= 5",
            "fade": "20 trading sessions later: leading theme rank worsens by 3+",
            "theme_persistence_score": "theme_continue_prob - theme_fade_prob",
        },
        "thresholds": {
            "theme_persist_strong": "continue_prob >= 0.75 and score >= 0.40",
            "theme_persist_watch": "continue_prob >= 0.45 and score >= 0.15",
            "theme_neutral": "no strong persistence/fade condition",
            "theme_fade_watch": "fade_prob >= 0.45 or score <= -0.10",
            "theme_fade_risk": "fade_prob >= 0.70",
        },
        "evaluation": evaluations,
        "tag_counts": _rows(tag_counts),
        "top_persistent_themes": _rows(current_out.sort_values("theme_persistence_score", ascending=False), 50),
        "top_fade_risk_themes": _rows(current_out.sort_values("theme_persistence_score", ascending=True), 50),
        "outputs": {
            "model_path": str(model_path),
            "detail_csv": str(detail_path),
            "eval_json": str(eval_path),
            "admin_current_json": str(current_json_path),
        },
    }
    eval_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    current_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# {MODEL_CODE} Evaluation - {asof}",
                "",
                f"- Korean name: {MODEL_NAME_KO}",
                f"- Current theme rows: {len(current_out):,}",
                "",
                "## Evaluation",
                "",
                *[
                    f"- {row['head']} / {row['label']}: AUC={row.get('auc')}, train={row.get('train_rows')}, valid={row.get('valid_rows')}, top30_label_rate={row.get('top30_label_rate')}"
                    for row in evaluations
                ],
                "",
                "## Tag Counts",
                "",
                *[f"- {row['theme_persistence_tag']}: {int(row['count'])}" for row in _rows(tag_counts)],
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI-THEME-PERSISTENCE-V01 theme persistence model.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = build_theme_persistence_ai(args.asof, args.train_end, args.valid_start)
    print(json.dumps({"status": "ok", "model_code": MODEL_CODE, "as_of_date": args.asof, "rows": len(payload["top_persistent_themes"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
