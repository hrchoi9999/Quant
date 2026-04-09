# T-ETF-V01 Operational Refresh (2026-03-31)

## 모델 코드
- 운영 모델: `T-ETF-V01`
- 1단계: `T-ETF-V01-S1`
- 2단계: `T-ETF-V01-S2`

## 목적
- 신규 데이터 수집 없이
- 현재 로컬 DB와 기존 연구 산출물을 재사용해서
- ETF `T-series` 운영형 후보군을 월간 기준으로 다시 생성한다.
- 현재 refresh 기준은 `PIT backfill` 운영형 결과다.

## 실행 스크립트
- [run_t_etf_v01_operational_refresh.py](D:/Quant/scripts/run_t_etf_v01_operational_refresh.py)

## 실행 순서
1. `build_etf_tseries_pit_operational_candidates.py`
2. `build_etf_tseries_pit_risk_filter.py`
3. `build_etf_tseries_pit_shadow_tracking.py`
4. `sync_tseries_operational_db.py --model etf`

## 입력 산출물
- strict walk-forward:
  - `D:\Quant\reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_STRICT_WALKFORWARD\etf_tseries_pit_strict_walkforward_top_picks.csv`
- tuned two-stage:
  - `D:\Quant\reports\model_upgrade_research\20260401\ETF_TWO_STAGE_DISCOVERY_TUNED_PIT\etf_two_stage_tuned_pit_stage1_candidates_2026-03-31.csv`
  - `D:\Quant\reports\model_upgrade_research\20260401\ETF_TWO_STAGE_DISCOVERY_TUNED_PIT\etf_two_stage_tuned_pit_stage2_confirmed_2026-03-31.csv`
  - `D:\Quant\reports\model_upgrade_research\20260401\ETF_TWO_STAGE_DISCOVERY_TUNED_PIT\etf_two_stage_tuned_pit_stage2_near_2026-03-31.csv`

## 출력 위치
- `D:\Quant\reports\model_upgrade_research\20260401\ETF_T_SERIES_OPERATIONALIZATION_PIT`
- 운영 DB:
  - `D:\Quant\data\db\tseries_operational.db`

## 주의
- 이 리프레시는 데이터 수집이나 DB 갱신을 수행하지 않는다.
- 입력은 기존 ETF T-series 연구 결과와 현재 저장된 로컬 데이터에 한정된다.
- 유동성 하한은 `20일 평균 거래대금 200억`으로 유지한다.
- 레버리지/인버스 ETF는 현재 운영형에서 허용한다.


- Current operational rule: inverse/leverage excluded, liquidity floor 20d avg trading value >= 20 billion KRW.

- Refresh now also builds a rolling watchlist using the latest monthly snapshots.
  - Output: `etf_tseries_pit_rolling_watchlist_YYYY-MM-DD.csv`
