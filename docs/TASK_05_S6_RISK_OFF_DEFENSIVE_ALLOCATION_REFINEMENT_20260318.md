# FILE: TASK_05_S6_RISK_OFF_DEFENSIVE_ALLOCATION_REFINEMENT_20260318.md

# TASK 05. S6 Risk-Off Defensive Allocation Refinement
## (하락 국면 방어형 ETF 자산배분 모델 고도화)

---

# A. TASK 문서용

## 1. 작업 목적
TASK 05의 목적은 TASK 04에서 구축한 ETF 자산배분 레이어 백테스트 엔진 위에,
하락 국면 전용 방어형 모델인 **S6 Risk-Off Defensive Allocation**의 실질적인 투자 규칙을 얹는 것입니다.

이번 단계의 핵심은 다음과 같습니다.

- 하락 국면에서 MDD를 줄이는 방어형 자산배분 규칙 구현
- 채권, 달러, 금, 현금대체, 인버스 ETF의 조합 구조 정교화
- 단순 골격 수준의 ETF allocation 엔진을 실제 모델 수준으로 고도화
- 향후 S4(상승형), S5(보합형), 국면 Router 통합의 기반 확보

이번 TASK는 “완전한 최적화 모델”을 만드는 것이 아니라,
**재현 가능하고 설명 가능한 방어형 모델의 v1.0**을 만드는 단계입니다.

---

## 2. 작업 배경
현재까지의 진행 상황은 다음과 같습니다.

- TASK 01: ETF 마스터 유니버스, ETF 일봉 수집, `prices_daily` 적재, 최소 validate 완료
- TASK 02: ETF 분류(rule + override), 코어 ETF 유니버스, 유동성 기준, group coverage 구축
- TASK 03: 멀티에셋 공통 데이터 모델(`asset_type`, `instrument_master`, `etf_meta`) 고정
- TASK 04: ETF 자산배분 레이어 백테스트 엔진 구축
  - `risk_on / neutral / risk_off` 모드 지원
  - 리밸런싱 구조
  - summary / equity / weights / trades 산출물 생성

이제 다음 단계는,
TASK 04에서 만든 일반 ETF allocation 엔진의 `risk_off` 포트폴리오를
실제 독립 모델 수준의 **S6 방어형 전략**으로 고도화하는 것입니다.

---

## 3. 핵심 원칙
1. S6는 하락 국면 전용 방어형 모델입니다.
2. 목적은 수익 극대화보다 **MDD 방어와 변동성 축소**입니다.
3. 직접 공매도는 하지 않습니다.
4. 헤지는 인버스 ETF로만 제한적으로 구현합니다.
5. 레버리지 ETF는 기본 제외합니다.
6. TR/분배금 반영은 이번 범위에서 제외합니다.
7. 복잡한 최적화보다 단순하고 해석 가능한 규칙을 우선합니다.
8. 기존 TASK 04 엔진을 최대한 재사용하고, 별도 전략 레이어로 분리합니다.
9. 결과는 반드시 CSV와 summary 지표로 재현 가능해야 합니다.

---

## 4. 모델 개요
S6는 하락 국면에서 아래 자산군을 조합하는 방어형 자산배분 모델입니다.

### 사용 자산군
- `bond_long`
- `bond_short`
- `fx_usd`
- `commodity_gold`
- `cash` 또는 현금대체
- `hedge_inverse_kr`

### 기본 설계 방향
- 금리 하락/위험회피 구간: 장기채 비중 확대 가능
- 불확실성 확대 구간: 단기채 / 현금대체 비중 유지
- 환율 급등/리스크오프 구간: 달러 노출 방어 강화
- 시스템 리스크 구간: 금 비중 보완
- 급락 방어: 인버스 ETF 제한적 활용

---

## 5. 작업 목표
이번 TASK 05의 목표는 아래와 같습니다.

1. S6 전용 포트폴리오 규칙 모듈을 만든다.
2. `risk_off` 모드를 단일 고정비중이 아닌 **조건부 방어형 배분 구조**로 고도화한다.
3. 자산군별 최소/최대 비중 제한을 둔다.
4. 인버스 ETF 비중을 통제된 범위에서만 사용한다.
5. 장기채 / 단기채 / 달러 / 금 / 현금대체 간 배분 규칙을 명확히 정의한다.
6. 설정값(config) 기반으로 규칙을 조정 가능하게 한다.
7. 성과평가 지표를 통해 TASK 04 기본형과 비교 가능하게 한다.

---

## 6. 입력 데이터
### 필수 입력
- `prices_daily`
- `instrument_master`
- `etf_meta`
- `universe_etf_core_{asof}.csv` 또는 동등 조회 함수
- 기존 국면 데이터 (`regime_history` 등)
- TASK 04 ETF allocation engine 산출 구조

### 사용 메타
- `asset_class`
- `group_key`
- `currency_exposure`
- `is_inverse`
- `is_leveraged`
- `liquidity_20d_value`
- `core_eligible`

---

## 7. S6 포트폴리오 규칙 초안

### 7.1 기본 자산군 바스켓
- 장기채: `bond_long`
- 단기채: `bond_short`
- 달러: `fx_usd`
- 금: `commodity_gold`
- 현금대체: `cash`
- 헤지: `hedge_inverse_kr`

### 7.2 기본 목표 비중 예시
초기 기본값 예시:

- `bond_long`: 25%
- `bond_short`: 25%
- `fx_usd`: 20%
- `commodity_gold`: 15%
- `cash`: 10%
- `hedge_inverse_kr`: 5%

주의:
- 위 값은 고정 확정값이 아니라 **초기 설정안**입니다.
- 반드시 config 파일로 분리합니다.

### 7.3 비중 제한 예시
- `bond_long`: 0% ~ 40%
- `bond_short`: 10% ~ 50%
- `fx_usd`: 0% ~ 30%
- `commodity_gold`: 0% ~ 25%
- `cash`: 0% ~ 30%
- `hedge_inverse_kr`: 0% ~ 15%

### 7.4 인버스 사용 원칙
- 인버스 ETF는 방어 보조 수단으로만 사용합니다.
- 기본 비중은 낮게 유지합니다.
- 인버스 비중 상한은 config에서 통제합니다.
- 인버스 ETF가 없거나 부적절할 경우 0% 허용합니다.

---

## 8. 조건부 배분 규칙
S6는 단순 고정비중이 아니라, 최소한 아래 조건에 따라 비중 조정이 가능해야 합니다.

### 8.1 변동성 확대 시
- 단기채 / 현금 비중 확대
- 인버스 ETF 비중 제한적 확대 가능

### 8.2 급락 구간 시
- 인버스 ETF 허용 범위 내 확대
- 주식성 노출 완전 제거
- 장기채보다 단기채/현금 우선 여부를 옵션화

### 8.3 달러 강세 시
- `fx_usd` 비중 확대 가능

### 8.4 안전자산 선호 강화 시
- `commodity_gold` 비중 확대 가능

### 8.5 금리 하락 친화 구간 시
- `bond_long` 비중 확대 가능

중요:
- 위 조건들은 모두 **명시적 규칙**으로 구현합니다.
- 머신러닝 최적화는 이번 범위에서 제외합니다.

---

## 9. 리밸런싱 규칙
### 지원
- 주간(`W`)
- 월간(`M`)

### 원칙
- 리밸런싱일 기준 목표비중 재산출
- 목표비중과 현재비중 차이에 따라 매매
- 거래비용 및 슬리피지 반영
- 가격 없는 ETF는 매매 제외
- 해당 group ETF가 없으면 대체자산 또는 현금 처리

---

## 10. 구현 범위

### 10.1 전략 모듈
- S6 전용 allocator / strategy 모듈 구현

### 10.2 config 분리
- 기본 비중
- 자산군별 min/max
- 인버스 상한
- 거래비용
- 슬리피지
- 리밸런싱 주기
- fallback 규칙

### 10.3 성과비교 기능
최소 아래 비교가 가능해야 합니다.
- TASK 04 기본 risk_off vs TASK 05 S6 refined
- FULL / 1Y / 2Y / 3Y / 5Y 성과 비교

### 10.4 산출물
- summary CSV
- equity CSV
- weights CSV
- trades CSV
- 비교 summary CSV (가능하면)

---

## 11. 권장 구현 파일
- `src/backtest/run_backtest_s6_defensive_allocation.py`
- `src/backtest/portfolio/s6_defensive_allocator.py`
- `src/backtest/configs/s6_defensive_config.py`
- `src/backtest/core/s6_backtest_runner.py`
- `scripts/validate_s6_defensive_backtest.py`

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

---

## 13. 완료 기준 (Definition of Done)
아래를 모두 만족하면 완료입니다.

1. S6 방어형 백테스트 실행이 가능하다.
2. 자산군별 기본/조건부 비중 규칙이 config 기반으로 동작한다.
3. 인버스 ETF 사용이 제한된 범위 내에서 통제된다.
4. summary / equity / weights / trades 산출물이 생성된다.
5. TASK 04 기본형 risk_off와 비교 가능한 결과가 나온다.
6. 기존 ETF allocation engine과 충돌하지 않는다.
7. validate 또는 smoke test가 통과한다.

---

## 14. 이번 TASK에서 하지 않을 것
- 머신러닝 기반 비중 최적화
- 리스크 패리티 본격 도입
- TR/분배금 반영
- ETF PDF/구성종목 반영
- 직접 공매도
- 실거래 연동
- 웹 UI 연결

---

## 15. 다음 TASK
- TASK 06: S4 Risk-On ETF Allocation Model
- TASK 07: S5 Neutral ETF Allocation Model
- TASK 08: 국면 Router 통합 실행 구조
- TASK 09: 신규 모델(S2/S3/S4/S5/S6) 통합 성과 비교 체계

---

# B. Codex 실행지시문

## 작업명
S6 Risk-Off Defensive Allocation Refinement

## 현재 상태
- TASK 01 완료: ETF 마스터 유니버스 / ETF 일봉 / `prices_daily` 적재 / validate
- TASK 02 완료: ETF 분류 / 코어 ETF 유니버스 / 유동성 기준 / 메타 구축
- TASK 03 완료: `asset_type`, `instrument_master`, `etf_meta`, 공통 조회 구조 고정
- TASK 04 완료: ETF allocation backtest engine 구축 (`risk_on / neutral / risk_off`)

이제 TASK 05에서는 TASK 04의 일반 `risk_off` 포트폴리오를
독립 모델 수준의 **S6 방어형 전략**으로 고도화한다.

## 중요 원칙
1. S6의 목적은 수익 극대화보다 MDD 방어다.
2. 직접 공매도는 하지 말 것.
3. 헤지는 인버스 ETF로만 제한적으로 구현할 것.
4. 레버리지 ETF는 제외할 것.
5. TR/분배금은 반영하지 말 것.
6. 기존 TASK 04 엔진을 최대한 재사용할 것.
7. 규칙은 단순하고 설명 가능해야 하며 config 기반이어야 한다.

## 구현 목표
1. S6 전용 allocator / strategy 모듈 구현
2. 하락 국면용 방어 자산군 배분 규칙 구현
3. 조건부 비중 조정 규칙 구현
4. 자산군별 min/max 제약 구현
5. 인버스 ETF 비중 상한 구현
6. TASK 04 기본 risk_off와 비교 가능한 summary 생성
7. validate 또는 smoke test 구현

## 사용 자산군
- `bond_long`
- `bond_short`
- `fx_usd`
- `commodity_gold`
- `cash`
- `hedge_inverse_kr`

## 초기 기본 비중 예시
- `bond_long`: 25%
- `bond_short`: 25%
- `fx_usd`: 20%
- `commodity_gold`: 15%
- `cash`: 10%
- `hedge_inverse_kr`: 5%

반드시 config로 분리할 것.

## 자산군별 비중 제한 예시
- `bond_long`: 0% ~ 40%
- `bond_short`: 10% ~ 50%
- `fx_usd`: 0% ~ 30%
- `commodity_gold`: 0% ~ 25%
- `cash`: 0% ~ 30%
- `hedge_inverse_kr`: 0% ~ 15%

## 조건부 규칙 요구사항
아래 조건에 따라 비중 조정 가능 구조를 구현하라.

1. 변동성 확대 시
- 단기채 / 현금 비중 확대
- 인버스 ETF 제한적 확대 가능

2. 급락 구간 시
- 인버스 ETF 허용 범위 내 확대
- 주식성 노출 제거
- 장기채보다 단기채/현금 우선 여부를 옵션화

3. 달러 강세 시
- `fx_usd` 비중 확대 가능

4. 안전자산 선호 강화 시
- `commodity_gold` 비중 확대 가능

5. 금리 하락 친화 구간 시
- `bond_long` 비중 확대 가능

중요:
- 머신러닝 최적화 금지
- 명시적 규칙 기반으로 구현할 것

## 리밸런싱
- `W`, `M` 지원
- 리밸런싱일에 목표비중 재산출
- 거래비용/슬리피지 반영 구조 유지
- 가격 없는 ETF는 제외
- group 후보가 없으면 대체자산 또는 현금 처리

## 권장 구현 파일
- `src/backtest/run_backtest_s6_defensive_allocation.py`
- `src/backtest/portfolio/s6_defensive_allocator.py`
- `src/backtest/configs/s6_defensive_config.py`
- `src/backtest/core/s6_backtest_runner.py`
- `scripts/validate_s6_defensive_backtest.py`

실제 프로젝트 구조에 맞춰 조정 가능하되,
영문 파일명과 역할 분리는 유지하라.

## 산출물
1. S6 백테스트 실행 스크립트
2. S6 config
3. 결과 CSV
   - summary
   - equity
   - weights
   - trades
4. validate 또는 smoke test
5. TASK 05 문서

## 비교 요구사항
아래 비교가 가능해야 한다.
- TASK 04 기본 risk_off vs TASK 05 S6 refined
- FULL / 1Y / 2Y / 3Y / 5Y 성과 비교

## 완료 기준
1. S6 방어형 백테스트가 실행된다
2. 조건부 비중 규칙이 동작한다
3. 인버스 ETF 비중이 제한 범위 내에서 통제된다
4. summary / equity / weights / trades가 생성된다
5. TASK 04 risk_off 대비 비교 결과가 나온다
6. 기존 ETF allocation engine과 충돌이 없다
7. validate 또는 smoke test가 통과한다

## 이번 TASK에서 하지 말 것
- ML 기반 비중 최적화
- 리스크 패리티 본격 도입
- TR/분배금 반영
- ETF PDF/구성종목 반영
- 직접 공매도
- 실거래 연동
- 웹 UI 연결

## 완료 후 보고 형식
1. 변경/추가 파일 목록
2. 각 파일 역할
3. S6 규칙 설명
4. config 설명
5. 실행 방법
6. validate 방법
7. 생성 산출물 목록
8. TASK 04 risk_off와의 비교 결과
9. 남은 리스크/주의사항
10. 다음 작업 제안
- TASK 06: S4 Risk-On ETF Allocation Model
- TASK 07: S5 Neutral ETF Allocation Model

---

# C. Codex 개발 기본방향

- 이번 TASK 05의 핵심은 TASK 04의 일반 risk_off 포트폴리오를 독립 전략 수준의 S6 모델로 고도화하는 것이다.
- 목표는 고수익이 아니라 하락장 방어, MDD 축소, 변동성 관리다.
- 직접 공매도는 하지 않고 인버스 ETF를 제한적으로만 사용한다.
- 규칙은 단순하고 명시적이어야 하며, 모든 주요 수치는 config로 분리한다.
- TASK 04 엔진을 최대한 재사용하고, 기존 구조를 깨지 않는 방향으로 확장한다.
- 결과는 반드시 summary / equity / weights / trades 형태로 남겨 비교 가능하게 한다.
