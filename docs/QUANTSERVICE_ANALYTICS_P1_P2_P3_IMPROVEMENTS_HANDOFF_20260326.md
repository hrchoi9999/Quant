# QuantService Analytics P1-P3 Improvements Handoff

## Scope

이 문서는 admin/internal preview 용 service analytics 개선사항 중 **1차, 2차, 3차 개선**을 한 번에 정리한 통합 handoff 입니다.

대상 preview payload:
- [today_model_info_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/today_model_info_20260325.json)
- [model_changes_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_changes_20260325.json)
- [model_compare_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_compare_20260325.json)
- [portfolio_structure_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/portfolio_structure_20260325.json)
- [holding_lifecycle_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/holding_lifecycle_20260325.json)
- [model_quality_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/model_quality_20260325.json)
- [weekly_briefing_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/weekly_briefing_20260325.json)

공통 원칙:
- internal preview only
- public web 반영 금지
- production API/current snapshot 과 분리 유지

## P1 Improvements

### 1. change_log 이름 보강
- `model_changes.items[].name` 누락을 최대한 줄이도록 backfill 강화
- exit row / historical row 도 `instrument_master` 기준으로 이름 보강
- 현재 `analytics_model_change_log` 기준 null name 은 `0`

### 2. date_context 추가
- P1/P2/P3 payload 전부에 `date_context` 추가
- 주요 필드:
  - `asof_date`
  - `signal_date`
  - `effective_date`
  - `week_end`
  - 페이지별 `snapshot_date / asset_mix_week_end / quality_week_end`

### 3. S3 / S3_CORE2 preview 안정화
- asset mix preview 는 최신 analytics 기준으로 재생성됨
- admin 에서는 여전히 `top_holdings` 와 `headline_metrics` 를 우선 해석해도 됨

## P2 Improvements

### 1. change log materiality threshold
- 기준: `CHANGE_WEIGHT_EPS = 0.001`
- 0.1% 미만 미세 변화는 change event 에서 제외
- 추가 필드:
  - `classification_eps`
  - `is_material_change`

### 2. holding lifecycle re-entry episode
- 기준: `REENTRY_GAP_DAYS = 45`
- 동일 종목 재편입 시 episode 분리
- 추가 필드:
  - `episode_no`
  - `total_episodes_for_ticker`
  - `is_current_episode`
  - `reentry_count`
  - `gap_rule_days`

### 3. quality checks 추가
- 원천 테이블: [analytics_data_quality_checks](D:/Quant/data/db/service_analytics.db)
- review CSV: [data_quality_checks_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/data_quality_checks_20260325.csv)
- 현재 대표 check:
  - `asset_mix_gross_weight`
  - `change_log_null_name`
  - `change_log_below_threshold`
  - `lifecycle_reentries`
  - `quality_current_drawdown`

### 4. P3 model_quality 에 quality_checks 포함
- 각 모델 row 에 `quality_checks[]` 추가
- 구조:
  - `check_name`
  - `status`
  - `metric_value`
  - `detail`

## P3 Improvements

### 1. benchmark 상대지표 확장
- 기존: `relative_strength_vs_benchmark_4w`
- 추가:
  - `relative_strength_vs_benchmark_12w`
  - `relative_strength_vs_benchmark_52w`

### 2. turnover / concentration 지표 추가
- `latest_quality` 추가 필드:
  - `turnover_1w`
  - `turnover_avg_4w`
  - `top1_weight`
  - `top3_weight`
  - `top5_weight`
  - `holdings_hhi`
- `quality_trend_26w` 에도 동일 계열 지표 포함

### 3. weekly_briefing summary 확장
- `weekly_briefing.models[].summary` 추가 필드:
  - `relative_strength_vs_benchmark_12w`
  - `turnover_avg_4w`
  - `top5_weight`

### 4. briefing_points 품질 보강
- 기존 성과/낙폭/변화량 외에 아래도 반영
  - 12주 benchmark 상대성과
  - 최근 4주 평균 회전율
  - 상위 5개 보유 집중도
  - 현금 비중
- admin 브리핑 문구가 더 풍성해짐

## QS 에서 반영하면 좋은 부분

### 1. 날짜 해석 표시
- 페이지 상단 또는 sub-meta 에 `date_context` 표시 가능
- 권장:
  - `asof_date`
  - `effective_date`
  - `week_end`

### 2. 변화 페이지 / lifecycle 페이지
- `model_changes` 는 더 낮은 노이즈 기준으로 해석 가능
- `holding_lifecycle` 는 `is_current_episode == 1` 기준으로 현재 보유 설명 가능
- 재편입 관련 내용은 admin 에서만 보조적으로 노출 권장

### 3. 모델 품질 페이지
- `quality_checks[]` 를 badge/table 로 노출 가능
- `latest_quality` 에서 아래를 추가 카드/열로 사용 가능
  - `relative_strength_vs_benchmark_12w`
  - `turnover_avg_4w`
  - `top5_weight`
  - `holdings_hhi`

### 4. 주간 브리핑 페이지
- `briefing_points` 는 Quant 생성 문구를 그대로 사용
- 추가 수치를 함께 붙일 수 있음
  - `relative_strength_vs_benchmark_12w`
  - `turnover_avg_4w`
  - `top5_weight`

## 표현 가이드
- `quality_checks.status` 는 `ok / warn` badge 정도로 간단히 표시
- `detail` 은 tooltip 또는 admin detail row 로만 사용
- `turnover` 는 퍼센트 포맷
- `top5_weight` 는 집중도 지표로 표시
- `holdings_hhi` 는 일반 사용자용보다 admin 품질 지표로 취급 권장

## Safety
- 이 payload 들은 계속 internal preview only
- `meta.internal_preview_only = true`
- `meta.web_publish_enabled = false`
- public/current snapshot/API 와 합치지 말 것
