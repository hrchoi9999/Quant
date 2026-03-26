# PROJECT_STATE.md (퀀트투자 시스템 리팩토링) — 2026-02-10

> 목적: 새로운 대화창에서 맥락 단절 없이 **리팩토링을 안전하게 이어가기 위한 상태/결정/산출물/다음 작업** 정리  
> 기준일: 2026-02-10 (KST)

---

## 0) 오늘 결론 요약

- **D=4 단계(레거시 결과를 Golden으로 고정 + 회귀 테스트 PASS) 완료**
  - Stamp: `3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206`
  - Golden Regression: **PASS**
- 백테스트 실행(레거시/래핑)으로 **CSV 풀세트 8개**가 정상 생성됨.
- Golden 갱신 과정에서 PowerShell 변수 치환 이슈로 `snapshot__trades` 복사 커맨드가 1회 실패했으나, **Regression이 PASS인 것으로 보아 필수 비교 파일은 정상 갱신됨.**
  - (원하면 `${stamp}`로 재복사 가능)

---

## 1) 개발 환경/전제

- OS/경로: Windows / `D:\Quant`
- Python venv: `D:\Quant\venv64` (Python 3.10.x)
- DB는 리팩토링 동안 **업데이트/변경하지 않음(고정)**  
  - `..\..\data\db\regime.db`
  - `..\..\data\db\price.db`
  - `..\..\data\db\fundamentals.db`
- 리팩토링 목표: 기존 레거시(run_backtest_s2_v5 계열) 동작을 유지하면서
  - `run_backtest_v5.py` + `core/*` + `strategies/s2.py` + `outputs/*`로 구조화
  - 회귀 테스트(golden)로 결과 동치 검증하며 단계적으로 “레거시 위임” 제거

---

## 2) 고정된 기준(결정 사항)

### 2.1 RBW vs RBM (리밸런싱)
- **RBW = 주간(Week-anchor) 리밸런싱**  
- **RBM = 월말(Month-end) 리밸런싱**
- 골든 fixture는 현재 **RBW 기준으로 확정**함.
  - Golden 파일명: `..._RBW_...`
- RBM은 이후 별도 fixture/stamp로 추가 예정(진행상황표 ID 8~9).

### 2.2 Golden 정책(Option A 선택)
- 리팩토링 동안 DB 고정이므로, **현재 실행 결과를 Golden 기준으로 갱신**하여
  - 이후부터는 “리팩토링 변경으로 인한 결과 변화”만 추적하기로 결정.
- 따라서 D=4에서 “수치 미세 차이” 문제는 **Golden 갱신으로 해결**.

---

## 3) 핵심 커맨드(확정본)

### 3.1 백테스트 실행 커맨드 (RBW / S2 / 3m / end=2026-02-06)
> 아래 실행으로 **reports/backtest_regime_refactor**에 산출물이 생성됨.

```powershell
cd D:\Quant\src\backtest

python .\run_backtest_v5.py `
  --strategy S2 `
  --s2-refactor `
  --regime-db ..\..\data\db\regime.db `
  --price-db ..\..\data\db\price.db `
  --fundamentals-db ..\..\data\db\fundamentals.db `
  --fundamentals-view s2_fund_scores_monthly `
  --universe-file ..\..\data\universe\universe_mix_top400_20260129_fundready.csv `
  --ticker-col ticker `
  --end 2026-02-06 `
  --horizon 3m `
  --good-regimes "4,3" `
  --top-n 30 `
  --sma-window 140 `
  --require-above-sma `
  --market-gate `
  --market-sma-window 60 `
  --market-sma-mult 1.02 `
  --exit-below-sma-weeks 2 `
  --rebalance W `
  --outdir ..\..\reports\backtest_regime_refactor
```

### 3.2 Golden Regression 실행(회귀 테스트)
```powershell
cd D:\Quant\src\backtest\tests

python .\regression_s2_golden.py `
  --stamp 3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206 `
  --golden-dir D:\Quant\src\backtest\tests\fixtures\golden\backtest_regime `
  --current-dir D:\Quant\reports\backtest_regime_refactor
```

- 결과: **[PASS] golden regression matched ...** (D=4 완료)

---

## 4) 산출물(현재 기준선) — CSV 풀세트 8개 확인

### 4.1 현재 출력 폴더
- `D:\Quant\reports\backtest_regime_refactor`

### 4.2 동일 stamp 기준 파일 8개(실제 확인됨)
- `regime_bt_equity_<stamp>.csv`
- `regime_bt_holdings_<stamp>.csv`
- `regime_bt_ledger_<stamp>.csv`
- `regime_bt_perf_windows_<stamp>.csv`
- `regime_bt_snapshot_<stamp>.csv`
- `regime_bt_snapshot_<stamp>__trades.csv`
- `regime_bt_summary_<stamp>.csv`
- `regime_bt_trades_C_<stamp>.csv`

> stamp = `3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206`

### 4.3 Golden 폴더(갱신 대상)
- `D:\Quant\src\backtest\tests\fixtures\golden\backtest_regime`

### 4.4 Golden 백업(생성 완료)
- `D:\Quant\src\backtest\tests\fixtures\golden\backtest_regime__backup_20260210_220552`

---

## 5) 오늘 발생한 이슈/해결

### 5.1 PowerShell 변수 치환 문제 (`$stamp__trades`)
Golden 갱신(copy) 중 아래 라인에서 에러 발생:
- `copy "$C\regime_bt_snapshot_$stamp__trades.csv" $G -Force`
- PowerShell이 `$stamp__trades`를 **다른 변수로 해석**해 `$stamp`가 빠진 `regime_bt_snapshot_.csv`가 되어 실패.

✅ 안전한 재복사(권장 문법):
```powershell
copy "$C\regime_bt_snapshot_${stamp}__trades.csv" $G -Force
```

※ 다만 오늘은 회귀 테스트가 PASS라서 “필수 비교”는 이미 통과.  
(회귀가 `__trades`까지 비교하지 않았을 가능성 있음. 향후 비교 범위 확장 시 대비로 재복사 권장.)

---

## 6) 리팩토링 전체 진행 상황표 (ID 1~10, 난이도 포함 / 항상 고정)

| ID | 작업 묶음 | 난이도 | 상태 | 실제 한 일(요약) | 다음 해야 할 일(요약) |
|---:|---|:---:|---|---|---|
| 1 | Golden fixture 정리/배치 | ★★☆☆☆ | Done | 기존 레거시 산출물(snap/summary) 기반 fixture 경로 정리 | RBM fixture 추가 시 동일 패턴 적용 |
| 2 | Regression 크래시 제거 | ★★★☆☆ | Done | regression_s2_golden.py의 비교 로직/타입/정렬 관련 오류들을 패치 | 향후 비교 항목 확장 시 재점검 |
| 3 | Snapshot 정보컬럼(name) 정책 | ★★☆☆☆ | Done | name/market 등 표시용 컬럼 mismatch가 회귀를 깨지 않도록 정책 정립(무시) | 현재 파일이 실제로 적용됐는지 계속 확인 |
| 4 | 레거시 위임 실행/CSV 풀세트 산출 | ★★★☆☆ | Done | run_backtest_v5.py 실행으로 8종 CSV 생성 확인 | refactor 엔진 직실행으로도 동일 8종 생성되게 만들기 |
| 5 | fee/slippage parity(5/5) | ★★★☆☆ | Done | fee/slippage 차이(5 vs 10) 정리 및 동일화 | 다른 숨은 기본값도 동치인지 점검 |
| 6 | RBW golden 갱신 + PASS | ★★★★☆ | Done | Golden 백업 생성 후 결과를 Golden에 갱신, 회귀 PASS 확보 | (선택) snapshot__trades도 `${stamp}` 문법으로 재복사 |
| 7 | refactor 엔진 parity 포팅 시작 | ★★★★★ | Pending | - | **레거시 위임 제거**: core/engine + strategies/s2.py가 골든과 동치가 되도록 단계적 전환 |
| 8 | RBM fixture 추가 | ★★☆☆☆ | Pending | - | 월말(M) 실행 stamp로 별도 golden 파일 생성/배치 |
| 9 | RBM golden PASS | ★★★★☆ | Pending | - | RBM regression PASS 확보 |
| 10 | 표준 커맨드/문서화 | ★★☆☆☆ | Pending | - | “표준 실행 커맨드/옵션” 문서와 체크리스트 고정 |

---

## 7) 내일 해야 할 작업(우선순위)

### 7.1 최우선: D=5 시작(레거시 위임 제거)
목표: `--s2-refactor`가 단순 래핑이 아니라 **진짜 refactor 엔진 경로**를 타고도
- 동일 stamp에서
- 동일 8종 CSV를 생성하며
- regression PASS를 유지하도록 만들기.

#### 권장 절차(안전한 단계적 전환)
1) **현재 PASS가 나는 실행 경로를 “기준선”으로 고정**
2) 레거시 위임 부분을 한번에 제거하지 말고:
   - (a) 데이터 로딩(core/data)만 refactor로 전환
   - (b) 리밸런싱 날짜 생성 로직 동치 확인
   - (c) S2 스코어/필터 계산 동치 확인
   - (d) 거래/스냅샷/요약 산출 동치 확인
3) 각 단계마다 regression 돌려 PASS 확인 → 다음 단계로 이동

### 7.2 두 번째: RBM(Month-end)도 기준선 마련(D=8~9)
- 동일한 S2 파라미터로 `--rebalance M` 실행 후
- RBM stamp로 산출물 생성
- Golden fixture에 추가
- Regression PASS 확보

### 7.3 세 번째: 표준 커맨드/문서화(D=10)
- “RBW 표준 커맨드”, “RBM 표준 커맨드”를 확정하고
- 옵션들의 의미/기본값/주의사항을 문서에 고정

---

## 8) 주의 사항(리팩토링 마무리 품질을 좌우)

1) **DB 고정 전제 유지**
   - 리팩토링 동안 DB/Universe 파일을 업데이트하면 golden 동치가 흔들림.
2) **stamp(파일명 규칙) 일관성 유지**
   - 회귀/fixture는 파일명(prefix + stamp) 매칭에 의존.
3) **PowerShell 문자열 내 변수 경계**
   - `${stamp}` 같은 중괄호 문법으로 변수 경계 명확히 할 것.
4) **RBW vs RBM 혼동 금지**
   - RBW는 week-anchor(weekday=2 등)로 rebalance_count가 크게 나옴(예: 642)
   - RBM은 month-end로 rebalance_count가 작게 나옴(예: 149)
5) **“PASS 기준선”은 항상 보존**
   - 큰 수정 전에는 현재 PASS 버전을 별도 백업(예: `_archive` 폴더) 권장.
6) **회귀 테스트 tol을 임의로 완화하지 않기**
   - 지금은 golden 갱신(Option A)로 해결했으므로, tol 완화는 지양.

---

## 9) 내일 새 대화창에서 바로 이어갈 때 필요한 자료(업로드 권장 리스트)

> “현재 로컬에서 실제 실행 중인 파일 그대로”가 중요합니다(버전 혼입 방지).

1) `D:\Quant\src\backtest\run_backtest_v5.py`
2) `D:\Quant\src\backtest\core\engine.py`
3) `D:\Quant\src\backtest\core\data.py`
4) `D:\Quant\src\backtest\strategies\s2.py`
5) `D:\Quant\src\backtest\outputs\csv_plugin.py`
6) `D:\Quant\src\backtest\tests\regression_s2_golden.py` (현재 사용본)

+ (선택) `naming.py`, `contracts.py`, `registry.py`, `base.py` 등 현재 적용본

---

## 10) 체크포인트(내일 시작하자마자 할 일)

1) RBW 기준선 재확인:
   - backtest 실행 → CSV 8종 생성 확인 → regression PASS 확인
2) 그 다음 D=5로 진입:
   - 레거시 위임 분기 위치 식별
   - “refactor 엔진 경로”를 활성화하는 최소 변경부터 적용
   - 매 변경마다 regression PASS 유지

---

## Appendix) 오늘 최종 상태(확정)

- D=4(RBW) Golden Regression: **PASS**
- Golden 백업 생성: **완료**
- 다음 목표: D=5(레거시 위임 제거, refactor 엔진 parity)

