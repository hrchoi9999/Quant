# ETF 전용 데이터 보강

## 목적

ETF AI를 주식형 가격/거래대금 feature만으로 학습하지 않고, ETF 고유 데이터까지 반영할 수 있도록 데이터 파이프라인을 확장한다.

ETF 전용 모델에서는 아래 데이터가 중요하다.

- NAV
- 괴리율/premium-discount
- 순자산/AUM
- 시가총액
- 상장좌수
- 기초지수명
- 기초지수 수익률
- ETF 수익률과 기초지수 수익률의 일간 tracking gap

## 추가 수집 데이터

KRX ETF 일별 endpoint(`/etp/etf_bydd_trd`)에서 아래 필드를 확인하고 Quant DB에 반영했다.

| 구분 | 원천 필드 | Quant 저장 필드 |
|---|---|---|
| NAV | `NAV` | `nav` |
| 괴리율 | `TDD_CLSPRC / NAV - 1` | `premium_discount` |
| 괴리율 절대값 | abs(`premium_discount`) | `premium_discount_abs` |
| 괴리율 품질 flag | abs 괴리율 구간화 | `premium_discount_quality_flag` |
| 순자산/AUM | `INVSTASST_NETASST_TOTAMT` | `aum` |
| AUM log | log1p(`aum`) | `aum_log` |
| 시가총액 | `MKTCAP` | `mcap` |
| 상장좌수 | `LIST_SHRS` | `list_shares` |
| 기초지수명 | `IDX_IND_NM` | `underlying_index_name` |
| 기초지수 | `OBJ_STKPRC_IDX` | `underlying_index_level` |
| 기초지수 등락률 | `FLUC_RT_IDX` | `underlying_index_return_pct` |
| ETF 등락률 | `FLUC_RT` | `etf_return_pct` |
| 일간 tracking gap | ETF 등락률 - 지수 등락률 | `daily_tracking_gap_pct` |

## 구현 내용

1. KRX ETF parser 보강
   - `D:\Quant\src\collectors\krx_openapi.py`
   - `fetch_etf_daily()`가 ETF 전용 필드를 같이 반환하도록 수정

2. ETF 전용 지표 적재 스크립트 추가
   - `D:\Quant\scripts\fetch_etf_daily_metrics_krx.py`
   - 저장 테이블: `price.db::etf_daily_metrics`

3. ETF AI mart join 반영
   - `D:\Quant\scripts\run_etf_ai_label_ablation.py`
   - `etf_metric_*` prefix로 AI mart에 반영

4. ETF 역할배분 실험 feature 후보 반영
   - `D:\Quant\scripts\run_etf_role_allocation_ai_v01_experiment.py`
   - 역할 sleeve feature에 premium/AUM/tracking gap 계열 추가

## 백필 결과

적재 구간: `2017-01-02 ~ 2026-05-08`

| 항목 | 값 |
|---|---:|
| total rows | 1,246,307 |
| distinct dates | 2,440 |
| NAV rows | 1,167,910 |
| AUM rows | 1,167,910 |
| underlying index name rows | 1,246,307 |
| tracking gap rows | 1,163,115 |

연도별 coverage:

| year | rows | NAV rows | AUM rows |
|---|---:|---:|---:|
| 2017 | 60,665 | 56,657 | 56,657 |
| 2018 | 76,517 | 71,512 | 71,512 |
| 2019 | 87,572 | 82,545 | 82,545 |
| 2020 | 94,955 | 89,867 | 89,867 |
| 2021 | 110,475 | 104,981 | 104,981 |
| 2022 | 134,130 | 126,980 | 126,980 |
| 2023 | 166,913 | 157,208 | 157,208 |
| 2024 | 206,622 | 192,420 | 192,420 |
| 2025 | 228,050 | 211,450 | 211,450 |
| 2026 | 80,408 | 74,290 | 74,290 |

괴리율 품질 플래그:

| flag | count | 의미 |
|---|---:|---|
| `normal` | 1,077,105 | abs premium < 1% |
| `watch` | 79,738 | 1% 이상 3% 미만 |
| `missing` | 78,397 | NAV 결측 |
| `wide` | 9,765 | 3% 이상 10% 미만 |
| `extreme` | 1,302 | 10% 이상 |

`extreme`은 러시아 ETF처럼 NAV가 비정상적으로 작게 표시되는 특수 상품에서 발생한다. 학습에는 원천값을 보존하되 `premium_discount_quality_flag`를 반드시 같이 사용해야 한다.

## AI mart 반영 확인

대상 mart:

`D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_market_context_mart_20260508.csv`

추가된 `etf_metric_*` 컬럼:

- `etf_metric_nav`
- `etf_metric_premium_discount`
- `etf_metric_premium_discount_abs`
- `etf_metric_premium_discount_quality_flag`
- `etf_metric_aum`
- `etf_metric_aum_log`
- `etf_metric_mcap`
- `etf_metric_list_shares`
- `etf_metric_underlying_index_name`
- `etf_metric_underlying_index_level`
- `etf_metric_underlying_index_return_pct`
- `etf_metric_etf_return_pct`
- `etf_metric_daily_tracking_gap_pct`
- `etf_metric_daily_tracking_gap_abs_pct`
- `etf_metric_mcap_to_aum`

mart coverage:

| 구분 | 값 |
|---|---:|
| mart rows | 8,837 |
| NAV joined rows | 8,837 |
| latest rows, 2026-05-08 | 200 |
| latest NAV joined rows | 200 |

연도별 mart NAV coverage는 2017년부터 2026년까지 모두 채워졌다.

## 재실험 결과

### Label Ablation

ETF 전용 지표를 학습 구간까지 백필한 뒤 label ablation을 재실행했다.

| 항목 | 이전 | 백필 후 |
|---|---:|---:|
| best label | `label_tactical_2w_pos` | `label_tactical_2w_pos` |
| best feature mode | `MARKET_CONTEXT` | `MARKET_CONTEXT` |
| numeric features | 48 | 61 |
| categorical features | 8 | 10 |
| AUC | 0.589858 | 0.584345 |

판단:

- ETF 전용 지표는 정상적으로 feature set에 들어갔다.
- 단순 추가만으로는 AUC가 개선되지 않았다.
- 현재 best는 여전히 시장국면/context 기반 timing label이다.

### Role Allocation

기준 실험:

- `top3`
- `horizon_v2_top1`
- `score_diff`
- `risk_adjusted`

| 항목 | 이전 | 백필 후 |
|---|---:|---:|
| AUC | 0.543034 | 0.511817 |
| AI top1 1M return | 5.34% | -0.40% |
| AI top1 risk adj | 3.29% | -3.54% |
| AI top1 worst 1M | -11.52% | -35.13% |

판단:

- ETF 전용 지표를 sleeve feature로 단순 투입하면 역할 선택 모델에는 노이즈가 섞인다.
- 특히 괴리율/AUM/기초지수명은 역할별로 의미가 다르므로 동일 feature로 직접 투입하면 부작용이 크다.
- 현 상태에서는 role allocation 운영 baseline에는 ETF 전용 raw metric을 직접 쓰지 않는 것이 낫다.

### Role Weight Template

비중 템플릿 모델 결과는 유지됐다.

| 항목 | 결과 |
|---|---:|
| AUC best template | 0.851117 |
| top-pick hit rate | 51.85% |
| AI top1 template avg 1M return | 4.02% |
| AI top1 template risk adj | 2.09% |
| mode default template avg 1M return | 2.35% |
| mode default template risk adj | 0.94% |

판단:

- 비중 템플릿 선택은 여전히 학습 가능성이 높다.
- ETF 전용 raw metric 추가보다 시장모드/역할수익률 기반 템플릿 선택 구조가 더 안정적이다.

## 결론

ETF 전용 데이터 보강은 완료됐다.

다만 현재 실험상 ETF 전용 지표는 raw feature로 바로 넣기보다 아래 방식으로 재가공해야 한다.

1. quality gate
   - `premium_discount_quality_flag in ('wide', 'extreme')` 상품은 role sleeve 후보에서 제외하거나 감점

2. liquidity gate
   - AUM 하위 구간 ETF는 sleeve 편입 제한

3. role-aware transform
   - core/sector/style은 AUM과 tracking gap 안정성 중시
   - hedge/inverse는 괴리율과 tracking gap을 더 강하게 감점
   - leverage는 AUM보다 단기 tracking gap과 괴리율 안정성 중시

4. underlying index category 정규화
   - `underlying_index_name` 원문을 그대로 category로 쓰지 말고 국가/자산/테마/레버리지/환노출 taxonomy로 변환

## 다음 단계

1. ETF quality gate ablation
   - wide/extreme 괴리 ETF 제외
   - AUM 하위 ETF 제외
   - tracking gap 상위 ETF 제외

2. ETF role-aware feature 재설계
   - raw metric 직접 투입 중단
   - 역할별 품질 score로 변환 후 투입

3. ETF universe taxonomy 구축
   - 기초지수명 기반 country/asset/theme/hedge/leverage 분류

4. 비중 템플릿 모델 유지 관찰
   - 현 시점에서는 `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01`이 더 안정적인 후보다.
