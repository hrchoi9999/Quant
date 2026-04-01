# S3 Two-Stage Discovery Prototype (2026-03-31)

## 목적

`T3`를 한 번에 맞추려 하지 않고, 실제 전이 구조를 따라 두 단계로 나눠 종목을 발굴한다.

- 1단계: `T30_ex_T10 -> T10_ex_T3`
- 2단계: `T10_ex_T3 -> T3`

## 구조

### Stage 1
- 목표: 상위권 후보(`T10_ex_T3`)로 올라올 가능성이 높은 종목 탐지
- 핵심 신호:
  - `op_income_yoy`
  - `revenue_yoy`
  - `dist_ma120`
  - `ma_stack_gap`
  - `dist_ma60`
  - `op_delta_3m`

### Stage 2
- 목표: 이미 상위권인 후보 중 최상위(`T3`) 승격 가능성이 높은 종목 선별
- 핵심 신호:
  - `revenue_yoy`
  - `dist_ma120`
  - `ma_stack_gap`
  - `dist_ma60`
  - `op_income_yoy`
  - `mom20`

## 해석 원칙

- 이 구조는 연구용 discovery prototype이다.
- `T%`는 실제 시장 데이터 기반 사후 라벨이며, 정식 포트폴리오 백테스트 결과가 아니다.
- 따라서 본 프로토타입의 1차 목적은 `T%` 정답지 적합도를 높일 수 있는 탐지 구조를 찾는 것이다.

## 최신 후보 산출물

- `D:\Quant\reports\model_upgrade_research\20260331\S3_TWO_STAGE_DISCOVERY_PROTOTYPE\s3_stage1_t10_candidates_2026-03-26.csv`
- `D:\Quant\reports\model_upgrade_research\20260331\S3_TWO_STAGE_DISCOVERY_PROTOTYPE\s3_stage2_t3_candidates_2026-03-26.csv`
- `D:\Quant\reports\model_upgrade_research\20260331\S3_TWO_STAGE_DISCOVERY_PROTOTYPE\s3_stage2_watchlist_top20_2026-03-26.csv`
