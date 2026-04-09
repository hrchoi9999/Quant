from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from .model_profiles import PUBLIC_EXPOSED_SERVICE_PROFILES
from .types import TimingFeatureSnapshot


PUBLIC_REPORT_PATH = Path(r"D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json")
PUBLIC_CHANGES_PATH = Path(r"D:\Quant\service_platform\web\public_data\current\user_recent_changes.json")
TSERIES_PATH = Path(r"D:\Quant\service_platform\web\public_data\current\quantservice_tseries_discovery.json")
PRICE_DB_PATH = Path(r"D:\Quant\data\db\price.db")
FUND_DB_PATH = Path(r"D:\Quant\data\db\fundamentals.db")


@dataclass(frozen=True)
class TargetSecurity:
    ticker: str
    name: str
    model_code: str
    service_profile: str
    asset_group: str
    is_recommended: bool
    is_held: bool
    source_channel: str


def _z6(value: object) -> str:
    return str(value).strip().zfill(6)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _public_model_code(service_profile: str) -> str:
    mapping = {
        "stable": "STABLE",
        "balanced": "BALANCED",
        "growth": "GROWTH",
        "auto": "AUTO",
    }
    return mapping.get(str(service_profile).strip().lower(), str(service_profile).strip().upper())


def _is_public_exposed_service_profile(service_profile: str) -> bool:
    return str(service_profile).strip().lower() in PUBLIC_EXPOSED_SERVICE_PROFILES


def load_public_model_targets(
    report_path: Path = PUBLIC_REPORT_PATH,
    changes_path: Path = PUBLIC_CHANGES_PATH,
) -> List[TargetSecurity]:
    report_payload = _load_json(report_path)
    changes_payload = _load_json(changes_path)

    model_name_to_profile: Dict[str, str] = {}
    merged: Dict[tuple[str, str], TargetSecurity] = {}

    for report in report_payload.get("reports", []):
        service_profile = str(report.get("service_profile") or "").strip().lower()
        if not _is_public_exposed_service_profile(service_profile):
            continue
        model_code = _public_model_code(service_profile)
        model_name = str(report.get("user_model_name") or "").strip()
        if model_name:
            model_name_to_profile[model_name] = service_profile
        for item in report.get("allocation_items", []):
            security_code = item.get("security_code")
            if not security_code:
                continue
            ticker = _z6(security_code)
            key = (ticker, model_code)
            merged[key] = TargetSecurity(
                ticker=ticker,
                name=str(item.get("display_name") or ticker),
                model_code=model_code,
                service_profile=service_profile,
                asset_group=str(item.get("asset_group") or ""),
                is_recommended=bool(merged[key].is_recommended) if key in merged else False,
                is_held=True,
                source_channel="public_model_portfolio",
            )

    for change in changes_payload.get("changes", []):
        service_profile = model_name_to_profile.get(str(change.get("user_model_name") or "").strip(), "")
        if not _is_public_exposed_service_profile(service_profile):
            continue
        model_code = _public_model_code(service_profile)
        for item in change.get("increase_items", []):
            security_code = item.get("security_code")
            if not security_code:
                continue
            ticker = _z6(security_code)
            key = (ticker, model_code)
            existing = merged.get(key)
            merged[key] = TargetSecurity(
                ticker=ticker,
                name=str(item.get("display_name") or (existing.name if existing else ticker)),
                model_code=model_code,
                service_profile=service_profile,
                asset_group=existing.asset_group if existing else "",
                is_recommended=True,
                is_held=existing.is_held if existing else False,
                source_channel=existing.source_channel if existing else "public_model_changes",
            )

    return sorted(merged.values(), key=lambda row: (row.model_code, row.ticker))


def load_tseries_targets(tseries_path: Path = TSERIES_PATH) -> List[TargetSecurity]:
    payload = _load_json(tseries_path)
    merged: Dict[tuple[str, str], TargetSecurity] = {}
    for model in payload.get("models", []):
        meta = model.get("meta") or {}
        model_code = str(meta.get("service_model_code") or model.get("model_code") or "").strip().upper()
        service_profile = str(meta.get("service_model_code") or model_code).strip().lower()
        top_by_bucket = model.get("top_by_bucket") or {}
        for bucket_name in ("confirmed", "near", "observe"):
            for row in top_by_bucket.get(bucket_name, []) or []:
                ticker = row.get("ticker")
                if not ticker:
                    continue
                ticker = _z6(ticker)
                key = (ticker, model_code)
                merged[key] = TargetSecurity(
                    ticker=ticker,
                    name=str(row.get("name") or ticker),
                    model_code=model_code,
                    service_profile=service_profile,
                    asset_group=str(meta.get("asset_scope") or ""),
                    is_recommended=True,
                    is_held=False,
                    source_channel=f"tseries_{bucket_name}",
                )
    return sorted(merged.values(), key=lambda row: (row.model_code, row.ticker))


def load_all_targets() -> List[TargetSecurity]:
    merged: Dict[tuple[str, str], TargetSecurity] = {}
    for row in [*load_public_model_targets(), *load_tseries_targets()]:
        key = (row.ticker, row.model_code)
        existing = merged.get(key)
        if existing is None:
            merged[key] = row
            continue
        merged[key] = TargetSecurity(
            ticker=row.ticker,
            name=existing.name or row.name,
            model_code=row.model_code,
            service_profile=existing.service_profile or row.service_profile,
            asset_group=existing.asset_group or row.asset_group,
            is_recommended=existing.is_recommended or row.is_recommended,
            is_held=existing.is_held or row.is_held,
            source_channel=existing.source_channel,
        )
    return sorted(merged.values(), key=lambda row: (row.model_code, row.ticker))


def _read_sql(db_path: Path, query: str, params: Iterable[object] = ()) -> pd.DataFrame:
    with sqlite3.connect(str(db_path)) as con:
        return pd.read_sql_query(query, con, params=list(params))


def _rank_high(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.rank(pct=True)


def _clip01(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(series, errors="coerce").clip(lower=0.0, upper=1.0)


def _load_price_metrics(
    tickers: List[str],
    *,
    data_asof_date: str,
    price_db_path: Path = PRICE_DB_PATH,
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["ticker"])
    placeholders = ",".join(["?"] * len(tickers))
    df = _read_sql(
        price_db_path,
        f"""
        SELECT ticker, date, close
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND date <= ?
        ORDER BY ticker, date
        """,
        params=[*tickers, data_asof_date],
    )
    if df.empty:
        return pd.DataFrame(columns=["ticker"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    rows: List[dict] = []
    for ticker, group in df.groupby("ticker"):
        group = group.sort_values("date").reset_index(drop=True)
        group["ma20"] = group["close"].rolling(20, min_periods=20).mean()
        group["ma60"] = group["close"].rolling(60, min_periods=60).mean()
        group["ma120"] = group["close"].rolling(120, min_periods=120).mean()
        group["ma60_slope_5"] = group["ma60"].diff(5)
        group["mom20"] = group["close"] / group["close"].shift(20) - 1.0
        last = group.iloc[-1]
        close = float(last["close"]) if pd.notna(last["close"]) else None
        ma60 = float(last["ma60"]) if pd.notna(last["ma60"]) else None
        ma120 = float(last["ma120"]) if pd.notna(last["ma120"]) else None
        ma60_slope_5 = float(last["ma60_slope_5"]) if pd.notna(last["ma60_slope_5"]) else None
        mom20 = float(last["mom20"]) if pd.notna(last["mom20"]) else None
        dist_ma60 = (close / ma60 - 1.0) if close is not None and ma60 not in (None, 0.0) else None
        ma_stack_gap = (ma60 / ma120 - 1.0) if ma60 not in (None, 0.0) and ma120 not in (None, 0.0) else None
        rows.append(
            {
                "ticker": ticker,
                "close": close,
                "ma60": ma60,
                "ma120": ma120,
                "close_above_ma60": bool(close is not None and ma60 is not None and close > ma60),
                "ma60_above_ma120": bool(ma60 is not None and ma120 is not None and ma60 > ma120),
                "ma60_slope_positive": bool(ma60_slope_5 is not None and ma60_slope_5 > 0),
                "dist_ma60": dist_ma60,
                "ma_stack_gap": ma_stack_gap,
                "mom20": mom20,
            }
        )
    return pd.DataFrame(rows)


def _load_fundamental_metrics(
    tickers: List[str],
    *,
    data_asof_date: str,
    fund_db_path: Path = FUND_DB_PATH,
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["ticker"])
    placeholders = ",".join(["?"] * len(tickers))
    df = _read_sql(
        fund_db_path,
        f"""
        SELECT date, ticker, revenue_yoy, op_income_yoy, growth_score, valid_fund
        FROM s2_fund_scores_monthly
        WHERE ticker IN ({placeholders})
          AND date <= ?
        ORDER BY ticker, date
        """,
        params=[*tickers, data_asof_date],
    )
    if df.empty:
        return pd.DataFrame(columns=["ticker"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"])
    for col in ("revenue_yoy", "op_income_yoy", "growth_score", "valid_fund"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    rows: List[dict] = []
    for ticker, group in df.groupby("ticker"):
        group = group.sort_values("date").reset_index(drop=True)
        valid_group = group[group["valid_fund"].fillna(0) == 1].copy()
        if valid_group.empty:
            rows.append({"ticker": ticker})
            continue
        valid_group["rev_delta_3m"] = valid_group["revenue_yoy"].diff(3)
        valid_group["op_delta_3m"] = valid_group["op_income_yoy"].diff(3)
        last = valid_group.iloc[-1]
        rows.append(
            {
                "ticker": ticker,
                "growth_score": float(last["growth_score"]) if pd.notna(last["growth_score"]) else None,
                "rev_delta_3m": float(last["rev_delta_3m"]) if pd.notna(last["rev_delta_3m"]) else None,
                "op_delta_3m": float(last["op_delta_3m"]) if pd.notna(last["op_delta_3m"]) else None,
            }
        )
    return pd.DataFrame(rows)


def build_feature_snapshots(
    *,
    targets: List[TargetSecurity],
    signal_date: str,
    data_asof_date: str,
    market_gate_open: bool = True,
    price_db_path: Path = PRICE_DB_PATH,
    fund_db_path: Path = FUND_DB_PATH,
) -> List[TimingFeatureSnapshot]:
    if not targets:
        return []
    tickers = sorted({row.ticker for row in targets})
    target_df = pd.DataFrame(
        [
            {
                "ticker": row.ticker,
                "name": row.name,
                "model_code": row.model_code,
                "service_profile": row.service_profile,
                "asset_group": row.asset_group,
                "is_recommended": row.is_recommended,
                "is_held": row.is_held,
                "source_channel": row.source_channel,
            }
            for row in targets
        ]
    )
    price_df = _load_price_metrics(tickers, data_asof_date=data_asof_date, price_db_path=price_db_path)
    fund_df = _load_fundamental_metrics(tickers, data_asof_date=data_asof_date, fund_db_path=fund_db_path)
    merged = target_df.merge(price_df, on="ticker", how="left").merge(fund_df, on="ticker", how="left")

    merged["rev_accel_pct"] = _rank_high(merged.get("rev_delta_3m"))
    merged["op_accel_pct"] = _rank_high(merged.get("op_delta_3m"))
    merged["growth_pct"] = _rank_high(merged.get("growth_score"))
    merged["fund_accel_score"] = merged[["rev_accel_pct", "op_accel_pct", "growth_pct"]].mean(axis=1, skipna=True)

    merged["ma_stack_gap_pct"] = _rank_high(merged.get("ma_stack_gap"))
    merged["dist_ma60_pct"] = _rank_high(merged.get("dist_ma60"))
    merged["mom20_pct"] = _rank_high(merged.get("mom20"))

    merged["trend_align_score"] = (
        merged["close_above_ma60"].fillna(False).astype(int)
        + merged["ma60_above_ma120"].fillna(False).astype(int)
        + merged["ma60_slope_positive"].fillna(False).astype(int)
        + _clip01(merged["ma_stack_gap_pct"]).fillna(0.0)
    ) / 4.0
    merged["overheat_score"] = merged[["dist_ma60_pct", "mom20_pct"]].mean(axis=1, skipna=True)

    snapshots: List[TimingFeatureSnapshot] = []
    for row in merged.itertuples(index=False):
        snapshots.append(
            TimingFeatureSnapshot(
                ticker=row.ticker,
                signal_date=signal_date,
                security_name=str(getattr(row, "name", "") or row.ticker),
                data_asof_date=data_asof_date,
                selected_by_upstream=bool(row.is_recommended),
                is_currently_held=bool(row.is_held),
                close_above_ma60=bool(getattr(row, "close_above_ma60", False)),
                ma60_above_ma120=bool(getattr(row, "ma60_above_ma120", False)),
                ma60_slope_positive=bool(getattr(row, "ma60_slope_positive", False)),
                market_gate_open=bool(market_gate_open),
                fund_accel_score=float(row.fund_accel_score) if pd.notna(row.fund_accel_score) else None,
                trend_align_score=float(row.trend_align_score) if pd.notna(row.trend_align_score) else None,
                overheat_score=float(row.overheat_score) if pd.notna(row.overheat_score) else None,
            )
        )
    return snapshots


def build_daily_feature_snapshots_from_public_sources(
    *,
    signal_date: str,
    data_asof_date: str,
    include_tseries: bool = True,
    market_gate_open: bool = True,
    price_db_path: Path = PRICE_DB_PATH,
    fund_db_path: Path = FUND_DB_PATH,
) -> Dict[str, List[TimingFeatureSnapshot]]:
    targets = load_public_model_targets()
    if include_tseries:
        targets.extend(load_tseries_targets())
    grouped: Dict[str, List[TargetSecurity]] = {}
    for target in targets:
        grouped.setdefault(target.model_code, []).append(target)
    out: Dict[str, List[TimingFeatureSnapshot]] = {}
    for model_code, model_targets in grouped.items():
        out[model_code] = build_feature_snapshots(
            targets=model_targets,
            signal_date=signal_date,
            data_asof_date=data_asof_date,
            market_gate_open=market_gate_open,
            price_db_path=price_db_path,
            fund_db_path=fund_db_path,
        )
    return out
