# ETF PIT Backfill Plan (2026-03-31)

## 목적
- `T-ETF-V01`을 `2017`부터 다시 검증할 수 있게, ETF용 point-in-time monthly universe를 구축한다.
- ETF는 주식과 달리 상장/폐지/유동성 변화가 크므로, 단순히 최신 `ETF 200`을 과거에 투영하지 않는다.

## 왜 PIT universe가 필요한가
- 현재 ETF 가격 데이터는 `2013-12-26`부터 존재한다.
- 하지만 `instrument_master.first_seen`, `etf_meta.asof` 기반 파생 메타는 `2024-01`부터 안정적으로 관리된다.
- 따라서 ETF backfill의 핵심 제약은 가격이 아니라 **과거 시점에서 어떤 ETF를 universe에 포함할지**이다.

## 기본 원칙
1. 월말 마지막 거래일을 `selection_asof`로 사용한다.
2. `prices_daily`에서 실제로 해당 월말 가격이 존재하는 ETF만 후보로 본다.
3. `prices_daily`의 최초 가격일을 `first_price_date`로 보고 사실상의 상장 시작점으로 사용한다.
4. trailing history와 trailing liquidity를 통과한 ETF만 universe 후보로 인정한다.
5. 메타 분류는 `etf_meta.asof <= selection_asof`가 있으면 그 값을 사용한다.
6. 과거 메타가 없으면 가장 이른 `etf_meta` snapshot을 backward-fill 해서 surrogate PIT 분류로 사용한다.

## V1 선정 규칙
- 최소 history: `120` trading days
- 최소 trailing liquidity: `20일 평균 거래대금 20억`
- 레버리지 제외
- 인버스는 `hedge_inverse_kr`만 허용
- 그룹 cap은 현재 `ETF extended 200`과 동일하게 유지
- 목표 universe 크기: `최대 200개`

## 해석 주의
- 이 구조는 `perfect PIT metadata`가 아니라 `price-anchored PIT universe + surrogate metadata`이다.
- 따라서 `2017~2023` 구간의 ETF 분류는 일부 현재/후행 분류가 섞일 수 있다.
- 그래도 `최신 ETF 200을 과거에 그대로 투영하는 방식`보다 훨씬 현실적이다.

## 단계별 로드맵
1. PIT monthly universe 생성
2. PIT universe 기준 `ET%` 정답지 재생성
3. ETF transition panel 재생성
4. strict walk-forward 재검증
5. `T-ETF-V01` threshold / risk filter / shadow tracking 재튜닝

## 이번 단계 산출물
- 스크립트: `D:\Quant\scripts\build_universe_etf_pit_backfill.py`
- 월별 universe: `D:\Quant\data\universe\etf_pit_backfill\universe_etf_pit_monthly_201701_202603.csv`
- 요약: `D:\Quant\reports\model_upgrade_research\20260331\ETF_PIT_BACKFILL\etf_pit_backfill_monthly_summary_201701_202603.csv`
