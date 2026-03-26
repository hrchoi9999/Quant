# etf_classifier.py ver 2026-03-17_001
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _find_project_root(start_path: Path) -> Path:
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    return start_path


def load_rules(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    data.setdefault("defaults", {})
    data.setdefault("rules", [])
    data.setdefault("required_groups", [])
    data.setdefault("optional_groups", [])
    data["rules"] = sorted(data["rules"], key=lambda x: int(x.get("priority", 9999)))
    return data


def load_overrides(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["ticker"])
    return pd.read_csv(path, dtype={"ticker": "string"}).fillna("")


def _match_rule(name: str, rule: dict[str, Any]) -> bool:
    patterns = [str(x) for x in rule.get("match_any", []) if str(x).strip()]
    if not patterns:
        return False
    target = str(name)
    return any(pat.lower() in target.lower() for pat in patterns)


def classify_etfs(master_df: pd.DataFrame, rules: dict[str, Any], overrides_df: pd.DataFrame) -> pd.DataFrame:
    df = master_df.copy()
    if "ticker" not in df.columns or "name" not in df.columns:
        raise ValueError("master_df must include ticker and name")

    df["ticker"] = df["ticker"].astype(str).str.strip().str.zfill(6)
    df["asset_class"] = ""
    df["group_key"] = ""
    df["currency_exposure"] = "KRW"
    df["is_inverse"] = False
    df["is_leveraged"] = False
    df["exclude_from_core"] = False
    df["classification_rule"] = ""

    for idx, row in df.iterrows():
        name = str(row.get("name", ""))
        for rule in rules.get("rules", []):
            if _match_rule(name, rule):
                for key, value in (rule.get("set", {}) or {}).items():
                    df.at[idx, key] = value
                if not df.at[idx, "classification_rule"]:
                    df.at[idx, "classification_rule"] = str(rule.get("name", ""))

    if not overrides_df.empty:
        override_cols = set(overrides_df.columns)
        for _, row in overrides_df.iterrows():
            ticker = str(row.get("ticker", "")).strip().zfill(6)
            mask = df["ticker"] == ticker
            if not mask.any():
                continue
            for col in [
                "name_override",
                "asset_class",
                "group_key",
                "currency_exposure",
                "is_inverse",
                "is_leveraged",
                "exclude_from_core",
            ]:
                if col not in override_cols:
                    continue
                value = row.get(col, "")
                if value == "":
                    continue
                if col == "name_override":
                    df.loc[mask, "name"] = str(value)
                    continue
                if col in {"is_inverse", "is_leveraged", "exclude_from_core"}:
                    bool_value = str(value).strip().lower() in {"1", "true", "y", "yes"}
                    df.loc[mask, col] = bool_value
                else:
                    df.loc[mask, col] = value
            df.loc[mask, "classification_rule"] = "override"

    df["is_inverse"] = df["is_inverse"].astype(bool)
    df["is_leveraged"] = df["is_leveraged"].astype(bool)
    df["exclude_from_core"] = df["exclude_from_core"].astype(bool)
    return df


def default_rule_paths() -> tuple[Path, Path]:
    root = _find_project_root(Path(__file__).resolve().parent)
    return (
        root / "data" / "universe" / "etf_classification_rules.yml",
        root / "data" / "universe" / "etf_meta_overrides.csv",
    )
