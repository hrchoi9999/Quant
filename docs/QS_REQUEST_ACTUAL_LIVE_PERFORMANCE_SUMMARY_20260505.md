# QS 작업 요청: 실제 운영 이후 성과 요약 표시 반영

## 작업명
admin 신규 편입 추적 실제 운영 성과 요약 표시 반영

## 요청 출처
Quant 모델 쓰레드

## 배경
`admin_new_entry_tracker.json`에는 기존부터 신규 편입/재편입/비중증가 이벤트별 실제 가격 기반 `current_return`, `forward_returns.1w/2w/1m/2m/3m/6m/1y`가 포함되어 있다.

다만 내부 모델과 T-series 이벤트에는 과거 재구성 히스토리가 함께 포함되어 있어, 웹에서 이를 그대로 집계하면 “실제 운영 시작 이후 성과”와 “백테스트/재구성 결과”가 섞이는 문제가 있었다.

Quant 쪽에서 백테스트 성과와 분리된 실제 운영 성과 전용 블록을 추가했다.

## 반영된 Quant payload
- 파일: `admin/current/admin_new_entry_tracker.json`
- 로컬 기준: `D:\Quant\service_platform\web\admin_data\current\admin_new_entry_tracker.json`
- 신규 top-level block: `actual_live_performance_summary`
- 기준일 테스트: `2026-05-04`
- 생성/검증 결과: `validate_admin_new_entry_tracker.py --mode quick/full` 모두 통과

## 신규 payload shape
```json
{
  "actual_live_performance_summary": {
    "metric_basis": "actual_market_price_forward_return_since_live_start",
    "description": "...",
    "horizons": ["current_return", "1w", "2w", "1m", "2m", "3m", "6m", "1y"],
    "user_models": [],
    "internal_models": [],
    "tseries_models": []
  }
}
```

각 모델 row:
```json
{
  "service_profile 또는 model_code": "...",
  "live_start_date": "YYYY-MM-DD",
  "source_event_count": 1808,
  "live_event_count": 26,
  "latest_live_event_date": "YYYY-MM-DD",
  "metric_basis": "actual_market_price_forward_return_since_live_start",
  "metrics": {
    "1w": {
      "sample_count": 26,
      "avg_return": 0.029765,
      "median_return": -0.001604,
      "win_rate": 0.5,
      "mdd_sample_count": 26,
      "avg_mdd": -0.03421,
      "median_mdd": -0.0215,
      "sharpe_sample_count": 26,
      "avg_sharpe": 1.24,
      "median_sharpe": 0.82
    }
  }
}
```

## QS 반영 요청
1. admin `신규 편입 종목` 또는 별도 성과 카드에서 실제 운영 성과는 `actual_live_performance_summary`를 우선 사용해 주세요.
2. 기존 `model_performance_summary`는 백테스트/프록시 성과로 유지하고, 실제 운영 성과와 시각적으로 분리해 주세요.
3. `sample_count = 0`인 기간의 `avg_return`, `median_return`, `win_rate`는 `null`로 제공되므로 웹에서는 `N/A`로 표시해 주세요.
4. 표시 기간은 아래를 지원해 주세요.
   - 현재까지: `current_return`
   - `1W`, `2W`, `1M`, `2M`, `3M`, `6M`, `1Y`
5. 문구는 아래 기준으로 분리해 주세요.
   - 백테스트 성과: `모델 규칙을 과거 데이터에 적용한 검증 결과`
   - 실제 운영 성과: `운영 시작 이후 모델 편입 종목의 실제 시장가격 추적 결과`

## 모델별 live_start_date
- `stable / balanced / growth`: `2026-03-18`
- `S2 / S3 / S3_CORE2`: `2026-03-12`
- `S4 / S5 / S6`: `2026-03-17`
- `S2_PIT_V01 / S3_ACCEL_V01`: `2026-04-23`
- `T-STOCK-V01 / T-ETF-V01`: `2026-04-01`
- `I-STOCK-STRONG-RSI-V01`: `2026-04-29`

## 검증 예시
- `S3`
  - source_event_count: `1808`
  - live_event_count: `26`
  - 의미: 2017년 이후 재구성 이벤트는 실제 운영 성과 집계에서 제외됨
- 사용자용 모델
  - `1W`, `2W`는 값 존재
  - `1M/2M/3M/6M/1Y`는 표본이 아직 없으면 `N/A`

## MDD/Sharpe 기준

- `actual_live_performance_summary`는 운영 시작 이후 이벤트 row의 실제 forward return과 가격 경로 기반 risk metric을 함께 제공한다.
- 각 horizon별로 `mdd_sample_count`, `avg_mdd`, `median_mdd`, `sharpe_sample_count`, `avg_sharpe`, `median_sharpe`를 제공한다.
- `MDD/Sharpe`는 편입일 이후 해당 horizon 종료일까지의 종목별 실제 가격 경로에서 산출한 뒤 모델별 평균/중앙값으로 집계한다.
- `MDD/Sharpe`는 현재 `model_performance_summary`의 모델 NAV 기반 요약 지표(`mdd_1y`, `sharpe_1y`)로 제공된다.
- 두 값은 계산 기준이 다르므로 QS에서는 `실제 운영 이벤트 기준`과 `모델 NAV 기준`을 구분해서 표시한다.

## 완료 기준
1. 웹에서 백테스트 성과와 실제 운영 성과가 섞이지 않음
2. 실제 운영 성과는 `actual_live_performance_summary` 기준으로 표시됨
3. `null` 값은 `0%`가 아니라 `N/A`로 표시됨
4. admin 화면에서 모델별 live event count와 기간별 성과를 확인할 수 있음
