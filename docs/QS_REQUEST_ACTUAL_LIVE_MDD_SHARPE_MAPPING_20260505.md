# QS 작업 요청: 모델별 실제 운영 성과 테이블 MDD/Sharpe 매핑 반영

## 작업명
admin 신규 편입 종목: 모델별 실제 운영 성과 테이블 MDD/Sharpe 표시 반영

## 요청 출처
Quant 모델 쓰레드

## 배경
Quant canonical admin current payload에는 `actual_live_performance_summary` 블록이 포함되어 있으며, 모델별 실제 운영 성과의 기간별 수익률뿐 아니라 MDD/Sharpe도 산출되어 있다.

QS 확인 과정에서 `1M MDD`, `1M SHARPE` 값이 보이지 않는다는 이슈가 있었으나, Quant 측에서 운영 GCS object를 직접 확인한 결과 해당 값은 payload에 존재한다.

따라서 이번 요청은 Quant 계산 추가 요청이 아니라, QS 화면 테이블에서 실제 payload 경로를 정확히 매핑해 표시하는 작업이다.

## 운영 payload
- URL:
  - `https://storage.googleapis.com/quantservice-489808-market-analysis/admin/current/admin_new_entry_tracker.json`
- 기준 확인값:
  - `as_of_date = 2026-05-04`
  - `generated_at = 2026-05-05T20:47:25`
- top-level block:
  - `actual_live_performance_summary`

## 표시 대상 화면
- admin `신규 편입 종목`
- `모델별 실제 운영 성과` 테이블

## 매핑 대상 scope
아래 3개 scope 모두 동일한 구조로 처리 요청.

- `actual_live_performance_summary.user_models[]`
- `actual_live_performance_summary.internal_models[]`
- `actual_live_performance_summary.tseries_models[]`

모델 식별 필드:
- user scope:
  - `service_profile`
- internal/tseries scope:
  - `model_code`

## 기간 horizon
현재 Quant payload의 horizons:

```json
[
  "current_return",
  "1w",
  "2w",
  "1m",
  "2m",
  "3m",
  "6m",
  "1y"
]
```

QS 테이블에서는 아래 기간을 표시 가능하도록 매핑 요청.

- 현재까지: `current_return`
- `1W`: `1w`
- `2W`: `2w`
- `1M`: `1m`
- `2M`: `2m`
- `3M`: `3m`
- `6M`: `6m`
- `1Y`: `1y`

## 필드 매핑
각 모델 row의 기간별 값은 아래 경로에서 읽는다.

```text
actual_live_performance_summary.{scope}[].metrics.{horizon}.sample_count
actual_live_performance_summary.{scope}[].metrics.{horizon}.avg_return
actual_live_performance_summary.{scope}[].metrics.{horizon}.median_return
actual_live_performance_summary.{scope}[].metrics.{horizon}.win_rate
actual_live_performance_summary.{scope}[].metrics.{horizon}.mdd_sample_count
actual_live_performance_summary.{scope}[].metrics.{horizon}.avg_mdd
actual_live_performance_summary.{scope}[].metrics.{horizon}.median_mdd
actual_live_performance_summary.{scope}[].metrics.{horizon}.sharpe_sample_count
actual_live_performance_summary.{scope}[].metrics.{horizon}.avg_sharpe
actual_live_performance_summary.{scope}[].metrics.{horizon}.median_sharpe
```

예: `1M MDD`, `1M Sharpe`

```text
actual_live_performance_summary.internal_models[]
  .metrics["1m"].avg_mdd

actual_live_performance_summary.internal_models[]
  .metrics["1m"].avg_sharpe
```

주의:
- `1m_mdd`, `mdd_1m`, `sharpe_1m` 같은 평면 필드는 제공하지 않는다.
- 반드시 `metrics["1m"].avg_mdd`, `metrics["1m"].avg_sharpe` 경로를 사용한다.

## 표시 권장 컬럼
모델별 실제 운영 성과 테이블에서 기간 선택 또는 기간별 컬럼에 아래 값 표시 요청.

- 표본수:
  - `sample_count`
- 평균수익률:
  - `avg_return`
- 중앙수익률:
  - `median_return`
- 승률:
  - `win_rate`
- 평균 MDD:
  - `avg_mdd`
- 중앙 MDD:
  - `median_mdd`
- 평균 Sharpe:
  - `avg_sharpe`
- 중앙 Sharpe:
  - `median_sharpe`

## null / N/A 처리
아래 경우 QS에서는 `0` 또는 `0%`로 표시하지 말고 `N/A`로 표시 요청.

- `sample_count = 0`
- `avg_return = null`
- `avg_mdd = null`
- `avg_sharpe = null`

특히 `2M/3M/6M/1Y`는 아직 운영 기간이 짧아 대부분 `sample_count = 0`일 수 있다.

## Quant 확인 예시
운영 payload 기준 `1M` 값 예시:

| scope | model | 1M sample_count | 1M avg_mdd | 1M avg_sharpe |
|---|---:|---:|---:|---:|
| user_models | stable | 16 | -0.051393 | 5.716243 |
| user_models | balanced | 16 | -0.051393 | 5.716243 |
| user_models | growth | 23 | -0.134433 | 1.742872 |
| internal_models | S2 | 20 | -0.139411 | 2.665317 |
| internal_models | S3 | 4 | -0.168788 | 0.121098 |
| internal_models | S3_CORE2 | 3 | -0.292204 | -0.611266 |
| internal_models | S4 | 1 | -0.049089 | 8.572861 |
| internal_models | S5 | 4 | -0.039530 | 6.365215 |
| internal_models | S6 | 2 | -0.135567 | -3.894138 |

위 값은 QS 표시 시 percent 변환 기준:

- `avg_mdd = -0.051393` → `-5.14%`
- `avg_return = 0.267127` → `26.71%`
- `avg_sharpe = 5.716243` → `5.72`

## 계산 기준 안내 문구
화면 또는 tooltip에 아래 취지의 설명을 권장.

```text
실제 운영 성과는 모델 운영 시작일 이후 신규 편입/재편입/비중 증가 이벤트를 대상으로 실제 시장가격을 추적한 결과입니다.
MDD와 Sharpe는 각 이벤트의 편입일 이후 해당 기간 종료일까지의 가격 경로를 기준으로 계산한 뒤 모델별로 집계합니다.
백테스트 NAV 성과와는 계산 기준이 다릅니다.
```

## 완료 기준
1. 모델별 실제 운영 성과 테이블에서 `1M MDD`, `1M Sharpe`가 표시된다.
2. 표시 값은 `metrics["1m"].avg_mdd`, `metrics["1m"].avg_sharpe` 기준이다.
3. `2M` horizon도 테이블/필터에 표시 가능하되, 표본이 없으면 `N/A`로 표시한다.
4. `null` 값을 `0%` 또는 `0.00`으로 오표시하지 않는다.
5. 백테스트 성과와 실제 운영 성과의 MDD/Sharpe를 혼용하지 않는다.

