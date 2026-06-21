# QS/QM 코드 품질 관리 도구 도입 작업요청서

작성일: 2026-05-30  
작성 주체: Quant thread  
대상 thread: QuantService(QS), QuantMarket(QM)

## 1. 요청 배경

Quant 프로젝트에서 소프트웨어 개발환경 안정화를 위해 코드 품질 관리 도구를 단계적으로 도입했습니다.

현재 Quant에는 아래의 안전한 1차 도입만 반영했습니다.

- `ruff`
- `pytest`
- 최소 `pyproject.toml`
- 최근 수정 핵심 파일 대상 lint 확인
- 자동수정 금지
- 전체 repo 강제 lint 미적용
- pre-commit 미도입

QS와 QM도 각각 운영 파이프라인과 웹/API/handoff 산출물을 관리하므로 동일한 수준의 최소 품질 관리 체계를 도입하는 것이 필요합니다.

## 2. 권한 및 작업 원칙

중요 원칙:

- Quant thread는 QS/QM 코드를 직접 수정하지 않습니다.
- QS thread는 QS 코드와 배포/웹/API 영역만 직접 수정합니다.
- QM thread는 QM 코드와 market context / forecast / handoff 영역만 직접 수정합니다.
- 공통 정책은 공유하되, 실제 도입과 커밋은 각 thread에서 수행합니다.

이 권한 구조는 계속 유지합니다.

## 3. 공통 도입 정책

초기 도입은 반드시 낮은 리스크 방식으로 진행합니다.

### 3.1 도입 도구

각 프로젝트 venv에 아래 도구를 설치합니다.

```powershell
python -m pip install ruff pytest
```

프로젝트별 Python 실행 경로는 각 thread의 기존 venv 기준을 사용합니다.

### 3.2 pyproject.toml 최소 설정

각 프로젝트 root에 `pyproject.toml`이 없다면 아래 수준으로 시작합니다.

```toml
[tool.ruff]
target-version = "py310"
line-length = 120
exclude = [
  ".git",
  ".venv",
  "venv",
  "venv64",
  "archive",
  "data",
  "reports",
  "service_platform/web/public_data/current",
  "service_platform/web/admin_data/current",
]

[tool.ruff.lint]
select = ["E", "F", "I"]
ignore = ["E501"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-q"
```

각 프로젝트 구조에 맞게 `exclude`는 조정해도 됩니다.

### 3.3 초기 운영 원칙

- 전체 repo lint를 강제하지 않습니다.
- 자동수정(`ruff --fix`)은 사용하지 않습니다.
- 최근 수정한 핵심 파일 3~5개만 우선 검사합니다.
- 실패가 나와도 운영 배포를 막는 gate로 쓰지 않습니다.
- pre-commit은 아직 도입하지 않습니다.
- pytest는 설치만 하고, 테스트 작성은 다음 단계로 둡니다.

## 4. QS thread 요청사항

QS는 redbot.co.kr 웹/API/payload 표시 계층을 담당하므로 아래 파일군부터 품질 관리를 시작해 주세요.

우선 대상:

- 웹 payload parser
- admin page data mapping
- API response schema 관련 파일
- GCS current payload fetch/parse 로직
- model snapshot 표시 로직

초기 실행 예시:

```powershell
<QS_PYTHON> -m ruff check <최근 수정한 QS 핵심 파일 3~5개>
<QS_PYTHON> -m py_compile <최근 수정한 QS 핵심 파일 3~5개>
```

검증 포인트:

- import 오류 없음
- 미정의 변수 없음
- payload field name typo 없음
- admin/public 데이터 표시 로직에서 null을 0으로 바꾸지 않음
- 기존 배포 방식에 영향 없음

## 5. QM thread 요청사항

QM은 market context / forecast / Quant handoff를 담당하므로 아래 파일군부터 품질 관리를 시작해 주세요.

우선 대상:

- market context mart 생성 스크립트
- market forecast calibration / validation 스크립트
- Quant handoff manifest 생성 스크립트
- `validate_quant_model_handoff.py`
- handoff current payload 생성/검증 로직

초기 실행 예시:

```powershell
<QM_PYTHON> -m ruff check <최근 수정한 QM 핵심 파일 3~5개>
<QM_PYTHON> -m py_compile <최근 수정한 QM 핵심 파일 3~5개>
```

검증 포인트:

- manifest 필드명 typo 없음
- `production_ready`, `asof_date`, `latest_asof_date`, `expected_asof_date` 일관성 유지
- 20d forecast scope `ALL/KOSPI/KOSDAQ` 검증 로직 유지
- null/coverage flag 처리 원칙 유지
- Quant handoff contract 훼손 없음

## 6. 다음 단계

각 thread에서 초기 도입 후 아래 내용을 회신해 주세요.

- 설치한 도구 버전
- 추가/수정한 `pyproject.toml` 경로
- lint 검사 대상 파일
- lint 결과
- py_compile 결과
- 자동수정 여부: 반드시 `없음`으로 유지
- 운영 배포 영향 여부

## 7. 향후 확장 원칙

1차 도입이 안정화된 뒤에만 다음을 검토합니다.

- 신규 유틸/검증 스크립트에 한해 `ruff --fix` 제한 허용
- 핵심 parser/validator 함수 단위 pytest 추가
- pipeline command build smoke test 추가
- 주말 research pipeline 이후 lint 리포트 생성
- pre-commit 도입 여부 검토

현재 단계에서는 pre-commit과 전체 repo 강제 lint는 도입하지 않습니다.
