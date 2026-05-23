# AI-GROWTH-VALUATION-V01 Feature Group Ablation - 2026-05-06

## 목적

QuantMarket 추가 context 데이터를 AI-GROWTH-VALUATION-V01에 반영하기 전에, 어떤 feature group이 실제 성능 개선에 기여하는지 분해 검증했다.

평가 기준일은 `2026-05-04`이며, 학습/검증 구조는 다음과 같다.

- Train: `2017-01-31` ~ `2023-12-28`
- Validation holdout: `2024-01-31` ~ `2025-03-31`
- Target: `fwd_excess_ret_12m`
- 모델: GradientBoostingRegressor, 기존 valuation score rule engine 결합

## 실험 조합

| feature set | 설명 |
|---|---|
| BASE_CORE | 가격, 섹터/테마, PIT 펀더멘털 중심. 시장 context 없음 |
| LOCAL_MARKET | BASE_CORE + Quant 내부 market context |
| QM_MARKET | BASE_CORE + QuantMarket market context |
| QM_MARKET_RISK | QM_MARKET + QuantMarket risk context |
| QM_MARKET_THEME | QM_MARKET + QuantMarket theme context |
| QM_MARKET_THEME_RISK | QM_MARKET + theme + risk context |
| QM_FULL | 현재 config 전체 feature. local market + QuantMarket full context |

## Validation Holdout 핵심 결과

| feature set | Rank IC | Top30 excess 12M | Top30 ret 12M | Spread | Win rate |
|---|---:|---:|---:|---:|---:|
| BASE_CORE | 0.178 | 52.00% | 93.70% | 57.19% | 63.33% |
| LOCAL_MARKET | 0.186 | 80.68% | 126.01% | 86.58% | 76.67% |
| QM_MARKET | 0.188 | 53.17% | 91.52% | 59.10% | 63.33% |
| QM_MARKET_RISK | 0.183 | 80.02% | 126.69% | 83.32% | 80.00% |
| QM_MARKET_THEME | 0.179 | 99.06% | 146.85% | 107.49% | 83.33% |
| QM_MARKET_THEME_RISK | 0.178 | 79.77% | 132.49% | 84.92% | 83.33% |
| QM_FULL | 0.174 | 75.75% | 129.76% | 82.39% | 76.67% |

## Top-N Proxy 핵심 결과

FULL window 기준:

| feature set | CAGR | MDD | Sharpe |
|---|---:|---:|---:|
| BASE_CORE | 35.06% | -29.00% | 1.265 |
| LOCAL_MARKET | 35.33% | -28.41% | 1.267 |
| QM_MARKET | 42.43% | -31.04% | 1.203 |
| QM_MARKET_RISK | 39.44% | -28.01% | 1.356 |
| QM_MARKET_THEME | 34.54% | -31.40% | 1.236 |
| QM_MARKET_THEME_RISK | 33.07% | -31.59% | 1.189 |
| QM_FULL | 36.35% | -28.96% | 1.289 |

1Y window 기준:

| feature set | CAGR | MDD | Sharpe |
|---|---:|---:|---:|
| BASE_CORE | 41.06% | -4.78% | 2.076 |
| LOCAL_MARKET | 42.90% | -5.85% | 2.038 |
| QM_MARKET | 42.66% | -4.74% | 1.827 |
| QM_MARKET_RISK | 42.94% | -4.41% | 1.935 |
| QM_MARKET_THEME | 43.60% | -4.72% | 1.962 |
| QM_MARKET_THEME_RISK | 41.22% | -4.42% | 1.768 |
| QM_FULL | 50.06% | -4.93% | 2.098 |

## 해석

1. `LOCAL_MARKET`는 기존 기준 모델로 계속 유효하다.
   - Rank IC, Top30 excess, win rate가 BASE_CORE 대비 모두 개선된다.

2. `QM_MARKET` 단독은 순위 안정성은 가장 높지만, Top30 수익성과 win rate는 약하다.
   - 시장 상태 정보만으로는 종목 후보 선별력이 충분하지 않다.

3. `QM_MARKET_THEME`가 holdout Top30 성과를 가장 크게 개선했다.
   - Top30 excess 99.06%, Top30 ret 146.85%, spread 107.49%, win rate 83.33%.
   - 성장주 주가수준 평가에서는 테마 rotation/context가 중요한 설명 변수일 가능성이 높다.

4. `QM_MARKET_RISK`는 안정성 보강에 의미가 있다.
   - Holdout Top30 win rate 80.00%, FULL Sharpe 1.356으로 risk context가 포트폴리오 안정성에는 도움이 된다.

5. `QM_FULL`은 최근 1Y Top-N proxy가 가장 좋지만, Rank IC는 가장 낮다.
   - 너무 많은 feature가 전체 universe ranking에는 노이즈를 만들 수 있다.
   - 다만 최근 시장 구간의 Top-N 선별에는 유리하게 작동했다.

## 1차 결론

지금 단계에서 `QM_FULL`을 바로 champion으로 올리는 것은 이르다.

권장 운영 방향:

- Champion/reference: `LOCAL_MARKET`
- Challenger 1: `QM_MARKET_THEME`
- Challenger 2: `QM_MARKET_RISK`
- Observation: `QM_FULL`

특히 `QM_MARKET_THEME`는 holdout Top30 성과가 가장 좋아서, 다음 단계에서 후보군 선별용 challenger로 집중 검증할 가치가 높다.

## 다음 작업

1. `QM_MARKET_THEME`와 `QM_MARKET_RISK`를 별도 model_version으로 저장해 shadow scoring 한다.
2. 최신 S/T/I/user 후보 overlay에서 두 challenger가 어떤 종목을 승격/강등하는지 비교한다.
3. theme mapping confidence가 낮은 bucket을 제외하거나 낮은 weight로 처리한 추가 실험을 수행한다.
4. 실제 운영 성과 tracker에 `valuation_ai_variant` 필드를 붙여 champion/challenger별 live 성과를 분리 추적한다.

## 산출물

- `D:\Quant\scripts\run_valuation_ai_feature_ablation.py`
- `D:\Quant\reports\valuation_ai\valuation_ai_feature_ablation_20260504.md`
- `D:\Quant\reports\valuation_ai\valuation_ai_feature_ablation_validation_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_ai_feature_ablation_windows_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_ai_feature_ablation_20260504.json`
