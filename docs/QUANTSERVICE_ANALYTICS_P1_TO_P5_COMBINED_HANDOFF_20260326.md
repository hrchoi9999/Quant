# QuantService Analytics P1-P5 Combined Handoff

## Scope

이 문서는 service analytics admin/internal preview의 **1차 ~ 5차** 개발분을 한 번에 정리한 통합 handoff 입니다.

중요 원칙:
- internal preview only
- public web 반영 금지
- production API/current snapshot 과 분리 유지
- 사용자 최종 승인 전까지 redbot.co.kr public 영역 연결 금지

## Preview Bundle Map

### P1
- 목적: 오늘의 모델 정보 / 모델 변화 / 모델 비교
- 경로:
  - [today_model_info_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/today_model_info_20260325.json)
  - [model_changes_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_changes_20260325.json)
  - [model_compare_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_compare_20260325.json)

### P2
- 목적: 포트폴리오 구조 / 보유 종목 이력
- 경로:
  - [portfolio_structure_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/portfolio_structure_20260325.json)
  - [holding_lifecycle_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/holding_lifecycle_20260325.json)

### P3
- 목적: 모델 품질 / 주간 브리핑
- 경로:
  - [model_quality_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/model_quality_20260325.json)
  - [weekly_briefing_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/weekly_briefing_20260325.json)

### P4
- 목적: 자산 노출 상세 / 변화 영향
- 경로:
  - [asset_exposure_detail_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p4_bundle/asset_exposure_detail_20260325.json)
  - [change_impact_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p4_bundle/change_impact_20260325.json)

### P5
- 목적: admin 운영 상태 / bundle health
- 경로:
  - [admin_ops_status_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p5_bundle/admin_ops_status_20260325.json)
  - [bundle_health_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p5_bundle/bundle_health_20260325.json)

## P1-P5 핵심 개선 내용

### P1
- `change_log` 이름 보강
- `date_context` 추가
- S3/S3_CORE2 preview 안정화

### P2
- `CHANGE_WEIGHT_EPS = 0.001` materiality threshold 적용
- `REENTRY_GAP_DAYS = 45` 기준 lifecycle episode 분리
- `quality_checks[]` 추가

### P3
- benchmark 상대지표 `4W -> 12W / 52W` 확장
- `turnover`, `top1/top3/top5`, `HHI` 추가
- `briefing_points` 품질 개선

### P4
- 자산 노출 세분화
  - `stock_equity`, `etf_equity`, `etf_bond`, `etf_fx`, `etf_gold`, `etf_inverse`, `etf_covered_call`, `cash`, `etf_other`, `other`
- 변화 강도 점수
  - `change_intensity_score`
  - `change_intensity_label`
- 편입/제외 이후 관찰값
  - `recent_new_entries_impact_8w`
  - `recent_exits_impact_8w`
  - `avg_new_return_observed_8w`
  - `avg_exit_return_observed_8w`

### P5
- P1~P4 공통 build/freshness meta 추가
- manifest `file_meta / build_status` 추가
- bundle validation 강화
- admin ops status / bundle health 추가
- 일일 배치에서 P5까지 자동 생성 연결

## Common Meta / Manifest

P1~P5 bundle manifest 공통 필드:
- `bundle_version`
- `schema_version`
- `built_at_utc`
- `freshness`
  - `asof`
  - `analytics_db_path`
  - `analytics_db_mtime_utc`
  - `latest_week_end`
  - `latest_change_week_end`
  - `latest_quality_week_end`
- `source_counts`
- `file_meta`
  - `path`
  - `exists`
  - `size_bytes`
  - `md5`
- `build_status`

예시:
- [p1 manifest](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/bundle_manifest_20260325.json)
- [p5 manifest](D:/Quant/reports/service_analytics_review/20260325/p5_bundle/bundle_manifest_20260325.json)

## QS 반영 우선순위 추천

### 1차 반영
- P1
- P2
- P3

### 2차 반영
- P4

### 3차 반영
- P5

이유:
- P1~P3가 사용자/admin 체감 가치가 가장 큼
- P4는 고급 분석
- P5는 운영 상태/관리 메타 중심

## QS 표현 가이드

### P1
- 카드 + 표 중심
- `date_context`를 보조 메타로 표시 가능

### P2
- 구조 페이지는 stacked / breakdown 중심
- lifecycle은 table 중심

### P3
- 품질 페이지는 line chart + table
- 브리핑 페이지는 `briefing_points` 우선 사용
- QS가 새 투자판단 문구를 만들지 말 것

### P4
- `asset_exposure_detail` 는 bucket stack chart / bucket table
- `change_impact` 는 intensity card + recent new/exit impact table

### P5
- `admin_ops_status` 는 상단 health card
- `bundle_health` 는 admin 운영 table
- stale/missing preview 확인용

## Internal Review Files

추가 review CSV:
- [latest_asset_detail_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/latest_asset_detail_20260325.csv)
- [latest_change_activity_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/latest_change_activity_20260325.csv)
- [recent_change_impact_8w_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/recent_change_impact_8w_20260325.csv)
- [latest_quality_metrics_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/latest_quality_metrics_20260325.csv)
- [data_quality_checks_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/data_quality_checks_20260325.csv)

## Validation Status

현재 검증 통과:
- [validate_service_analytics.py](D:/Quant/scripts/validate_service_analytics.py)
- [validate_service_analytics_bundle_p1.py](D:/Quant/scripts/validate_service_analytics_bundle_p1.py)
- [validate_service_analytics_bundle_p2.py](D:/Quant/scripts/validate_service_analytics_bundle_p2.py)
- [validate_service_analytics_bundle_p3.py](D:/Quant/scripts/validate_service_analytics_bundle_p3.py)
- [validate_service_analytics_bundle_p4.py](D:/Quant/scripts/validate_service_analytics_bundle_p4.py)
- [validate_service_analytics_bundle_p5.py](D:/Quant/scripts/validate_service_analytics_bundle_p5.py)

## Daily Pipeline

일일 Quant 배치 후 자동 생성:
- analytics DB
- review CSV/MD
- P1
- P2
- P3
- P4
- P5

연결 파일:
- [run_daily_quant_pipeline.py](D:/Quant/src/quant_service/run_daily_quant_pipeline.py)

## Safety

- 모든 bundle 은 `internal_preview_only = true`
- 모든 bundle 은 `web_publish_enabled = false`
- public/current snapshot/API 와 합치지 말 것
- 최종 승인 전까지 redbot.co.kr public 메뉴 연결 금지
