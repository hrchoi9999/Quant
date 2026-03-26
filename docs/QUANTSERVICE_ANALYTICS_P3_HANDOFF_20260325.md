# QuantService Analytics P3 Handoff (2026-03-25)

이번 handoff는 `3차 묶음` 페이지 개발용 내부 preview 데이터 전달이다.
아직 사용자 웹서비스에 반영하거나 배포하지 않는다.
최종 반영은 사용자 컨펌 이후에만 진행한다.

## 범위
- 모델 품질 페이지
- 주간 브리핑 페이지

## 중요 원칙
1. 현재 payload는 내부 preview 전용이다.
2. `web_publish_enabled=false` 상태를 유지한다.
3. QuantService는 이 파일들을 mock/internal source로만 사용한다.
4. production API/current snapshot으로 합치지 않는다.
5. 사용자 컨펌 전까지 redbot.co.kr 실서비스에 연결하지 않는다.

## 사용 파일
- [bundle_manifest_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/bundle_manifest_20260325.json)
- [model_quality_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/model_quality_20260325.json)
- [weekly_briefing_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/weekly_briefing_20260325.json)

## 페이지별 사용 데이터
### 1. 모델 품질
파일:
- [model_quality_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/model_quality_20260325.json)

핵심 필드:
- `models[].latest_quality`
- `models[].quality_trend_26w[]`
- `models[].change_density`

추천 UI:
- 최신 품질 요약 카드
  - CAGR
  - MDD
  - Sharpe
  - 최근 4W / 12W
  - 현재 drawdown
- 최근 26주 품질 추이 차트
- 최근 변화 밀도 요약
  - new / exit / increase / decrease

### 2. 주간 브리핑
파일:
- [weekly_briefing_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/weekly_briefing_20260325.json)

핵심 필드:
- `models[].summary`
- `models[].briefing_points[]`
- `models[].top_holdings[]`
- `models[].one_week_changes[]`
- `models[].recent_changes_8w[]`

추천 UI:
- 모델별 브리핑 카드
- 핵심 bullet 3~4개
- 이번 주 변화 종목 섹션
- 최근 8주 변화 요약 섹션
- 상위 보유종목 5개 카드/표

## 권장 구현 순서
1. 모델 품질 페이지
2. 주간 브리핑 페이지

## 표현 주의
- 모델 품질 페이지는 운영성 데이터가 많으므로 카드/라인차트/표 조합이 적합하다.
- 주간 브리핑 페이지는 텍스트 summary + 상위 변화/상위 보유종목 혼합형이 좋다.
- 브리핑 문구는 현재 Quant가 만든 `briefing_points`를 우선 사용하고, QuantService에서 새 투자판단 문구를 임의 생성하지 않는다.

## 금지
- current web snapshot 교체 금지
- production API 연결 금지
- 실서비스 메뉴 노출 금지
- redbot.co.kr 반영 금지

## 완료 기준
1. 2개 페이지가 내부 환경에서 렌더링된다.
2. 위 2개 JSON 파일만으로 화면을 구성한다.
3. 사용자 컨펌 전까지 배포/실서비스 반영은 하지 않는다.
