# E Series ETF AI Base Design

- 작성일: 2026-05-13
- 전략모델 코드: `E-ETF-V01`
- 한글명: `ETF전용 E시리즈AI`
- 현재 단계: admin-only shadow 설계/관찰

## 핵심 정의

`E-ETF-V01`은 ETF 전용 독립 전략모델입니다.

기존 S/T/I/C 주식 전략모델에 AI overlay를 붙이는 방식이 아니라, 모델의 기본 설계부터 AI 학습을 포함합니다.

## 개발 원칙

- ETF는 주식 valuation AI의 대상이 아닙니다.
- T-ETF는 기존 timing/운영 후보 모델로 유지합니다.
- E-series는 ETF 전용 포트폴리오 전략 모델로 별도 개발합니다.
- 소스 데이터는 ETF 가격, 유동성, AUM, NAV 괴리, 추적 품질, 상품구조, 역할군, QuantMarket 시장 context를 사용합니다.
- 결과는 우선 admin-only shadow portfolio로 관찰합니다.

## 모델 계층

| 계층 | 코드 | 역할 |
| --- | --- | --- |
| Strategy | `E-ETF-V01` | 최종 ETF 전략모델 |
| Market Mode AI | `AI-E-ETF-MARKET-MODE-V01` | risk_on / neutral / risk_off 판단 |
| Role Allocation AI | `AI-E-ETF-ROLE-ALLOCATION-V01` | 6개 ETF 역할군 매력도 판단 |
| Sleeve Selection AI | `AI-E-ETF-SLEEVE-SELECTION-V01` | 역할군 내부 ETF 후보 선택 |
| Weight Template AI | `AI-E-ETF-ROLE-WEIGHT-TEMPLATE-V01` | 역할군별 비중 템플릿 선택 |
| Portfolio AI | `AI-E-ETF-PORTFOLIO-V01` | 최종 shadow portfolio 생성 |

## 6개 ETF 역할군

| 역할군 | 의미 |
| --- | --- |
| CORE_BETA | 시장 대표지수/광범위 beta |
| SECTOR_THEME | 섹터/테마 ETF |
| STYLE_FACTOR | 배당, 가치, 성장, 퀄리티 등 factor ETF |
| DEFENSIVE | 저변동, 방어주, 채권성 방어 ETF |
| INCOME | 배당, 채권, 이자수익 중심 ETF |
| CASH_LIKE | 현금성, 초단기, 위험회피 대기 자산 |

현재 코드의 일부 role key는 기존 실험 호환을 위해 `DEFENSIVE_HEDGE`, `TACTICAL_HEDGE`, `TACTICAL_LEVERAGE`를 사용합니다.
다음 단계에서 E-series 표준 role taxonomy로 정리합니다.

## 1차 구현 범위

이번 단계에서는 기존 ETF AI shadow portfolio 산출물을 E-series 모델로 승격 정의했습니다.

- `model_code`: `E-ETF-V01`
- `strategy_family`: `E`
- `ai_portfolio_model_code`: `AI-E-ETF-PORTFOLIO-V01`
- legacy alias: `AI-ETF-SHADOW-PORTFOLIO-V01`

현재 payload:

```text
D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json
```

## 다음 구현 작업

1. E-series 표준 role taxonomy 정리
2. ETF 전용 mart v2 생성
3. Market Mode AI 분리 학습
4. Sleeve Selection AI 신규 구현
5. Weight Template AI 고도화
6. `E-ETF-V01` baseline vs AI portfolio shadow tracking 구축
