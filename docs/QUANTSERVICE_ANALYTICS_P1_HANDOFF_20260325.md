# QuantService Analytics P1 Handoff (2026-03-25)

이번 handoff는 `1차 묶음` 페이지 개발용 내부 preview 데이터 전달이다.
아직 사용자 웹서비스에 반영하거나 배포하지 않는다.
최종 반영은 사용자 컨펌 이후에만 진행한다.

## 범위
- 오늘의 모델 정보 페이지
- 모델 변화 페이지
- 모델 비교 페이지

## 중요 원칙
1. 현재 payload는 내부 preview 전용이다.
2. `web_publish_enabled=false` 상태를 유지한다.
3. QuantService는 이 파일들을 mock/internal source로만 사용한다.
4. production API/current snapshot으로 합치지 않는다.
5. 사용자 컨펌 전까지 redbot.co.kr 실서비스에 연결하지 않는다.

## 사용 파일
- [bundle_manifest_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/bundle_manifest_20260325.json)
- [today_model_info_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/today_model_info_20260325.json)
- [model_changes_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_changes_20260325.json)
- [model_compare_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_compare_20260325.json)

## 페이지별 사용 데이터
### 1. 오늘의 모델 정보
파일:
- [today_model_info_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/today_model_info_20260325.json)

핵심 필드:
- `models[].model_code`
- `models[].display_name`
- `models[].risk_grade`
- `models[].headline_metrics.cagr`
- `models[].headline_metrics.mdd`
- `models[].headline_metrics.sharpe`
- `models[].headline_metrics.current_drawdown`
- `models[].headline_metrics.return_4w`
- `models[].headline_metrics.return_12w`
- `models[].asset_mix.stock_weight`
- `models[].asset_mix.etf_weight`
- `models[].asset_mix.cash_weight`
- `models[].recent_change_summary`
- `models[].top_holdings[]`
- `models[].holding_highlights[]`

추천 UI:
- 모델 상단 요약 카드
- 최근 4W/12W 성과 카드
- 자산 비중 카드
- 상위 보유종목 테이블
- 장기 보유 highlight 3~5개

### 2. 모델 변화
파일:
- [model_changes_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_changes_20260325.json)

핵심 필드:
- `models[].summary.new_8w`
- `models[].summary.exit_8w`
- `models[].summary.increase_8w`
- `models[].summary.decrease_8w`
- `models[].items[]`
  - `week_end`
  - `ticker`
  - `name`
  - `asset_type`
  - `change_type`
  - `weight_prev`
  - `weight_curr`
  - `delta_weight`

추천 UI:
- 최근 8주 요약 카드
- 변경 타임라인/테이블
- change_type filter
- 종목코드/종목명/변화폭 표시

### 3. 모델 비교
파일:
- [model_compare_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_compare_20260325.json)

핵심 필드:
- `rows[].model_code`
- `rows[].display_name`
- `rows[].risk_grade`
- `rows[].cagr`
- `rows[].mdd`
- `rows[].sharpe`
- `rows[].return_4w`
- `rows[].return_12w`
- `rows[].current_drawdown`
- `rows[].relative_strength_vs_benchmark_4w`
- `rows[].stock_weight`
- `rows[].etf_weight`
- `rows[].cash_weight`
- `rows[].new_8w`
- `rows[].exit_8w`
- `rows[].increase_8w`
- `rows[].decrease_8w`

추천 UI:
- compare table
- 정렬 가능한 KPI 테이블
- 4W / 12W / CAGR / MDD 중심 카드

## 개발 순서
1. 오늘의 모델 정보 페이지
2. 모델 변화 페이지
3. 모델 비교 페이지

## 현재 데이터 해석 주의
- S3 / S3_CORE2는 asset mix가 payload에서 display fallback으로 보정되어 있다.
- 즉 지금 단계에서는 `top_holdings`와 `headline_metrics`가 더 신뢰도 높은 표시축이다.
- 모델 비교 페이지에서 S3 / S3_CORE2의 자산구성은 과도한 정밀 해석을 피한다.

## 금지
- current web snapshot 교체 금지
- production API 연결 금지
- 실서비스 메뉴 노출 금지
- redbot.co.kr 반영 금지

## 완료 기준
1. 3개 페이지가 내부 환경에서 렌더링된다.
2. 위 3개 JSON 파일만으로 화면을 구성한다.
3. 사용자 컨펌 전까지 배포/실서비스 반영은 하지 않는다.
