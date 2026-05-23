# AI-THEME-PERSISTENCE-V01 Design - 2026-05-11

## Identity

| item | value |
|---|---|
| model_code | `AI-THEME-PERSISTENCE-V01` |
| 한글명 | 테마지속성AI |
| role | theme persistence shadow |
| target | Quant theme bucket |
| operating mode | admin-only shadow |

## Purpose

`테마지속성AI`는 현재 강한 테마가 다음 리밸런싱/1개월 구간에서도 상위 테마로 유지될 가능성과, 순위가 둔화될 위험을 관찰한다.

이 모델은 개별 종목 매수/매도 모델이 아니다.

용도:

- S/T/I/C 후보의 theme overlay
- 테마 추종 후보의 지속성 확인
- 테마 과열/둔화 관찰
- 향후 Meta AI의 theme specialist score로 활용

## Data

Primary input:

- `D:\QuantMarket\service_platform\ai_training\market_context\current\theme_context_daily_quant_bucket_current.csv`

Main features:

- `theme_ret_1w`
- `theme_ret_1m`
- `theme_ret_3m`
- `theme_momentum_score`
- `theme_rotation_score`
- `theme_persistence_days`
- `theme_breadth_positive_ratio`
- `theme_above_sma60_ratio`
- `theme_trading_value_expansion_ratio`
- `theme_concentration_score`
- `leading_theme_rank`
- `mapping_confidence`

## Labels

20 trading sessions ahead 기준.

Continue label:

- `label_theme_continue_1m`
- future `leading_theme_rank <= 5`

Fade label:

- `label_theme_fade_1m`
- future leading theme rank worsens by 3+

Score:

`theme_persistence_score = theme_continue_prob - theme_fade_prob`

## 2026-05-08 Baseline Result

| head | label | AUC | top30 label rate |
|---|---|---:|---:|
| continue | `label_theme_continue_1m` | 0.714944 | 1.000000 |
| fade | `label_theme_fade_1m` | 0.772875 | 0.366667 |

Current tag counts:

| tag | count |
|---|---:|
| `theme_persist_strong` | 3 |
| `theme_persist_watch` | 3 |
| `theme_neutral` | 9 |
| `theme_fade_watch` | 2 |

## QM Market/Risk/Flow Feature Experiment

2026-05-11에 QM market/risk/flow context 결합 실험을 진행했다.

Feature modes:

- `BASE`: theme context only
- `QM_MARKET_RISK_FLOW`: theme context + market/risk/flow context

결과:

| feature mode | label | AUC | note |
|---|---|---:|---|
| `BASE` | `fade_rank_worse3` | 0.773228 | best |
| `QM_MARKET_RISK_FLOW` | `fade_rank_worse3` | 0.772159 | 소폭 악화 |
| `BASE` | `continue_top5` | 0.715410 | best |
| `QM_MARKET_RISK_FLOW` | `continue_top5` | 0.708848 | 악화 |

판단:

- market/risk/flow context는 현재 테마 지속성 AUC를 높이지 못했다.
- 운영 builder에는 아직 반영하지 않고 `BASE` feature mode를 유지한다.
- 다음 개선 후보는 `rotation acceleration`, `rank acceleration`, `volume expansion acceleration` 등 테마 자체의 변화속도 feature다.

## Rotation Acceleration Feature Experiment

2026-05-11에 테마 자체 변화속도 feature를 추가해 실험했다.

추가 feature:

- `theme_momentum_score_delta_5d`
- `theme_momentum_score_delta_10d`
- `theme_rotation_score_delta_5d`
- `theme_rotation_score_delta_10d`
- `theme_ret_1w_delta_5d`
- `theme_ret_1m_delta_5d`
- `theme_breadth_positive_ratio_delta_5d`
- `theme_above_sma60_ratio_delta_5d`
- `theme_trading_value_expansion_ratio_delta_5d`
- `leading_theme_rank_improvement_5d`
- `theme_momentum_rotation_accel_5d`
- `theme_participation_accel_5d`

결과:

| feature mode | label | AUC | top30 label rate | note |
|---|---|---:|---:|---|
| `BASE` | `fade_rank_worse3` | 0.773228 | 0.333333 | best AUC |
| `ACCELERATION` | `fade_rank_worse3` | 0.772040 | 0.433333 | top30 hit은 개선, AUC는 소폭 악화 |
| `BASE` | `continue_top5` | 0.715410 | 0.966667 | best AUC |
| `ACCELERATION` | `continue_top5` | 0.708740 | 0.966667 | 악화 |

판단:

- acceleration feature는 AUC를 높이지 못했다.
- `fade_rank_worse3`의 top30 label rate는 개선됐지만 전체 분리력은 소폭 악화됐다.
- 운영 builder에는 반영하지 않고 `BASE` feature mode를 유지한다.
- 다음 개선 후보는 테마 내부 종목 품질 feature다.

## Theme Internal Stock Quality Feature Experiment

2026-05-11에 테마 내부 편입 종목 품질 feature를 추가해 실험했다.

입력:

- `reports\ai_overlay_v01\ai_overlay_training_mart_20260508.csv`

추가 feature:

- 테마별 후보 종목 수, 후보 row 수, scope/model 수
- 테마별 평균 rank, score, weight, overlap count
- 테마별 평균 최근 수익률, 변동성, MDD, 거래대금
- 테마별 평균 growth score, theme support, confidence
- 테마별 평균 외국인/기관 수급, DART 이벤트 지표

결과:

| feature mode | label | AUC | top30 label rate | note |
|---|---|---:|---:|---|
| `BASE` | `fade_rank_worse3` | 0.773228 | 0.333333 | best AUC |
| `THEME_QUALITY` | `fade_rank_worse3` | 0.772837 | 0.400000 | top30 hit은 개선, AUC는 소폭 악화 |
| `ACCELERATION_THEME_QUALITY` | `fade_rank_worse3` | 0.772778 | 0.400000 | AUC는 소폭 악화 |
| `BASE` | `continue_top5` | 0.715410 | 0.966667 | best AUC |
| `THEME_QUALITY` | `continue_top5` | 0.715132 | 1.000000 | top30 hit은 개선, AUC는 거의 동일 |
| `ACCELERATION_THEME_QUALITY` | `continue_top5` | 0.709524 | 0.966667 | 악화 |

판단:

- 테마 내부 종목 품질 feature는 AUC를 높이지 못했다.
- 다만 top30 hit rate 개선 신호는 있어, Meta AI나 top-k ranking 보조 feature로는 재검토 여지가 있다.
- 운영 builder에는 반영하지 않고 `BASE` feature mode를 유지한다.
- 다음 개선 후보는 테마 수명/age regime 또는 label horizon 차등화다.

## Current Interpretation

2026-05-08 기준 가장 강한 지속 테마:

- `semiconductor_tech`
- `electronics_it`
- `software_platform`

Fade watch:

- `battery_chemical`
- `energy_utility_infra`

## Outputs

- `D:\Quant\scripts\build_theme_persistence_ai_v01.py`
- `D:\Quant\scripts\run_theme_persistence_label_ablation.py`
- `D:\Quant\reports\theme_persistence_ai_v01\theme_persistence_ai_current_scores_YYYYMMDD.csv`
- `D:\Quant\reports\theme_persistence_ai_v01\theme_persistence_ai_eval_YYYYMMDD.json`
- `D:\Quant\service_platform\web\admin_data\current\theme_persistence_ai_current.json`

## Operating Rule

초기에는 admin-only shadow다.

`theme_persist_strong`은 테마가 계속 강할 가능성을 뜻하지만, 자동 매수 신호가 아니다.

`theme_fade_watch`는 테마 순위 둔화 가능성을 뜻하지만, 자동 매도 신호가 아니다.

S/T/I/C 후보 및 향후 Meta AI에 theme specialist feature로 제공한다.
