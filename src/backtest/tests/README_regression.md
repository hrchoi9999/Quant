# README_regression.md ver 2026-02-10_001

## 목적
- S2 리팩토링이 골든(레거시) 결과를 깨지 않았는지 자동 검증

## 준비
- 골든 fixture를 별도 폴더로 고정
  예) D:\Quant\src\backtest\tests\fixtures\golden\backtest_regime\
  - regime_bt_summary_{stamp}.csv
  - regime_bt_snapshot_{stamp}.csv

## 실행 예
python .\src\backtest\tests\regression_s2_golden.py `
  --stamp 3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206 `
  --golden-dir D:\Quant\src\backtest\tests\fixtures\golden\backtest_regime `
  --current-dir D:\Quant\src\backtest\outputs\backtest_regime

## 결과
- PASS: 종료코드 0
- FAIL: 종료코드 1 + diff 파일 생성
  - src/backtest/tests/_artifacts/diff_summary_{stamp}.csv
  - src/backtest/tests/_artifacts/diff_snapshot_{stamp}.csv
