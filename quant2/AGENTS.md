# Quant 2.x Workspace Instructions

- 답변은 한국어 존댓말로 핵심만 간단히 작성한다.
- 연구 작업 종료 시 이전 결론에서 달라진 점, 아직 확인하지 못한 점, 다음 작업을 쉬운 말로 짧게 정리한다. 변화가 없으면 없다고 명시한다.
- 진행·종료 보고에는 대분류 단계, 현재 세분류 단계, 해당 단계와 전체 완성률, 완료 범위와 다음 작업을 표시한다. 기준은 `docs/Quant2_5/QUANT_2_5_PROGRESS.md`의 고정 완료 조건이며, 실행 횟수·파일 수·작업 요청만으로 진척률을 올리지 않는다. 완성률은 검증·운영 인계·서비스 전환을 포함한 납품 완료 조건의 비율이며 투자 성과 보장이나 소요시간 예측이 아니다.
- Quant 2.x 신규 코드, 스크립트, 테스트, 문서, 데이터 snapshot과 보고서는 모두 `D:\Quant\quant2` 아래에 생성한다.
- Quant 1.0 파일은 `D:\Quant`의 기존 위치에 그대로 보존하며 직접 이동하거나 구조 변경하지 않는다.
- 1.0 공통 데이터와 S/T 전략 코드는 읽기 전용 의존성으로 사용한다.
- 핵심 로직은 `src\quant2`, 실행 진입점은 `scripts`, 테스트는 `tests\quant2`, 문서는 `docs`, 산출물은 `reports\quant2_0`에 둔다.
- 새 실행기가 다른 실행기 파일을 직접 import하지 않도록 하고 공통 로직은 `src\quant2`로 이동한다.
- 호환 junction인 `D:\Quant\src\quant2`, `D:\Quant\tests\quant2`, `D:\Quant\data\quant2`, `D:\Quant\reports\quant2_0`를 실제 소스 저장 위치로 사용하지 않는다.
- 기존 `D:\Quant\venv64`를 사용하고 별도 가상환경을 만들지 않는다.
- 변경 후 `py_compile` 또는 `compileall`, `ruff`, `pytest`를 실행한다.
- 운영, public/GCS, QuantMarket, QuantService 변경은 별도 승인 없이 수행하지 않는다.
