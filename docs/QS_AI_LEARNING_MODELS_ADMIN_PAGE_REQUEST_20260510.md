# QS AI Learning Models Admin Page Request - 2026-05-10

## 목적

QS/redbot admin의 `AI 학습 모델` 메뉴에서 Quant가 생성한 AI 학습 모델 5종의 상태와 shadow tracking 상황을 함께 볼 수 있도록 화면/API를 확장한다.

현재 QS 화면은 메뉴명은 `AI 학습 모델`이지만 실제 구현은 `AI-GROWTH-VALUATION-V01 / 주가수준평가AI` 전용이다. 이제 통합 payload를 기준으로 여러 AI 학습 모델을 표시해야 한다.

## 대상 모델

| model_code | 한글명 | 상태 | 용도 |
|---|---|---|---|
| `AI-CANDIDATE-VALIDATION-V01` | 퀀트후보검증AI | shadow | S/T/I/user/T 후보 검증 |
| `AI-GROWTH-VALUATION-V01` | 주가수준평가AI | shadow/reference | 주가수준, challenger, risk overlay 관찰 |
| `AI-DOWNSIDE-RISK-V01` | 하락위험예측AI | shadow | 하락위험, 비중축소/매도 후보 관찰 |
| `AI-CANDIDATE-RANK-DELTA-V01` | 후보순위조정AI | shadow | 다음 리밸런싱 후보 편출/순위변화 관찰 |
| `AI-THEME-PERSISTENCE-V01` | 테마지속성AI | shadow | 테마 지속/둔화 가능성 관찰 |

## Quant 제공 payload

QS는 GCS `admin/current/` 또는 로컬 fallback에서 아래 파일을 읽으면 된다.

### 통합 목록 payload

| file | GCS path | local fallback |
|---|---|---|
| `ai_learning_models_current.json` | `admin/current/ai_learning_models_current.json` | `D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json` |

역할:

- AI 학습 모델 전체 목록
- 모델별 status, as_of_date, performance_asof_date
- 개별 payload 위치
- 핵심 summary

우선 이 파일을 `AI 학습 모델` 메뉴의 entry point로 사용한다.

### 개별 모델 payload

| model | file | GCS path |
|---|---|---|
| 퀀트후보검증AI | `ai_shadow_observation.json` | `admin/current/ai_shadow_observation.json` |
| 주가수준평가AI | `valuation_ai_challenger_current.json` | `admin/current/valuation_ai_challenger_current.json` |
| 주가수준평가AI | `valuation_ai_challenger_shadow_performance.json` | `admin/current/valuation_ai_challenger_shadow_performance.json` |
| 주가수준평가AI | `valuation_ai_shadow_monitor.json` | `admin/current/valuation_ai_shadow_monitor.json` |
| 하락위험예측AI | `downside_risk_ai_current.json` | `admin/current/downside_risk_ai_current.json` |
| 하락위험예측AI | `downside_risk_ai_shadow_tracker.json` | `admin/current/downside_risk_ai_shadow_tracker.json` |
| 후보순위조정AI | `candidate_rank_delta_ai_current.json` | `admin/current/candidate_rank_delta_ai_current.json` |
| 테마지속성AI | `theme_persistence_ai_current.json` | `admin/current/theme_persistence_ai_current.json` |

## 화면 요구사항

### 1. AI 모델 목록 카드

`ai_learning_models_current.json.models[]`를 사용해 모델 카드 5개를 표시한다.

각 카드 표시 항목:

- 한글명
- model_code
- model_role
- status
- as_of_date
- performance_asof_date
- 핵심 지표

모델별 핵심 지표:

- 퀀트후보검증AI
  - trained_models
  - fallback_models
  - live horizon status
- 주가수준평가AI
  - candidate_count
  - monitor_status
  - performance horizons
- 하락위험예측AI
  - AUC
  - train_rows / valid_rows
  - tag_counts
  - tracker_roles
- 후보순위조정AI
  - model_structure
  - head별 AUC
  - decision_counts
  - drop / retained rank-change target
- 테마지속성AI
  - continue/fade head별 AUC
  - tag_counts
  - top_persistent_themes
  - top_fade_risk_themes

### 2. 모델별 상세 섹션

목록 카드 클릭 또는 탭으로 상세 내용을 전환한다.

권장 탭:

- `퀀트후보검증AI`
- `주가수준평가AI`
- `하락위험예측AI`
- `후보순위조정AI`
- `테마지속성AI`

### 3. 퀀트후보검증AI 상세

입력 payload:

- `ai_shadow_observation.json`

표시 항목:

- common AI / model-specific AI 관찰 상태
- trained model-specific rows
- fallback model rows
- live_summary.horizon_status
- reconstructed_summary
- latest_shadow_sample

주의:

- `live_summary.status == pending_samples`이면 정상 상태로 표시한다.
- 기준일과 성과일이 같거나 충분한 기간이 지나지 않은 경우 1W/2W/1M은 `N/A`가 정상이다.

### 4. 주가수준평가AI 상세

기존 QS 화면을 유지하되, 통합 화면의 한 탭으로 이동한다.

입력 payload:

- `valuation_ai_challenger_current.json`
- `valuation_ai_challenger_shadow_performance.json`
- `valuation_ai_shadow_monitor.json`

표시 항목:

- champion/reference
- QM-THEME challenger
- QM-RISK risk overlay
- 후보별 champion_state, challenger_state, risk_tag
- 1W/2W/1M/2M/3M/6M/1Y shadow 성과

주의:

- 기존 public 추천 모델에 반영하지 않는다.
- QM-RISK는 추천 모델이 아니라 caution tag다.

### 5. 하락위험예측AI 상세

입력 payload:

- `downside_risk_ai_current.json`
- `downside_risk_ai_shadow_tracker.json`

표시 항목:

- model_version
- target label 정의
- AUC
- train_rows / valid_rows
- risk tag 분포
- top_risk_candidates
- tracker_roles
  - `common_champion`
  - `t_stock_specific_challenger`
- tag별 1W/2W/1M shadow 성과

주요 tag:

| tag | 표시명 | 의미 |
|---|---|---|
| `risk_exit_watch` | 매도/비중축소 관찰 | 강한 하락위험 경고 |
| `risk_caution` | 비중축소 검토 | 하락위험 주의 |
| `risk_watch` | 관찰 필요 | 중간 위험 |
| `risk_clear` | 유지 가능 | 낮은 위험 |

주의:

- 현재는 admin-only shadow다.
- `risk_exit_watch`는 자동 매도 신호가 아니다.
- live sample이 없으면 `N/A`로 표시한다. `0%`로 표시하면 안 된다.

### 6. 후보순위조정AI 상세

입력 payload:

- `candidate_rank_delta_ai_current.json`

표시 항목:

- model_version
- model_structure
  - `split_drop_and_retained_rank_change`
- target 정의
- thresholds
- head별 evaluation
  - `drop`
  - `retained_upgrade`
  - `retained_downgrade`
- decision_counts
- top_drop_candidates
- top_upgrade_candidates
- top_downgrade_candidates

주요 tag:

| tag | 표시명 | 의미 |
|---|---|---|
| `rank_drop_candidate` | 편출 후보 | 다음 리밸런싱에서 후보군에서 빠질 가능성 높음 |
| `rank_drop_watch` | 편출 관찰 | 후보군 이탈 가능성 관찰 |
| `rank_upgrade_candidate` | 순위상승 후보 | 잔류 후보 내 순위상승 가능성 높음 |
| `rank_upgrade_watch` | 순위상승 관찰 | 잔류 후보 내 순위상승 가능성 관찰 |
| `rank_hold` | 유지 | 큰 순위변화 가능성 낮음 |
| `rank_downgrade_watch` | 순위하락 관찰 | 잔류 후보 내 순위하락 가능성 관찰 |
| `rank_downgrade_candidate` | 순위하락 후보 | 잔류 후보 내 순위하락 가능성 높음 |

주의:

- `drop`은 매도 신호가 아니라 “다음 리밸런싱 후보군 편출 가능성”이다.
- `retained_upgrade`/`retained_downgrade`는 편출되지 않고 남아 있는 후보 안에서의 순위 변화다.
- 세 head를 하나의 매수/매도 신호처럼 섞어 표시하지 않는다.
- 현재는 admin-only shadow다.

### 7. 테마지속성AI 상세

입력 payload:

- `theme_persistence_ai_current.json`

표시 항목:

- model_version
- target 정의
- thresholds
- head별 evaluation
  - `continue`
  - `fade`
- tag_counts
- top_persistent_themes
- top_fade_risk_themes

주요 tag:

| tag | 표시명 | 의미 |
|---|---|---|
| `theme_persist_strong` | 테마 지속 강함 | 다음 1개월에도 상위 테마 유지 가능성 높음 |
| `theme_persist_watch` | 테마 지속 관찰 | 지속 가능성 관찰 |
| `theme_neutral` | 중립 | 지속/둔화 신호가 뚜렷하지 않음 |
| `theme_fade_watch` | 테마 둔화 관찰 | 테마 순위 둔화 가능성 관찰 |
| `theme_fade_risk` | 테마 둔화 위험 | 테마 둔화 위험 높음 |

주의:

- 테마지속성AI는 종목 매수/매도 신호가 아니다.
- S/T/I/C 후보의 theme overlay 및 향후 Meta AI specialist score로 사용한다.
- 현재는 admin-only shadow다.

## API 요구사항

기존 `/api/v1/admin/valuation-ai`는 valuation 전용이다.

권장 신규 API:

`GET /api/v1/admin/ai-learning-models`

응답 구조:

```json
{
  "source_name": "ai_learning_models_current",
  "as_of_date": "2026-05-08",
  "generated_at": "...",
  "models": [],
  "details": {
    "candidate_validation": {},
    "valuation_ai": {},
    "downside_risk_ai": {},
    "candidate_rank_delta_ai": {},
    "theme_persistence_ai": {}
  },
  "errors": []
}
```

또는 기존 `/api/v1/admin/valuation-ai`를 유지하고, 신규 통합 API를 별도로 추가한다.

## 라우팅 요구사항

기존 메뉴 URL은 유지 가능하다.

- 기존: `/admin/valuation-ai`
- 권장 alias 추가: `/admin/ai-learning-models`

`/admin/valuation-ai`는 backward compatibility로 새 통합 화면을 렌더링해도 된다.

## 데이터 로딩 우선순위

각 파일은 다음 순서로 로드한다.

1. GCS URL
2. QS local current path
3. Quant local fallback path

Quant local fallback 예:

`D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json`

## N/A 처리 원칙

아래 값은 `0`이나 `0%`로 표시하지 않는다.

- sample_count == 0
- avg_return == null
- win_rate == null
- avg_mdd == null
- horizon available false

표시값은 `N/A`로 통일한다.

## 구현 참고

현재 QS 파일:

- `D:\QuantService\service_platform\web\valuation_ai_api.py`
- `D:\QuantService\service_platform\web\templates\admin\valuation_ai.html`
- `D:\QuantService\service_platform\web\app.py`

현재 문제:

- 위 구현은 `valuation_ai_challenger_current.json`, `valuation_ai_challenger_shadow_performance.json`만 읽는다.
- 그래서 `AI-CANDIDATE-VALIDATION-V01`과 `AI-DOWNSIDE-RISK-V01`이 웹에 표시되지 않는다.

필요 작업:

1. `ai_learning_models_current.json` loader 추가
2. 개별 detail payload loader 추가
3. admin template을 통합 모델 목록 + 모델별 detail 구조로 확장
4. 기존 valuation AI 후보/성과 테이블은 `주가수준평가AI` 탭에 유지
5. 테스트 추가
- admin에서 5개 model_code가 모두 보이는지
- 후보순위조정AI split-head 평가와 tag count가 보이는지
- 테마지속성AI continue/fade 평가와 tag count가 보이는지
   - sample_count 0이 `N/A`로 표시되는지
   - 비관리자에게 노출되지 않는지

## 완료 기준

- admin `AI 학습 모델` 페이지에서 5개 모델이 모두 표시된다.
- `퀀트후보검증AI`의 shadow observation 상태가 보인다.
- `주가수준평가AI` 기존 화면 기능이 유지된다.
- `하락위험예측AI`의 AUC, tag count, shadow tracker 상태가 보인다.
- `후보순위조정AI`의 drop/retained rank-change head별 AUC와 tag count가 보인다.
- `테마지속성AI`의 continue/fade head별 AUC와 tag count가 보인다.
- live 성과 미도래 값은 `N/A`로 보인다.
- public 페이지에는 노출되지 않는다.
