# Quant Model Return-First Principle - 2026-05-14

## Purpose

Quant 전략모델과 AI 학습모델의 개발, 실험, 운영 승격 기준을 `수익률 개선` 중심으로 정렬한다.

## Core Principle

모델 개선의 1차 목표는 투자수익률 향상이다.

- AUC, Rank IC, hit rate, win rate는 보조 지표다.
- 운영 후보 승격은 실제 또는 백테스트 수익률 개선이 확인될 때만 검토한다.
- 위험 지표는 수익률을 보완하는 제약 조건으로 사용한다.
- 위험 제어 모델도 최종 목적은 손실 회피를 통한 누적 수익률 개선이다.

## Evaluation Priority

모델 비교 시 우선순위는 아래 순서로 본다.

1. 누적수익률 / CAGR / Top-N forward return 개선
2. 전략모델 baseline 대비 excess return 개선
3. 손실 위험 제어: MDD, worst return, drawdown frequency
4. 안정성: 기간별 일관성, turnover, coverage
5. 통계 성능: AUC, Rank IC, hit rate

## QuantMarket Market Forecast Usage

QuantMarket handoff의 시장전망 feature는 Quant 모델의 시장 관련 변수로 사용한다.

Primary source:

`D:\QuantMarket\service_platform\quant_model_handoff\market_context\current`

Primary forecast:

`market_forecast_ai_calibrated_daily_current.csv`

Usage policy:

- primary model: ridge calibration
- primary horizon: `20d`
- key columns:
  - `predicted_forward_return`
  - `calibrated_forecast_score`
  - `calibrated_forecast_label`
  - `calibration_confidence_score`
  - `training_sample_count`
- AI v1.1 prediction은 research candidate로만 사용한다.
- null은 0으로 즉시 대체하지 않고 coverage/confidence feature와 함께 해석한다.

## Model Upgrade Rule

새 feature 또는 AI 모델은 아래 순서로 반영한다.

1. Feature ablation
2. Baseline vs overlay return comparison
3. Shadow tracking
4. 운영 후보 등록
5. 실제 운영 반영

승격 조건은 단순 예측 정확도가 아니라 baseline 대비 수익률 개선이다.

## Scope

이 원칙은 아래 모델군에 적용한다.

- S/T/I/C 전략모델
- AI-CANDIDATE-VALIDATION-V01 / 퀀트후보검증AI
- AI-DOWNSIDE-RISK-V01 / 하락위험예측AI
- AI-CANDIDATE-RANK-DELTA-V01 / 후보순위조정AI
- AI-GROWTH-VALUATION-V01 / 주가수준평가AI
- AI-THEME-PERSISTENCE-V01 / 테마지속성AI
- AI-MODEL-SELECTION-V01 / 모델선택AI
- E-series ETF 모델 및 ETF AI 학습모델

