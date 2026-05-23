# ETF Common Framework KR/US V1 (2026-04-28)

## 목적

- 한국 ETF 모델과 미국 ETF 모델을 완전히 별도 체계로 키우지 않고, 공통 전략 프레임 위에서 시장별 구현만 분리한다.
- 현재 KR ETF 모델(S4/S5/S6/T-ETF)의 장점을 유지하면서도, 미국 시장 확장 시 재사용 가능한 분류/선별 구조를 먼저 고정한다.
- 이번 문서는 "모델 교체" 문서가 아니라 "공통 프레임 정의" 문서다.

## 현재 KR ETF 모델 구조 요약

- 배분형
  - `S4`: 공격형 / risk-on
  - `S5`: 중립형 / neutral
  - `S6`: 방어형 / defensive
- 발굴형
  - `T-ETF-V01`

현재 구조의 장점:

- 사용자/운영 해석이 쉽다.
- risk-on / neutral / defensive / discovery 역할이 이미 분리되어 있다.
- KR ETF 운영 실적과 shadow tracking 자산이 쌓여 있다.

현재 구조의 한계:

- `group_key`가 한국 ETF 이름 규칙에 많이 의존한다.
- `equity_kr_broad`와 `sector/theme` 경계가 흐리다.
- 인버스/레버리지 ETF를 공통 역할군 안에서 다루기 어렵다.
- T-ETF는 "역할군 내 발굴"보다 "현행 입력 universe 기반 탐색" 성격이 더 강하다.

## 이번 공통 프레임 설계 원칙

### 1. 전략 축은 유지

- `S4 / S5 / S6 / T-ETF`라는 전략 철학은 유지한다.
- 바꾸는 것은 모델 목적이 아니라 ETF 입력 프레임과 role 분류 체계다.

### 2. ETF는 종목명이 아니라 역할(role)로 먼저 분류

- 한국/미국 모두 동일한 role taxonomy를 사용한다.
- 시장별 차이는 role 안의 universe, threshold, quota, whitelist/blacklist에서 처리한다.

### 3. 레버리지/인버스는 포함하되 분리 관리

- 분석 대상에서는 제외하지 않는다.
- 다만 일반 core/style/theme ETF와 같은 bucket에서 섞지 않는다.

### 4. 시장 공통 프레임 + 시장별 파라미터

- 공통:
  - role taxonomy
  - role purity 규칙
  - strategy layer 정의
- 시장별:
  - universe
  - liquidity cutoff
  - role별 quota
  - 허용 ETF 목록

## 공통 role taxonomy V1

### ROLE 1. CORE_BETA

정의:

- 시장 대표 broad beta
- 국가/지역 broad index
- large / mid / small broad beta

KR 예시:

- KODEX 200
- TIGER 200
- KODEX 코스닥150

US 예시:

- SPY, IVV, VOO
- QQQ
- IWM

운용 원칙:

- 장기 기준 포트폴리오의 중심축
- style/theme와 구분된 순수 beta 역할 유지

### ROLE 2. STYLE_FACTOR

정의:

- growth
- value
- dividend
- quality
- low volatility
- covered call income

KR 예시:

- PLUS 고배당주
- 파워 고배당저변동성
- KODEX 200타겟위클리커버드콜

US 예시:

- VUG, IWF
- VTV, IWD
- SCHD, VYM
- QUAL, USMV
- JEPI, JEPQ

운용 원칙:

- broad beta의 대체축 또는 보완축
- factor rotation 및 안정성 조절에 사용

### ROLE 3. SECTOR_THEME

정의:

- 반도체, AI, 전력설비, 헬스케어, 금융, 에너지 등
- broad beta가 아닌 특정 산업/테마 노출

KR 예시:

- KODEX 반도체
- TIGER 200 IT
- KODEX AI전력핵심설비
- KODEX 2차전지산업

US 예시:

- SOXX, SMH
- XLK
- XLF
- XLE
- IBB, XBI

운용 원칙:

- risk-on 구간의 공격적 alpha 소스
- T-ETF discovery의 핵심 비교군

### ROLE 4. DEFENSIVE_HEDGE

정의:

- 단기채
- 장기채
- 금
- 달러
- 현금성/금리형 ETF

KR 예시:

- KODEX CD금리액티브
- KODEX KOFR금리액티브
- ACE 미국30년국채액티브(H)
- ACE KRX금현물
- KODEX 미국달러선물

US 예시:

- BIL, SGOV
- IEF, TLT
- GLD, IAU
- UUP

운용 원칙:

- S5/S6의 방어축
- risk-off 구간과 변동성 완충 기능

### ROLE 5. TACTICAL_LEVERAGE

정의:

- 방향성을 증폭하는 레버리지 ETF

KR 예시:

- KODEX 레버리지
- 미국달러선물레버리지

US 예시:

- UPRO, TQQQ, SOXL

운용 원칙:

- 기본 운영 포트폴리오에서는 비중 상한 적용
- discovery / tactical branch / 내부 전용 모델에서 주로 활용

### ROLE 6. TACTICAL_HEDGE

정의:

- 인버스 ETF
- 시장 또는 특정 자산군 헤지 ETF

KR 예시:

- KODEX 인버스
- KODEX 200선물인버스2X

US 예시:

- SH, PSQ, SQQQ, DOG

운용 원칙:

- 방어 목적의 tactical hedge
- 일반 broad/theme ETF와 같은 경쟁군으로 두지 않는다

## 현재 KR group_key와 공통 role의 매핑 초안

| 현재 group_key | 공통 role | 비고 |
|---|---|---|
| `equity_kr_broad` | `CORE_BETA` 또는 `SECTOR_THEME` | 현재 가장 큰 문제 구간. broad purity 재분류 필요 |
| `equity_kr_growth` | `SECTOR_THEME` 또는 일부 `STYLE_FACTOR` | 성장/섹터가 혼합되어 있어 분리 필요 |
| `bond_short` | `DEFENSIVE_HEDGE` | 유지 |
| `bond_long` | `DEFENSIVE_HEDGE` | 유지 |
| `fx_usd` | `DEFENSIVE_HEDGE` | 유지 |
| `commodity_gold` | `DEFENSIVE_HEDGE` | 유지 |
| `equity_low_vol` | `STYLE_FACTOR` | 유지 |
| `equity_dividend` | `STYLE_FACTOR` | 유지 |
| `equity_covered_call` | `STYLE_FACTOR` | 유지 |
| `hedge_inverse_kr` | `TACTICAL_HEDGE` | 일반 core에서 분리 유지 |
| leveraged ETF | `TACTICAL_LEVERAGE` | 현재 core 제외 상태에서 공통 프레임상 role 포함으로 승격 |

## 전략별 공통 프레임 재매핑

### KR/US 공통 S4: ETF_RISK_ON_CORE

역할:

- `CORE_BETA`
- `STYLE_FACTOR`
- `SECTOR_THEME`

목표:

- 강한 시장 구간에서 alpha 우선
- broad beta와 sector/theme를 혼용하되 role purity 유지

주의:

- `TACTICAL_LEVERAGE`는 별도 cap 또는 내부 전용 branch에서만 허용

### KR/US 공통 S5: ETF_BALANCED_CORE

역할:

- `CORE_BETA`
- `STYLE_FACTOR`
- 일부 `DEFENSIVE_HEDGE`

목표:

- neutral / mixed regime 대응
- broad + factor + cash-like 완충 구조

### KR/US 공통 S6: ETF_DEFENSIVE_CORE

역할:

- `DEFENSIVE_HEDGE`
- 일부 `CORE_BETA`
- 필요 시 제한적 `TACTICAL_HEDGE`

목표:

- 방어 우선
- drawdown 억제와 유동성 유지

### KR/US 공통 T-ETF: ETF_DISCOVERY

역할:

- role-aware discovery
- 같은 role 안에서 상대강도, 승격 가능성, state transition 분석

목표:

- "전체 ETF 중 어떤 것이 뜨나"보다
- "같은 역할군 안에서 어떤 ETF가 강해지나"를 본다

## 이번 설계 기준에서 먼저 손봐야 할 KR ETF 문제

### 1. broad purity 문제

현재 확인된 문제:

- `TIGER 200 IT`
- `KODEX 코스닥150선물인버스`
같은 ETF가 broad 그룹으로 들어오는 케이스가 있다.

정책:

- broad는 "시장 대표 beta"만 허용
- sector/theme/inverse는 broad에서 제거

### 2. growth와 theme 혼합 문제

현재 `equity_kr_growth`는:

- 성장 factor
- 반도체/AI/2차전지 등 sector/theme
가 섞여 있다.

정책:

- 성장 factor는 `STYLE_FACTOR`
- 산업/테마는 `SECTOR_THEME`

### 3. 인버스/레버리지의 별도 role 분리

현재는:

- 레버리지는 core 제외
- 인버스는 `hedge_inverse_kr`만 예외 허용

새 프레임에서는:

- 둘 다 분석 universe에 포함
- 다만 role을 분리하고 전략별 허용정책을 따로 둔다

## KR -> US 확장 방식

### 유지되는 것

- role taxonomy
- 전략 정의
- 성과 비교 방식
- discovery / shadow / watchlist 개념

### 시장별로 달라지는 것

- ETF universe source
- liquidity threshold
- role별 quota
- 허용 ETF whitelist
- tactical leverage/hedge 사용 상한

## 개발 순서

### Phase 1. KR 공통 프레임 정리

1. KR ETF를 공통 role taxonomy 기준으로 재분류
2. 현재 `group_key`와 신규 `role_key`를 병행 관리
3. broad/theme purity 검증 리포트 생성

### Phase 2. KR 기존 모델 shadow remap

1. `S4 / S5 / S6 / T-ETF`를 신규 role 기준으로 재매핑
2. 현행 모델과 신규 role 프레임 기반 결과 비교
3. 종목 변화 / 성과 변화 / 회전율 변화 점검

### Phase 3. KR 운영형 확정

1. Challenger 검증
2. 운영 승인 시 current 승격

### Phase 4. US ETF universe 연결

1. US ETF master 수집
2. 같은 role taxonomy로 분류
3. `US_ETF_RISK_ON / BALANCED / DEFENSIVE / DISCOVERY` 개발

## 이번 문서 기준 결론

- 현재 KR ETF 모델은 폐기 대상이 아니다.
- 다만 미국 확장을 위해서는 ETF 입력 프레임을 공통 role 기반으로 먼저 정리해야 한다.
- 즉 "모델을 다시 만든다"보다 "같은 전략 축을 공통 ETF 프레임 위에 다시 세운다"가 정확한 표현이다.

## 다음 바로 할 일

1. KR ETF `role_key` 초안 생성
2. 현행 `group_key` 대비 `role_key` 매핑 리포트 작성
3. broad purity 위반 ETF 목록 추출
4. 그 기준으로 `S4/S5/S6/T-ETF` shadow 재매핑

## 구현 산출물

- Taxonomy file: `data/universe/etf_role_taxonomy_common_v1.yml`
- KR role classifier: `scripts/build_etf_common_role_classification.py`
- 2026-04-27 classification output: `data/universe/etf_role_classification_20260427.csv`
- 2026-04-27 review reports: `reports/etf_common_framework/20260427/`

### 2026-04-27 1차 분류 결과

| role_key | count |
| --- | ---: |
| SECTOR_THEME | 300 |
| DEFENSIVE_HEDGE | 182 |
| CORE_BETA | 146 |
| STYLE_FACTOR | 124 |
| TACTICAL_LEVERAGE | 45 |
| TACTICAL_HEDGE | 40 |
| UNCLASSIFIED | 37 |

정리:

- 기존 `group_key`는 덮어쓰지 않고 신규 `role_key`를 병렬 산출했다.
- 레버리지/인버스 ETF는 공통 프레임에 포함하되 tactical role로 분리했다.
- `UNCLASSIFIED` 37개는 억지 분류하지 않고 수동 검토 대상으로 남겼다.
- 기존 `equity_kr_broad` 중 33개는 공통 role 기준에서 pure broad beta가 아니어서 검토 대상으로 표시했다.

### 2026-04-27 운영 전환 비교 결과

비교 방식:

- ETF core 후보를 `role_key` purity 기준으로 재구성했다.
- `price.db.etf_meta`에 role 필드를 추가하고, core CSV의 group assignment가 DB에도 반영되도록 동기화했다.
- S4는 `equity_sector_momentum`을 기본 보유가 아니라 강한 섹터 신호가 있을 때만 제한적으로 쓰도록 수정했다.
- S5는 배당과 커버드콜을 섞지 않도록 스타일 하위 그룹을 분리했다.
- S6는 인버스성 달러 ETF가 `fx_usd`로 들어가지 않도록 `TACTICAL_HEDGE`와 `DEFENSIVE_HEDGE`를 분리했다.

| model | legacy CAGR | common-frame CAGR | legacy MDD | common-frame MDD | legacy Sharpe | common-frame Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S4 | 35.79% | 43.42% | -19.94% | -19.99% | 1.30 | 1.48 |
| S5 | 23.62% | 23.62% | -9.36% | -9.36% | 1.79 | 1.79 |
| S6 | -0.24% | 4.29% | -7.82% | -5.31% | -0.00 | 0.72 |

해석:

- S4는 기존보다 개선됐지만, 섹터 ETF 기본 보유는 위험해서 제한 사용으로 고정했다.
- S5는 기존 스타일 세분화가 적합했으므로 성과가 유지되도록 배당/커버드콜 분리 규칙을 반영했다.
- S6는 `fx_usd`에 잘못 들어가던 인버스성 ETF가 제거되면서 방어 성과와 MDD가 개선됐다.
- T-ETF는 재학습하지 않고 role overlay만 수행했다. 2026-04-27 후보 16개 중 confirmed/near는 모두 `TACTICAL_HEDGE`에 몰려 있어, 이후 T-ETF에는 role별 cap 또는 tactical 후보 별도 표시가 필요하다.

Generated / updated files:

- `reports/etf_common_framework/20260427/shadow_compare/ETF_COMMON_ROLE_SHADOW_COMPARISON.md`
- `data/universe/universe_etf_core_20260427.csv`
- `data/universe/etf_meta_20260427.csv`

### 2026-04-27 T-ETF 운영 프레임 반영

적용 내용:

- `T-ETF-V01` 후보 생성 산출물에 `role_key`, `role_confidence`, `role_reason`을 추가했다.
- risk filter를 기존 theme cap 중심에서 common ETF role cap + theme cap 병행 구조로 바꿨다.
- `TACTICAL_HEDGE`, `TACTICAL_LEVERAGE`는 primary watchlist에서 제외하고 `tactical_watch_only` 후보로 별도 보존한다.
- `tseries_operational.db`의 latest/history/rolling watchlist 테이블에도 role 필드를 추가했다.
- T-series 조회 계층과 public discovery snapshot에서도 role 필드가 유지되도록 보강했다.

2026-04-27 결과:

| bucket | ticker | name | role_key | theme_bucket |
| --- | --- | --- | --- | --- |
| observe | 261220 | KODEX WTI원유선물(H) | SECTOR_THEME | energy_materials |
| observe | 481050 | KODEX CD1년금리플러스액티브(합성) | DEFENSIVE_HEDGE | gold |

별도 tactical watch-only:

| original bucket | ticker | name | role_key | stage2_prob |
| --- | --- | --- | --- | ---: |
| confirmed | 271050 | KODEX WTI원유선물인버스(H) | TACTICAL_HEDGE | 0.7831 |
| confirmed | 114800 | KODEX 인버스 | TACTICAL_HEDGE | 0.7689 |
| observe | 251340 | KODEX 코스닥150선물인버스 | TACTICAL_HEDGE |  |

해석:

- T-ETF의 원천 discovery 신호는 여전히 인버스/방어성 후보를 강하게 포착했다.
- 다만 한국/미국 ETF 공통 프레임에서는 인버스/레버리지 ETF를 일반 추천 후보와 섞지 않는다.
- 따라서 `T-ETF-V01` primary watchlist는 일반/방어 ETF 중심으로 유지하고, tactical 후보는 별도 관찰 대상으로 남기는 방식이 장기 확장에 더 적합하다.

Generated / updated files:

- `reports/model_upgrade_research/20260427/ETF_T_SERIES_OPERATIONALIZATION_PIT/etf_tseries_pit_latest_watchlist_2026-04-27.csv`
- `reports/model_upgrade_research/20260427/ETF_T_SERIES_OPERATIONALIZATION_PIT/etf_tseries_pit_tactical_watch_candidates_2026-04-27.csv`
- `reports/model_upgrade_research/20260427/ETF_T_SERIES_OPERATIONALIZATION_PIT/etf_tseries_pit_role_summary_20260427.csv`
