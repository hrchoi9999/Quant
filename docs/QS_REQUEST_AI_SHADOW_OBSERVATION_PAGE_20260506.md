# QS 작업 요청서 - AI Shadow 운영 관찰 페이지 반영

## 작업명

AI Shadow 운영 관찰 payload 연동 및 admin 화면 반영

## 요청 출처

Quant 모델 쓰레드

## 배경

Quant 쪽에서 공통 AI overlay와 모델별 AI overlay를 비교하고, 실제 운영 이후 live-only 성과를 추적하기 위한 payload를 생성했습니다.

이제 redbot.co.kr admin 영역에서 AI shadow 관찰 결과를 볼 수 있도록 QS 연동이 필요합니다.

## Quant 제공 payload

운영 canonical 예정 경로:

- `https://storage.googleapis.com/quantservice-489808-market-analysis/admin/current/ai_shadow_observation.json`

로컬 생성 경로:

- `D:\Quant\service_platform\web\admin_data\current\ai_shadow_observation.json`

현재 생성 기준:

- `as_of_date = 2026-05-04`
- `visibility = admin_only`
- `source_name = quant_ai_shadow_observation`
- `schema_version = 1.0`

## Payload 주요 shape

Top-level:

- `source_name`
- `schema_version`
- `visibility`
- `model_code`
- `as_of_date`
- `generated_at`
- `timezone`
- `metric_basis`
- `description`
- `horizons`
- `model_specific_training`
- `decision_matrix`
- `shadow_counts`
- `reconstructed_summary`
- `live_summary`
- `latest_shadow_sample`

## 주요 표시 요청

### 1. AI Shadow 관찰 요약

표시 내용:

- 기준일 `as_of_date`
- 생성시각 `generated_at`
- live 관찰 상태 `live_summary.status`
- 학습 성공 모델 수
- fallback 모델 수

현재 예시:

- trained model count: `8`
- fallback model count: `6`
- live status: `pending_samples`

### 2. 공통 AI vs 모델별 AI 비교

사용 필드:

- `decision_matrix`
- `reconstructed_summary.common_ai_1m`
- `reconstructed_summary.model_specific_ai_1m`
- `reconstructed_summary.comparison_bucket_1m`

핵심 테이블:

- 공통 AI bucket별 1M 성과
- 모델별 AI bucket별 1M 성과
- 조합 bucket별 1M 성과

권장 표시 문구:

- reconstructed 성과는 연구/검증용입니다.
- live-only 성과가 충분히 쌓이기 전까지 실제 모델 교체 로직으로 사용하지 않습니다.

### 3. 모델별 전용 AI 학습 상태

사용 필드:

- `model_specific_training.trained_models`
- `model_specific_training.fallback_models`

표시 내용:

- 모델 코드
- label rows
- AUC
- top30 1M return
- top30 win rate
- fallback 사유

### 4. Live-only 추적 현황

사용 필드:

- `live_summary.status`
- `live_summary.horizon_status`
- `live_summary.decision_rows`
- `live_summary.tag_rows`
- `live_summary.model_specific_tag_rows`

표시 규칙:

- `sample_count = 0`이면 N/A
- `pending_samples`이면 “아직 forward 기간 미도래”로 표시
- 1W는 5거래일 이후, 2W는 10거래일 이후, 1M은 21거래일 이후부터 의미 있음

### 5. 최신 shadow 후보 샘플

사용 필드:

- `latest_shadow_sample`

표시 가능 컬럼:

- scope/model
- 종목코드/종목명
- event_date
- 공통 AI decision/tag
- 모델별 AI tag
- 공통 AI quality/risk prob
- 모델별 AI quality/risk prob

## QS UI 위치 제안

admin 전용 메뉴 아래 신규 페이지:

- 메뉴명: `AI Shadow 관찰`
- 또는 기존 `내부용 모델` 페이지 하단 탭으로 추가

추천은 별도 admin 페이지입니다.

이유:

- reconstructed 성과와 live-only 성과를 명확히 구분해야 함
- 일반 모델 성과 카드와 섞이면 백테스트/실제성과/AI shadow 성과가 혼동될 수 있음

## Acceptance Criteria

1. admin 로그인 상태에서만 접근 가능
2. `ai_shadow_observation.json` remote payload를 읽어 화면 표시
3. 공통 AI vs 모델별 AI 비교표 표시
4. model-specific trained/fallback 모델 목록 표시
5. live-only sample이 없는 구간은 `N/A` 또는 `기간 미도래`로 표시
6. reconstructed 성과와 live-only 성과가 시각적으로 분리됨

## 참고

Quant 쪽 publish 연결:

- `D:\Quant\scripts\publish_public_current_to_gcs.py`
- admin current publish 시 `admin/current/ai_shadow_observation.json`도 함께 업로드되도록 반영 완료

Quant pipeline 연결:

- `D:\Quant\src\quant_service\run_daily_quant_pipeline.py`
- AI overlay 단계에서 payload 생성까지 연결 완료
