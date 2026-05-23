# ETF 전용 AI 데이터/Feature Inventory - 2026-05-11

## 목적

ETF 전용 AI 모델 개발 전에 현재 Quant가 보유한 ETF 데이터와 바로 사용할 수 있는 feature, 추가 수집이 필요한 feature를 정리한다.

ETF는 주식용 `주가수준평가AI`, `하락위험예측AI`, `후보순위조정AI`를 그대로 확장하지 않는다. 별도 `AI-ETF-*` 트랙으로 개발한다.

## 기준일

- 데이터 기준일: `2026-05-08`
- inventory 생성 스크립트: `D:\Quant\scripts\build_etf_ai_feature_inventory.py`
- 결과:
  - `D:\Quant\reports\etf_ai_feature_inventory\etf_ai_feature_inventory_20260508.json`
  - `D:\Quant\reports\etf_ai_feature_inventory\etf_ai_feature_inventory_20260508.md`

## 현재 보유 데이터

| 구분 | 상태 |
|---|---:|
| ETF master | 874 rows |
| ETF meta | 874 rows |
| ETF core universe | 23 rows |
| ETF PIT monthly panel | 8,837 rows |
| ETF price coverage | 874 / 874 |
| latest ETF price date | 2026-05-08 |
| T-ETF feature panel | 8,837 rows |
| T-ETF operational candidates | 16 rows |

## ETF 분류 상태

Asset class:

| asset_class | count |
|---|---:|
| `UNKNOWN` | 548 |
| `equity` | 216 |
| `bond` | 73 |
| `fx` | 18 |
| `hedge` | 13 |
| `commodity` | 6 |

Role:

| role_key | count |
|---|---:|
| `SECTOR_THEME` | 300 |
| `DEFENSIVE_HEDGE` | 182 |
| `CORE_BETA` | 145 |
| `STYLE_FACTOR` | 124 |
| `TACTICAL_LEVERAGE` | 45 |
| `TACTICAL_HEDGE` | 40 |
| `UNCLASSIFIED` | 38 |

해석:

- 가격/유동성/role 분류는 ETF AI 실험에 바로 사용할 수 있다.
- `asset_class`와 `group_key`에는 `UNKNOWN`이 많다.
- 다만 `role_key`는 대부분 채워져 있으므로 초기 모델은 `role_key` 중심으로 시작하는 것이 현실적이다.

## 바로 사용 가능한 feature

- ETF identity: ticker, name, active flag, history proxy
- ETF classification: `asset_class`, `group_key`, `expanded_group`, `role_key`
- Product structure: `currency_exposure`, `is_inverse`, `is_leveraged`
- Liquidity: `liquidity_20d_value`, price DB의 volume/value
- Trend/momentum: `ret_20d`, `ret_60d`, `ret_120d`, `ret_240d`
- Risk: `vol_20d`, `vol_60d`, `dd_60d`, `dd_120d`, `path_mdd_3M/6M/1Y`
- MA state: `dist_ma20/60/120`, `ma20_ma60_gap`, `ma60_ma120_gap`
- Oscillator: `rsi20`
- T-ETF scores: `stage1_prob`, `stage2_prob`, `candidate_grade`
- ETF allocation backtest metrics: CAGR, MDD, Sharpe, turnover

## 현재 없는 ETF 고유 feature

추가 수집 필요:

- NAV/iNAV 및 괴리율
- 공식 추종지수와 tracking error
- 총보수, AUM, 상장좌수
- 기초지수 식별자와 지수 수익률
- ETF 구성종목/비중
- 호가 스프레드 또는 intraday liquidity proxy
- 설정/환매 또는 ETF fund flow
- ETF 노출별 FX/원자재/금리/해외지수 context

## T-ETF 현재 상태

T-ETF current output은 이미 존재한다.

현재 상위 stage1 후보는 인버스/헤지형 ETF가 많이 잡힌다.

예:

- `TIGER 인버스`
- `KODEX 인버스`
- `TIGER 원유선물인버스(H)`
- `KODEX WTI원유선물인버스(H)`
- `KODEX 미국달러선물`

해석:

- 2026-05-08 기준 T-ETF는 공격적 성장 ETF보다 방어/헤지/인버스 성격을 강하게 보고 있다.
- ETF AI는 단일 “좋은 ETF” 모델이 아니라 `역할별 선택/배분` 구조가 되어야 한다.

## ETF Allocation Backtest

현재 ETF allocation P0 결과:

| metric | value |
|---|---:|
| CAGR | 0.211289 |
| MDD | -0.083688 |
| Sharpe | 1.804079 |
| turnover | 0.400000 |
| 1Y CAGR | 0.710906 |
| 1Y Sharpe | 3.601840 |
| 1Y MDD | -0.083212 |

해석:

- ETF allocation은 이미 투자 성과 측면에서 의미 있는 baseline이 있다.
- ETF AI는 이 allocation baseline을 대체하기보다, 처음에는 `role별 ETF score`, `risk-adjusted allocation score`, `regime별 sleeve score`를 보강하는 방향이 적합하다.

## 첫 개발 방향 제안

ETF AI를 하나의 모델로 바로 만들지 말고 3층으로 나눈다.

1. `AI-ETF-TIMING-V01`
   - 목적: ETF 단기 진입/관찰 타이밍
   - horizon: 1W/2W/1M
   - 기반: T-ETF feature panel + price/liquidity/momentum/risk

2. `AI-ETF-ROLE-ALLOCATION-V01`
   - 목적: CORE_BETA / DEFENSIVE_HEDGE / TACTICAL_HEDGE / SECTOR_THEME 등 역할별 배분 적합도
   - horizon: 1M/3M
   - 기반: role_key + regime + risk-adjusted return

3. `AI-ETF-RISK-CONTROL-V01`
   - 목적: 레버리지/인버스/저유동성/고변동 ETF caution tag
   - horizon: 1W/1M drawdown avoidance
   - 기반: volatility, MDD, liquidity, product structure

초기 champion 후보:

- `AI-ETF-ROLE-ALLOCATION-V01`

이유:

- ETF는 단순 종목 추천보다 자산군/역할별 배분이 핵심이다.
- 이미 ETF allocation baseline과 role taxonomy가 존재한다.
- T-ETF는 timing feature provider로 흡수하기 좋다.

## 다음 작업

1. ETF label ablation 설계
   - 1W/2W tactical return
   - 1M/3M risk-adjusted return
   - drawdown avoidance
   - role-aware label
   - regime-aware label

2. `AI-ETF-ROLE-ALLOCATION-V01` baseline 학습
   - ETF PIT monthly feature panel 사용
   - ETF role별 label 분리
   - 평가: AUC, top-k return, top-k MDD, role coverage

3. 부족 데이터 수집 계획 분리
   - NAV/iNAV
   - tracking error
   - expense/AUM
   - holdings/index mapping

## 운영 원칙

- ETF AI는 주식 AI와 별도 model_code 체계로 관리한다.
- ETF 추천/배분은 public 반영 전 최소 4~8주 shadow tracking을 둔다.
- 레버리지/인버스 ETF는 일반 ETF와 같은 label로 섞지 않는다.
- T-ETF는 폐기하지 않고 ETF AI의 timing/score feature provider로 활용한다.
