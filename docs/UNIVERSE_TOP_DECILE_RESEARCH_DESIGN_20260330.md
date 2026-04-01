# Universe Top-3% Research Design
## (Universe 내부 상위 3% 종목 연구용 테이블 설계)

### 1. 목적
S2 축 연구가 끝난 뒤에는, 각 모델이 실제로 보는 universe 안에서
- 높은 forward return
- 낮은 path MDD
를 동시에 보인 상위 3% 종목을 따로 모아 연구한다.

이 테이블은 전체 상장 종목이 아니라 반드시 `model universe` 안에서만 만든다.

### 2. 입력 데이터
- `reports/score_correlation_review/20260330/selected_vs_not_selected_3m_6m_1y_detail.csv`
- `price.db.instrument_master`

### 3. 산출 DB
- `data/db/model_research.db`

### 4. 핵심 테이블
#### universe_top_3pct_candidates
행 단위:
- model_code
- horizon (`3M`, `6M`, `1Y`)
- signal_date
- end_date
- ticker
- name
- market
- selected
- fwd_ret
- path_mdd
- return_pct_rank
- mdd_pct_rank
- composite_score
- top_threshold
- top_flag
- top_rank
- top_bucket_label

#### universe_top_3pct_summary
집계 단위:
- model_code
- horizon
- ticker
- name
- market
- top_observations
- avg_fwd_ret
- avg_path_mdd
- selected_hit_rate
- avg_composite_score
- top_bucket_label

### 5. composite_score 정의
기본안:
- return percentile rank: 70%
- MDD percentile rank: 30%

즉,
- 수익률이 높을수록 가점
- MDD가 덜 나쁠수록 가점
- 각 signal_date / horizon 내부에서 top 3%를 추출

### 6. 활용 목적
- 상위 3% 종목의 공통 특징 연구
- S2 조건 재설계 후보 도출
- 신규 signal universe 설계
- model upgrade hypothesis 생성
