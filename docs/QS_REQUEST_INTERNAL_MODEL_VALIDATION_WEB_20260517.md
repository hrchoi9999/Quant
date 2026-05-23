# QS 작업요청서: 내부용 모델 검증 섹션 추가

## 요청 목적

redbot.co.kr admin의 `내부용 모델` 페이지 하단에 `내부용 모델 검증` 섹션을 추가해 주세요.

목표는 운영 중인 내부 모델별로 다음을 한 화면에서 비교하는 것입니다.

- 모델별 성능 목표 또는 기준치
- 검증일 기준 현재 성능치
- 기준 충족 여부
- 권고 조치: 유지 / 관찰 / 재검토 / 보정 또는 중단 후보

모델 검증은 매일 정책을 바꾸기 위한 기능이 아닙니다. **주말 1회 검증**을 원칙으로 하고, 검증 결과에 따라 다음 주에 모델 보정/수정/중단 여부를 검토합니다.

## Quant 제공 데이터

신규 payload:

```text
D:\Quant\service_platform\web\admin_data\current\internal_model_validation_current.json
```

누적 history payload:

```text
D:\Quant\service_platform\web\admin_data\current\internal_model_validation_history.json
```

주차별 snapshot:

```text
D:\Quant\reports\internal_model_validation\internal_model_validation_YYYYMMDD.json
```

생성 스크립트:

```text
D:\Quant\scripts\build_internal_model_validation_current.py
```

운영 반영:

- `research_full` pipeline에서 생성되도록 연결했습니다.
- daily_light에서는 매일 재생성하지 않습니다.
- 주말 또는 정기 검증일에 `research_full` 실행 후 최신화하는 구조입니다.
- 같은 검증일을 재실행하면 history는 중복 append하지 않고 해당 검증일 row를 교체합니다.

## Payload 주요 구조

```json
{
  "source_name": "internal_model_validation_current",
  "schema_version": "2026-05-17.v3",
  "visibility": "admin_only",
  "page_target": "admin_internal_models",
  "section_title_ko": "내부용 모델 검증",
  "as_of_date": "2026-05-15",
  "review_schedule": {...},
  "decision_policy": {...},
  "metric_definitions": {...},
  "summary": {...},
  "models": [...]
}
```

History payload 주요 구조:

```json
{
  "source_name": "internal_model_validation_history",
  "schema_version": "2026-05-17.v1",
  "history_grain": "weekly_model_validation_by_model",
  "dedupe_key": ["validation_asof_date", "model_code"],
  "summary": {...},
  "history": [...]
}
```

History row 핵심 필드:

- `validation_asof_date`
- `model_code`
- `review_state`
- `recommended_action`
- `total_score`
- `grade`
- `profitability_score`
- `risk_score`
- `consistency_score`
- `model_value_score`
- `backtest_reference_score`
- `score_basis`
- `backtest_reference_only`
- `backtest_1y_return`
- `backtest_mdd_1y`
- `backtest_sharpe_1y`
- `live_1m_sample_count`
- `sample_confidence`
- `live_1m_avg_return`
- `live_1m_win_rate`
- `qualitative_assessment_ko`

모델 row 핵심 필드:

- `scope`: `internal_models` 또는 `tseries_models`
- `model_code`
- `display_name`
- `model_profile`
- `review_state`
- `recommended_action`
- `review_reasons`
- `validation_score`
- `qualitative_assessment_ko`
- `target`
- `current_backtest_metrics`
- `current_live_metrics`
- `metric_checks`
- `supporting_validation`

## 표시 위치

`내부용 모델` 페이지 하단에 기존 내부용 모델 블록들과 같은 카드형 UI로 추가해 주세요.

권장 구성:

1. 상단 요약
   - 검증 기준일: `as_of_date`
   - 모델 수: `summary.model_count`
   - 상태별 개수: `summary.by_review_state`
   - 조치 필요 모델 수: `summary.action_required_count`

2. 모델별 카드
   - 모델명: `display_name` / `model_code`
   - 상태 badge: `review_state`
   - 권고 조치: `recommended_action`
   - 종합 검증 점수: `validation_score.total_score`
   - 등급: `validation_score.grade`
   - 등급 기준: `validation_score.grade_rule`
   - 점수 기준: `validation_score.score_basis`
   - 표본 신뢰도: `current_live_metrics.sample_confidence`
   - 정성평가: `qualitative_assessment_ko`
   - 판정 사유: `review_reasons`
   - 성능 목표: `target`
   - 현재 백테스트 성능: `current_backtest_metrics`
   - 현재 live 성능: `current_live_metrics`
   - 지표별 통과 여부: `metric_checks`

3. Historical 평가
   - `internal_model_validation_history.json`의 `history`를 사용해 모델별 점수/등급 추이를 표시해 주세요.
   - 기본 표시: 최근 8회 검증 이력
   - 추천 차트: `total_score`, `grade`, `review_state`
   - 추천 표: 검증일, 점수, 등급, 상태, 권고조치, 핵심 사유

## 상태 표시 기준

`review_state` 표시 문구:

- `PASS`: 기준 충족, 현행 운영 유지
- `WATCH`: live-first 점수 85점 이상 90점 미만, 다음 주말 재검증
- `REVIEW`: live-first 점수 85점 미만, 보정/강등/중단 후보 검토 필요

`recommended_action` 표시 문구:

- `MAINTAIN`: 유지
- `KEEP_OBSERVING`: 관찰 지속
- `REVIEW_NEXT_WEEK`: 다음 주 재검토
- `MODEL_REVIEW_OR_DOWNGRADE_CANDIDATE`: 보정/강등/중단 후보 검토

## 지표 표시 가이드

퍼센트 표기 대상:

- `trailing_1m`, `trailing_3m`, `trailing_6m`, `trailing_1y`
- `itd_return`, `cagr`, `mdd_1y`
- `current_avg_return`, `current_win_rate`, `current_avg_mdd`
- `one_month_avg_return`, `one_month_win_rate`, `one_month_avg_mdd`
- `metric_checks[].actual`
- `metric_checks[].target`

점수 표기 대상:

- `validation_score.total_score`
- `validation_score.profitability_score`
- `validation_score.risk_score`
- `validation_score.consistency_score`
- `validation_score.model_value_score`
- `validation_score.backtest_reference_score`

등급 표시 기준:

- `S`: 95점 이상
- `A`: 90점 이상
- `B`: 85점 이상
- `C`: 85점 미만

정성평가:

- `qualitative_assessment_ko`를 모델 카드 하단에 표시해 주세요.
- 50단어 이내의 객관적·보수적·냉정한 평가입니다.
- `REVIEW` 모델은 정성평가와 `review_reasons`를 함께 강조해 주세요.

표기 예:

- `0.184369` → `18.44%`
- `-0.207798` → `-20.78%`
- null → `N/A`

중요:

- null을 `0%`로 표시하지 말아 주세요.
- live 표본이 적어도 점수는 그대로 표시하되 `current_live_metrics.sample_confidence`를 함께 표시해 주세요.
- `backtest`와 `live`는 성격이 다르므로 UI에서 구분해 주세요.
- v3에서는 backtest가 참고 점수이며 실운영 평가보다 우선하지 않습니다.

## 검증 포인트

QS 반영 후 확인할 항목:

1. `internal_model_validation_current.json`을 정상 로딩한다.
2. `내부용 모델` 페이지 하단에 `내부용 모델 검증` 섹션이 표시된다.
3. 모델별 카드가 11개 표시된다. 현재 기준:
   - internal_models: S2, S2_PIT_V01, S3, S3_ACCEL_V01, S3_CORE2, S4, S5, S6, I-STOCK-STRONG-RSI-V01
   - tseries_models: T-STOCK-V01, T-ETF-V01
4. 상태 요약이 표시된다. 2026-05-15 기준:
   - PASS: 5
   - WATCH: 1
   - REVIEW: 5
5. `N/A`가 0%로 보이지 않는다.
6. `REVIEW` 모델은 별도 강조된다.
7. `validation_score.total_score`, `validation_score.grade`, `validation_score.grade_rule`, `review_reasons`가 표시된다.
8. `qualitative_assessment_ko`가 모델별로 표시된다.
9. `internal_model_validation_history.json`을 로딩해 모델별 historical 평가가 표시된다.
10. 같은 검증일 재실행 시 history row가 중복 표시되지 않는다.
11. 주말 1회 검증 원칙이 화면에 짧게 표시된다.

## v3 평가 관점

v3는 live-first 평가입니다. 표본 수가 적어도 동일한 틀로 점수를 계산하고, 표본 부족은 별도 `sample_confidence`로만 표시합니다.

- Live 1M 평균수익률: 35%
- Live 현재수익률: 15%
- Live 1M Win rate: 15%
- Live 1M MDD: 15%
- 모델효용: 10%
- 백테스트 참고 점수: 10%

추가 지표:

- `model_value_score`: 모델 자체 효용 점수
- `backtest_reference_score`: 백테스트 참고 점수
- `total_validation_score`: live-first v3 종합 점수
- `sample_confidence`: high / medium / low
- `grade`: S는 95점 이상, A는 90점 이상, B는 85점 이상, C는 85점 미만
- `qualitative_assessment_ko`: Quant 쓰레드가 작성한 50단어 이내의 객관적·보수적·냉정한 정성 평가
- `confirmed_t10_hit_rate`: T-STOCK confirmed 후보가 실제 T10 이상 성과군에 들어간 비율
- `confirmed_avg_excess_vs_all_1m`: T-STOCK confirmed 후보의 1개월 평균 초과수익률

주의:

- 백테스트 성과는 참고 지표이며 live 평가보다 우선하지 않습니다.
- 표본 수가 적어도 `INSUFFICIENT_LIVE_SAMPLE` 상태로 분리하지 않습니다.
- 표본 신뢰도는 `sample_confidence`로 표시합니다.
- `review_reasons`를 같이 표시해야 사용자가 판정 이유를 이해할 수 있습니다.

## 운영 원칙

- 이 섹션은 admin-only입니다.
- 일반 사용자 페이지에는 노출하지 않습니다.
- 모델 보정/수정/중단 판단은 주말 정기 검증 기준으로만 수행합니다.
- 평일 daily update에서는 성과 표시만 보고, 특별한 데이터 오류가 없으면 모델 정책을 변경하지 않습니다.
