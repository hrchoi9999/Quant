# QS Request: AI Learning Model Explanation Guide

작성일: 2026-05-11  
요청 주체: Quant thread  
대상: QuantService(QS) admin AI 학습 모델 화면

## 1. 요청 목적

현재 admin AI 학습 모델 화면에는 모델 코드, tag, AUC, shadow tracking 값 등이 표시되지만, 사용자가 보기에 다음 내용을 즉시 이해하기 어렵습니다.

- 이 AI 모델이 무엇을 판단하는 모델인지
- 기존 S/T/I/C 전략 모델과 어떤 관계인지
- 어떤 지표를 중요하게 봐야 하는지
- 현재 결과가 실제 추천 반영인지, shadow 관찰인지, research 단계인지

따라서 QS 화면에 모델별 설명 영역과 지표 해석 가이드를 추가해 주시기 바랍니다.

주의:
- Quant thread에서는 QS 코드를 직접 수정하지 않습니다.
- 이 문서는 QS thread에 전달할 작업요청서입니다.
- 기존 Quant payload는 유지하고, QS 화면 표현/가이드 문구를 보강하는 작업입니다.

## 2. 모델별 설명 문구

아래 설명을 각 모델 카드 또는 상세 화면 상단에 표시해 주세요.

### AI-CANDIDATE-VALIDATION-V01 / 퀀트후보검증AI

역할:
- 기존 S/T/I/C 전략 모델이 뽑은 후보가 실제 투자 후보로 적합한지 검증하는 AI입니다.

목적:
- 전략 모델의 후보를 그대로 믿기보다, 과거 유사 조건에서 성과가 좋았는지 학습해 후보의 신뢰도를 보강합니다.
- 현재는 shadow 관찰 단계이며, public 추천에 직접 반영하지 않습니다.

기대효과:
- 후보군의 품질을 높이고, 성과 가능성이 낮은 후보를 사전에 걸러내는 데 활용합니다.
- 향후 Meta AI의 입력 feature로 사용될 수 있습니다.

사용자가 봐야 할 지표:
- horizon별 sample count
- 1W/2W/1M/2M/3M 실제 성과
- 후보별 validation score 또는 shadow performance

표시 주의:
- sample이 아직 없으면 0%가 아니라 `N/A` 또는 `관찰 데이터 부족`으로 표시해 주세요.

### AI-GROWTH-VALUATION-V01 / 주가수준평가AI

역할:
- 주식 후보의 현재 주가 수준이 부담스러운지, 합리적인지, 여전히 매력적인지 평가하는 AI입니다.

목적:
- 정식 DCF 모델은 아니며, valuation/growth/momentum/risk를 결합한 proxy 기반 주가수준 평가 모델입니다.
- champion 모델과 QM-THEME challenger, QM-RISK caution tag를 함께 관찰합니다.

기대효과:
- 좋은 기업이라도 너무 비싼 구간에서 추격 매수하는 위험을 줄입니다.
- 테마 context가 강한 후보를 재평가하고, risk context가 높은 후보에는 caution tag를 붙입니다.

사용자가 봐야 할 지표:
- champion_state
- challenger_state
- risk_tag
- champion 대비 challenger 승격/강등 여부
- 1W/2W/1M/2M/3M/6M/1Y shadow performance

표시 주의:
- `QM-RISK`는 추천 모델이 아니라 caution tag입니다.
- ETF는 이 모델의 적용 대상이 아닙니다.

### AI-DOWNSIDE-RISK-V01 / 하락위험예측AI

역할:
- 후보 종목의 단기 하락 위험 또는 편입 후 손실 위험을 예측하는 AI입니다.

목적:
- 매수 후보 발굴보다 위험 회피, 비중 축소, 매도 검토에 가까운 보조 모델입니다.
- T-series 보강 및 후보 리스크 필터로 활용 가능성이 큽니다.

기대효과:
- 큰 손실과 MDD를 줄이고, 위험이 커진 후보를 조기에 watch/caution으로 분류합니다.

사용자가 봐야 할 지표:
- downside_risk_tag
- risk_clear / risk_watch / risk_caution / risk_exit_watch 분포
- AUC
- tag별 1W/2W/1M 실제 성과
- tag별 평균 수익률, MDD, 하락 회피 효과

표시 주의:
- `risk_exit_watch`는 자동 매도 신호가 아니라 매도 검토/관찰 신호로 표시해 주세요.

### AI-CANDIDATE-RANK-DELTA-V01 / 후보순위조정AI

역할:
- 다음 리밸런싱에서 후보가 편출될지, 잔류 후보 중 순위가 올라갈지/내려갈지 예측하는 AI입니다.

목적:
- 기존 전략 모델 후보의 순위를 AI로 재평가해 승격/강등 후보를 구분합니다.
- 편출 예측 모델과 잔류 순위변화 모델을 분리해 운영합니다.

기대효과:
- 리밸런싱 품질을 높이고, 순위가 약해질 후보를 미리 감지합니다.
- 향후 S/T/I/C 후보의 최종 점수 조정에 활용할 수 있습니다.

사용자가 봐야 할 지표:
- rank_drop_prob
- retained_rank_change_score
- rank_delta_score
- rank_delta_decision
- drop / upgrade / downgrade head별 AUC

표시 주의:
- `rank_drop_candidate`는 현재 후보에서 다음 리밸런싱 편출 가능성이 높다는 뜻입니다.
- `rank_upgrade_candidate`는 매수 확정이 아니라 후보 우선순위 상향 관찰 신호입니다.

### AI-THEME-PERSISTENCE-V01 / 테마지속성AI

역할:
- 현재 강한 테마가 다음 1개월 구간에서도 유지될지, 또는 둔화될지 예측하는 AI입니다.

목적:
- 테마 추종 후보가 단기 과열인지, 지속 가능성이 있는지 구분합니다.
- S/T/I/C 후보 및 향후 Meta AI에 theme specialist feature로 제공됩니다.

기대효과:
- 테마가 꺾이는 구간의 추격 매수 위험을 줄이고, 지속성이 높은 테마 후보를 더 신뢰할 수 있게 합니다.

사용자가 봐야 할 지표:
- theme_continue_prob
- theme_fade_prob
- theme_persistence_score
- theme_persistence_tag
- continue/fade head별 AUC
- top persistent / top fade risk 테마

표시 주의:
- `theme_persist_strong`은 자동 매수 신호가 아닙니다.
- `theme_fade_watch`는 자동 매도 신호가 아니라 테마 둔화 관찰 신호입니다.

### AI-MODEL-SELECTION-V01 / 모델선택AI

현재 상태:
- research 단계입니다.
- 아직 admin shadow tracking 정식 모델로 확정된 상태는 아닙니다.

역할:
- 현재 시장/후보 조건에서 어떤 전략 모델 또는 전략군이 상대적으로 유리한지 판단하는 AI입니다.

목적:
- S/T/I/C 전략 모델을 동일 비중으로 보지 않고, 시장국면과 후보 특성에 따라 더 적합한 모델을 선택하거나 가중합니다.

기대효과:
- 시장 상황별 전략 선택 품질을 높이고, 향후 Meta AI 또는 Portfolio AI의 상위 선택 layer로 활용할 수 있습니다.

표시 주의:
- QS 화면에 표시할 경우 반드시 `Research only` 또는 `실험 단계`로 표시해 주세요.
- 실제 추천/리밸런싱 반영 모델처럼 보이면 안 됩니다.

### AI-ETF-SHADOW-PORTFOLIO-V01 / ETF전용포트폴리오AI

역할:
- ETF 전용 데이터와 시장국면을 바탕으로 ETF 포트폴리오 후보를 구성하는 shadow AI입니다.

목적:
- 주식용 AI와 분리해 ETF 전용 모델로 운영합니다.
- ETF역할배분AI와 ETF비중템플릿AI를 결합해 시장 모드별 ETF 포트폴리오를 관찰합니다.

구성 모델:
- AI-ETF-ROLE-ALLOCATION-V01 / ETF역할배분AI
- AI-ETF-ROLE-WEIGHT-TEMPLATE-V01 / ETF비중템플릿AI

기대효과:
- ETF를 단순히 수익률 순서로 고르는 것이 아니라, 시장국면에 맞는 역할과 비중 템플릿으로 포트폴리오를 구성합니다.
- 향후 ETF 전용 추천/배분 모델의 기반이 됩니다.

사용자가 봐야 할 지표:
- regime_mode
- selected_role
- selected_template
- selected_role_prob
- selected_template_prob
- primary_shadow_variant
- backtest avg_1m_ret / win_rate / avg_1m_mdd / worst_1m_ret
- current_holding_count

표시 주의:
- 현재는 admin-only shadow portfolio입니다.
- 실제 ETF 추천 포트폴리오가 아니라 관찰용 포트폴리오입니다.

## 3. 화면 구성 가이드

### 3.1 모델 카드 상단

각 모델 카드 상단에는 다음 순서로 보여 주세요.

1. 한글 모델명
2. 영문 model_code
3. 상태 badge
4. 한 줄 설명
5. 적용 범위
6. 추천 반영 여부

상태 badge 예시:
- `Shadow 관찰`
- `Research`
- `Payload 준비됨`
- `성과 데이터 부족`
- `추천 미반영`

적용 범위 예시:
- 주식 후보
- S/T/I/C 후보
- 테마 단위
- ETF 전용

추천 반영 여부 예시:
- `Public 추천 미반영`
- `Admin 관찰 전용`
- `향후 Meta AI 후보 feature`

### 3.2 상세 화면 상단 안내문

상세 화면에는 다음 안내문을 공통으로 넣어 주세요.

> 이 화면은 AI 학습 모델의 shadow 관찰 화면입니다. 표시된 score와 tag는 현재 추천을 자동으로 바꾸는 신호가 아니라, 기존 전략 모델 후보를 검증하고 향후 모델 개선에 활용하기 위한 관찰 지표입니다.

ETF 화면에는 다음 문구를 추가해 주세요.

> ETF전용포트폴리오AI는 주식용 AI와 별도 트랙으로 개발 중인 ETF 전용 shadow 모델입니다. 현재 포트폴리오는 실제 추천이 아니라 시장국면별 ETF 배분 가능성을 관찰하기 위한 테스트 결과입니다.

## 4. 지표 해석 가이드

### 4.1 공통 지표

`AUC`
- AI가 positive/negative case를 구분하는 능력입니다.
- 0.5는 무작위 수준, 1.0에 가까울수록 구분력이 높습니다.
- 단, AUC가 높아도 실제 투자 성과가 항상 좋다는 뜻은 아닙니다.

`sample_count`
- 실제 성과 평가에 사용 가능한 관찰 건수입니다.
- sample이 부족한 기간은 성과 해석을 보류해야 합니다.

`1W / 2W / 1M / 2M / 3M`
- AI tag가 붙은 뒤 실제 시간이 지난 후의 성과입니다.
- 기준일과 성과 측정일이 같으면 `N/A`가 정상입니다.

`win_rate`
- 관찰 구간 중 수익이 난 비율입니다.

`MDD`
- 관찰 구간의 최대 낙폭입니다.
- 수익률이 좋아도 MDD가 크면 위험이 큰 후보로 봐야 합니다.

`risk_adj`
- 수익률에서 낙폭 위험을 함께 고려한 관찰 지표입니다.

### 4.2 score/prob 해석

`prob`
- 해당 사건이 발생할 AI 예측 확률입니다.
- 예: rank_drop_prob이 높으면 다음 리밸런싱 편출 가능성이 높다는 뜻입니다.

`score`
- 여러 확률 또는 feature를 결합한 종합 점수입니다.
- score가 높다고 무조건 매수라는 뜻은 아니며, 모델별 목적에 따라 해석해야 합니다.

`tag`
- score/prob를 사람이 보기 쉽게 구간화한 결과입니다.
- tag는 의사결정 보조 신호이며, 단독 매수/매도 신호가 아닙니다.

### 4.3 N/A 표시 원칙

다음 경우는 반드시 `0%`가 아니라 `N/A`로 표시해 주세요.

- 아직 해당 기간이 지나지 않아 실제 성과를 계산할 수 없는 경우
- sample_count가 0인 경우
- 값이 null인 경우
- 모델은 생성됐지만 shadow tracking이 아직 누적되지 않은 경우

권장 표시:
- `N/A`
- `관찰 데이터 부족`
- `성과 집계 전`

피해야 할 표시:
- `0%`
- `0.00`
- 빈칸

## 5. 사용자 친화적 컬럼명 제안

QS 화면에서는 원본 필드명을 그대로 노출하기보다 아래처럼 병기하거나 tooltip을 제공해 주세요.

| 원본 필드 | 권장 표시명 | 설명 |
| --- | --- | --- |
| model_code | 모델 코드 | 내부 관리용 AI 모델명 |
| model_name_ko | 모델명 | 사용자용 한글 모델명 |
| as_of_date | 기준일 | AI 판단 기준일 |
| auc | 구분력(AUC) | 모델이 정답/오답 케이스를 구분하는 정도 |
| sample_count | 관찰 건수 | 성과 평가에 사용 가능한 샘플 수 |
| rank_drop_prob | 편출 가능성 | 다음 리밸런싱에서 후보에서 빠질 가능성 |
| retained_rank_change_score | 잔류 순위 변화 점수 | 잔류 후보의 순위 상승/하락 방향 |
| downside_risk_tag | 하락 위험 태그 | 단기 손실 위험 구간 |
| theme_persistence_tag | 테마 지속성 태그 | 테마 지속/둔화 가능성 |
| selected_role | 선택된 ETF 역할 | 현재 ETF 포트폴리오에서 유리하다고 본 역할 |
| selected_template | 선택된 ETF 비중 템플릿 | 현재 시장모드에 맞는 ETF 비중 구성안 |
| avg_1m_ret | 평균 1개월 수익률 | 과거 검증 구간의 평균 1개월 성과 |
| avg_1m_mdd | 평균 1개월 낙폭 | 과거 검증 구간의 평균 최대 낙폭 |
| worst_1m_ret | 최악 1개월 수익률 | 검증 구간 중 가장 나빴던 1개월 성과 |

## 6. 구현 요청 사항

1. AI 학습 모델 목록 화면에 모델 설명 영역을 추가해 주세요.
2. 모델 상세 화면에 `역할`, `목적`, `기대효과`, `주요 확인 지표`, `주의사항`을 표시해 주세요.
3. 공통 지표 해석 가이드를 접이식 help panel 또는 tooltip으로 제공해 주세요.
4. null/성과 미도래 값은 반드시 `N/A`로 표시해 주세요.
5. tag/score/prob는 원본 필드명만 노출하지 말고 사용자 친화적 표시명과 설명을 함께 제공해 주세요.
6. shadow/research/admin-only 상태가 명확히 보이도록 badge를 추가해 주세요.
7. 실제 추천 반영 모델처럼 오해되지 않도록 `Public 추천 미반영`, `Admin 관찰 전용` 문구를 명확히 표시해 주세요.

## 7. 완료 기준

- 사용자가 각 AI 모델의 목적을 화면에서 바로 이해할 수 있어야 합니다.
- 사용자가 어떤 지표를 봐야 하는지 알 수 있어야 합니다.
- null 값이 0%처럼 오해되지 않아야 합니다.
- shadow/research 모델이 실제 추천 반영 모델처럼 보이지 않아야 합니다.
- ETF 전용 모델은 주식용 AI와 별도 트랙임이 명확해야 합니다.

