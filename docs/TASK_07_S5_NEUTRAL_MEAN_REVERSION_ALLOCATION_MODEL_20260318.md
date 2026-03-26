# FILE: TASK_07_S5_NEUTRAL_MEAN_REVERSION_ALLOCATION_MODEL_20260318.md

# TASK 07. S5 Neutral Mean-Reversion Allocation Model
## (보합 국면용 중립형 ETF/멀티에셋 basic 모델)

---

# A. TASK 문서용

## 1. 작업 목적
TASK 07의 목적은 TASK 04에서 구축한 ETF 자산배분 백테스트 엔진,
TASK 05의 S6 방어형 모델,
TASK 06의 S4 상승형 모델에 이어,
보합 국면 전용 중립형 모델인 **S5 Neutral Mean-Reversion Allocation**의 v1.0을 구현하는 것입니다.

이번 단계의 핵심은 다음과 같습니다.

- 보합 국면에서 과매도/되돌림 특성을 활용하는 중립형 포트폴리오 규칙 구현
- 배당/저변동/현금대체/단기채 ETF를 활용한 neutral 배분 구조 도입
- 단순 고정비중이 아니라 변동성 수축, 과매도, 되돌림 신호를 반영한 조건부 배분 구조 구현
- 향후 주식 슬리브(S2, S5_stock 등)와 병합 가능한 상위 멀티에셋 구조의 기초 마련

이번 TASK는 “완전한 최적화 모델”이 아니라,
**보합 국면에서 설명 가능하고 재현 가능한 중립형 basic 모델의 v1.0**을 만드는 단계입니다.

> 관리용 모델명: **S5**
> 사용자용 연결 포지션: 향후 **균형형**의 핵심 엔진 중 하나로 활용 예정

---

## 2. 작업 배경
현재까지의 진행 상황은 다음과 같습니다.

- TASK 01: ETF 마스터 유니버스 생성, ETF 일봉 수집, `prices_daily` 적재, 최소 validate 완료
- TASK 02: ETF 분류(rule + override), 코어 ETF 유니버스(core), 유동성 기준, group coverage 구축
- TASK 03: 멀티에셋 공통 데이터 모델(`asset_type`, `instrument_master`, `etf_meta`) 고정
- TASK 04: ETF 자산배분 레이어 백테스트 엔진 구축
  - `risk_on / neutral / risk_off` 모드 지원
  - 리밸런싱 구조
  - summary / equity / weights / trades 산출물 생성
- TASK 05: S6 Risk-Off Defensive Allocation 고도화
  - 하락 국면 방어형 모델 고도화
- TASK 06: S4 Risk-On Offensive Allocation 고도화
  - 상승 국면 공격형 모델 고도화

이제 다음 단계는,
보합 국면에서 **배당/저변동/커버드콜 + 채권/현금대체**를 활용하고,
단기 과매도/되돌림 특성을 반영하는 중립형 basic 모델을 구축하는 것입니다.

---

## 3. 핵심 원칙
1. S5는 보합 국면 전용 중립형 모델입니다.
2. 목적은 강한 추세 추종이 아니라 **변동성 완충 + 과매도/되돌림 알파**입니다.
3. 하락장 방어는 S6의 영역이고, 강한 추세 추종은 S4의 영역입니다.
4. S5는 turnover가 높아질 수 있으므로 거래비용/슬리피지 반영이 필수입니다.
5. 직접 공매도는 하지 않습니다.
6. 인버스 ETF는 S5에서 기본 사용하지 않습니다.
7. 레버리지 ETF는 기본 제외합니다.
8. TR/분배금 반영은 이번 범위에서 제외합니다.
9. 복잡한 최적화보다 단순하고 해석 가능한 규칙을 우선합니다.
10. 기존 TASK 04 엔진을 최대한 재사용하고, 별도 전략 레이어로 분리합니다.
11. 결과는 반드시 CSV와 summary 지표로 재현 가능해야 합니다.

---

## 4. 모델 개요
S5는 보합 국면에서 아래 자산군/그룹을 활용하는 중립형 자산배분 모델입니다.

### 사용 자산군 / 그룹
- `equity_kr_broad`
- `bond_short`
- `cash`
- (확장 가능) `equity_low_vol`
- (확장 가능) `equity_dividend`
- (확장 가능) `equity_covered_call`

### 기본 설계 방향
- 추세 강도가 낮고 변동성이 수축된 국면에서 중립 운용
- broad equity는 낮은 비중으로 유지
- 저변동/배당/커버드콜 성격 ETF가 있으면 우선 활용
- 단기 과매도 신호 발생 시 되돌림 비중 확대
- 불확실성이 커지면 bond_short / cash 비중 확대
- 본격 방어 전환은 하지 않으며, 강한 risk-off는 S6 또는 Router 단계에서 처리

---

## 5. 작업 목표
이번 TASK 07의 목표는 아래와 같습니다.

1. S5 전용 포트폴리오 규칙 모듈을 만든다.
2. `neutral` 모드를 단일 고정비중이 아닌 **보합장 회귀형 배분 구조**로 고도화한다.
3. broad / 저변동 / 배당 / 커버드콜 / bond_short / cash 간 비중 배분 규칙을 명확히 정의한다.
4. ADX / 변동성 수축 / RSI / 볼린저 성격의 최소 신호를 반영한다.
5. 자산군별 최소/최대 비중 제한을 둔다.
6. 설정값(config) 기반으로 규칙을 조정 가능하게 한다.
7. TASK 04 기본 neutral과 비교 가능한 성과평가 체계를 만든다.

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

## 7. S5 포트폴리오 규칙 초안

### 7.1 기본 바스켓
- broad neutral beta: `equity_kr_broad`
- 방어/대기: `bond_short`
- 현금대체: `cash`
- (선택) 저변동 ETF: `equity_low_vol`
- (선택) 배당 ETF: `equity_dividend`
- (선택) 커버드콜 ETF: `equity_covered_call`

### 7.2 기본 목표 비중 예시
초기 기본값 예시:

- `equity_kr_broad`: 25%
- `equity_low_vol`: 20%
- `equity_dividend`: 15%
- `equity_covered_call`: 10%
- `bond_short`: 20%
- `cash`: 10%

주의:
- 위 값은 고정 확정값이 아니라 **초기 설정안**입니다.
- 반드시 config 파일로 분리합니다.
- 실제 그룹 커버리지가 없으면 fallback 규칙을 적용합니다.
- low_vol / dividend / covered_call 그룹이 아직 core에 없다면 1차 버전에서는 broad + bond_short + cash 구조로 시작해도 됩니다.

### 7.3 비중 제한 예시
- `equity_kr_broad`: 10% ~ 40%
- `equity_low_vol`: 0% ~ 30%
- `equity_dividend`: 0% ~ 25%
- `equity_covered_call`: 0% ~ 20%
- `bond_short`: 10% ~ 40%
- `cash`: 0% ~ 30%

### 7.4 사용 금지 / 제한 원칙
- `is_leveraged=True` ETF는 기본 제외
- `is_inverse=True` ETF는 S5에서 사용 금지
- 유동성 부족 ETF는 제외
- 가격 히스토리 부족 ETF는 제외

---

## 8. 조건부 배분 규칙
S5는 단순 고정비중이 아니라, 최소한 아래 조건에 따라 비중 조정이 가능해야 합니다.

### 8.1 ADX 낮음 / 추세 약함
- neutral 포지션 유지
- broad 비중 과도 확대 금지
- 저변동 / 배당 / 커버드콜 / bond_short 비중 유지 또는 확대

### 8.2 변동성 수축 시
- mean-reversion 성격 자산 비중 확대 가능
- broad의 단기 되돌림 참여 허용

### 8.3 단기 과매도 신호 발생 시
- broad 또는 저변동 ETF 비중 확대 가능
- cash / bond_short 일부 축소 가능

### 8.4 되돌림 완료 / 반등 과열 시
- broad 또는 회귀 노출 일부 축소
- bond_short / cash 회복

### 8.5 불확실성 확대 시
- bond_short / cash 비중 확대
- 주식성 노출 축소
- 단, 강한 risk-off 전환 자체는 하지 않음

중요:
- 위 조건들은 모두 **명시적 규칙**으로 구현합니다.
- 머신러닝 최적화는 이번 범위에서 제외합니다.

---

## 9. 신호/판정 규칙(초기안)
이번 TASK 07에서는 ETF allocation 모델이므로,
개별주식 수준의 정교한 mean-reversion 엔진이 아니라
**ETF 그룹/대표 ETF 단위의 간단한 neutral 판정 신호**를 사용합니다.

예시 신호:
- ADX 낮음 여부
- 최근 10~20일 변동성 수축 여부
- RSI(2~5) 과매도 영역 여부
- 볼린저 하단 접촉 또는 이탈 후 회복 여부
- 최근 N일 낙폭 대비 반등 신호

주의:
- 이것은 S5_stock의 정교한 회귀 엔진과는 다릅니다.
- 현재 TASK 07은 **ETF 기반 basic S5 모델**입니다.
- 향후 Router 단계에서 주식형 S5와 병합 가능하도록 구조를 열어 둡니다.

---

## 10. 리밸런싱 규칙
### 지원
- 주간(`W`)
- 월간(`M`)

### 추가 고려
- 회귀형 특성상 더 짧은 재조정 주기를 테스트할 수 있도록 구조는 열어두되,
  1차 버전의 공식 지원은 W / M으로 제한합니다.

### 원칙
- 리밸런싱일 기준 목표비중 재산출
- 목표비중과 현재비중 차이에 따라 매매
- 거래비용 및 슬리피지 반영
- 가격 없는 ETF는 매매 제외
- 해당 group ETF가 없으면 대체자산 또는 현금 처리

---

## 11. 구현 범위

### 11.1 전략 모듈
- S5 전용 allocator / strategy 모듈 구현

### 11.2 config 분리
- 기본 비중
- 자산군별 min/max
- ADX / RSI / 볼린저 / 변동성 수축 조건 파라미터
- 거래비용
- 슬리피지
- 리밸런싱 주기
- fallback 규칙

### 11.3 성과비교 기능
최소 아래 비교가 가능해야 합니다.
- TASK 04 기본 neutral vs TASK 07 S5 refined
- FULL / 1Y / 2Y / 3Y / 5Y 성과 비교

### 11.4 산출물
- summary CSV
- equity CSV
- weights CSV
- trades CSV
- 비교 summary CSV (가능하면)

---

## 12. 권장 구현 파일
- `src/backtest/run_backtest_s5_neutral_allocation.py`
- `src/backtest/portfolio/s5_neutral_allocator.py`
- `src/backtest/configs/s5_neutral_config.py`
- `src/backtest/core/s5_backtest_runner.py`
- `scripts/validate_s5_neutral_backtest.py`

실제 구조에 맞게 파일명은 조정 가능하되,
영문 파일명 규칙과 역할 분리는 유지합니다.

---

## 13. 성과 지표
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

특히 S5는 회귀형 특성상 아래를 추가 확인하는 것이 바람직합니다.
- 거래비용 차감 전/후 성과 차이
- turnover 수준
- 짧은 홀딩 구간 성과 민감도

---

## 14. 완료 기준 (Definition of Done)
아래를 모두 만족하면 완료입니다.

1. S5 보합형 백테스트 실행이 가능하다.
2. broad / low-vol / dividend / covered-call / bond_short / cash 간 비중 규칙이 config 기반으로 동작한다.
3. ADX / 변동성 수축 / RSI / 볼린저 기반 최소 규칙이 반영된다.
4. summary / equity / weights / trades 산출물이 생성된다.
5. TASK 04 기본형 neutral과 비교 가능한 결과가 나온다.
6. 기존 ETF allocation engine과 충돌하지 않는다.
7. validate 또는 smoke test가 통과한다.

---

## 15. 이번 TASK에서 하지 않을 것
- 개별주식 mean-reversion 엔진 전체 구현
- 머신러닝 기반 비중 최적화
- 리스크 패리티 본격 도입
- TR/분배금 반영
- ETF PDF/구성종목 반영
- 직접 공매도
- 실거래 연동
- 웹 UI 연결

---

## 16. 다음 TASK
- TASK 08: 국면 Router 통합 실행 구조
- TASK 09: 신규 모델(S2/S3/S4/S5/S6) 통합 성과 비교 체계
- 이후: 사용자용 모델(안정형/균형형/성장형/자동전환형)과 관리용 모델 매핑 정교화

---

# B. Codex 실행지시문

## 작업명
S5 Neutral Mean-Reversion Allocation Model

## 현재 상태
- TASK 01 완료: ETF 마스터 유니버스 / ETF 일봉 / `prices_daily` 적재 / validate
- TASK 02 완료: ETF 분류 / 코어 ETF 유니버스 / 유동성 기준 / 메타 구축
- TASK 03 완료: `asset_type`, `instrument_master`, `etf_meta`, 공통 조회 구조 고정
- TASK 04 완료: ETF allocation backtest engine 구축 (`risk_on / neutral / risk_off`)
- TASK 05 완료: S6 Risk-Off Defensive Allocation 고도화
- TASK 06 완료: S4 Risk-On Offensive Allocation 고도화

이제 TASK 07에서는 TASK 04의 일반 `neutral` 포트폴리오를
독립 모델 수준의 **S5 보합형 전략**으로 고도화한다.

## 중요 원칙
1. S5의 목적은 보합 국면에서 과매도/되돌림 알파 + 변동성 완충이다.
2. 하락 방어는 S6의 영역이고, 강한 추세 추종은 S4의 영역이다.
3. 직접 공매도는 하지 말 것.
4. 인버스 ETF는 사용하지 말 것.
5. 레버리지 ETF는 제외할 것.
6. 거래비용/슬리피지 반영은 필수다.
7. TR/분배금은 반영하지 말 것.
8. 기존 TASK 04 엔진을 최대한 재사용할 것.
9. 규칙은 단순하고 설명 가능해야 하며 config 기반이어야 한다.

## 구현 목표
1. S5 전용 allocator / strategy 모듈 구현
2. 보합 국면용 중립 자산군 배분 규칙 구현
3. ADX / RSI / 볼린저 / 변동성 수축 기반 조건부 비중 조정 규칙 구현
4. 자산군별 min/max 제약 구현
5. TASK 04 기본 neutral과 비교 가능한 summary 생성
6. validate 또는 smoke test 구현

## 사용 자산군 / 그룹
- `equity_kr_broad`
- `equity_low_vol` (있으면 사용)
- `equity_dividend` (있으면 사용)
- `equity_covered_call` (있으면 사용)
- `bond_short`
- `cash`

## 초기 기본 비중 예시
- `equity_kr_broad`: 25%
- `equity_low_vol`: 20%
- `equity_dividend`: 15%
- `equity_covered_call`: 10%
- `bond_short`: 20%
- `cash`: 10%

반드시 config로 분리할 것.

## 자산군별 비중 제한 예시
- `equity_kr_broad`: 10% ~ 40%
- `equity_low_vol`: 0% ~ 30%
- `equity_dividend`: 0% ~ 25%
- `equity_covered_call`: 0% ~ 20%
- `bond_short`: 10% ~ 40%
- `cash`: 0% ~ 30%

## 조건부 규칙 요구사항
아래 조건에 따라 비중 조정 가능 구조를 구현하라.

1. ADX 낮음 / 추세 약함
- neutral 포지션 유지
- broad 과대비중 금지
- 저변동 / 배당 / 커버드콜 / bond_short 비중 유지 또는 확대

2. 변동성 수축 시
- mean-reversion 성격 자산 비중 확대 가능
- broad의 단기 되돌림 참여 허용

3. 단기 과매도 시
- broad 또는 저변동 ETF 비중 확대 가능
- cash / bond_short 일부 축소 가능

4. 되돌림 완료 / 반등 과열 시
- broad 또는 회귀 노출 일부 축소
- bond_short / cash 회복

5. 불확실성 확대 시
- bond_short / cash 비중 확대
- 주식성 노출 축소
- 단, 본격적인 risk-off 전환 자체는 하지 말 것

중요:
- 머신러닝 최적화 금지
- 명시적 규칙 기반으로 구현할 것

## ETF 단위 신호 예시
아래 수준의 간단한 신호를 구현하라.
- ADX 낮음 여부
- 최근 10~20일 변동성 수축 여부
- RSI(2~5) 과매도 영역 여부
- 볼린저 하단 접촉 또는 회복 여부
- 최근 N일 낙폭 대비 반등 신호

중요:
- 이는 ETF 기반 basic S5 모델이다.
- 개별주식 S5 mean-reversion 엔진 전체 구현은 이번 범위가 아니다.

## 리밸런싱
- `W`, `M` 지원
- 리밸런싱일에 목표비중 재산출
- 거래비용/슬리피지 반영 구조 유지
- 가격 없는 ETF는 제외
- group 후보가 없으면 대체자산 또는 현금 처리

## 권장 구현 파일
- `src/backtest/run_backtest_s5_neutral_allocation.py`
- `src/backtest/portfolio/s5_neutral_allocator.py`
- `src/backtest/configs/s5_neutral_config.py`
- `src/backtest/core/s5_backtest_runner.py`
- `scripts/validate_s5_neutral_backtest.py`

실제 프로젝트 구조에 맞춰 조정 가능하되,
영문 파일명과 역할 분리는 유지하라.

## 산출물
1. S5 백테스트 실행 스크립트
2. S5 config
3. 결과 CSV
   - summary
   - equity
   - weights
   - trades
4. validate 또는 smoke test
5. TASK 07 문서

## 비교 요구사항
아래 비교가 가능해야 한다.
- TASK 04 기본 neutral vs TASK 07 S5 refined
- FULL / 1Y / 2Y / 3Y / 5Y 성과 비교

## 완료 기준
1. S5 보합형 백테스트가 실행된다
2. 조건부 비중 규칙이 동작한다
3. broad / low-vol / dividend / covered-call / bond_short / cash 배분이 제한 범위 내에서 통제된다
4. summary / equity / weights / trades가 생성된다
5. TASK 04 neutral 대비 비교 결과가 나온다
6. 기존 ETF allocation engine과 충돌이 없다
7. validate 또는 smoke test가 통과한다

## 이번 TASK에서 하지 말 것
- 개별주식 mean-reversion 엔진 전체 구현
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
3. S5 규칙 설명
4. config 설명
5. 실행 방법
6. validate 방법
7. 생성 산출물 목록
8. TASK 04 neutral과의 비교 결과
9. 남은 리스크/주의사항
10. 다음 작업 제안
- TASK 08: 국면 Router 통합 실행 구조
- TASK 09: 모델 통합 성과 비교 체계

---

# C. Codex 개발 기본방향

- 이번 TASK 07의 핵심은 TASK 04의 일반 neutral 포트폴리오를 독립 전략 수준의 S5 모델로 고도화하는 것이다.
- 목표는 보합 국면에서 과매도/되돌림 알파를 얻되, 비용 민감도를 통제하는 것이다.
- S5는 공격형도 방어형도 아닌 중립형 완충 모델이다.
- 인버스/레버리지는 사용하지 않고, 저변동/배당/현금대체/단기채를 적절히 활용한다.
- 규칙은 단순하고 명시적이어야 하며, 모든 주요 수치는 config로 분리한다.
- TASK 04 엔진을 최대한 재사용하고, 기존 구조를 깨지 않는 방향으로 확장한다.
- 현재 TASK 07은 ETF 기반 basic S5 모델이며, 향후 주식 슬리브와의 병합은 Router 단계에서 처리한다.
- 결과는 반드시 summary / equity / weights / trades 형태로 남겨 비교 가능하게 한다.