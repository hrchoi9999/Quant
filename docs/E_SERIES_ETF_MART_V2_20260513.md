# E Series ETF Mart V2

- 작성일: 2026-05-13
- 전략모델: `E-ETF-V01`
- 기준일: 2026-05-12
- 상태: 생성 완료

## 설계 방향

`E-ETF-V01`은 ETF 기본 데이터로 baseline 전략을 먼저 만들고 사후에 AI를 붙이는 방식이 아닙니다.

운영 비교를 위해 baseline rule score는 유지하지만, 설계 단계부터 아래 학습층을 함께 포함합니다.

- ETF 시장 모드
- ETF 역할군
- 역할별 baseline score
- ETF quality/liquidity/tracking score
- AI 학습 label

따라서 mart v2는 baseline 전략과 AI 학습을 동시에 지원하는 공통 학습 mart입니다.

## 생성 스크립트

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_e_series_etf_mart_v2.py --asof 2026-05-12
```

## 산출물

```text
D:\Quant\reports\e_series_etf\e_series_etf_mart_v2_20260512.csv
D:\Quant\reports\e_series_etf\e_series_etf_mart_v2_current_sample_20260512.csv
D:\Quant\reports\e_series_etf\e_series_etf_mart_v2_20260512.json
```

## 생성 결과

- rows: 8,837
- tickers: 451
- signal dates: 113
- columns: 190

## 추가된 핵심 필드

| field | 의미 |
| --- | --- |
| `strategy_family` | `E` |
| `strategy_model_code` | `E-ETF-V01` |
| `e_series_role` | E-series 표준 6개 ETF 역할군 |
| `e_market_mode` | risk_on / neutral / risk_off |
| `e_mode_role_weight` | 시장모드별 역할군 기본 비중 |
| `e_quality_score` | 유동성/AUM/추적품질/역할신뢰도 기반 품질 점수 |
| `e_momentum_score` | 20D/60D/120D/240D momentum rank |
| `e_risk_control_score` | 변동성/MDD 기반 방어 점수 |
| `e_baseline_selection_score` | baseline ETF selection score |
| `e_baseline_rank_in_role` | 역할군 내부 baseline rank |
| `e_baseline_rank_overall` | 전체 ETF baseline rank |

## AI 학습 label

| label | 의미 |
| --- | --- |
| `e_label_1m_positive` | 1개월 forward return 양수 여부 |
| `e_label_1m_drawdown_safe` | 1개월 수익률 양수 및 MDD -5% 이상 |
| `e_label_role_top1_1m_risk_adj` | 역할군 내 1개월 risk-adjusted 1위 |
| `e_label_role_top3_1m_risk_adj` | 역할군 내 1개월 risk-adjusted Top3 |
| `e_label_role_top20pct_1m_risk_adj` | 역할군 내 상위 20% |
| `e_label_overall_top5_1m_risk_adj` | 전체 ETF 중 Top5 |
| `e_label_overall_top10pct_1m_risk_adj` | 전체 ETF 중 상위 10% |

## 다음 단계

1. mart v2 기준 label ablation
2. Market Mode AI 분리 학습
3. Sleeve Selection AI 학습
4. Weight Template AI v2 학습
5. `E-ETF-V01` baseline vs AI portfolio shadow backtest
