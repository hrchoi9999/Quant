# Quant Backtest Refactoring Project State

Date: 2026-02-12

------------------------------------------------------------------------

# 1. 프로젝트 목적

목표는 **레거시 S2 전략 백테스트 시스템과 리팩토링 시스템의 완전
동치(또는 거의 동일) 상태 확보**입니다.

동치 기준:

-   TOTAL / 1Y / 2Y / 3Y / 5Y 성능지표
-   equity curve
-   snapshot (보유 종목 30 + CASH)
-   ledger / trades_C
-   perf_windows / summary

------------------------------------------------------------------------

# 2. 현재 문제 요약

## 핵심 증상

-   holdings는 정상 (마지막 리밸런스 2026-02-04, 비캐시 30종목 존재)
-   snapshot은 계속 CASH 1줄 (Count=1)

이는 전략 실패가 아니라:

> snapshot 생성 단계에서 ticker → close_wide 컬럼 매칭이 전부 실패하여
> 종목이 drop되는 현상

------------------------------------------------------------------------

# 3. 원인 분석

### 확인된 사실

1.  holdings 총 row = 8982
2.  마지막 리밸런스 날짜 = 2026-02-04
3.  해당 날짜 noncash_count = 30
4.  snapshot 결과 = CASH 1줄

→ snapshot 로직에서 종목 가격 조회 실패 패턴

### 근본 원인

ticker 자료형/포맷 불일치:

-   holdings ticker = '065350' (6자리 문자열)
-   close_wide columns = 65350 (int) 또는 '65350'

→ close_wide.loc\[date, ticker\] KeyError → 예외 continue → 30종목 전부
drop → CASH-only snapshot

------------------------------------------------------------------------

# 4. 수행된 패치 내역

## 1차: fill_bundle 수정

-   rebalance_date 유지
-   snapshot carry-forward 제거

## 2차: csv_plugin 기본 prefix 보강

## 3차\~4차: legacy_reports ticker resolver 강화

-   zfill(6)
-   strip
-   A 제거
-   numeric equivalence

## 5차: A안(전역 표준화)

-   ticker = 문자열 6자리로 통일
-   core/data.py 수정
-   core/engine.py 수정
-   fill_bundle 수정
-   legacy_reports 수정
-   core/tickers.py 신규 생성

현재 상태: - 패치 적용 후에도 snapshot Count=1 유지

------------------------------------------------------------------------

# 5. 왜 snapshot에서만 터지는가?

다른 CSV는 단순 출력만 수행.

snapshot만 ticker로 가격을 조회:

    close_wide.loc[snapshot_date, ticker]

여기서 타입/포맷 불일치 시 즉시 실패.

------------------------------------------------------------------------

# 6. 레거시 시스템과 차이 가능성

레거시는 다음 중 하나였을 가능성:

1)  가격 로더 단계에서 ticker를 문자열 6자리로 고정
2)  snapshot 생성 시점에서 더 강한 정규화 수행

리팩토링 과정에서 pandas read_sql / pivot 과정에서 ticker dtype이 int로
변환되었을 가능성 높음.

------------------------------------------------------------------------

# 7. 현재 리팩토링 진행 단계

  단계   목표                 상태
  ------ -------------------- -----------
  P0     CLI/옵션 안정화      완료
  P1     모듈 분리            완료
  P1-1   ticker 표준화        패치 적용
  P1-2   snapshot 동치 확보   실패 상태
  P1-3   perf_windows 동치    대기
  P1-4   ledger/trades 동치   대기
  P1-5   golden 확정          대기

------------------------------------------------------------------------

# 8. 다음 대화에서 해야 할 것

1)  close_wide.columns 실제 dtype 확인
2)  snapshot 직전 close_wide.columns 샘플 출력
3)  실행 시 import 경로 확인
4)  snapshot 생성 함수에 디버그 로그 삽입

------------------------------------------------------------------------

# 9. 현재 결론

-   전략은 정상
-   holdings는 정상
-   snapshot 실패 원인은 ticker ↔ price 컬럼 매칭 실패
-   A안 패치가 실제 실행 코드에 반영되었는지 검증 필요

------------------------------------------------------------------------

# 10. 목표 상태

레거시와 다음 항목이 동일해야 함:

-   snapshot row 수 (30+1)
-   perf_windows CAGR/MDD/Sharpe
-   equity curve 차이 0 또는 허용 오차 내
-   ledger/trades 건수 및 날짜 동일

------------------------------------------------------------------------

(End of Project State Document)
