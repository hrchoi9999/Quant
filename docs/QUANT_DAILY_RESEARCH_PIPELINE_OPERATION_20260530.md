# Quant Pipeline Operation Split

기준일: 2026-05-30

## 목적

주중 운영 속도를 줄이고, 무거운 연구/재학습/검증 작업은 주말에 모아 실행한다.

## 주중 파이프라인

실행 모드: `daily_light`

역할:
- 일별 데이터 수집 및 feature 갱신
- 전략모델 current 산출물 갱신
- 웹/public/admin current payload 갱신
- AI shadow 관찰용 current score 및 성과 tracker 갱신
- Trading Sign current 갱신
- 최종 contract 검증

전반부:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\quant_service\run_daily_quant_pipeline.py --asof YYYY-MM-DD --include-etf --data-refresh-only
```

전반부 완료 후:
- QuantMarket에서 같은 `asof` 기준 market context / forecast handoff 갱신
- Quant handoff 검증 조건: `production_ready=true`, `20d` 기준 `ALL/KOSPI/KOSDAQ` 존재

후반부:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\quant_service\run_daily_quant_pipeline.py --asof YYYY-MM-DD --include-etf --model-run-only --pipeline-mode daily_light
```

GCS publish:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\publish_public_current_to_gcs.py
```

## 주말 파이프라인

실행 모드: `research_full`

역할:
- 주중 파이프라인 산출물 갱신
- AI 재학습
- E-series mart / sleeve AI / ETF shadow portfolio full rebuild
- ETF 분배금/총수익률 보정 점검
- walk-forward / policy 안정성 검증
- 내부용 모델 검증 payload 및 historical 기록 생성

실행:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\quant_service\run_daily_quant_pipeline.py --asof YYYY-MM-DD --include-etf --model-run-only --pipeline-mode research_full
```

선택 연구 ablation 포함:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\quant_service\run_daily_quant_pipeline.py --asof YYYY-MM-DD --include-etf --model-run-only --pipeline-mode research_full --include-ai-research
```

## 검증 기준

주중:
- `validate_redbot_web_snapshots.py`
- `validate_redbot_history_payloads.py`
- `validate_admin_new_entry_tracker.py --mode quick`
- `validate_trading_sign_snapshots.py`
- `validate_daily_pipeline_contract.py`

주말:
- 주중 검증 전체
- `build_internal_model_validation_current.py`
- `internal_model_validation_current.json`
- `internal_model_validation_history.json`

표준 검증 suite:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_quant_validation_suite.py --asof YYYY-MM-DD --mode daily_contract
```

GCS publish 전 최소 검증:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_quant_validation_suite.py --asof YYYY-MM-DD --mode pre_gcs_publish
```

주말 research 검증:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_quant_validation_suite.py --asof YYYY-MM-DD --mode research_validation
```

## Timing Report

모든 실행은 아래에 timing report를 남긴다.

```text
D:\Quant\reports\pipeline_runs\daily_quant_pipeline_timing_<asof>_<timestamp>.json
```

주요 확인 필드:
- `status`
- `wall_elapsed_seconds`
- `group_wall_elapsed_seconds`
- `top_commands`
- `failure`
- `last_completed_command`

실패 시 `failure.resume_hint`를 기준으로 재개한다.

## DB Schema Manifest

SQLite DB 구조와 용량은 주말 또는 대규모 모델 변경 전후에 manifest로 남긴다.

기본 schema/size 점검:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_sqlite_db_schema_manifest.py --asof YYYY-MM-DD
```

주말 table row count 포함 점검:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_sqlite_db_schema_manifest.py --asof YYYY-MM-DD --include-row-counts
```

산출물:

```text
D:\Quant\reports\data_quality\db_schema_manifest\sqlite_db_schema_manifest_<asof>.json
D:\Quant\reports\data_quality\db_schema_manifest\sqlite_db_schema_manifest_current.json
```

## 운영 원칙

- 주중에는 모델 적용 정책을 임의 변경하지 않는다.
- AI/E-series policy 변경은 최소 1M 이상 shadow 관찰 후 주말 `research_full`에서 검토한다.
- QS/QM 코드 직접 수정은 하지 않는다. 필요한 변경은 작업요청서로 전달한다.
- 수익률 개선과 손실 위험 축소에 직접 기여하지 않는 연구 루틴은 주말 또는 연구 보관 대상으로 둔다.
