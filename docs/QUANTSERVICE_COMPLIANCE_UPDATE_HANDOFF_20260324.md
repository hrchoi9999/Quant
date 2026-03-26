# Quant -> QuantService Compliance Update Handoff (2026-03-24)

이 문서는 `D:\Quant\docs\QUANT_Codex_작업지시문_2026-03-24.md` 기준으로, Quant 쪽에서 반영된 법적 규제 대응 사항을 QuantService 쪽에서 후속 반영할 수 있도록 정리한 최신 handoff 문서다.

## 1. 이번 변경의 목적

이번 변경의 목적은 사용자에게 노출되는 데이터와 문구가 `1:1 투자자문`, `개인 맞춤 추천`, `매수/매도 권유`로 읽히지 않도록 정리하는 것이다.

따라서 QuantService는 이제부터:
- `추천` 중심 표현이 아니라
- `공개 규칙 기반 모델`, `기준일 모델 구성`, `모델 스냅샷`, `산출 배경`
기준으로 화면 문구를 수정해야 한다.

## 2. Quant 쪽에서 이미 반영된 내용

### 2-1. canonical snapshot 파일명 변경

기존 canonical 파일:
- `D:\Quant\service_platform\web\public_data\current\user_recommendation_report.json`

현재 canonical 파일:
- `D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json`

주의:
- 기존 `user_recommendation_report.json` 은 current 경로에서 제거됐다.
- 새 코드는 반드시 `user_model_snapshot_report.json` 기준으로 맞춘다.

### 2-2. 새 API 경로 추가

새 canonical API:
- `GET /api/v1/model-snapshots/today`
- `GET /api/v1/model-snapshots/{service_profile}`

legacy 호환 API는 아직 남아 있지만, 새 개발 기준은 위 경로를 우선 사용한다.

### 2-3. compliance metadata 추가

아래 파일들에는 `compliance_metadata`가 포함된다.
- `user_model_catalog.json`
- `user_model_snapshot_report.json`
- `user_performance_summary.json`
- `user_recent_changes.json`

핵심 필드:
- `content_class`
- `is_personalized_advice`
- `is_one_to_one_advisory`
- `is_actual_trade_instruction`
- `data_basis`

중요:
- `is_personalized_advice` 는 항상 `false`
- `is_one_to_one_advisory` 는 항상 `false`
- `is_actual_trade_instruction` 는 항상 `false`

## 3. QuantService에서 반드시 수정해야 하는 사항

### 3-1. 데이터 소스 경로 교체

기존:
- `user_recommendation_report.json`

현재:
- `user_model_snapshot_report.json`

적용 대상:
- today 화면
- 모델 상세 화면
- 관련 mock adapter
- API client mapping

### 3-2. API 경로 교체

기존 우선 경로:
- `/api/v1/recommendation/today`
- `/api/v1/recommendation/{service_profile}`

현재 우선 경로:
- `/api/v1/model-snapshots/today`
- `/api/v1/model-snapshots/{service_profile}`

주의:
- legacy route는 당분간 남아 있어도, 새 구현/수정은 canonical route 기준으로 맞춘다.

### 3-3. 사용자 노출 문구 수정

사용자 화면에서 아래 표현은 사용하지 않는다.
- 추천
- 오늘의 추천
- 추천 포트폴리오
- 추천 이유
- 개인 맞춤
- 성향별 추천
- 매수 추천
- 매도 추천
- 권유
- 적합한 투자자
- 유리한 포트폴리오

대체 표현 기준:
- `오늘의 추천` -> `오늘의 모델 정보` 또는 `기준일 모델 정보`
- `추천 포트폴리오` -> `기준일 모델 구성`
- `추천 이유` -> `산출 배경`
- `현재 추천 모델` -> `현재 기준 모델`
- `투자자 성향` -> `모델 프로필`
- `적합한 투자자` -> `참고 이용자 유형` 또는 `reference usage context`

### 3-4. 화면별 문구 변경 가이드

#### today 화면
기존 표현 예:
- 오늘의 추천
- 현재 추천 모델
- 추천 포트폴리오
- 추천 이유

변경 권장:
- 오늘의 모델 정보
- 현재 기준 모델
- 기준일 모델 구성
- 산출 배경

#### model detail 화면
기존 표현 예:
- 이 모델이 적합한 투자자
- 추천 이유

변경 권장:
- 참고 이용자 유형
- 산출 배경

#### changes 화면
기존 표현 예:
- 추천 변경
- 추천 사유

변경 권장:
- 모델 구성 변경
- 변경 기준

## 4. 구조 관련 주의사항

### 4-1. 웹 snapshot은 flat field 유지

원본 report 내부에서는 아래 canonical key가 사용된다.
- `model_overview`
- `model_portfolio`
- `model_rationale`
- `model_changes`
- `current_model_label`
- `summary_basis`
- `reference_response`

하지만 QuantService가 직접 읽는 web snapshot(`user_model_snapshot_report.json`)은 계속 아래 flat field를 제공한다.
- `summary_text`
- `allocation_items`
- `rationale_items`
- `change_log`
- `market_view`
- `risk_level`
- `performance_summary`
- `disclaimer_text`

즉 QuantService는 원칙적으로:
- 파일명과 API 경로는 바꾸되
- snapshot 내부 flat field는 그대로 소비하면 된다.

### 4-2. recent changes 구조

이전과 동일하게 객체 배열 구조를 유지한다.

필드:
- `display_name`
- `security_code`
- `delta_weight`
- `direction`

문자열 파싱 방식으로 되돌리지 않는다.

### 4-3. 종목 코드 표시

`allocation_items[].security_code` 는 계속 사용한다.

규칙:
- 주식/ETF: 6자리 문자열
- 현금성 row: `null`
- 숫자형 변환 금지

## 5. stale / manifest 처리

아래 파일을 기준으로 stale-data 표시를 유지한다.
- `D:\Quant\service_platform\web\public_data\current\publish_manifest.json`

이번 버전에서 주요 변경:
- `files` 목록이 `user_model_snapshot_report.json` 기준으로 갱신됨
- `version` 은 `v2`
- `compliance_note` 추가됨

가능하면 QuantService는 `compliance_note`를 내부 로그/디버그 용도로만 사용하고, 일반 사용자 화면에는 과도하게 노출하지 않는다.

## 6. 성능/표시 정책 유지사항

이번 compliance 작업 이후에도 아래 정책은 그대로 유지한다.

### 성능 노출 순서
- `1Y`
- `2Y`
- `3Y`
- `6M`
- `3M`

### 사용자 화면 비노출
- `5Y`
- `FULL`

### 짧은 기간 표시 원칙
- `3M`, `6M` 는 `CAGR`보다 `total_return` 중심

### MDD 해석
- 동일 급락 구간이 겹치면 `3M / 6M / 1Y` MDD가 같게 보일 수 있음
- 계산 오류로 간주하지 않음

## 7. QuantService에서 하지 말아야 할 것

- Quant payload를 기반으로 투자 권유 문구를 다시 만들지 말 것
- `추천`, `권유`, `개인 맞춤` 표현을 다시 넣지 말 것
- `is_personalized_advice=false` 인 payload를 화면에서 상담/자문처럼 재해석하지 말 것
- raw DB를 직접 읽어 사용자별 맞춤 문구를 만들지 말 것
- 매수/매도 행동 문구를 추가하지 말 것

## 8. 우선 반영 순서

1. data source를 `user_model_snapshot_report.json` 으로 교체
2. API route를 `/api/v1/model-snapshots/...` 로 교체
3. today / detail / changes 화면의 문구 교체
4. `reference_usage_context` 와 `compliance_metadata` 반영
5. legacy recommendation wording 제거 여부 전수 점검
6. stale-data / manifest 확인

## 9. 참고 파일

- `D:\Quant\docs\QUANT_Codex_작업지시문_2026-03-24.md`
- `D:\Quant\docs\QUANTSERVICE_WEBSERVICE_UPDATE_HANDOFF_20260323.md`
- `D:\Quant\docs\QUANT_TO_QUANTSERVICE_API_SPEC_20260318.md`
- `D:\Quant\docs\QUANTSERVICE_SCREEN_FIELD_MAPPING_20260318.md`
- `D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json`
