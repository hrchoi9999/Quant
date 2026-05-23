# I-series Stock V01 Research Plan

## Purpose

`I-STOCK-V01`은 일목균형표, RSI, MACD를 이용해 주식 universe 400 종목의 기술적 매수/보유/매도 타이밍을 검증하는 연구 모델이다.

핵심 가설:

- 상승 종목은 상승 시작 전후로 일목 구조가 정배열 상태가 된다.
- 상승이 유지될수록 가격과 구름대, 전환선과 기준선, 선행스팬1과 선행스팬2의 이격도가 유지 또는 확대된다.
- 이격도 축소와 MACD/RSI 약화는 이후 수익률 둔화 또는 매도 경고로 쓸 수 있다.

## No-lookahead Definition

일목균형표는 차트상 선행/후행 표시가 있으므로, 백테스트에서는 의사결정일에 이미 알 수 있는 값만 사용한다.

사용 지표:

- `conversion_9`: 최근 9일 고가/저가 중간값
- `base_26`: 최근 26일 고가/저가 중간값
- `span1_raw`: `(conversion_9 + base_26) / 2`
- `span2_raw`: 최근 52일 고가/저가 중간값
- `lagging_strength_26`: 현재 종가 / 26거래일 전 종가 - 1
- `gap_price_cloud`: 현재 종가 / max(span1_raw, span2_raw) - 1
- `gap_span1_span2`: span1_raw / span2_raw - 1
- `gap_conversion_base`: conversion_9 / base_26 - 1
- `gap_price_cloud_expansion_5d`, `gap_price_cloud_expansion_10d`
- `gap_stability_10d`
- `RSI14`
- `MACD 12/26/9`

## Signal Draft

`BUY`:

- `i_score >= 75`
- 종가가 구름대 위
- 전환선 > 기준선
- span1_raw > span2_raw
- 현재 종가가 26거래일 전 종가보다 높음

`HOLD`:

- `i_score >= 60`
- 종가가 구름대 위
- 최근 10거래일 중 구름대 위 유지 비율이 60% 이상

`EXIT_WATCH`:

- 구름대 위에 있으나 최근 20일 이격 고점 대비 이격도가 크게 축소
- 또는 MACD histogram이 음수 전환/약화

`SELL`:

- 종가가 구름대 아래
- 또는 26거래일 전 종가 대비 약세
- 또는 RSI 45 미만이며 MACD histogram 음수

## 2026-04-29 First Backtest

공통 조건:

- 대상: `universe_mix_top400_latest_priceready.csv`
- 시작: 2017-01-01
- 종료: 2026-04-29
- 리밸런싱: 주간, 수요일 기준
- 비용: fee 5bps + slippage 5bps
- 기본 포트폴리오: I-score 상위 BUY/HOLD 후보 equal weight

| config | CAGR | total return | MDD | Sharpe | latest holdings |
| --- | ---: | ---: | ---: | ---: | ---: |
| top10 / score >= 65 | 8.48% | 113.40% | -58.55% | 0.56 | 10 |
| top20 / score >= 65 | 16.51% | 315.21% | -48.05% | 0.79 | 20 |
| top20 / score >= 70 | 16.43% | 312.33% | -48.53% | 0.80 | 20 |
| top20 / score >= 75 | 16.36% | 310.27% | -47.27% | 0.78 | 20 |
| top30 / score >= 65 | 22.86% | 580.31% | -39.98% | 1.02 | 30 |

Initial read:

- I-score는 소수 종목 초집중보다 넓은 추세 바스켓에서 더 안정적으로 작동했다.
- 독립 모델로도 가능성은 있으나 MDD가 아직 커서 운영형으로 확정하기에는 이르다.
- `top30 / score >= 65`가 1차 후보 설정으로 가장 양호하다.

## Breadth/Regime Gate Test

목적:

- I-score 종목선정력은 유지하되, 시장 전체 breadth가 약한 구간에서는 포트폴리오 현금 비중을 늘려 MDD를 낮출 수 있는지 확인한다.
- 게이트는 종목 점수를 바꾸지 않고, 주간 리밸런싱 시점의 목표 노출만 조절한다.

게이트 입력:

- universe 내 `가격 > 구름대` 비율
- universe 내 `BUY/HOLD` 비율
- universe의 `gap_price_cloud` 중앙값

설정:

- `conservative`: breadth와 BUY/HOLD 조건을 엄격하게 적용하며 현금 100% 구간을 많이 허용한다.
- `moderate`: 방어와 수익 기회를 절충한다.
- `aggressive`: 시장이 아주 약할 때만 노출을 줄이고 상승 구간 참여를 우선한다.

공통 조건:

- 대상: stock universe 400
- 기간: 2017-01-04 ~ 2026-04-29
- 포트폴리오: `top30 / score >= 65`
- 비용: fee 5bps + slippage 5bps

| regime mode | CAGR | total return | MDD | Sharpe | avg exposure | cash-only days |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 22.86% | 580.31% | -39.98% | 1.02 | 99.78% | 0.22% |
| conservative | 7.01% | 87.96% | -23.21% | 0.65 | 26.40% | 53.02% |
| moderate | 11.40% | 173.23% | -24.95% | 0.84 | 49.39% | 24.41% |
| aggressive | 17.99% | 367.03% | -29.30% | 0.99 | 78.30% | 7.54% |

초기 해석:

- regime gate는 MDD를 확실히 낮춘다.
- 보수형은 방어 효과는 크지만 현금 구간이 너무 많아 I-series의 상승 포착 장점을 크게 희석한다.
- 중도형은 MDD를 크게 줄이지만 CAGR 하락도 크다.
- 공격형은 CAGR을 어느 정도 유지하면서 MDD를 약 `-39.98%`에서 `-29.30%`로 낮춰 1차 운영 후보로 가장 균형이 좋다.
- 다음 단계에서는 공격형을 기준으로 하되, 폭락 구간에서만 더 빨리 현금화하는 crash gate를 추가 테스트한다.

## Liquidity Score / Conversion Filter Test

목적:

- 거래대금은 상승초기 발굴에는 변별력이 낮고, 오히려 상투/매도 확인 변수에 더 가까울 수 있다는 가설을 확인한다.
- `전환선 > 기준선`은 상승 확인에는 유용하지만 상승초기 포착에는 늦을 수 있으므로, BUY 필수조건에서 제거했을 때의 변화를 확인한다.

주의:

- 이번 테스트에서 거래대금은 I-score 가산점에서만 제거했다. universe의 최소 거래가능성 관리는 별도 품질 필터로 유지하는 것이 맞다.
- `전환선 > 기준선`은 BUY 필수조건에서 제거했다. 다만 `전환선/기준선` 관련 점수 성분은 아직 남겨 두었으므로, 완전 제거 실험은 별도 challenger로 진행해야 한다.

공통 조건:

- 대상: stock universe 400
- 기간: 2017-01-04 ~ 2026-04-29
- 포트폴리오: `top30 / score >= 65`
- 비용: fee 5bps + slippage 5bps

### No Regime Gate

| variant | CAGR | total return | MDD | Sharpe | latest holdings |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 22.86% | 580.31% | -39.98% | 1.02 | 30 |
| no liquidity score | 22.37% | 555.42% | -40.86% | 1.00 | 30 |
| no conversion BUY filter | 23.03% | 589.08% | -38.82% | 1.02 | 30 |
| no liquidity + no conversion BUY filter | 21.91% | 533.09% | -42.72% | 0.99 | 30 |

### Aggressive Regime Gate

| variant | CAGR | total return | MDD | Sharpe | latest holdings |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 17.99% | 367.03% | -29.30% | 0.99 | 30 |
| no liquidity score | 17.84% | 361.45% | -28.40% | 0.98 | 30 |
| no conversion BUY filter | 18.47% | 384.69% | -28.57% | 1.01 | 30 |
| no liquidity + no conversion BUY filter | 17.77% | 358.98% | -27.27% | 0.99 | 30 |

초기 해석:

- 거래대금 점수 제거는 최신 보유 30종목을 바꾸지는 않았고, 장기 성과는 소폭 낮아졌다.
- 하지만 aggressive gate와 결합하면 MDD는 조금 낮아져, 거래대금은 매수 발굴보다 위험/매도 관찰 변수로 재배치하는 것이 합리적이다.
- `전환선 > 기준선`을 BUY 필수조건에서 제거하면 base와 aggressive gate 양쪽에서 성과가 소폭 개선됐다.
- 따라서 다음 I-series 후보는 `전환선 > 기준선`을 필수조건에서 제외하고, 거래대금은 매수 점수에서 제외하거나 매우 낮은 비중으로 두는 방향이 타당하다.

## Early Breakout Profile Test

목적:

- 기존 I-STOCK-V01은 상승 확인 후 추세 탑승형에 가깝다.
- early profile은 바닥권/초기 상승 구간에서 `선행스팬1 > 선행스팬2`가 아직 정배열이 아닐 수 있다는 가정을 반영한다.
- 따라서 선행스팬1/2 정배열은 BUY 필수조건에서 제외하고, 낮은 보조점수만 부여한다.

early profile 핵심 변수:

- 구름대 신규 돌파: 최근 10일 중 구름 위 체류가 낮다가 현재 구름 위로 진입
- 구름대 재진입: 5거래일 전 구름 아래/근처에서 현재 구름 위로 회복
- 후행 강도 개선: 26거래일 전 대비 수익률이 최근 10일 동안 개선
- MACD histogram 회복: histogram 개선 및 음수권 회복/양수 전환
- RSI 50 회복: RSI가 50선을 회복
- 20일/40일 박스권 고점 돌파
- 눌림 후 재상승: 구름대 근처 눌림 이후 5일선 회복

제거/완화:

- 거래대금은 I-score 가산점에서 제거한다.
- `전환선 > 기준선`은 BUY 필수조건에서 제거한다.
- `선행스팬1 > 선행스팬2`는 BUY 필수조건에서 제거하고 낮은 보조점수만 부여한다.

공통 조건:

- 대상: stock universe 400
- 기간: 2017-01-04 ~ 2026-04-29
- 비용: fee 5bps + slippage 5bps

| variant | CAGR | total return | MDD | Sharpe | avg exposure | latest holdings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base top30 / score >= 65 | 22.86% | 580.31% | -39.98% | 1.02 | 99.78% | 30 |
| base + aggressive gate + no conversion BUY filter | 18.47% | 384.69% | -28.57% | 1.01 | 78.61% | 30 |
| early top30 / score >= 65 | 31.14% | 1,149.37% | -33.87% | 1.35 | 99.78% | 30 |
| early top30 / score >= 65 + aggressive gate | 21.13% | 496.20% | -28.48% | 1.29 | 77.88% | 30 |
| early top20 / score >= 65 + aggressive gate | 20.52% | 468.91% | -23.89% | 1.20 | 77.88% | 20 |
| early top30 / score >= 70 + aggressive gate | 20.95% | 487.88% | -28.48% | 1.26 | 77.88% | 30 |

초기 해석:

- early profile은 기존 base보다 CAGR, Sharpe, MDD가 모두 개선됐다.
- aggressive gate를 붙이면 CAGR은 낮아지지만 MDD가 `-28.48%`까지 낮아지고 Sharpe가 `1.29`로 유지된다.
- top20은 CAGR은 조금 낮지만 MDD가 `-23.89%`까지 내려가므로 운영형 안정화 후보로 볼 수 있다.
- 최신 2026-04-29 기준 early top30은 기존 base top30과 3종목만 겹친다. 따라서 early profile은 기존 모델의 단순 개선판이 아니라 별도 성격의 상승초기 발굴형 후보로 관리해야 한다.
- 다음 단계에서는 early profile을 `I-STOCK-EARLY-V01` 후보로 두고, 기간별/시장국면별 성과와 S/T 모델 overlay 효과를 검증한다.

## Strong Initial RSI Profile Test

목적:

- RSI를 단순 기준선 돌파가 아니라, 초기 회복 강도로 본다.
- 강한 초기 신호는 `RSI >= 42`, 최근 10거래일 RSI 상승폭 `+8p` 이상, MACD histogram 개선, 가격이 구름대 근처 또는 위로 회복한 상태로 정의한다.

핵심 조건:

- `rsi14 >= 42`
- `rsi14_delta_10d >= 8`
- `macd_hist_recovery = true`
- `gap_price_cloud >= -3%` 및 종가가 5일선 위
- 구름대 신규 돌파, 구름대 재진입, 20일 고점 돌파, 눌림 후 재상승, 또는 구름대 위 안착 중 하나 이상

공통 조건:

- 대상: stock universe 400
- 기간: 2017-01-04 ~ 2026-04-29
- 거래대금 점수 제거
- `전환선 > 기준선` BUY 필수조건 제거
- 비용: fee 5bps + slippage 5bps

| variant | CAGR | total return | MDD | Sharpe | avg exposure | latest holdings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base top30 / score >= 65 | 22.86% | 580.31% | -39.98% | 1.02 | 99.78% | 30 |
| early top30 / score >= 65 | 31.14% | 1,149.37% | -33.87% | 1.35 | 99.78% | 30 |
| early top30 / score >= 65 + aggressive gate | 21.13% | 496.20% | -28.48% | 1.29 | 77.88% | 30 |
| strong RSI top30 / score >= 65 | 36.21% | 1,678.78% | -26.57% | 1.50 | 99.78% | 30 |
| strong RSI top30 / score >= 65 + aggressive gate | 22.30% | 552.05% | -27.00% | 1.40 | 72.10% | 30 |
| strong RSI top20 / score >= 65 + aggressive gate | 22.58% | 566.17% | -28.62% | 1.35 | 72.10% | 20 |
| strong RSI top30 / score >= 70 + aggressive gate | 22.30% | 551.99% | -26.82% | 1.40 | 72.10% | 30 |

초기 해석:

- strong RSI profile은 현재까지의 I-series 실험 중 가장 강한 성과를 보였다.
- 특히 gate 없이도 MDD가 `-26.57%`로 낮아졌고, CAGR과 Sharpe가 모두 개선됐다.
- aggressive gate를 붙이면 수익률은 낮아지지만 MDD와 Sharpe가 안정적으로 유지된다.
- 최신 2026-04-29 기준 strong RSI top30은 기존 base top30과 4종목, early top30과 15종목만 겹친다.
- 다만 최신 후보 30개가 모두 `i_score=100`으로 포화되어 점수 변별력이 사라졌다. 따라서 신호 조건은 유망하지만, 운영형으로 쓰려면 점수 산식을 재스케일링해야 한다.
- 다음 단계에서는 strong RSI 조건을 유지하되, 점수 포화를 줄이기 위해 연속형 점수 비중을 늘리고 binary 가산점 비중을 낮춘 challenger를 만든다.

## Universe Raw/Rank Score Separation

목적:

- I-series를 top30 내부 순위가 아니라, 전체 stock universe 400개를 대상으로 하는 독립 발굴 모델로 정의한다.
- 점수 체계를 내부 계산용, universe 상대순위용, 표시용으로 분리한다.

정의:

- `i_raw_score`: 전체 universe 종목에 대해 계산한 uncapped 내부 점수
- `universe_rank_no`: 같은 날짜 universe 전체 기준 raw score 순위
- `universe_rank_score`: 같은 날짜 universe 전체 기준 percentile score
- `portfolio_rank_no`: 최종 편입 top N 내부 순번
- `i_score`: 0~100으로 제한한 display score

중요 원칙:

- `raw_score/rank_score`는 top30에 들어온 종목끼리 다시 계산하지 않는다.
- 모든 점수와 순위는 먼저 universe 400 전체 기준으로 계산한다.
- top30은 그 결과를 이용한 최종 포트폴리오 후보일 뿐이다.

공통 조건:

- 대상: stock universe 400
- 기간: 2017-01-04 ~ 2026-04-29
- 포트폴리오: top30 / display score >= 65
- selection score: `raw`
- 비용: fee 5bps + slippage 5bps

| profile | CAGR | total return | MDD | Sharpe | latest raw avg | latest universe rank avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base raw | 22.86% | 580.31% | -39.98% | 1.02 | 98.45 | 16.43 |
| early raw | 31.29% | 1,162.30% | -33.87% | 1.36 | 96.62 | 16.83 |
| strong RSI raw | 35.12% | 1,549.98% | -26.64% | 1.46 | 112.41 | 16.37 |
| base raw + aggressive gate | 17.99% | 367.03% | -29.30% | 0.99 | 98.45 | 16.43 |
| early raw + aggressive gate | 21.26% | 502.38% | -28.48% | 1.30 | 96.62 | 16.83 |
| strong RSI raw + aggressive gate | 21.36% | 507.03% | -30.57% | 1.34 | 112.41 | 16.37 |

최신 2026-04-29 top30 종목 겹침:

- base raw vs early raw: 3개
- base raw vs strong RSI raw: 0개
- early raw vs strong RSI raw: 22개

초기 해석:

- strong RSI raw는 기존 base와 종목 구성이 완전히 다르다.
- 따라서 strong RSI는 기존 I-STOCK-V01의 단순 튜닝이 아니라 별도 모델 후보로 보는 것이 맞다.
- early와 strong RSI는 상승초기형 계열 안에서 상당히 겹치므로, 둘을 모두 운영하기보다 strong RSI를 early challenger의 핵심 후보로 두는 것이 합리적이다.
- aggressive gate는 strong RSI의 CAGR을 낮추고 MDD 개선이 크지 않아, 현재 상태에서는 strong RSI 단독 또는 별도 crash gate가 더 적합할 수 있다.
- 다음 단계에서는 strong RSI raw를 기준으로 S-series/T-series/C-series 현행 종목과 overlay하고, 기존 모델 대비 추가 발굴 종목의 forward return을 검증한다.

## Strong RSI Raw vs S/T/C Overlay

저장 위치:

- Script: `D:\Quant\scripts\analyze_i_strong_rsi_stc_overlay.py`
- SQLite: `D:\Quant\data\db\i_series_research.db`
- `i_strong_rsi_stc_overlay_history`
- `i_strong_rsi_stc_overlay_summary`
- `i_strong_rsi_stc_overlay_latest`
- Report: `D:\Quant\reports\i_series_stock_v01\I_STRONG_RSI_STC_OVERLAY_20260429.md`

분석 방식:

- I strong RSI raw top30을 기존 S/T/C 모델별 종목과 주차별로 비교한다.
- 그룹은 `base_i_intersection`, `base_only`, `i_only`로 나눈다.
- 각 그룹의 1주, 4주, 8주, 12주 forward return과 승률을 비교한다.

최신 2026-04-29 겹침:

| model | intersection | base only | I only |
| --- | ---: | ---: | ---: |
| S2 | 3 | 27 | 27 |
| S2_PIT_V01 | 3 | 27 | 27 |
| S3 | 1 | 19 | 29 |
| S3_CORE2 | 1 | 19 | 29 |
| T-STOCK-V01 | 1 | 8 | 29 |

Historical forward return 주요 결과:

| model | group | avg 4w | avg 8w | avg 12w | win 4w |
| --- | --- | ---: | ---: | ---: | ---: |
| S2 | intersection | 2.92% | 5.70% | 6.76% | 49.29% |
| S2 | base only | 2.57% | 5.53% | 8.64% | 48.36% |
| S2 | I only | 3.13% | 6.03% | 8.69% | 49.37% |
| S3 | intersection | 2.55% | 5.02% | 7.85% | 46.49% |
| S3 | base only | 2.66% | 5.18% | 8.34% | 47.19% |
| S3 | I only | 2.59% | 4.51% | 6.40% | 48.87% |
| S3_CORE2 | intersection | 5.09% | 6.73% | 6.81% | 47.88% |
| S3_CORE2 | base only | 3.09% | 5.12% | 7.77% | 48.22% |
| S3_CORE2 | I only | 3.58% | 6.38% | 9.42% | 50.75% |
| S3_ACCEL_V01 | intersection | 3.99% | 7.18% | 10.17% | 49.10% |
| S3_ACCEL_V01 | base only | 3.89% | 7.35% | 11.10% | 49.42% |
| S3_ACCEL_V01 | I only | 2.42% | 4.23% | 6.07% | 48.63% |

초기 해석:

- S2 대비 I only는 4주/8주/12주 평균수익률이 모두 소폭 높다. I strong RSI는 S2가 놓친 후보를 보완하는 별도 발굴 모델 가능성이 있다.
- S3/S3_ACCEL 계열에서는 I only가 기존 모델 단독보다 우월하다고 보기 어렵다. 따라서 S3의 대체 모델보다는 별도 관찰 모델에 가깝다.
- S3_CORE2에서는 I only의 4주/8주/12주 성과와 4주 승률이 괜찮아 보완 신호로 볼 여지가 있다.
- 최신 기준 교집합이 S2 3개, S3/S3_CORE2 1개, T-STOCK 1개에 불과해, I strong RSI는 기존 모델의 단순 필터가 아니라 독립 발굴 모델 성격이 강하다.
- T-series와 C-series는 현재 이력 기간이 짧아 forward return 결론을 내리기 어렵다. 최소 4~8주 shadow tracking이 필요하다.

## Operational Shadow Setup

2026-05-04에 아래 1~3단계를 완료했다.

1. 모델명 고정:

- `I-STOCK-STRONG-RSI-V01`
- status: `shadow`
- 성격: stock universe 400 전체를 대상으로 한 상승초기 발굴형 독립 후보 모델

2. 점수 스키마 고정:

- `i_raw_score`: 내부 선별용 uncapped raw score
- `universe_rank_no`: 같은 날짜 universe 전체 기준 순위
- `universe_rank_score`: 같은 날짜 universe 전체 기준 percentile score
- `display_score`: 사용자/admin 표시용 0~100 capped score
- 원칙: top30 내부에서 점수를 재계산하지 않고, universe 전체 기준 점수를 먼저 산출한 뒤 top30을 선택한다.

3. shadow tracking DB/산출물 생성:

- Script: `D:\Quant\scripts\sync_i_series_shadow_operational.py`
- Operational DB: `D:\Quant\data\db\i_series_operational.db`
- Report: `D:\Quant\reports\i_series_stock_v01\operational_shadow\I_STOCK_STRONG_RSI_V01_SHADOW_20260429.md`

Operational DB tables:

- `is_meta_models`
- `is_score_schema`
- `is_candidates_latest`
- `is_candidates_history`
- `is_shadow_tracking_summary`
- `is_rolling_watchlist_latest`
- `is_rolling_watchlist_summary`
- `is_backtest_nav`
- `is_backtest_summary`
- `is_runs`

2026-04-29 적재 결과:

- latest candidates: 30
- history rows: 11,545
- rolling watchlist rows: 83
- rolling states: active 12, new 18, cooling 53

Shadow summary:

| bucket | obs | avg 4w | avg 8w | avg 12w | win 4w |
| --- | ---: | ---: | ---: | ---: | ---: |
| core | 4,670 | 2.80% | 4.89% | 6.66% | 48.51% |
| candidate | 6,875 | 2.42% | 4.29% | 6.40% | 48.86% |

초기 해석:

- core와 candidate 모두 4~12주 평균 forward return은 양호하다.
- core가 candidate보다 평균수익률은 높지만 승률은 큰 차이가 없다.
- 따라서 초기 운영에서는 `core`를 적극 관찰군, `candidate`를 보조 관찰군으로 분리하는 것이 적절하다.
- `active/new/cooling` rolling 상태를 유지하므로, 매주 종목이 바뀌어도 후보를 단절하지 않고 누적 관찰할 수 있다.

## Weekly Pipeline And Web Handoff

2026-05-04에 `I-STOCK-STRONG-RSI-V01`을 주간 Quant pipeline과 admin 웹 payload에 연결했다.

Pipeline:

- Wrapper: `D:\Quant\scripts\run_i_stock_strong_rsi_v01_shadow_refresh.py`
- Daily/weekly pipeline hook: `D:\Quant\src\quant_service\run_daily_quant_pipeline.py`
- 실행 위치: T-series shadow refresh 이후, ingest/publish 이전
- 기본 동작: 실행 포함
- skip option: `--skip-iseries-shadow`

Wrapper 실행 내용:

- `build_i_stock_v01_research.py`
- `--model-code I-STOCK-STRONG-RSI-V01`
- `--signal-profile early_strong_rsi`
- `--disable-liquidity-score`
- `--disable-buy-conversion-filter`
- `--selection-score raw`
- `--regime-mode none`
- 이후 `sync_i_series_shadow_operational.py`로 operational DB 동기화

Admin/web handoff:

- Admin tracker: `D:\Quant\scripts\build_admin_new_entry_tracker.py`
- History payload: `D:\Quant\service_platform\publishers\build_redbot_history_payloads.py`
- Validator: `D:\Quant\scripts\validate_admin_new_entry_tracker.py`
- History validator: `D:\Quant\scripts\validate_redbot_history_payloads.py`

Payload 반영 원칙:

- `I-STOCK-STRONG-RSI-V01`은 공개 사용자 모델이 아니라 `internal_models` scope로만 제공한다.
- `admin_new_entry_tracker.json`의 `internal_models`, `weekly_rankings.internal_models`, `model_performance_summary.internal_models`에 포함한다.
- 내부 모델 이벤트 타입 관례에 맞춰 신규 후보는 `new_entry`, 재진입은 `re_entry`, candidate에서 core로 올라가는 경우는 `weight_increase`로 표기한다.
- 성과 기준은 `metric_basis = i_series_shadow_backtest`로 명시한다.

2026-04-29 검증 결과:

- latest candidates: 30
- admin tracker internal event rows: 17,867
- I-series latest weekly ranking rows: 30
- admin tracker event/ranking match ratio: user 100%, internal 100%, tseries 100%
- performance coverage: `I-STOCK-STRONG-RSI-V01` 포함 전체 internal/tseries required fields 100%
- history payload validation: ok

QS 반영 필요:

- QS admin `내부용 모델` 페이지에서 `I-STOCK-STRONG-RSI-V01` 라벨과 표시 순서를 추가한다.
- 이미 payload는 기존 내부용 모델과 같은 구조로 제공되므로, QS가 동적 렌더링이면 별도 계산 로직은 필요 없다.
- 외부 공개 메뉴에는 노출하지 않고 관리자 로그인 영역에만 표시한다.

## Forward Return Diagnostic

2026-04-29 기준 1차 signal bucket별 forward return은 `i_stock_v01_forward_return_summary`에 저장했다.

초기 해석:

- `BUY`와 `HOLD`는 대체로 1주~12주 평균수익률에서 양호하다.
- 다만 전체 시장 상승 편향이 있어 `SELL` 그룹도 장기 forward return이 양수로 나온다.
- 따라서 I-series 신호는 단독 매도 모델보다 기존 S/T/C 모델의 타이밍 overlay로 먼저 검증하는 것이 안전하다.

## S/T/C Overlay Review

최신 S/T/C 선정 종목과 I-series 신호를 조인했다.

저장 위치:

- SQLite: `D:\Quant\data\db\i_series_research.db`
- `i_stock_v01_overlay_latest`
- `i_stock_v01_overlay_summary`
- Report: `D:\Quant\reports\i_series_stock_v01\I_STOCK_V01_OVERLAY_REVIEW_20260429.md`

2026-04-29 요약:

- S2: 20 aligned, 9 conflict/exit-watch, 1 neutral
- S2_PIT_V01: 22 aligned, 8 conflict/exit-watch
- S3: 6 aligned, 12 conflict/exit-watch, 2 neutral
- S3_CORE2: 7 aligned, 10 conflict/exit-watch, 3 neutral
- T-STOCK-V01: 1 aligned, 7 conflict/exit-watch, 1 neutral
- T-ETF-V01: 2 neutral

초기 해석:

- S2 계열은 I-series와의 정합도가 높은 편이다.
- S3/S3_CORE2는 기존 모델 선정 종목 중 I-series가 매도/주의로 보는 종목 비율이 높다.
- T-STOCK 후보도 I-series와 충돌하는 후보가 많아, T-series 후보의 실제 진입 타이밍 필터로 쓸 가능성이 있다.
- ETF는 I-STOCK-V01 적용 대상이 아니므로 별도 `I-ETF-V01`이 필요하다.
- C-series 최신 overlay는 2026-04-22 기준 산출물이므로, 이후 C pipeline 최신화 후 다시 비교해야 한다.

## Next Research Steps

1. `top30 / score >= 65`를 1차 baseline으로 두고 안정화한다.
2. MDD를 줄이기 위해 aggressive breadth/regime gate를 1차 안정화 후보로 둔다.
3. `EXIT_WATCH`와 `SELL`이 실제 하락 회피에 도움이 되는지 보유 종목 청산 규칙으로 별도 검증한다.
4. S3/S3_CORE2/T-STOCK에 I-filter를 적용한 challenger backtest를 만든다.
5. C-series를 최신 asof로 재산출한 뒤 C overlay와 I overlay의 결합 효과를 본다.
6. 4~8주 shadow tracking 후 운영 모델 승격 여부를 판단한다.

## Early Split Challenger

2026-05-04에 기존 strong RSI 모델의 성격 분리를 위해 early-only challenger를 만들었다.

변경 원칙:

- 기존 `I-STOCK-STRONG-RSI-V01`은 보존한다.
- `I-STOCK-EARLY-V01`은 universe 전체를 먼저 `early / reacceleration / overheated_watch`로 분류한 뒤 `early` 후보만 선택한다.
- `I-STOCK-STRONG-RSI-NO-EARLY-CH01`은 기존 strong RSI에서 `early`를 제외한 관찰용 challenger다.

2026-04-29 기준 비교:

| model | CAGR | total return | MDD | Sharpe | latest holdings |
| --- | ---: | ---: | ---: | ---: | ---: |
| I-STOCK-STRONG-RSI-V01 | 35.12% | 1,549.98% | -26.64% | 1.46 | 30 |
| I-STOCK-STRONG-RSI-NO-EARLY-CH01 | 41.02% | 2,357.43% | -39.78% | 1.46 | 30 |
| I-STOCK-EARLY-V01 | 18.82% | 398.26% | -47.64% | 0.85 | 18 |

초기 판단:

- `I-STOCK-EARLY-V01`은 의도대로 최신 후보가 모두 `early`로 제한됐다.
- 다만 성과와 MDD는 아직 baseline 대비 부족하므로 운영 전환 전 안정화가 필요하다.
- `I-STOCK-STRONG-RSI-NO-EARLY-CH01`은 CAGR은 높지만 MDD가 커서 즉시 대체하지 않는다.
- 상세 비교: `D:\Quant\reports\i_series_stock_v01\I_SERIES_EARLY_SPLIT_COMPARISON_20260429.md`

## Early Quality Filter Test

`I-STOCK-EARLY-V01`의 MDD를 줄이기 위해 early 후보 내부 quality filter를 테스트했다.

테스트 결과:

| variant | CAGR | total return | MDD | Sharpe | latest holdings |
| --- | ---: | ---: | ---: | ---: | ---: |
| early_base | 18.82% | 398.26% | -47.64% | 0.85 | 18 |
| early_quality_guard_v1 | 20.16% | 453.28% | -45.61% | 0.92 | 18 |
| early_quality_guard_v2 | 14.66% | 257.56% | -52.90% | 0.73 | 17 |
| early_quality_v1 | 16.27% | 307.28% | -51.68% | 0.70 | 11 |
| early_quality_v2 | 11.95% | 186.26% | -49.41% | 0.60 | 10 |
| early_quality_v3 | 17.83% | 360.96% | -52.26% | 0.85 | 5 |

초기 판단:

- `early_quality_guard_v1`만 성과와 위험을 동시에 소폭 개선했다.
- 더 강한 hard filter는 상승 초기 구간의 거친 회복 특성까지 잘라내 성과가 나빠졌다.
- 따라서 early 모델에는 강한 품질 필터보다 극단 위험만 제거하는 guard형 필터가 더 적합하다.
- 다음 단계에서는 `early_quality_guard_v1`에 regime/crash gate를 결합해 MDD 개선 효과를 테스트한다.
- 상세 비교: `D:\Quant\reports\i_series_stock_v01\I_SERIES_EARLY_QUALITY_FILTER_COMPARISON_20260429.md`

## Reaccel / Overheated Backtest

`early`의 독립 선발력이 약했기 때문에 `reacceleration` 및 `overheated_watch` bucket을 독립 전략 후보로 테스트했다.

결과:

| variant | CAGR | total return | MDD | Sharpe | avg exposure |
| --- | ---: | ---: | ---: | ---: | ---: |
| strong_base | 35.12% | 1,549.98% | -26.64% | 1.46 | 99.78% |
| reaccel | 38.46% | 1,972.23% | -38.53% | 1.24 | 96.76% |
| overheated | 52.10% | 4,868.90% | -63.49% | 1.23 | 86.33% |
| reaccel + overheated | 41.02% | 2,357.43% | -39.78% | 1.46 | 97.63% |
| reaccel + aggressive gate | 22.20% | 547.19% | -27.02% | 1.19 | 71.70% |
| overheated + aggressive gate | 50.90% | 4,518.12% | -43.08% | 1.40 | 66.25% |
| reaccel + overheated + aggressive gate | 31.86% | 1,214.19% | -30.80% | 1.64 | 71.88% |

초기 판단:

- `overheated_watch`는 수익 잠재력은 가장 크지만 MDD가 커서 주력 모델로는 위험하다.
- `reacceleration`은 기술적 타이밍 강화 태그로 유용하다.
- `reacceleration + overheated_watch + aggressive gate`는 Sharpe가 가장 높고 MDD가 크게 낮아져 독립 challenger로 유지할 가치가 있다.
- 이름 후보는 `I-STOCK-MOMENTUM-V01`이다.
- 상세 비교: `D:\Quant\reports\i_series_stock_v01\I_SERIES_REACCEL_OVERHEAT_BACKTEST_20260429.md`
