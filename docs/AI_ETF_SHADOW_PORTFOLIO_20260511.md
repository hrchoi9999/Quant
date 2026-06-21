# E Series ETF AI Shadow Portfolio

## 목적

`E-ETF-V01`을 ETF 전용 E series 전략모델로 정의하고, 기본 설계 단계부터 AI 학습 구조를 내장해 admin-only shadow portfolio로 관찰한다.

## 구성

- strategy model: `E-ETF-V01` (ETF전용 E시리즈AI)
- AI portfolio model: `AI-E-ETF-PORTFOLIO-V01` (E시리즈 ETF포트폴리오AI)
- legacy alias: `AI-ETF-SHADOW-PORTFOLIO-V01`
- role model: `AI-ETF-ROLE-ALLOCATION-V01` (ETF역할배분AI), quality gate `no_watch_plus`
- template model: `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01` (ETF비중템플릿AI), quality gate `aum_p20`
- as-of: `2026-06-19`
- role signal date: `2026-06-19`
- template signal date: `2026-06-19`
- regime mode: `risk_off`
- selected role: `SECTOR_THEME`
- selected template: `ON_THEME_TILT`
- primary shadow variant: `hybrid_b50_ai50_top3_role`

## Backtest Summary

| variant | observations | avg 1M ret | win rate | avg MDD | avg risk adj | worst 1M | compounded |
|---|---:|---:|---:|---:|---:|---:|---:|
| `hybrid_b50_ai50_top3_role` | 29 | 2.65% | 62.07% | -2.99% | 1.16% | -7.50% | 103.73% |
| `role_ai_no_watch_plus_top1` | 28 | 4.97% | 60.71% | -5.32% | 2.31% | -35.13% | 179.44% |
| `template_ai_aum_p20_top1` | 28 | 3.86% | 57.14% | -3.43% | 2.15% | -15.42% | 150.43% |
| `mode_default_aum_p20` | 28 | 2.29% | 71.43% | -2.73% | 0.92% | -3.97% | 80.39% |

## 운영 판단

- 현재 단계는 admin-only shadow 관찰이다.
- public 추천/배분 반영은 최소 4~8주 live shadow 성과를 본 뒤 판단한다.
- `template_ai_aum_p20_top1`을 주 관찰 variant로 둔다.
- `role_ai_no_watch_plus_top1`은 역할 판단 보조 지표로 관찰한다.

## Outputs

- `D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_holdings_20260619.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_backtest_20260619.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_20260619.json`
