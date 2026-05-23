# AI Learning Model Development History - 2026-05-07

## 목적

Quant 프로젝트에서 진행한 AI 학습모델 개발 과정을 진행순서별로 정리한다.

현재 AI 학습모델은 기존 S/T/I/C 모델을 즉시 대체하는 운영 추천 모델이 아니라, 기존 모델이 선별한 후보 종목의 품질을 재평가하고 shadow 성과를 추적하는 보조 학습 체계다.

## 1. AI 학습 도입 방향 정리

AI 학습은 기존 모델을 바로 대체하는 방식이 아니라, 기존 모델의 산출값과 실제 성과를 학습해 후보 종목의 품질을 재평가하는 방식으로 시작했다.

성과 평가는 다음 3단계로 분리했다.

| 단계 | 의미 |
|---|---|
| 백테스트 성과 | 모델 규칙을 과거 데이터에 적용한 검증 결과 |
| 실제 운영 성과 | 모델 운영 시작 이후 실제 시장가격 추적 결과 |
| AI shadow 성과 | AI 점수/태그를 붙인 이후의 관찰 성과 |

## 2. 학습 데이터 정의

AI 학습에 사용할 데이터는 다음으로 정리했다.

- 기존 S/T/I 모델의 산출값
- 종목별 가격, 수익률, 변동성, 모멘텀
- 실제 운영 이후 forward return
- DART 기반 펀더멘털 데이터
- 수급 데이터
- QuantMarket 시장 context 데이터
- 테마, 업종, 리스크, 시장 국면 데이터

## 3. 수급/DART 데이터 보강

AI 성능을 높이기 위해 외부 데이터를 보강했다.

- 네이버 기반 수급 데이터 수집
- 키움증권 API 기반 수급 데이터 연동
- DART 공식 이벤트 및 펀더멘털 데이터 보강
- 2024년 이후 수급 데이터 학습 반영

## 4. 공통 AI 학습모델 구축

처음에는 여러 모델에 공통으로 적용되는 AI 학습모델을 만들었다.

이 모델의 정식명은 `퀀트후보검증AI`, 정식 model_code는 `AI-CANDIDATE-VALIDATION-V01`로 관리한다. 기존 개발 산출물의 `AI-OVERLAY-V01` 표기는 legacy alias다.

목적은 특정 모델 하나가 아니라, 여러 모델에서 선별된 종목을 공통 기준으로 재평가하는 것이었다.

주요 실험:

- Gradient Boosting
- Logistic Regression
- label 정교화
- 1M, 2M, 3M 등 기간별 label 분리
- 공통 AI vs 모델별 AI 비교

결론:

- 공통 AI는 baseline/reference로 가치가 있다.
- 모델별 성격이 달라서 모델별 AI 학습도 병행하는 것이 유리하다.

## 5. 모델별 AI 학습

S/T/I 모델별로 개별 학습을 진행했다.

목적은 각 모델의 전략 성격에 맞게 AI가 후보 종목의 품질을 다르게 평가하게 하는 것이다.

결론:

- 공통 AI는 reference로 유지한다.
- 모델별 AI는 실제 운영 보강용으로 관찰한다.
- 공통 AI와 모델별 AI를 병행 관찰하는 구조가 적절하다.

## 6. AI Shadow Performance Tracker 구축

AI가 실제로 도움이 되는지 판단하기 위해 shadow tracker를 붙였다.

추적 기준:

- AI 점수 구간별 성과
- AI tag별 성과
- 모델별 성과
- 종목별 forward return
- 1W, 2W, 1M, 2M, 3M, 6M, 1Y 성과

## 7. 성장주 주가수준평가AI 모델 검토

ChatGPT가 작성한 성장주 적정 주가 수준 평가 AI 학습모델 문서를 검토했다.

원본 문서:

- `D:\Quant\docs\20260506_growth_stock_valuation_ai_model_spec.md`

초기에는 성장주 flag를 만들었지만, 이후 방향을 다음과 같이 정리했다.

- 성장주 flag는 참고 정보로만 관리한다.
- 주가수준 평가 모델은 전체 universe 대상으로 학습한다.
- 성장주 여부는 나중에 variation 실험으로 분리한다.

## 8. AI-GROWTH-VALUATION-V01 독립 모델 정의

주가수준평가AI 모델을 독립 모델로 정의했다.

| 항목 | 내용 |
|---|---|
| model_code | `AI-GROWTH-VALUATION-V01` |
| 한글명 | 주가수준평가AI |
| 대상 | 전체 universe |
| 성격 | 현재 주가 수준이 부담스러운지, 합리적인지, 상대적으로 매력적인지 평가 |
| 구조 | Rule + ML Hybrid |

주요 score 구성:

- valuation score
- growth quality score
- downside risk score
- expected return score
- revision momentum score

## 9. Reverse DCF Proxy 적용

정식 DCF는 아직 보류했다.

정식 DCF에 필요한 데이터:

- FCF
- 할인율
- terminal growth
- debt/cash
- capex
- 운전자본

현재 단계에서는 복잡한 정식 DCF보다 학습 가능한 proxy가 더 실용적이라고 판단했다.

핵심은 정확한 적정주가 산출이 아니라, 현재 주가 수준을 상대적으로 평가하는 것이다.

## 10. AI-GROWTH-VALUATION-V01 검증

검증 항목:

- Rank IC
- Top-N 성과
- MDD
- Sharpe
- 1Y, 2Y, 3Y, 5Y, FULL 성과표
- Top30 forward return
- Top decile spread

초기 결과:

- 시장이 강세장일 때 valuation 부담을 과하게 반영하면 오히려 성과가 낮아질 수 있다.
- 시장 국면을 함께 반영할 필요가 있다.

## 11. QuantMarket 시장 Context 연동

시장 국면을 반영하기 위해 QuantMarket 데이터를 요청했고, QuantMarket에서 AI 학습용 market context mart를 제공했다.

주요 입력:

- `market_context_daily`
- `theme_context_daily`
- `risk_context_daily`
- `flow_context_daily`

경로:

- `D:\QuantMarket\service_platform\ai_training\market_context\current`

Quant 쪽에서는 이 데이터를 읽어 `AI-GROWTH-VALUATION-V01` feature에 반영했다.

## 12. QuantMarket Feature 반영 후 재학습

QuantMarket context 44개 feature를 추가했다.

포함된 feature:

- 시장 상태
- 시장 추세
- breadth
- risk-on/risk-off
- 테마 모멘텀
- 테마 rotation
- 테마 persistence
- 시장 stress
- 수급 context

재학습 결과:

- 전체 Rank IC는 소폭 하락했다.
- Top-N 후보 포트폴리오 성과는 개선됐다.
- 즉 전체 universe를 줄 세우는 능력보다는 상위 후보 선별에 더 도움이 되는 데이터로 판단했다.

## 13. Feature Group Ablation 테스트

어떤 데이터 묶음이 실제로 도움이 되는지 분해 실험했다.

실험 조합:

- `BASE_CORE`
- `LOCAL_MARKET`
- `QM_MARKET`
- `QM_MARKET_RISK`
- `QM_MARKET_THEME`
- `QM_MARKET_THEME_RISK`
- `QM_FULL`

핵심 결과:

| feature set | 판단 |
|---|---|
| `LOCAL_MARKET` | 기존 champion 유지 |
| `QM_MARKET_THEME` | challenger 1순위 |
| `QM_MARKET_RISK` | risk/caution overlay에 적합 |
| `QM_FULL` | observation only |

관련 문서:

- `D:\Quant\docs\AI_GROWTH_VALUATION_FEATURE_ABLATION_20260506.md`

## 14. Challenger / Risk Overlay 설계

최종 구조는 다음과 같이 정리했다.

| 역할 | model/feature set | 사용 방식 |
|---|---|---|
| Champion | `AI-GROWTH-VALUATION-V01`, `LOCAL_MARKET` | 기준 모델 유지 |
| Challenger | `AI-GROWTH-VALUATION-V01-QM-THEME`, `QM_MARKET_THEME` | shadow 성과 관찰 |
| Risk overlay | `AI-GROWTH-VALUATION-V01-QM-RISK`, `QM_MARKET_RISK` | 추천 모델이 아니라 위험 태그 |

## 15. Challenger Overlay 생성

현재 S/T/I/user 후보 348개에 대해 champion, challenger, risk overlay를 붙였다.

비교 항목:

- `champion_state`
- `champion_score`
- `challenger_state`
- `challenger_score`
- `challenger_change_label`
- `risk_state`
- `risk_score`
- `risk_tag`

결론:

- `QM_MARKET_THEME`는 후보 선별 challenger로 적합하다.
- `QM_MARKET_RISK`는 하락 위험 경고용으로 적합하다.
- `QM_FULL`은 변화 폭이 작아 관찰용으로 둔다.

관련 문서:

- `D:\Quant\docs\AI_GROWTH_VALUATION_CHALLENGER_OVERLAY_20260506.md`

## 16. 웹 Admin 제공 Payload 생성

AI 모델을 웹 admin에서 볼 수 있도록 current payload를 만들었다.

파일:

- `D:\Quant\service_platform\web\admin_data\current\valuation_ai_challenger_current.json`
- `D:\Quant\service_platform\web\admin_data\current\valuation_ai_challenger_shadow_performance.json`

용도:

- AI 학습 모델 admin 페이지 표시
- champion/challenger/risk tag 비교
- 종목별 성과 추적
- 1W, 2W, 1M, 2M, 3M, 6M, 1Y 성과 표시

## 17. Pipeline 연결

valuation AI pipeline에 challenger current와 shadow tracker 생성 단계를 연결했다.

수정 파일:

- `D:\Quant\src\pipelines\rebuild_growth_valuation_ai_pipeline.py`

추가 실행 단계:

- `build_valuation_ai_challenger_current.py`
- `build_valuation_ai_challenger_shadow_tracker.py`

## 18. QS/redbot Admin 반영

QS 쪽에서 admin 전용 `AI 학습 모델` 페이지를 만들었다.

현재 상태:

- public 추천 모델에는 미반영
- admin-only 관찰용
- champion/challenger/risk tag 확인 가능
- shadow 성과 추적 가능

## 주요 산출물

### 문서

- `D:\Quant\docs\AI_GROWTH_VALUATION_FEATURE_ABLATION_20260506.md`
- `D:\Quant\docs\AI_GROWTH_VALUATION_CHALLENGER_OVERLAY_20260506.md`
- `D:\Quant\docs\AI_GROWTH_VALUATION_CHALLENGER_SHADOW_WEB_PAYLOAD_20260506.md`

### 스크립트

- `D:\Quant\scripts\run_valuation_ai_feature_ablation.py`
- `D:\Quant\scripts\build_valuation_ai_challenger_overlay.py`
- `D:\Quant\scripts\build_valuation_ai_challenger_current.py`
- `D:\Quant\scripts\build_valuation_ai_challenger_shadow_tracker.py`

### 웹 제공 payload

- `D:\Quant\service_platform\web\admin_data\current\valuation_ai_challenger_current.json`
- `D:\Quant\service_platform\web\admin_data\current\valuation_ai_challenger_shadow_performance.json`

### 모델 파일

- `D:\Quant\data\models\valuation_ai\AI-GROWTH-VALUATION-V01-QM-MARKET-THEME-20260504-001.joblib`
- `D:\Quant\data\models\valuation_ai\AI-GROWTH-VALUATION-V01-QM-MARKET-RISK-20260504-001.joblib`

## 현재 최종 상태

현재 AI 학습모델은 다음 단계까지 완료됐다.

- 데이터 보강 완료
- AI 학습모델 1차 구축 완료
- QuantMarket context 반영 완료
- feature group ablation 테스트 완료
- challenger/risk overlay 분리 완료
- 웹 admin payload 생성 완료
- pipeline 연결 완료
- admin 화면 반영 완료

현재는 운영 추천 모델이 아니라 shadow 관찰 단계다.

## 다음 검증 과제

1. `QM-THEME` challenger의 실제 성과 추적
   - champion 대비 승격/강등 종목의 1W, 2W, 1M 성과 확인

2. `QM-RISK` risk tag 검증
   - `risk_caution`, `risk_watch`, `risk_clear`별 실제 성과 비교

3. 웹 admin 화면 점검
   - null이 `0%`가 아니라 `N/A`로 표시되는지 확인
   - champion/challenger/risk tag 구분이 명확한지 확인

4. 추가 학습 보강
   - theme mapping confidence 낮은 bucket 제외 또는 downweight 실험
   - `QM_MARKET_THEME + selective risk` 조합 실험

5. 운영 승격 판단
   - 4~8주 shadow tracking 후 `QM-THEME` challenger를 champion으로 올릴지 판단
