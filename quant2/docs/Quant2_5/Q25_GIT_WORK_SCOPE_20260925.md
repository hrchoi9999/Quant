# Quant 2.5 Git 작업 범위 — 2026-09-25

## 이번 완료 범위

- 사용자 지시: 이 총괄 작업의 Git 정리도 수행한다.
- 저장소: `D:\Quant`, `hrchoi9999/Quant`, 로컬 `main`.
- 소스 커밋: `a5758412ea22d88f09de695c2e9a2f2f75e924e1`.
- 모의투자 재구성·원본 장부에서 독립한 입력·서비스 exporter와 직접/간접 Python 의존 파일 90개를 명시적으로 선별했다. 기존에 추적되지 않던 의존 파일을 포함한 최초 기준이며, 90개 각각이 오늘 새로 개발되었다는 뜻은 아니다.
- 기존 승인 소스 4개 해시는 [원본 장부 독립화 검수](../../reports/quant2_0/q25_ledger_retirement_20260925/MASTER_REVIEW.json)와 일치한다. 소스 내용을 변경하지 않았다.
- 미추적 파일을 숨기던 로컬 `status.showUntrackedFiles=no`를 `normal`로 바꿨다.
- 루트 `.gitignore`에는 실제 소스가 아닌 `src/quant2`, `tests/quant2`, `data/quant2`, `reports/quant2_0` 호환 junction 경로만 추가했다. 소스는 `quant2/`의 실제 경로로 추적하며, 나머지 미추적 제품 코드를 숨기지 않는다.

## 검증과 재현 경계

- Git index에서 추출한 격리 사본으로 원본 입력/재구성 13개 검사를 통과했다.
- 기존 manifest `72f00e83ec8a97b4fa30343acb4b1701b085b697543561c7d78aff6fa59607e3`와 일치하는 로컬 자료를 별도로 복사해 exporter 12개 검사를 통과했다. 해당 실제 자료는 Git에 넣지 않았다.
- 변경 주대상과 신규 공통 의존 파일의 Ruff 및 선별 소스 구문검사 통과. 기존 소스의 끝 빈 줄 4건은 해시 보존을 위해 그대로 두었으며, 그 경고를 제외한 staged whitespace 검사는 통과했다.
- 새 Windows 체크아웃은 기존 작업영역 규약대로 `src/quant2`에서 `quant2/src/quant2`로 향하는 junction을 설정해야 한다. 검증 사본에서도 이 구조로 시험했다. 원천 DB·보고서·모델 산출물은 별도 보존 자료가 필요하다.
- exporter 시험은 원본 검수 자료를 `quant2/reports/quant2_0/q25_paper_reconstruction_20260924/run_02_os`에 복원하고, pytest의 새 `--basetemp`를 `quant2/reports/` 하위에 지정한다. 소스만으로 실제 운영 자료가 생성되는 것은 아니다.
- 이 결과는 해당 모의투자 기능의 한정 검수이며 모든 전략·운영 실행의 승인이나 전체 저장소 테스트 통과를 의미하지 않는다.

## 남은 변경과 보존

- 기존 1.0 전략·수집·하네스 변경, 문서 이동으로 보이는 삭제 221개 및 다른 미추적 연구 코드는 이번 커밋에 섞지 않았다. 원래 위치와 내용을 유지했다.
- 루트의 기존 `AGENTS.md` 변경도 전체 누적 차이를 이번 작업에 묶지 않고 보존했다.
- 실제 남은 dirty 수와 전체 파일별 목록은 [로컬 Git 마감 기록](../../reports/quant2_0/git_closeout_20260925/selection.json)에 기록한다. 저장소 전체 clean으로 보고하지 않는다.
- 로컬 커밋만 수행하며 push·배포·GCS 게시·DB/모델 재산출은 이번 범위에 없다.
- Q25 규칙·기업행위 검토는 보류 목록에 유지한다. 주중·주말 Harness는 사용자가 직접 지시할 때만 시작한다.
