# AI-CANDIDATE-RANK-DELTA-V01 Design - 2026-05-10

## Identity

| item | value |
|---|---|
| model_code | `AI-CANDIDATE-RANK-DELTA-V01` |
| 한글명 | 후보순위조정AI |
| role | candidate rank delta shadow |
| target | S/T/I/C/user 후보 중 주식 후보 |
| operating mode | admin-only shadow |

## Purpose

`후보순위조정AI`는 기존 Quant 모델이 뽑은 후보를 새로 대체하지 않는다.

목적은 기존 후보 안에서 다음을 관찰하는 것이다.

1. AI 관점에서 더 올려볼 후보
2. AI 관점에서 낮춰볼 후보
3. 기존 rank/score와 AI 판단이 충돌하는 후보

## Baseline Target

1M forward return을 같은 event_date 후보군 median과 비교한 excess proxy를 사용한다.

Upgrade label:

- 1M forward excess return >= +5%
- and 1M MDD > -12%

Downgrade label:

- 1M forward excess return <= -5%
- or 1M MDD <= -12%

Score:

`rank_delta_score = rank_upgrade_prob - rank_downgrade_prob`

## Next Rebalance Rank-Change Label Experiment

2026-05-10에 다음 리밸런싱 rank 변화 label 실험을 추가했다.

실험 목적은 1M forward return proxy가 아니라, 실제 주간 리밸런싱 결과에서 후보의 다음 상태를 직접 label로 쓰는 것이다.

Label source:

- `D:\Quant\service_platform\web\admin_data\current\admin_new_entry_tracker.json`
- `weekly_rankings.user_models`
- `weekly_rankings.internal_models`
- `weekly_rankings.tseries_models`

Label definition:

- `label_next_rank_drop`: 다음 리밸런싱에서 후보군에서 편출
- `label_next_rank_downgrade_3_retained`: 다음 리밸런싱에도 잔류한 후보 중 rank 3단계 이상 하락
- `label_next_rank_downgrade_3_or_drop`: rank 3단계 이상 하락 또는 편출
- `label_next_rank_upgrade_3_retained`: 다음 리밸런싱에도 잔류한 후보 중 rank 3단계 이상 상승

2026-05-08 기준 실험 결과:

| label | AUC | note |
|---|---:|---|
| `label_next_rank_drop` | 0.868866 | 편출 예측력이 가장 강함 |
| `label_next_rank_downgrade_3_retained` | 0.842631 | 잔류 후보 내 순위하락 예측도 양호 |
| `label_next_rank_downgrade_3_or_drop` | 0.842385 | 하락/편출 통합 caution label로 후보 |
| `label_next_rank_upgrade_3_retained` | 0.840665 | 잔류 후보 내 승격 가능성은 관찰 가치 있음 |

주의:

- 편출 label은 AUC가 높지만 투자성과 하락 label과 동일하지 않다.
- 따라서 이 label은 매수/매도 수익률 판단보다는 후보 유지/편출/순위조정 가능성 관찰에 우선 사용한다.
- 운영 target 교체 전에는 shadow tracker에서 실제 1W/2W/1M 성과와 함께 검증한다.

Experiment outputs:

- `D:\Quant\scripts\run_candidate_rank_delta_rank_change_ablation.py`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_rank_change_ablation_YYYYMMDD.csv`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_rank_change_ablation_YYYYMMDD.json`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_rank_change_labels_YYYYMMDD.csv`

## Model Breakdown

2026-05-08 기준 모델별 성능 분해를 추가했다.

Breakdown outputs:

- `D:\Quant\scripts\run_candidate_rank_delta_model_breakdown.py`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_model_breakdown_YYYYMMDD.csv`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_family_breakdown_YYYYMMDD.csv`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_model_breakdown_YYYYMMDD.md`

Family-level result:

| label | S | I | T | note |
|---|---:|---:|---:|---|
| `label_next_rank_drop` | 0.807783 | 0.562280 | 0.662727 | S 편출 예측은 강함, I는 편출률이 높아 분리력 약함 |
| `label_next_rank_downgrade_3_retained` | 0.840252 | 0.853522 | 0.575638 | S/I 하락 예측은 강함, T 하락 예측은 약함 |
| `label_next_rank_upgrade_3_retained` | 0.815837 | 0.888512 | 0.852912 | S/I/T 모두 승격 예측 신호 있음 |

Model-level note:

- `I-STOCK-STRONG-RSI-V01`: 잔류 후보 내 상승/하락 예측이 강함
- `S3`, `S3_ACCEL_V01`: 편출과 순위변화 예측이 비교적 안정적
- `S2`: rank-change label에서는 약함
- `T-STOCK-V01`: 상승 예측은 강하지만 하락/편출 caution은 약함
- `C` 계열은 이번 평가에서 충분한 rank history가 없어 별도 데이터 보강 후 검증 필요

## Model-Specific Learning And Label Selection

2026-05-10에 model-specific 학습 + label 차등화 실험을 추가했다.

목적:

- pooled model 하나로 모든 S/I/T 후보를 판단하지 않고, 모델군/개별 모델별로 따로 학습한다.
- 각 segment에서 AUC가 가장 높은 rank-change label을 선택한다.
- pooled model 대비 개선되는 구간만 선별한다.

Experiment outputs:

- `D:\Quant\scripts\run_candidate_rank_delta_model_specific_experiment.py`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_model_specific_experiment_YYYYMMDD.csv`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_model_specific_best_YYYYMMDD.csv`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_model_specific_experiment_YYYYMMDD.md`

2026-05-08 기준 best result:

| segment | best label | AUC | pooled AUC | lift | note |
|---|---|---:|---:|---:|---|
| S family | `label_next_rank_upgrade_5` | 0.871323 | 0.855761 | +0.015562 | S 전체는 분리 학습 이점 있음 |
| I family | `label_next_rank_upgrade_3_retained` | 0.877551 | 0.888512 | -0.010961 | pooled 유지가 더 우세 |
| T family | `label_next_rank_upgrade_3_retained` | 0.839573 | 0.852912 | -0.013339 | pooled 유지가 더 우세 |
| `S2` | `label_next_rank_upgrade_3_retained` | 0.660186 | 0.450338 | +0.209848 | 분리 학습으로 개선되지만 절대 성능은 보통 |
| `S3` | `label_next_rank_drop` | 0.938996 | 0.924781 | +0.014215 | 분리 학습 적용 후보 |
| `S3_ACCEL_V01` | `label_next_rank_drop` | 0.903580 | 0.870584 | +0.032996 | 분리 학습 적용 후보 |
| `T-STOCK-V01` | `label_next_rank_upgrade_3_retained` | 0.839573 | 0.852912 | -0.013339 | pooled 유지 또는 별도 feature 보강 필요 |

Implication:

- 무조건 model-specific으로 갈 필요는 없다.
- 1차 적용 후보는 `S3`, `S3_ACCEL_V01`, S family rank-up label이다.
- I/T는 pooled model이 더 강하므로 현재는 pooled 유지가 낫다.
- S2는 개선 폭은 크지만 절대 AUC가 낮아 shadow 관찰용으로만 둔다.

## AI Score Feature Combination

2026-05-10에 `하락위험예측AI`, `주가수준평가AI` score를 후보순위조정AI feature에 결합하는 실험을 추가했다.

Feature mode:

- `BASE`: 기존 후보/가격/재무/QM feature
- `AI_SCORE_SNAPSHOT`: 2026-05-08 current AI score snapshot을 추가

추가한 주요 feature:

- `downside_risk_prob`
- `downside_risk_tag`
- `valuation_ai_score`
- `valuation_predicted_excess_return_12m`
- `valuation_current_valuation_percentile`
- `valuation_expected_return_score`
- `valuation_growth_quality_score`
- `valuation_champion_score`
- `valuation_challenger_score`
- `valuation_risk_score`
- `valuation_risk_tag`

주의:

- `AI_SCORE_SNAPSHOT`은 현재 시점 AI score를 과거 rank-change row에 붙인 stress test다.
- 따라서 이것은 leakage-free historical backtest가 아니다.
- 운영 채택 전에는 as-of별 historical AI score 재생성이 필요하다.

2026-05-08 기준 결과:

| segment | best AI-score lift label | BASE AUC | AI-score AUC | lift | note |
|---|---|---:|---:|---:|---|
| I family | `label_next_rank_upgrade_3_retained` | 0.877551 | 0.881268 | +0.003717 | 소폭 개선 |
| T family | `label_next_rank_downgrade_3_retained` | 0.551702 | 0.565319 | +0.013617 | 하락 label 보강 가능성 |
| `S2` | `label_next_rank_downgrade_3_retained` | 0.508065 | 0.641862 | +0.133797 | 개선폭 큼, 단 절대 성능은 보통 |
| `S3` | `label_next_rank_upgrade_3_retained` | 0.771659 | 0.772585 | +0.000926 | 효과 거의 없음 |
| `S3_ACCEL_V01` | `label_next_rank_upgrade_3_retained` | 0.723190 | 0.724885 | +0.001695 | 효과 거의 없음 |
| `S2_PIT_V01` | `label_next_rank_drop` | 0.623512 | 0.602679 | -0.020833 | 악화 |

Implication:

- AI score feature는 전체적으로 결정적 개선은 아니다.
- `S3`, `S3_ACCEL_V01`의 주력 label은 여전히 BASE model-specific `drop`이 우세하다.
- `S2`, `T-STOCK` 하락/주의 label에는 보조 feature로 실험 가치가 있다.
- 다음 단계는 historical AI score snapshot을 as-of별로 재생성해 leakage-free ablation을 다시 돌리는 것이다.

## Recent Weighting

2026-05-10에 최근 1~2년 train sample 가중 실험을 추가했다.

Weight modes:

- `none`: 무가중
- `recent_1y_x3`: train window 내 최근 1년 sample 3배 가중
- `recent_2y_x2`: train window 내 최근 2년 sample 2배 가중
- `recent_2y_x3`: train window 내 최근 2년 sample 3배 가중

주의:

- 가중은 train window 내부에만 적용한다.
- valid window는 기존과 동일하게 유지한다.

2026-05-08 기준 결과:

| segment | label | best weight | AUC | base AUC | lift |
|---|---|---|---:|---:|---:|
| I | `label_next_rank_upgrade_3_retained` | `recent_1y_x3` | 0.881400 | 0.877551 | +0.003849 |
| S | `label_next_rank_upgrade_5` | `none` | 0.871323 | 0.871323 | 0.000000 |
| T | `label_next_rank_upgrade_3_retained` | `recent_1y_x3` | 0.846154 | 0.839573 | +0.006581 |
| `S2` | `label_next_rank_upgrade_3_retained` | `recent_2y_x2` | 0.675190 | 0.660186 | +0.015004 |
| `S3` | `label_next_rank_drop` | `recent_1y_x3` | 0.942015 | 0.938996 | +0.003019 |
| `S3_ACCEL_V01` | `label_next_rank_drop` | `recent_1y_x3` | 0.909235 | 0.903580 | +0.005655 |
| `S3_CORE2` | `label_next_rank_upgrade_5` | `recent_1y_x3` | 0.973046 | 0.970350 | +0.002696 |
| `T-STOCK-V01` | `label_next_rank_upgrade_3_retained` | `recent_1y_x3` | 0.846154 | 0.839573 | +0.006581 |

Implication:

- recent weighting은 대체로 소폭 개선이다.
- 가장 일관적인 개선은 `recent_1y_x3`에서 나타났다.
- `S` family rank-up label은 무가중이 가장 좋으므로 전체 S family에는 recent weighting을 일괄 적용하지 않는다.
- `S3`, `S3_ACCEL_V01`, `T-STOCK-V01`, I rank-up에는 recent weighting을 shadow 후보로 둘 수 있다.

Experiment outputs:

- `D:\Quant\scripts\run_candidate_rank_delta_recent_weight_experiment.py`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_recent_weight_experiment_YYYYMMDD.csv`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_recent_weight_best_YYYYMMDD.csv`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_recent_weight_experiment_YYYYMMDD.md`

## Split Operation: Drop Head And Retained Rank-Change Head

2026-05-10에 운영 builder를 split-head 구조로 변경했다.

변경 전:

- `label_rank_upgrade_1m`
- `label_rank_downgrade_1m`
- `rank_delta_score = rank_upgrade_prob - rank_downgrade_prob`

변경 후:

- `drop` head: `label_next_rank_drop`
- `retained_upgrade` head: `label_next_rank_upgrade_3_retained`
- `retained_downgrade` head: `label_next_rank_downgrade_3_retained`
- `retained_rank_change_score = retained_rank_upgrade_prob - retained_rank_downgrade_prob`
- `rank_delta_score = (1 - rank_drop_prob) * retained_rank_change_score`

Threshold:

| tag | rule |
|---|---|
| `rank_drop_candidate` | `rank_drop_prob >= 0.70` |
| `rank_drop_watch` | `0.50 <= rank_drop_prob < 0.70` |
| `rank_upgrade_candidate` | `retained_rank_change_score >= 0.25` and `rank_drop_prob < 0.50` |
| `rank_upgrade_watch` | `0.10 <= retained_rank_change_score < 0.25` and `rank_drop_prob < 0.50` |
| `rank_hold` | `-0.10 < retained_rank_change_score < 0.10` and `rank_drop_prob < 0.50` |
| `rank_downgrade_watch` | `-0.25 < retained_rank_change_score <= -0.10` and `rank_drop_prob < 0.50` |
| `rank_downgrade_candidate` | `retained_rank_change_score <= -0.25` and `rank_drop_prob < 0.50` |

2026-05-08 builder result:

| head | label | AUC | top30 label rate |
|---|---|---:|---:|
| drop | `label_next_rank_drop` | 0.869477 | 0.933333 |
| retained_upgrade | `label_next_rank_upgrade_3_retained` | 0.839054 | 0.300000 |
| retained_downgrade | `label_next_rank_downgrade_3_retained` | 0.847066 | 1.000000 |

2026-05-08 current decision counts:

| tag | count |
|---|---:|
| `rank_drop_candidate` | 40 |
| `rank_drop_watch` | 36 |
| `rank_upgrade_candidate` | 30 |
| `rank_upgrade_watch` | 10 |
| `rank_hold` | 50 |
| `rank_downgrade_watch` | 9 |
| `rank_downgrade_candidate` | 52 |

Operational note:

- `drop`은 “다음 리밸런싱 후보군 편출 가능성”이다.
- `retained_upgrade`/`retained_downgrade`는 편출되지 않고 남아 있는 후보 안에서 순위 변화 가능성을 본다.
- 따라서 admin 화면에서는 drop tag와 retained rank-change tag를 동일한 의미의 매수/매도 신호로 섞지 않는다.

## Tags

| tag | rule | meaning |
|---|---:|---|
| `rank_upgrade_candidate` | score >= 0.25 | 승격 후보 |
| `rank_upgrade_watch` | score >= 0.10 | 승격 관찰 |
| `rank_hold` | -0.10 < score < 0.10 | 유지 |
| `rank_downgrade_watch` | score <= -0.10 | 강등 관찰 |
| `rank_downgrade_candidate` | score <= -0.25 | 강등 후보 |

## Outputs

- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_ai_current_scores_YYYYMMDD.csv`
- `D:\Quant\reports\candidate_rank_delta_ai_v01\candidate_rank_delta_ai_eval_YYYYMMDD.json`
- `D:\Quant\service_platform\web\admin_data\current\candidate_rank_delta_ai_current.json`
- `D:\Quant\data\models\candidate_rank_delta_ai\AI-CANDIDATE-RANK-DELTA-V01_YYYYMMDD_001.joblib`

## Operating Rule

초기에는 admin-only shadow다.

실제 S/T/I/C 점수 보정, 후보 제외, public 추천 반영은 live shadow 검증 이후 판단한다.
