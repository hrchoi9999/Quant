# AI Overlay Backtest Design

작성일: 2026-05-12  
기준 데이터: 2026-05-11 pipeline 이후 current/admin payload  
범위: 주식/전략모델 S/T/I/C 계열. ETF는 별도 트랙으로 제외.

## 1. 목적

AI 학습 모델을 기존 전략모델에 실제 반영하기 전에, AI overlay가 성과 개선에 도움이 되는지 백테스트로 검증한다.

검증 목표는 다음 세 가지다.

1. 수익률 개선: 기존 전략모델 대비 forward return이 좋아지는가
2. 위험 축소: MDD, downside, 최악 구간 손실이 줄어드는가
3. 운영 안정성: 종목 변경, turnover, 모델별 편향이 과도하지 않은가

현재 AI 모델은 모두 shadow/admin 관찰 단계이며, 이 백테스트 결과가 나오기 전까지 public 추천 또는 S/T/I/C 실제 scoring에는 반영하지 않는다.

## 2. 적용 대상

### 2.1 포함

- S-series: `S2`, `S2_PIT_V01`, `S3`, `S3_ACCEL_V01`, `S3_CORE2`
- T-series 주식: `T-STOCK-V01`
- I-series 주식: `I-STOCK-STRONG-RSI-V01`
- C-series: Quant 내부 후보 데이터에 명시적으로 연결 가능한 범위부터 순차 적용
- user model: `stable`, `balanced`, `growth`는 참고용으로 별도 집계 가능

### 2.2 제외

- `T-ETF-V01`
- ETF전용포트폴리오AI
- ETF 역할/비중 template 모델
- ETF 종목이 섞인 user model row는 주식용 valuation overlay 적용 대상에서 제외

ETF는 데이터 소스와 모델 목적이 다르므로 별도 ETF AI 트랙에서 검증한다.

## 3. 사용 AI 모델

### 3.1 퀀트후보검증AI

model_code: `AI-CANDIDATE-VALIDATION-V01`

역할:
- 기존 전략모델 후보가 실제 투자 후보로 적합한지 검증한다.

사용 필드:
- `ai_quality_prob`
- `ai_risk_prob`
- `ai_model_specific_quality_prob`
- `ai_model_specific_risk_prob`
- `ai_shadow_decision`
- `ai_model_specific_tag`

1차 적용:
- `AI_CONFIRM`, `MS_CONFIRM`: 가점
- `AI_OBSERVE`, `MS_OBSERVE`: 중립
- `AI_RISK`, `MS_RISK`: 감점 또는 제외 후보

### 3.2 하락위험예측AI

model_code: `AI-DOWNSIDE-RISK-V01`

역할:
- 단기 하락 위험이 큰 후보를 줄이거나 제외한다.

사용 필드:
- `downside_risk_prob`
- `downside_risk_tag`

1차 적용:
- `risk_clear`: 중립 또는 소폭 가점
- `risk_watch`: 소폭 감점
- `risk_caution`: 강한 감점
- `risk_exit_watch`: 제외 또는 비중 축소

우선순위:
- 가장 먼저 단독 검증한다.
- 목표는 수익률 극대화보다 MDD와 최악 손실 축소다.

### 3.3 후보순위조정AI

model_code: `AI-CANDIDATE-RANK-DELTA-V01`

역할:
- 다음 리밸런싱에서 후보가 편출될지, 잔류 후보 중 순위가 오를지/내릴지 판단한다.

사용 필드:
- `rank_drop_prob`
- `retained_rank_change_score`
- `rank_delta_score`
- `rank_delta_decision`

1차 적용:
- `rank_drop_candidate`: 제외 또는 하위권 강등
- `rank_drop_watch`: 감점
- `rank_upgrade_candidate`: 가점
- `rank_upgrade_watch`: 소폭 가점
- `rank_downgrade_candidate`: 감점
- `rank_hold`: 중립

우선순위:
- 하락위험예측AI 다음으로 검증한다.
- 목표는 리밸런싱 후보 품질 개선이다.

### 3.4 주가수준평가AI

model_code: `AI-GROWTH-VALUATION-V01`

역할:
- 현재 주가수준이 부담스러운지, 합리적인지, 매력적인지 평가한다.

사용 필드:
- `champion_score`
- `champion_state`
- `challenger_score`
- `challenger_state`
- `challenger_change_label`
- `risk_tag`
- `risk_score`

1차 적용:
- `UNDERVALUED`, `FAIR`: 가점 후보
- `OVERHEATED`: 감점
- `AVOID`: 강한 감점 또는 제외
- `risk_caution`, `risk_watch`: caution penalty
- `out_of_scope`: 주식용 valuation 적용 제외

주의:
- ETF에는 적용하지 않는다.
- 단독 매수 신호가 아니라 valuation overlay로만 사용한다.

### 3.5 테마지속성AI

model_code: `AI-THEME-PERSISTENCE-V01`

역할:
- 현재 강한 테마가 다음 1개월에도 유지될 가능성을 판단한다.

사용 필드:
- `theme_continue_prob`
- `theme_fade_prob`
- `theme_persistence_score`
- `theme_persistence_tag`

1차 적용:
- `theme_persist_strong`: 테마 후보 가점
- `theme_persist_watch`: 소폭 가점
- `theme_neutral`: 중립
- `theme_fade_watch`: 감점
- `theme_fade_risk`: 강한 감점

주의:
- 테마 mapping이 없는 종목은 중립 처리한다.
- 테마지속성AI는 종목 단독 판단이 아니라 theme overlay다.

## 4. 백테스트 단계

### Stage 1. Event-level overlay ablation

가장 먼저 실행할 빠른 검증 단계다.

데이터:
- `admin_new_entry_tracker.json`
- AI current score CSV
- AI live shadow tracker
- forward return / forward risk metric

방법:
- 기존 후보 이벤트 row에 AI tag와 score를 붙인다.
- AI overlay별로 후보를 bucket화한다.
- bucket별 forward 1W/2W/1M/2M/3M 수익률과 MDD를 비교한다.

검증 질문:
- `risk_exit_watch` 후보가 실제로 더 위험했는가
- `rank_upgrade_candidate` 후보가 실제로 더 좋은 성과를 냈는가
- `AI_CONFIRM` 후보가 `AI_RISK` 후보보다 나았는가
- `OVERHEATED/AVOID` 후보가 이후 성과에서 불리했는가
- `theme_persist_strong` 테마 후보가 더 오래 성과를 냈는가

장점:
- 빠르다.
- 각 AI 모델의 기여도를 분해해 보기 좋다.

한계:
- 실제 포트폴리오 비중, 교체, turnover를 완전히 반영하지 않는다.

### Stage 2. Weekly candidate rerank simulation

전략모델별 후보 리스트를 AI overlay로 재정렬하는 단계다.

데이터:
- `admin_new_entry_tracker.weekly_rankings`
- `price.db::prices_daily`
- AI score CSV

방법:
- 각 전략모델의 주간 후보 universe를 가져온다.
- 기존 rank/score를 baseline으로 둔다.
- AI overlay score를 계산해 후보를 재정렬한다.
- 기존 top N과 동일한 종목 수를 유지한다.
- 탈락 후보가 생기면 다음 순위 후보로 채운다.

비교군:
- baseline: 기존 전략모델 rank 그대로
- risk_only: 하락위험예측AI만 적용
- rank_only: 후보순위조정AI만 적용
- validation_only: 퀀트후보검증AI만 적용
- valuation_only: 주가수준평가AI만 적용
- theme_only: 테마지속성AI만 적용
- risk_rank: 하락위험 + 후보순위조정
- risk_rank_validation: 하락위험 + 후보순위조정 + 후보검증
- full_stock_overlay: risk + rank + validation + valuation + theme

비중 방식:
- 1차: equal weight
- 2차: 기존 weight 유지 후 재정규화
- 3차: AI score 기반 mild tilt

### Stage 3. Portfolio backtest

실제 전략 반영 가능성을 판단하는 단계다.

방법:
- Stage 2에서 생성한 주간 holdings를 사용해 NAV를 계산한다.
- baseline 대비 성과를 비교한다.

평가지표:
- CAGR
- 누적수익률
- 1M/3M/6M rolling return
- MDD
- worst 1M return
- volatility
- Sharpe
- win rate
- turnover
- average holding count
- excluded/replaced count

모델별 분해:
- S2 계열
- S3 계열
- T-STOCK
- I-STOCK
- C-series 후보

시장국면별 분해:
- risk-on
- neutral
- risk-off
- high-vol
- low-vol

### Stage 4. Live shadow comparison

백테스트에서 유효한 overlay만 live shadow로 올린다.

방법:
- 실제 추천은 baseline 유지
- 별도 shadow portfolio로 AI overlay 적용 버전을 생성
- 4~8주 동안 실제 성과 비교

승격 조건:
- baseline 대비 MDD 감소
- 최악 손실 감소
- 수익률 또는 risk-adjusted return 개선
- turnover가 과도하게 증가하지 않음
- 특정 모델/테마에 과도하게 편향되지 않음

## 5. Overlay score 설계안

### 5.1 Conservative Guardrail

목적:
- 손실 회피를 먼저 검증한다.

적용:
- 하락위험예측AI
- 후보순위조정AI의 drop signal

규칙:
- `risk_exit_watch`: 제외
- `risk_caution`: score -20%
- `rank_drop_candidate`: 제외 또는 최하위 강등
- `rank_drop_watch`: score -10%

예상 효과:
- MDD 감소
- worst return 개선
- 수익률은 일부 낮아질 수 있음

### 5.2 Balanced Overlay

목적:
- 위험 회피와 후보 품질 개선을 동시에 본다.

적용:
- 하락위험예측AI
- 후보순위조정AI
- 퀀트후보검증AI

규칙:
- risk penalty 적용
- rank upgrade/downgrade 반영
- `AI_CONFIRM/MS_CONFIRM`: score +10%
- `AI_RISK/MS_RISK`: score -10% 또는 제외 후보

예상 효과:
- 후보 품질 개선
- 리밸런싱 성과 개선

### 5.3 Full Stock Overlay

목적:
- 모든 주식용 AI를 결합했을 때의 최대 개선 가능성을 본다.

적용:
- 하락위험예측AI
- 후보순위조정AI
- 퀀트후보검증AI
- 주가수준평가AI
- 테마지속성AI

규칙:
- risk/rank/validation을 기본축으로 둔다.
- valuation은 S2/S2_PIT에 더 강하게 반영한다.
- theme은 S3/I 계열에 더 강하게 반영한다.
- out_of_scope는 중립 처리한다.

예상 효과:
- 모델별로 다르게 작동할 가능성이 높다.
- 전체 평균보다 모델별 성능 분해가 중요하다.

## 6. 모델별 우선 적용 가설

| 전략모델 | 우선 AI overlay | 이유 |
| --- | --- | --- |
| S2/S2_PIT | 주가수준평가AI, 하락위험예측AI | 펀더멘털/valuation 성격이 강함 |
| S3/S3_ACCEL/S3_CORE2 | 하락위험예측AI, 후보순위조정AI, 테마지속성AI | 추세 과열/둔화 리스크 관리가 중요 |
| T-STOCK | 하락위험예측AI, 후보순위조정AI | 매수 타이밍과 하락 위험 제어가 핵심 |
| I-STOCK | 후보순위조정AI, 테마지속성AI, 하락위험예측AI | 초기 강한 신호의 지속성과 급락 위험 확인 |
| C-series | 테마지속성AI, 하락위험예측AI | 관계/테마 후보의 지속성과 위험 확인 |

## 7. 데이터 연결 키

기본 연결 키:

- `scope_key` 또는 `scope`
- `model_id` 또는 `model_code`
- `ticker` 또는 `security_code`
- `event_date` 또는 `snapshot_date`
- `week_end`

ticker 정규화:

- 문자열 6자리 zero-fill로 통일한다.
- ETF row는 주식용 overlay에서 제외한다.

날짜 원칙:

- 후보 기준일: `snapshot_date` 또는 `event_date`
- 성과 평가일: `performance_asof`
- 데이터 최신일: `data_asof`
- 세 날짜를 혼용하지 않는다.

## 8. Leakage 방지 원칙

1. 실전 반영 판단용 백테스트는 반드시 시간 순서를 지킨다.
2. 현재 학습된 2026-05-11 모델로 과거 전체를 재평가하는 결과는 research proxy로만 본다.
3. 운영 채택 후보는 walk-forward 방식으로 검증한다.
4. `performance_asof` 이후의 정보가 overlay score에 들어가면 안 된다.
5. theme/valuation/risk score는 해당 후보 기준일 이전 또는 당일 장마감 기준 데이터만 사용한다.

## 9. 산출물 제안

### Stage 1 산출물

- `reports/ai_overlay_backtest/ai_overlay_event_ablation_YYYYMMDD.csv`
- `reports/ai_overlay_backtest/ai_overlay_event_ablation_YYYYMMDD.json`
- `reports/ai_overlay_backtest/AI_OVERLAY_EVENT_ABLATION_YYYYMMDD.md`

### Stage 2/3 산출물

- `reports/ai_overlay_backtest/ai_overlay_policy_holdings_YYYYMMDD.csv`
- `reports/ai_overlay_backtest/ai_overlay_policy_nav_YYYYMMDD.csv`
- `reports/ai_overlay_backtest/ai_overlay_policy_performance_YYYYMMDD.csv`
- `reports/ai_overlay_backtest/AI_OVERLAY_POLICY_BACKTEST_YYYYMMDD.md`

### Stage 4 산출물

- `service_platform/web/admin_data/current/ai_overlay_backtest_current.json`
- `service_platform/web/admin_data/current/ai_overlay_shadow_portfolios_current.json`

QS 웹 반영은 Quant thread에서 직접 수정하지 않고, 별도 작업요청서로 전달한다.

## 10. 실행 순서

1. Stage 1 event-level ablation 스크립트를 만든다.
2. 하락위험예측AI 단독 효과를 먼저 확인한다.
3. 후보순위조정AI 단독 효과를 확인한다.
4. 퀀트후보검증AI 단독 효과를 확인한다.
5. 주가수준평가AI와 테마지속성AI를 모델별로 제한 적용한다.
6. `risk_rank`, `risk_rank_validation`, `full_stock_overlay` 조합을 비교한다.
7. 성과가 좋은 정책만 Stage 2 weekly rerank simulation으로 넘긴다.
8. Stage 2/3 결과가 좋은 정책만 live shadow portfolio로 올린다.

## 11. 1차 구현 범위

다음 단계에서는 먼저 `Stage 1 event-level ablation`만 구현한다.

이유:
- 빠르게 실행 가능하다.
- AI별 기여도를 분해하기 좋다.
- portfolio backtest로 가기 전에 어떤 overlay가 유효한지 거를 수 있다.

1차 구현 대상:
- 하락위험예측AI
- 후보순위조정AI
- 퀀트후보검증AI
- 주가수준평가AI
- 테마지속성AI
- 단독 정책과 3개 조합 정책

1차 성공 기준:
- risk 관련 정책에서 MDD 또는 worst return 개선
- rank/validation 정책에서 1M/2M 평균 수익률 개선
- full overlay가 단독 정책보다 항상 좋을 필요는 없으며, 모델별 적합성을 우선 확인한다.

