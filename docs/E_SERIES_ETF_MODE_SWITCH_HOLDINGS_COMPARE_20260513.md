# E-Series ETF Mode Switch Holdings Compare

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 비교 대상:
  - base: `hybrid_b50_ai50_top3_role`
  - switch: `mode_switch_stress_tail_asset`
- 스크립트: `D:\Quant\scripts\build_e_series_etf_mode_switch_holdings_compare.py`

## Current Context

- current market mode: `risk_off`
- current stress flag: `true`
- mode switch best policy: `mode_switch_stress_tail_asset`
- stress days in walk-forward: 13 / 26
- risk-off days in walk-forward: 15 / 26

## Holdings Change Summary

| 항목 | 값 |
|---|---:|
| base holding count | 18 |
| switch holding count | 18 |
| unchanged | 9 |
| added by switch | 9 |
| removed by switch | 9 |
| one-way turnover | 30.0% |

## Added By Switch

| ticker | name | role | asset bucket | weight |
|---|---|---|---|---:|
| 357870 | TIGER CD금리투자KIS(합성) | CASH_LIKE | CASH_RATE | 8.3333% |
| 469830 | SOL 초단기채권액티브 | CASH_LIKE | BOND_SHORT | 8.3333% |
| 360200 | ACE 미국S&P500 | CORE_BETA | EQUITY_US | 1.6667% |
| 379800 | KODEX 미국S&P500 | CORE_BETA | EQUITY_US | 1.6667% |
| 381170 | TIGER 미국테크TOP10 INDXX | CORE_BETA | EQUITY_US | 1.6667% |
| 390390 | KODEX 미국반도체 | SECTOR_THEME | EQUITY_US | 1.6667% |
| 465580 | ACE 미국빅테크TOP7 Plus | SECTOR_THEME | EQUITY_US | 1.6667% |
| 497570 | TIGER 미국필라델피아AI반도체나스닥 | SECTOR_THEME | EQUITY_US | 1.6667% |
| 457480 | ACE 테슬라밸류체인액티브 | STYLE_FACTOR | EQUITY_US | 3.3333% |

## Removed By Switch

| ticker | name | role | asset bucket | weight |
|---|---|---|---|---:|
| 272580 | TIGER 단기채권액티브 | CASH_LIKE | BOND_SHORT | 8.3333% |
| 423160 | KODEX KOFR금리액티브(합성) | CASH_LIKE | CASH_RATE | 8.3333% |
| 139260 | TIGER 200 IT | CORE_BETA | EQUITY_KR | 1.6667% |
| 237350 | KODEX 코스피100 | CORE_BETA | EQUITY_KR | 1.6667% |
| 294400 | KIWOOM 200TR | CORE_BETA | EQUITY_KR | 1.6667% |
| 243880 | TIGER 200IT레버리지 | SECTOR_THEME | EQUITY_KR | 1.6667% |
| 367760 | RISE 네트워크인프라 | SECTOR_THEME | EQUITY_KR | 1.6667% |
| 381180 | TIGER 미국필라델피아반도체나스닥 | SECTOR_THEME | EQUITY_US | 1.6667% |
| 494220 | UNICORN SK하이닉스밸류체인액티브 | STYLE_FACTOR | EQUITY_KR | 3.3333% |

## Interpretation

현재 switch는 단순히 현금/채권으로만 이동하는 방어가 아니다.
stress 구간에서 일부 국내 주식형/테마형 노출을 줄이고, 같은 equity sleeve 안에서도 미국 S&P500, 미국 테크, 미국 반도체 등 quality guard가 더 높게 평가한 ETF로 교체한다.

즉 현재 전환의 성격은 다음과 같다.

- CASH_LIKE: 단기채/금리형 후보 교체
- CORE_BETA: 국내 beta 일부를 미국 S&P500/테크 beta로 전환
- SECTOR_THEME: 국내 IT/인프라 일부를 미국 반도체/빅테크로 전환
- STYLE_FACTOR: 국내 반도체 밸류체인 일부를 미국 테슬라 밸류체인으로 전환
- DEFENSIVE/INCOME: 변화 없음

## Operating View

one-way turnover 30%는 작지는 않지만 stress 전환으로는 과도한 수준은 아니다.
다만 실거래 반영 전에는 거래비용/회전율 차감 backtest가 필요하다.
