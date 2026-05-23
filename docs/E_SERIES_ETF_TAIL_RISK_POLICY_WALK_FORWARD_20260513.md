# E-Series ETF Tail-Risk Policy Walk-Forward

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 목적: adaptive selection policy를 수익률 극대화가 아니라 손실 꼬리 완화 관점으로 재설계
- 스크립트: `D:\Quant\scripts\run_e_series_etf_tail_risk_policy_walk_forward.py`

## Tail Score

과거 구간에서 role/asset별 policy를 고를 때 아래 가중치를 사용했다.

| 항목 | 가중치 |
|---|---:|
| worst 1M return | 35% |
| avg MDD proxy | 25% |
| avg risk-adjusted return | 25% |
| win rate | 10% |
| avg return | 5% |

검증 방식은 walk-forward 구조다.

- 과거 365일로 policy 선택
- 평가일 직전 31일은 제외
- 선택된 policy를 다음 평가일에만 적용

## Result

| policy | avg 1M ret | win rate | avg 1M risk adj | avg MDD proxy | worst 1M | compounded |
|---|---:|---:|---:|---:|---:|---:|
| wf_tail_asset_policy | 2.0414% | 57.6923% | 0.5911% | -2.9005% | -3.1640% | 64.5265% |
| hybrid_b50_ai50_top3_role | 2.1174% | 57.6923% | 0.4684% | -3.2981% | -7.4980% | 65.6200% |
| hybrid_b70_ai30_top3_role | 2.0158% | 57.6923% | 0.3799% | -3.2718% | -7.4835% | 61.5646% |
| ai_quality_guard_top3_role | 1.8110% | 61.5385% | 0.3799% | -2.8622% | -2.7661% | 56.4779% |
| baseline_top3_role | 1.8252% | 57.6923% | 0.2320% | -3.1865% | -7.6366% | 54.7330% |

## Interpretation

성장 목적의 대표 shadow policy는 여전히 `hybrid_b50_ai50_top3_role`이 가장 적합하다.

다만 tail-risk 완화 목적에서는 `wf_tail_asset_policy`가 의미 있는 결과를 보였다.

Baseline 대비:

- 평균 1M 수익률: +0.2162%p
- 평균 1M risk-adjusted: +0.3591%p
- avg MDD proxy: +0.2860%p 개선
- worst 1M return: +4.4726%p 개선
- 누적 검증 수익률: +9.7935%p

Hybrid 50/50 대비:

- 평균 1M 수익률은 -0.0760%p 낮음
- 누적 검증 수익률은 -1.0935%p 낮음
- worst 1M return은 +4.3340%p 개선
- avg MDD proxy도 +0.3976%p 개선

## Operating View

현 단계 운영 판단은 다음과 같다.

- 대표 성장형 shadow: `hybrid_b50_ai50_top3_role`
- tail-risk overlay 후보: `wf_tail_asset_policy`
- `wf_tail_asset_policy`는 전체 대체 모델이 아니라 risk-off 또는 변동성 확대 국면에서만 적용하는 overlay 후보로 관찰

## Next Step

다음 단계는 시장모드별 전환 규칙이다.

예:

- risk-on / neutral: `hybrid_b50_ai50_top3_role`
- risk-off 또는 변동성 stress: `wf_tail_asset_policy`
- 급락 위험 구간: `ai_quality_guard_top3_role` 또는 tail-risk asset policy 병행 관찰
