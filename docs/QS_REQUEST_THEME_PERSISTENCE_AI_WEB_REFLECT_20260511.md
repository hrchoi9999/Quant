# QS 작업요청서 - 테마지속성AI 웹 반영

작성일: 2026-05-11

## 목적

QS/redbot admin `AI 학습 모델` 메뉴에서 `AI-THEME-PERSISTENCE-V01 / 테마지속성AI`의 현재 shadow 관찰 상태를 확인할 수 있도록 반영한다.

이 요청은 public 추천 화면 반영이 아니라 admin-only 관찰 화면 반영이다.

## 반영 대상 모델

| 항목 | 값 |
|---|---|
| model_code | `AI-THEME-PERSISTENCE-V01` |
| 한글명 | `테마지속성AI` |
| model_version | `AI-THEME-PERSISTENCE-V01_20260508_001` |
| model_role | `theme_persistence_shadow` |
| as_of_date | `2026-05-08` |
| feature_mode | `BASE` |
| visibility | `admin_only` |

## Quant 제공 payload

QS는 기존 AI 학습 모델 통합 페이지와 동일하게 아래 current payload를 읽으면 된다.

| 용도 | local path | GCS object |
|---|---|---|
| AI 모델 통합 목록 | `D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json` | `admin/current/ai_learning_models_current.json` |
| 테마지속성AI 상세 | `D:\Quant\service_platform\web\admin_data\current\theme_persistence_ai_current.json` | `admin/current/theme_persistence_ai_current.json` |

통합 목록에는 현재 아래 5개 모델이 포함되어 있다.

- `AI-CANDIDATE-VALIDATION-V01`
- `AI-GROWTH-VALUATION-V01`
- `AI-DOWNSIDE-RISK-V01`
- `AI-CANDIDATE-RANK-DELTA-V01`
- `AI-THEME-PERSISTENCE-V01`

## 화면 표시 요청

`AI 학습 모델` 메뉴에서 `테마지속성AI` 카드/탭을 추가한다.

상단 요약:

- model_code
- 한글명
- model_version
- as_of_date
- model_role
- feature_mode
- visibility/admin-only badge

평가 지표:

| head | label | AUC | top30 label rate | bottom30 label rate |
|---|---|---:|---:|---:|
| continue | `label_theme_continue_1m` | 0.714944 | 1.000000 | 0.166667 |
| fade | `label_theme_fade_1m` | 0.772875 | 0.366667 | 0.000000 |

tag count:

| tag | count |
|---|---:|
| `theme_persist_strong` | 3 |
| `theme_persist_watch` | 3 |
| `theme_neutral` | 9 |
| `theme_fade_watch` | 2 |

테마 리스트:

- `top_persistent_themes`: `theme_persistence_score` 높은 순
- `top_fade_risk_themes`: `theme_persistence_score` 낮은 순

권장 컬럼:

- `quant_theme_bucket`
- `theme_name_kr`
- `theme_ret_1w`
- `theme_ret_1m`
- `theme_momentum_score`
- `theme_rotation_score`
- `leading_theme_rank`
- `mapping_confidence`
- `theme_continue_prob`
- `theme_fade_prob`
- `theme_persistence_score`
- `theme_persistence_tag`

## 표시 문구 원칙

테마지속성AI는 종목 매수/매도 신호가 아니다.

권장 설명:

- `theme_persist_strong`: 현재 강한 테마가 다음 1개월 구간에도 상위권을 유지할 가능성이 높은 상태
- `theme_persist_watch`: 지속 가능성은 있으나 강한 확정 신호는 아닌 상태
- `theme_neutral`: 지속/둔화 신호가 뚜렷하지 않은 상태
- `theme_fade_watch`: 테마 순위 둔화 가능성이 있어 관찰이 필요한 상태
- `theme_fade_risk`: 테마 둔화 위험이 높은 상태

금지/주의:

- `theme_persist_strong`을 자동 매수 추천으로 표현하지 않는다.
- `theme_fade_watch` 또는 `theme_fade_risk`를 자동 매도 추천으로 표현하지 않는다.
- public 추천 모델에는 아직 반영하지 않는다.

## 최근 feature 실험 결과 반영 기준

최근 추가 실험:

- QM market/risk/flow context
- rotation acceleration feature
- 테마 내부 종목 품질 feature

판단:

- 위 feature들은 현재 AUC를 개선하지 못했다.
- 따라서 QS 화면에는 운영 feature mode를 `BASE`로 표시한다.
- 실험 feature mode를 운영 feature처럼 표시하지 않는다.

참고 문서:

- `D:\Quant\docs\AI_THEME_PERSISTENCE_V01_DESIGN_20260511.md`

## N/A 처리

값이 `null`, 누락, 빈 문자열이면 `0` 또는 `0%`로 표시하지 말고 `N/A`로 표시한다.

확률/비율 값은 표시 시 percentage 변환 가능:

- 예: `0.714944` -> `71.49%`

단 AUC는 통상 소수점 또는 percentage 중 QS 기존 AI 페이지 표현 방식과 일관되게 표시한다.

## 완료 기준

- admin `AI 학습 모델` 메뉴에서 `테마지속성AI`가 보인다.
- `AI-THEME-PERSISTENCE-V01` 상세에서 continue/fade head별 AUC가 보인다.
- tag count가 보인다.
- persistent/fade risk 테마 리스트가 각각 보인다.
- feature_mode가 `BASE`로 표시된다.
- null 값이 `0%`가 아니라 `N/A`로 표시된다.
- public 추천 화면에는 노출되지 않는다.
