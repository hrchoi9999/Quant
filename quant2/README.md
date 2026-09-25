# Quant 2.x 전용 작업영역

이 폴더는 Quant 2.0 이후에 새로 개발되는 코드, 실행기, 테스트, 문서와 산출물을 1.0 작업영역과 분리하기 위한 전용 루트다.

## 구조

- `src/quant2`: Quant 2.x 핵심 코드
- `scripts`: Quant 2.x 실행기
- `tests/quant2`: Quant 2.x 테스트
- `docs/Quant2_0`: Master 문서
- `docs/Market Regime Model`: 설계·결과·운영 문서
- `data/quant2`: Quant 2.x 전용 입력 snapshot과 재현 데이터
- `reports/quant2_0`: Quant 2.0 산출물
- `_tmp`: 검증용 임시 산출물

## 경계

- `D:\Quant`의 Quant 1.0 코드·데이터·문서는 이동하거나 수정하지 않는다.
- 공통 1.0 데이터와 S/T 전략 코드는 `D:\Quant`에서 읽어 사용한다.
- 앞으로 Quant 2.x 신규 파일은 반드시 `D:\Quant\quant2` 아래에 생성한다.
- 기존 1.1 참조를 보존하기 위해 `D:\Quant\src\quant2`, `tests\quant2`, `data\quant2`, `reports\quant2_0`에는 호환 junction만 유지한다.
- Python은 `D:\Quant\venv64\Scripts\python.exe`를 계속 사용한다.

