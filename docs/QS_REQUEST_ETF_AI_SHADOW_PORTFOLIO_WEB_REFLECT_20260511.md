# QS 작업요청서: ETF AI Shadow Portfolio 웹 반영

## 요청 목적

Quant에서 신규 생성한 ETF 전용 AI shadow portfolio 데이터를 QS admin 웹의 `AI 학습 모델` 메뉴에서 조회할 수 있도록 반영 요청합니다.

이번 요청은 public 추천/배분 반영이 아니라 **admin-only shadow 관찰용**입니다.

## 배경

ETF 전용 AI는 주식 AI와 별도 트랙으로 개발 중입니다.

현재 ETF AI 구조는 아래 2개 컴포넌트 모델을 조합합니다.

| 구분 | model_code | 한글명 | 역할 | quality gate |
|---|---|---|---|---|
| 역할 선택 | `AI-ETF-ROLE-ALLOCATION-V01` | ETF역할배분AI | 시장국면별 유리한 ETF 역할군 선택 | `no_watch_plus` |
| 비중 템플릿 | `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01` | ETF비중템플릿AI | 역할별 비중 템플릿 선택 | `aum_p20` |

웹에 표시할 대표 portfolio model은 아래 코드입니다.

| 항목 | 값 |
|---|---|
| model_code | `AI-ETF-SHADOW-PORTFOLIO-V01` |
| model_name_ko | `ETF전용포트폴리오AI` |
| model_role | `etf_shadow_portfolio` |
| status | `shadow_observation` |
| visibility | `admin_only` |

## Quant 제공 파일

QS에서 가져갈 current payload는 아래 파일입니다.

```text
D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json
D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json
```

보조 산출물은 아래 경로에 있습니다.

```text
D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_holdings_20260508.csv
D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_backtest_20260508.csv
D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_20260508.json
D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_20260508.md
```

## 웹 반영 요청사항

### 1. AI 학습 모델 목록 반영

QS admin `AI 학습 모델` 메뉴에서 `AI-ETF-SHADOW-PORTFOLIO-V01 / ETF전용포트폴리오AI`가 보이도록 반영해 주세요.

통합 index payload:

```text
D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json
```

해당 payload의 `models[]`에 아래 모델이 포함되어 있습니다.

```json
{
  "model_code": "AI-ETF-SHADOW-PORTFOLIO-V01",
  "model_name_ko": "ETF전용포트폴리오AI",
  "model_role": "etf_shadow_portfolio",
  "status": "shadow_observation"
}
```

### 2. ETF AI 상세 payload 연결

상세 화면 또는 확장 패널에서 아래 payload를 읽어 표시해 주세요.

```text
D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json
```

주요 표시 권장 필드:

- `model_code`
- `model_name_ko`
- `status`
- `as_of_date`
- `component_models`
- `current_decision`
- `backtest_summary`
- `current_holdings`
- `current_role_scores`
- `current_template_scores`
- `policy`

### 3. 현재 Shadow 판단 표시

`current_decision` 영역에서 아래 항목을 표시해 주세요.

| 필드 | 의미 |
|---|---|
| `regime_mode` | 현재 시장 모드 |
| `selected_role` | 역할 선택 AI가 선택한 역할 |
| `selected_role_prob` | 선택 역할 확률 |
| `selected_template` | 비중 템플릿 AI가 선택한 템플릿 |
| `selected_template_prob` | 선택 템플릿 확률 |
| `mode_default_template` | rule-based 기본 템플릿 |

2026-05-08 기준 예시:

| 항목 | 값 |
|---|---|
| 시장 모드 | `neutral` |
| 선택 역할 | `CORE_BETA` |
| 선택 역할 확률 | `0.54337` |
| 선택 템플릿 | `ON_THEME_TILT` |
| 선택 템플릿 확률 | `0.376965` |
| 기본 템플릿 | `NEUTRAL_BALANCED` |

### 4. Backtest Summary 표시

`backtest_summary`를 표로 표시해 주세요.

권장 컬럼:

- `variant`
- `observations`
- `avg_1m_ret`
- `median_1m_ret`
- `win_rate`
- `avg_1m_mdd`
- `avg_1m_risk_adj`
- `worst_1m_ret`
- `compounded_validation_return`

2026-05-08 기준 핵심 결과:

| variant | avg 1M ret | win rate | avg risk adj | worst 1M |
|---|---:|---:|---:|---:|
| `role_ai_no_watch_plus_top1` | 4.69% | 70.37% | 2.43% | -35.13% |
| `template_ai_aum_p20_top1` | 4.13% | 62.96% | 2.35% | -15.42% |
| `mode_default_aum_p20` | 2.27% | 66.67% | 0.95% | -3.97% |

주의:

- `template_ai_aum_p20_top1`을 주 관찰 variant로 표시해 주세요.
- `mode_default_aum_p20`은 비교 baseline입니다.
- `role_ai_no_watch_plus_top1`은 역할 판단 보조 관찰용입니다.

### 5. Current Holdings 표시

`current_holdings`를 ETF shadow portfolio 구성 종목으로 표시해 주세요.

권장 컬럼:

- `variant`
- `role_key`
- `ticker`
- `name`
- `holding_weight`
- `role_weight`
- `source`

주의:

- 동일 payload 안에 여러 variant가 들어 있습니다.
- 기본 표시 variant는 `template_ai_aum_p20_top1`로 해 주세요.
- 사용자가 선택하면 `role_ai_no_watch_plus_top1`, `mode_default_aum_p20`도 비교할 수 있으면 좋습니다.

### 6. Component Model 표시

`component_models`에서 각 하위 모델의 성능을 표시해 주세요.

권장 표시:

- model_code
- model_name_ko
- role
- quality_gate
- evaluation.auc
- evaluation.train_rows
- evaluation.valid_rows
- evaluation.valid_dates

현재 값:

| model_code | quality_gate | AUC |
|---|---|---:|
| `AI-ETF-ROLE-ALLOCATION-V01` | `no_watch_plus` | 0.605467 |
| `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01` | `aum_p20` | 0.910138 |

## 운영 정책

이 ETF AI는 현재 **admin-only shadow 관찰 단계**입니다.

QS 웹에서는 아래 정책을 명확히 표시해 주세요.

- public 추천 모델에 반영하지 않음
- 실제 ETF 포트폴리오 교체/추천에 사용하지 않음
- 최소 4~8주 live shadow 성과 관찰 후 운영 반영 여부 판단
- ETF는 주식 AI와 별도 모델 트랙으로 관리

payload 내 정책 필드:

```json
{
  "operating_stage": "admin_only_shadow",
  "public_recommendation_use": "disabled",
  "primary_shadow_variant": "template_ai_aum_p20_top1",
  "role_gate": "no_watch_plus",
  "template_gate": "aum_p20",
  "tail_risk_guard_candidates": ["tracking_gap_p90", "quality_combo"]
}
```

## 배포/수집 관련 요청

QS 쪽 데이터 수집 또는 배포 루틴에서 아래 파일을 admin current 대상으로 가져가도록 반영해 주세요.

```text
etf_ai_shadow_portfolio_current.json
```

권장 원격 object path:

```text
admin/current/etf_ai_shadow_portfolio_current.json
```

기존 `ai_learning_models_current.json`도 함께 갱신되어 있으므로, AI 학습 모델 목록은 이 파일을 기준으로 갱신하면 됩니다.

## 검증 요청

QS 반영 후 아래를 확인해 주세요.

1. `AI 학습 모델` 메뉴에 `ETF전용포트폴리오AI`가 표시되는지
2. status가 `shadow_observation`으로 표시되는지
3. `current_decision`이 정상 표시되는지
4. `backtest_summary`의 null/NaN 값이 `0%`가 아니라 `N/A` 또는 빈 값으로 표시되는지
5. 기본 holdings view가 `template_ai_aum_p20_top1` variant를 기준으로 표시되는지
6. public 추천 화면에는 노출되지 않는지

## Quant 측 참고

Quant에서는 QS 코드를 직접 수정하지 않습니다.

QS 반영이 필요한 작업은 본 작업요청서를 기준으로 QS 쓰레드에서 처리해 주세요.
