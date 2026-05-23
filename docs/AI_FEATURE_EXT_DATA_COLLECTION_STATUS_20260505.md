# AI Feature Extension Data Collection Status - 2026-05-05

## Scope

This note records the first collection pass for AI learning feature expansion.

Included now:

- Investor flow data
- OpenDART official disclosure events

Excluded for now:

- News data

## Storage

Feature extension DB:

- `D:\Quant\data\db\ai_feature_ext.db`

Tables:

- `investor_flows_daily`
- `dart_disclosure_events`

## DART Official Disclosure Events

Collector:

- `D:\Quant\scripts\collect_dart_disclosure_events.py`

Source:

- OpenDART list API

Key source:

- `D:\Quant\.env` / `DART_API_KEY`

Smoke test:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\collect_dart_disclosure_events.py --start 2026-05-04 --end 2026-05-05
```

Result:

- status: `ok`
- rows: `356`
- saved: `356`
- categories:
  - `other_disclosure`: 148
  - `ownership`: 116
  - `earnings_guidance`: 58
  - `major_event`: 20
  - `market_watch`: 9
  - `periodic_report`: 5

Initial AI feature use:

- recent disclosure count
- event category flags
- ownership/major-event/earnings-guidance recency
- disclosure shock around model entry dates

## Investor Flow Data

Primary collector scaffold:

- `D:\Quant\scripts\collect_investor_flows.py`

Temporary Naver collector:

- `D:\Quant\scripts\collect_investor_flows_naver.py`

Kiwoom REST collector:

- `D:\Quant\scripts\collect_investor_flows_kiwoom.py`

Target table:

- `investor_flows_daily`
- `investor_flows_naver_meta_daily`

Official-source status:

- KRX OpenAPI service list does not currently expose an investor-by-ticker flow API for the approved services in this project.
- Kiwoom REST API is now connected as the preferred operating source.
- Naver Finance was used only as a temporary bridge source.

Temporary Naver implementation:

- Source page: Naver Finance `frgn.naver`
- Stores `기관합계` and `외국인` net buy volume by ticker/date.
- Stores derived `net_value = net_volume * close`, because Naver page exposes net volume but not full investor buy/sell value.
- Stores close, volume, and foreign holding rate in `investor_flows_naver_meta_daily`.
- Source marker: `naver_finance_frgn_derived_value`

Smoke test:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\collect_investor_flows.py --start 2026-05-04 --end 2026-05-04
```

Result:

- status: `ok`
- rows: `0`
- saved: `0`
- universe_count: `400`
- errors: `0`

Finding:

- The current pykrx investor flow endpoint returned empty rows.
- Direct KRX Data Portal hidden endpoint testing returned `LOGOUT`.
- The approved KRX OpenAPI service list currently used by this project includes daily stock/ETF/index trading data, but does not expose a free official investor-by-ticker flow endpoint in the same OpenAPI list.

Decision:

- Keep the DB table and collector scaffold.
- Use Naver investor flow features only as temporary/shadow features until Kiwoom is connected.
- Treat DART event features as the first usable external feature extension.

Naver full-universe temporary load:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\collect_investor_flows_naver.py --pages 3 --sleep 0.12
```

Result:

- status: `ok`
- universe_count: `400`
- flow rows: `47,906`
- meta rows: `23,953`
- date range: `2026-02-03` to `2026-05-04`
- investors:
  - `기관합계`: `23,953`
  - `외국인`: `23,953`
- errors: `0`

Temporary-use caution:

- Naver is not the final operating source.
- Do not mix Naver and Kiwoom rows without source-aware validation.
- When Kiwoom is connected, compare overlapping dates/tickers and then decide whether to replace Naver rows or keep them only as bridge history.

Kiwoom REST full-universe load:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\collect_investor_flows_kiwoom.py --end 2026-05-04 --start 2026-02-03 --sleep 0.03
```

Initial full run:

- status: `partial`
- universe_count: `400`
- rows saved: `306,709`
- rate-limited tickers: `6`

Retry run:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\collect_investor_flows_kiwoom.py --end 2026-05-04 --start 2026-02-03 --universe-file D:\Quant\_tmp\kiwoom_retry_tickers.csv --sleep 0.5
```

Retry result:

- status: `ok`
- retry tickers: `6`
- rows saved: `4,680`
- final Kiwoom rows: `311,389`
- date range: `2026-02-03` to `2026-05-04`
- tickers: `400`
- investor groups: `13`

Kiwoom investor groups:

- `개인`
- `외국인`
- `기관합계`
- `금융투자`
- `보험`
- `투신`
- `기타금융`
- `은행`
- `연기금`
- `사모`
- `국가`
- `기타법인`
- `기타외국인`

AI integration status:

- `AI-OVERLAY-V01` now reads Kiwoom source rows where `source='kiwoom_rest_ka10059'`.
- Naver-specific temporary features are no longer the active source for AI overlay.

## Next Steps

1. Add DART event features into `build_ai_overlay_v01.py`.
2. Compare Kiwoom vs Naver overlap for the latest 10 trading days:
   - ticker coverage
   - net-volume sign match
   - net-volume rank correlation
   - missing/zero anomaly rate
3. Continue using Kiwoom as the official flow source and add rolling features:
   - foreign net buy value 5d/20d
   - institution net buy value 5d/20d
   - consecutive foreign/institution net-buy days
   - net-buy value divided by trading value
