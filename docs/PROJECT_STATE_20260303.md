# PROJECT_STATE_20260303.md
(작성일: 2026-03-03 KST)

## 0. 이번 대화의 범위/목표
- **목표:** 기존 S2(레짐 기반) 시스템을 절대 건드리지 않는 전제에서, **S3(급등 초입 포착 → 상승 유지 시 중장기 홀드)** 전략을 별도 실험/운영 가능한 형태로 구축·검증.
- **핵심 방향:** S3는 S2와 **동일 유니버스(Top400)**를 일단 사용하되, **선별 로직(스코어/필터/홀드/게이트)** 차이로 서로 다른 종목을 고르게 만드는 것을 우선 검증.
- **리스크 관리:** S3 core2(공격적) 외에, 별도 모델로 **Market Gate(Breadth) 기반 리스크 관리형(core2_gate)** 를 만들고 스윕 테스트로 튜닝.

---

## 1. 환경/경로/안전 원칙(중요)
### 1.1 프로젝트 루트/환경
- 프로젝트 루트: `D:\Quant`
- 가상환경: `D:\Quant\venv64`

### 1.2 “S2 절대 불변” 운영 원칙
- S2 실행환경/DB/파일을 **절대 수정·덮어쓰기 하지 않음**.
- S3 개발은 **S3 전용 DB 폴더** 및 **실험 스크립트**로만 진행.

### 1.3 S3 전용 DB/입력
- S3 전용 features DB (S2와 분리):  
  - `D:\Quant\data\db_s3\features_s3.db`
- 유니버스(공통):  
  - `D:\Quant\data\universe\universe_mix_top400_latest.csv` (`asof = 2026-02-23` 확인)

---

## 2. S3 데이터 확인(스키마/커버리지)
### 2.1 가격 DB(참고: S2에서 사용)
- `price.db :: prices_daily` 스키마 확인 완료
- 컬럼: ticker/date/open/high/low/close/volume/value/source/created_at/updated_at
- ticker는 TEXT이며 6자리 표준이 가능(0-padding 필요).

### 2.2 펀더멘털 DB(참고: S2에서 사용)
- `fundamentals.db` 내 객체 목록 확인:
  - `fundamentals_monthly`
  - `fundamentals_monthly_mix400_latest` 등
  - `view s2_fund_scores_monthly`, `view vw_s2_top30_monthly`
- `fundamentals_monthly_mix400_latest` 샘플 확인:
  - columns: date/ticker/corp_name/bsns_year/available_from/revenue_yoy/op_income_yoy/growth_score

### 2.3 S3 features 생성/확인(실행 로그 기반)
- `build_s3_fund_features_monthly.py`
  - output: `features_s3.db::s3_fund_features_monthly`
- `build_s3_price_features_daily.py`
  - output: `features_s3.db::s3_price_features_daily`
  - pandas groupby.apply 경고(FutureWarning) 관찰됨 (동작은 정상)

---

## 3. S3 종목 선택(Top-N) 및 “KOSDAQ only” 이슈 분석
### 3.1 S3 선택 스크립트 실행 결과
- 실행: `python .\src\experiments\select_s3_weekly.py`
- output: `D:\Quant\reports\backtest_s3_dev\s3_selection_top30_2026-02-23.csv`
- 결과: Top30이 **KOSDAQ로만 구성**되는 현상 확인

### 3.2 원인 후보를 데이터로 확인
- 시장별 커버리지 자체는 정상:
  - KOSPI 200 / KOSDAQ 200 모두 피처 커버리지(모멘텀/거래대금/adv 등) 1.0 수준
- 그러나 `growth_score==275.75`가 **KOSDAQ에 편중**:
  - 예: KOSDAQ 174 vs KOSPI 4
- 스코어 통계도 시장별 차이가 큼:
  - KOSDAQ score mean이 KOSPI보다 높게 나타나 Top30이 KOSDAQ로 쏠림

### 3.3 전략적 판단
- 강제로 KOSPI/KOSDAQ를 15/15로 나누는 할당은  
  - “스코어 기반 전략”의 의미를 훼손하고,
  - 이후 개선 효과 비교(AB test)에도 장애가 될 수 있어
- **1차는 “그대로 진행”** 하기로 결정(전략 수정/정교화 이후 분포 변화 가능).

---

## 4. S3 백테스트(Trend Hold) 구현 및 산출물 정의
### 4.1 목표 전략 형태(사용자 요구 반영)
- **상승 조건 유지 시 계속 홀드**:
  - “최대 보유기간 15일 제한” 같은 단타 제한은 제거/미적용 방향
- 주간 리밸런싱 유지(A안 유지)
- 최종 보유 종목 수는 **항상 20개 유지**(중복 방지 포함)

### 4.2 실행 및 산출물(기본)
- 실행: `python .\src\experiments\run_s3_trend_hold_top20.py`
- 출력(예):
  - NAV: `D:\Quant\reports\backtest_s3_dev\s3_nav_hold_top20_2013-10-14_2026-02-23.csv`
  - HOLD(last): `D:\Quant\reports\backtest_s3_dev\s3_holdings_hold_top20_2026-02-23.csv`
- 이후 요구에 따라 산출물 정의를 확장:
  - **(1) 최종 보유 Top20 “last”**
  - **(2) 기간 전체 “holdings history”**
  - **(3) NAV 시계열**
  - “TOP20”의 기준은 (사용자 선택) **2번(기간/리밸런스 전체 흐름 기반)으로 정리**

### 4.3 오류/이슈 및 해결
- DatetimeIndex `.iloc` 오류:
  - `_build_weekly_rebalance_dates`에서 `DatetimeIndex`에 `.iloc` 호출 → 수정 필요
- PermissionError(파일 잠금):
  - 엑셀로 CSV를 열어둔 상태에서 덮어쓰기 시도 → 다른 파일명으로 저장하도록 우회 로직 추가
- ticker 6자리 0-padding 누락:
  - CSV 저장 전 ticker를 문자열로 `zfill(6)` 적용 필요
- 누적수익률 컬럼 값 미기입:
  - last 파일에 **entry_price/entry_date 기반 누적수익률**을 계산해 넣도록 개선 시도

---

## 5. S3 버전 관리(코어 진화)
### 5.1 core2 / tiebreak / exit grace 흐름
- core2: 모멘텀·거래대금 비중 기반 “공격형” 개선
- tiebreak: 동점/근접 점수에서 펀더멘털(레벨/가속)로 미세 우선순위
- exit grace: 급락/횡보에서 “불필요한 털림” 완화 방향의 아이디어(구현 파일 생성)

### 5.2 core2 vs core2_gate
- 사용자 의사결정:
  - **B안(리스크 관리형 gate 모델)을 우선** 별도 모델로 실험/개선
- 목적:
  - 상승장 성능(core2)을 유지하면서, 잠재 리스크(과도한 MDD/급락 구간)를 완화

---

## 6. Market Gate(Breadth) 모델: 스윕 자동화 도입
### 6.1 왜 gate가 “0% 구간(현금) 길어짐”으로 왜곡될 수 있나
- breadth 임계값이 높거나(예: 0.55) 정의가 엄격하면(예: `ma60>ma120 AND ma60_slope>0`)
  - 시장이 충분히 좋아야만 “열림(투자 허용)”
  - 그 결과 **투자 기회 상실**이 길어지고 NAV가 “최근 강세에 과잉 의존/왜곡”될 수 있음

### 6.2 제안된 우선 튜닝(대화 합의)
1) breadth_min(임계값) 스윕: 0.45~0.60
2) 히스테리시스(OPEN/CLOSE 분리): 채터링 방지
3) breadth 정의 완화(특히 slope 조건 제거 옵션): gate_use_slope=0 스윕

### 6.3 스윕용 파일 생성(새 파일/안전)
> **중요:** 기존 파일을 덮어쓰지 않고 “새 파일”로만 제공함.

#### 6.3.1 스윕 실행 파일(새 파일)
- 파일: `run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP_2026-03-03_001.py`
- 기능:
  - CLI(argparse) 지원
  - `gate_open_th`, `gate_close_th`, `gate_use_slope` 등 스윕 파라미터 받음
  - output 파일명에 `tag` 포함(덮어쓰기 방지)
  - NAV에 `exposure`, `gate_open_ratio` 분석용 컬럼 포함

#### 6.3.2 스윕 러너(PS1)
- 파일: `sweep_s3_gate_breadth.ps1`
- 기능:
  - open 리스트(0.45~0.60) × slope 사용여부(1/0) 루프 실행
  - close = open - gap(기본 0.04)로 히스테리시스 자동 생성
  - 실행 결과 nav csv를 glob로 모아 요약 생성 호출

#### 6.3.3 요약 스크립트
- 파일: `_summarize_s3_gate_sweep.py`
- 기능:
  - NAV CSV들을 읽어 `cum_return / CAGR / MDD / Sharpe(주간)` 계산
  - `gate_open_ratio / exposure_mean / breadth_mean` 함께 산출
  - 결과: `s3_gate_sweep_summary.csv`로 저장

### 6.4 “스윕 실행했는데 파일이 안 생김” 문제 발생
- 사용자가 실행:
  - `powershell -ExecutionPolicy Bypass -File .\sweep_s3_gate_breadth.ps1`
- 콘솔 출력 없이 종료 + 결과 폴더에 파일 미생성
- 가장 유력한 원인:
  - **PS1이 기대하는 경로/파일명과 실제 배치가 불일치**
  - 예: 스윕 파일을 `..._2026-03-03_001.py` 이름 그대로 두면,
    PS1이 찾는 `run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py`를 못 찾아 실행이 되지 않음
- 해결책(진단 포함) 제시:
  - `Test-Path`로 파일 존재 확인
  - 스윕 파일을 **정해진 이름**으로 저장하거나, PS1의 `$py` 경로를 실제 파일명으로 변경
  - 스윕 파일 단독 1회 실행으로 에러를 강제로 노출

---

## 7. 현재 상태 요약(“지금 어디까지 됐나”)
- S3 core2(공격형) 베이스는 이미 실행/결과 CSV 생성까지 확인됨.
- S3 core2_gate(게이트형) 별도 모델을 위한:
  - 스윕용 실행파일/PS1/요약 스크립트 **제공 완료**
- 다만 사용자 PC 환경에서는:
  - **스윕 파일 배치/파일명 불일치로 인해 스윕이 실제로 실행되지 않은 상태**로 보임(출력 없음, 결과 파일 없음).

---

## 8. 산출물/첨부 파일(대화 중 생성/제공된 파일)
### 8.1 제공된 스윕 관련 파일(이번 대화 끝 기준)
- `run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP_2026-03-03_001.py`
- `sweep_s3_gate_breadth.ps1`
- `_summarize_s3_gate_sweep.py`

### 8.2 기타(대화 중 다룬/업로드된 주요 결과물)
- `s3_selection_top30_2026-02-23.csv`
- `s3_nav_hold_top20_core2_2013-10-14_2026-02-23.csv` 등 core2 관련
- `s3_core2_gate.zip` 등 gate 결과 zip(사용자 업로드)
- (중요) 엑셀 잠금 파일(`~$...csv`)이 생길 수 있음 → PermissionError 유발

---

## 9. 다음 대화창에서 “바로 이어서 시작하는 체크리스트”
- [ ] 스윕 파일이 아래 경로/이름으로 존재하는지 확인:
  - `D:\Quant\src\experiments\run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py`
- [ ] 요약 스크립트 확인:
  - `D:\Quant\_summarize_s3_gate_sweep.py`
- [ ] 스윕 PS1 실행:
  - `powershell -ExecutionPolicy Bypass -File .\sweep_s3_gate_breadth.ps1`
- [ ] 결과 생성 확인:
  - `D:\Quant\reports\backtest_s3_dev\s3_nav_hold_top20_core2_gate_swp_*.csv`
  - `D:\Quant\reports\backtest_s3_dev\s3_gate_sweep_summary.csv`

---

## 10. 결정사항(확정된 운영 철학)
- S3는 S2와 병합하지 않고 **별도 모델로 운영** (S2 안정성 보장 + 개발 리스크 분리)
- B안(core2_gate): **리스크 관리형**을 1순위로 먼저 실험/정교화
- 유니버스 확장은 단계적으로 진행하되,
  - 1차는 **Top400 동일 유니버스**에서 S2 vs S3 선별 차이를 검증하는 것이 우선
