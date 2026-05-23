# AI Live Shadow Tracker Policy - 2026-05-06

## Purpose

`AI-CANDIDATE-VALIDATION-V01`의 shadow tag가 실제 운영 이후에도 성과를 구분하는지 추적한다.

한글명은 `퀀트후보검증AI`다. `AI-OVERLAY-V01`은 기존 파일명/과거 리포트에 남아 있는 legacy alias로만 본다.

이 문서는 재구성/백테스트 성격의 AI 성과와 실제 운영 이후 성과를 분리하기 위한 기준이다.

## Tracker Types

### Reconstructed tracker

- Script: `D:\Quant\scripts\build_ai_shadow_performance_tracker.py`
- DB table: `D:\Quant\data\db\ai_learning.db::ai_shadow_performance_tracker`
- Meaning: 과거 이벤트를 현재 AI 로직으로 재구성해 tag별 성과를 빠르게 검증한다.
- Use: 연구용 방향성 검증.
- Limitation: 실제 운영 이후의 독립 성과는 아니다.

### Live-only tracker

- Script: `D:\Quant\scripts\build_ai_live_shadow_tracker.py`
- DB tables:
  - `D:\Quant\data\db\ai_learning.db::ai_live_shadow_tracker_detail`
  - `D:\Quant\data\db\ai_learning.db::ai_live_shadow_tracker_summary`
- Meaning: AI shadow score가 생성된 이후의 실제 가격 흐름만 추적한다.
- Tracking start: `max(event_date, scored_at_date)`
- Use: 실제 운영 이후 AI tag 성과 검증.

## Live Horizons

- `1w`: 5 trading days after tracking start
- `2w`: 10 trading days
- `1m`: 21 trading days
- `2m`: 42 trading days
- `3m`: 63 trading days

충분한 거래일이 지나지 않은 구간은 `sample_count=0`, 성과값은 `N/A`로 본다.

## Daily Pipeline Integration

`D:\Quant\src\quant_service\run_daily_quant_pipeline.py`에 AI overlay 단계가 연결되어 있다.

Execution order:

1. `admin_new_entry_tracker.json` 생성 및 검증
2. `build_ai_overlay_v01.py` 실행
3. `build_ai_shadow_performance_tracker.py` 실행
4. `build_ai_live_shadow_tracker.py --shadow-asof all --asof {asof}` 실행
5. trading sign 및 publish 단계 진행

Skip option:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\quant_service\run_daily_quant_pipeline.py --asof 2026-05-04 --skip-ai-overlay
```

## Manual Commands

Single shadow date:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_ai_live_shadow_tracker.py --shadow-asof 2026-05-04 --asof 2026-05-04
```

All recent shadow files:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_ai_live_shadow_tracker.py --shadow-asof all --asof 2026-05-04
```

## Current Baseline

- First live shadow score date: `2026-05-04`
- First live tracker run: `2026-05-04`
- Detail rows: `2,736`
- Summary rows: `50`
- Current live samples: `0` for all horizons because the scoring date and performance date are the same.

Expected first meaningful checks:

- `1w`: after at least 5 trading days
- `2w`: after at least 10 trading days
- `1m`: after at least 21 trading days

## Operating Rule

AI shadow output is not a portfolio replacement signal yet.

Use it as:

- `AI_HIGH_CONVICTION`: strong shadow confirmation candidate
- `AI_CONFIRM`: short-term confirmation candidate
- `AI_RISK_REVIEW`: risk review / avoid candidate
- `AI_OBSERVE`: no strong AI evidence

Promotion to model logic requires live-only sample accumulation and comparison against reconstructed tracker results.
