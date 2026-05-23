# E Series ETF Sleeve Selection AI V1

- 작성일: 2026-05-13
- 전략모델: `E-ETF-V01`
- AI model: `AI-E-ETF-SLEEVE-SELECTION-V01`
- 한글명: `E시리즈 ETF슬리브선택AI`
- 기준일: 2026-05-12

## 목적

`E-ETF-V01`의 6개 ETF 역할군 안에서 어떤 ETF가 다음 1개월 risk-adjusted 성과 상위권에 들 가능성이 높은지 학습합니다.

이 모델은 E-series 내부의 sleeve selection layer입니다.
주식 전략모델의 AI overlay가 아니라 ETF 전용 전략모델의 기본 학습층입니다.

## 학습 설정

| 항목 | 값 |
| --- | --- |
| target label | `e_label_role_top3_1m_risk_adj` |
| feature mode | `E_BASELINE` |
| train end | 2023-12-31 |
| valid start | 2024-01-01 |
| valid end | 2026-05-12 |
| model | GradientBoostingClassifier |

## 검증 결과

- AUC: 0.671
- top1 label rate: 55.56%
- top3 label rate: 51.85%
- top3 avg 1M risk-adjusted return: 1.55%
- top3 avg 1M forward return: 3.83%

## 산출물

```text
D:\Quant\data\models\e_series_etf_sleeve_selection_ai\AI-E-ETF-SLEEVE-SELECTION-V01_20260512_001.joblib
D:\Quant\data\models\e_series_etf_sleeve_selection_ai\AI-E-ETF-SLEEVE-SELECTION-V01_20260512_001_metadata.json
D:\Quant\reports\e_series_etf\e_series_etf_sleeve_selection_current_scores_20260512.csv
D:\Quant\reports\e_series_etf\e_series_etf_sleeve_selection_valid_scored_20260512.csv
D:\Quant\reports\e_series_etf\e_series_etf_sleeve_selection_role_perf_20260512.csv
D:\Quant\service_platform\web\admin_data\current\e_series_etf_sleeve_selection_current.json
```

## 1차 판단

모델은 완성됐고 E-series pipeline에 연결했습니다.

다음 단계는 이 sleeve selection score를 기존 `E-ETF-V01` shadow portfolio 생성 로직에 연결해, baseline ETF portfolio와 AI sleeve portfolio의 백테스트 차이를 비교하는 것입니다.
