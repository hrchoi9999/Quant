# QuantService Analytics P5 Handoff

## Summary

P5 는 admin/internal preview 운영 안정화 단계입니다.

핵심 범위:
1. bundle 공통 build/freshness meta 추가
2. manifest file_meta / build_status 추가
3. bundle validation 공통화 강화
4. admin ops status / bundle health preview 추가
5. 일일 배치에서 P5 자동 생성 연결

## Common Meta Added To Bundles

대상 bundle:
- P1
- P2
- P3
- P4
- P5

공통 meta 주요 필드:
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

## Manifest Enhancements

각 bundle manifest 에 추가:
- `file_meta`
  - `path`
  - `exists`
  - `size_bytes`
  - `md5`
- `build_status`

의미:
- QS admin 에서 현재 preview 파일이 실제 생성됐는지 확인 가능
- 운영 점검용으로 바로 활용 가능

## New P5 Bundle

- [bundle_manifest_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p5_bundle/bundle_manifest_20260325.json)
- [admin_ops_status_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p5_bundle/admin_ops_status_20260325.json)
- [bundle_health_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p5_bundle/bundle_health_20260325.json)

### admin_ops_status
- `overall_status`
- `bundle_count`
- `bundles_ok`
- `recommendation`

### bundle_health
- P1~P4 각 bundle 의 상태 요약
- `manifest_exists`
- `build_status`
- `built_at_utc`
- `latest_week_end`
- `files_ok`
- `schema_version`
- `bundle_version`

## Validation Reinforcement

- P1/P2/P3/P4 validator 가 공통 meta 검증을 수행
- manifest 의 `file_meta.exists` 도 같이 확인
- P5 validator 는 admin ops status/bundle health 자체도 검증

## Daily Pipeline

- [run_daily_quant_pipeline.py](D:/Quant/src/quant_service/run_daily_quant_pipeline.py) 에서 P5 build/validate 까지 자동 연결
- 즉 일일 Quant 배치 후 admin/internal preview 상태 점검도 같이 수행됨

## QS 활용 가이드

### 1. Admin 운영 상태 페이지
- `admin_ops_status` 를 최상단 health card 로 사용 가능
- `bundle_health` 를 bundle 상태 table 로 사용 가능

### 2. Admin 디버그/운영 표시
- 각 페이지 상단에서 `built_at_utc`, `latest_week_end` 를 보조 메타로 표시 가능
- stale/missing 파일 판단을 admin 에서 바로 할 수 있음

### 3. Public 반영 금지
- P5 는 운영용/관리용 메타 성격이 강함
- public/current snapshot 으로 합치지 말 것

## Safety

- internal preview only
- `meta.internal_preview_only = true`
- `meta.web_publish_enabled = false`
- public API/current snapshot 과 분리 유지
