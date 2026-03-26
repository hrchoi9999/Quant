# TASK_13_MARKET_ANALYSIS_PIPELINE_P0_20260323.md

## 1. 작업명

시장 분석 전용 오케스트레이션 P0
(공식 시장데이터 기반 7단계 시장상태 산출 + 웹 payload 생성)

## 2. 목적

이번 TASK의 목적은 기존 모델/백테스트 오케스트레이션과 분리된 `시장 분석` 전용 파이프라인을 설계하고 구현 준비를 마치는 것이다.

이 파이프라인은 아래를 담당한다.

1. 공식 시장데이터 수집
2. 시장 feature 계산
3. 시장 상태 7단계 산출
4. 정량/정성 분석 payload 생성
5. 웹서비스용 snapshot/API 입력 생성

## 3. 범위

### 이번 P0에서 반드시 할 것

- `KR` 시장 기준 오케스트레이션 구조 설계
- 공식 시장데이터 수집 구조 설계
- 시장 상태 점수/라벨 구조 설계
- 웹 payload 구조 설계
- 향후 `US` 확장이 가능한 스키마 설계

### 이번 P0에서 하지 않을 것

- 미국시장 실제 수집 구현
- 뉴스 수집 시스템
- 실시간 스트리밍
- AI 실호출 배포
- 시장 분석 UI 구현

## 4. 운영 방식

시장 분석은 기존 일일 백테스트 배치와 분리한다.

### 권장 스케줄

- 초기: 1시간 간격
- 장중 권장 예시:
  - 09:10
  - 10:10
  - 11:10
  - 13:10
  - 14:10
  - 15:40
  - 18:00

### 파이프라인 이름 제안

- `run_market_analysis_pipeline.py`

## 5. 핵심 입력 데이터

### 공식 데이터

- KOSPI (`1001`)
- KOSDAQ (`2001`)
- KOSPI200 (`1028`)
- USD/KRW
- 금리(기준금리, CD91, 국고채3Y, 국고채5Y)

### 내부 보조 데이터

- breadth 계산용 종목 가격
- ETF 상대강도 계산용 ETF 가격
- 인버스/달러/금/채권 ETF

## 6. 7단계 시장상태 정의

최종 라벨:

- 강상승
- 상승
- 강보합
- 중립
- 약보합
- 하락
- 강하락

산출 방식:

- trend_score
- breadth_score
- risk_score
- defensive_flow_score

를 합성한 `state_score`를 버킷화한다.

## 7. 산출물

### DB / 테이블

- `market_index_daily`
- `market_fx_daily`
- `market_rates_daily`
- `market_features_hourly`
- `market_component_scores`
- `market_state_history`
- `market_analysis_payload`
- `market_analysis_ai_notes`

### 웹 snapshot

- `market_analysis_summary.json`
- `market_analysis_detail.json`
- `market_analysis_manifest.json`

## 8. 웹 노출 구조

### 메인페이지

- 현재 시장상태
- 한 줄 요약
- 전일 대비 변화
- 핵심 신호 2개

### 오늘의 추천 페이지

- 현재 시장상태
- 추천 모델과 연결된 설명
- 대응 가이드 한 줄

### 시장 분석 페이지

- 7단계 상태
- 종합 점수
- 시장 방향
- 시장 건강도
- 시장 흔들림
- 방어자산 선호도
- 긍정 요인
- 주의 요인
- 대응 가이드
- 선택적 AI 해설

## 9. 개발 우선순위

1. 공식 시장데이터 수집 DB 구조
2. 시장 feature 계산 모듈
3. 상태 점수/라벨 산출 모듈
4. 웹 payload 생성기
5. 1시간 간격 오케스트레이션
6. 룰베이스 정성 해설
7. AI 해설(선택적)

## 10. 완료 기준

1. 시장 분석이 기존 백테스트 오케스트레이션과 분리된다.
2. 공식 시장지표를 메인 축으로 수집한다.
3. 7단계 상태 라벨이 산출된다.
4. 웹서비스용 summary/detail payload가 생성된다.
5. 향후 미국시장 확장이 가능한 구조를 갖춘다.
