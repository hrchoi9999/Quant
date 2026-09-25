# 1.0 AI 폐지 실행 계약 — 2026-09-25

근거: 사용자 전면 폐지/의존성 선행 점검 지시 후 “다음 작업 진행해”. 선행 점검은 QUANT1_AI_RETIREMENT_DEPENDENCY_REVIEW_20260925.md. 새 수집·학습·전략 재계산이 아니라 기존 AI 실행/소비 종료 및 비AI 호환 수정이다.

후속 사용자 확인: “검증이 완료되면 배포까지 진행하는 거지?”에 따라 검증된 동일 범위의 서비스 배포, 고정 전환 자료 게시, 실제 운영 화면 확인까지 마무리한다. 미검수 후보 전환은 포함하지 않는다. 기존 기능 보존은 검증된 운영 이미지 기준으로 대조하고, 신규 AI 폐지 변경과 호환 보완을 개발본에도 통합·검증한다.

## 분장과 공통 계약

- Master: `quant2/config/quant1_ai_retirement.json`, `quant2/src/quant2/operations/ai_retirement.py` 공통 정책/가드, quant2 storage 게시 경로 차단, 총괄 검수. OS는 해당 파일을 직접 수정하지 않는다.
- Quant OS: 기존 Quant pipeline, scripts, src/models 및 quant_service 실행/생성/검증/게시·T 의존 C/I 연결 수정과 격리 검사. 공유 원천/과거 자료 보존, canonical DB 재계산 없음.
- QA: 자체 포트폴리오 모델목록·기여/참고 후보에서 폐지 T 제거, 입력 없는 상태의 비AI 유지와 새 payload 계약 검증. 값 재계산 없이 고정 자료에서 전환 후보 생성·격리 검수. 원격 게시 전 후보 보고.
- QS: 자체 reader/API/메뉴와 새 payload 검증. 기존 비AI 포트폴리오 및 Q25 보존, AI/T 현재 소비 차단. 고정 자료로 호환 검수 및 release 준비. 배포 전 exact candidate 보고.
- Harness: 새 cycle 없이 차기 실행 계획/게이트가 폐지 모델을 재활성화하지 않도록 범위·검증 연결. 과거 run·승인 기록은 불변.

신규 포트폴리오 최상위 `ai_model_lifecycle`는 아래 객체를 정확히 사용한다. 기존 `ai_output_scope`와 외부 생성형 설명의 `ai_deferred`는 다른 계약이므로 그대로 보존한다.

모든 모델 ID 목록은 순서 무관이며 정확한 집합·중복 금지로 검증한다. 아래 JSON의 표시 순서는 필수 직렬화 순서가 아니다.

```json
{"schema_version":"quant1_ai_retirement_v1","status":"retired","retired_model_ids":["T-STOCK-V01","T-ETF-V01"],"current_ai_outputs_allowed":false,"historical_records_preserved":true}
```

신규 포트폴리오 `stock_strategy.model_operation_policy`: active는 S2/S3/S3_CORE2/S3_ACCEL_V01/S4/S5, retired는 기존 S2_PIT_V01/I-STOCK-STRONG-RSI-V01/S6에 T-STOCK-V01/T-ETF-V01 추가, reference_only는 빈 목록. 순서 무관/중복 금지. 실제 S6 폐지 계약과 과거 기록은 보존한다. 신규 계약은 임의 상태/누락 필드를 허용하지 않으며, old payload의 T/AI는 현재 노출·의사결정에 다시 사용하지 않는다. old/new reader 전환의 안전한 호환 방법은 QS가 명시·검증한다.

검수 조건: ①공통 계약·경로 차단 ②QA/QS 비AI 입력/결과 보존 및 AI 부재 호환 ③OS/Harness 직접 실행·게시·재활성화 차단 ④정확한 변경 범위 총괄 검수·반영 근거. 단계② 폐지 실행은 0/4부터 시작하며 요청 전송만으로 완료율을 올리지 않는다. 운영 배포/게시 범위와 실제 완료는 개발 검증과 구분한다.

대상 외: QuantMarket 소유 시장예측 자체, 외부 생성형 설명 모델, 비AI ETF 분류/분배금/공통 특성, Q25 기존 회계/모의투자. 별도 SAI-S1/SAI-E1/SAI-G1 연구와 strategy_research_observation 화면은 이번 효용 분석 대상의 legacy AI 모델이 아니므로 보존하며 새 실행을 뜻하지 않는다. 모델 DB와 과거 자료를 삭제하지 않는다. 규칙·기업행위는 계속 보류. 새 일상 Harness cycle은 사용자 직접 명령에만 따른다. 후속 주말 폐지 receipt의 retired/historical_read_only 상태를 유지하며 이 계약을 정기 주말 Harness 재활성화 근거로 사용하지 않는다.

전환 순서: 기존/신규 payload를 모두 검증하는 QS 최소 변경 후보의 무트래픽 검수 → 총괄 exact candidate 검수 → QS 호환 reader 반영·실제 검증 → QA의 고정 release 게시(CAS 직전 원격 generation/bytes 확인) → 실서비스 대조. QA의 일회성 exact release gate와 향후 비AI cycle에 사용할 영구 소비 호환 gate는 분리한다. 후자에 이번 release SHA/이전 generation을 고정하지 않으며, Harness WD05는 활성화된 manifest path/SHA와 기존 각 cycle 입력 pin을 전달한다. 이 순서 자체로 새 수집 cycle을 시작하지 않는다.

## Git 보존 범위와 재현 조건

후속 사용자 지시 “git 작업도 진행해”에 따라 이번 폐지 변경과 실행에 필요한 직접 선행 의존성을 함께 보존한다. HEAD에 없던 exact47 공개 게시 차단과 비공개 게시 검증은 선행 의존성으로 구분한다. 무관한 기존 연구·폴더 이동·정기 cycle 개선은 이 커밋에 포함하지 않으며, 전체 dirty 트리를 운영 이미지와 동일하다고 주장하지 않는다. 원본 작업 트리와 분리한 index/checkout에서 실제 커밋 구성을 검수한다.

Quant의 실제 소스는 `quant2/src/quant2`이며 기존 Windows 환경은 `src/quant2` junction을 사용한다. 새 checkout에서 `src.quant2` 경로로 실행할 때는 동일한 junction을 해당 checkout 내부의 실제 소스에 연결해야 한다. 검수 사본도 원본 `D:\Quant`의 junction을 공유하지 않고 사본 내부에 연결한다.

DB·생성 payload·운영 승인 receipt 및 `reports`는 Git 보존 대상이 아니다. 별도 백업에서 기존 운영 승인 파일을 정확한 절대경로·SHA로 복구해야 QA의 고정 승인 gate와 차기 승인 cycle을 실행할 수 있다. Git checkout만으로 새 수집·학습·게시 권한이 생기지 않는다. Git 처리 증거는 로컬 `quant2/reports/quant2_0/ai_retirement_git_20260925`에 보존한다.
