# E Series ETF AI Shadow Portfolio

## 목적

`E-ETF-V01`을 ETF 전용 E series 전략모델로 정의하고, 기본 설계 단계부터 AI 학습 구조를 내장해 admin-only shadow portfolio로 관찰한다.

## 구성

- strategy model: `E-ETF-V01` (ETF전용 E시리즈AI)
- AI portfolio model: `AI-E-ETF-PORTFOLIO-V01` (E시리즈 ETF포트폴리오AI)
- legacy alias: `AI-ETF-SHADOW-PORTFOLIO-V01`
- role model: `AI-ETF-ROLE-ALLOCATION-V01` (ETF역할배분AI), quality gate `no_watch_plus`
- template model: `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01` (ETF비중템플릿AI), quality gate `aum_p20`
- as-of: `2026-05-21`
- role signal date: `2026-05-21`
- template signal date: `2026-05-21`
- regime mode: `risk_off`
- selected role: `SECTOR_THEME`
- selected template: `ON_THEME_TILT`
- primary shadow variant: `hybrid_b50_ai50_top3_role`

## Backtest Summary

| variant | observations | avg 1M ret | win rate | avg MDD | avg risk adj | worst 1M | compounded |
|---|---:|---:|---:|---:|---:|---:|---:|
| `hybrid_b50_ai50_top3_role` | 28 | 2.19% | 60.71% | -3.13% | 0.63% | -7.50% | 76.32% |
| `role_ai_no_watch_plus_top1` | 27 | 4.28% | 62.96% | -4.78% | 1.89% | -35.13% | 144.60% |
| `template_ai_aum_p20_top1` | 27 | 3.06% | 55.56% | -3.51% | 1.30% | -15.42% | 99.27% |
| `mode_default_aum_p20` | 27 | 2.28% | 70.37% | -2.64% | 0.96% | -3.97% | 75.97% |

## 운영 판단

- 현재 단계는 admin-only shadow 관찰이다.
- public 추천/배분 반영은 최소 4~8주 live shadow 성과를 본 뒤 판단한다.
- `template_ai_aum_p20_top1`을 주 관찰 variant로 둔다.
- `role_ai_no_watch_plus_top1`은 역할 판단 보조 지표로 관찰한다.

## Outputs

- `D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_holdings_20260521.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_backtest_20260521.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_20260521.json`
