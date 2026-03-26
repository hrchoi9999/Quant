# PROJECT_CONVENTIONS_20260212

## A. 실행 방식(Entrypoint) 단일화

1)  작업 디렉터리는 항상 D:`\Quant  `{=tex}
2)  백테스트 실행은 항상 모듈 실행(python -m)만 허용
    -   ✅ python -m src.backtest.run_backtest_v5 ...
    -   ❌ cd src`\backtest `{=tex}후 python run_backtest\_\*.py\
3)  코드 내부에서 subprocess로 파이썬 파일 직접 실행 금지
    -   ❌ subprocess.run(\["python", "run_backtest_s2_refactor_v1.py",
        ...\])
    -   ✅ import 후 main(args) 호출 방식 사용

## B. import 규칙 단일화

1)  src/backtest 내부 코드는 패키지 기준 import만 사용
    -   권장: from src.backtest.core.tickers import normalize_ticker\
2)  다음 패턴은 전면 금지
    -   ❌ from core.xxx import ...
    -   ❌ from outputs.xxx import ...
    -   ❌ sys.path.insert(...)\
3)  try/except ImportError로 dual-mode import는 임시 대응 외 금지

## C. 패키지 구조 강제

1)  다음 폴더에 **init**.py 존재 보장
    -   src/
    -   src/backtest/
    -   src/backtest/core/
    -   src/backtest/outputs/
    -   src/backtest/strategies/
2)  VSCode workspace root는 D:`\Quant로 `{=tex}고정

## D. 수정 시 준수 사항

1)  모든 파일에 버전 헤더 유지\
2)  변경 순서: 문서 수정 → 코드 수정 → 검증 커맨드 기록\
3)  새 대화창 시작 시 반드시 아래 파일 확인
    -   PROJECT_STATE
    -   PROJECT_CONVENTIONS
    -   TODO_REFACTOR

## E. 검증 커맨드 표준

1)  python -m py_compile ...
2)  python -c "import src.backtest...."
3)  python -m src.backtest.run_backtest_v5 ...
