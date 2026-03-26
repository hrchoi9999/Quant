# PROJECT_STATE_2026-02-04.md
(퀀트(레짐) 투자 시스템 개발 – S2 전략 / 시장게이트 + 종목 방어룰 + Google Sheet 업로드)

> 작성 기준: 2026-02-04 대화에서 실제로 실행/확인된 내용만 정리합니다.
> 목적: 내일/새 대화창에서 맥락 끊김 없이 바로 이어서 개발/실험 가능하도록 “결정사항 + 실행환경 + 파일/버전 + 결과 + 해야 할 일”을 한 문서로 고정합니다.

---

## 0. 오늘의 목표와 결과 요약

### 오늘 목표
1) **S2 백테스트를 안정적으로 실행**하고 결과 CSV를 산출  
2) **시장게이트 + 종목레벨 방어(P2-2)**를 전략에 반영  
3) **SMA 파라미터 / 시장게이트 파라미터**를 sweep으로 탐색  
4) 백테스트 결과를 **Google Sheets에 자동 업로드**(snapshot/trades/windows)  
5) 전략 확정은 전체기간 CAGR이 아니라 **최근 1/2/3/5년** 중심으로 판단

### 오늘 결과(완료/확정)
- S2 전략 백테스트 정상 실행 및 결과 CSV 생성 확인
- Google Sheets 업로드 정상 확인(**새 시트 3개 생성**)
- windows(perf_windows)에 **2년(2y)** 구간 성과가 포함되도록 코드 수정 반영
- **월간 리밸런싱(RBM)** 결과까지 산출(주간 RBW와 비교 분석 준비)

---

## 1. 오늘 확정된 전략(S2) 핵심 로직

### 1.1 전략 개요(S2)
- 후보군: `fundamentals_view = s2_fund_scores_monthly` 기반(월별 펀더멘털 점수)
- 리스크온 조건: **good_regimes = [4, 3]**
- 종목 필터: **종목 종가 > 종목 SMA(140)** 통과 종목만 편입
- 포트폴리오 크기: **Top 50**
- 비용 반영: `fee_bps=10`, `slippage_bps=10` (총 20bp 가정)

### 1.2 시장게이트(Market Gate)
- 목적: “상승장 진입 + 위험구간 회피”를 게이트로 제어
- 현재 proxy: **universe 기반 프록시**(ALL 또는 KOSPI 스코프)
- 시장 기준선: **market_sma_window = 60**
- 진입/이탈 멀티플: **entry=1.00, exit=1.00**
  - Entry: proxy_price > proxy_SMA * 1.00
  - Exit:  proxy_price < proxy_SMA * 1.00

> 결론(오늘): KOSPI 지수 적용은 “잊지 말아야 할 숙제”로 보류.  
> 지금 프록시로도 전략적 판단은 가능하나, 장기적으로는 정식 지수로 교체/검증 필요.

### 1.3 종목레벨 방어룰(P2-2)
- 확정: **exit_below_sma_weeks = 2**
- 규칙: 보유 종목이 SMA(140) 아래로 **연속 2회 리밸런싱 시점** 확인되면 매도
- 목적: 시장게이트로 인한 과도한 강제 현금화/재진입 반복을 완화

---

## 2. 성능 측정 방식(오늘 합의)

### 2.1 전체기간 CAGR만 보지 않는 이유
- 2013~2026(12년+)은 너무 길어 최근 성능 판단이 왜곡될 수 있음
- 따라서 **최근 1/2/3/5년 구간 CAGR/MDD**를 중심으로 전략 확정

### 2.2 perf_windows 정의
- equity 곡선을 기준으로 “최근 N년” 슬라이스 성과를 산출
- 오늘 기준: **1y / 2y / 3y / 5y**
  - 초기에 2y가 누락되어 있었고, 오늘 2y 포함하도록 수정함

---

## 3. 오늘 확정된 파라미터(최종값)

| 항목 | 파라미터 | 값 |
|---|---|---|
| 레짐 horizon | `--horizon` | `3m` |
| 전략 | `--strategy` | `S2` |
| Good regimes | `--good-regimes` | `4,3` |
| 리밸런싱 | `--rebalance` | `W`(주간) / `M`(월간도 테스트) |
| 보유 종목 수 | `--top-n` | `50` |
| 종목 SMA | `--sma-window` | `140` |
| 종목 방어룰 | `--exit-below-sma-weeks` | `2` |
| 시장게이트 | `--market-gate` | ON |
| 시장 SMA | `--market-sma-window` | `60` |
| 게이트 entry | `--market-sma-mult` | `1.00` |
| 게이트 exit | `--market-exit-mult` | `1.00` |
| 수수료 | `--fee-bps` | `10` |
| 슬리피지 | `--slippage-bps` | `10` |
| fundamentals view | `--fundamentals-view` | `s2_fund_scores_monthly` |
| 구글시트 업로드 | `--gsheet-enable` | ON |
| 시트 prefix | `--gsheet-prefix` | `S2` |

---

## 4. 실행 환경 / 경로 / 구조(오늘 확인)

### 4.1 환경
- Windows PowerShell
- venv: `(venv64)`
- Python: 3.10.11
  - Google API에서 FutureWarning: 3.10은 2026-10-04 이후 지원 중단 예정 → **장기 과제**로 Python 3.11+ 업그레이드 고려

### 4.2 주요 경로
- 프로젝트 루트: `D:\Quant`
- 백테스트: `D:\Quant\src\backtest\run_backtest_regime_s2_v3.py`
- 업로더: `D:\Quant\src\utils\gsheet_uploader.py`
- 결과 폴더: `D:\Quant\reports\backtest_regime\`

### 4.3 입력 데이터(실행 인자)
- `--regime-db ..\..\data\db\regime.db`
- `--price-db ..\..\data\db\price.db`
- `--fundamentals-db ..\..\data\db\fundamentals.db`
- `--universe-file ..\..\data\universe\universe_mix_top400_20260129_fundready.csv`

---

## 5. Google Sheets 업로드(오늘 완성)

### 5.1 업로드 대상(3개)
- **snapshot**: 마지막 시점 보유 종목/비중/상태 요약
- **trades**: 매매 내역
- **windows**: 최근 1/2/3/5년 성과 요약

### 5.2 시트 생성 규칙(새 시트)
- overwrite가 아니라 **항상 새 시트 생성**
- 규칙: `S2_YYYYMMDD_###_{snapshot|trades|windows}`
- 실제 확인 예:
  - `S2_20260204_001_snapshot`
  - `S2_20260204_001_trades`
  - `S2_20260204_001_windows`

### 5.3 credential / spreadsheet id (업로더에 내장)
- cred json: `d:\Quant\config\quant-485814-0df3dc750a8d.json`
- spreadsheet id: `1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs`

### 5.4 import 경로 이슈(오늘 겪은 것)
- `D:\Quant` 루트에서 `from utils...`가 실패했으나,
- `D:\Quant\src`에서 실행하면 import 성공 확인
- 해결 방향:
  - 백테스트 스크립트에서 `src`를 `sys.path`에 추가하는 부트스트랩 반영
  - `src/__init__.py`, `src/utils/__init__.py` 존재 확인

---

## 6. 오늘 발생한 주요 문제와 해결 로그

### 6.1 sweep 스크립트 문제
- `unicodeescape` 오류(Windows 경로 문자열 내 `\u` 해석)
- argparse `--version` 중복 등록 충돌
- backtest 인자 전달 불일치(horizon/rebalance/sma-window 등)
- 여러 번 수정 후 sweep 결과 CSV 산출까지 성공

### 6.2 backtest 버전 혼선
- 파일명 버전, 코드 상단 주석, help 출력, 실행 로그의 버전이 서로 달라 혼란 발생
- 합의: **실행 로그의 `[INFO] script_version=...`를 기준으로 단일화**
- 이후 008/010 계열에서 정리 진행

### 6.3 gsheet-enable 옵션 누락(009)
- `--gsheet-enable` 미인식(unrecognized arguments) 발생
- 010에서 argparse 복구

### 6.4 IndentationError(011 시도)
- `args = ap.parse_args()` 인덴트 깨짐으로 실행 실패
- 012에서 인덴트 정상화(단, 최종 운영 버전 정리 필요)

---

## 7. 실행 명령(정상 동작 확인용)

### 7.1 주간 리밸런싱 + gsheet 업로드(정상)
```powershell
python .\run_backtest_regime_s2_v3.py `
  --regime-db ..\..\data\db\regime.db `
  --price-db ..\..\data\db\price.db `
  --fundamentals-db ..\..\data\db\fundamentals.db `
  --fundamentals-view s2_fund_scores_monthly `
  --universe-file ..\..\data\universe\universe_mix_top400_20260129_fundready.csv `
  --ticker-col ticker `
  --horizon 3m `
  --strategy S2 `
  --good-regimes 4,3 `
  --rebalance W `
  --top-n 50 `
  --sma-window 140 `
  --exit-below-sma-weeks 2 `
  --market-gate `
  --market-sma-window 60 `
  --market-sma-mult 1.00 `
  --market-exit-mult 1.00 `
  --fee-bps 10 `
  --slippage-bps 10 `
  --outdir ..\..\reports\backtest_regime `
  --gsheet-enable `
  --gsheet-prefix S2

7.2 월간 리밸런싱

위 명령에서 --rebalance M으로 변경하여 실행(결과 파일 stamp에서 RBM 확인)


8. 산출 파일(오늘 확인된 종류)
8.1 공통 산출물

  regime_bt_summary_...csv
  regime_bt_equity_...csv
  regime_bt_holdings_...csv
  regime_bt_snapshot_...csv
  regime_bt_snapshot_...__trades.csv
  regime_bt_perf_windows_...csv ← 1/2/3/5년

8.2 stamp 차이

  주간: RBW
  월간: RBM


9. 주간(RBW) vs 월간(RBM) 비교(오늘 결론 정리)

  월간은 리밸런싱 횟수 감소로 거래 부담이 줄지만, 전체 성과가 자동으로 좋아지지는 않음
  최종 확정은 최근 1/2/3/5년 성과표를 기준으로 판단하기로 합의

10. 추가 개발해야 할 사항(단기 To-do)

  KOSPI 지수 데이터 확보 및 시장게이트 교체 적용(숙제로 보류)
  windows(perf_windows)에서 항상 1/2/3/5년 산출/업로드 보장(로그/검증 강화)
  trades 저장 범위 제한(요구사항)
  “최근 6년까지만 trades CSV 저장”
  기준(Entry 기준 vs Exit 기준) 명확화 필요
  리밸런싱 기본 정책 정리
  실행 인자 변경으로 충분하지만, 실수 방지 위해 기본값(M/W) 고정 여부 검토

11. 장기 과제(기술부채/고도화)

  Python 3.11+ 업그레이드(google api_core 지원 중단 대비)
  시장게이트 proxy → 정식 KOSPI 지수로 교체 및 검증
  시장게이트 파라미터(윈도우/멀티플) 자동 스윕 체계 고정
  snapshot 기반 “종목별 매수일/매도일/보유기간/수익률” 산출 및 구글시트 업로드(기존 S1 기능을 S2로 이식)
  버전관리 룰을 코드로 강제(상단/상수/로그/파일명 일치)

12. 내일 시작 체크리스트

  python .\run_backtest_regime_s2_v3.py --help로 script_version 확인
  실행 후 Google Sheets에 S2_YYYYMMDD_###_{snapshot|trades|windows} 3개 생성되는지 확인
  windows 탭에 2y 포함 확인
  “최근 6년 trades 제한” 구현 상태/정의(Entry vs Exit 기준) 확정

(끝)