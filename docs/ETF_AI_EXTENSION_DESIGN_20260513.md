# E Series ETF 전용 AI 모델 확장 설계

- 작성일: 2026-05-13
- 대상: Quant thread
- 상태: 설계안
- 원칙: ETF는 주식 AI overlay와 별도 트랙으로 관리

## 정식 모델 정의

ETF 전용 전략모델은 `E series`로 관리합니다.

| 구분 | 코드 | 한글명 | 역할 |
| --- | --- | --- | --- |
| 전략모델 | `E-ETF-V01` | ETF전용 E시리즈AI | ETF 전용 최종 전략모델 |
| AI 포트폴리오 엔진 | `AI-E-ETF-PORTFOLIO-V01` | E시리즈 ETF포트폴리오AI | E series shadow portfolio 생성 |
| 역할배분 AI | `AI-E-ETF-ROLE-ALLOCATION-V01` | ETF역할배분AI | 시장 모드별 ETF 역할군 선택 |
| 비중템플릿 AI | `AI-E-ETF-ROLE-WEIGHT-TEMPLATE-V01` | ETF비중템플릿AI | 역할군별 비중 템플릿 선택 |

기존 `AI-ETF-SHADOW-PORTFOLIO-V01`은 이전 payload 호환을 위한 legacy alias로만 유지합니다.

`E-ETF-V01`은 T-ETF의 하위 모델이 아닙니다.
처음부터 ETF 전용 데이터, ETF 전용 label, ETF 전용 AI 학습 구조를 포함하는 독립 전략모델입니다.

## 현재 상태

현재 ETF AI는 아래 구조까지 구성되어 있습니다.

- `E-ETF-V01` / `ETF전용 E시리즈AI`
- `AI-E-ETF-PORTFOLIO-V01` / `E시리즈 ETF포트폴리오AI`
- `AI-ETF-ROLE-ALLOCATION-V01` / `ETF역할배분AI`
- `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01` / `ETF비중템플릿AI`

현재 payload:

```text
D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json
```

현재 구조는 시장 모드, 역할 선택, 비중 템플릿 선택을 통해 E-series shadow portfolio를 만드는 1차 버전입니다.

## 확장 목표

E-series ETF 모델은 단순히 좋은 ETF를 고르는 모델이 아니라, 시장 국면에 따라 ETF 역할 포트폴리오의 비중을 조정하는 모델로 확장합니다.

목표:

- 수익률 개선
- 손실 위험 축소
- 시장 국면별 ETF 역할 분담 명확화
- 신규 ETF/신규 테마 편입 가능성 확보
- 주식 전략모델과 분리된 ETF 전용 source data/mart 구축

## 핵심 개념

ETF 모델은 아래 3단계로 판단합니다.

1. 시장 모드 판단
   - risk_on
   - neutral
   - risk_off

2. 역할 포트폴리오 점수화
   - CORE_BETA
   - SECTOR_THEME
   - STYLE_FACTOR
   - DEFENSIVE
   - INCOME
   - CASH_LIKE

3. 최종 ETF 포트폴리오 구성
   - 선택된 시장 모드에 맞춰 역할별 기본 비중 결정
   - 역할 내 ETF score로 종목 선택
   - liquidity/quality/risk gate 적용

## 시장 모드 설계

QuantMarket의 세부 시장국면과 변동성 국면은 그대로 보존하되, ETF 운영 판단에서는 3개 모드로 단순화합니다.

| ETF 운영 모드 | 의미 | 포트폴리오 방향 |
| --- | --- | --- |
| risk_on | 상승/위험자산 우호 | CORE_BETA, SECTOR_THEME, STYLE_FACTOR 확대 |
| neutral | 방향성 혼재 | CORE_BETA 중심, 방어/인컴 일부 혼합 |
| risk_off | 하락/변동성 확대 | DEFENSIVE, INCOME, CASH_LIKE 확대 |

세부 score는 버리지 않고 feature로 유지합니다.
최종 운영 판단만 3개 모드로 단순화합니다.

## 데이터 mart 확장

ETF 전용 mart는 주식 valuation mart와 분리합니다.

필수 데이터 그룹:

| 그룹 | 예시 feature |
| --- | --- |
| ETF 가격/수익률 | 1W/1M/3M/6M/12M return, volatility, MDD |
| 유동성 | AUM, 거래대금, 거래량, 스프레드 proxy |
| 추적 품질 | NAV 괴리율, 추적오차 proxy, premium/discount |
| 상품 구조 | 국내/해외, 환헤지, 레버리지/인버스, 액티브 여부 |
| 기초자산/역할 | equity, bond, commodity, sector, theme, factor |
| 시장 context | QuantMarket regime, volatility, risk, flow, theme context |
| 역할 sleeve | 6개 역할군별 후보 ETF score |

## label 설계

Top1/Top3/Top5 논란을 줄이기 위해 병행 관리합니다.

| label | 목적 |
| --- | --- |
| role_top1_win | 역할 선택의 최고 성과 예측 |
| role_top3_win | 현실적 후보군 안착 여부 |
| role_top5_win | 신규 ETF/신규 테마 포용성 |
| next_1m_risk_adjusted_win | 1개월 위험조정 성과 |
| downside_avoid | 큰 손실 회피 여부 |
| template_outperform_default | AI 비중 템플릿이 기본 템플릿을 이겼는지 |

운영 주 label은 `template_outperform_default`와 `next_1m_risk_adjusted_win`을 우선 사용하고, Top1/Top3/Top5는 보조 성능 지표로 둡니다.

## 모델 구조

### 1단계: ETF Market Mode AI

- 입력: 시장국면, 변동성, flow, risk, macro proxy
- 출력: risk_on / neutral / risk_off probability
- 목적: ETF 역할 비중의 상위 방향 결정
- E-series code: `AI-E-ETF-MARKET-MODE-V01`

### 2단계: ETF Role Allocation AI

- 입력: 시장 모드 + 역할별 ETF score + 시장 context
- 출력: 6개 역할군의 상대 매력도
- 목적: 이번 국면에 어떤 역할 ETF를 늘릴지 판단
- E-series code: `AI-E-ETF-ROLE-ALLOCATION-V01`

### 3단계: ETF Sleeve Selection AI

- 입력: 역할별 ETF feature
- 출력: 역할군 안에서 Top ETF 후보
- 목적: 신규 ETF/신규 테마가 들어와도 역할군 안에서 평가 가능하게 함
- E-series code: `AI-E-ETF-SLEEVE-SELECTION-V01`

### 4단계: ETF Weight Template AI

- 입력: 시장 모드, 역할 점수, risk score
- 출력: 비중 템플릿 선택 또는 역할별 weight
- 목적: 단순 종목 선택이 아니라 최종 포트폴리오 비중을 학습
- E-series code: `AI-E-ETF-ROLE-WEIGHT-TEMPLATE-V01`

### 5단계: ETF Portfolio AI

- 입력: 1~4단계 결과
- 출력: 최종 shadow portfolio
- 목적: 운영 가능한 ETF 포트폴리오 산출 및 live shadow tracking
- E-series code: `AI-E-ETF-PORTFOLIO-V01`

## 운영 단계

### Phase 1: mart 재정비

- ETF 전용 market context mart 생성
- ETF feature inventory 최신화
- 신규 ETF 포함 가능하도록 role taxonomy 정비

### Phase 2: label ablation 재실행

- Top1/Top3/Top5 병행
- horizon별 1M/2M/3M 분리
- risk-adjusted label과 downside label 비교

### Phase 3: 역할 sleeve 모델 개발

- 6개 역할 포트폴리오별 후보 ETF score 산출
- 역할 내 ETF selection score 개선
- liquidity/quality gate ablation

### Phase 4: 비중학습 고도화

- 기존 fixed template 유지
- AI 선택 template 비교
- 역할별 continuous weight 모델 실험
- tail-risk guard 적용

### Phase 5: shadow portfolio 운영화

- daily pipeline 갱신
- current payload 생성
- 4~8주 admin-only shadow tracking
- baseline ETF 전략 대비 성과 비교

## 검증 기준

- risk-adjusted return 개선
- MDD 악화 여부
- worst 1M return 축소 여부
- turnover 과도 여부
- 신규 ETF 편입 가능성
- 특정 역할군 쏠림 여부
- 시장 모드별 성과 일관성

## 다음 구현 순서

1. ETF mart schema 확장안 확정
2. role taxonomy와 신규 ETF mapping rule 정리
3. label ablation script 확장
4. sleeve selection score script 구현
5. weight learning backtest 구현
6. shadow portfolio current payload v2 생성
