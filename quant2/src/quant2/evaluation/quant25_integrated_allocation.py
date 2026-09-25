"""One funded stock/defensive-ETF book, using frozen monthly ETF intent."""

from dataclasses import replace

import pandas as pd

from src.quant2.evaluation.quant25_risk_allocation import risk_targets


def integrated_targets(stock_events, etf_events, calendar, modes=None, *, fixed_exposure=None, defensive=False, cap=20):
    scaled, records = risk_targets(stock_events, calendar, modes, fixed_exposure=fixed_exposure)
    etf_ordered = sorted(etf_events, key=lambda e: e.published_at)
    output, rows = [], []
    for event, record in zip(scaled, records.to_dict("records")):
        weights = {}
        etf_record = {"etf_signal_date": None, "etf_publication": None, "etf_target": 0.0, "etf_names": 0}
        if defensive:
            available = [
                e
                for e in etf_ordered
                if e.published_at <= event.published_at and e.decision_date <= event.decision_date
            ]
            if not available:
                raise ValueError("no already-published ETF intent")
            etf = available[-1]
            ew = {t: float(w) for t, w in etf.weights.items()}
            if any(not 0 <= w <= 1 for w in ew.values()) or abs(sum(ew.values()) - 1) > 1e-9:
                raise ValueError("invalid ETF weights")
            weights = {t: w * (1 - record["budget"]) for t, w in ew.items() if t != "CASH" and w > 0}
            if len(weights) > 5 or set(weights) & (set(event.weights) - {"CASH"}):
                raise ValueError("ETF count or stock overlap violation")
            etf_record = {
                "etf_signal_date": etf.decision_date.strftime("%Y-%m-%d"),
                "etf_publication": etf.published_at.isoformat(),
                "etf_target": sum(weights.values()),
                "etf_names": len(weights),
            }
        weights.update({t: w for t, w in event.weights.items() if t != "CASH" and w > 0})
        if len(weights) > cap:
            raise ValueError("target holding cap breached")
        weights["CASH"] = 1 - sum(weights.values())
        if weights["CASH"] < -1e-10:
            raise ValueError("unfunded integrated target")
        weights["CASH"] = max(0.0, weights["CASH"])
        output.append(replace(event, weights=weights, run_id="Q25_INTEGRATED_20_30"))
        rows.append(
            {**record, **etf_record, "cash_target": weights["CASH"], "target_names": len(weights) - 1, "total_cap": cap}
        )
    return output, pd.DataFrame(rows)
