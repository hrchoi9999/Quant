# MARKET_ANALYSIS_DATA_MODEL_20260323.md

## 1. 목적

이 문서는 시장 분석 전용 데이터 저장 구조를 정의한다.

핵심 원칙:

- 국내/미국 시장을 같은 구조로 저장할 수 있어야 한다.
- 원천 데이터와 가공 데이터, 웹용 payload를 분리한다.
- 공식 시장지표를 메인 원천으로 둔다.

## 2. 권장 DB

권장 파일:

- `D:\Quant\data\db\market_analysis.db`

기존 `market.db`는 원천/실험 단계로 유지 가능하지만, 서비스용 시장분석은 별도 DB로 분리하는 것이 좋다.

## 3. 테이블 계층

### A. 원천 계층

#### `market_index_daily`

컬럼:

- `market` (`KR`, `US`)
- `index_code`
- `index_name`
- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `value`
- `source`
- `updated_at`

PK 제안:
- `(market, index_code, date)`

#### `market_fx_daily`

컬럼:

- `market`
- `series_code`
- `series_name`
- `date`
- `close`
- `source`
- `updated_at`

#### `market_rates_daily`

컬럼:

- `market`
- `rate_code`
- `rate_name`
- `date`
- `value`
- `source`
- `updated_at`

### B. 계산 feature 계층

#### `market_features_hourly`

컬럼:

- `market`
- `asof`
- `asof_date`
- `kospi_1d_ret`
- `kospi_5d_ret`
- `kospi_20d_ret`
- `kosdaq_1d_ret`
- `kosdaq_5d_ret`
- `kosdaq_20d_ret`
- `above_20dma_ratio`
- `above_60dma_ratio`
- `adv_dec_ratio`
- `new_high_count`
- `new_low_count`
- `realized_vol_20d`
- `drawdown_5d`
- `drawdown_20d`
- `usdkrw_20d_ret`
- `bond_20d_ret`
- `gold_20d_ret`
- `inverse_20d_ret`
- `created_at`

PK 제안:
- `(market, asof)`

#### `market_component_scores`

컬럼:

- `market`
- `asof`
- `trend_score`
- `breadth_score`
- `risk_score`
- `defensive_flow_score`
- `total_score`
- `state_label`
- `created_at`

### C. 상태 이력 계층

#### `market_state_history`

컬럼:

- `market`
- `asof`
- `state_label`
- `state_score`
- `prev_state_label`
- `state_change_direction`
- `created_at`

### D. 웹 payload 계층

#### `market_analysis_payload`

컬럼:

- `market`
- `asof`
- `payload_type` (`summary`, `detail`, `today_bridge`)
- `payload_json`
- `created_at`

### E. AI 해설 계층

#### `market_analysis_ai_notes`

컬럼:

- `market`
- `asof`
- `provider` (`openai`, `gemini`)
- `model_name`
- `input_hash`
- `note_json`
- `created_at`

## 4. 미국시장 확장 고려

모든 테이블에 `market` 컬럼을 포함한다.

예:

- `KR`
- `US`

이 구조면 나중에 동일 테이블에 미국시장 데이터를 넣어도 된다.

## 5. 웹서비스용 기준

웹서비스는 원칙적으로 DB를 직접 읽지 않고, summary/detail snapshot 또는 API를 사용한다.
