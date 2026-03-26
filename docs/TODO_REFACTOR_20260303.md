# TODO_REFACTOR_20260303.md
(작성일: 2026-03-03 KST)

## 0. 최우선 목표
- **S3 core2_gate(리스크 관리형) 스윕이 “실제로 실행되어 결과 파일이 생성”되도록** 배치/실행 체인을 정상화한다.
- 그 다음, 스윕 결과로 **임계값(OPEN/CLOSE)과 breadth 정의(use_slope)를 튜닝**한다.

---

## 1. P0: 스윕 실행이 안 되는 문제(가장 먼저 해결)
### 1.1 파일 배치/파일명 정합성 확보
**해야 할 일**
- 아래 파일을 “정확한 경로/파일명”으로 저장(중요):
  - `D:\Quant\src\experiments\run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py`
  - `D:\Quant\_summarize_s3_gate_sweep.py`
  - `D:\Quant\sweep_s3_gate_breadth.ps1`

**검증 명령**
```powershell
Test-Path D:\Quant\src\experiments\run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py
Test-Path D:\Quant\_summarize_s3_gate_sweep.py
Test-Path D:\Quant\sweep_s3_gate_breadth.ps1
```
- 3개 모두 `True`여야 함.

### 1.2 단독 1회 실행으로 에러 노출
**해야 할 일**
- 스윕 파일을 직접 1회 실행해 “출력/에러”를 확인한다.
```powershell
cd D:\Quant
python D:\Quant\src\experiments\run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py --start 2013-10-14 --end 2026-02-23 --top-n 20 --min-holdings 10 --tag test_open0p50 --gate-enabled 1 --gate-open-th 0.50 --gate-close-th 0.46 --gate-use-slope 1 --gate-use-ma-stack 1
```

### 1.3 PS1 스윕 실행 및 결과 생성 확인
**해야 할 일**
```powershell
cd D:\Quant
powershell -ExecutionPolicy Bypass -File .\sweep_s3_gate_breadth.ps1
```

**결과 확인**
- 아래 패턴의 파일이 최소 1개 이상 생성되어야 함:
  - `D:\Quant\reports\backtest_s3_dev\s3_nav_hold_top20_core2_gate_swp_*.csv`
- 요약 파일 생성:
  - `D:\Quant\reports\backtest_s3_dev\s3_gate_sweep_summary.csv`

---

## 2. P1: Gate 튜닝(스윕 결과 기반)
### 2.1 임계값(breadth_open/close) 튜닝
**목표**
- gate_open_ratio가 지나치게 낮아 “현금 구간이 길어지는” 현상을 완화
- 동시에 MDD 개선 효과를 유지

**권장 스윕 해석 프레임**
- 상위 후보 3~5개를 고를 때, 아래를 함께 본다:
  - CAGR(또는 cum_return)
  - MDD
  - gate_open_ratio (너무 낮으면 기회 손실)
  - exposure_mean (평균 노출이 너무 낮으면 NAV 왜곡)

### 2.2 breadth 정의 완화(use_slope=0)
**해야 할 일**
- `gate_use_slope=1`과 `0` 결과를 비교
- slope 포함이 너무 엄격하면 `0`이 실용적일 가능성이 큼

---

## 3. P2: 성능평가 표준화(사용자 선호 포맷 반영)
사용자 선호:
- 백테스트 성능 지표를 A안(1Y/2Y/3Y/5Y/FULL: Start/End/일수/CAGR/MDD/Sharpe/평균 일간수익률/일간 변동성) 표로 제공

**해야 할 일**
- S3 NAV(주간) 기반이므로,
  - “주간 기준 성능표”와 “일간 환산 지표”를 구분해 표준화하거나
  - S3 평가용 별도 템플릿(주간)을 정의
- core2 vs core2_gate vs 스윕 상위 케이스를 동일 포맷으로 비교

---

## 4. P3: S3 모델 정교화 로드맵(게이트 이후)
### 4.1 KOSDAQ 편중 원인에 대한 정교화 옵션(선택)
- growth_score 분포 편향(275.75가 KOSDAQ에 과다) 때문에 tie-break가 시장별 점수 분포에 영향을 주는 문제
- 옵션:
  1) tie-break 가중치 축소/0(순수 core only) 비교
  2) 펀더멘털 점수의 “시장별 표준화(z-score)” 또는 “분위수 계산을 시장별로 분리”
  3) 성장점수 결측/동일값 처리 개선(특정 값이 과다 발생하는 원인 점검)

### 4.2 “전략 풀” 관점의 S4(방어형) 설계(별도 트랙)
- core2(공격형)과 별개로:
  - 하락/횡보장 대응 S4 전략이 필요
- 접근:
  - S3의 gate 논리를 더 강하게(시장 노출 축소) 하거나
  - 완전히 다른 알파(저변동/퀄리티/배당/저PBR 등)로 새 전략 설계
- 단, S2/S3 개발 안정화(스윕/운영) 이후 착수 권장

---

## 5. 운영 리스크/실수 방지 체크리스트
- [ ] 엑셀로 결과 CSV를 열어둔 채 재실행하지 않기(잠금파일 `~$` 생성/PermissionError)
- [ ] ticker는 항상 문자열 6자리(zfill)로 저장되는지 확인
- [ ] S2 관련 파일/DB 경로를 스크립트가 참조하지 않는지(특히 features.db) 재확인
- [ ] 결과 파일명(tag 포함)이 스윕 케이스별로 고유한지 확인

---

## 6. 다음 대화에서 내가(사용자) 제공하면 좋은 것
- (필수) `s3_gate_sweep_summary.csv`
- (선택) summary 상위 3개 케이스의 NAV csv 3개
- 그러면:
  - core2 vs core2_gate(최적 후보) 비교표
  - “B안 별도 모델 운영” 여부를 데이터로 바로 결론 가능
