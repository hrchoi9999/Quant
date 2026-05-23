from __future__ import annotations

import argparse
import json
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
SOURCE_DIR = ROOT / r"reports\ai_overlay_v01"
REPORT_DIR = ROOT / r"reports\candidate_rank_delta_ai_v01"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
TRACKER_PATH = ADMIN_CURRENT_DIR / "admin_new_entry_tracker.json"

MODEL_CODE = "AI-CANDIDATE-RANK-DELTA-V01"
MODEL_NAME_KO = "후보순위조정AI"
RANDOM_STATE = 42

KEY_COLUMNS = {"scope_key", "model_id", "ticker", "name", "event_date", "week_end", "live_start_date"}
FORWARD_PREFIXES = ("fwd_", "label_", "has_")
EXCLUDED_NUMERIC = {"is_current", "is_live_event"}

LABEL_SPECS: list[dict[str, Any]] = [
    {
        "label": "label_next_rank_drop",
        "kind": "drop",
        "description": "candidate drops out at the next rebalance",
    },
    {
        "label": "label_next_rank_upgrade_3",
        "kind": "upgrade",
        "threshold": 3,
        "description": "next rebalance rank improves by at least 3 places",
    },
    {
        "label": "label_next_rank_upgrade_5",
        "kind": "upgrade",
        "threshold": 5,
        "description": "next rebalance rank improves by at least 5 places",
    },
    {
        "label": "label_next_rank_downgrade_3_or_drop",
        "kind": "downgrade",
        "threshold": -3,
        "include_drop": True,
        "description": "next rebalance rank worsens by at least 3 places or drops out",
    },
    {
        "label": "label_next_rank_downgrade_5_or_drop",
        "kind": "downgrade",
        "threshold": -5,
        "include_drop": True,
        "description": "next rebalance rank worsens by at least 5 places or drops out",
    },
    {
        "label": "label_next_rank_upgrade_3_retained",
        "kind": "upgrade",
        "threshold": 3,
        "retained_only": True,
        "description": "among retained candidates, next rebalance rank improves by at least 3 places",
    },
    {
        "label": "label_next_rank_downgrade_3_retained",
        "kind": "downgrade",
        "threshold": -3,
        "retained_only": True,
        "description": "among retained candidates, next rebalance rank worsens by at least 3 places",
    },
]
LABEL_NAMES = {str(spec["label"]) for spec in LABEL_SPECS}


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _read_mart(asof: str) -> pd.DataFrame:
    path = SOURCE_DIR / f"ai_overlay_training_mart_{asof.replace('-', '')}.csv"
    if not path.exists():
        raise SystemExit(f"missing mart: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    df = df[df["event_date"].notna()].copy()
    if "asset_type" in df.columns:
        asset = df["asset_type"].astype(str).str.upper()
        df = df[~asset.str.contains("ETF", na=False)].copy()
    return df


def _rank_rows_from_tracker() -> pd.DataFrame:
    if not TRACKER_PATH.exists():
        raise SystemExit(f"missing tracker: {TRACKER_PATH}")
    payload = json.loads(TRACKER_PATH.read_text(encoding="utf-8"))
    weekly = payload.get("weekly_rankings") or {}
    rows: list[dict[str, Any]] = []
    for item in weekly.get("user_models", []):
        rows.append(
            {
                "scope_key": "user",
                "model_id": item.get("service_profile") or item.get("model_key"),
                "ticker": item.get("security_code"),
                "name": item.get("display_name"),
                "week_end": item.get("week_end"),
                "snapshot_date": item.get("snapshot_date"),
                "rank_no": item.get("rank_no"),
                "score": item.get("score"),
            }
        )
    for item in weekly.get("internal_models", []):
        rows.append(
            {
                "scope_key": "internal",
                "model_id": item.get("model_code") or item.get("model_key"),
                "ticker": item.get("security_code"),
                "name": item.get("display_name"),
                "week_end": item.get("week_end"),
                "snapshot_date": item.get("snapshot_date"),
                "rank_no": item.get("rank_no"),
                "score": item.get("score"),
            }
        )
    for item in weekly.get("tseries_models", []):
        rows.append(
            {
                "scope_key": "tseries",
                "model_id": item.get("model_code") or item.get("model_key"),
                "ticker": item.get("security_code"),
                "name": item.get("display_name"),
                "week_end": item.get("week_end"),
                "snapshot_date": item.get("snapshot_date"),
                "rank_no": item.get("rank_no"),
                "score": item.get("score"),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        raise SystemExit("weekly rank tracker has no rank rows")
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["week_end"] = pd.to_datetime(out["week_end"], errors="coerce")
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"], errors="coerce")
    out["rank_no"] = pd.to_numeric(out["rank_no"], errors="coerce")
    out["score"] = pd.to_numeric(out["score"], errors="coerce")
    out = out[out["week_end"].notna() & out["rank_no"].notna()].copy()
    return out.drop_duplicates(["scope_key", "model_id", "ticker", "week_end"], keep="last")


def _add_next_rank_labels(mart: pd.DataFrame) -> pd.DataFrame:
    rank_rows = _rank_rows_from_tracker()
    group_cols = ["scope_key", "model_id"]
    key_cols = [*group_cols, "ticker", "week_end"]
    date_rows = rank_rows[group_cols + ["week_end"]].drop_duplicates().sort_values([*group_cols, "week_end"])
    date_rows["next_week_end"] = date_rows.groupby(group_cols)["week_end"].shift(-1)
    rank_rows = rank_rows.merge(date_rows, on=[*group_cols, "week_end"], how="left")
    rank_rows = rank_rows[rank_rows["next_week_end"].notna()].copy()
    next_rank = rank_rows[key_cols + ["rank_no"]].rename(columns={"week_end": "next_week_end", "rank_no": "next_rank_no"})
    labeled = rank_rows.merge(next_rank, on=[*group_cols, "ticker", "next_week_end"], how="left")
    next_size = (
        rank_rows.groupby([*group_cols, "next_week_end"], as_index=False)["rank_no"]
        .max()
        .rename(columns={"rank_no": "next_rank_size"})
    )
    labeled = labeled.merge(next_size, on=[*group_cols, "next_week_end"], how="left")
    labeled["dropped_next_rebalance"] = labeled["next_rank_no"].isna().astype(int)
    labeled["next_rank_no_effective"] = labeled["next_rank_no"].fillna(labeled["next_rank_size"] + 1)
    labeled["next_rank_delta"] = labeled["rank_no"] - labeled["next_rank_no_effective"]
    for spec in LABEL_SPECS:
        label = str(spec["label"])
        if spec["kind"] == "drop":
            labeled[label] = labeled["dropped_next_rebalance"].astype(int)
            continue
        if spec["kind"] == "upgrade":
            hit = labeled["next_rank_delta"] >= float(spec["threshold"])
        else:
            hit = labeled["next_rank_delta"] <= float(spec["threshold"])
            if spec.get("include_drop"):
                hit = hit | labeled["dropped_next_rebalance"].eq(1)
        labeled[label] = hit.astype(int)
        if spec.get("retained_only"):
            labeled.loc[labeled["dropped_next_rebalance"].eq(1), label] = np.nan

    label_cols = [
        *key_cols,
        "next_week_end",
        "next_rank_no",
        "next_rank_no_effective",
        "next_rank_size",
        "next_rank_delta",
        "dropped_next_rebalance",
        *sorted(LABEL_NAMES),
    ]
    mart_key = mart.copy()
    mart_key["week_end"] = mart_key["week_end"].fillna(mart_key["event_date"])
    return mart_key.merge(labeled[label_cols], on=key_cols, how="left", suffixes=("", "_rankhist"))


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    rank_label_cols = {
        "next_week_end",
        "next_rank_no",
        "next_rank_no_effective",
        "next_rank_size",
        "next_rank_delta",
        "dropped_next_rebalance",
    }
    for col in df.columns:
        if col in KEY_COLUMNS or col in EXCLUDED_NUMERIC or col in LABEL_NAMES or col in rank_label_cols:
            continue
        if col.startswith(FORWARD_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
            numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _split(df: pd.DataFrame, label: str, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[label].notna()].sort_values("event_date").copy()
    train = labeled[labeled["event_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["event_date"] >= pd.Timestamp(valid_start)) & (labeled["event_date"] <= pd.Timestamp(valid_end))].copy()
    if len(train) >= 200 and len(valid) >= 50 and train[label].nunique() >= 2 and valid[label].nunique() >= 2:
        return train, valid
    dates = sorted(labeled["event_date"].dropna().unique())
    if len(dates) < 3:
        return train, valid
    cut = dates[max(1, int(len(dates) * 0.80)) - 1]
    return labeled[labeled["event_date"] <= cut].copy(), labeled[labeled["event_date"] > cut].copy()


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


def _fit(train: pd.DataFrame, label: str, numeric: list[str], categorical: list[str]) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=160, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    pipe.fit(train, train[label].astype(int))
    return pipe


def _evaluate(df: pd.DataFrame, label: str, train_end: str, valid_start: str, valid_end: str) -> dict[str, Any]:
    train, valid = _split(df, label, train_end, valid_start, valid_end)
    numeric, categorical = _feature_columns(train)
    spec = next((item for item in LABEL_SPECS if item["label"] == label), {})
    row: dict[str, Any] = {
        "label": label,
        "label_kind": spec.get("kind"),
        "description": spec.get("description"),
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "train_positive_rate": _safe_float(train[label].mean()) if not train.empty else None,
        "valid_positive_rate": _safe_float(valid[label].mean()) if not valid.empty else None,
        "status": "ok",
    }
    if train.empty or valid.empty or train[label].nunique() < 2 or valid[label].nunique() < 2:
        row["status"] = "skipped"
        row["reason"] = "insufficient_rows_or_one_class"
        return row
    model = _fit(train, label, numeric, categorical)
    prob = model.predict_proba(valid)[:, 1]
    scored = valid.copy()
    scored["prob"] = prob
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    row.update(
        {
            "numeric_features": int(len(numeric)),
            "categorical_features": int(len(categorical)),
            "auc": _safe_float(roc_auc_score(valid[label].astype(int), prob)),
            "top30_label_rate": _safe_float(top[label].mean()),
            "bottom30_label_rate": _safe_float(bottom[label].mean()),
            "top_bottom_label_spread": _safe_float(top[label].mean() - bottom[label].mean()),
            "top30_avg_next_rank_delta": _safe_float(top["next_rank_delta"].mean()),
            "bottom30_avg_next_rank_delta": _safe_float(bottom["next_rank_delta"].mean()),
            "top30_drop_rate": _safe_float(top["dropped_next_rebalance"].mean()),
            "bottom30_drop_rate": _safe_float(bottom["dropped_next_rebalance"].mean()),
            "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()),
            "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()),
        }
    )
    return row


def run_rank_change_ablation(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    mart = _add_next_rank_labels(_read_mart(asof))
    rows = [_evaluate(mart, label, train_end, valid_start, asof) for label in sorted(LABEL_NAMES)]
    result = pd.DataFrame(rows).sort_values(["auc", "top_bottom_label_spread"], ascending=False, na_position="last")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    csv_path = REPORT_DIR / f"candidate_rank_delta_rank_change_ablation_{token}.csv"
    json_path = REPORT_DIR / f"candidate_rank_delta_rank_change_ablation_{token}.json"
    md_path = REPORT_DIR / f"candidate_rank_delta_rank_change_ablation_{token}.md"
    labeled_path = REPORT_DIR / f"candidate_rank_delta_rank_change_labels_{token}.csv"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig")
    label_cols = [
        "scope_key",
        "model_id",
        "ticker",
        "name",
        "event_date",
        "week_end",
        "rank_no",
        "next_week_end",
        "next_rank_no",
        "next_rank_no_effective",
        "next_rank_delta",
        "dropped_next_rebalance",
        *sorted(LABEL_NAMES),
    ]
    mart[[col for col in label_cols if col in mart.columns]].to_csv(labeled_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "candidate_rank_delta_rank_change_ablation",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "label_source": str(TRACKER_PATH),
        "labeled_rows": int(mart[sorted(LABEL_NAMES)].notna().any(axis=1).sum()),
        "results": result.where(pd.notna(result), None).to_dict(orient="records"),
        "outputs": {"csv": str(csv_path), "json": str(json_path), "md": str(md_path), "labeled_csv": str(labeled_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# Candidate Rank Delta Rank-Change Ablation - {asof}",
                "",
                f"- Model: {MODEL_CODE} / {MODEL_NAME_KO}",
                f"- Label source: `{TRACKER_PATH}`",
                f"- Labeled rows: {payload['labeled_rows']:,}",
                "",
                "| label | auc | top30_label | bottom30_label | top30_rank_delta | bottom30_rank_delta | top30_drop |",
                "|---|---:|---:|---:|---:|---:|---:|",
                *[
                    "| {label} | {auc} | {top30_label_rate} | {bottom30_label_rate} | {top30_avg_next_rank_delta} | {bottom30_avg_next_rank_delta} | {top30_drop_rate} |".format(
                        **{k: "" if pd.isna(v) else v for k, v in row.items()}
                    )
                    for row in result.to_dict(orient="records")
                ],
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run next-rebalance rank-change label ablation for AI-CANDIDATE-RANK-DELTA-V01.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run_rank_change_ablation(args.asof, args.train_end, args.valid_start)
    print(
        json.dumps(
            {
                "status": "ok",
                "as_of_date": args.asof,
                "labeled_rows": payload["labeled_rows"],
                "best": payload["results"][0] if payload["results"] else None,
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
