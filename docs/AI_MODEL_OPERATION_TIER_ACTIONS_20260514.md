# AI Model Operation Tier Actions

## 목적

모델과 AI 학습 실험이 늘어나면서 daily pipeline 부하가 증가하고 있다. 운영 우선순위는 `return_first`로 두고, 수익률 개선 또는 손실 회피에 직접 기여하지 않는 항목은 기본 운영 루틴에서 제외한다.

## 현 단계 조치

| 구분 | 항목 | 조치 |
| --- | --- | --- |
| D 제외 후보 | 수익률 개선 근거가 약한 AI variant | daily pipeline 기본 실행 대상에서 제외 |
| D 제외 후보 | 중복 shadow tracker | 개별 중복 실행보다 current payload 통합 관찰 우선 |
| D 제외 후보 | daily ablation | 수동 연구 실행으로 전환 |
| C 연구 보관 | 모델선택AI | 코드/리포트 유지, 기본 daily pipeline 미포함 |
| C 연구 보관 | QM_FULL류 feature 실험 | observation only, 수동 ablation |

## Pipeline 반영

`D:\Quant\src\quant_service\run_daily_quant_pipeline.py`에 `--include-ai-research` 옵션을 추가했다.

기본 daily pipeline에서는 아래 research 성격 작업을 제외한다.

- `D:\Quant\scripts\run_e_series_etf_selection_policy_ablation.py`

필요할 때는 다음처럼 명시적으로 실행한다.

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\quant_service\run_daily_quant_pipeline.py --asof YYYY-MM-DD --include-etf --include-ai-research
```

## 운영 등급 설정

운영 등급 정의 파일:

- `D:\Quant\config\ai_model_operational_tiers.json`

통합 AI 학습 모델 payload에도 `operation_tiers`와 모델별 `operation_tier`를 포함하도록 반영했다.

대상 payload:

- `D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json`

## 물리적 Archive 결과

연구 보관/제외 후보 산출물을 운영 경로에서 archive 경로로 이동했다.

| 항목 | 결과 |
| --- | ---: |
| archive root | `D:\Quant\archive\ai_model_research_20260514` |
| moved files | 343 |
| moved size | 약 84.99 MB |
| manifest JSON | `D:\Quant\archive\ai_model_research_20260514\archive_manifest.json` |
| manifest CSV | `D:\Quant\archive\ai_model_research_20260514\archive_manifest.csv` |

Archive 대상:

- `AI-MODEL-SELECTION-V01` 연구 산출물과 joblib 모델파일
- 주가수준평가AI feature ablation 산출물
- 하락위험예측AI label/QM/model-specific/recent-weight ablation 산출물
- 후보순위조정AI ablation/experiment 산출물
- 테마지속성AI label ablation 산출물
- E-series ETF label/selection policy ablation 산출물
- ETF 초기 role allocation / quality gate / weight template 실험 산출물
- 운영에 필요하지 않은 과거 ETF AI market context mart

운영에 필요한 source script는 이동하지 않았다. 일부 운영 스크립트가 연구 스크립트의 helper 함수를 import하고 있기 때문이다.

## 주의

이번 조치는 삭제가 아니다. 수익률 개선 가능성이 다시 확인되면 `manual_only` 또는 `--include-ai-research` 실행 결과를 근거로 운영 등급을 다시 올린다.

## 다음 검토 대상

실제 병목은 제외 후보보다 core AI 학습 쪽에 더 크다. 최근 timing 기준 주요 부하는 다음 항목이다.

| 항목 | 최근 소요 |
| --- | ---: |
| `build_ai_overlay_v01.py` | 약 474초 |
| `build_ai_live_shadow_tracker.py` | 약 143초 |
| `build_e_series_etf_mart_v2.py` | 약 136초 |
| `build_candidate_rank_delta_ai_v01.py` | 약 96초 |

따라서 다음 단계는 core AI의 재학습 주기 조정, incremental update, mart 캐싱을 검토하는 것이다.
