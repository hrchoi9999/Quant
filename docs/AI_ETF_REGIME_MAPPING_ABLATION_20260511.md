# ETF 시장 모드 Mapping Ablation

## 목적

QM의 5단계 시장국면, 4단계 변동성 국면, 연속 score를 ETF AI 운용용 3모드(`risk_on`, `neutral`, `risk_off`)로 단순화하는 mapping rule을 비교한다.

기준 모델은 직전 실험에서 가장 좋았던 조합으로 고정한다.

- model_code: `AI-ETF-ROLE-ALLOCATION-V01`
- sleeve: `top3`
- label: `horizon_v2_top1`
- 검증 구간: `2024-01-01` ~ `2026-05-08`

## Mapping 후보

| regime_map | 의미 |
|---|---|
| `score_default` | 기존 score rule. `risk_on_score`, `risk_off_score`, `market_state_score` 사용 |
| `score_diff` | `risk_on_score - risk_off_score` 차이와 state fallback 사용 |
| `label_vol` | 시장국면 label 중심, stress volatility는 risk_off override |
| `strict` | clean uptrend에서만 risk_on, stress/downside는 빠르게 risk_off |
| `state_only` | 시장국면 label만 사용 |

## 결과

| regime_map | AUC | top-pick label rate | AI top1 risk adj | rule risk adj | learned risk adj | mode 분포 |
|---|---:|---:|---:|---:|---:|---|
| `score_diff` | 0.711817 | 48.15% | 1.84% | 0.04% | -0.25% | risk_off 75 / risk_on 29 / neutral 7 |
| `score_default` | 0.711817 | 48.15% | 1.84% | 0.03% | -0.91% | risk_off 63 / risk_on 24 / neutral 24 |
| `state_only` | 0.711817 | 48.15% | 1.84% | -0.26% | -0.06% | risk_off 50 / risk_on 33 / neutral 28 |
| `strict` | 0.711817 | 48.15% | 1.84% | -0.53% | -0.48% | risk_off 70 / risk_on 23 / neutral 18 |
| `label_vol` | 0.711817 | 48.15% | 1.84% | -0.77% | -0.07% | risk_off 65 / risk_on 26 / neutral 20 |

## 해석

1. AUC는 mapping별로 동일했다.
   - 현재 모델은 `regime_mode` categorical보다 QM 연속 score에서 예측력을 더 많이 얻고 있다.
   - 따라서 mapping은 AI 판별력보다 운용 rule weight에 더 직접적으로 영향을 준다.

2. `score_diff`가 rule 기반 배분에서 가장 좋았다.
   - risk_on/risk_off의 상대 강도를 보는 방식이 단순 label보다 낫다.
   - neutral을 지나치게 많이 두지 않고 방향성을 더 명확히 준다.

3. `label_vol`, `strict`는 너무 방어적이다.
   - risk_off override가 강해지면서 rule risk-adjusted 성과가 낮아졌다.
   - ETF 역할배분에서는 stress를 무조건 방어로 보내기보다, score spread와 함께 보는 편이 낫다.

4. `state_only`는 정보 손실이 크다.
   - 5단계 label만으로는 변동성/리스크 강도를 충분히 반영하지 못한다.

## 현재 판단

ETF AI의 시장 모드 mapping baseline은 `score_diff`로 두는 것이 좋다.

다만 AI model feature에는 3모드 label만 넣지 말고, 아래 원천 score를 계속 유지해야 한다.

- `market_state_score`
- `risk_on_score`
- `risk_off_score`
- `market_stress_score`
- `drawdown_pressure_score`
- `volatility_regime_label`
- `market_state_label`

즉 운용 표시는 3모드로 단순화하되, 학습 feature는 QM의 세부 국면과 연속 score를 유지한다.

## Outputs

- `D:\Quant\scripts\run_etf_role_allocation_ai_v01_experiment.py`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_allocation_experiment_20260508_top3_horizon_v2_top1_score_diff.json`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_allocation_policy_summary_20260508_top3_horizon_v2_top1_score_diff.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_ai_scored_20260508_top3_horizon_v2_top1_score_diff.csv`
