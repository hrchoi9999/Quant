# FILE: TASK_08_MULTI_ASSET_REGIME_ROUTER_INTEGRATION_20260318.md

# TASK 08. Multi-Asset Regime Router Integration
## (국면 기반 상위 통합 실행 구조)

---

# A. TASK 문서용

## 1. 작업 목적
TASK 08의 목적은 지금까지 구축한 개별 모델들을 하나의 상위 실행 구조로 통합하는 것입니다.

즉,
- 기존 주식 모델 `S2`, `S3`
- ETF/멀티에셋 basic 모델 `S4`, `S5`, `S6`
를 각각 따로 실행하는 단계를 넘어,

**시장 국면(regime)에 따라 어떤 모델을 사용할지 결정하고,**
**주식 슬리브와 ETF 슬리브를 어떤 비중으로 병합할지 결정하는**
상위 Router를 구현하는 것이 이번 TASK의 핵심입니다.

이번 단계가 완료되면,
비로소 Redbot의 최종형에 가까운
**“국면 대응형 멀티에셋 통합 모델”**의 첫 버전이 만들어집니다.

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

이제 다음 단계는,
각 모델을 개별적으로 보는 것이 아니라,
**국면별로 적절한 모델을 선택하고 병합하는 상위 의사결정 구조**를 만드는 것입니다.

---

## 3. 핵심 원칙
1. Router는 새로운 알파 모델이 아니라 **상위 배분/선택 엔진**입니다.
2. 기존 모델(S2/S3/S4/S5/S6)을 재사용하고, Router는 이들의 사용 비중과 실행 방식을 결정합니다.
3. 국면 판정 로직 자체의 대규모 변경은 이번 범위에서 제외합니다.
4. Router는 **설명 가능하고 재현 가능한 규칙 기반**으로 먼저 구현합니다.
5. 직접 공매도는 하지 않으며, 하락 헤지는 S6 내부의 인버스 ETF로만 처리합니다.
6. Router는 반드시 **의사결정 로그(decision log)** 를 남겨야 합니다.
7. Redbot 서비스 목표를 고려해,
   내부 관리용 모델 구조와 사용자용 상품 구조를 동시에 염두에 둡니다.

---

## 4. Router의 역할
Router는 아래 4가지 역할을 수행합니다.

### 4.1 국면 입력
- 외부에서 계산된 시장 국면(regime)을 입력받습니다.
- 국면은 최소 아래 3가지로 구분합니다.
  - `risk_on`
  - `neutral`
  - `risk_off`

### 4.2 모델 선택
국면에 따라 어떤 내부 모델을 사용할지 결정합니다.

예시:
- 상승장(`risk_on`): S3 + S4
- 보합장(`neutral`): S2 + S5
- 하락장(`risk_off`): S6 중심 + 필요시 S2 저비중

### 4.3 슬리브 비중 결정
- 주식 슬리브와 ETF 슬리브의 비중을 국면별로 정합니다.
- 예:
  - `risk_on`: 주식 70%, ETF 30%
  - `neutral`: 주식 40%, ETF 60%
  - `risk_off`: 주식 10%, ETF 90%

### 4.4 최종 포트폴리오 병합
- 선택된 모델 결과를 하나의 최종 포트폴리오로 합칩니다.
- 최종 weights / holdings / trades / summary를 생성합니다.

---

## 5. 내부 관리용 모델 구조
이번 TASK 08에서 Router가 병합하는 내부 관리용 모델은 아래와 같습니다.

### 5.1 주식 슬리브
- `S2`: 품질/성장 기반 안정형 주식 모델
- `S3`: 가격 가속/상승 탄력형 주식 모델

### 5.2 ETF/멀티에셋 슬리브
- `S4`: 상승 국면용 공격형 ETF allocation
- `S5`: 보합 국면용 중립형 ETF allocation
- `S6`: 하락 국면용 방어형 ETF allocation

### 5.3 상위 계층
- `Router`: 국면에 따라 내부 모델을 선택/병합하는 최종 엔진

---

## 6. 사용자용 상품 구조와의 연결
Redbot 서비스 목표를 고려하면, Router는 향후 아래 사용자용 모델과 연결될 수 있어야 합니다.

- `안정형`
- `균형형`
- `성장형`
- `자동전환형`

이번 TASK 08에서는 사용자 UI를 만들지 않지만,
내부적으로는 Router가 **service_profile** 개념을 지원할 수 있게 설계하는 것이 바람직합니다.

예시:
- `stable`: S6 비중 우선
- `balanced`: S2/S5 중심
- `growth`: S3/S4 중심
- `auto`: pure regime routing

---

## 7. Router 규칙 초안

### 7.1 국면별 기본 매핑
#### 상승장 (`risk_on`)
- 주식 슬리브:
  - S3 비중 확대
  - 필요 시 S2 소량 허용 가능
- ETF 슬리브:
  - S4 사용
- 기본 비중 예시:
  - 주식 70%
  - ETF 30%

#### 보합장 (`neutral`)
- 주식 슬리브:
  - S2 중심
- ETF 슬리브:
  - S5 사용
- 기본 비중 예시:
  - 주식 40%
  - ETF 60%

#### 하락장 (`risk_off`)
- 주식 슬리브:
  - S2 저비중 또는 0~소량
- ETF 슬리브:
  - S6 중심
- 기본 비중 예시:
  - 주식 10%
  - ETF 90%

주의:
- 위 비중은 고정 확정값이 아니라 **초기 설정안**입니다.
- 반드시 config 파일로 분리합니다.

### 7.2 fallback 원칙
- 특정 모델 실행 결과가 비어 있거나 실패하면 fallback 모델 또는 현금으로 대체
- 예:
  - S4 실패 시 broad ETF fallback
  - S5 후보 부족 시 bond_short / cash 확대
  - S6 후보 부족 시 cash / bond_short 중심 fallback

### 7.3 제약
- 주식 슬리브와 ETF 슬리브 합산 비중은 100%
- 인버스 사용은 S6 내부에서만 허용
- 레버리지는 전체 Router 구조에서 기본 금지
- 모델 실패/결측 시 반드시 decision log에 기록

---

## 8. 입력 데이터
### 필수 입력
- 시장 국면 데이터 (`regime_history` 또는 동등 구조)
- S2 실행 결과
- S3 실행 결과
- S4 실행 결과
- S5 실행 결과
- S6 실행 결과
- `prices_daily`
- `instrument_master`
- `etf_meta`

### 전제
- Router는 각 개별 모델의 백테스트 결과 또는 리밸런싱 시점 포트폴리오 결과를 입력으로 받을 수 있어야 합니다.
- 1차 버전에서는 모델별 “목표 비중/보유종목 결과”를 받아 단순 병합하는 방식으로 시작합니다.

---

## 9. 구현 범위

### 9.1 Router 엔진
- 국면 입력
- 국면 → 모델 매핑
- 모델별 목표 비중 결정
- 주식/ETF 슬리브 병합
- 최종 포트폴리오 산출

### 9.2 config 분리
- 국면별 슬리브 비중
- 모델별 fallback
- service_profile별 bias
- 거래비용
- 리밸런싱 주기
- 결측 처리 규칙

### 9.3 decision log
최소 아래를 기록합니다.
- date
- detected_regime
- selected_models
- stock_sleeve_weight
- etf_sleeve_weight
- service_profile
- fallback_used
- note / reason

### 9.4 산출물
- summary CSV
- equity CSV
- weights CSV
- trades CSV
- decision log CSV
- 가능하면 모델별 기여도 요약 CSV

---

## 10. 산출물 파일 예시
- `reports/backtest_router/router_summary_{stamp}.csv`
- `reports/backtest_router/router_equity_{stamp}.csv`
- `reports/backtest_router/router_weights_{stamp}.csv`
- `reports/backtest_router/router_trades_{stamp}.csv`
- `reports/backtest_router/router_decisions_{stamp}.csv`

---

## 11. 권장 구현 파일
- `src/backtest/run_backtest_multiasset_router.py`
- `src/backtest/router/multiasset_regime_router.py`
- `src/backtest/configs/router_config.py`
- `src/backtest/core/router_backtest_runner.py`
- `scripts/validate_multiasset_router.py`

실제 구조에 맞게 파일명은 조정 가능하되,
영문 파일명 규칙과 역할 분리는 유지합니다.

---

## 12. 성과 지표
summary에는 최소 아래 지표를 포함합니다.

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

추가 비교 구간:
- FULL
- 1Y
- 2Y
- 3Y
- 5Y

추가 비교 대상:
- S2 단독
- S3 단독
- S4 단독
- S5 단독
- S6 단독
- Router 통합모델

---

## 13. 완료 기준 (Definition of Done)
아래를 모두 만족하면 완료입니다.

1. Router 기반 통합 백테스트 실행이 가능하다.
2. `risk_on / neutral / risk_off` 국면에 따라 모델 선택이 동작한다.
3. 주식 슬리브 + ETF 슬리브 병합이 정상 동작한다.
4. summary / equity / weights / trades / decisions 산출물이 생성된다.
5. fallback 규칙과 decision log가 동작한다.
6. 기존 개별 모델과 충돌하지 않는다.
7. validate 또는 smoke test가 통과한다.

---

## 14. 이번 TASK에서 하지 않을 것
- 국면 산출 로직 자체의 대규모 개편
- ML 기반 Router 최적화
- 사용자 웹 UI 직접 연결
- 실거래 주문 연동
- TR/분배금 반영
- ETF PDF/구성종목 반영
- 직접 공매도

---

## 15. 다음 TASK
- TASK 09: 모델 통합 성과 비교 체계
- TASK 10: Redbot 사용자용 모델(안정형/균형형/성장형/자동전환형) 매핑 및 서비스 설명체계 정리
- 이후: 운영 자동화 / 일일 발행 / 웹 연동 고도화

---

# B. Codex 실행지시문

## 작업명
Multi-Asset Regime Router Integration

## 현재 상태
- TASK 01 완료: ETF 마스터 유니버스 / ETF 일봉 / `prices_daily` 적재 / validate
- TASK 02 완료: ETF 분류 / 코어 ETF 유니버스 / 유동성 기준 / 메타 구축
- TASK 03 완료: `asset_type`, `instrument_master`, `etf_meta`, 공통 조회 구조 고정
- TASK 04 완료: ETF allocation backtest engine 구축 (`risk_on / neutral / risk_off`)
- TASK 05 완료: S6 Risk-Off Defensive Allocation 고도화
- TASK 06 완료: S4 Risk-On Offensive Allocation 고도화
- TASK 07 완료: S5 Neutral Mean-Reversion Allocation 고도화

이제 TASK 08에서는 개별 모델들을 하나의 상위 Router로 통합하여,
국면별로 어떤 모델을 선택하고 어떻게 병합할지 결정하는 구조를 구현한다.

## 중요 원칙
1. Router는 새로운 알파 모델이 아니라 상위 선택/배분 엔진이다.
2. 기존 모델(S2/S3/S4/S5/S6)을 최대한 재사용할 것.
3. 국면 산출 로직 자체는 크게 바꾸지 말 것.
4. 규칙은 단순하고 설명 가능해야 하며 config 기반이어야 한다.
5. 반드시 decision log를 남길 것.
6. Redbot 서비스 목표를 고려해 service_profile 개념을 수용 가능한 구조로 만들 것.
7. 직접 공매도는 하지 말 것.

## 구현 목표
1. 국면 기반 Router 엔진 구현
2. 국면 → 모델 매핑 규칙 구현
3. 주식 슬리브 + ETF 슬리브 병합 규칙 구현
4. service_profile 지원 가능한 구조 구현
5. summary / equity / weights / trades / decisions 산출물 생성
6. validate 또는 smoke test 구현

## 내부 관리용 모델
### 주식 슬리브
- `S2`
- `S3`

### ETF 슬리브
- `S4`
- `S5`
- `S6`

### 상위 계층
- `Router`

## 사용자용 연결 고려
향후 아래 사용자용 모델과 연결될 수 있도록 service_profile 개념을 열어 둘 것.
- `stable`
- `balanced`
- `growth`
- `auto`

1차 버전에서는 UI 구현이 아니라,
config 수준에서 profile bias만 지원해도 충분하다.

## 국면별 기본 매핑 예시
### `risk_on`
- stock sleeve: `S3` 중심
- ETF sleeve: `S4`
- 기본 비중 예시:
  - stock 70%
  - ETF 30%

### `neutral`
- stock sleeve: `S2`
- ETF sleeve: `S5`
- 기본 비중 예시:
  - stock 40%
  - ETF 60%

### `risk_off`
- stock sleeve: `S2` 저비중 또는 0~소량
- ETF sleeve: `S6`
- 기본 비중 예시:
  - stock 10%
  - ETF 90%

반드시 config로 분리할 것.

## fallback 규칙 요구사항
- 특정 모델 결과가 비어 있거나 실패하면 fallback 모델 또는 현금으로 대체
- fallback 발생 시 decision log에 반드시 기록
- 예:
  - S4 실패 시 broad ETF fallback
  - S5 후보 부족 시 bond_short / cash 확대
  - S6 후보 부족 시 cash / bond_short fallback

## 입력 데이터
- 시장 국면 데이터 (`regime_history` 또는 동등 구조)
- S2 결과
- S3 결과
- S4 결과
- S5 결과
- S6 결과
- `prices_daily`
- `instrument_master`
- `etf_meta`

## 구현 범위
1. Router 엔진
- 국면 입력
- 국면 → 모델 매핑
- 모델별 목표 비중 결정
- 주식/ETF 슬리브 병합
- 최종 포트폴리오 산출

2. config
- 국면별 슬리브 비중
- fallback 규칙
- service_profile bias
- 거래비용
- 리밸런싱 주기
- 결측 처리 규칙

3. decision log
최소 아래 필드를 포함할 것.
- `date`
- `detected_regime`
- `selected_models`
- `stock_sleeve_weight`
- `etf_sleeve_weight`
- `service_profile`
- `fallback_used`
- `note`

## 권장 구현 파일
- `src/backtest/run_backtest_multiasset_router.py`
- `src/backtest/router/multiasset_regime_router.py`
- `src/backtest/configs/router_config.py`
- `src/backtest/core/router_backtest_runner.py`
- `scripts/validate_multiasset_router.py`

실제 프로젝트 구조에 맞춰 조정 가능하되,
영문 파일명과 역할 분리는 유지하라.

## 산출물
1. Router 실행 스크립트
2. Router config
3. 결과 CSV
   - summary
   - equity
   - weights
   - trades
   - decisions
4. validate 또는 smoke test
5. TASK 08 문서

## 비교 요구사항
아래 비교가 가능해야 한다.
- S2 단독
- S3 단독
- S4 단독
- S5 단독
- S6 단독
- Router 통합모델

또한 가능하면 아래 구간 비교도 포함한다.
- FULL
- 1Y
- 2Y
- 3Y
- 5Y

## 완료 기준
1. Router 기반 통합 백테스트가 실행된다
2. `risk_on / neutral / risk_off`에 따라 모델 선택이 동작한다
3. 주식 슬리브 + ETF 슬리브 병합이 동작한다
4. summary / equity / weights / trades / decisions가 생성된다
5. fallback 규칙과 decision log가 동작한다
6. 기존 개별 모델과 충돌이 없다
7. validate 또는 smoke test가 통과한다

## 이번 TASK에서 하지 말 것
- 국면 산출 로직 대규모 변경
- ML 기반 Router 최적화
- 사용자 웹 UI 직접 연결
- 실거래 주문 연동
- TR/분배금 반영
- ETF PDF/구성종목 반영
- 직접 공매도

## 완료 후 보고 형식
1. 변경/추가 파일 목록
2. 각 파일 역할
3. 국면 → 모델 매핑 설명
4. service_profile 구조 설명
5. fallback 규칙 설명
6. 실행 방법
7. validate 방법
8. 생성 산출물 목록
9. 개별 모델 대비 Router 비교 결과
10. 남은 리스크/주의사항
11. 다음 작업 제안
- TASK 09: 모델 통합 성과 비교 체계
- TASK 10: Redbot 사용자용 모델 매핑 정리

---

# C. Codex 개발 기본방향

- 이번 TASK 08의 핵심은 개별 모델(S2/S3/S4/S5/S6)을 상위 Router로 통합하는 것이다.
- Router는 알파 엔진이 아니라 선택/배분/병합 엔진이다.
- 국면별로 주식 슬리브와 ETF 슬리브를 어떻게 섞을지 명시적 규칙으로 먼저 구현한다.
- 규칙은 단순하고 설명 가능해야 하며, 주요 수치는 config로 분리한다.
- 반드시 decision log를 남겨서 Redbot 서비스에서 설명 가능한 구조로 만든다.
- 내부 관리용 모델 구조와 향후 사용자용 모델(`stable / balanced / growth / auto`) 매핑 가능성을 동시에 고려한다.
- 결과는 반드시 summary / equity / weights / trades / decisions 형태로 남겨 비교 가능하게 한다.