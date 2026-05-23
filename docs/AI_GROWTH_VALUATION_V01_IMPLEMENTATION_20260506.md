# AI-GROWTH-VALUATION-V01 Implementation - 2026-05-06

## Model Identity

- Model code: `AI-GROWTH-VALUATION-V01`
- Korean name: `주가수준평가AI`
- Role: 성장성 대비 현재 주가 수준이 저평가/적정/과열/회피인지 판단하는 독립 AI 모델

## Relationship With Existing AI

Existing model:

- Code: `AI-CANDIDATE-VALIDATION-V01`
- Korean name: `퀀트후보검증AI`
- Legacy alias: `AI-OVERLAY-V01`
- Role: S/T/I 모델 후보가 해당 모델의 성격에 맞는지 평가

New model:

- Code: `AI-GROWTH-VALUATION-V01`
- Role: 후보 종목 자체의 성장성 대비 가격 부담과 하방위험을 평가

Recommended combined interpretation:

- `MS_CONFIRM` + `UNDERVALUED/FAIR`: 강한 후보
- `MS_CONFIRM` + `OVERHEATED`: 후보는 좋지만 신규매수 주의
- `MS_RISK_REVIEW` + `AVOID`: 제외 또는 강한 경계
- `COMMON_CONFIRM` + `FAIR/UNDERVALUED`: 보조 확인

## Implemented Files

- `D:\Quant\src\models\valuation_ai\config.py`
- `D:\Quant\src\models\valuation_ai\common.py`
- `D:\Quant\src\models\valuation_ai\build_market_context.py`
- `D:\Quant\src\models\valuation_ai\build_features.py`
- `D:\Quant\src\models\valuation_ai\build_labels.py`
- `D:\Quant\src\models\valuation_ai\train_model.py`
- `D:\Quant\src\models\valuation_ai\rule_score_engine.py`
- `D:\Quant\src\models\valuation_ai\predict_scores.py`
- `D:\Quant\src\models\valuation_ai\evaluate_model.py`
- `D:\Quant\src\pipelines\rebuild_growth_valuation_ai_pipeline.py`
- `D:\Quant\scripts\build_valuation_ai_overlay_validation.py`
- `D:\Quant\scripts\build_valuation_ai_live_shadow_tracker.py`

## DB

- DB: `D:\Quant\data\db\valuation_ai.db`

Tables:

- `valuation_features_monthly`
- `valuation_market_context_daily`
- `valuation_market_context_monthly`
- `valuation_labels_forward`
- `valuation_ai_scores`
- `valuation_model_eval`
- `valuation_overlay_live_shadow_detail`
- `valuation_overlay_live_shadow_summary`

## Reports

- `D:\Quant\reports\valuation_ai\valuation_features_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_market_context_daily_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_market_context_monthly_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_labels_forward.csv`
- `D:\Quant\reports\valuation_ai\valuation_model_eval_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_scores_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_backtest_eval_20260504.md`
- `D:\Quant\reports\valuation_ai\valuation_overlay_validation_20260504.md`
- `D:\Quant\reports\valuation_ai\valuation_overlay_current_candidates_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_overlay_live_shadow_tracker_20260504_to_20260504.md`
- `D:\Quant\reports\valuation_ai\valuation_overlay_live_shadow_detail_20260504_to_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_overlay_live_shadow_summary_20260504_to_20260504.csv`

## Current Data Coverage

Run date:

- `asof = 2026-05-04`

Feature rows:

- `38,512`

Market context rows:

- Daily: `6,855`
- Monthly: `339`
- Feature rows with market context: `38,155`

Forward 12M label rows:

- `33,018`

Latest scoring universe:

- `400` price-ready stock tickers

Note:

- The base model trains and scores the full 400-stock universe.
- Growth stock flags are managed separately and are not included in base model learning or scoring.
- Growth flags will be used later as an interpretation layer or model variation.

## Current Baseline Evaluation

Model version:

- `AI-GROWTH-VALUATION-V01_20260504_001`

Training:

- Train: `2017-01-31` to `2023-12-28`
- Validation with available 12M labels: `2024-01-31` to `2025-03-31`

Validation result:

- Rank IC: `0.186`
- IC: `0.187`
- Top30 avg excess 12M return: `80.68%`
- Top30 avg 12M return: `126.01%`
- Top-bottom spread: `86.58%`
- Top30 win rate: `76.67%`

Full reconstructed ranking evaluation:

- FULL Rank IC: `0.148`
- FULL top decile avg excess 12M return: `54.31%`
- FULL top-bottom spread: `52.71%`
- FULL top decile win rate: `60.16%`

Top-N portfolio proxy:

| Window | Months | CAGR | MDD | Sharpe |
|---|---:|---:|---:|---:|
| FULL | 99 | 35.33% | -28.41% | 1.267 |
| 1Y | 12 | 42.90% | -5.85% | 2.038 |
| 2Y | 25 | 49.87% | -9.19% | 2.137 |
| 3Y | 37 | 33.09% | -20.63% | 1.307 |
| 5Y | 61 | 51.39% | -23.89% | 1.754 |

## Current Top Scores

2026-05-04 top examples:

| ticker | name | score | state |
|---|---|---:|---|
| `096530` | 씨젠 | 87.96 | `UNDERVALUED` |
| `214150` | 클래시스 | 87.74 | `UNDERVALUED` |
| `160190` | 하이젠알앤엠 | 86.68 | `UNDERVALUED` |
| `035760` | CJ ENM | 85.99 | `UNDERVALUED` |
| `007390` | 네이처셀 | 84.13 | `UNDERVALUED` |

## Important Limitation

This V01 does not yet use true consensus valuation data.

Missing or proxy-based fields:

- Forward PER
- Forward EPS revision
- EV/EBITDA
- true ROIC
- analyst consensus
- industry demand forecast

Current V01 uses available proxies:

- PIT growth score
- revenue/op income growth
- price percentile over 3 years
- sector relative momentum
- market context from `regime.db` and breadth features
- volatility/MDD
- moving average distance

## Market Context Integration

QuantMarket-style market context is now included in the base learning mart.

Source inputs:

- `D:\Quant\data\db\regime.db` table `regime_history`
- `D:\Quant\data\db\price.db` table `prices_daily`
- `D:\Quant\data\db\security_classification.db` table `security_classification_master`

Generated context fields:

- `market_regime`
- `market_regime_label`
- `market_regime_score`
- `market_regime_bullish_pct`
- `market_regime_bearish_pct`
- `market_regime_neutral_pct`
- `market_ret_1m`
- `market_ret_3m`
- `market_ret_6m`
- `market_vol_20d`
- `market_mdd_3m`
- `market_breadth_ret_pos_1m`
- `market_breadth_above_sma60`
- `market_breadth_above_sma120`

Initial effect:

- Validation Rank IC improved from `0.178` to `0.186`.
- Validation Top30 excess 12M return improved from `52.00%` to `80.68%`.
- This supports the hypothesis that valuation signals need market-regime context.

Reverse DCF proxy fields now included:

- `current_valuation_percentile`
- `implied_growth_pressure`
- `valuation_growth_gap`

These are not true DCF values. They are a first-pass proxy for "how much future growth the current price appears to require."

Therefore V01 should be used as a shadow valuation overlay first, not as a final target-price model.

## Deferred Work

These items are intentionally kept outside the V01 base model so the project does not drift away from the core objective.

1. Growth stock flag overlay

- Status: separated from base learning and scoring.
- Reason: the base model should first learn whether price level is favorable across the full 400-stock universe.
- Future use: interpretation layer, variation model, or growth-only slice comparison.

2. Formal DCF / Reverse DCF engine

- Status: deferred to V02 or later.
- Reason: true DCF requires stable assumptions for FCF, WACC, terminal growth, net debt, share count, and scenario logic.
- Current V01 substitute: proxy fields `current_valuation_percentile`, `implied_growth_pressure`, and `valuation_growth_gap`.
- Future use: add as an auxiliary feature after the proxy model has enough shadow/live evidence.

3. Consensus valuation data

- Status: not included.
- Reason: forward PER, EPS revision, EV/EBITDA, analyst consensus, and industry demand forecast are not yet managed as stable production data.
- Future use: add only after source reliability, coverage, and point-in-time handling are confirmed.

## Commands

End-to-end:

```powershell
D:\Quant\venv64\Scripts\python.exe -m src.pipelines.rebuild_growth_valuation_ai_pipeline --asof 2026-05-04
```

Individual steps:

```powershell
D:\Quant\venv64\Scripts\python.exe -m src.models.valuation_ai.build_market_context --start 2017-01-01 --end 2026-05-04
D:\Quant\venv64\Scripts\python.exe -m src.models.valuation_ai.build_features --start 2017-01-01 --end 2026-05-04
D:\Quant\venv64\Scripts\python.exe -m src.models.valuation_ai.build_labels
D:\Quant\venv64\Scripts\python.exe -m src.models.valuation_ai.train_model --train-end 2023-12-31 --valid-start 2024-01-01 --valid-end 2026-05-04
D:\Quant\venv64\Scripts\python.exe -m src.models.valuation_ai.predict_scores --asof 2026-05-04
D:\Quant\venv64\Scripts\python.exe -m src.models.valuation_ai.evaluate_model --asof 2026-05-04
```

## Next Steps

1. Build valuation overlay joins for S/T/I current holdings.
2. Compare S/T/I selected names by `UNDERVALUED`, `FAIR`, `OVERHEATED`, and `AVOID` state.
3. Start live-only shadow tracking by valuation state.
4. Prepare QS payload fields for admin display after the overlay shape is fixed.
5. Test challenger usage such as `S2_PLUS_VALAI` only after shadow evidence is accumulated.

## Overlay Validation - 2026-05-04

Current latest-candidate overlay results:

- Candidate rows checked: `348`
- Valuation-covered rows: `300`
- Out-of-scope rows: `48`, mostly ETF or non-stock rows because V01 is a stock valuation model
- Favorable rows: `41`, split into `UNDERVALUED` and `FAIR`
- `UNDERVALUED` rows inside current S/T/I/user model candidates: `1`
- Caution rows: `259`, split into `OVERHEATED` and `AVOID`

Initial interpretation:

- V01 is more useful as a price-burden warning overlay than as an immediate buy-list generator.
- Current model candidates are already momentum-heavy, so many names score as `OVERHEATED` or `AVOID`.
- Do not auto-remove candidates yet. First track whether `FAIR` candidates outperform `OVERHEATED/AVOID` candidates in live shadow results.

Generated by:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_valuation_ai_overlay_validation.py --asof 2026-05-04
```

## Live Shadow Tracking - 2026-05-04

Live shadow tracking has been implemented for valuation overlay snapshots.

Purpose:

- Track what happens after each valuation overlay snapshot.
- Compare live returns by `valuation_state`: `UNDERVALUED`, `FAIR`, `OVERHEATED`, `AVOID`, `OUT_OF_SCOPE_OR_MISSING`.
- Compare live returns by broader group: `FAVORABLE`, `CAUTION`, `OUT_OF_SCOPE_OR_MISSING`.
- Keep the result separate from backtest metrics.

Initial run:

- Shadow snapshot: `2026-05-04`
- Performance asof: `2026-05-04`
- Detail rows: `348`
- Summary rows: `512`

Important interpretation:

- `current` means return from the overlay snapshot date to the performance asof date.
- Fixed horizons such as `1w`, `2w`, and `1m` remain `N/A` until enough trading days have elapsed.
- Because the first run is snapshot-day tracking, it only validates the plumbing. It is not enough to judge performance yet.

Generated by:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_valuation_ai_live_shadow_tracker.py --shadow-asof 2026-05-04 --asof 2026-05-04
```

Refresh all available snapshots:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_valuation_ai_live_shadow_tracker.py --shadow-asof all --asof YYYY-MM-DD
```
