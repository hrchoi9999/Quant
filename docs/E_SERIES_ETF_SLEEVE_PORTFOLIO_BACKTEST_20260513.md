# E Series ETF Sleeve Portfolio Backtest

- 작성일: 2026-05-13
- 전략모델: `E-ETF-V01`
- Sleeve AI: `AI-E-ETF-SLEEVE-SELECTION-V01`
- 기준일: 2026-05-12

## 목적

`E-ETF-V01`의 baseline ETF selection score와 Sleeve Selection AI score를 실제 포트폴리오 구성에 적용해 비교했습니다.

비교 기준은 동일합니다.

- 같은 ETF universe
- 같은 6개 역할군
- 같은 시장모드별 역할 비중
- 역할군별 ETF 선택 score만 다르게 적용

## 비교 정책

| policy | 설명 |
| --- | --- |
| `baseline_top3_role` | baseline rule score로 역할군별 Top3 선택 |
| `ai_top1_role` | Sleeve AI score로 역할군별 Top1 선택 |
| `ai_top3_role` | Sleeve AI score로 역할군별 Top3 선택 |
| `ai_top5_role` | Sleeve AI score로 역할군별 Top5 선택 |
| `hybrid_b70_ai30_top3_role` | baseline 70% + AI 30% score로 역할군별 Top3 선택 |
| `hybrid_b50_ai50_top3_role` | baseline 50% + AI 50% score로 역할군별 Top3 선택 |
| `ai_quality_guard_top3_role` | AI score + quality/risk guard로 역할군별 Top3 선택 |

## 주요 결과

| policy | avg 1M ret | win rate | avg 1M risk adj | MDD proxy | compounded |
| --- | ---: | ---: | ---: | ---: | ---: |
| `hybrid_b50_ai50_top3_role` | 2.13% | 67.86% | 0.78% | -2.71% | 74.04% |
| `baseline_top3_role` | 2.07% | 57.14% | 0.73% | -2.68% | 71.53% |
| `hybrid_b70_ai30_top3_role` | 2.04% | 64.29% | 0.67% | -2.74% | 70.19% |
| `ai_top1_role` | 1.89% | 67.86% | 0.11% | -3.56% | 65.77% |
| `ai_top3_role` | 1.69% | 60.71% | -0.07% | -3.53% | 56.60% |

## 판단

AI 단독 선택은 아직 baseline을 이기지 못했습니다.

다만 `hybrid_b50_ai50_top3_role`은 baseline 대비 아래 개선을 보였습니다.

- avg 1M return: +0.06%p
- win rate: +10.71%p
- avg 1M risk-adjusted return: +0.05%p
- compounded validation return: +2.51%p

따라서 현재 1차 후보는 `baseline 50% + AI 50% hybrid Top3`입니다.

## 산출물

```text
D:\Quant\reports\e_series_etf\e_series_etf_sleeve_portfolio_summary_20260512.csv
D:\Quant\reports\e_series_etf\e_series_etf_sleeve_portfolio_current_holdings_20260512.csv
D:\Quant\reports\e_series_etf\e_series_etf_sleeve_portfolio_backtest_20260512.json
D:\Quant\service_platform\web\admin_data\current\e_series_etf_sleeve_portfolio_current.json
```

## 다음 단계

1. hybrid score를 `E-ETF-V01` shadow portfolio 생성 로직의 primary candidate로 연결
2. 역할군별 부진 영역인 `DEFENSIVE`, `CASH_LIKE`, `INCOME` label/feature 보강
3. 1M 외 2M/3M horizon label 실험
4. turnover 및 중복 ETF concentration guard 추가
