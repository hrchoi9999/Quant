# QS 작업 요청

## 작업명

관리자 전용 `신규 편입 추적` 페이지 및 API 추가

## 요청 출처

Quant 모델 쓰레드

## 배경

현재 redbot 공개 `변경내역` 페이지는 사용자용 3모델(`stable / balanced / growth`)의 최근 변경 항목을 보여주는 용도입니다.

하지만 운영/분석 관점에서는 아래 목적의 별도 관리자 전용 화면이 필요합니다.

- 매주 새로 편입된 종목만 누적 관리
- 사용자용 모델 / 내부 S-series / T-series를 분리 조회
- 편입 이후 실제 시장 성과 추적
- 비중 증가와 진짜 신규 편입을 구분

이번 요청의 목적은 공개 `변경내역`과 분리된 admin-only 페이지를 추가해, `신규 편입` cohort를 장기 추적하는 것입니다.

## Quant 측 선반영 완료 사항

Quant 쪽에서는 admin 전용 handoff payload를 생성하도록 반영했습니다.

### 1. 신규 payload 생성 스크립트

- [build_admin_new_entry_tracker.py](D:/Quant/scripts/build_admin_new_entry_tracker.py)
- [validate_admin_new_entry_tracker.py](D:/Quant/scripts/validate_admin_new_entry_tracker.py)

### 2. daily pipeline 자동 연결

- [run_daily_quant_pipeline.py](D:/Quant/src/quant_service/run_daily_quant_pipeline.py)

즉, 앞으로 Quant daily pipeline이 돌면 아래 admin payload도 함께 갱신됩니다.

### 3. 산출 파일 위치

- [admin_new_entry_tracker.json](D:/Quant/service_platform/web/admin_data/current/admin_new_entry_tracker.json)

### 4. 현재 생성 기준

- `as_of_date = 2026-04-14`
- 현재 row 수
  - user models: `149`
  - internal models: `2969`
  - tseries models: `2804`

## 데이터 설계 의도

이 payload는 단순 변경내역이 아니라 `신규 편입 추적용`입니다.

### 사용자용 모델

원천:
- `redbot_user_report_{profile}_{yyyymmdd}.json`

판정 규칙:
- `new_entry`
  - 직전 snapshot 비중 `0`
  - 현재 snapshot 비중 `> 0`
- `re_entry`
  - 과거 보유 이력이 있으나 비보유 상태를 거친 뒤 재등장
- `weight_increase`
  - 이미 보유 중이던 종목의 비중 증가

즉 기존의 `increase_items`를 그대로 신규 편입으로 쓰지 않고, 실제 holdings 비교로 재계산합니다.

### 내부 운영 모델

원천:
- `service_analytics.db`
- table: `analytics_model_change_log`

판정 규칙:
- `change_type='new'` 기반
- 과거 동일 모델/종목의 `new` 이력이 있으면 `re_entry`로 재분류
- `change_type='increase'`는 `weight_increase`로 별도 보존

### T-series

원천:
- `tseries_operational.db`
- `ts_candidates_history`
- `ts_candidates_latest`

판정 규칙:
- `new_entry`
  - watchlist에 처음 등장
- `re_entry`
  - 과거 등장 이력이 있으나 비등장 구간 후 재등장
- `promotion`
  - `observe -> near`, `near -> confirmed` 같은 승격

즉 T-series는 비중이 아니라 `watchlist 등장/재등장/승격` 중심으로 관리합니다.

## Payload shape

top-level:

- `source_name`
- `schema_version`
- `visibility`
- `as_of_date`
- `generated_at`
- `freshness`
- `summary`
- `user_models`
- `internal_models`
- `tseries_models`

### `freshness`

- `user_latest_asof`
- `internal_latest_week_end`
- `tstock_latest_event_date`
- `tetf_latest_event_date`

### `summary`

- `user_models[]`
  - `service_profile`
  - `event_type`
  - `count`
- `internal_models[]`
  - `model_code`
  - `event_type`
  - `count`
- `tseries_models[]`
  - `model_code`
  - `event_type`
  - `count`

### `user_models[]` row 예시 필드

- `scope`
- `service_profile`
- `user_model_name`
- `model_key`
- `event_type`
- `event_date`
- `week_end`
- `security_code`
- `display_name`
- `asset_group`
- `prev_weight`
- `curr_weight`
- `delta_weight`
- `is_current`
- `forward_returns`
- `current_return`
- `latest_price_date`

### `internal_models[]` row 예시 필드

- `scope`
- `model_code`
- `model_key`
- `event_type`
- `event_date`
- `week_end`
- `security_code`
- `display_name`
- `delta_weight`
- `is_current`
- `forward_returns`
- `current_return`
- `latest_price_date`

### `tseries_models[]` row 예시 필드

- `scope`
- `model_code`
- `model_key`
- `event_type`
- `event_date`
- `week_end`
- `security_code`
- `display_name`
- `from_bucket`
- `to_bucket`
- `stage1_prob`
- `stage2_prob`
- `is_current`
- `forward_returns`
- `current_return`
- `latest_price_date`

## QS 요청 사항

### 1. 관리자 전용 페이지 추가

권장 route:

- `/admin/new-entries`

### 2. 외부 비노출

- public navigation에 노출하지 말 것
- direct public route로 공개하지 말 것
- 관리자 로그인 / admin session 상태에서만 접근 가능하게 해 주세요

### 3. 관리자 API 추가

권장 route:

- `/api/v1/admin/new-entries`

권장 query:

- `?scope=user`
- `?scope=internal`
- `?scope=tseries`
- `?event_type=new_entry`
- `?event_type=re_entry`
- `?event_type=promotion`
- `?period=4w`
- `?period=8w`
- `?period=all`

### 4. 화면 구조

상단 필터:

- scope
  - `user`
  - `internal`
  - `tseries`
- event type
  - `new_entry`
  - `re_entry`
  - `promotion`
  - `weight_increase`
- 기간
  - `4w`
  - `8w`
  - `all`

모델 필터:

- user
  - `stable`
  - `balanced`
  - `growth`
- internal
  - `S2`
  - `S3`
  - `S4`
  - `S5`
  - `S6`
- tseries
  - `T-STOCK-V01`
  - `T-ETF-V01`

### 5. 페이지 기본 노출 원칙

기본값은 아래를 권장합니다.

- 기본 scope: `user`
- 기본 event_type: `new_entry`

즉, 관리자 화면을 열면 우선 `사용자용 모델의 진짜 신규 편입`만 보이게 해 주세요.

보조적으로:

- `re_entry`
- `weight_increase`
- `promotion`

을 필터로 전환해서 볼 수 있게 해 주세요.

### 6. 표시 컬럼 권장

공통:

- 주차(`week_end`)
- 모델명
- 종목명
- 종목코드
- 이벤트 유형
- 최초/해당 편입일
- 현재 추적 수익률
- 1주 / 2주 / 1개월 / 3개월 추적 수익률
- 현재 유지 여부

user 전용 추가:

- `prev_weight`
- `curr_weight`
- `delta_weight`

tseries 전용 추가:

- `from_bucket`
- `to_bucket`
- `stage1_prob`
- `stage2_prob`

### 7. 문구/표현 원칙

권장:

- `신규 편입`
- `재편입`
- `비중 증가`
- `승격`
- `편입 후 추적 성과`

비권장:

- `추천 종목`
- `매수 종목`
- `수익 보장`
- `실전 매매 지시`

## 현재 판단

이 기능은 기존 공개 `변경내역` 페이지 안에 넣기보다, 관리자 전용 별도 페이지로 분리하는 것이 맞습니다.

이유:

- 공개 `변경내역`은 diff 설명용
- `신규 편입 추적`은 cohort 추적용
- 사용자용 모델 / 내부 S-series / T-series는 의미가 달라 한 화면 공개 합치기가 부적절함

## 완료 기준

1. `/admin/new-entries` 관리자 전용 페이지 접근 가능
2. public nav / public route에는 노출되지 않음
3. `user / internal / tseries` scope 분리 조회 가능
4. `new_entry / re_entry / weight_increase / promotion` 필터 동작
5. 주차별 신규 편입 종목과 추적 수익률 조회 가능
6. 공개 `변경내역` 페이지와는 별도 관리

## 참고

이번 요청은 `QS UI/API/admin route` 작업 요청입니다.

Quant 쪽 데이터 생성은 이미 완료되었고, 앞으로 daily pipeline에서 자동 갱신됩니다.
