# QS 작업 요청: I-series 내부용 모델 화면 반영

## 작업명

I-STOCK-STRONG-RSI-V01 admin 내부용 모델 페이지 반영

## 요청 출처

Quant 모델 쓰레드

## 배경

Quant 쪽에서 신규 I-series shadow 모델 `I-STOCK-STRONG-RSI-V01`을 주간 파이프라인과 admin current/history payload에 연결했습니다.

이 모델은 공개 사용자 모델이 아니라 관리자 로그인 상태에서만 확인하는 내부용 모델입니다.

## Quant 반영 완료 내용

- 주간 파이프라인 기본 흐름에 I-series shadow refresh 추가
- `admin_new_entry_tracker.json`의 `internal_models` scope에 I-series 이벤트 row 추가
- `weekly_rankings.internal_models`에 I-series 주간 순위/점수 추가
- `model_performance_summary.internal_models`에 I-series 성과 요약 추가
- `internal_model_performance_history.json`에 I-series 성과 history 추가
- canonical GCS publish 대상은 기존 admin current/history publish 흐름을 그대로 사용

## QS 요청 사항

1. admin `내부용 모델` 페이지에 아래 모델을 기존 내부용 모델들과 같이 노출

- model_code: `I-STOCK-STRONG-RSI-V01`
- 권장 표시명: `I-series Strong RSI`
- 한글 표시명: `I 강한 RSI 초기상승형`
- scope: `internal_models`
- visibility: admin only

2. 모델 선택기/정렬에 추가

- 기존 S-series 내부 모델 아래 또는 별도 I-series 그룹으로 배치
- 공개 사용자 메뉴에는 노출하지 않음

3. 기존 내부용 모델과 같은 필드로 렌더링

- 성과 카드: CAGR, 1Y MDD, 1Y SHARPE
- 기간별 성과: 1W, 2W, 1M, 3M, 6M, 1Y, ITD
- 신규 편입/재편입/비중 증가 이벤트
- 순위/전략 적합도:
  - `rank_no`
  - `score`
  - `score_basis = i_raw_score`
  - `universe_rank_no`
  - `universe_rank_score`
  - `display_score`

4. 이벤트 타입 처리

- `new_entry`: 신규 편입
- `re_entry`: 재진입
- `weight_increase`: candidate에서 core로 승격된 내부 관찰 강도 증가 이벤트

## Quant 검증 결과

기준일: `2026-04-29`

- admin tracker validation: passed
- history payload validation: passed
- internal event/ranking match ratio: 100%
- internal direct score population ratio: 100%
- `I-STOCK-STRONG-RSI-V01` performance coverage: 100%
- latest ranking rows: 30

샘플 최신 top ranking:

- `033100` 제룡전기, rank 1, score 125.0
- `018670` SK가스, rank 2, score 121.0
- `454910` 두산로보틱스, rank 3, score 121.0

## 완료 기준

1. admin 로그인 상태에서 `내부용 모델` 페이지에 `I-STOCK-STRONG-RSI-V01`이 표시됨
2. 성과 카드와 기간별 성과가 공란 없이 표시됨
3. 신규 편입/재진입/weight increase 이벤트가 조회됨
4. 최신 30개 후보의 순위와 score가 표시됨
5. 비로그인/공개 영역에는 노출되지 않음
