# ETF 전용 AI 시장 Context 및 학습 구조 - 2026-05-11

## 핵심 판단

ETF 전용 AI는 ETF 자체 데이터만으로 학습하면 안 된다.

ETF는 개별 기업 실적보다 다음 요소의 영향을 더 크게 받는다.

- 주식시장 전반 추세/모멘텀
- risk-on / risk-off 국면
- 환율, 금, 채권, 원자재 등 방어/대체자산 흐름
- 외국인/기관 수급
- 테마/섹터 rotation
- ETF 상품 구조: 레버리지, 인버스, 환헤지, 자산군, 역할

따라서 ETF AI는 `ETF 자체 feature + 시장 context + ETF role interaction` 구조로 설계한다.

## 현재 사용 가능한 시장 Context

QuantMarket 제공 경로:

- `D:\QuantMarket\service_platform\ai_training\market_context\current`

### 1. Market Context

파일:

- `market_context_daily_current.csv`

주요 feature:

- `market_state_label`
- `market_state_score`
- `trend_score`
- `breadth_score`
- `risk_score`
- `defensive_flow_score`
- `kospi_ret_1m`
- `kospi_ret_3m`
- `kosdaq_ret_1m`
- `kosdaq_ret_3m`
- `market_vol_20d`
- `market_mdd_3m`
- `market_breadth_ret_pos_1m`
- `market_breadth_above_sma20`
- `market_breadth_above_sma60`
- `market_breadth_above_sma120`
- `new_high_ratio_20d`
- `new_low_ratio_20d`
- `trading_value_expansion_ratio`
- `risk_on_score`
- `risk_off_score`

ETF 적용 의미:

- `CORE_BETA`, `SECTOR_THEME`, `STYLE_FACTOR` ETF에는 risk-on/trend/breadth가 중요하다.
- `DEFENSIVE_HEDGE`, `TACTICAL_HEDGE` ETF에는 risk_off/market_mdd/stress가 중요하다.

### 2. Risk Context

파일:

- `risk_context_daily_current.csv`

주요 feature:

- `usdkrw_ret_1m`
- `gold_proxy_ret_1m`
- `bond_proxy_ret_1m`
- `inverse_etf_ret_1m`
- `defensive_asset_strength_score`
- `market_stress_score`
- `drawdown_pressure_score`
- `crash_warning_flag`
- `volatility_regime_label`

ETF 적용 의미:

- 달러, 금, 장기채, 인버스 ETF는 일반 주식형 ETF와 반대로 움직일 수 있다.
- risk context는 ETF 선택뿐 아니라 ETF role별 배분비 결정에 직접 들어가야 한다.

### 3. Flow Context

파일:

- `flow_context_daily_current.csv`

주요 feature:

- `foreign_net_buy_ratio`
- `institution_net_buy_ratio`
- `retail_net_buy_ratio`
- `foreign_buying_breadth`
- `institution_buying_breadth`
- `flow_concentration_score`
- `smart_money_score`
- `flow_context_available`
- `flow_coverage_flag`

ETF 적용 의미:

- 외국인/기관 risk-on 여부를 ETF 배분에 반영한다.
- 다만 현재 flow source는 2026-03-26 이후 availability가 있으므로, 과거 학습에서는 결측 처리가 필요하다.

### 4. Theme Context

파일:

- `theme_context_daily_quant_bucket_current.csv`

주요 feature:

- `theme_ret_1w`
- `theme_ret_1m`
- `theme_ret_3m`
- `theme_momentum_score`
- `theme_rotation_score`
- `theme_persistence_days`
- `theme_breadth_positive_ratio`
- `theme_above_sma60_ratio`
- `theme_trading_value_expansion_ratio`
- `theme_concentration_score`
- `leading_theme_rank`
- `mapping_confidence`

ETF 적용 의미:

- `SECTOR_THEME` ETF에는 관련 theme bucket과 연결해서 사용할 수 있다.
- 단 ETF-to-theme mapping이 별도로 필요하다.
- 초기에는 `role_key=SECTOR_THEME`인 ETF에만 제한적으로 붙이는 것이 좋다.

## 추가로 정의해야 할 시장 요소

현재 QM context에 일부 proxy는 있지만, ETF 모델의 장기 확장을 위해 아래를 별도 데이터 과제로 둔다.

### 글로벌 주식시장

- S&P 500
- Nasdaq 100
- Russell 2000
- MSCI EM proxy
- China/Hang Seng Tech proxy
- Japan/Nikkei proxy

적용 ETF:

- 해외주식형 ETF
- 미국성장/기술주 ETF
- 중국/일본/신흥국 ETF

### 금리/채권

- 한국 국고채 3Y/10Y
- 미국 국채 2Y/10Y
- 장단기 금리차
- 금리 변화율

적용 ETF:

- 장기채 ETF
- 단기채/금리형 ETF
- 커버드콜/배당형 ETF
- 성장주 ETF valuation pressure proxy

### 환율

- USD/KRW spot
- USD/KRW 1M/3M 변화율
- 달러 강세 regime

적용 ETF:

- 미국/해외주식 ETF
- 환헤지/비헤지 ETF
- 달러선물 ETF
- 원자재 ETF

### 원자재

- 금
- WTI
- 구리
- 원자재 basket

적용 ETF:

- 금 ETF
- 원유 ETF
- 원자재 ETF
- 인플레이션 hedge ETF

## ETF AI 학습 구조

### Layer 1. ETF Native Feature Layer

ETF 자체 상태를 만든다.

입력:

- ETF meta
- ETF PIT feature panel
- price.db
- T-ETF output

feature:

- role_key
- asset_class
- group_key
- currency_exposure
- is_inverse
- is_leveraged
- liquidity_20d_value
- ret_20d/60d/120d/240d
- vol_20d/60d
- dd_60d/120d
- dist_ma20/60/120
- rsi20
- stage1_prob
- stage2_prob

역할:

- ETF 자체 momentum/risk/liquidity/timing 측정

### Layer 2. Market Context Layer

시장 국면을 만든다.

입력:

- QM market context
- QM risk context
- QM flow context
- regime.db
- 향후 global/macro context

feature:

- risk_on_score
- risk_off_score
- market_state_score
- trend_score
- breadth_score
- market_vol_20d
- market_mdd_3m
- market_stress_score
- drawdown_pressure_score
- usdkrw_ret_1m
- gold_proxy_ret_1m
- bond_proxy_ret_1m
- smart_money_score

역할:

- 지금 ETF 시장이 공격/방어/중립 중 어디에 가까운지 판단

### Layer 3. Role Interaction Layer

ETF role과 시장 context의 상호작용을 만든다.

예:

- `CORE_BETA * risk_on_score`
- `SECTOR_THEME * theme_rotation_score`
- `DEFENSIVE_HEDGE * risk_off_score`
- `TACTICAL_HEDGE * market_stress_score`
- `Tactical leverage * market_vol_20d`
- `USD exposure * usdkrw_ret_1m`
- `Bond ETF * bond_proxy_ret_1m`
- `Gold ETF * gold_proxy_ret_1m`

역할:

- 같은 시장 context라도 ETF role마다 의미가 다르다는 점을 학습시킨다.

예시:

- risk_on_score 상승은 KOSPI200 ETF에는 긍정적일 수 있다.
- 같은 risk_on_score 상승은 인버스 ETF에는 부정적일 수 있다.
- market_stress_score 상승은 방어/헤지 ETF에는 긍정적일 수 있다.

### Layer 4. Specialist ETF AI

초기에는 3개 specialist 모델을 둔다.

#### 1. `AI-ETF-TIMING-V01`

목적:

- ETF 단기 진입 타이밍 판단

label 후보:

- 1W/2W/1M forward return positive
- 1W/2W/1M top quantile
- T-ETF confirmed/near 승격 여부

주요 feature:

- ETF native momentum
- T-ETF stage1/stage2 score
- market trend/breadth
- role interaction

#### 2. `AI-ETF-ROLE-ALLOCATION-V01`

목적:

- ETF role별 배분 적합도 판단

label 후보:

- role 내 1M/3M risk-adjusted return 상위
- `forward_return - drawdown_penalty`
- regime별 sleeve 성과 상위

주요 feature:

- role_key
- risk_on/risk_off
- market stress
- defensive asset strength
- ETF native risk/return

초기 champion 후보:

- `AI-ETF-ROLE-ALLOCATION-V01`

#### 3. `AI-ETF-RISK-CONTROL-V01`

목적:

- ETF caution tag 생성

label 후보:

- 1M path MDD threshold 초과
- 저유동성 + 고변동 + 급락 조합
- 레버리지/인버스 위험 구간

주요 feature:

- volatility
- drawdown
- liquidity
- leverage/inverse flag
- market_vol/stress

### Layer 5. ETF Meta Allocation AI

specialist output을 합쳐 최종 ETF sleeve를 만든다.

입력:

- ETF timing score
- ETF role allocation score
- ETF risk control tag
- market regime
- ETF allocation baseline

출력:

- ETF별 최종 allocation score
- role별 target weight
- caution/exclusion tag
- T-ETF shadow candidate comparison

## 학습 데이터 구성 원칙

### Point-in-time 원칙

모든 feature는 `signal_date` 또는 `feature_date` 기준으로 과거/당일 확정값만 사용한다.

금지:

- forward return
- future MDD
- 사후 확정된 role/classification 변경값 무비판 사용

### Role-aware 학습

ETF 전체를 하나의 label로 섞지 않는다.

최소 분리:

- CORE_BETA
- SECTOR_THEME
- STYLE_FACTOR
- DEFENSIVE_HEDGE
- TACTICAL_HEDGE
- TACTICAL_LEVERAGE

### Regime-aware 학습

동일 ETF도 국면별 label 의미가 달라진다.

예:

- risk_on: core beta/sector theme 선호
- neutral: style factor/defensive carry 선호
- risk_off: defensive hedge/tactical hedge 선호

### Horizon-aware 학습

ETF role별 horizon을 다르게 둔다.

| role | primary horizon |
|---|---|
| TACTICAL_HEDGE | 1W/2W |
| TACTICAL_LEVERAGE | 1W/2W |
| SECTOR_THEME | 1M/3M |
| CORE_BETA | 1M/3M |
| DEFENSIVE_HEDGE | 1M/3M |
| STYLE_FACTOR | 1M/3M |

## 초기 실험 순서

1. ETF market context join mart 생성
   - ETF PIT feature panel + QM market/risk/flow context
   - role interaction feature 추가

2. Label ablation
   - timing label
   - risk-adjusted allocation label
   - drawdown avoidance label
   - role-aware label
   - regime-aware label

3. `AI-ETF-ROLE-ALLOCATION-V01` baseline 학습
   - ETF role별 AUC
   - top-k return
   - top-k MDD
   - role coverage

4. `AI-ETF-TIMING-V01` 실험
   - T-ETF stage1/stage2 score 결합
   - 1W/2W/1M label 비교

5. `AI-ETF-RISK-CONTROL-V01` 실험
   - 레버리지/인버스 별도 성능 분리
   - low-liquidity high-vol caution 검증

## 운영 반영 원칙

- ETF AI는 주식 AI와 완전히 별도 model_code로 운영한다.
- 최초에는 admin-only shadow tracking만 한다.
- public 추천/배분에는 바로 반영하지 않는다.
- T-ETF 기존 모델은 유지하고, ETF AI는 처음에는 overlay/score provider로 붙인다.
- NAV/iNAV, tracking error, AUM/보수 데이터가 들어오기 전까지는 “ETF 적정가치”라는 표현을 쓰지 않는다.
- 초기 명칭은 `ETF 역할별 배분 AI` 또는 `ETF 배분적합도AI`가 더 적절하다.

