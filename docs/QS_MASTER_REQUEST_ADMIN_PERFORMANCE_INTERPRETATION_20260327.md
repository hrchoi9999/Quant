# QS 요청 제출처: QS-Master
- 권장 담당 쓰레드: QS-Admin-Preview, QS-Quant-Handoff
- 공개 반영 포함 여부: No
- Admin only 여부: Yes
- 관련 시스템: Quant

## 요청 배경
/admin 의 `모델품질` 페이지에서 특히 `S3`, `S3 Core2`의 최근 12주 성과가 크게 보일 때, 운영자/검토자가 숫자의 맥락을 바로 해석할 수 있도록 Quant 쪽 preview payload에 성과 해석 보조 필드를 추가했습니다.

이번 변경은 public 웹 반영이 아니라 internal preview/admin 용도입니다.

## Quant 쪽 반영 완료 사항
대상 파일:
- `D:\Quant\reports\service_analytics_review\20260325\p3_bundle\model_quality_20260325.json`
- `D:\Quant\reports\service_analytics_review\20260325\p3_bundle\weekly_briefing_20260325.json`

추가된 필드:
- `models[].performance_interpretation`

세부 필드:
- `window_weeks`
- `window_start_week_end`
- `window_end_week_end`
- `cumulative_return_12w`
- `best_weekly_return_12w`
- `best_weekly_return_week_end`
- `worst_weekly_return_12w`
- `worst_weekly_return_week_end`
- `positive_weeks_12w`
- `negative_weeks_12w`
- `flat_weeks_12w`
- `annualized_volatility_12w`
- `top_contributors_12w[]`
  - `ticker`
  - `name`
  - `estimated_contribution_12w`

## 기대 효과
- 최근 12주 수익률이 크게 보일 때 단순 headline 숫자만 보지 않고,
  - 어느 기간을 본 것인지
  - 최고/최악 주간이 언제였는지
  - 상승/하락 주 수가 어땠는지
  - 어떤 종목이 성과를 끌어올렸는지
  를 admin에서 바로 해석할 수 있습니다.

## QS 작업 요청
### 1. 모델품질 페이지
각 모델 카드 또는 상세 영역에 `performance_interpretation` 블록을 표시해 주세요.

권장 표시 항목:
- 최근 12주 기준 구간
- 최근 12주 누적수익률
- 최고 주간 수익률 / 기준 주간
- 최저 주간 수익률 / 기준 주간
- 상승 주 수 / 하락 주 수 / 보합 주 수
- 최근 12주 연환산 변동성
- 상위 기여 종목 3~5개

### 2. 주간 브리핑 페이지
`weekly_briefing.models[].performance_interpretation`를 활용해서,
- `왜 최근 12주 성과가 크게 보이는지`
- `어느 주간 변동이 컸는지`
- `상위 기여 종목이 무엇인지`
를 보조 정보로 보여 주세요.

### 3. 표현 원칙
- 투자 권유형 문구 금지
- `최근 12주 성과 해석`, `성과 구간`, `상위 기여 종목`, `변동성 참고` 같은 설명형 표현 사용
- `추정 기여`라는 점이 드러나도록 표시
  - 예: `상위 추정 기여 종목`

### 4. 배포 원칙
- 이번 변경은 admin preview 전용입니다.
- public 영역, current snapshot, production API에는 붙이지 마세요.
- `internal_preview_only = true`, `web_publish_enabled = false` 전제를 유지하세요.

## 참고
이번 필드는 QuantService가 추가 계산하지 않도록 Quant 쪽에서 미리 생성한 해석 보조 데이터입니다.
숫자 재계산 없이 그대로 표시하는 방식으로 연결하면 됩니다.
