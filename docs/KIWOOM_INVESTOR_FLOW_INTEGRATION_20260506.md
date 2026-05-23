# Kiwoom Investor Flow Integration - 2026-05-06

## Summary

Kiwoom REST API has been connected as the official investor-flow source for AI feature expansion.

Key files are stored locally under `D:\Quant\config`.
Secret values must never be printed in logs, reports, or chat.

## Source

- Host: `https://api.kiwoom.com`
- Token endpoint: `/oauth2/token`
- Investor flow endpoint: `/api/dostk/stkinfo`
- API ID: `ka10059`
- API name: `종목별투자자기관별요청`

Official references:

- Kiwoom REST API guide: `https://openapi.kiwoom.com/guide/apiguide`
- Kiwoom REST API main: `https://openapi.kiwoom.com/main`

## Collector

- `D:\Quant\scripts\collect_investor_flows_kiwoom.py`

Target DB:

- `D:\Quant\data\db\ai_feature_ext.db`

Target table:

- `investor_flows_daily`

Source marker:

- `kiwoom_rest_ka10059`

## Smoke Test

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\collect_investor_flows_kiwoom.py --end 2026-05-04 --start 2026-05-04 --limit 5 --sleep 0.02
```

Result:

- status: `ok`
- universe_count: `5`
- rows: `65`
- errors: `0`

## Full Load

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\collect_investor_flows_kiwoom.py --end 2026-05-04 --start 2026-02-03 --sleep 0.03
```

Initial result:

- status: `partial`
- universe_count: `400`
- rows saved: `306,709`
- rate limit errors: `6`

Retry result:

- status: `ok`
- retry tickers: `6`
- rows saved: `4,680`

Final DB coverage:

- date range: `2026-02-03` to `2026-05-04`
- rows: `311,389`
- tickers: `400`
- investor groups: `13`

Investor groups:

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

## AI Overlay Rebuild

Command:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_ai_overlay_v01.py --asof 2026-05-04
```

Result:

- mart rows: `20,819`
- 1M label rows: `20,427`
- live rows: `322`
- shadow rows: `2,736`
- Kiwoom feature rows: `721`

Evaluation:

| label | model | train | test | auc | top30 1M return | top30 win rate |
|---|---:|---:|---:|---:|---:|---:|
| label_quality_1m | logistic | 15663 | 4764 | 0.503 | 1.05% | 60.00% |
| label_quality_1m | gb | 15663 | 4764 | 0.533 | 4.90% | 76.67% |
| label_risk_1m | logistic | 15663 | 4764 | 0.505 | 6.05% | 46.67% |
| label_risk_1m | gb | 15663 | 4764 | 0.529 | 15.66% | 63.33% |

Interpretation:

- Kiwoom investor-flow data is now present in the AI mart.
- Because Kiwoom historical coverage currently begins at `2026-02-03`, it is still too short to materially affect the historical train/test score.
- Keep AI overlay in shadow mode until more live labels accumulate or Kiwoom flow is backfilled farther.

## 2024 Backfill Update

The first collector version only saved the first 100 Kiwoom rows per ticker because it did not follow the continuation cursor.

Cause:

- `ka10059` returns about 100 trading rows per request.
- The response header can include:
  - `cont-yn=Y`
  - `next-key=<older date cursor>`
- The collector now follows `next-key` until the requested `--start` date is reached.

Backfill command:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\collect_investor_flows_kiwoom.py --end 2026-05-04 --start 2024-01-01 --sleep 0.08
```

Backfill result:

- status: `ok`
- universe_count: `400`
- rows saved: `2,856,607`
- date range: `2024-01-02` to `2026-05-04`
- tickers: `400`
- investor groups: `13`
- errors: `0`

AI overlay rerun after 2024 backfill:

- Kiwoom feature rows in mart: `5,587`

Evaluation:

| label | model | train | test | auc | top30 1M return | top30 win rate |
|---|---:|---:|---:|---:|---:|---:|
| label_quality_1m | logistic | 15663 | 4764 | 0.495 | 6.45% | 53.33% |
| label_quality_1m | gb | 15663 | 4764 | 0.521 | 7.00% | 83.33% |
| label_risk_1m | logistic | 15663 | 4764 | 0.497 | 4.22% | 60.00% |
| label_risk_1m | gb | 15663 | 4764 | 0.520 | 7.65% | 50.00% |

Interpretation:

- Kiwoom feature coverage improved from `721` to `5,587` mart rows.
- AUC weakened versus the pre-backfill run, but top30 1M return and quality win rate improved.
- This is a mixed result, so the AI overlay should remain shadow-only.
- Next step is feature ablation:
  - base features only
  - base + Kiwoom
  - base + DART
  - base + Kiwoom + DART
