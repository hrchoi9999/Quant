# regime_score.py ver 2026-01-27_001
from __future__ import annotations

import pandas as pd


HORIZONS = {
    "3m": 63,
    "6m": 126,
    "1y": 252,
}


def _pct_rank(df: pd.DataFrame, ascending: bool = True) -> pd.DataFrame:
    """
    Row-wise percentile rank (0~1) across columns (tickers) for each date.
    """
    return df.rank(axis=1, pct=True, ascending=ascending)


def compute_regime_scores(
    close_wide: pd.DataFrame,
    horizons: dict[str, int] | None = None,
    vol_window: int = 63,
    w_ret: float = 0.60,
    w_dd: float = 0.20,
    w_vol: float = 0.20,
) -> dict[str, pd.DataFrame]:
    """
    Parameters
    ----------
    close_wide : DataFrame
        index=date, columns=ticker, values=close
    Returns
    -------
    dict[horizon] -> DataFrame with columns:
        score_pct, score, regime, ret_h, dd_h, vol_63 (long-form은 빌드 스크립트에서 melt)
    """
    if horizons is None:
        horizons = HORIZONS

    close = close_wide.sort_index()
    ret1d = close.pct_change()
    vol = ret1d.rolling(vol_window).std()

    out: dict[str, pd.DataFrame] = {}

    for name, h in horizons.items():
        ret_h = close / close.shift(h) - 1.0
        roll_max = close.rolling(h).max()
        dd_h = 1.0 - (close / roll_max)

        # cross-sectional ranks per date
        ret_rank = _pct_rank(ret_h, ascending=True)          # high is good
        dd_good = 1.0 - _pct_rank(dd_h, ascending=True)      # low dd is good
        vol_good = 1.0 - _pct_rank(vol, ascending=True)      # low vol is good

        score_pct = (w_ret * ret_rank) + (w_dd * dd_good) + (w_vol * vol_good)
        score = (score_pct * 100.0).round(4)

        # 5 bins: [0, .2), [.2,.4), ... [.8,1.0+)
        regime = pd.cut(
            score_pct,
            bins=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0000001],
            labels=[0, 1, 2, 3, 4],
            right=False,
        ).astype("Int64")

        # pack wide metrics (same shape as close)
        # We'll return wide frames; builder will melt to long and write to DB.
        out[name] = {
            "score_pct": score_pct,
            "score": score,
            "regime": regime,
            "ret_h": ret_h,
            "dd_h": dd_h,
            "vol": vol,
        }

    return out
