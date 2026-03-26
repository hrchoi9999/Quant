# QuantService Analytics P2 Improvements Handoff

## Summary

2차 묶음 개선은 admin preview 데이터의 운영 신뢰성을 높이는 방향으로 반영되었습니다.

핵심 변경:
1. change log 분류에 materiality threshold 적용
2. holding lifecycle 에 re-entry episode 규칙 반영
3. data quality checks 테이블 및 review CSV 추가
4. p3 `model_quality` payload 에 `quality_checks` 추가

## What Changed

### 1. change log threshold
- 원천 테이블: [analytics_model_change_log](D:/Quant/data/db/service_analytics.db)
- 기준: `CHANGE_WEIGHT_EPS = 0.001`
- 의미:
  - 0.1% 미만의 미세한 비중 변화는 change event 로 잡지 않음
  - `new / exit / increase / decrease` 분류가 더 안정적으로 유지됨

추가 필드:
- `classification_eps`
- `is_material_change`

### 2. holding lifecycle re-entry episode
- 원천 테이블: [analytics_holding_lifecycle](D:/Quant/data/db/service_analytics.db)
- 기준: `REENTRY_GAP_DAYS = 45`
- ticker 가 다시 들어오면 별도 episode 로 분리

추가 필드:
- `episode_no`
- `total_episodes_for_ticker`
- `is_current_episode`
- `reentry_count`
- `gap_rule_days`

현재 preview 반영:
- P2 `current_holdings_lifecycle` 는 current episode 기준으로 정리됨
- P2 `longest_historical_holdings` 는 historical episode 전체 기준으로 남음

### 3. quality checks
- 새 테이블: [analytics_data_quality_checks](D:/Quant/data/db/service_analytics.db)
- review CSV: [data_quality_checks_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/data_quality_checks_20260325.csv)

대표 check:
- `asset_mix_gross_weight`
- `change_log_null_name`
- `change_log_below_threshold`
- `lifecycle_reentries`
- `quality_current_drawdown`

### 4. P3 payload quality_checks
- 파일: [model_quality_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/model_quality_20260325.json)
- 각 모델 row 에 `quality_checks[]` 추가

구조:
- `check_name`
- `status`
- `metric_value`
- `detail`

## Operational Meaning For QS

### breaking change 여부
- 기존 페이지는 대부분 그대로 동작 가능
- 이번 변경은 주로 품질 보강과 admin 보조 정보 추가

### QS 에서 활용 가능한 것
1. `model_quality` 페이지에 `quality_checks` badge / table 추가 가능
2. `holding_lifecycle` 페이지에서 current lifecycle 은 더 신뢰해도 됨
3. `model_changes` 페이지는 노이즈가 줄어든 change rows 를 사용하면 됨

### 권장 표현
- quality check 상태는 `ok / warn` badge 로만 표시
- detail 문자열은 tooltip 또는 admin table detail 로 사용
- re-entry 관련 값은 admin 전용으로만 노출 권장

## Safety

- 여전히 internal preview only
- public web 반영 금지
- production current snapshot/API 와 분리 유지
