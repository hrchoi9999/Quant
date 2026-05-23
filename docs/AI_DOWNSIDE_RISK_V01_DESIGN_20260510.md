# AI-DOWNSIDE-RISK-V01 Design - 2026-05-10

## Identity

| item | value |
|---|---|
| model_code | `AI-DOWNSIDE-RISK-V01` |
| 한글명 | 하락위험예측AI |
| role | risk overlay shadow |
| target | S/T/I/C/user 후보 중 주식 후보 |
| ETF | out-of-scope, `AI-ETF-*` 별도 트랙 |

## Purpose

`하락위험예측AI`는 좋은 종목을 새로 찾는 모델이 아니라, 기존 후보와 보유 후보 중 하락위험이 커진 대상을 찾는 모델이다.

활용 목적은 세 가지다.

1. 신규 후보 caution tag
2. 보유 후보 비중축소/매도 후보 관찰
3. 기존 `QM-RISK`와 결합한 risk overlay 고도화

## Target

초기 target은 1M downside risk다.

`label_downside_1m = 1` 조건:

- 1M forward return <= -3%
- 또는 1M forward MDD <= -15%

기존 `AI-CANDIDATE-VALIDATION-V01` mart의 `label_bad_1m_strict`를 우선 사용한다.

## Tags

| tag | probability rule | interpretation |
|---|---:|---|
| `risk_exit_watch` | >= 0.70 | 매도/비중축소 후보 관찰 |
| `risk_caution` | >= 0.60 | 비중축소 검토 |
| `risk_watch` | >= 0.45 | 관찰 필요 |
| `risk_clear` | < 0.45 | 유지 가능 |

## Initial Implementation

Script:

`D:\Quant\scripts\build_downside_risk_ai_v01.py`

Inputs:

- `D:\Quant\reports\ai_overlay_v01\ai_overlay_training_mart_YYYYMMDD.csv`

Outputs:

- `D:\Quant\reports\downside_risk_ai_v01\downside_risk_ai_current_scores_YYYYMMDD.csv`
- `D:\Quant\reports\downside_risk_ai_v01\downside_risk_ai_eval_YYYYMMDD.json`
- `D:\Quant\reports\downside_risk_ai_v01\downside_risk_ai_eval_YYYYMMDD.md`
- `D:\Quant\service_platform\web\admin_data\current\downside_risk_ai_current.json`
- `D:\Quant\data\models\downside_risk_ai\AI-DOWNSIDE-RISK-V01_YYYYMMDD_001.joblib`

## Operating Rule

초기에는 admin-only shadow다.

`risk_caution`, `risk_exit_watch`가 실제로 1W/2W/1M 손실 회피에 도움이 되는지 확인하기 전까지 public 추천 제외나 자동 매도 판단에는 사용하지 않는다.
