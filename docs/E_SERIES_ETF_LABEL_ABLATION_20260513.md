# E Series ETF Label Ablation

- 작성일: 2026-05-13
- 전략모델: `E-ETF-V01`
- 기준일: 2026-05-12
- mart: `D:\Quant\reports\e_series_etf\e_series_etf_mart_v2_20260512.csv`

## 목적

`E-ETF-V01`의 AI 학습 target을 정하기 위해 mart v2 기준 label ablation을 실행했습니다.

E-series는 baseline ETF 전략에 AI를 사후 부착하는 구조가 아니라, baseline rule score와 AI 학습층을 처음부터 함께 관리합니다.
이번 ablation은 그중 어떤 label이 sleeve selection / portfolio selection에 적합한지 확인하는 작업입니다.

## 실행 스크립트

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_e_series_etf_label_ablation.py --asof 2026-05-12
```

## 산출물

```text
D:\Quant\reports\e_series_etf\e_series_etf_label_ablation_20260512.csv
D:\Quant\reports\e_series_etf\e_series_etf_label_ablation_20260512.json
D:\Quant\reports\e_series_etf\e_series_etf_label_ablation_20260512.md
```

## 주요 결과

| label | feature mode | AUC | top3 hit | top3 risk adj | 해석 |
| --- | --- | ---: | ---: | ---: | --- |
| `e_label_overall_top5_1m_risk_adj` | `E_MARKET` | 0.691 | 4.94% | -1.93% | AUC는 높지만 실제 top pick 품질은 부진 |
| `e_label_role_top1_1m_risk_adj` | `E_BASELINE` | 0.690 | 16.05% | -0.44% | Top1 label은 희소하지만 판별력 있음 |
| `e_label_role_top3_1m_risk_adj` | `E_BASELINE` | 0.679 | 54.32% | 1.80% | 현재 가장 운영성이 좋은 label |
| `e_label_role_top3_1m_risk_adj` | `E_MARKET` | 0.675 | 46.91% | 0.67% | 시장 context 추가 시 AUC는 유사하나 top3 성과 약화 |

## 1차 판단

운영 target은 `e_label_role_top3_1m_risk_adj` + `E_BASELINE` 조합이 가장 적합합니다.

이유:

- AUC가 0.679로 충분히 의미 있음
- top1 hit 59.26%, top3 hit 54.32%
- top3 평균 1M risk-adjusted return이 1.80%로 양호
- 전체 ETF Top5 label은 AUC는 높지만 실제 top pick 성과가 약해 운영 target으로는 부적합

## 다음 단계

1. `e_label_role_top3_1m_risk_adj` 기준 Sleeve Selection AI v1 학습
2. 역할군별 성능 분해
3. `E_BASELINE`과 `E_MARKET`의 혼합 feature 재실험
4. E-series baseline vs AI sleeve selection backtest
