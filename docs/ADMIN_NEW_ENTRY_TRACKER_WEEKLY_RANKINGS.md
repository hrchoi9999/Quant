# Admin New Entry Tracker Weekly Rankings

## 목적

`admin_new_entry_tracker.json`의 이벤트 row와 주간 순위 row를 같은 키로 연결해,
관리자 화면에서 신규 편입/재편입/비중증가/승격 이벤트 당시의 순위와 점수를 함께 보여주기 위한 운영 규칙을 정의한다.

## Canonical Payload

- 파일: [admin_new_entry_tracker.json](D:/Quant/service_platform/web/admin_data/current/admin_new_entry_tracker.json)
- 생성 스크립트: [build_admin_new_entry_tracker.py](D:/Quant/scripts/build_admin_new_entry_tracker.py)
- 검증 스크립트: [validate_admin_new_entry_tracker.py](D:/Quant/scripts/validate_admin_new_entry_tracker.py)

## Top-level 구조

- `user_models`
  - 사용자용 모델 이벤트 row
- `internal_models`
  - 내부 S-series 이벤트 row
- `tseries_models`
  - T-series 이벤트 row
- `weekly_rankings.user_models`
  - 사용자용 모델 주간 순위 row
- `weekly_rankings.internal_models`
  - 내부 S-series 주간 순위 row
- `weekly_rankings.tseries_models`
  - T-series 주간 순위 row
- `actual_live_performance_summary`
  - 모델별 실제 운영 시작일 이후 이벤트 성과 집계

## 매칭 키

이벤트 row와 주간 순위 row는 아래 키로 매칭한다.

- user
  - `service_profile`
  - `security_code`
  - `week_end`
- internal
  - `model_code`
  - `security_code`
  - `week_end`
- tseries
  - `model_code`
  - `security_code`
  - `week_end`

`snapshot_date`는 해당 주의 실제 스냅샷 산출일을 보조로 나타내는 필드이고,
QS 연동의 canonical 매칭 키는 `week_end`다.

## weekly_rankings 생성 기준

### user_models

- 입력 소스: `reports/redbot_user_reports/redbot_user_report_{profile}_{date}.json`
- 각 공개 리포트 날짜를 주차로 묶어 `week_end` 산출
- 해당 스냅샷의 보유 종목 전체를 `target_weight` 내림차순으로 정렬
- `rank_no`, `score=target_weight`, `score_basis=target_weight_proxy` 부여

### internal_models

- 입력 소스: `quant_service_detail.db / run_holdings_history`
- `pub_model_current.published_run_id` 기준 최신 운영 run의 전체 과거 holdings history 사용
- 같은 주에 여러 스냅샷이 있으면 해당 주의 최신 `snapshot_date`를 canonical 주간 순위 스냅샷으로 사용
- 해당 스냅샷의 보유 종목 전체를 사용
- `rank_no`, `score`, `weight`를 그대로 반영
- `score_basis`
  - `score` 존재 시 `model_score`
  - 그 외 `weight_proxy`

### tseries_models

- 입력 소스: `tseries_operational.db / ts_candidates_history + ts_candidates_latest`
- 같은 주에 여러 스냅샷이 있으면 해당 주의 최신 `snapshot_date`를 canonical 주간 순위 스냅샷으로 사용
- 해당 스냅샷의 후보 전체를 사용
- 정렬 우선순위
  - `candidate_bucket` 우선순위
  - `stage2_prob` 내림차순
  - `stage1_prob` 내림차순
- `score_basis`
  - `stage2_prob` 존재 시 `stage2_prob`
  - 그 외 `stage1_prob`

## weekly_rankings 필수 필드

모든 `weekly_rankings.*` row는 아래 필드를 가진다.

- `week_end`
- `snapshot_date`
- `security_code`
- `display_name`
- `rank_no`
- `score`
- `score_basis`
- `weight`
- `is_latest_snapshot`

T-series row는 가능하면 아래 필드를 추가 유지한다.

- `candidate_bucket`
- `stage1_prob`
- `stage2_prob`

## Coverage 기대치

validator는 이벤트 row 대비 weekly ranking 매칭률을 계산한다.

- user: `95%` 이상
- internal: `90%` 이상
- tseries: `90%` 이상

기본 목표는 각 scope의 이벤트 row 대부분이 같은 주차 키로 주간 순위 row와 매칭되는 것이다.

## actual_live_performance_summary

백테스트 성과와 실제 운영 이후 성과를 분리하기 위해 아래 top-level 블록을 제공한다.

- `metric_basis`: `actual_market_price_forward_return_since_live_start`
- `horizons`: `current_return`, `1w`, `2w`, `1m`, `2m`, `3m`, `6m`, `1y`
- scope: `user_models`, `internal_models`, `tseries_models`

각 모델 row는 아래 필드를 가진다.

- `live_start_date`
- `source_event_count`
- `live_event_count`
- `latest_live_event_date`
- `metrics.{horizon}.sample_count`
- `metrics.{horizon}.avg_return`
- `metrics.{horizon}.median_return`
- `metrics.{horizon}.win_rate`
- `metrics.{horizon}.mdd_sample_count`
- `metrics.{horizon}.avg_mdd`
- `metrics.{horizon}.median_mdd`
- `metrics.{horizon}.sharpe_sample_count`
- `metrics.{horizon}.avg_sharpe`
- `metrics.{horizon}.median_sharpe`

`sample_count=0`인 기간은 성과값을 `0`으로 채우지 않고 `null`로 둔다.
QS는 이를 `N/A`로 표시해야 하며, 백테스트 성과 카드에는 이 값을 섞지 않는다.

`actual_live_performance_summary`의 MDD/Sharpe는 각 이벤트의 실제 가격 경로 기준이다.
예를 들어 `1m`은 편입일 이후 달력상 1개월 목표일 이후 첫 거래일까지의 path MDD와 일간 수익률 기반 Sharpe를 계산한 뒤 모델별 평균/중앙값으로 집계한다.
`model_performance_summary`의 `mdd_1y`, `sharpe_1y`는 모델 NAV 기반 요약 지표이므로 실제 운영 이벤트 코호트 지표와 구분해서 표시한다.

## 운영 메모

- `weekly_rankings`는 현재 보유 종목만이 아니라 이벤트 집합을 덮을 수 있도록 전체 과거 스냅샷을 포함한다.
- 관리자 화면에서는 `rank_no`, `score`, `score_basis`, `weight`를 직접 표시하고,
  필요 시 `snapshot_date`를 함께 노출해 같은 주 내 실제 산출일도 확인할 수 있다.
