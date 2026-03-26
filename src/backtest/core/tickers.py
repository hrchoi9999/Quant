# core/tickers.py ver 2026-02-12_001
"""Ticker normalization utilities.

Project-wide invariant (A-plan):
- ticker is a string
- for KRX equities, ticker is 6-digit zero-padded string (e.g., '005930')
- special symbols like 'CASH' are preserved as-is

We keep normalization small and deterministic to ensure golden-regression parity.
"""

from __future__ import annotations

from typing import Iterable, List, Union
import pandas as pd


def normalize_ticker(x: object, *, cash_label: str = "CASH") -> str:
    """Normalize a single ticker value into canonical string form."""
    if x is None:
        return ""
    s = str(x).strip()
    if not s:
        return ""
    if s.upper() == cash_label:
        return cash_label
    # common legacy prefixes
    if s.startswith("A") and s[1:].isdigit():
        s = s[1:]
    # numeric equivalence: keep digits only if purely numeric
    if s.isdigit():
        return s.zfill(6)
    return s


def normalize_ticker_series(s: pd.Series, *, cash_label: str = "CASH") -> pd.Series:
    return s.apply(lambda v: normalize_ticker(v, cash_label=cash_label))


def normalize_ticker_list(xs: Iterable[object], *, cash_label: str = "CASH") -> List[str]:
    return [normalize_ticker(x, cash_label=cash_label) for x in xs]


def normalize_columns_to_tickers(cols: Union[pd.Index, Iterable[object]], *, cash_label: str = "CASH") -> pd.Index:
    if isinstance(cols, pd.Index):
        vals = cols.tolist()
    else:
        vals = list(cols)
    return pd.Index([normalize_ticker(v, cash_label=cash_label) for v in vals])
