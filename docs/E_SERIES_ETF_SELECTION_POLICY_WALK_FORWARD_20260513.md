# E-Series ETF Selection Policy Walk-Forward

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 목적: role/asset adaptive selection policy가 과최적화인지 확인
- 스크립트: `D:\Quant\scripts\run_e_series_etf_selection_policy_walk_forward.py`
- 검증 방식:
  - 평가일 이전 365일 데이터를 사용해 role/asset별 best policy 선택
  - 1M forward label 누수를 줄이기 위해 평가일 직전 31일 제외
  - 선택된 policy를 다음 평가일 포트폴리오에만 적용

## Result

| policy | avg 1M ret | win rate | avg 1M risk adj | worst 1M | compounded |
|---|---:|---:|---:|---:|---:|
| hybrid_b50_ai50_top3_role | 2.1174% | 57.6923% | 0.4684% | -7.4980% | 65.6200% |
| hybrid_b70_ai30_top3_role | 2.0158% | 57.6923% | 0.3799% | -7.4835% | 61.5646% |
| wf_role_asset_adaptive_policy | 1.7933% | 57.6923% | 0.2461% | -3.5420% | 55.6375% |
| baseline_top3_role | 1.8252% | 57.6923% | 0.2320% | -7.6366% | 54.7330% |
| wf_role_adaptive_policy | 1.7037% | 53.8462% | 0.1216% | -7.1724% | 50.5295% |
| wf_asset_adaptive_policy | 1.2779% | 53.8462% | -0.4614% | -2.8960% | 36.8773% |

## Interpretation

In-sample ablation에서는 `role_asset_adaptive_best_policy`가 가장 좋았지만, walk-forward 재검증에서는 고정 `hybrid_b50_ai50_top3_role`이 가장 안정적이었다.

따라서 현재 판단은 다음과 같다.

- `hybrid_b50_ai50_top3_role`: 대표 shadow policy 유지
- `role_asset_adaptive_best_policy`: 운영 승격 보류
- adaptive policy: 과거 선택 정책이 다음 기간에 그대로 유지되지 않는 문제가 있음

다만 `wf_role_asset_adaptive_policy`는 worst 1M return이 baseline보다 크게 개선됐다.
수익률 목적이 아니라 tail-risk 완화 overlay로 재설계할 여지는 있다.

## Next Step

다음 실험은 adaptive policy를 “수익률 극대화”가 아니라 “tail-risk control” 관점으로 재설계하는 것이다.

후보:

- adaptive 정책 변경 빈도 제한
- 최근 3~6개월보다 12~18개월 안정성 가중
- best policy 선택 기준을 avg return이 아니라 worst return / MDD / risk-adjusted 복합점수로 변경
- asset bucket별 최소 관측 수 상향
