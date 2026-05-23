# Legacy / Backfill Script Archive Policy - 2026-04-18

## Summary

The ETF legacy price collector was isolated from the operational code path on 2026-04-18.

Archived script:
- `D:/Quant/archive/legacy_scripts/20260418/src/collectors/prices/fetch_etf_prices_daily.py`

Original path:
- `D:/Quant/src/collectors/prices/fetch_etf_prices_daily.py`

## Reason

The production ETF data path now uses KRX OpenAPI for both:
- ETF universe generation
- ETF daily price collection

The old ETF collector depended on pykrx first and FinanceDataReader as fallback. That made the daily logs confusing because pykrx warnings could appear even though the intended production source was KRX OpenAPI.

## Current Operational Source Of Truth

ETF universe:
- `D:/Quant/src/collectors/universe/build_universe_etf_krx.py`
- Source: KRX OpenAPI ETF daily trading endpoint

ETF prices:
- `D:/Quant/src/collectors/price/fetch_krx_openapi_daily_prices.py --markets ETF`
- Source: KRX OpenAPI

Daily pipeline:
- `D:/Quant/src/quant_service/run_daily_quant_pipeline.py --include-etf`

## Use Policy

Archived scripts are not part of routine operations.

Do not use archived scripts for:
- daily market data refresh
- weekly or monthly model refresh
- public current publishing
- web handoff generation

Archived scripts may be used only for:
- historical reproduction of older research runs
- one-off source comparison
- emergency diagnostics if KRX OpenAPI has an outage

If an archived script is used, record:
- reason for use
- date range
- affected tickers
- whether any result was written back into operational DBs

## Related Note

Stock universe generation still keeps non-primary fallback paths such as pykrx, Naver, FinanceDataReader, and cache for operational resilience. This archive decision applies to the legacy ETF pykrx/FDR daily price collector, not to the stock universe fallback ladder.
