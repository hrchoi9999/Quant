# TODO_REFACTOR_20260212_V1

## 1. 실행 경로 단일화

-   run_backtest_v5.py에서 S2-refactor 호출 방식 점검
-   subprocess 호출 여부 제거
-   import 후 main(args) 호출 방식으로 변경

## 2. import 전수 점검

-   from core. → from src.backtest.core.
-   from outputs. → from src.backtest.outputs.
-   from strategies. → from src.backtest.strategies.
-   sys.path 조작 제거

## 3. **init**.py 점검

-   모든 패키지 폴더에 존재 여부 확인

## 4. dual-mode import 제거

-   단일 실행 방식 확정 후 제거

## 5. 최종 검증

-   모듈 import 전체 성공 확인
-   백테스트 정상 실행 확인
-   snapshot/holdings/trades CSV 생성 확인
