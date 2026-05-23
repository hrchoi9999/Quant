# E-Series ETF Primary Shadow Variant Update

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- AI 포트폴리오 모델: AI-E-ETF-PORTFOLIO-V01 / E시리즈 ETF포트폴리오AI
- 대표 shadow variant: `hybrid_b50_ai50_top3_role`

## 변경 내용

기존 ETF shadow portfolio current payload는 과거 실험용 role/template AI 결과를 병렬 제공하는 구조였다.
이번 변경으로 E-series sleeve portfolio backtest에서 가장 안정적인 개선을 보인 최신 `best_ai_policy`를 대표 variant로 지정하도록 변경했다.

2026-05-12 기준 대표 variant는 ETF 전용 feature 보강 후 `hybrid_b50_ai50_top3_role`이다.
해당 variant는 역할별 baseline selection score와 Sleeve Selection AI score를 50:50으로 결합한 뒤, 각 역할 sleeve에서 Top3 ETF를 선택하는 방식이다.

## Current Payload

- 파일: `D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json`
- `policy.primary_shadow_variant`: `hybrid_b50_ai50_top3_role`
- `policy.primary_shadow_source`: `AI-E-ETF-SLEEVE-SELECTION-V01 + E-series baseline score`
- `primary_sleeve_policy_summary`: 대표 hybrid 정책의 baseline 대비 성과 비교
- `current_holdings`: 대표 hybrid 보유 후보를 우선 포함

## 2026-05-12 Backtest Snapshot

| 항목 | Baseline | Hybrid 50/50 | 차이 |
|---|---:|---:|---:|
| 평균 1M 수익률 | 1.8874% | 2.1633% | +0.2759%p |
| 승률 | 60.7143% | 60.7143% | +0.0000%p |
| 평균 1M risk-adjusted | 0.3721% | 0.5993% | +0.2272%p |
| 누적 검증 수익률 | 63.1838% | 74.8877% | +11.7039%p |

## 운영 해석

현 단계는 public 추천 반영이 아니라 admin-only shadow tracking 단계다.
QS는 AI 학습 모델 페이지와 내부용 모델 페이지에서 E-ETF-V01의 대표 shadow portfolio를 `policy.primary_shadow_variant` 기준으로 표시하면 된다.
