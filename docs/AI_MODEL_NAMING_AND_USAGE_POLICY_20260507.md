# AI Model Naming and Usage Policy - 2026-05-07

## Purpose

Quant의 AI 학습모델을 운영 모델과 혼동하지 않도록 model identity, 역할, 활용 범위를 고정한다.

현재 AI 학습모델은 기존 S/T/I/C 모델을 대체하지 않는다. 기존 모델 후보에 보조 score/tag를 붙이고, live-only shadow 성과가 충분히 쌓인 뒤 운영 반영 여부를 판단한다.

## AI Model Layers

| layer | canonical model code | legacy alias | Korean name | role | status |
|---|---|---|---|---|---|
| 1 | `AI-CANDIDATE-VALIDATION-V01` | `AI-OVERLAY-V01` | 퀀트후보검증AI | 기존 S/T/I/user/T 후보가 해당 모델 성격에 맞는지 재평가 | shadow |
| 2 | `AI-GROWTH-VALUATION-V01` | same | 주가수준평가AI | 종목 자체의 성장성 대비 주가수준과 하방위험 평가 | shadow/reference |
| 3 | `AI-DOWNSIDE-RISK-V01` | none | 하락위험예측AI | 신규/보유 후보의 하락위험과 비중축소 관찰 tag 평가 | shadow |
| 4 | `AI-CANDIDATE-RANK-DELTA-V01` | none | 후보순위조정AI | 기존 후보의 승격/강등 후보를 AI score로 관찰 | shadow |

`AI-OVERLAY-V01`은 기존 파일명, 디렉터리명, 일부 과거 리포트에 남아 있는 legacy alias다. 신규 문서, admin 문구, registry, payload의 `model_code`에서는 `AI-CANDIDATE-VALIDATION-V01`을 정식명으로 사용한다.

## Layer 1. AI-CANDIDATE-VALIDATION-V01

### Definition

| item | value |
|---|---|
| canonical model code | `AI-CANDIDATE-VALIDATION-V01` |
| Korean name | `퀀트후보검증AI` |
| legacy alias | `AI-OVERLAY-V01` |
| target | S/T/I/user/T 모델이 이미 선별한 후보 |
| main question | 이 후보가 원 모델의 의도와 실제 성과 패턴에 부합하는가? |
| primary horizon | 1M, live tracking은 1W/2W/1M/2M/3M |
| operating mode | admin-only shadow |

### Components

`AI-CANDIDATE-VALIDATION-V01`은 단일 tag만 내는 모델이 아니라 common layer와 model-specific layer를 함께 관리한다.

| component code | current columns | meaning |
|---|---|---|
| `AI-CANDIDATE-VALIDATION-V01-COMMON` | `ai_shadow_decision`, `ai_shadow_tags` | 모든 후보에 공통 기준 AI tag 부여 |
| `AI-CANDIDATE-VALIDATION-V01-MODEL-SPECIFIC` | `ai_model_specific_tag` | 각 source model별 성격에 맞춘 전용 tag 부여 |
| `AI-CANDIDATE-VALIDATION-V01-LIVE-TRACKER` | `ai_live_shadow_tracker_*` | score 생성 이후 실제 가격 흐름만 추적 |

### Tags

Common tags:

| tag | interpretation |
|---|---|
| `AI_HIGH_CONVICTION` | 강한 AI 확인 후보 |
| `AI_CONFIRM` | AI 확인 후보 |
| `AI_RISK_REVIEW` | 위험 재검토 후보 |
| `AI_OBSERVE` | 명확한 AI 판단 없음 |

Model-specific tags:

| tag | interpretation |
|---|---|
| `MS_CONFIRM` | 해당 source model 성격 기준으로 품질 확인 |
| `MS_RISK_REVIEW` | 해당 source model 성격 기준으로 위험 재검토 |
| `MS_OBSERVE` | model-specific 모델은 있으나 판단 약함 |
| `MS_FALLBACK_COMMON` | model-specific 학습 표본 부족으로 common tag 사용 |

### Intended Use

`AI-CANDIDATE-VALIDATION-V01`은 후보를 새로 발굴하는 모델이 아니다. 기존 후보를 다음처럼 분류한다.

| use case | guidance |
|---|---|
| admin display | 후보별 common tag, model-specific tag, live shadow 성과 표시 |
| candidate triage | `MS_CONFIRM`은 확인 후보, `MS_RISK_REVIEW`는 보류/재검토 후보 |
| score adjustment | live-only 검증 후 기존 S/T/I score에 보조 가감점으로 반영 가능 |
| exclusion rule | 4~8주 이상 검증 전에는 자동 제외 금지 |
| public service | 현재 미반영, admin-only 관찰 |

### Promotion Gates

운영 반영은 다음 조건을 모두 본 뒤 판단한다.

1. `MS_CONFIRM`이 `MS_OBSERVE`보다 1W/2W/1M 평균수익률과 win rate에서 우위
2. `MS_RISK_REVIEW`가 MDD 또는 손실 회피 측면에서 유의미하게 분리
3. reconstructed tracker와 live-only tracker의 방향성이 충돌하지 않음
4. source model별 표본 수가 충분함

## Layer 2. AI-GROWTH-VALUATION-V01

### Definition

| item | value |
|---|---|
| model code | `AI-GROWTH-VALUATION-V01` |
| Korean name | `주가수준평가AI` |
| target | 전체 주식 universe |
| main question | 현재 주가 수준이 성장성 대비 부담스러운가, 합리적인가, 매력적인가? |
| scope note | ETF out-of-scope |
| operating mode | admin-only shadow/reference |

### Variants

| role | model / feature set | usage |
|---|---|---|
| champion/reference | `AI-GROWTH-VALUATION-V01`, `LOCAL_MARKET` | 기준 주가수준 평가 |
| challenger | `AI-GROWTH-VALUATION-V01-QM-THEME`, `QM_MARKET_THEME` | theme context 기반 승격/강등 관찰 |
| risk overlay | `AI-GROWTH-VALUATION-V01-QM-RISK`, `QM_MARKET_RISK` | 추천 모델이 아니라 caution tag |

### States and Tags

Valuation states:

| state | interpretation |
|---|---|
| `UNDERVALUED` | 성장성 대비 상대적으로 매력적 |
| `FAIR` | 부담 크지 않은 적정권 |
| `OVERHEATED` | 가격 부담 또는 과열 주의 |
| `AVOID` | 회피 또는 강한 재검토 |
| `OUT_OF_SCOPE_OR_MISSING` | 주식 valuation AI 적용 불가 또는 feature 부족 |

Risk tags:

| tag | interpretation |
|---|---|
| `risk_clear` | valuation/risk 양쪽에서 큰 경고 없음 |
| `risk_watch` | 시장 stress 또는 risk overlay 주의 |
| `risk_caution` | 하방위험 재검토 필요 |
| `out_of_scope` | 적용 대상 아님 |

## Combined Usage Matrix

두 AI layer는 서로 대체 관계가 아니라 다른 질문에 답한다.

| AI-CANDIDATE-VALIDATION-V01 | AI-GROWTH-VALUATION-V01 | interpretation |
|---|---|---|
| `MS_CONFIRM` | `UNDERVALUED` or `FAIR` | 강한 확인 후보 |
| `MS_CONFIRM` | `OVERHEATED` | 후보 품질은 좋지만 신규 진입 가격 주의 |
| `MS_CONFIRM` | `AVOID` | 후보는 좋으나 valuation 부담이 커서 보류 검토 |
| `MS_RISK_REVIEW` | `UNDERVALUED` or `FAIR` | 가격은 괜찮아도 원 모델 적합성/단기 리스크 점검 |
| `MS_RISK_REVIEW` | `OVERHEATED` or `AVOID` | 강한 경계 또는 제외 검토 |
| `MS_FALLBACK_COMMON` | any | model-specific 증거 부족, common AI와 valuation만 참고 |

## Layer 3. AI-DOWNSIDE-RISK-V01

### Definition

| item | value |
|---|---|
| model code | `AI-DOWNSIDE-RISK-V01` |
| Korean name | `하락위험예측AI` |
| target | S/T/I/C/user 후보 중 주식 후보 |
| main question | 이 후보가 향후 1M에 손실 또는 큰 MDD를 만들 위험이 높은가? |
| primary horizon | 1M, live tracking은 1W/2W/1M부터 확장 |
| operating mode | admin-only shadow |
| ETF scope | out-of-scope. ETF는 `AI-ETF-*` 별도 트랙 |

### Tags

| tag | interpretation |
|---|---|
| `risk_clear` | 유지 가능 |
| `risk_watch` | 관찰 필요 |
| `risk_caution` | 비중축소 검토 |
| `risk_exit_watch` | 매도/비중축소 후보 관찰 |

### Intended Use

`AI-DOWNSIDE-RISK-V01`은 추천 후보를 새로 뽑는 모델이 아니다. 기존 후보와 보유 후보에 하락위험 tag를 붙이는 risk overlay다.

초기 운영에서는 public 추천 제외 규칙으로 쓰지 않고, admin에서 `risk_caution`, `risk_exit_watch`의 실제 1W/2W/1M 성과를 관찰한다.

## Layer 4. AI-CANDIDATE-RANK-DELTA-V01

### Definition

| item | value |
|---|---|
| model code | `AI-CANDIDATE-RANK-DELTA-V01` |
| Korean name | `후보순위조정AI` |
| target | S/T/I/C/user 후보 중 주식 후보 |
| main question | 이 후보를 기존 순위보다 올려 볼지, 낮춰 볼지 AI가 보조 판단할 수 있는가? |
| primary horizon | 1M |
| operating mode | admin-only shadow |

### Scores

| score | meaning |
|---|---|
| `rank_upgrade_prob` | 1M 상대 성과와 MDD 기준 승격 가능성 |
| `rank_downgrade_prob` | 1M 상대 부진 또는 MDD 기준 강등 가능성 |
| `rank_delta_score` | `rank_upgrade_prob - rank_downgrade_prob` |

### Tags

| tag | interpretation |
|---|---|
| `rank_upgrade_candidate` | 승격 후보 |
| `rank_upgrade_watch` | 승격 관찰 |
| `rank_hold` | 유지 |
| `rank_downgrade_watch` | 강등 관찰 |
| `rank_downgrade_candidate` | 강등 후보 |

초기에는 실제 순위 변경에 사용하지 않고, admin에서 후보별 AI 보조 판단과 이후 성과를 관찰한다.

## Management Rules

1. AI model code는 `AI-{DOMAIN}-{FUNCTION}-V{NN}` 형태로 관리한다.
2. 기존 코드에 남은 alias는 즉시 삭제하지 않고, registry와 문서에서 canonical name을 먼저 고정한다.
3. `champion`, `challenger`, `overlay`, `shadow`, `reference` 상태를 명확히 분리한다.
4. AI output은 public 추천에 바로 반영하지 않는다.
5. admin payload에는 `model_code`, `model_version`, `model_role`, `feature_set`, `status`, `as_of_date`, `performance_asof_date`를 포함하는 방향으로 정리한다.
6. ETF는 `AI-GROWTH-VALUATION-V01`에서 제외한다. ETF용 AI는 별도 `AI-ETF-*` 계열로 설계한다.

## Immediate Work Items

1. `AI-CANDIDATE-VALIDATION-V01` registry 문서와 payload naming을 정리한다.
2. 코드 내부 legacy alias `AI-OVERLAY-V01` 파일명/테이블명 refactor 범위를 산정한다.
3. `ai_shadow_observation.json`에 canonical model code와 legacy alias를 함께 노출한다.
4. layer 1 live-only tracker에서 `MS_CONFIRM`, `MS_RISK_REVIEW`, common tag별 1W/2W/1M 성과를 누적한다.
5. layer 2 valuation AI와 결합한 combined matrix 리포트를 만든다.
