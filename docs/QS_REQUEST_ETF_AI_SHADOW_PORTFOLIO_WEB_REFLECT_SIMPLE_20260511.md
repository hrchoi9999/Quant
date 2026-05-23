# QS 작업요청: ETF전용포트폴리오AI 웹 반영

QS admin `AI 학습 모델` 메뉴에 Quant에서 생성한 ETF 전용 AI shadow portfolio를 반영해 주세요.

## 반영 대상

- model_code: `AI-ETF-SHADOW-PORTFOLIO-V01`
- 한글명: `ETF전용포트폴리오AI`
- 상태: `shadow_observation`
- 용도: admin-only shadow 관찰
- public 추천 반영: 금지

## Quant 제공 payload

```text
D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json
D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json
```

## 웹 표시 요청

`AI 학습 모델` 메뉴에서 아래 정보를 표시해 주세요.

1. 현재 판단
   - 시장 모드: `current_decision.regime_mode`
   - 선택 역할: `current_decision.selected_role`
   - 선택 템플릿: `current_decision.selected_template`
   - 기본 템플릿: `current_decision.mode_default_template`

2. 백테스트 요약
   - `backtest_summary`
   - 기본 관찰 variant: `template_ai_aum_p20_top1`

3. 현재 ETF 구성
   - `current_holdings`
   - 기본 표시 variant: `template_ai_aum_p20_top1`

4. 하위 모델 정보
   - `component_models`
   - `AI-ETF-ROLE-ALLOCATION-V01`
   - `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01`

## 운영 원칙

- 이 모델은 아직 실전 추천 모델이 아닙니다.
- admin 화면에서만 shadow tracking 용도로 표시해 주세요.
- public 화면이나 실제 추천/배분에는 반영하지 말아 주세요.
- 최소 4~8주 live shadow 성과를 본 뒤 운영 반영 여부를 판단합니다.

## 검증 요청

- `AI 학습 모델` 목록에 `ETF전용포트폴리오AI`가 보이는지 확인
- 상세 화면에서 current decision, backtest summary, holdings가 보이는지 확인
- null 값이 `0%`로 표시되지 않고 `N/A` 또는 빈 값으로 표시되는지 확인
- public 추천 화면에는 노출되지 않는지 확인

