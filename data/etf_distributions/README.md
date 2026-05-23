ETF Distribution CSV Drop Zone
==============================

Purpose
-------
Place issuer-downloaded ETF cash distribution CSV files here when an issuer site does not expose a stable machine-readable table.

The daily AI overlay pipeline reads this directory through:

    D:\Quant\scripts\fetch_issuer_etf_distributions.py --providers kodex,tiger,csv

Supported Columns
-----------------
The parser accepts common Korean or English headers. Recommended headers:

    ticker,name,distribution_date,pay_date,distribution_amount

Notes
-----
- `ticker` should be a six-digit ETF ticker.
- `distribution_date` should be the 기준일 or 분배락/record date.
- `pay_date` is optional.
- `distribution_amount` should be the per-share cash distribution in KRW.
- Files should be saved as CSV with UTF-8 or UTF-8-SIG encoding.

