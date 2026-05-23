# QS 작업요청서: E Series ETF AI 웹 반영

- 작성일: 2026-05-13
- 요청 주체: Quant thread
- 대상 thread: QuantService(QS)
- 관련 화면: admin `AI 학습 모델`
- 상태: admin-only shadow observation

## 요청 목적

ETF 전용 모델을 `E series`로 정식 정의했습니다.

QS admin `AI 학습 모델` 메뉴에서 기존 ETF shadow portfolio 표시를 아래 정식 모델명 기준으로 갱신해 주세요.

## 정식 모델 정의

| 항목 | 값 |
| --- | --- |
| strategy family | `E` |
| strategy model code | `E-ETF-V01` |
| 한글명 | `ETF전용 E시리즈AI` |
| AI portfolio model | `AI-E-ETF-PORTFOLIO-V01` |
| legacy alias | `AI-ETF-SHADOW-PORTFOLIO-V01` |
| 상태 | `shadow_observation` |
| public 추천 반영 | 금지 |

## Quant 제공 payload

```text
D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json
```

현재 payload는 `schema_version=1.1`이며 아래 필드를 포함합니다.

- `strategy_family`
- `strategy_model_code`
- `strategy_model_name_ko`
- `model_code`
- `model_name_ko`
- `ai_portfolio_model_code`
- `ai_portfolio_model_name_ko`
- `legacy_model_code`
- `learning_architecture`
- `component_models`
- `current_decision`
- `backtest_summary`
- `current_holdings`

## 화면 표시 요청

`AI 학습 모델` 메뉴에서 `ETF전용 E시리즈AI` 항목을 표시해 주세요.

표시 우선순위:

1. 모델 개요
   - `strategy_model_code`
   - `strategy_model_name_ko`
   - `status`
   - `policy.operating_stage`
   - `policy.public_recommendation_use`

2. 학습 구조
   - `learning_architecture.stages`
   - ETF시장모드AI
   - ETF역할배분AI
   - ETF비중템플릿AI
   - E시리즈 ETF포트폴리오AI

3. 현재 판단
   - `current_decision.regime_mode`
   - `current_decision.selected_role`
   - `current_decision.selected_role_prob`
   - `current_decision.selected_template`
   - `current_decision.selected_template_prob`
   - `current_decision.mode_default_template`

4. 백테스트 요약
   - `backtest_summary`
   - 기본 관찰 variant: `template_ai_aum_p20_top1`

5. 현재 ETF 구성
   - `current_holdings`
   - `variant=template_ai_aum_p20_top1` 우선 표시

## 사용자 안내 문구

아래 문구를 화면에 짧게 표시해 주세요.

```text
E-ETF-V01은 ETF 전용 E series 전략모델입니다. 주식 전략모델의 AI overlay가 아니라, ETF 전용 데이터와 시장국면/역할배분/비중학습을 처음부터 포함해 설계한 독립 shadow 모델입니다.
```

## N/A 처리

- null, NaN, 빈 값은 `0%`가 아니라 `N/A`로 표시해 주세요.
- 확률 값은 `%` 표시 가능하나, 원본 값이 null이면 `N/A`입니다.

## 운영 원칙

- admin-only shadow 관찰용입니다.
- public 추천/배분에는 아직 반영하지 않습니다.
- 최소 4~8주 live shadow tracking 후 운영 반영 여부를 판단합니다.
- Quant thread는 QS 코드를 직접 수정하지 않고 payload만 제공합니다.

## 검증 요청

- `AI 학습 모델` 목록에 `ETF전용 E시리즈AI`가 표시되는지 확인
- 기존 `ETF전용포트폴리오AI` 명칭이 남아 혼동되지 않는지 확인
- legacy alias는 상세 정보 정도로만 표시되는지 확인
- public 화면에는 노출되지 않는지 확인
