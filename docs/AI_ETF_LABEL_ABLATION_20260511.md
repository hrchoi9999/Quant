# ETF AI Label Ablation - 2026-05-11

## 목적

ETF 전용 AI의 첫 학습 mart를 만들고, 시장국면 context가 ETF label 예측에 도움이 되는지 확인한다.

이번 실험은 model_code 기준으로는 `AI-ETF-ROLE-ALLOCATION-V01` 작업 디렉터리를 사용했지만, 한글명과 최종 모델명은 아직 확정하지 않는다.

## 입력 데이터

기준일:

- `2026-05-08`

입력:

- ETF PIT feature panel
  - `D:\Quant\reports\model_upgrade_research\20260508\ETF_T_SERIES_PIT_BACKFILL_V1\etf_tseries_pit_feature_panel.csv`
- ETF 가격
  - `D:\Quant\data\db\price.db::prices_daily`
- QM market context
  - `market_context_daily_current.csv`
  - `risk_context_daily_current.csv`
  - `flow_context_daily_current.csv`

생성 mart:

- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_market_context_mart_20260508.csv`

mart 규모:

| 항목 | 값 |
|---|---:|
| rows | 8,837 |
| signal dates | 113 |

role 분포:

| role | count |
|---|---:|
| `STYLE_FACTOR` | 4,055 |
| `CORE_BETA` | 2,016 |
| `SECTOR_THEME` | 1,435 |
| `DEFENSIVE_HEDGE` | 1,093 |
| `TACTICAL_HEDGE` | 238 |

## Feature Modes

| mode | 설명 |
|---|---|
| `ETF_NATIVE` | ETF 자체 feature만 사용 |
| `MARKET_CONTEXT` | ETF native + QM market/risk/flow context |
| `ROLE_INTERACTION` | ETF native + QM context + role x market interaction |

## Label 후보

| label | 의미 |
|---|---|
| `label_tactical_1w_pos` | 1W forward return > 0 |
| `label_tactical_2w_pos` | 2W forward return > 0 |
| `label_tactical_1m_pos` | 1M forward return > 0 |
| `label_drawdown_safe_1m` | 1M return >= 0 and path MDD >= -5% |
| `label_role_top30_1m_risk_adj` | 같은 날짜/role 내 1M risk-adjusted score 상위 30% |
| `label_role_top30_3m_risk_adj` | 같은 날짜/role 내 3M risk-adjusted score 상위 30% |

## 결과 요약

Best:

| feature_mode | label | AUC | top30 label | bottom30 label |
|---|---|---:|---:|---:|
| `MARKET_CONTEXT` | `label_tactical_2w_pos` | 0.589858 | 0.966667 | 0.333333 |

상위 결과:

| feature_mode | label | kind | AUC |
|---|---|---|---:|
| `MARKET_CONTEXT` | `label_tactical_2w_pos` | timing | 0.589858 |
| `ROLE_INTERACTION` | `label_drawdown_safe_1m` | risk | 0.576287 |
| `MARKET_CONTEXT` | `label_drawdown_safe_1m` | risk | 0.572058 |
| `ROLE_INTERACTION` | `label_tactical_2w_pos` | timing | 0.567494 |
| `ETF_NATIVE` | `label_tactical_1m_pos` | timing | 0.567380 |

## 해석

1. 시장 context는 ETF 학습에 의미가 있다.
   - `label_tactical_2w_pos` 기준 AUC가 `ETF_NATIVE 0.546396`에서 `MARKET_CONTEXT 0.589858`로 개선됐다.
   - ETF 모델은 시장국면을 기본 feature 축으로 넣는 것이 맞다.

2. 현재 role-allocation label은 약하다.
   - `label_role_top30_1m_risk_adj`, `label_role_top30_3m_risk_adj`는 AUC가 0.5 근처 또는 이하이다.
   - 단순 role/date 내 top30 risk-adjusted label은 ETF 배분 적합도를 충분히 설명하지 못한다.

3. 단기 timing label이 먼저 잘 잡힌다.
   - 2W positive label이 가장 높다.
   - T-ETF가 timing 성격을 갖고 있기 때문에 자연스러운 결과다.

4. Role interaction은 아직 일관된 개선을 만들지 못했다.
   - drawdown-safe label에서는 개선 신호가 있다.
   - timing 2W에서는 MARKET_CONTEXT보다 낮다.
   - role interaction은 feature 설계 개선 후 재실험이 필요하다.

## 다음 개선 방향

1. ETF role-allocation label 재설계
   - 단순 top30 대신 sleeve 기여도 기반 label
   - 예: 해당 ETF를 role 대표로 편입했을 때 portfolio return/MDD 개선 여부

2. Regime-aware label 분리
   - risk_on / neutral / risk_off별로 label을 따로 계산
   - risk_on에서는 CORE_BETA/SECTOR_THEME, risk_off에서는 DEFENSIVE_HEDGE/TACTICAL_HEDGE를 다르게 평가

3. Horizon 분리
   - timing: 1W/2W
   - allocation: 1M/3M
   - risk-control: 1M MDD

4. Role mapping 개선
   - 현재 mart의 role은 derived rule 기반이다.
   - `role_key` PIT panel 또는 stable role taxonomy를 mart에 직접 붙이는 개선 필요

## Outputs

- `D:\Quant\scripts\run_etf_ai_label_ablation.py`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_market_context_mart_20260508.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_label_ablation_20260508.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_label_ablation_20260508.json`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_label_ablation_20260508.md`

## 현재 판단

ETF AI는 시장국면 context를 기본축으로 넣어야 한다.

하지만 `AI-ETF-ROLE-ALLOCATION-V01`의 현재 label은 아직 champion으로 삼기 어렵다.

다음 단계는 `ETF allocation portfolio contribution label` 또는 `regime-aware role label`을 만드는 것이다.

