# QuantService Analytics P4 Handoff

## Summary

P4 internal preview adds two new admin-facing data views:

1. `asset_exposure_detail`
2. `change_impact`

Both remain internal preview only and are not connected to public web.

## New Source Tables

- [analytics_model_asset_detail_weekly](D:/Quant/data/db/service_analytics.db)
- [analytics_model_change_activity_weekly](D:/Quant/data/db/service_analytics.db)
- [analytics_model_change_impact_weekly](D:/Quant/data/db/service_analytics.db)

## New Review Outputs

- [latest_asset_detail_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/latest_asset_detail_20260325.csv)
- [latest_change_activity_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/latest_change_activity_20260325.csv)
- [recent_change_impact_8w_20260325.csv](D:/Quant/reports/service_analytics_review/20260325/recent_change_impact_8w_20260325.csv)

## New Preview Bundle

- [bundle_manifest_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p4_bundle/bundle_manifest_20260325.json)
- [asset_exposure_detail_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p4_bundle/asset_exposure_detail_20260325.json)
- [change_impact_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p4_bundle/change_impact_20260325.json)

## asset_exposure_detail

각 모델 row 에 포함:
- `latest_asset_detail`
- `asset_detail_trend_26w`
- `latest_change_activity`

세부 bucket 예시:
- `stock_equity`
- `etf_equity`
- `etf_bond`
- `etf_fx`
- `etf_gold`
- `etf_inverse`
- `etf_covered_call`
- `cash`
- `etf_other`
- `other`

의미:
- 기존 `stock / etf / cash`보다 더 세밀한 자산 노출 해석 가능
- 구조 페이지 고도화에 적합

## change_impact

각 모델 row 에 포함:
- `latest_change_activity`
- `change_activity_trend_26w`
- `recent_new_entries_impact_8w`
- `recent_exits_impact_8w`
- `impact_summary`

핵심 지표:
- `change_intensity_score`
- `change_intensity_label`
- `avg_new_return_observed_8w`
- `avg_exit_return_observed_8w`

의미:
- 최근 변경 강도가 어느 정도인지
- 최근 신규 편입 종목이 이후 얼마나 움직였는지
- 제외 종목이 어떤 성과 구간에서 빠졌는지
를 admin 에서 분석 가능

## QS 표현 가이드

### 1. 자산 노출 상세 페이지
- stacked bar / area chart / bucket table 중심 권장
- `latest_asset_detail` 는 현재 bucket 비중 카드/표로 사용
- `asset_detail_trend_26w` 는 주차별 stack chart 로 사용 가능

### 2. 변화 영향 페이지
- `latest_change_activity` 는 상단 요약 카드
- `change_activity_trend_26w` 는 line/bar chart
- `recent_new_entries_impact_8w`, `recent_exits_impact_8w` 는 table 중심
- `change_intensity_label` 은 `low / medium / high` badge 로 사용 가능

## Safety

- internal preview only
- `meta.internal_preview_only = true`
- `meta.web_publish_enabled = false`
- public/current snapshot/API 와 분리 유지
