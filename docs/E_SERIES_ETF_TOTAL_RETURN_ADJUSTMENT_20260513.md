# E-Series ETF Distribution / Total Return Adjustment

- 기준일: 2026-05-12
- 대상: E-ETF-V01 mart v2 및 ETF sleeve selection AI
- 목적: ETF 분배금이 있는 상품의 forward return label을 가격수익률이 아니라 총수익률 기준으로 보정

## 반영 내용

ETF mart 생성 단계에 총수익률 보정 구조를 추가했다.

- `fwd_ret_price_1w/2w/1m`: 가격 기준 forward return
- `fwd_ret_total_1w/2w/1m`: 분배금 반영 총수익률 forward return
- `distribution_sum_1w/2w/1m`: horizon 내 분배금 합계
- `total_return_adjustment_1w/2w/1m`: 분배금 보정분
- `total_return_source_1w/2w/1m`: `distribution_adjusted` 또는 `price_only`

향후 분배금 원천이 들어오면 기존 `fwd_ret_1w/2w/1m`은 자동으로 `fwd_ret_total_*` 기준으로 대체된다.

## 현재 진단 결과

현재 로컬 DB와 CSV에는 ETF 분배금 이벤트 원천이 없다.

| horizon | rows | adjusted rows | coverage | avg price ret | avg total ret | avg adjustment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1w | 8,837 | 0 | 0.00% | 0.19% | 0.19% | 0.00% |
| 2w | 8,837 | 0 | 0.00% | 0.95% | 0.95% | 0.00% |
| 1m | 8,837 | 0 | 0.00% | 1.32% | 1.32% | 0.00% |

따라서 현재 모델 성과 수치는 기존 가격수익률 기준과 동일하다.

## 운영 판단

이번 단계에서는 보정 구조와 진단 payload까지 준비 완료했다.

다음 단계는 QuantMarket 또는 별도 수집 루틴에서 ETF 분배금 이벤트 원천을 제공받는 것이다. 원천 형식은 아래 중 하나면 된다.

- SQLite table: `etf_distributions`, `etf_distribution_events`, `etf_dividends`, `etf_cash_distributions`
- CSV: `D:\Quant\data\etf_distributions.csv` 또는 `D:\Quant\data\universe\etf_distributions.csv`
- 필수 컬럼: `ticker`, 날짜 컬럼, 종목당 분배금 금액 컬럼

지원 날짜 컬럼명:

- `ex_date`, `distribution_date`, `base_date`, `record_date`, `pay_date`, `date`

지원 금액 컬럼명:

- `distribution_amount`, `distribution`, `cash_distribution`, `dividend_amount`, `dividend`, `dist_amount`, `amount`, `per_share_distribution`

## 산출물

- `D:\Quant\scripts\run_etf_ai_label_ablation.py`
- `D:\Quant\scripts\run_e_series_etf_total_return_adjustment_check.py`
- `D:\Quant\reports\e_series_etf\e_series_etf_total_return_adjustment_20260512.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_total_return_adjustment_current.json`

