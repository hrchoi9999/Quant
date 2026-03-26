# FILE: TASK_09_INTEGRATED_MODEL_PERFORMANCE_COMPARISON_FRAMEWORK_20260318.md

# TASK 09. Integrated Model Performance Comparison Framework
## (통합 모델 성과 비교 / 평가 / 리포팅 체계)

---

# A. TASK 문서용

## 1. 작업 목적
TASK 09의 목적은 현재까지 개발된 개별 모델들과 Router 통합모델을
같은 기준으로 비교·평가할 수 있는 **표준 성과 비교 체계**를 구축하는 것입니다.

즉,
- 기존 주식 모델 `S2`, `S3`
- ETF/멀티에셋 모델 `S4`, `S5`, `S6`
- 상위 통합모델 `Router`
를 각각 따로 보는 단계를 넘어,

**어떤 모델이 어떤 기간, 어떤 국면, 어떤 비용 조건에서 더 유효한지**
명확하게 비교하고,
향후 Redbot 서비스에서 사용자용 모델과 관리용 모델을 연결할 수 있는
평가 기반을 만드는 것이 이번 TASK의 핵심입니다.

이번 단계가 완료되면,
모델 개발이 “좋아 보이는 개별 결과” 수준을 넘어
**통합적인 모델 평가/선정/상품화 체계**로 진입하게 됩니다.

---

## 2. 작업 배경
현재까지의 진행 상황은 다음과 같습니다.

- TASK 01: ETF 마스터 유니버스 생성, ETF 일봉 수집, `prices_daily` 적재, 최소 validate 완료
- TASK 02: ETF 분류(rule + override), 코어 ETF 유니버스(core), 유동성 기준, group coverage 구축
- TASK 03: 멀티에셋 공통 데이터 모델(`asset_type`, `instrument_master`, `etf_meta`) 고정
- TASK 04: ETF 자산배분 레이어 백테스트 엔진 구축
- TASK 05: S6 Risk-Off Defensive Allocation 고도화
- TASK 06: S4 Risk-On Offensive Allocation 고도화
- TASK 07: S5 Neutral Mean-Reversion Allocation 고도화
- TASK 08: Multi-Asset Regime Router 통합 실행 구조 구축

이제 다음 단계는,
각 모델을 “개별 백테스트 결과”로 보는 것이 아니라,
**공통 지표 / 공통 기간 / 공통 리포트 포맷**으로 비교하는 체계를 만드는 것입니다.

---

## 3. 핵심 원칙
1. TASK 09는 새로운 알파 모델 개발이 아니라 **비교/평가/리포팅 인프라** 구축입니다.
2. 모든 모델은 동일한 성과지표 정의를 사용해야 합니다.
3. FULL 성과만 보지 말고, 1Y / 2Y / 3Y / 5Y 구간 성과를 반드시 병행합니다.
4. 거래비용/슬리피지 반영 여부를 명확히 구분합니다.
5. 개별 모델 성과와 Router 통합모델 성과를 동시에 비교할 수 있어야 합니다.
6. 결과는 Redbot의 사용자용 모델 설명에도 연결될 수 있어야 합니다.
7. 성과 비교는 반드시 CSV/표/차트 형태로 재현 가능해야 합니다.
8. “좋아 보이는 숫자”보다 **일관된 비교 기준**을 우선합니다.

---

## 4. 비교 대상 모델
이번 TASK 09의 기본 비교 대상은 아래와 같습니다.

### 4.1 주식 모델
- `S2`
- `S3`

### 4.2 ETF / 멀티에셋 모델
- `S4`
- `S5`
- `S6`

### 4.3 상위 통합 모델
- `Router`

### 4.4 선택 비교 대상
- `S3 core2` (기존 베이스라인 비교용)
- `TASK 04 기본 risk_on / neutral / risk_off`
- 기타 실험 모델

---

## 5. 비교 기준(표준화 항목)

### 5.1 공통 성과 지표
최소 아래 지표를 표준으로 사용합니다.

- Start
- End
- 일수
- CAGR
- MDD
- Sharpe
- 평균 일간수익률
- 일간 변동성
- turnover
- rebalance_count

### 5.2 필수 비교 구간
아래 구간을 반드시 병행합니다.

- FULL
- 1Y
- 2Y
- 3Y
- 5Y

### 5.3 추가 비교 항목
가능하면 아래도 포함합니다.

- 누적 수익률
- 최대 연속 손실 기간
- 월간 수익률 승률
- 연도별 성과
- 거래비용 차감 전/후 성과 차이
- 슬리피지 민감도
- 국면별 성과 분해(risk_on / neutral / risk_off)

---

## 6. 비교 프레임 구조

### 6.1 모델 단위 비교
각 모델별로 아래를 산출합니다.
- summary
- period stats (FULL/1Y/2Y/3Y/5Y)
- equity curve
- drawdown curve
- turnover / 거래횟수

### 6.2 모델군 비교
아래 수준의 비교표를 만듭니다.
- 주식 모델 비교: `S2 vs S3`
- ETF 모델 비교: `S4 vs S5 vs S6`
- 통합 비교: `S2/S3/S4/S5/S6/Router`

### 6.3 Router 기여도 비교
가능하면 Router에 대해 아래도 기록합니다.
- 국면별 사용 모델
- 모델별 기여도
- 국면별 성과 기여
- fallback 사용 비율

---

## 7. 출력 형식
### 7.1 CSV 출력
최소 아래 파일을 생성합니다.

- `reports/model_compare/model_compare_summary_{stamp}.csv`
- `reports/model_compare/model_compare_periods_{stamp}.csv`
- `reports/model_compare/model_compare_yearly_{stamp}.csv`
- `reports/model_compare/model_compare_regime_{stamp}.csv`
- `reports/model_compare/model_compare_cost_sensitivity_{stamp}.csv`

### 7.2 시각화 출력
가능하면 아래 파일도 생성합니다.

- `reports/model_compare/model_compare_equity_{stamp}.png`
- `reports/model_compare/model_compare_drawdown_{stamp}.png`

### 7.3 Markdown 또는 HTML 리포트
가능하면 비교 결과를 하나의 보고서로 정리합니다.

- `reports/model_compare/model_compare_report_{stamp}.md`

---

## 8. 사용자 선호 포맷 반영
사용자는 백테스트 성능 지표를 아래 형식으로 보기를 선호합니다.

### A안 표준 포맷
- 1Y / 2Y / 3Y / 5Y / FULL
- 컬럼:
  - Start
  - End
  - 일수
  - CAGR
  - MDD
  - Sharpe
  - 평균 일간수익률
  - 일간 변동성

이번 TASK 09에서는 이 A안 포맷을 기본 비교표의 표준 포맷으로 사용합니다.

---

## 9. 사용자용 모델 / 관리용 모델 연결
TASK 09는 성과 비교 체계를 만들면서,
향후 Redbot 사용자용 모델과도 연결될 수 있어야 합니다.

### 관리용 모델
- S2
- S3
- S4
- S5
- S6
- Router

### 사용자용 모델(향후 연결)
- 안정형
- 균형형
- 성장형
- 자동전환형

이번 TASK에서는 사용자 UI를 직접 만들지 않지만,
비교 리포트에서 아래 연결 가능성을 열어 두는 것이 바람직합니다.

예시:
- 안정형 ↔ S6 / Router(stable bias)
- 균형형 ↔ S2 + S5 / Router(balanced bias)
- 성장형 ↔ S3 + S4 / Router(growth bias)
- 자동전환형 ↔ Router(auto)

---

## 10. 구현 범위

### 10.1 성과 집계 모듈
- 개별 모델 summary 집계
- 기간별 성과 계산
- 비용 반영 전/후 비교
- 연도별 성과 계산

### 10.2 비교 모듈
- 모델 간 성과 비교표 생성
- 국면별 성과 비교
- Router vs 단일 모델 비교
- 기여도/선택 빈도 집계(가능하면)

### 10.3 시각화 모듈
- equity curve 비교 차트
- drawdown 비교 차트
- 비용 민감도 비교 차트(선택)

### 10.4 리포트 생성
- CSV
- Markdown
- 가능하면 HTML

---

## 11. 권장 구현 파일
- `src/analytics/model_performance_comparator.py`
- `src/analytics/performance_period_report.py`
- `src/analytics/regime_performance_report.py`
- `src/analytics/cost_sensitivity_report.py`
- `src/analytics/render_model_compare_report.py`
- `scripts/run_model_comparison.py`
- `scripts/validate_model_comparison_outputs.py`

실제 구조에 맞게 파일명은 조정 가능하되,
영문 파일명 규칙과 역할 분리는 유지합니다.

---

## 12. 완료 기준 (Definition of Done)
아래를 모두 만족하면 완료입니다.

1. S2 / S3 / S4 / S5 / S6 / Router를 같은 기준으로 비교할 수 있다.
2. FULL / 1Y / 2Y / 3Y / 5Y 성과표가 생성된다.
3. 사용자 선호 A안 포맷 표가 생성된다.
4. 거래비용/슬리피지 반영 전후 비교가 가능하다.
5. summary / periods / yearly / regime 비교 산출물이 생성된다.
6. Router 통합모델과 개별 모델 비교가 가능하다.
7. validate 또는 smoke test가 통과한다.

---

## 13. 이번 TASK에서 하지 않을 것
- 새로운 알파 모델 개발
- Router 로직 자체의 대규모 변경
- 사용자 웹 UI 직접 연결
- 실거래 주문 연동
- TR/분배금 반영
- ETF PDF/구성종목 반영
- ML 기반 성과 최적화

---

## 14. 다음 TASK
- TASK 10: Redbot 사용자용 모델 / 관리용 모델 매핑 문서화
- TASK 11: 사용자용 포트폴리오 추천 리포트 구조 정리
- 이후: 일일 발행 / 웹 렌더링 / 서비스 연동 고도화

---

# B. Codex 실행지시문

## 작업명
Integrated Model Performance Comparison Framework

## 현재 상태
- TASK 01 완료: ETF 데이터 파이프라인 구축
- TASK 02 완료: ETF 코어 유니버스 / 메타 구축
- TASK 03 완료: 멀티에셋 데이터 모델 고정
- TASK 04 완료: ETF allocation backtest engine 구축
- TASK 05 완료: S6 Risk-Off Defensive Allocation 고도화
- TASK 06 완료: S4 Risk-On Offensive Allocation 고도화
- TASK 07 완료: S5 Neutral Mean-Reversion Allocation 고도화
- TASK 08 완료: Multi-Asset Regime Router 통합 실행 구조 구축

이제 TASK 09에서는
개별 모델과 Router 통합모델을 같은 기준으로 비교·평가하는
통합 성과 비교 체계를 구현한다.

## 중요 원칙
1. TASK 09는 새로운 알파 모델 개발이 아니라 비교/평가/리포팅 인프라 구축이다.
2. 모든 모델은 동일한 성과지표 정의를 사용해야 한다.
3. FULL뿐 아니라 1Y / 2Y / 3Y / 5Y 구간 성과를 반드시 병행할 것.
4. 거래비용/슬리피지 반영 여부를 명확히 구분할 것.
5. 결과는 CSV/표/차트 형태로 재현 가능해야 한다.
6. 사용자 선호 A안 포맷을 기본 비교표 포맷으로 반영할 것.
7. Redbot 사용자용 모델 연결 가능성을 고려하되, 이번 TASK는 내부 비교 체계 구축에 집중할 것.

## 비교 대상 모델
기본 비교 대상:
- `S2`
- `S3`
- `S4`
- `S5`
- `S6`
- `Router`

선택 비교 대상:
- `S3 core2`
- `TASK 04 기본 risk_on / neutral / risk_off`
- 기타 실험 모델

## 필수 성과 지표
- Start
- End
- 일수
- CAGR
- MDD
- Sharpe
- 평균 일간수익률
- 일간 변동성
- turnover
- rebalance_count

## 필수 비교 구간
- FULL
- 1Y
- 2Y
- 3Y
- 5Y

## 추가 비교 항목(가능하면)
- 누적 수익률
- 최대 연속 손실 기간
- 월간 승률
- 연도별 성과
- 거래비용 차감 전/후 차이
- 슬리피지 민감도
- 국면별 성과 분해

## 필수 출력 파일
- `reports/model_compare/model_compare_summary_{stamp}.csv`
- `reports/model_compare/model_compare_periods_{stamp}.csv`
- `reports/model_compare/model_compare_yearly_{stamp}.csv`
- `reports/model_compare/model_compare_regime_{stamp}.csv`
- `reports/model_compare/model_compare_cost_sensitivity_{stamp}.csv`

가능하면 추가:
- `reports/model_compare/model_compare_equity_{stamp}.png`
- `reports/model_compare/model_compare_drawdown_{stamp}.png`
- `reports/model_compare/model_compare_report_{stamp}.md`

## 사용자 선호 포맷 반영
기본 비교표는 아래 A안 형식을 사용하라.

행:
- 1Y
- 2Y
- 3Y
- 5Y
- FULL

열:
- Start
- End
- 일수
- CAGR
- MDD
- Sharpe
- 평균 일간수익률
- 일간 변동성

## 사용자용 / 관리용 연결 고려
관리용 모델:
- S2
- S3
- S4
- S5
- S6
- Router

향후 사용자용 연결:
- stable
- balanced
- growth
- auto

이번 TASK에서는 UI 구현이 아니라,
리포트 구조상 향후 사용자용 모델 매핑 가능성을 열어 둘 것.

## 구현 범위
1. 성과 집계 모듈
- 개별 모델 summary 집계
- 기간별 성과 계산
- 비용 반영 전/후 비교
- 연도별 성과 계산

2. 비교 모듈
- 모델 간 비교표 생성
- 국면별 성과 비교
- Router vs 단일 모델 비교
- 기여도/선택 빈도 집계(가능하면)

3. 시각화 모듈
- equity curve 비교
- drawdown 비교
- 비용 민감도 비교(선택)

4. 리포트 생성
- CSV
- Markdown
- 가능하면 HTML

## 권장 구현 파일
- `src/analytics/model_performance_comparator.py`
- `src/analytics/performance_period_report.py`
- `src/analytics/regime_performance_report.py`
- `src/analytics/cost_sensitivity_report.py`
- `src/analytics/render_model_compare_report.py`
- `scripts/run_model_comparison.py`
- `scripts/validate_model_comparison_outputs.py`

실제 프로젝트 구조에 맞춰 조정 가능하되,
영문 파일명과 역할 분리는 유지하라.

## 완료 기준
1. S2 / S3 / S4 / S5 / S6 / Router를 같은 기준으로 비교할 수 있다.
2. FULL / 1Y / 2Y / 3Y / 5Y 성과표가 생성된다.
3. 사용자 선호 A안 포맷 표가 생성된다.
4. 거래비용/슬리피지 반영 전후 비교가 가능하다.
5. summary / periods / yearly / regime 비교 산출물이 생성된다.
6. Router 통합모델과 개별 모델 비교가 가능하다.
7. validate 또는 smoke test가 통과한다.

## 이번 TASK에서 하지 말 것
- 새로운 알파 모델 개발
- Router 로직 자체의 대규모 변경
- 사용자 웹 UI 직접 연결
- 실거래 주문 연동
- TR/분배금 반영
- ETF PDF/구성종목 반영
- ML 기반 성과 최적화

## 완료 후 보고 형식
1. 변경/추가 파일 목록
2. 각 파일 역할
3. 비교 대상 모델 목록
4. 성과지표 정의
5. 출력 파일 목록
6. 실행 방법
7. validate 방법
8. 개별 모델 vs Router 비교 결과 요약
9. 남은 리스크/주의사항
10. 다음 작업 제안
- TASK 10: Redbot 사용자용 모델 / 관리용 모델 매핑 문서화
- TASK 11: 사용자용 포트폴리오 추천 리포트 구조 정리

---

# C. Codex 개발 기본방향

- 이번 TASK 09의 핵심은 모델을 더 만드는 것이 아니라, 이미 만든 모델을 같은 기준으로 비교 가능하게 만드는 것이다.
- FULL 성과만 보여주지 말고 1Y / 2Y / 3Y / 5Y 구간을 반드시 병행한다.
- 사용자 선호 A안 표 포맷을 기본으로 삼아 비교 결과를 표준화한다.
- 개별 모델(S2/S3/S4/S5/S6)과 Router를 같은 테이블에서 비교할 수 있어야 한다.
- 비용 반영 전후 차이와 국면별 성과 차이도 가능한 범위에서 함께 본다.
- 결과는 Redbot 서비스의 사용자용 모델 설명과 향후 연결될 수 있도록 구조화한다.
- 비교 기준의 일관성이 숫자 하나를 좋게 만드는 것보다 더 중요하다.