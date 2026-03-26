# Redbot User Models and Internal Models

## 목적
이 문서는 내부 운용 모델 `S2`, `S3`, `S4`, `S5`, `S6`, `Router`를 Redbot 서비스에서 사용자에게 어떻게 번역해 보여줄지 정리한 기준 문서다.

## 사용자용 모델 4종

### 안정형
- 목표: 낙폭 방어 우선
- 설명: 채권, 달러, 금 등 방어 자산 비중이 높은 보수형 포트폴리오
- 내부 연결:
  - Primary: `S6`
  - Secondary: `Router(stable)`
- 적합 사용자: 수익보다 안정성과 방어를 우선하는 사용자
- 주요 자산: 채권, 달러, 금, 현금성 자산

### 균형형
- 목표: 수익과 안정성의 균형
- 설명: 주식과 ETF를 함께 사용해 분산된 중립형 포트폴리오를 구성
- 내부 연결:
  - Primary: `S2`, `S5`
  - Secondary: `Router(balanced)`
- 적합 사용자: 중장기 성장을 원하지만 과한 변동성은 피하고 싶은 사용자
- 주요 자산: 주식, 저변동/배당/커버드콜 ETF, 단기채 ETF

### 성장형
- 목표: 상승 추세에서 높은 수익 추구
- 설명: 추세와 모멘텀을 적극 활용하는 공격형 포트폴리오
- 내부 연결:
  - Primary: `S3`, `S4`
  - Secondary: `Router(growth)`
- 적합 사용자: 높은 변동성을 감수하고 더 큰 기대수익을 원하는 사용자
- 주요 자산: 모멘텀 주식, 성장형 ETF, 공격형 equity ETF

### 자동전환형
- 목표: 시장 상황에 따라 자동 대응
- 설명: 상승/보합/하락 국면에 따라 내부 모델이 자동 전환되는 동적 포트폴리오
- 내부 연결:
  - Primary: `Router(auto)`
  - Secondary: `S2`, `S3`, `S4`, `S5`, `S6`
- 적합 사용자: 직접 전략을 고르기보다 자동 조정을 선호하는 사용자
- 주요 자산: 멀티에셋, 국면전환형 자산배분

## 내부 관리용 모델
- `S2`: 안정형 주식 sleeve
- `S3`: 공격형 주식 sleeve
- `S4`: risk_on ETF sleeve
- `S5`: neutral ETF sleeve
- `S6`: risk_off ETF sleeve
- `Router`: 국면 기반 멀티에셋 상위 엔진

## 기본 매핑 원칙
- 사용자에게는 엔진명보다 상품형 이름을 노출한다.
- 내부 운용과 성과 비교는 계속 `S2/S3/S4/S5/S6/Router` 기준으로 관리한다.
- 사용자용 상품은 1:1 매핑이 아니라 1:many 매핑을 허용한다.
- `Router`는 사용자에게는 “자동전환형” 혹은 각 bias 기반 상품의 보조 엔진으로 설명한다.

## 사용자 노출 정보와 내부 정보의 경계
사용자 노출:
- 상품명
- 한 줄 설명
- 목표 성향
- 예상 변동성 수준
- 최근 성과
- 최대 낙폭 성격
- 주요 자산군

내부 전용:
- ADX, RSI, Donchian, ATR
- regime threshold
- group_key, ETF core selection logic
- fallback 세부 규칙
- decision log 상세 파라미터
