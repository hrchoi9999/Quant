아래 요구사항에 따라 TASK 04를 수행하라.

[작업명]
ETF 자산배분 레이어 백테스트 엔진
(국면별 ETF 포트폴리오 P0/P1)

[현재 상태]
- TASK 01 완료
  - ETF 마스터 유니버스 생성
  - ETF 일봉 OHLCV 수집
  - `prices_daily` 적재
  - 최소 validate 완료
- TASK 02 완료
  - ETF 분류(rule + override)
  - 코어 ETF 유니버스(core) 생성
  - ETF 메타(asset_class, group_key, currency_exposure, inverse/leverage, liquidity) 구축
- TASK 03 완료
  - `asset_type`, `instrument_master`, `etf_meta`, 공통 조회/필터 구조 고정

이번 TASK 04의 목적은
ETF 코어 유니버스를 사용한 국면별 자산배분 백테스트 엔진의 첫 버전을 구현하는 것이다.

[중요 원칙]
1. 기존 주식 백테스트 엔진을 최대한 재사용하되 ETF 자산배분은 별도 레이어로 시작할 것
2. `prices_daily` 스키마는 절대 변경하지 말 것
3. ETF는 `universe_etf_core_{asof}.csv` 또는 동등한 core 조회 결과만 사용할 것
4. 직접 공매도는 하지 말 것. 헤지는 인버스 ETF로만 구현할 것
5. TR/분배금 반영은 하지 말 것
6. 국면 산출 로직 자체는 이번 TASK에서 고도화하지 말 것
7. 단순하고 재현 가능한 규칙 기반 포트폴리오부터 구현할 것

[구현 목표]
1. ETF 자산배분 백테스트 실행 파일 구현
2. 국면별 포트폴리오 모드 지원
   - `risk_on`
   - `neutral`
   - `risk_off`
3. 주간/월간 리밸런싱 지원
4. 거래비용/슬리피지 반영 구조 마련
5. 결과 CSV 생성
   - summary
   - equity curve
   - weights
   - trades
6. validate 또는 smoke test 스크립트 구현

[입력]
- `data/db/price.db` 의 `prices_daily`
- `instrument_master`
- `etf_meta`
- `data/universe/universe_etf_core_{asof}.csv` 또는 동등 조회 함수
- 기존 시장 국면 데이터 (`regime_history` 등)

[포트폴리오 구조 초기안]
1. 상승 국면 (`risk_on`)
- 사용 group:
  - `equity_kr_broad`
  - `equity_kr_growth` (있으면 사용)
- 초기 비중 예:
  - equity_kr_broad: 60%
  - equity_kr_growth: 40%

2. 보합 국면 (`neutral`)
- 사용 group:
  - `equity_kr_broad`
  - `bond_short`
  - `cash` 또는 현금대체 성격 ETF(있으면 사용)
- 초기 비중 예:
  - equity_kr_broad: 40%
  - bond_short: 40%
  - cash/현금대체: 20%

3. 하락 국면 (`risk_off`)
- 사용 group:
  - `bond_long`
  - `bond_short`
  - `fx_usd`
  - `commodity_gold`
  - `hedge_inverse_kr`
- 초기 비중 예:
  - bond_long: 30%
  - bond_short: 25%
  - fx_usd: 20%
  - commodity_gold: 15%
  - hedge_inverse_kr: 10%

중요:
- 위 비중은 config 파일로 분리할 것
- 실제 사용 가능한 ETF는 core 유니버스와 group coverage에 따라 결정할 것

[국면 입력 규칙]
1. 기존 국면 데이터를 입력으로 받을 것
2. 국면 -> 포트폴리오 모드 매핑은 config 또는 함수로 분리할 것
3. fallback 모드(예: always neutral)는 선택적으로 지원 가능

[리밸런싱 규칙]
1. 최소 지원:
- `W`
- `M`

2. 리밸런싱 방식:
- 리밸런싱일에 목표 비중으로 재조정
- 가격이 없는 ETF는 매매 제외
- group 후보가 없으면 현금 보유 또는 대체 규칙 적용 여부를 config로 제어

3. group 내부 선택:
- 초기 버전은 group별 대표 ETF 1개 선택
- 대표 ETF 기준:
  - 유동성 가장 높은 ETF 우선
- 확장 가능 구조로 만들 것:
  - top_k equal weight
  - inverse-vol weight

[거래비용/실행 가정]
1. 매수/매도 수수료 반영 구조
2. 슬리피지 반영 구조
3. 기본값은 config에서 설정 가능하게 할 것

[권장 구현 파일]
- `src/backtest/run_backtest_etf_allocation.py`
- `src/backtest/core/etf_allocation_engine.py`
- `src/backtest/portfolio/etf_regime_allocator.py`
- `src/backtest/configs/etf_allocation_config.py`
- `scripts/validate_etf_allocation_backtest.py`

실제 프로젝트 구조에 맞춰 파일명은 조정 가능하되 역할 분리는 유지하라.

[산출물]
1. ETF 자산배분 백테스트 실행 스크립트
2. 포트폴리오 규칙 config
3. 결과 CSV
   - summary
   - equity
   - weights
   - trades
4. validate 또는 smoke test 스크립트
5. TASK 04 문서

[결과 파일 예시]
- `reports/backtest_etf_allocation/etf_alloc_summary_{stamp}.csv`
- `reports/backtest_etf_allocation/etf_alloc_equity_{stamp}.csv`
- `reports/backtest_etf_allocation/etf_alloc_weights_{stamp}.csv`
- `reports/backtest_etf_allocation/etf_alloc_trades_{stamp}.csv`

[성과 지표]
summary에는 최소 아래를 포함하라.
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

가능하면 아래 구간별 성과도 함께 산출하라.
- 1Y
- 2Y
- 3Y
- 5Y
- FULL

[완료 기준]
1. ETF 코어 유니버스를 사용한 자산배분 백테스트가 실행된다
2. `risk_on / neutral / risk_off` 모드가 동작한다
3. 주간/월간 리밸런싱 중 최소 1개 이상 정상 동작한다
4. summary / equity / weights / trades가 생성된다
5. 거래비용/슬리피지 반영 구조가 존재한다
6. 기존 주식 백테스트 시스템에 회귀가 없다
7. validate 또는 smoke test가 통과한다

[이번 TASK에서 하지 말 것]
- 국면 산출 로직 자체의 고도화
- 리스크 패리티 최적화
- 변동성 타겟 정교화
- TR/분배금 반영
- ETF PDF/구성종목 반영
- 직접 공매도
- 실거래 주문 연동
- 웹서비스 UI 연결

[완료 후 보고 형식]
작업이 끝나면 아래 형식으로 정리하라.
1. 변경/추가한 파일 목록
2. 각 파일의 역할
3. 포트폴리오 구성 규칙 설명
4. 국면 -> 포트폴리오 매핑 설명
5. 실행 방법
6. validate 방법
7. 생성 산출물 목록
8. 남은 리스크/주의사항
9. 다음 작업 제안
   - TASK 05: S6 Risk-Off Defensive Allocation 고도화