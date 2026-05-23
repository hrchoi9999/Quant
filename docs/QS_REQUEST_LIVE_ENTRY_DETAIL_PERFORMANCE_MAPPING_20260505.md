# QS 작업 요청: 신규 편입 종목 종목별 실제 운영 성과 매핑 반영

## 작업명
admin 신규 편입 종목: `편입 후 추적 성과` 및 `주간 순위 히스토리` 종목별 실제 운영 성과 표시 반영

## 요청 출처
Quant 모델 쓰레드

## 배경
현재 admin `신규 편입 종목` 페이지에는 `모델별 실제 운영 성과` 블록이 있으며, 이 블록은 Quant payload의 `actual_live_performance_summary`를 기준으로 표시된다.

사용자가 보고자 하는 핵심은 백테스트가 아니라 “모델 운영 시작 이후 실제로 선정된 종목들이 편입 후 시장에서 어떻게 움직였는지”이다.

따라서 같은 기준을 아래 종목별 블록에도 적용해 달라는 요청이다.

- `편입 후 추적 성과`
- `주간 순위 히스토리`

## 핵심 원칙
아래 블록들은 모두 “실제 운영 이후 성과” 기준으로 표시한다.

- `모델별 실제 운영 성과`
- `편입 후 추적 성과`
- `주간 순위 히스토리`

즉, 과거 2017년 이후 재구성/백테스트 이벤트를 실제 운영 성과처럼 표시하면 안 된다.

## 운영 payload
- URL:
  - `https://storage.googleapis.com/quantservice-489808-market-analysis/admin/current/admin_new_entry_tracker.json`
- 기준 확인값:
  - `as_of_date = 2026-05-04`
  - `generated_at = 2026-05-05T20:47:25`

## live_start_date 기준
모델별 실제 운영 성과로 표시할 row는 반드시 아래 조건을 만족해야 한다.

```text
event_date >= live_start_date
```

live_start_date는 `actual_live_performance_summary`의 모델 row에서 읽는 것을 권장한다.

예:

```text
actual_live_performance_summary.user_models[].live_start_date
actual_live_performance_summary.internal_models[].live_start_date
actual_live_performance_summary.tseries_models[].live_start_date
```

모델 식별:

- user scope:
  - `service_profile`
- internal/tseries scope:
  - `model_code`

## 대상 event row
종목별 상세 성과는 아래 event row에서 읽는다.

- `user_models[]`
- `internal_models[]`
- `tseries_models[]`

단, 실제 운영 성과 화면에서는 모델별 `live_start_date` 이전 row는 제외한다.

## 편입 후 추적 성과 블록 매핑
`편입 후 추적 성과` 블록에서는 종목별 event row의 아래 필드를 사용한다.

### 기본 식별 필드

```text
scope
service_profile 또는 model_code
event_type
event_date
week_end
security_code
display_name
rank_no
score
score_basis
weight
candidate_bucket
```

### 종목별 기간 수익률

```text
forward_returns["1w"]
forward_returns["2w"]
forward_returns["1m"]
forward_returns["2m"]
forward_returns["3m"]
forward_returns["6m"]
forward_returns["1y"]
current_return
```

표시명 권장:

- `1W`
- `2W`
- `1M`
- `2M`
- `3M`
- `6M`
- `1Y`
- `현재까지`

### 종목별 MDD / Sharpe

```text
forward_risk_metrics["1w"].mdd
forward_risk_metrics["1w"].sharpe
forward_risk_metrics["2w"].mdd
forward_risk_metrics["2w"].sharpe
forward_risk_metrics["1m"].mdd
forward_risk_metrics["1m"].sharpe
forward_risk_metrics["2m"].mdd
forward_risk_metrics["2m"].sharpe
forward_risk_metrics["3m"].mdd
forward_risk_metrics["3m"].sharpe
forward_risk_metrics["6m"].mdd
forward_risk_metrics["6m"].sharpe
forward_risk_metrics["1y"].mdd
forward_risk_metrics["1y"].sharpe
current_risk_metrics.mdd
current_risk_metrics.sharpe
```

특히 `1M MDD`, `1M Sharpe`는 아래 경로를 사용한다.

```text
event_row.forward_risk_metrics["1m"].mdd
event_row.forward_risk_metrics["1m"].sharpe
```

주의:

- `1m_mdd`, `mdd_1m`, `sharpe_1m` 같은 평면 필드는 제공하지 않는다.
- 반드시 `forward_risk_metrics["1m"].mdd`, `forward_risk_metrics["1m"].sharpe` 경로를 사용한다.

## 주간 순위 히스토리 블록 매핑
`주간 순위 히스토리` 블록은 현재 `weekly_rankings`를 기준으로 순위/점수/비중 히스토리를 표시하는 구조다.

여기에도 같은 종목의 실제 운영 성과를 함께 보여주려면, `weekly_rankings` row와 event row를 매칭해 표시한다.

### 매칭 키

user scope:

```text
service_profile
security_code
week_end
```

internal/tseries scope:

```text
model_code
security_code
week_end
```

매칭된 event row에서 아래 값을 함께 표시한다.

```text
event_type
event_date
forward_returns["1w"]
forward_returns["2w"]
forward_returns["1m"]
forward_returns["2m"]
forward_returns["3m"]
current_return
forward_risk_metrics["1m"].mdd
forward_risk_metrics["1m"].sharpe
current_risk_metrics.mdd
current_risk_metrics.sharpe
```

## null / N/A 처리
아래 경우에는 `0` 또는 `0%`로 표시하지 말고 `N/A`로 표시한다.

- 해당 horizon 종료일이 아직 도래하지 않은 경우
- 해당 기간 거래 데이터가 아직 부족한 경우
- `forward_returns[horizon] = null`
- `forward_risk_metrics[horizon].mdd = null`
- `forward_risk_metrics[horizon].sharpe = null`

특히 `2M/3M/6M/1Y`는 아직 운영 기간이 짧아 `N/A`가 정상일 수 있다.

## 표시 기준
수익률/MDD:

- `0.1234` → `12.34%`
- `-0.051393` → `-5.14%`

Sharpe:

- `5.716243` → `5.72`
- percent로 표시하지 않는다.

## 화면 안내 문구 권장

```text
이 표는 모델 운영 시작 이후 실제로 편입된 종목의 사후 시장가격 성과를 보여줍니다.
과거 백테스트 재구성 이벤트는 제외되며, 아직 기간이 도래하지 않은 성과는 N/A로 표시됩니다.
MDD와 Sharpe는 편입일 이후 해당 기간 종료일까지의 종목별 가격 경로 기준입니다.
```

## 완료 기준
1. `편입 후 추적 성과` 블록에서 모델별 live_start_date 이후 종목만 실제 운영 성과로 표시된다.
2. 종목별 `1W`, `2W`, `1M`, `2M`, `3M`, `현재까지` 수익률이 표시된다.
3. 종목별 `1M MDD`, `1M Sharpe`가 표시된다.
4. `주간 순위 히스토리` 블록에서도 동일 종목/주차에 매칭되는 실제 운영 성과가 함께 표시된다.
5. live_start_date 이전 백테스트/재구성 row는 실제 운영 성과로 표시하지 않는다.
6. `null` 값은 `0`이 아니라 `N/A`로 표시한다.
7. Sharpe는 percent가 아닌 숫자 지표로 표시한다.

