# QUANT 시스템용 Codex 작업지시문

작성일: 2026-03-24  
대상 시스템: **Quant**  
목적: Quant 시스템을 **내부 연구·모델 생성·백테스트·성능평가 전용 엔진**으로 명확히 고정하고, 향후 QuantService/QuantMarket으로 전달되는 데이터가 법적 오해를 만들지 않도록 **출력 형식과 메타데이터를 보수적으로 표준화**한다.

---

## 1. 이번 작업의 핵심 목표

Quant 시스템은 다음 역할만 수행한다.

1. 퀀트 모델 생성
2. 백테스트 실행
3. 성능평가 산출
4. 모델 산출물의 표준화된 데이터 패키지 생성
5. QuantService / QuantMarket 에 전달할 **비개인화·공개형 모델 데이터** 생성

Quant 시스템은 다음 역할을 수행하면 안 된다.

1. 개인별 맞춤 포트폴리오 생성
2. 사용자 입력(나이, 자산, 보유종목, 손실허용도 등)에 따라 다른 모델 결과 생성
3. 특정 사용자 계좌 기준의 매수/매도/비중 제안
4. 1:1 자문으로 해석될 수 있는 출력 생성
5. 서비스용 마케팅 문구 자동 생성
6. “추천”, “최적”, “매수/매도 권고”, “AI 추천” 같은 표현이 포함된 외부 노출용 문구 생성

**중요 원칙:** Quant는 어디까지나 내부 연구/산출 엔진이다.  
서비스에 노출되는 모든 결과는 “공개 규칙 기반 모델 산출물”이어야 하며, Quant 단계에서부터 개인화 가능성을 제거해야 한다.

---

## 2. Codex가 이해해야 하는 시스템 경계

### Quant
- 내부 엔진
- 모델 생성 / 백테스트 / 성능평가
- 공개 가능한 모델 데이터 패키지 생성

### QuantService
- Quant가 넘긴 공개형 모델 데이터를 웹에 표시
- 사용자에게 동일한 정보만 제공
- 서비스 운영/UI/문구 관리

### QuantMarket
- 국내외 시장자료 분석
- 시장 상태 브리핑 데이터 생성
- 투자판단 보조용 시장 상황 설명 제공

### 경계 원칙
- Quant는 **개별 사용자 컨텍스트를 절대 다루지 않는다.**
- QuantService는 **Quant 결과를 개인 맞춤형처럼 가공하지 않는다.**
- QuantMarket은 **시장 상황 설명만 제공하며 계좌 단위 제안으로 넘어가지 않는다.**

---

## 3. Quant 시스템 개발 원칙

### 3-1. 내부 연구 시스템 원칙
Quant는 내부적으로는 자유롭게 연구할 수 있다. 다만 **운영 배포 경로에 올라가는 데이터셋/JSON/CSV/API 응답**은 반드시 아래 원칙을 지켜야 한다.

- 불특정 다수에게 동일하게 공개 가능한 구조일 것
- 특정 개인 입력값을 반영하지 않을 것
- 모델 로직/백테스트 조건/평가 기준이 추적 가능할 것
- 성과 수치에 대한 산출 조건이 메타데이터로 남을 것
- 서비스 화면에서 오해 소지가 없도록 label/field 명이 보수적일 것

### 3-2. 외부 전달 데이터 원칙
Quant가 외부 시스템에 넘기는 데이터는 다음 성격만 허용한다.

- 공개형 모델 정보
- 기준일(as-of date) 기준 모델 구성 정보
- 동일 규칙 기반의 주간/월간 스냅샷
- 백테스트 및 성능평가 결과
- 시장 국면과 무관한 순수 모델 정보

다음 성격의 데이터는 외부 전달 금지.

- user_id 기반 결과
- investor_type_input 기반 결과
- holdings_input 기반 결과
- 개인별 차등 비중 결과
- 개인별 리밸런싱 제안 결과
- 개인별 경고/알림 트리거 결과

---

## 4. 이번 작업 지시사항

### 작업 1. Quant 산출물 분류 체계 재정의
Quant 산출물을 아래 4종으로 분류하라.

#### A. research_only
내부 연구 전용. 서비스 전달 금지.
예:
- 실험 중간 결과
- 파라미터 튜닝 로그
- 과최적화 비교 결과
- 내부 후보 전략 비교표
- 사용자 입력 가정 실험

#### B. service_public_model
서비스 전달 가능.
예:
- 모델명
- 기준일
- 종목/ETF 구성
- 비중
- 현금 비중
- 리밸런싱 기준
- 위험등급
- 모델 설명 요약

#### C. service_public_backtest
서비스 전달 가능.
예:
- CAGR
- MDD
- Sharpe
- 변동성
- 기간별 성과
- 비교지수 대비 성과
- 회전율
- 리밸런싱 주기

#### D. compliance_meta
반드시 포함.
예:
- backtest_flag = true
- actual_return_flag = false
- fee_included 여부
- slippage_included 여부
- rebalance_frequency
- benchmark
- start_date / end_date
- calculation_version
- model_version
- disclaimer_required = true

**구현 요구:**
- 산출물 export 단계에서 위 4분류 중 하나 이상이 반드시 지정되도록 한다.
- service_public_model / service_public_backtest 데이터에는 compliance_meta가 반드시 함께 붙도록 한다.

---

### 작업 2. 필드명/출력명 보수화
외부 전달 데이터의 필드명과 레이블을 아래 기준으로 수정하라.

#### 금지 표현
- 추천
- 오늘의 추천
- 매수 추천
- 매도 추천
- AI 추천
- 최적 포트폴리오
- 개인 맞춤
- 내게 맞는
- 성향별 추천
- 수익률 보장
- 안정적 수익
- 유망 종목

#### 허용 표현 예시
- 모델
- 모델 기준안
- 모델 스냅샷
- 기준일 포트폴리오
- 공개 규칙 기반 산출 결과
- 주간 모델 구성
- 참고용 모델 정보
- 백테스트 결과
- 성과지표
- 리스크 지표

#### 필드명 변경 예시
- recommendation_type -> model_type
- recommended_weight -> model_weight
- buy_signal -> model_entry_condition
- sell_signal -> model_exit_condition
- today_pick -> current_model_snapshot
- investor_profile -> model_profile_label

**구현 요구:**
- 서비스 외부 노출 가능 데이터셋에는 recommendation, pick, advice, personalized, best 같은 영문 키도 사용하지 않는다.
- 기존 export JSON/CSV/schema에서 위험 키를 전수 점검하여 치환한다.

---

### 작업 3. 백테스트 결과 표준 메타데이터 강제
CAGR, MDD 등 백테스트 지표를 외부 전달할 때 아래 메타데이터를 반드시 포함하라.

#### 필수 메타데이터
- model_name
- model_version
- calculation_version
- asof_date
- backtest_start_date
- backtest_end_date
- rebalance_frequency
- fee_bps
- slippage_bps
- benchmark_name
- benchmark_return_if_available
- universe_definition
- data_source_summary
- actual_investment_result = false
- backtest_result = true
- disclaimer_required = true

#### 권장 메타데이터
- turnover
- max_recovery_days
- number_of_rebalances
- number_of_holdings_range
- cash_policy
- tax_assumption_if_any
- survivorship_bias_note_if_any

**구현 요구:**
- Quant에서 생성되는 성과 JSON/CSV는 메타데이터 블록 없이 배포되지 않도록 validation 추가
- validation 실패 시 export 중단

---

### 작업 4. “서비스 전달 가능 데이터” 전용 export 레이어 신설 또는 정비
현재 Quant에서 다양한 결과물이 섞여 있다면, 서비스 전달 전용 export 레이어를 분리하라.

권장 구조 예시:

```text
quant/
  models/
  backtests/
  evaluation/
  experiments/
  exports/
    research/
    service_public/
    compliance/
```

또는 기존 구조 유지 시 아래 개념을 반영하라.

- internal experiment output
- service public output
- compliance metadata output

**목표:**
서비스로 전달되는 데이터는 반드시 `service_public` 경로를 거치게 만들 것.

---

### 작업 5. 개인화 가능성 차단 장치 추가
Quant 코드 전반에서 아래 입력을 서비스 산출용 파이프라인에서 금지하라.

#### 금지 입력
- age
- income
- asset_size
- occupation
- retirement_year
- risk_tolerance_personal
- holdings_list
- account_balance
- user_goal
- user_segment

#### 허용 입력
- 공개된 모델 정의값
- 시장 데이터
- 종목/ETF 유니버스 데이터
- 백테스트 파라미터
- 사전 정의된 모델 라벨 (안정형/균형형/성장형 등)

**구현 요구:**
- 서비스 배포용 pipeline에서 개인화 입력 필드가 감지되면 에러 발생
- 코드 주석으로 “개인별 자문성 결과 생성 금지” 명시

---

### 작업 6. 모델 라벨 체계 정비
현재 안정형/균형형/성장형 같은 라벨은 유지할 수 있으나, 내부 정의와 외부 표시 기준을 명확히 분리하라.

#### 내부용
- risk_bucket_code
- volatility_target_band
- drawdown_limit_band
- asset_mix_policy

#### 외부용
- model_profile_label
- model_risk_level
- model_description_short

**주의:**
외부용 설명에서 “당신에게 맞는”, “성향에 따른 추천” 같은 문구 금지.
대신 아래처럼 표현.

- “공개 기준에 따라 산출된 안정 지향형 모델”
- “공개 규칙 기반의 균형형 모델”
- “변동성을 감수하는 성장 지향형 모델”

---

### 작업 7. 성과지표 출력 정책 정비
성과지표는 표시 가능하지만, 좋은 구간만 마케팅용으로 뽑히지 않도록 Quant 단계에서 표준 출력 정책을 만든다.

#### 필수 출력
- FULL 기간 성과
- 1Y / 3Y / 5Y 등 고정 윈도우 성과
- CAGR
- MDD
- Sharpe
- 변동성
- 벤치마크 비교

#### 금지 출력 관행
- 가장 성과 좋은 구간만 별도 추출해서 기본 출력으로 제공
- 특정 전략의 최고 수익 구간만 강조하는 export
- “best period”, “winning mode”, “alpha guaranteed” 등 공격적 label

**구현 요구:**
- 기본 export는 전체기간 + 고정 윈도우를 함께 내보내는 구조로 통일
- 특정 구간 강조용 별도 export는 research_only로만 분류

---

### 작업 8. Quant -> QuantService 전달 계약(schema contract) 작성
서비스 전달용 표준 schema를 문서 또는 코드로 명시하라.

최소 포함 항목:
- model snapshot schema
- backtest metric schema
- compliance metadata schema
- enum 목록
- 금지 필드 목록
- nullable 규칙
- 버전 규칙

권장 방식:
- JSON Schema
- Pydantic model
- dataclass + validator
- markdown contract 문서

**목표:**
QuantService는 Quant가 준 데이터만 그대로 보여도 규제 오해가 커지지 않는 수준으로 안전한 schema를 받게 할 것.

---

### 작업 9. 감사 추적(audit trail) 추가
향후 법적/운영상 설명을 위해 아래를 남겨라.

- model_version
- export_timestamp
- source_data_date_range
- parameter_hash
- code_commit_hash_if_available
- evaluation_run_id
- schema_version

**목표:**
사이트에 노출된 숫자가 어떤 코드/데이터/기간에서 나왔는지 역추적 가능해야 한다.

---

## 5. Quant 시스템에서 절대 하면 안 되는 것

1. 사용자 개인정보 또는 계좌정보를 입력받아 모델 결과를 다르게 만드는 기능
2. “회원별 포트폴리오” 생성 기능
3. “내 보유종목 기준 리밸런싱안” 생성 기능
4. 사용자별 다른 종목/비중 결과 export
5. 외부 노출용 파일에 buy/sell recommendation 텍스트 포함
6. 고수익 보장으로 읽힐 label 자동 생성
7. 챗봇 응답용 개별 자문 데이터 생성
8. 서비스용으로 가장 좋은 수익구간만 export

---

## 6. 산출물 예시 구조

### 6-1. 서비스 공개용 모델 스냅샷 예시

```json
{
  "model_name": "balanced_weekly_model",
  "model_profile_label": "균형형 모델",
  "asof_date": "2026-03-20",
  "holdings": [
    {"ticker": "069500", "asset_type": "ETF", "model_weight": 0.22},
    {"ticker": "360750", "asset_type": "ETF", "model_weight": 0.15}
  ],
  "cash_weight": 0.11,
  "rebalance_frequency": "W",
  "compliance_meta": {
    "public_model": true,
    "personalized": false,
    "disclaimer_required": true,
    "model_version": "v2026.03.20"
  }
}
```

### 6-2. 서비스 공개용 백테스트 예시

```json
{
  "model_name": "balanced_weekly_model",
  "backtest_result": true,
  "actual_investment_result": false,
  "metrics": {
    "cagr": 0.123,
    "mdd": -0.154,
    "sharpe": 0.88,
    "volatility": 0.172
  },
  "window_metrics": {
    "1Y": {"cagr": 0.08, "mdd": -0.11},
    "3Y": {"cagr": 0.12, "mdd": -0.15},
    "5Y": {"cagr": 0.10, "mdd": -0.19}
  },
  "compliance_meta": {
    "backtest_start_date": "2018-01-01",
    "backtest_end_date": "2026-03-20",
    "rebalance_frequency": "W",
    "fee_bps": 5,
    "slippage_bps": 5,
    "benchmark_name": "KOSPI200/TR",
    "disclaimer_required": true,
    "model_version": "v2026.03.20",
    "calculation_version": "perf_v2"
  }
}
```

---

## 7. Codex 구현 우선순위

### P0
1. 서비스 배포용 export에서 개인화 입력 차단
2. 외부 노출 필드명/라벨 정리
3. compliance_meta 강제
4. backtest / actual 구분 플래그 강제
5. service_public schema 정의

### P1
1. export validation layer 구축
2. audit trail 추가
3. FULL/1Y/3Y/5Y 고정 성과 출력 표준화
4. research_only / service_public 분리

### P2
1. 내부 문서화
2. schema 테스트 코드 작성
3. 위험 키워드 lint 또는 정적 점검 추가

---

## 8. 테스트/검수 기준

아래 질문에 하나라도 “예”가 나오면 실패로 간주.

1. 사용자 입력값에 따라 결과가 달라지는가?
2. 외부 산출물에 recommendation/advice/pick 같은 키가 남아 있는가?
3. backtest 결과에 메타데이터가 누락되어 있는가?
4. actual result와 backtest result 구분이 없는가?
5. 서비스 공개용 데이터가 research output과 혼합되어 있는가?
6. 특정 고성과 구간만 기본 출력되는가?
7. 모델 설명에 “추천”, “맞춤”, “최적” 표현이 남아 있는가?

모든 항목이 “아니오”여야 통과.

---

## 9. Codex 산출물 요청

이번 작업에서 Codex는 아래 결과물을 제출하라.

1. 수정 대상 파일 목록
2. 변경 요약
3. service_public schema 정의 파일
4. compliance_meta validator 코드
5. 위험 키워드 치환 내역
6. export 전/후 샘플 JSON 또는 CSV
7. 테스트 결과
8. 남은 리스크 및 후속 제안

---

## 10. 최종 지시

이번 작업의 목적은 Quant를 더 화려하게 만드는 것이 아니다.  
**Quant를 “내부 모델 엔진”으로 고정하고, QuantService에 전달되는 결과가 개인 자문이나 직접 추천으로 오해되지 않도록 데이터 구조를 보수적으로 표준화하는 것**이 목적이다.

Codex는 UI 문구 개선이 아니라 **데이터 구조, export schema, 메타데이터, validation, 금지 입력 차단**에 집중하라.

