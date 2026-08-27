# Harness Smart Brain 운영 전략

작성일: 2026-07-09
역할: redbot.co.kr 운영 상태와 Quant/QuantMarket/QuantAnalysis/QuantService 산출물 정합성을 총괄 점검하고, 각 스레드 작업을 지휘한다.

## 1. 하네스 역할 정의

하네스는 단순 실행기가 아니다.

하네스의 1차 역할은 다음이다.

- redbot.co.kr live 상태가 정상인지 점검한다.
- 각 스레드 폴더의 current/history/report 산출물이 최신인지 확인한다.
- 각 스레드 작업 지시 범위가 기존 직접 지시의 실제 완료 조건을 빠뜨리지 않도록 관리한다.
- 기준일, publish, validation, live API 반영 상태를 하나의 운영 표로 취합한다.
- 오류, stale, 미반영, 정책 범위 불명확 항목을 발견하면 다음 스레드에 정확히 지시한다.
- 주말에는 모델/AI 성능 개선 후보를 정리하되, 정책 변경 확정은 별도 승인 후 진행한다.

기본 원칙:

`하네스 범위 = 기존 직접 지시의 실제 완료 조건 + 명시적 금지 조건 + live 운영 정합성 확인`

날짜 원칙:

- 하네스 `asof`는 사용자가 요청한 운영/실행 기준일이다.
- 실제 데이터 기준일은 각 시스템의 최신 가용 거래일인 `data_asof`로 별도 확정한다.
- 장 마감 전, 데이터 적재 전, 휴장일 직후처럼 최신 DB/mart가 전 거래일까지인 경우에는 전 거래일을 `data_asof`로 사용하고 stale로 보지 않는다.
- public/GCS/live 결과에는 `asof`와 `data_asof`의 차이를 보고해야 하며, 데이터는 전 거래일인데 오늘 날짜로 최신 데이터처럼 표시하면 안 된다.

## 2. 시스템별 운영 책임

### Quant

담당:

- 주중 전반부 데이터 refresh
- 주중 후반부 `daily_light` 모델/current 산출
- public current/history payload 생성
- admin current/AI shadow payload 생성
- pre-GCS validation
- canonical user snapshot GCS publish

핵심 산출물:

- `D:\Quant\service_platform\web\public_data\current\publish_manifest_user.json`
- `D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json`
- `D:\Quant\service_platform\web\public_data\current\user_performance_summary.json`
- `D:\Quant\service_platform\web\public_data\current\user_recent_changes.json`
- `D:\Quant\service_platform\web\public_data\history\user_model_performance_history.json`
- `D:\Quant\service_platform\web\admin_data\current\internal_model_validation_current.json`
- `D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json`

live 확인:

- `https://redbot.co.kr/api/v1/model-snapshots/today`

### QuantMarketData

담당:

- 시장데이터 수집
- US/global environment 갱신
- market context mart current 갱신
- forecast calibrated current 갱신
- Quant handoff 생성/검증

핵심 산출물:

- `D:\QuantMarket\service_platform\ai_training\market_context\current\market_model_input_daily_current.csv`
- `D:\QuantMarket\service_platform\ai_training\market_context\current\market_forecast_ai_calibrated_daily_current.csv`

### QuantMarket

담당:

- 시장분석 payload 생성
- QuantService market handoff current 갱신
- 3축 그래프 입력 freshness 확인
- market-analysis GCS remote publish

핵심 산출물:

- `D:\QuantMarket\service_platform\web\public_data\handoff\quantservice\current\quantservice_market_manifest.json`
- `D:\QuantMarket\service_platform\web\public_data\handoff\quantservice\current\api_v1_market_analysis_page.json`

live 확인:

- `https://redbot.co.kr/api/v1/market-analysis/manifest`
- `https://redbot.co.kr/api/v1/market-analysis/page`

### QuantAnalysis

담당:

- 투자 포트폴리오 업데이트
- `portfolio_pipeline.py --asof <target_asof>` 실행
- 투자 포트폴리오 GCS current/history publish
- 투자 포트폴리오 selection history, top10/top3 후보 성과, benchmark-relative 성과 점검
- source model attribution과 개선 검증 후보 보고
- top3와 rank4~10 성과 격차, weak/strong model combination, 정책 변경 없는 개선 후보 보고

핵심 산출물:

- `D:\QuantAnalysis\outputs\investment_portfolio_latest.json`
- `D:\QuantAnalysis\docs\portfolio\investment_portfolio_latest.md`
- `D:\QuantAnalysis\outputs\daily_portfolio_selection_history_*.json`
- `D:\QuantAnalysis\analysis.db`
- GCS: `gs://quantservice-489808-market-analysis/admin/current/investment_portfolio_latest.json`

### QuantService

담당:

- redbot.co.kr 웹/API 렌더링
- remote GCS current 조회
- local fallback 보관

운영 원칙:

- QS는 source thread의 직접 GCS publish 결과를 읽는다.
- QS local sync는 기본적으로 fallback/복구 용도다.
- QS 코드 수정은 하네스가 직접 하지 않고 작업요청서로 전달한다.

## 3. 현재 확인된 운영 상태

기준: 2026-07-09 확인

| 영역 | 현재 상태 | 판단 |
|---|---:|---|
| Quant local public current | 2026-07-07 | 2026-07-08 기준 실행에는 stale |
| Quant history performance | 2026-07-07 | 2026-07-08 validation 실패 원인 |
| live user model API | 2026-06-24 | GCS/live publish 미반영 |
| QuantMarket live market-analysis API | 2026-07-09 22:00 | 최신화 진행됨 |
| QuantAnalysis latest portfolio | 2026-06-28 | 투자 포트폴리오 stale |
| AI learning models current | 2026-07-03 | 일부 core AI freshness 점검 필요 |

현재 핵심 문제:

1. 사용자 모델 snapshot publish가 하네스 지시 범위에서 누락되어 live API가 2026-06-24에 멈췄다.
2. 2026-07-08 daily contract는 `user_model_performance_history` 기준일 불일치로 실패했다.
3. QuantAnalysis 투자 포트폴리오 산출물도 2026-06-28에 머물러 있다.
4. QuantMarket은 2026-07-09 22:00 기준까지 갱신되어, 시스템별 최신성이 서로 어긋나 있다.

## 4. 하네스 운영 SLO

주중 하네스 완료 조건:

- WD01~WD06 모든 stage가 completed 또는 명시 승인된 acceptable 상태여야 한다.
- Quant public current/history 기준일이 target asof 또는 latest common asof와 일치해야 한다.
- QuantMarket market-analysis live API 기준일이 WD02/WD03에서 확정한 `data_asof` 기준 publish 결과와 일치해야 한다.
- QuantAnalysis portfolio current/live source 기준일이 target asof 또는 승인된 포트폴리오 기준일과 일치해야 한다.
- `pre_gcs_publish` validation이 통과해야 한다.
- GCS publish가 수행되어야 한다.
- redbot.co.kr live API가 publish 결과를 반환해야 한다.
- 최종 보고에는 전체 소요시간과 stage별 소요시간이 포함되어야 한다.

completed 금지 조건:

- live user model API stale
- market-analysis remote manifest stale
- portfolio current stale
- public history payload stale
- validation failure
- publish 권한/네트워크 실패
- 기준일 불일치가 known_issues에만 남고 완료 처리되는 경우

## 5. 주중/주말 분리 원칙

주중:

- daily_light 중심
- 데이터/current/publish/검증 중심
- 정책 변경 금지
- public current publish 허용

주말:

- Quant 모델 스레드만 실행
- research_full/research_validation/AI 검증 중심
- QuantMarket/QuantAnalysis 실행 없음
- public current GCS publish 없음
- 정책 후보와 보류 의견만 정리

주중/주말 동시 실행은 금지한다.

## 6. 하네스 발전 전략

### 6.1 운영 상태 감사 기능

다음 단계에서 별도 audit 기능을 만든다.

예정 기능:

- local current/history 기준일 수집
- GCS/live API 기준일 수집
- QuantMarket/QuantAnalysis source 기준일 수집
- validation report와 timing report 연결
- `ok/stale/blocked/unknown` 상태 판정
- 최종 표준 보고서 생성

예상 산출물:

- `reports/harness_operational_audit/<run_id>/redbot_operational_state.json`
- `reports/harness_operational_audit/<run_id>/redbot_operational_state.md`

### 6.1A 포트폴리오 성과 거버넌스

WD05는 투자 포트폴리오 최신화만 확인하면 안 된다. 하네스는 QuantAnalysis 산출물을 근거로 다음을 취합한다.

- selection history 전체 성과
- top10 후보 성과
- top3 후보 성과
- rank4~10 후보 성과와 top3 대비 격차
- benchmark-relative 성과
- source model attribution
- weak/strong model combination
- weak/REVIEW/retired 모델 노출 여부
- stock/ETF/cash 비중, top3 필터, relative-to-index 필터, drawdown/turnover 추가 산출 같은 개선 후보

예상 산출물:

- `reports/harness_portfolio_governance/<run_id>/portfolio_governance_review.json`
- `reports/harness_portfolio_governance/<run_id>/portfolio_governance_review.md`

하네스는 포트폴리오 정책, 실제 비중, 모델 편입/제외를 직접 확정하지 않는다. 개선 후보는 QuantAnalysis와 Quant Model 스레드 검증 후 사용자 승인으로만 운영 반영한다.

### 6.2 프롬프트 품질 게이트 강화

각 stage prompt에는 다음을 반드시 포함한다.

- target asof
- latest common asof 허용 여부
- local current 확인 대상
- GCS publish 여부
- live API 확인 대상
- completed 금지 조건
- 다음 stage로 넘길 evidence

### 6.3 운영 원칙 레지스트리

각 시스템별 운영 원칙을 하네스가 참조할 수 있게 별도 registry로 관리한다.

필요 항목:

- source thread
- 담당 산출물
- canonical local path
- canonical GCS path
- live API URL
- freshness rule
- allowed fallback rule
- blocked condition

### 6.4 모델/AI 개선 전략 루프

주말 하네스 close에서 다음을 자동 요약한다.

- public model 성과 악화 항목
- internal model REVIEW/PASS 상태
- AI learning model stale 항목
- overlay shadow 개선/악화 항목
- E-series risk/return 개선 후보
- 다음 주 실험 후보와 보류 후보

단, public 모델 정책 변경은 live-only evidence와 사용자 승인 없이 적용하지 않는다.

## 7. 즉시 보완 우선순위

1. 2026-07-08/이후 주중 파이프라인에서 Quant user snapshot GCS publish와 live API 확인을 복구한다.
2. `user_model_performance_history` 기준일 불일치를 해결한다.
3. QuantAnalysis `portfolio_pipeline.py --asof <target_asof>` 실행과 GCS publish를 복구한다.
4. WD06/WD07 live API freshness gate를 하네스 완료 조건으로 강제한다.
5. 별도 운영 상태 감사 스크립트/리포트를 만든다.
6. 주말 하네스에 모델/AI 개선 후보 요약을 고정한다.
