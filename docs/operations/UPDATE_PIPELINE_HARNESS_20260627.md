# Update Pipeline Harness

기준일: 2026-06-27

## 목적

Quant, QuantMarket, QuantAnalysis 쓰레드가 주중 업데이트를 정해진 순서로 진행하고, 주말 업데이트는 Quant 모델 스레드의 단일 모델/AI 검증 요청으로 진행하도록 상태와 handoff 지시문을 남긴다.

범위 제외:
- LangChain / LangGraph / LLM Agent
- 자동 매매
- 자동 배포
- QS/QM 코드 직접 수정

## 파일

- CLI: `D:\Quant\scripts\update_pipeline_harness.py`
- 상태: `D:\Quant\reports\update_pipeline_harness\current_state.json`
- handoff 지시문: `D:\Quant\reports\update_pipeline_harness\handoffs\*.md`

## 주중 workflow

1. Quant: `data-refresh-only`
2. QuantMarket: 같은 `asof`의 market context / forecast handoff 갱신
3. Quant: `daily_light` model-run 및 `daily_contract` 검증
4. QuantAnalysis: timing / validation / model change 리뷰
5. Quant: `pre_gcs_publish` 검증 후 publish gate 판단

## 주말 workflow

1. Quant: 주말 모델/AI 검증 통합 파이프라인 실행 및 결과 정리

주말에는 QuantMarket, QuantMarketData, QuantAnalysis로 별도 handoff를 보내지 않는다.

## 사용 예

주중 최종 운영 batch 시작:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\update_pipeline_harness.py init --workflow weekday --asof 2026-06-26 --batch-type final_operational_publish
```

주말 research 시작:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\update_pipeline_harness.py init --workflow weekend --asof 2026-06-26 --batch-type research_full
```

현재 상태 확인:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\update_pipeline_harness.py status
```

현재 step 완료 및 다음 handoff 생성:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\update_pipeline_harness.py complete-step --evidence "timing report path" --note "특이사항 없음" --render-next
```

현재 step blocked 처리:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\update_pipeline_harness.py block-step --note "QM handoff manifest production_ready=false"
```

## 운영 원칙

- Harness는 파이프라인을 자동 실행하지 않는다. 실행 순서, 상태, 다음 thread 지시문만 관리한다.
- publish 명령은 지시문에 표시되지만, 실제 실행은 검증 통과 후 운영자가 결정한다.
- 주중에는 정책 변경을 적용하지 않는다.
- AI/E-series policy 변경은 주말 `research_full`에서 후보로만 검토한다.
- 실패 시 각 step의 evidence/notes에 report 경로와 resume hint를 남긴다.
