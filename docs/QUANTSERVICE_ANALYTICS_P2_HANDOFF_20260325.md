# QuantService Analytics P2 Handoff (2026-03-25)

이번 handoff는 `2차 묶음` 페이지 개발용 내부 preview 데이터 전달이다.
아직 사용자 웹서비스에 반영하거나 배포하지 않는다.
최종 반영은 사용자 컨펌 이후에만 진행한다.

## 범위
- 포트폴리오 구조 페이지
- 보유 종목 이력 페이지

## 중요 원칙
1. 현재 payload는 내부 preview 전용이다.
2. `web_publish_enabled=false` 상태를 유지한다.
3. QuantService는 이 파일들을 mock/internal source로만 사용한다.
4. production API/current snapshot으로 합치지 않는다.
5. 사용자 컨펌 전까지 redbot.co.kr 실서비스에 연결하지 않는다.

## 사용 파일
- [bundle_manifest_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/bundle_manifest_20260325.json)
- [portfolio_structure_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/portfolio_structure_20260325.json)
- [holding_lifecycle_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/holding_lifecycle_20260325.json)

## 페이지별 사용 데이터
### 1. 포트폴리오 구조
파일:
- [portfolio_structure_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/portfolio_structure_20260325.json)

핵심 필드:
- `models[].latest_asset_mix`
- `models[].asset_mix_trend_26w[]`
- `models[].current_allocation_breakdown[]`
- `models[].concentration`
- `models[].quality_context`

추천 UI:
- 최신 자산구조 stacked bar
- 최근 26주 구조 추이 area/stacked chart
- 현재 보유 비중 테이블
- concentration 카드
  - top1
  - top3
  - top5
- 최근 4W / 12W 보조 카드

### 2. 보유 종목 이력
파일:
- [holding_lifecycle_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/holding_lifecycle_20260325.json)

핵심 필드:
- `models[].current_holdings_lifecycle[]`
- `models[].longest_historical_holdings[]`
- `models[].recent_new_entries_8w[]`
- `models[].recent_exits_8w[]`
- `models[].current_holding_highlights[]`

추천 UI:
- 현재 보유 종목 lifecycle table
- 장기 보유 종목 top table
- 최근 신규/제외 종목 섹션
- 종목별 보유기간 badge
- 최신 비중/최근 편입 여부 표시

## 권장 구현 순서
1. 포트폴리오 구조 페이지
2. 보유 종목 이력 페이지

## 표현 주의
- 이번 페이지는 데이터 설명형 성격이 강하므로 카드 + 표 + 중간 정도의 차트 조합이 적합하다.
- 지나치게 복잡한 인터랙션보다 비교 가능한 시계열과 테이블 가독성을 우선한다.
- 종목코드는 기존 규칙대로 문자열 그대로 노출한다.

## 금지
- current web snapshot 교체 금지
- production API 연결 금지
- 실서비스 메뉴 노출 금지
- redbot.co.kr 반영 금지

## 완료 기준
1. 2개 페이지가 내부 환경에서 렌더링된다.
2. 위 2개 JSON 파일만으로 화면을 구성한다.
3. 사용자 컨펌 전까지 배포/실서비스 반영은 하지 않는다.
