# Prompt Handoff Harness

## AI 폐지 및 WD05 영구 소비 호환 (2026-09-25)

- 승인된 Quant 1.0 AI/T 영구 폐지가 아래 과거 AI freshness·주말 학습 안내보다 우선한다. 현재 비AI 모델은 S2/S3/S3_CORE2/S3_ACCEL_V01/S4/S5이며 T 모델과 AI current 파일을 실행/필수 입력으로 요구하지 않는다. 과거 기록은 보존한다.
- 신규 승인 WD05는 기존 cycle 입력 pin과 함께 `--ai-retirement-operating-compatibility-manifest D:/QuantAnalysis/reports/ai_retirement_20260925/operating_compatibility_manifest.json --ai-retirement-operating-compatibility-sha256 e1961e4574b3385dddef98503a8f990acb934fe068c8cd957022610dd6cfbdee`를 전달한다. 실행 전 QA compiled pin/파일/proof를 재대조하며 불일치는 해당 단계만 보류한다.
- 영구 호환 gate는 일회성 release activation과 별개다. 이전 payload SHA/generation을 새 cycle에 고정하지 않으며, 이 연결은 새 수집/게시 승인이나 일회성 게시 완료 선언이 아니다.

## 목적

`Quant`, `QuantMarket`, `QuantAnalysis` 스레드가 주중 업데이트를 프롬프트 기반으로 순서대로 진행하도록 상태와 다음 지시문을 관리한다. 주말 업데이트는 Quant 모델/AI 검증 중심이므로 Quant 모델 스레드만 사용한다.

## 범위

- 실행파일 직접 실행 없음
- Codex thread 프롬프트 자동 전달 가능
- 자동 승인 없음
- 주중/주말 동시 실행 금지
- 자동 반복 실행 금지
- 자동 매매/자동 배포 없음
- 주중 public current/GCS publish는 WD06의 `pre_gcs_publish` 검증 통과 후에만 수행한다.
- Harness 프롬프트는 기존에 사용자가 각 thread에 직접 지시하던 운영 범위를 넘기지 않는다.
- 새 장기 작업, full rebuild, research_full, 정책 변경은 명시 승인 전까지 기본 stage 범위에서 제외한다. 단, WD02의 market context mart/forecast current 갱신과 WD03의 마켓분석 payload/QuantService handoff/GCS 게시 갱신은 기존 직접 지시 범위에 포함한다.
- 기존 직접 지시보다 범위가 넓어질 것 같으면 대상 thread는 실행하지 않고 `blocked`로 보고한다.
- 프롬프트 하네스가 운영 orchestration의 primary이며, command 하네스는 diagnostic-only 보조 도구다.
- Quant 모델/AI 학습모델 상태 변경은 Quant Model 스레드에서만 수행한다. 하네스는 `D:\Quant\config\harness\model_scope_registry.yaml`과 current validation payload를 읽어 실행 전 scope gate와 모델 성능 거버넌스 점검을 수행한다.
- retired/research_archive/excluded 모델은 기본 파이프라인에서 제외하고, REVIEW 모델은 자동 제외하지 않고 주말 검토 후보로만 보고한다.
- 하네스는 전략 모델과 AI 학습 모델의 성능 점검 결과를 취합해 성과 우수 모델의 확장 후보, 성과 저하 모델의 정리 후보, 신규 모델 개발 후보를 Quant Model 스레드에 지시한다. 모델 승격/강등/폐기/정책 변경은 사용자 승인 전 확정하지 않는다.
- 하네스는 QuantAnalysis 투자 포트폴리오 구성 결과도 성능 거버넌스 대상으로 본다. WD05는 포트폴리오 최신화/publish 확인뿐 아니라 selection history, top10/top3, benchmark-relative 성과, source model attribution, 개선 검증 후보를 보고한다. 포트폴리오 정책/비중 변경은 사용자 승인 전 확정하지 않는다.

## Command Harness에서 이관된 기능

- stage 순서 관리
- weekday/weekend 분리 정책
- thread target mapping
- timebox 기준
- stage report quality gate
- evidence/known_issues 기록
- blocked/failed 상태 전파
- run summary/closeout
- model performance governance review
- portfolio performance governance review

command 하네스는 safe echo, preflight, 짧은 점검 command 검증에만 사용한다. 기존 직접 지시 범위를 정확히 대체하지 못하는 command는 `manual_prompt_only`로 둔다.

## 주중 순서

1. `WD01_QUANT_FRONT` - Quant
2. `WD02_MARKET_COLLECT` - QuantMarketData / 시장데이터수집 작업
3. `WD03_MARKET_ANALYSIS` - QuantMarket
4. `WD04_QUANT_REAR` - Quant
5. `WD05_PORTFOLIO_ANALYSIS` - QuantAnalysis
6. `WD06_PRE_GCS_PUBLISH` - Quant
7. `WD07_HARNESS_CLOSE` - Quant

## 주말 순서

1. `WE01_QUANT_WEEKEND_PIPELINE` - Quant
2. `WE06_HARNESS_CLOSE` - Quant

주말에는 QuantMarket, QuantMarketData, QuantAnalysis 스레드로 프롬프트를 보내지 않는다.

## Stage Scope

- `WD01_QUANT_FRONT`: 평소 직접 지시 수준의 주중 전반부 데이터 refresh와 freshness 확인만 수행한다. full model run, research_full, 정책 변경, public publish 확정은 제외한다.
- `WD02_MARKET_COLLECT`: 기존 직접 지시의 시장데이터 수집 파이프라인 범위로 market_analysis public payload, US/global environment, market context mart current, forecast calibrated current, 3축 그래프 입력 데이터, 최신 가용 Quant handoff를 갱신/확인한다. 하네스 `asof`는 요청/운영일이고, 실제 데이터 기준일은 DB/mart/market source의 최신 가용 거래일인 `data_asof`로 분리한다. 장 마감/데이터 적재 전이라 최신 데이터가 전 거래일까지면 그 날짜를 `data_asof`로 확정하고 stale로 보지 않는다. 기본 timebox는 30분이다. `market_model_input_daily_current.csv`와 `market_forecast_ai_calibrated_daily_current.csv`가 `data_asof`보다 stale이면 WD03로 넘기기 전에 `run_daily_market_ai_training_update.py --profile operational --expected-asof <data_asof>` 또는 동등한 운영용 market context mart refresh를 수행하고 public payload를 재생성한다. `--profile full` 또는 AI v1.1 학습/비교 단계는 WD02에서 실행하지 않는다. 시장분석 public payload는 `--publish-remote` 또는 `publish_market_analysis_remote.py --asof <data_asof>T19:00:00+09:00` 동등 절차로 remote current까지 갱신하고 검증한다. 갱신 실패 시 `blocked_needs_operational_mart_refresh`, `blocked_needs_market_context_mart_refresh`, `blocked_forecast_source_stale`, `blocked_quant_handoff_unavailable`처럼 원인을 명확히 보고한다.
- `WD03_MARKET_ANALYSIS`: 기존 직접 지시의 마켓분석 진행 범위로 최신 가용 데이터 기준일(`data_asof`)의 시장분석 payload 생성, QuantService handoff current 갱신, 시장 브리핑 3축 그래프 값 반영 확인, GCS 원격 게시, remote current manifest 확인까지 수행한다. WD01/WD02 완료와 market context mart/forecast current freshness를 선행조건으로 확인하되, 하네스 `asof`와 `data_asof`가 달라도 `data_asof`가 최신 가용 거래일이면 stale로 처리하지 않는다. `publish_asof`는 웹/GCS 게시 기준시각이고 `data_asof`는 mart/forecast 실제 기준일로 분리 보고한다. mart가 `data_asof`보다 stale이면 기존 직접 지시 범위에 맞게 market context/model input mart 갱신을 진행하거나 `blocked_needs_market_context_mart_refresh`, `blocked_forecast_source_stale`로 보고한다. GCS 게시 실패, remote current manifest 미갱신, handoff 기준일 불일치, stale mart가 있으면 completed로 처리하지 않는다. 자동매매, 정책 변경, full rebuild, research_full은 제외한다.
- `WD04_QUANT_REAR`: 기존 market context/handoff 기준의 주중 후반부 current 산출과 필수 검증을 수행/확인한다. 실행 전에 model scope gate를 적용해 `S2_PIT_V01`, `I-STOCK-STRONG-RSI-V01`, AI research archive/excluded 모델을 기본 범위에서 제외한다. REVIEW 모델은 자동 제외하지 않고 known issue로 보고한다. Quant user/model snapshot 화면에 필요한 user report, user-facing current snapshot, history payload가 target asof인지 확인하고 stale이면 갱신하거나 `blocked`로 보고한다. 동시에 모델 성능 거버넌스 입력으로 `high_performance_models_to_expand`, `low_performance_models_to_reduce_or_archive`, `ai_models_to_refresh_or_downgrade`, `new_model_research_candidates`, `model_improvement_experiments`, `expected_return_improvement_hypothesis`를 요약 보고한다. research_full, 장기 백테스트, 정책 변경, 자동 publish 확정은 제외한다.
- `WD05_PORTFOLIO_ANALYSIS`: WD04 결과를 참고해 `D:\Quant\venv64\Scripts\python.exe D:\QuantAnalysis\portfolio_pipeline.py --asof <target_asof>`를 실행하고, QuantAnalysis 투자 포트폴리오 JSON/Markdown/DB current와 기본 GCS publish 결과를 확인한다. 동시에 selection history, top10/top3/rank4~10 후보 성과, top3와 rank4~10 격차, benchmark-relative 성과, weak/strong source model attribution, risk flags, 개선 검증 후보를 보고한다. `--skip-gcs-publish`는 붙이지 않고 `QUANTANALYSIS_SKIP_GCS_PUBLISH=1`이면 완료 처리하지 않는다. Quant 쪽 `redbot_user_report_*`, `user_model_snapshot_report.json`, `user_model_*_history.json` 검증은 WD04/WD06 책임이다. 장기 성과 재산출, 전체 히스토리 rebuild, 정책 변경, 자동 승인/배포는 제외한다.
- `WD06_PRE_GCS_PUBLISH`: WD04/WD05 결과를 기준으로 `pre_gcs_publish` 검증을 실행하고, 통과한 경우에만 `publish_public_current_to_gcs.py`로 public current를 GCS에 publish한다. 실패/보류 사유가 있으면 publish 성공으로 처리하지 않는다.
- `WE01_QUANT_WEEKEND_PIPELINE`: Quant 모델 스레드에서 주말 모델/AI 검증 통합 파이프라인을 한 번에 수행한다. 기본 timebox는 120분으로 잡는다. 실행 전에 model scope gate를 적용한다. retired/research_archive/excluded 모델은 명시 승인 없이 기본 실행하지 않고, REVIEW 모델과 stale A-core AI는 `downgrade_or_redesign_candidate`, `freshness_recovery_candidate`, `hold_for_more_samples` 같은 후보 의견으로만 보고한다. 주말 WE01은 모델 성능 거버넌스의 핵심 단계이며, 전략 모델 keep/improve/downgrade/retire 후보, AI operating_core/observation/refresh/archive 후보, 성과 우수 모델 발전 방향, 성과 저하 모델 정리 조건, 신규 모델 개발 후보와 기대 수익률 개선 가설을 반드시 보고한다. 모든 research_full/research_validation/AI 검증 결과는 target asof 기준으로 보고하고, 산출물 asof가 다르면 completed로 처리하지 않는다. 주말에는 QuantMarket, QuantMarketData, QuantAnalysis handoff와 market remote publish, `portfolio_pipeline.py`, public current GCS publish를 실행하지 않는다. 필요한 publish/포트폴리오 갱신은 주중 WD02/WD05/WD06 이슈로 넘긴다.
- WD02의 same-asof daily market-context / forecast / Quant handoff 갱신은 허용 범위다. 단, source stale 또는 실행 실패로 same-asof 생성이 안 되면 failed가 아니라 blocked 사유로 보고한다.

## 사용

시작:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\prompt_handoff_cycle.py start --cycle weekday --asof 2026-06-26 --run-id 20260626_weekday_prompt_01
```

상태 확인:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\prompt_handoff_cycle.py status --run-id 20260626_weekday_prompt_01
```

현재 stage 프롬프트 재생성:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\prompt_handoff_cycle.py render-prompt --run-id 20260626_weekday_prompt_01
```

스레드 보고 기록 및 다음 프롬프트 생성:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\prompt_handoff_cycle.py record-report --run-id 20260626_weekday_prompt_01 --status completed --report-file D:\Quant\_tmp\wd01_report.md --evidence "report path" --issue "none"
```

마감:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\prompt_handoff_cycle.py close --run-id 20260626_weekday_prompt_01
```

## 산출물

- `reports\prompt_handoff_runs\<run_id>\prompt_cycle_state.json`
- `reports\prompt_handoff_runs\<run_id>\<stage_id>\prompt.md`
- `reports\prompt_handoff_runs\<run_id>\<stage_id>\thread_report.md`
- `reports\prompt_handoff_runs\<run_id>\final_summary.md`
- `reports\harness_model_governance\<run_id>\model_governance_review.json`
- `reports\harness_model_governance\<run_id>\model_governance_review.md`
- `reports\harness_portfolio_governance\<run_id>\portfolio_governance_review.json`
- `reports\harness_portfolio_governance\<run_id>\portfolio_governance_review.md`

## 자동 Dispatch 구조

Thread target mapping:

- `config\harness\prompt_thread_targets.yaml`

동작 방식:

1. Harness가 현재 stage의 `prompt.md`를 생성한다.
2. Harness thread가 Codex app thread tool로 대상 thread에 prompt를 전송한다.
3. 대상 thread가 자기 workspace에서 작업하고 final report를 남긴다.
4. Harness thread가 대상 thread report를 읽어 `thread_report.md`로 저장한다.
5. Harness가 다음 stage prompt를 생성하고 다음 thread에 전송한다.

주의:

- 이 방식은 실행파일 직접 실행 runner가 아니다.
- Harness가 다른 repository 파일을 직접 수정하지 않는다.
- 대상 thread의 작업 결과는 해당 thread report를 근거로만 stage 완료 처리한다.
