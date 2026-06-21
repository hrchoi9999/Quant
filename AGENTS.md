# Quant Master Agent Instructions

## 기본 원칙

- 답변은 핵심만 간단히 한다.
- 작업 루트는 `D:\Quant`로 고정한다.
- Quant thread는 Quant 모델, 파이프라인, 데이터, 리포트, 운영 문서를 담당한다.
- QuantService(QS), QuantMarket(QM) 코드는 직접 수정하지 않고 작업요청서로 전달한다.
- 사용자가 명시적으로 중단하지 않으면 확인, 수정, 검증까지 이어서 처리한다.

## 시작 시 확인 순서

1. `git status --short`
2. 최근 변경 파일과 diff
3. 최신 `docs/PROJECT_STATE_*.md`
4. 최신 운영/요청 문서
5. 최신 pipeline timing report와 validation report

## 개발 원칙

- 운영 기준일, 데이터 기준일, 검증 결과를 명확히 구분한다.
- generated payload, DB, report 산출물과 소스 코드 변경을 분리해서 판단한다.
- public publish는 검증 통과 후에만 허용한다.
- 주중에는 정책 변경을 피하고, AI/E-series policy 변경은 주말 `research_full`에서 검토한다.
- 변경 후 가능한 범위에서 `py_compile`, `ruff`, validation suite를 실행한다.

## Sub Agent 운영

- sub agent는 Master 지시가 있을 때만 만든다.
- sub agent별 담당 범위와 산출물을 명확히 지정한다.
- sub agent는 직접 운영 판단을 확정하지 않고 결과를 Master에게 보고한다.
- Master는 보고를 취합해 최종 판단, 수정, 커밋/배포 여부를 결정한다.

## 권장 Sub Agent 역할

- Pipeline QA: pipeline timing, validation, 산출물 freshness 점검
- Git Hygiene: 커밋 대상과 제외 대상 분리
- Model Research: AI/E-series/S-series 성과와 정책 변경 후보 분석
- Data Quality: DB, universe, price, ETF coverage, schema manifest 점검
- Cross Thread Request: QS/QM 대상 작업요청서 작성

## 현재 기준

- Python venv: `D:\Quant\venv64`
- 코드 품질 도구: `ruff`, `pytest`
- 최신 운영 원칙 문서:
  - `docs\QUANT_DAILY_RESEARCH_PIPELINE_OPERATION_20260530.md`
  - `docs\GIT_AND_BACKUP_OPERATION_POLICY.md`
  - `docs\BATCH_OPERATION_POLICY_20260423.md`
