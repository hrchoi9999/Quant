# S3 Bucket Transition Research Plan

## 목적

정적인 T3/T10/T30/T50 특성 분석을 넘어서, 종목이 `universe` 안에서 어떤 전이 과정을 거쳐 `T3`까지 올라가는지 관찰한다.

핵심 질문:

1. 종목은 `OUTSIDE -> T50_ex_T30 -> T30_ex_T10 -> T10_ex_T3 -> T3`로 실제로 이동하는가
2. 각 그룹에서 다음 시점에 상위 그룹으로 이동할 확률은 얼마인가
3. `T3`까지 올라간 종목들은 직전 3~5개 시점에서 어떤 경로를 밟는가
4. 이 전이 히스토리를 기반으로 새로운 discovery 모델을 만들 수 있는가

## 전이 상태 정의

- `OUTSIDE`: top 50% 밖
- `T50_ex_T30`: 30~50%
- `T30_ex_T10`: 10~30%
- `T10_ex_T3`: 3~10%
- `T3`: 0~3%

## 이번 산출물

- `s3_bucket_transition_panel`
- `s3_bucket_transition_matrix`
- `s3_bucket_transition_prob_summary`
- `s3_bucket_t3_path_examples`

모두 `D:\Quant\data\db\model_research.db`에 저장한다.

## 해석 원칙

- 이번 연구는 `S3`와 동일한 universe, 동일한 future-label 구조 안에서 본다.
- `T%`는 실제 시장 데이터 기반 사후 라벨이며, 포트폴리오 백테스트가 아니라 종목 단위 정답지다.
- 따라서 전이 확률은 `미래 상위 그룹 진입 가능성` 연구에 사용한다.
