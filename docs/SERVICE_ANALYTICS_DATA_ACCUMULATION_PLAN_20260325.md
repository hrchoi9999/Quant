# SERVICE_ANALYTICS_DATA_ACCUMULATION_PLAN_20260325.md

## 목적
모델 운영 과정에서 발생하는 각종 지표, 변경내역, 자산구조 변화를 누적 저장하고 시계열 분석할 수 있도록 데이터 계층을 설계한다.

중요 원칙:
- 원천 데이터는 기존 Quant DB를 그대로 사용한다.
- 신규 분석 결과는 별도 analytics DB에 저장한다.
- 웹서비스 반영 전까지는 read-only 분석 자산으로만 사용한다.

## 현재 이미 저장되고 있는 데이터

### quant_service.db
- `run_runs`
- `run_summary`
- `pub_model_current`
- `pub_model_current_holdings`
- `pub_model_nav_history`
- `pub_model_performance`
- `pub_model_rebalance_events`

### quant_service_detail.db
- `run_nav_daily`
- `run_holdings_history`
- `run_trades`
- `run_signal_details_s2`
- `run_signal_details_s3`
- `run_signal_details_s3_core2`

### price.db / regime.db
- `prices_daily`
- `instrument_master`
- `etf_meta`
- `regime_history`

## 현재 데이터로 바로 만들 수 있는 분석 자산
- 모델 run 시계열
- 일별 NAV 품질 지표
- 주간 holdings 변화
- 자산구조 변화
- 모델 품질 지표

## 추가로 필요한 분석 전용 데이터
신규 DB 권장:
- `D:\Quant\data\db\service_analytics.db`

권장 테이블:
- `analytics_model_run_overview`
- `analytics_model_weekly_snapshot`
- `analytics_model_asset_mix_weekly`
- `analytics_model_change_log`
- `analytics_holding_lifecycle`
- `analytics_model_quality_weekly`

## 개발 방안
1. 기존 DB는 수정하지 않는다.
2. analytics 전용 DB를 신규 생성한다.
3. 분석 스크립트는 기존 DB를 read-only로 읽고 집계 결과만 새 DB에 저장한다.
4. 초기에는 수동 또는 일일 배치 종료 후 별도 실행한다.
5. 사용자 승인 전까지는 웹 current payload 갱신 단계에 연결하지 않는다.
