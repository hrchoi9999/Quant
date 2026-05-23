# AI 학습 공통축: 시장국면별 역할 배분 - 2026-05-11

## 핵심 원칙

앞으로 Quant의 AI 학습 모델은 ETF든 주식이든 다음 공통축을 기본 구조로 관리한다.

`개별 후보 feature + 시장국면 context + 후보 역할/전략 role interaction`

이 원칙은 단순 feature 추가가 아니라 AI 학습 구조의 기본 설계 원칙이다.

## 왜 필요한가

같은 종목/ETF라도 시장국면에 따라 의미가 달라진다.

예:

- risk-on 국면의 성장주/섹터 ETF는 긍정적으로 해석될 수 있다.
- risk-off 국면의 같은 성장주/섹터 ETF는 위험 신호일 수 있다.
- risk-off 국면의 현금성/채권/달러/인버스 ETF는 방어 역할을 할 수 있다.
- 주식 후보도 S/T/I/C 전략 목적에 따라 같은 market context를 다르게 받아들여야 한다.

따라서 AI는 “좋은 후보”만 예측하는 것이 아니라 “현재 시장국면에서 어떤 역할의 후보가 유리한가”를 학습해야 한다.

## 공통 학습 Layer

### Layer 1. Candidate Native Feature

후보 자체의 상태.

- 주식: 가격, 모멘텀, 재무, 수급, valuation, risk, theme
- ETF: 가격, 유동성, role, 레버리지/인버스, 변동성, MDD, T-ETF score

### Layer 2. Market Regime Context

시장 전체 상태.

- trend
- breadth
- volatility
- MDD/stress
- risk_on/risk_off
- defensive asset strength
- FX/rate/commodity proxy
- foreign/institution flow

### Layer 3. Role/Strategy Axis

후보가 어떤 역할을 하는지.

주식:

- S-series: 핵심 주식 후보
- T-series: 타이밍 후보
- I-series: 강한 단기/초기 신호 후보
- C-series: 관계/테마/헤지 보조 후보

ETF:

- CORE_BETA
- SECTOR_THEME
- STYLE_FACTOR
- DEFENSIVE_HEDGE
- TACTICAL_HEDGE
- TACTICAL_LEVERAGE

### Layer 4. Regime x Role Interaction

시장국면과 후보 역할의 상호작용.

예:

- `risk_on_score x CORE_BETA`
- `risk_on_score x S-series`
- `risk_off_score x DEFENSIVE_HEDGE`
- `market_stress_score x TACTICAL_HEDGE`
- `market_vol_20d x T-series`
- `theme_rotation_score x SECTOR_THEME`

## 운영 원칙

- 앞으로 신규 AI 모델 문서에는 `market context 사용 여부`와 `role interaction 사용 여부`를 명시한다.
- label ablation은 최소한 `NATIVE`, `MARKET_CONTEXT`, `ROLE_INTERACTION` 세 모드로 비교한다.
- 단일 AUC만 보지 않고 top-k return, top-k MDD, role coverage도 함께 본다.
- ETF는 role별 배분/위험 제어가 핵심이고, 주식은 전략별 후보 보강/위험 제어가 핵심이다.

