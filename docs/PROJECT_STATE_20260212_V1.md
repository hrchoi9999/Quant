# PROJECT_STATE_20260212_V1

## 1. 현재 리팩토링 배경

-   ticker 정규화 모듈(core/tickers.py) 도입
-   snapshot CSV에서 ticker 숫자 문제 해결 시도
-   import 경로 혼재 발생 (core.*, outputs.*, 상대/절대 import 혼재)

## 2. 지금까지 수행한 작업

-   fill_bundle.py import 구조 수정
-   run_backtest_s2_refactor_v1.py bootstrap 적용
-   core/data.py, core/engine.py 상대 import 전환
-   dual-mode import 임시 적용
-   패키지 실행 방식 점검

## 3. 현재 문제 상태

-   패키지 실행과 레거시 실행 혼재
-   VSCode Pylance 정적 분석 경고 다수 발생
-   실행 진입점 단일화 필요

## 4. 핵심 원인

-   실행 컨텍스트가 일관되지 않음
-   import 규칙이 통일되지 않음
-   subprocess/파일 직접 실행 가능성 존재

## 5. 정리 방향

-   실행 방식 단일화 (python -m 방식 고정)
-   import 전면 패키지 기준 통일
-   dual-mode import 제거 예정
