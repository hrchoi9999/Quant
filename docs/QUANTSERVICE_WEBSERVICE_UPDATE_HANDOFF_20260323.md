# Quant -> QuantService 웹서비스 수정 작업지시서 (2026-03-23)

이 문서는 `D:\Quant` 쪽에서 최근 반영된 사용자용 snapshot / API / 성능지표 / ETF 백테스트 구간 확장 내용을 기준으로, `QuantService` 쓰레드에서 수정해야 할 내용을 정리한 handoff 문서다.

## 1. 이번 변경의 핵심

이번 변경으로 아래가 달라졌다.

1. 사용자 모델명은 `안정형 / 균형형 / 성장형 / 자동전환형`으로 고정한다.
2. 포트폴리오 종목 항목에 `security_code`가 포함된다.
3. recent changes는 문자열 배열이 아니라 구조화 객체 배열이다.
4. 사용자용 성능 데이터는 `stable / balanced / growth / auto`별로 분리된다.
5. ETF 모델 `S4 / S5 / S6`의 비교 구간이 `2023-06-08 ~ 2026-03-20` 기준으로 확장 반영됐다.
6. Router / model comparison / user report / web snapshot도 같은 기준으로 다시 생성됐다.
7. 성능지표 표시 정책은 `1Y`를 메인으로 하고, `5Y / FULL`은 사용자 화면에서 제외한다.

## 2. 계속 사용할 데이터 경로

아래 경로는 그대로 사용한다.

- `D:\Quant\service_platform\web\public_data\current\publish_manifest.json`
- `D:\Quant\service_platform\web\public_data\current\user_model_catalog.json`
- `D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json`
- `D:\Quant\service_platform\web\public_data\current\user_performance_summary.json`
- `D:\Quant\service_platform\web\public_data\current\user_recent_changes.json`

API 골격은 아래를 사용할 수 있다.

- `GET /api/v1/manifest`
- `GET /api/v1/user-models`
- `GET /api/v1/model-snapshots/today`
- `GET /api/v1/model-snapshots/{service_profile}`
- `GET /api/v1/performance/summary`
- `GET /api/v1/changes/recent`

## 3. 반드시 반영해야 하는 프론트 수정사항

### 3-1. 사용자 모델명

사용자 화면에서는 아래 이름만 사용한다.

- `안정형`
- `균형형`
- `성장형`
- `자동전환형`

`Redbot 안정형` 같은 옛 이름은 더 이상 쓰지 않는다.

### 3-2. 포트폴리오 종목 코드 표시

`allocation_items[]`에는 아래 필드가 있다.

- `security_code: string | null`

규칙:

- 주식 / ETF는 항상 6자리 문자열
- 예: `005930`, `069500`, `192720`, `459580`
- 현금성 row만 `null` 허용
- 숫자형으로 변환 금지
- 앞자리 `0` 유지 필수

렌더링 예시:

- `삼성전자 (005930)`
- `KODEX 200 (069500)`
- `현금/대기자금` (`security_code == null`이면 코드 생략)

### 3-3. recent changes 구조 변경

기존:

- `increase_items[]`, `decrease_items[]` = 문자열 배열

현재:

- `increase_items[]`, `decrease_items[]` = 객체 배열

구조 예시:

```json
{
  "display_name": "파워 고배당저변동성",
  "security_code": "192720",
  "delta_weight": 0.019145,
  "direction": "increase"
}
```

필드:

- `display_name: string`
- `security_code: string | null`
- `delta_weight: number`
- `direction: "increase" | "decrease"`

프론트 규칙:

- 문자열 split/parsing 로직 제거
- `delta_weight`는 UI에서 `%`로 포맷팅
- `direction`으로 증가/감소 스타일 분리
- `security_code`가 있으면 종목명 옆에 같이 표시

## 4. 포트폴리오 노출 방식 변경

기존처럼 하나의 통합 상위 종목 리스트만 보여주지 말고, 아래 순서로 보여주는 것을 권장한다.

1. sleeve 요약
   - 주식 sleeve 비중
   - ETF sleeve 비중
   - 현금성 비중
2. 주식 상위 종목
3. ETF 상위 종목
4. 현금성 자산

이유:

- `stable / balanced / growth / auto`는 종목 단위 상위 리스트만 보면 ETF가 비슷하게 반복되어 보일 수 있다.
- 실제 차이는 sleeve 비중과 주식 모델 선택에서 나타난다.
- 특히 `growth`는 현재 neutral / risk_on 구간에서 최근 1Y CAGR이 더 높은 성장형 주식 모델(`S3` 또는 `S3_CORE2`)을 사용한다.
- 현재 기준으로는 `S3`가 선택되므로, 성장형은 이전보다 주식 sleeve 색깔이 더 강한 것이 정상이다.

## 5. 성능지표 표시 정책

### 5-1. 사용자 화면에 노출할 기간

사용자 화면에서는 아래 기간만 노출한다.

- `1Y`
- `2Y`
- `3Y`
- `6M`
- `3M`

사용자 화면에서 **제외할 기간**:

- `5Y`
- `FULL`

`5Y`, `FULL`은 내부 참고자료로만 남기고, 사용자용 웹 화면에서는 표시하지 않는다.

### 5-2. 노출 우선순위

성능지표 노출 우선순위는 반드시 아래 순서를 따른다.

1. `1Y` (메인 지표)
2. `2Y`
3. `3Y`
4. `6M`
5. `3M`

권장 UI 규칙:

- headline 성과 카드는 `1Y` 기준
- `2Y`, `3Y`는 중기 참고 지표
- `6M`, `3M`은 최근 장세 확인용 보조 지표
- `5Y`, `FULL`은 사용자 화면 비노출

### 5-3. 지표별 표시 방식

권장 표시 방식:

- `1Y`: `CAGR`, `MDD`, `Sharpe`
- `2Y`: `CAGR`, `MDD`, `Sharpe`
- `3Y`: `CAGR`, `MDD`, `Sharpe`
- `6M`: `total_return`, `MDD`, `Sharpe`
- `3M`: `total_return`, `MDD`, `Sharpe`

중요:

- `3M`, `6M`은 `CAGR`보다 `total_return`을 메인으로 보여준다.
- 짧은 기간 CAGR은 체감상 과장되어 보일 수 있으므로 headline으로 쓰지 않는다.

payload 참고 필드:

- `performance_cards.primary_period`
- `performance_cards.cagr`
- `performance_cards.total_return`
- `performance_cards.mdd`
- `performance_cards.sharpe`
- `period_table[].period`
- `period_table[].total_return`
- `period_table[].cagr`
- `period_table[].mdd`
- `period_table[].sharpe`

## 6. MDD 해석 관련 주의사항

기간별 MDD가 여러 구간에서 같은 값으로 보일 수 있다.

이유:

- 최근의 동일한 급락 이벤트가 `3M / 6M / 1Y`에 모두 포함되면, 각 기간의 MDD가 동일하게 계산될 수 있다.
- 이것은 현재 기준으로는 계산 버그가 아니라 자연스러운 결과일 수 있다.

프론트 표시 원칙:

- MDD가 여러 기간에서 같아도 오류로 간주하지 말 것
- 필요하면 도움말 문구 또는 툴팁으로 설명할 것

권장 설명 문구:

- `최근 동일한 급락 구간이 여러 기간에 공통으로 포함되어 최대낙폭(MDD)이 같은 값으로 보일 수 있습니다.`

즉, 이번 수정에서 MDD 계산 로직을 프론트에서 바꾸는 게 아니라, **표시와 해석을 보수적으로 가져가는 것**이 핵심이다.

## 7. ETF 백테스트 구간 확장 관련 이해사항

ETF 모델 `S4 / S5 / S6`은 이제 `2023-06-08 ~ 2026-03-20` 기준으로 다시 생성됐다.

주의사항:

- `S5`는 `covered_call` 대표 ETF가 `2024-12-03` 상장이라서, `2023-06-08 ~ 2024-12-02` 구간에는 일부 비중이 현금/대체 규칙으로 처리될 수 있다.
- 따라서 초기 구간의 S5 성격은 현재 시점과 완전히 동일하지 않을 수 있다.
- 그래도 사용자 관점에서는 이전 `2024-01-02` 시작보다 비교 가능 구간이 더 합리적이다.

프론트에서 별도 복잡한 설명을 강하게 노출할 필요는 없지만, 내부적으로는 이 차이를 알고 있어야 한다.

## 8. 오케스트레이션 관련 이해사항

현재 일일 배치에는 아래가 포함된다.

- 주식 / ETF 데이터 업데이트
- `S2 / S3 / S3 core2 / S4 / S5 / S6` 백테스트
- `stable / balanced / growth / auto` Router 실행
- model comparison 생성
- user report 생성
- web snapshot 생성
- web snapshot validate
- Google Sheets 업로드

즉 QuantService는 별도 수동 export를 기다리지 말고, 배치 완료 후 최신 snapshot/API를 읽는 구조로 보면 된다.

## 9. QuantService에서 하면 안 되는 것

- `S2/S3/S4/S5/S6/Router` 계산 재실행
- CAGR / MDD / Sharpe 재계산
- 종목코드 재정규화
- recent changes 문자열 파싱 복원
- raw DB 직접 조인
- `5Y / FULL`을 프론트에서 다시 꺼내 사용자에게 노출

QuantService는 Quant가 만든 user-facing payload를 그대로 소비하는 것이 원칙이다.

## 10. 반영 우선순위

1. 모델명 교체
2. `security_code` 렌더링 추가
3. recent changes 객체 배열 렌더링으로 수정
4. 포트폴리오를 sleeve 중심으로 재배치
5. 성능 화면을 `1Y > 2Y > 3Y > 6M > 3M` 우선순위로 재배치
6. `5Y / FULL` 비노출 처리
7. MDD 설명 툴팁 또는 도움말 문구 추가
8. `publish_manifest.json` 기준 stale-data 표시 연결

## 11. 관련 참고 문서

- `D:\Quant\docs\QUANT_TO_QUANTSERVICE_API_SPEC_20260318.md`
- `D:\Quant\docs\QUANTSERVICE_SCREEN_FIELD_MAPPING_20260318.md`
- `D:\Quant\docs\QUANTSERVICE_IMPLEMENTATION_BRIEF_20260318.md`
- `D:\Quant\docs\DAILY_QUANT_BATCH_CHECKLIST_20260320.md`

## 12. 법적 규제 대응 관련 추가 반영사항

이번 배치부터 사용자 노출 payload는 `투자자문`, `개인 맞춤`, `추천`으로 읽히지 않도록 아래 원칙을 따른다.

- canonical payload 파일명은 `user_model_snapshot_report.json` 이다.
- `추천` 대신 `기준일 모델`, `공개 규칙 기반 모델`, `모델 스냅샷`, `산출 배경` 표현을 사용한다.
- 세부 원본 report key도 아래 기준으로 바뀌었다. 웹 snapshot(`user_model_snapshot_report.json`)은 계속 `summary_text`, `allocation_items`, `rationale_items`, `change_log` 같은 flat field를 제공한다.
  - `recommended_model` -> `model_overview`
  - `recommended_portfolio` -> `model_portfolio`
  - `why_this_portfolio` -> `model_rationale`
  - `changes_since_previous` -> `model_changes`
  - `current_recommendation` -> `current_model_label`
  - `primary_reason` -> `summary_basis`
  - `current_response` -> `reference_response`
- report / snapshot에는 `compliance_metadata`가 포함된다.
- `compliance_metadata.is_personalized_advice` 는 항상 `false` 여야 한다.
- 사용자 화면 문구는 `추천`, `매수 추천`, `매도 추천`, `개인 맞춤`, `성향별 추천` 표현을 사용하지 않는다.

QuantService는 기존 recommendation 명칭 대신 model snapshot 명칭을 우선 사용하고, legacy route나 legacy file name을 새 코드에서 기준으로 삼지 않는다.

