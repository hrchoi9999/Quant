# 2026-05-06 Growth Stock Valuation AI Model Spec

## 문서 목적

본 문서는 기존 퀀트투자 시스템에 **성장주의 현재 주가 수준이 적정한지, 과열인지, 저평가인지 판단하는 AI 학습 모델**을 추가하기 위한 개발 명세서입니다.

핵심 목표는 단순히 “성장 산업인가?”를 판단하는 것이 아니라, 다음 질문에 답하는 모델을 만드는 것입니다.

> “향후 1~5년 수요처 또는 시장 성장 전망을 고려했을 때, 현재 주가는 미래 성장 기대를 과도하게 반영하고 있는가, 적정하게 반영하고 있는가, 아직 덜 반영하고 있는가?”

이 모델은 기존 퀀트투자 모델의 종목선정 점수에 보조 점수로 결합되며, 최종적으로는 **주가 수준 판단 AI**로 발전시키는 것을 목표로 합니다.

---

## 0. 핵심 개발 방향 요약

### 0.1 모델의 역할

본 모델은 목표주가를 직접 예측하는 모델이 아니라, **현재 주가에 반영된 성장 기대치와 향후 실현 가능성을 비교하여 투자 매력도를 점수화하는 모델**입니다.

### 0.2 출력값

모델은 종목별로 다음 값을 생성합니다.

| 출력값 | 설명 |
|---|---|
| `valuation_ai_score` | 0~100점 주가 수준 판단 점수 |
| `valuation_state` | `UNDERVALUED`, `FAIR`, `OVERHEATED`, `AVOID` 중 하나 |
| `expected_return_bucket` | 향후 3/6/12개월 초과수익 가능성 구간 |
| `downside_risk_score` | 향후 손실 위험 점수 |
| `confidence_score` | 모델 판단 신뢰도 |
| `reason_codes` | 판단 근거 코드 목록 |

### 0.3 적용 범위

1차 적용 대상은 기존 퀀트 시스템의 **KOSPI/KOSDAQ 혼합 유니버스**입니다.

초기에는 개별 성장주 중심으로 적용하고, 이후 다음 순서로 확장합니다.

1. 개별 성장주
2. 반도체/AI/로봇/바이오 등 성장 섹터별 특화 모델
3. ETF 구성종목 기반 ETF 수준 평가
4. 레버리지 ETF의 기초지수 수준 평가

주의: 레버리지 ETF 자체의 장기 적정성을 직접 평가하지 않습니다. 레버리지 ETF는 기초지수 평가 + 레버리지 구조 리스크를 별도로 반영해야 합니다.

---

# 1. 주가 수준 평가 학습 모델의 내용

## 1.1 문제 정의

성장주의 적정 주가 수준 평가는 다음 구조로 정의합니다.

```text
시장 성장 전망
→ 기업 매출 성장 가능성
→ 이익률/현금흐름/ROIC 개선 가능성
→ 현재 밸류에이션 수준
→ 현재 주가가 요구하는 미래 성장률
→ 향후 초과수익 가능성 및 하방위험
```

즉, 본 모델은 다음을 학습해야 합니다.

1. 고성장 산업에서 실제로 주가가 더 상승한 종목의 특징
2. 좋은 업황에도 불구하고 이미 고평가되어 이후 수익률이 낮았던 종목의 특징
3. 이익 전망이 개선되면서도 아직 주가에 덜 반영된 종목의 특징
4. 단기 과열과 중장기 성장성을 구분하는 특징
5. 향후 손실 위험이 큰 구간의 특징

---

## 1.2 모델의 핵심 판단 질문

모델은 각 종목에 대해 다음 질문을 점수화합니다.

| 질문 | 판단 목적 |
|---|---|
| 해당 기업의 매출 성장률은 산업 성장률을 따라갈 가능성이 높은가? | 성장 실현 가능성 |
| 영업이익률과 순이익률이 개선되고 있는가? | 수익성 개선 여부 |
| ROE/ROIC가 자본비용보다 충분히 높은가? | 주주가치 창출 여부 |
| PER/PBR/PSR/EV/EBITDA가 역사적 밴드 대비 과도한가? | 현재 가격 부담 |
| 이익 전망 상향이 주가 상승보다 빠른가? | 실적 모멘텀 |
| 현재 주가가 요구하는 미래 성장률이 현실적인가? | Reverse DCF 관점 |
| 최근 수급과 가격 상승이 과열권인가? | 단기 리스크 |
| 하락 시 방어력이 있는가? | 손실 위험 |

---

## 1.3 판단 등급 체계

### 1.3.1 `valuation_state`

| 등급 | 의미 | 투자 해석 |
|---|---|---|
| `UNDERVALUED` | 성장성과 실적 대비 주가가 낮음 | 적극 검토 |
| `FAIR` | 성장성과 현재 주가가 대체로 균형 | 보유 또는 분할 접근 |
| `OVERHEATED` | 성장 기대가 주가에 과도하게 반영됨 | 신규매수 주의, 조정 대기 |
| `AVOID` | 성장성 대비 고평가이거나 하방위험 큼 | 제외 또는 비중 축소 |

### 1.3.2 점수 구간

| 점수 | 상태 | 해석 |
|---:|---|---|
| 80~100 | `UNDERVALUED` | 기대수익 대비 리스크 우수 |
| 60~79 | `FAIR` | 적정 수준, 다른 모델 점수와 결합 필요 |
| 40~59 | `OVERHEATED` | 과열 또는 기대 선반영 |
| 0~39 | `AVOID` | 손실위험 또는 고평가 부담 큼 |

---

## 1.4 학습 타깃 정의

단일 타깃보다 복수 타깃을 사용하는 것이 바람직합니다.

### 1.4.1 기본 타깃

| 타깃명 | 산식 | 용도 |
|---|---|---|
| `fwd_ret_3m` | 3개월 후 수익률 | 단기 검증 |
| `fwd_ret_6m` | 6개월 후 수익률 | 중기 검증 |
| `fwd_ret_12m` | 12개월 후 수익률 | 핵심 타깃 |
| `fwd_excess_ret_12m` | 종목 12개월 수익률 - 시장/섹터 수익률 | 초과수익 판단 |
| `fwd_max_drawdown_6m` | 향후 6개월 최대낙폭 | 하방위험 판단 |
| `fwd_sharpe_12m` | 향후 12개월 위험조정 수익 | 품질 평가 |

### 1.4.2 분류 타깃

| 타깃명 | 정의 |
|---|---|
| `label_outperform` | 향후 12개월 섹터 대비 초과수익률 상위 30%면 1 |
| `label_underperform` | 향후 12개월 섹터 대비 초과수익률 하위 30%면 1 |
| `label_overheated` | 최근 급등 + 고밸류 + 이후 6개월 부진이면 1 |
| `label_value_creation` | 향후 초과수익률 양호 + 하방위험 제한이면 1 |

### 1.4.3 최종 학습 방향

초기 모델은 다음 2개 모델을 병행합니다.

1. **회귀 모델**: 향후 12개월 초과수익률 예측
2. **분류 모델**: `UNDERVALUED` / `FAIR` / `OVERHEATED` / `AVOID` 분류

실전 적용에서는 회귀값보다 **랭킹과 등급**을 더 중요하게 사용합니다.

---

# 2. 필요한 학습데이터의 종류와 소스

## 2.1 데이터 분류

필요 데이터는 크게 8개 계층으로 나눕니다.

| 데이터 계층 | 주요 내용 | 필수 여부 |
|---|---|---|
| 가격/거래 데이터 | 일봉, 주간 수익률, 거래대금, 변동성 | 필수 |
| 재무 데이터 | 매출, 영업이익, 순이익, 자본, 부채, 현금흐름 | 필수 |
| 밸류에이션 데이터 | PER, PBR, PSR, PCR, EV/EBITDA, 배당수익률 | 필수 |
| 성장성 데이터 | 매출성장률, EPS성장률, 이익전망 변화 | 필수 |
| 품질 데이터 | ROE, ROIC, 영업이익률, FCF margin, 부채비율 | 필수 |
| 산업/시장 전망 데이터 | 섹터별 성장률, CAPEX, 수요처 지표 | 2단계 필수 |
| 수급/심리 데이터 | 외국인/기관 순매수, 공매도, 거래대금 급증 | 권장 |
| 텍스트 데이터 | 공시, 뉴스, 실적발표, 리포트 요약 | 2단계 이후 |

---

## 2.2 현재 퀀트 시스템 내 활용 가능한 데이터

기존 `D:\Quant` 프로젝트 기준으로 다음 데이터를 우선 활용합니다.

| 기존 자산 | 예상 경로/테이블 | 활용 내용 |
|---|---|---|
| 가격 DB | `D:\Quant\data\db\price.db`, `prices_daily` | 일봉, 수익률, 변동성, SMA, MDD |
| 시장 DB | `D:\Quant\data\db\market.db`, `market_daily` | KOSPI/KOSDAQ 시장 상태, 시장 게이트 |
| 레짐 DB | `D:\Quant\data\db\regime.db`, `regime_history` | 시장 국면 정보 |
| 펀더멘털 DB | `D:\Quant\data\db\fundamentals.db` | 재무/밸류에이션 팩터 |
| 유니버스 CSV | `D:\Quant\data\universe\universe_mix_top400_*.csv` | KOSPI/KOSDAQ 혼합 유니버스 |
| S2 펀더멘털 점수 | `s2_fund_scores_monthly` view | 기존 펀더멘털 점수와 결합 |

---

## 2.3 외부 데이터 소스

### 2.3.1 국내 공식/준공식 데이터

| 데이터 | 소스 | 용도 | 비고 |
|---|---|---|---|
| 기업 공시/재무제표 | OpenDART | 재무제표, 사업보고서, 주요 공시 | 공식 소스 |
| 시장 가격/종목정보 | KRX Data Marketplace / KRX Open API | 일별매매정보, 종목기본정보, ETF 정보 | 공식 소스 |
| 실시간/기간별 가격 | 한국투자증권 Open API | 현재가, 일/주/월봉, 계좌 연동 | 실전 운영용 |
| 거시경제 | 한국은행 ECOS | 금리, 환율, 통화, 경기 지표 | 권장 |
| 통계 | KOSIS | 산업/인구/거시 보조지표 | 권장 |

### 2.3.2 유료/상용 데이터 후보

| 데이터 | 후보 소스 | 용도 |
|---|---|---|
| 애널리스트 컨센서스 | FnGuide, Quantiwise, 에프앤가이드 계열 | EPS 전망, 목표주가, 전망치 변화 |
| 업종별 밸류에이션 | FnGuide, Quantiwise | 섹터 비교 |
| 기관 수급 고도화 | 증권사 API, KRX | 수급 모멘텀 |
| 글로벌 산업 전망 | Gartner, IDC, S&P Global, Bloomberg, Refinitiv | 산업 성장률, CAPEX 전망 |

### 2.3.3 글로벌 공개 데이터

| 데이터 | 소스 | 용도 |
|---|---|---|
| 미국 금리/경기 | FRED API | 할인율, 유동성, 경기 국면 |
| 글로벌 ETF/가격 | Yahoo Finance, Stooq 등 | 글로벌 비교 참고 |
| 원자재/환율 | FRED, Investing, 거래소 데이터 | 반도체/소재 업종 보조지표 |

---

## 2.4 핵심 피처 설계

### 2.4.1 가격/모멘텀 피처

| 피처명 | 설명 |
|---|---|
| `ret_1m`, `ret_3m`, `ret_6m`, `ret_12m` | 기간별 수익률 |
| `excess_ret_3m_sector` | 섹터 대비 초과수익률 |
| `vol_20d`, `vol_60d` | 단기/중기 변동성 |
| `mdd_3m`, `mdd_6m` | 최근 최대낙폭 |
| `distance_sma_60`, `distance_sma_140`, `distance_sma_200` | 이동평균 대비 이격도 |
| `turnover_ratio_20d` | 거래대금 회전율 |
| `price_acceleration` | 수익률 가속도 |

### 2.4.2 밸류에이션 피처

| 피처명 | 설명 |
|---|---|
| `per_ttm`, `per_fwd` | 후행/선행 PER |
| `pbr` | PBR |
| `psr` | PSR |
| `ev_ebitda` | EV/EBITDA |
| `peg` | PER / EPS 성장률 |
| `valuation_percentile_5y` | 5년 역사적 밸류에이션 백분위 |
| `sector_valuation_zscore` | 섹터 대비 밸류에이션 z-score |

### 2.4.3 성장성 피처

| 피처명 | 설명 |
|---|---|
| `sales_growth_yoy` | 매출 YoY 성장률 |
| `op_growth_yoy` | 영업이익 YoY 성장률 |
| `eps_growth_yoy` | EPS YoY 성장률 |
| `sales_cagr_3y` | 3년 매출 CAGR |
| `op_cagr_3y` | 3년 영업이익 CAGR |
| `consensus_eps_revision_1m` | 1개월 EPS 전망 변화율 |
| `consensus_eps_revision_3m` | 3개월 EPS 전망 변화율 |

### 2.4.4 품질/수익성 피처

| 피처명 | 설명 |
|---|---|
| `roe` | 자기자본이익률 |
| `roic` | 투하자본이익률 |
| `op_margin` | 영업이익률 |
| `net_margin` | 순이익률 |
| `fcf_margin` | 잉여현금흐름률 |
| `debt_to_equity` | 부채비율 |
| `interest_coverage` | 이자보상배율 |
| `capex_to_sales` | 매출 대비 설비투자 비율 |

### 2.4.5 시장/레짐 피처

| 피처명 | 설명 |
|---|---|
| `market_regime` | 기존 regime 점수 또는 등급 |
| `kospi_ret_3m`, `kosdaq_ret_3m` | 시장 수익률 |
| `market_sma_gate` | 시장 게이트 상태 |
| `usdkrw_ret_3m` | 환율 변화 |
| `rate_level` | 금리 수준 |
| `liquidity_proxy` | 유동성 대용 지표 |

### 2.4.6 산업 성장 피처

초기에는 정형화된 데이터 확보가 어려우므로 섹터 단위 대체지표부터 시작합니다.

| 피처명 | 설명 |
|---|---|
| `sector_sales_growth_median` | 섹터 내 매출 성장률 중앙값 |
| `sector_op_growth_median` | 섹터 내 영업이익 성장률 중앙값 |
| `sector_capex_growth` | 섹터 설비투자 증가율 |
| `sector_valuation_percentile` | 섹터 전체 밸류에이션 위치 |
| `industry_demand_score` | 산업 수요 전망 점수 |
| `ai_infra_proxy_score` | AI 인프라 관련 수요 점수, 반도체 특화 |

---

# 3. 학습 모델 설계 방법

## 3.1 전체 아키텍처

```text
[Data Layer]
  가격/재무/밸류에이션/시장/산업 데이터 수집
        ↓
[Feature Layer]
  월간 또는 주간 기준 as-of feature 생성
        ↓
[Label Layer]
  향후 3/6/12개월 초과수익률 및 하방위험 label 생성
        ↓
[Model Layer]
  회귀 모델 + 분류 모델 + 랭킹 모델 학습
        ↓
[Scoring Layer]
  valuation_ai_score, valuation_state, reason_codes 생성
        ↓
[Integration Layer]
  기존 S2/S3 종목선정 모델에 결합
        ↓
[Monitoring Layer]
  실전 성과, 예측 안정성, drift 점검
```

---

## 3.2 권장 모델 구조

### 3.2.1 1차 모델: Rule + ML Hybrid

초기에는 완전한 딥러닝보다 **규칙 기반 점수 + LightGBM/CatBoost/XGBoost 계열 모델**을 권장합니다.

이유는 다음과 같습니다.

1. 국내 주식 데이터 수가 제한적입니다.
2. 재무 데이터는 분기/월 단위라 딥러닝 학습량이 충분하지 않을 수 있습니다.
3. 트리 기반 모델은 tabular 데이터에서 성능이 안정적입니다.
4. feature importance와 SHAP 분석으로 판단 근거를 설명하기 쉽습니다.
5. 기존 퀀트 시스템에 결합하기 쉽습니다.

### 3.2.2 모델 구성

| 모델 | 역할 |
|---|---|
| `valuation_regressor` | 향후 12개월 초과수익률 예측 |
| `overheat_classifier` | 과열/고평가 위험 분류 |
| `downside_risk_model` | 향후 6개월 손실위험 예측 |
| `ranker_model` | 유니버스 내 상대 매력도 순위화 |
| `rule_score_engine` | Reverse DCF/밴드/ROIC 기반 보조 점수 |

---

## 3.3 최종 점수 산식

초기 버전에서는 다음과 같이 합성 점수를 만듭니다.

```text
valuation_ai_score
= 0.35 * expected_return_score
+ 0.25 * valuation_safety_score
+ 0.20 * growth_quality_score
+ 0.10 * revision_momentum_score
+ 0.10 * downside_safety_score
```

각 하위 점수는 0~100점으로 표준화합니다.

| 하위 점수 | 의미 |
|---|---|
| `expected_return_score` | 향후 초과수익 가능성 |
| `valuation_safety_score` | 현재 밸류에이션 부담의 낮음 |
| `growth_quality_score` | 성장성과 수익성의 질 |
| `revision_momentum_score` | 이익전망 개선 여부 |
| `downside_safety_score` | 손실위험의 낮음 |

---

## 3.4 Reverse DCF 보조 엔진

정밀 DCF를 모든 종목에 적용하기 어렵기 때문에 초기에는 **간이 Reverse DCF 또는 implied growth score**를 만듭니다.

### 3.4.1 목적

현재 주가 수준이 정당화되려면 향후 성장률이 얼마나 높아야 하는지 추정합니다.

### 3.4.2 간이 산식 예시

```text
implied_growth_pressure
= current_valuation_percentile
- normalized_growth_quality_score
```

또는:

```text
valuation_growth_gap
= sector_valuation_zscore - sector_growth_zscore
```

해석:

| 값 | 의미 |
|---|---|
| 높음 | 성장성 대비 밸류에이션 부담 큼 |
| 중간 | 성장성과 주가 수준이 균형 |
| 낮음 | 성장성 대비 주가 부담 낮음 |

### 3.4.3 실전 판단

| 조건 | 판단 |
|---|---|
| 성장성 높음 + 밸류에이션 낮음 | 저평가 가능성 |
| 성장성 높음 + 밸류에이션 높음 | 적정 또는 과열 |
| 성장성 낮음 + 밸류에이션 높음 | 회피 |
| 성장성 낮음 + 밸류에이션 낮음 | 가치주 모델로 별도 판단 |

---

## 3.5 학습 주기

초기 학습 단위는 **월간 리밸런싱 기준**을 권장합니다.

| 구분 | 권장 기준 |
|---|---|
| feature 생성 주기 | 월간, 이후 주간 확장 |
| label horizon | 3개월, 6개월, 12개월 |
| 학습 데이터 기간 | 최소 7년 이상, 가능하면 10년 이상 |
| 검증 방식 | walk-forward validation |
| 재학습 주기 | 월 1회 또는 분기 1회 |
| 실전 score 생성 | 주 1회 또는 월 1회 |

기존 시스템이 주간 리밸런싱을 사용하더라도, 재무/밸류에이션 기반 모델은 월간 기준으로 생성하고 주간 모델에서는 가장 최근 월간 점수를 참조하는 방식이 안정적입니다.

---

## 3.6 데이터 누수 방지 원칙

본 모델에서 가장 중요한 것은 **as-of 기준**입니다.

금지 사항:

1. 발표되지 않은 미래 재무제표 사용 금지
2. 미래 컨센서스 변경 데이터 사용 금지
3. 미래 편입 종목 정보를 과거 시점에 사용 금지
4. 상장폐지/관리종목 survivorship bias 방치 금지
5. 수정주가 처리 기준 불일치 금지

필수 처리:

| 항목 | 처리 원칙 |
|---|---|
| 재무제표 | 공시일 기준 lag 적용 |
| 컨센서스 | 해당 일자 기준 스냅샷 필요 |
| 유니버스 | 당시 시점의 유니버스 재현 |
| 가격 | 수정주가 기준 통일 |
| 리밸런싱 | decision date와 trade date 분리 |

---

# 4. 학습 모델 평가 방법

## 4.1 예측 성능 평가

| 지표 | 설명 | 목표 |
|---|---|---|
| `IC` | 예측 점수와 향후 수익률 상관 | 양수 유지 |
| `Rank IC` | 순위 상관 | 핵심 지표 |
| `AUC` | outperform/underperform 분류 성능 | 0.55 이상부터 의미 |
| `Brier Score` | 확률 예측 보정 | 낮을수록 좋음 |
| `Calibration Curve` | 확률 예측 신뢰도 | 과신 여부 확인 |
| `Precision@TopN` | 상위 N개 종목 적중률 | 실전 중요 |

단순 정확도보다 **Rank IC와 Top-N 성과**가 중요합니다.

---

## 4.2 투자 성과 평가

모델 점수를 이용한 포트폴리오 백테스트를 반드시 수행합니다.

| 평가 항목 | 설명 |
|---|---|
| CAGR | 연복리 수익률 |
| MDD | 최대낙폭 |
| Sharpe | 위험조정 수익률 |
| Sortino | 하방위험 조정 수익률 |
| Hit Ratio | 승률 |
| Turnover | 회전율 |
| 거래비용 반영 후 수익률 | 수수료/슬리피지 반영 |
| Top-Decile Spread | 상위 10% - 하위 10% 수익률 차이 |

기존 사용자 선호 포맷에 맞춰 1Y/2Y/3Y/5Y/FULL 성과표를 생성합니다.

| Window | Start | End | Days | CAGR | MDD | Sharpe | Avg Daily Ret | Daily Vol |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1Y |  |  |  |  |  |  |  |  |
| 2Y |  |  |  |  |  |  |  |  |
| 3Y |  |  |  |  |  |  |  |  |
| 5Y |  |  |  |  |  |  |  |  |
| FULL |  |  |  |  |  |  |  |  |

---

## 4.3 안정성 평가

모델은 전체 기간 평균 성과보다 **국면별 안정성**이 중요합니다.

| 구분 | 평가 내용 |
|---|---|
| 상승장 | 과열 종목을 너무 빨리 제외하지 않는지 |
| 하락장 | 고평가 성장주 손실을 줄이는지 |
| 박스권 | 불필요한 회전율을 높이지 않는지 |
| 금리 상승기 | 고밸류 성장주 리스크를 반영하는지 |
| 금리 하락기 | 성장주 프리미엄을 적절히 반영하는지 |
| 반도체 사이클 | 메모리/AI/HBM 사이클을 반영하는지 |

---

## 4.4 설명 가능성 평가

모델은 사용자가 납득할 수 있어야 합니다.

필수 출력:

| 항목 | 설명 |
|---|---|
| `top_positive_factors` | 점수를 높인 주요 요인 |
| `top_negative_factors` | 점수를 낮춘 주요 요인 |
| `reason_codes` | 사람이 읽을 수 있는 판단 코드 |
| `sector_comparison` | 섹터 내 위치 |
| `historical_band_position` | 과거 밸류에이션 밴드 내 위치 |

예시:

```json
{
  "ticker": "000660",
  "valuation_ai_score": 72,
  "valuation_state": "FAIR",
  "confidence_score": 0.68,
  "reason_codes": [
    "EPS_REVISION_POSITIVE",
    "ROIC_IMPROVING",
    "VALUATION_HIGH_BUT_SUPPORTED_BY_GROWTH",
    "SHORT_TERM_OVERHEAT_RISK"
  ]
}
```

---

## 4.5 신뢰성 판단 기준

본 모델의 신뢰성은 다음 기준으로 평가합니다.

| 수준 | 조건 |
|---|---|
| 높음 | 여러 기간에서 Rank IC 양수, Top-N 초과수익 일관, MDD 개선 |
| 중상 | 특정 국면에서 성과 우수, 장기 평균 양호 |
| 중간 | 성과는 있으나 국면 의존성 큼 |
| 낮음 | 백테스트 성과 불안정, 특정 기간 과최적화 의심 |

목표는 “정확한 목표주가 예측”이 아니라 **종목선정 과정에서 고평가 리스크를 줄이고, 성장성 대비 주가 부담이 낮은 종목을 선별하는 것**입니다.

---

# 5. 기존 퀀트 투자 모델에 적용방안

## 5.1 적용 원칙

기존 S2 모델의 방향성을 유지하면서 `valuation_ai_score`를 보조 팩터로 추가합니다.

기존 S2는 다음 성격입니다.

```text
S2 = regime + fundamentals + SMA filter
```

추가 후 구조:

```text
S2 Plus = regime + fundamentals + SMA filter + valuation_ai_score
```

---

## 5.2 통합 방식

### 5.2.1 1단계: 필터로 사용

초기에는 매수 후보에서 과열 종목을 제외하는 필터로 사용합니다.

```text
if valuation_state == "AVOID":
    exclude from buy candidates

if valuation_state == "OVERHEATED" and distance_sma_60 is very high:
    reduce rank or exclude
```

장점:

1. 기존 모델 성격을 크게 훼손하지 않습니다.
2. 과최적화 위험이 낮습니다.
3. 모델이 완전히 안정화되기 전에도 사용할 수 있습니다.

### 5.2.2 2단계: 랭킹 점수로 사용

모델 안정성이 확인되면 최종 종목 랭킹에 반영합니다.

예시:

```text
final_score
= 0.45 * s2_fund_score
+ 0.25 * momentum_score
+ 0.20 * valuation_ai_score
+ 0.10 * quality_score
```

또는 더 보수적으로:

```text
final_score
= existing_s2_score * valuation_adjustment_factor
```

```text
valuation_adjustment_factor:
UNDERVALUED = 1.10
FAIR        = 1.00
OVERHEATED  = 0.85
AVOID       = 0.00
```

### 5.2.3 3단계: 포지션 비중 조정

추후에는 종목 비중 조절에도 사용합니다.

```text
position_weight
= base_weight * risk_adjustment * valuation_adjustment
```

예시:

| 상태 | 비중 조정 |
|---|---:|
| `UNDERVALUED` | 1.10배 |
| `FAIR` | 1.00배 |
| `OVERHEATED` | 0.70배 |
| `AVOID` | 0배 |

---

## 5.3 권장 개발 파일 구조

기존 `D:\Quant` 구조를 유지하면서 다음 모듈을 추가합니다.

```text
D:\Quant
└─ src
   ├─ models
   │  └─ valuation_ai
   │     ├─ __init__.py
   │     ├─ config.py
   │     ├─ build_features.py
   │     ├─ build_labels.py
   │     ├─ train_model.py
   │     ├─ predict_scores.py
   │     ├─ rule_score_engine.py
   │     ├─ explain_scores.py
   │     ├─ evaluate_model.py
   │     └─ model_registry.py
   │
   ├─ backtest
   │  ├─ run_backtest_s2_refactor_v1.py
   │  └─ run_backtest_s2_plus_valuation_ai.py
   │
   └─ pipelines
      └─ rebuild_valuation_ai_pipeline.py

D:\Quant
└─ data
   ├─ db
   │  └─ valuation_ai.db
   └─ models
      └─ valuation_ai
         ├─ model_YYYYMMDD.pkl
         ├─ feature_columns_YYYYMMDD.json
         └─ training_report_YYYYMMDD.json

D:\Quant
└─ reports
   └─ valuation_ai
      ├─ valuation_scores_YYYYMMDD.csv
      ├─ valuation_model_eval_YYYYMMDD.csv
      ├─ valuation_backtest_YYYYMMDD.csv
      └─ valuation_reason_codes_YYYYMMDD.csv
```

---

## 5.4 권장 DB 테이블

### 5.4.1 `valuation_features_monthly`

```sql
CREATE TABLE IF NOT EXISTS valuation_features_monthly (
    asof_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    market TEXT,
    sector TEXT,
    ret_1m REAL,
    ret_3m REAL,
    ret_6m REAL,
    ret_12m REAL,
    vol_60d REAL,
    distance_sma_140 REAL,
    per_ttm REAL,
    pbr REAL,
    psr REAL,
    ev_ebitda REAL,
    sales_growth_yoy REAL,
    op_growth_yoy REAL,
    roe REAL,
    roic REAL,
    op_margin REAL,
    debt_to_equity REAL,
    sector_valuation_zscore REAL,
    valuation_percentile_5y REAL,
    market_regime INTEGER,
    created_at TEXT,
    PRIMARY KEY (asof_date, ticker)
);
```

### 5.4.2 `valuation_labels_forward`

```sql
CREATE TABLE IF NOT EXISTS valuation_labels_forward (
    asof_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    fwd_ret_3m REAL,
    fwd_ret_6m REAL,
    fwd_ret_12m REAL,
    fwd_excess_ret_12m REAL,
    fwd_max_drawdown_6m REAL,
    label_outperform INTEGER,
    label_underperform INTEGER,
    label_overheated INTEGER,
    created_at TEXT,
    PRIMARY KEY (asof_date, ticker)
);
```

### 5.4.3 `valuation_ai_scores`

```sql
CREATE TABLE IF NOT EXISTS valuation_ai_scores (
    asof_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    valuation_ai_score REAL,
    valuation_state TEXT,
    expected_return_score REAL,
    valuation_safety_score REAL,
    growth_quality_score REAL,
    revision_momentum_score REAL,
    downside_safety_score REAL,
    confidence_score REAL,
    reason_codes TEXT,
    model_version TEXT,
    created_at TEXT,
    PRIMARY KEY (asof_date, ticker, model_version)
);
```

---

## 5.5 CLI 설계

### 5.5.1 Feature 생성

```powershell
python -m src.models.valuation_ai.build_features `
  --universe D:\Quant\data\universe\universe_mix_top400_latest.csv `
  --price-db D:\Quant\data\db\price.db `
  --fund-db D:\Quant\data\db\fundamentals.db `
  --market-db D:\Quant\data\db\market.db `
  --out-db D:\Quant\data\db\valuation_ai.db `
  --start 2017-01-01 `
  --end 2026-05-06 `
  --freq M
```

### 5.5.2 Label 생성

```powershell
python -m src.models.valuation_ai.build_labels `
  --price-db D:\Quant\data\db\price.db `
  --feature-db D:\Quant\data\db\valuation_ai.db `
  --out-db D:\Quant\data\db\valuation_ai.db `
  --horizons 3m,6m,12m
```

### 5.5.3 모델 학습

```powershell
python -m src.models.valuation_ai.train_model `
  --db D:\Quant\data\db\valuation_ai.db `
  --target fwd_excess_ret_12m `
  --model-type lightgbm `
  --train-start 2017-01-01 `
  --train-end 2024-12-31 `
  --valid-start 2025-01-01 `
  --valid-end 2026-05-06 `
  --out-dir D:\Quant\data\models\valuation_ai
```

### 5.5.4 점수 생성

```powershell
python -m src.models.valuation_ai.predict_scores `
  --db D:\Quant\data\db\valuation_ai.db `
  --model-dir D:\Quant\data\models\valuation_ai `
  --asof 2026-05-06 `
  --out-csv D:\Quant\reports\valuation_ai\valuation_scores_20260506.csv
```

### 5.5.5 S2 Plus 백테스트

```powershell
python -m src.backtest.run_backtest_s2_plus_valuation_ai `
  --strategy S2_PLUS_VALAI `
  --horizon 3m `
  --rebalance W `
  --weekly-anchor-weekday 2 `
  --weekly-holiday-shift prev `
  --good-regimes 4,3 `
  --top-n 30 `
  --sma-window 140 `
  --market-gate `
  --market-sma-window 60 `
  --exit-below-sma-weeks 2 `
  --valuation-ai-db D:\Quant\data\db\valuation_ai.db `
  --valuation-ai-min-score 60 `
  --valuation-ai-weight 0.20
```

---

# 6. 개발 이후의 '주가 수준 판단' AI 추가학습 방법과 발전 방향

## 6.1 운영 후 추가학습 구조

모델 개발 후에는 다음 루프를 운영합니다.

```text
매월 데이터 업데이트
→ feature 재생성
→ 실전 예측값 저장
→ 3/6/12개월 후 실제 결과 비교
→ 모델 성능 리포트 생성
→ 필요 시 재학습
→ 모델 버전 교체 여부 판단
```

---

## 6.2 추가학습 원칙

| 항목 | 원칙 |
|---|---|
| 재학습 주기 | 월 1회 또는 분기 1회 |
| 모델 교체 | 성과가 검증된 경우에만 교체 |
| 기존 모델 보존 | 모든 모델 버전 저장 |
| 실전 예측 기록 | inference 시점의 score 반드시 저장 |
| 데이터 누수 점검 | 재학습 때마다 자동 점검 |
| 성과 저하 점검 | rolling IC, Top-N 성과 모니터링 |

---

## 6.3 모델 발전 단계

### Phase 1: 정형 데이터 기반 기본 모델

목표:

1. 가격, 재무, 밸류에이션, 품질 데이터 기반 모델 구축
2. 기존 S2 모델에 필터 방식으로 결합
3. Top-N 성과와 MDD 개선 여부 검증

모델:

```text
Rule score + LightGBM/CatBoost
```

---

### Phase 2: 컨센서스/이익전망 반영

목표:

1. EPS 전망 변화율 반영
2. 목표주가 변화율 반영
3. 실적 서프라이즈/쇼크 반영
4. 전망치 상향 종목과 주가 과열 종목 구분

필요 데이터:

1. FnGuide/Quantiwise 등 유료 컨센서스
2. 증권사 리포트 요약 데이터
3. 실적발표일 캘린더

---

### Phase 3: 산업 특화 모델

성장 산업별로 별도 feature를 추가합니다.

| 산업 | 특화 피처 예시 |
|---|---|
| 반도체/AI | HBM 가격, DRAM/NAND 가격, CAPEX, 장비 발주, 수출 데이터 |
| 로봇 | 산업용 로봇 출하, 자동화 투자, 수주잔고 |
| 바이오 | 임상 단계, 기술수출, R&D 비용, 현금소진율 |
| 2차전지 | 리튬 가격, 양극재 가격, 전기차 판매량, 배터리 출하량 |
| 방산 | 수주잔고, 수출계약, 국방예산 |

---

### Phase 4: 공시/뉴스 텍스트 AI 반영

텍스트 모델은 초기부터 넣지 말고, 정형 모델이 안정화된 뒤 추가합니다.

활용 데이터:

1. 사업보고서 MD&A
2. 분기보고서 주요 위험요인
3. 증권사 리포트 요약
4. 뉴스 헤드라인
5. 실적발표 컨퍼런스콜 요약

모델 방식:

```text
공시/뉴스 텍스트
→ 임베딩 생성
→ sentiment / growth / risk score 생성
→ 정형 모델 feature로 결합
```

주의:

텍스트 감성점수는 노이즈가 많으므로 단독 매매 신호로 사용하지 않습니다.

---

### Phase 5: ETF/섹터 평가 모델 확장

ETF 평가 방식:

```text
ETF valuation score
= Σ(구성종목 비중 × 구성종목 valuation_ai_score)
```

추가 조정:

| 항목 | 조정 내용 |
|---|---|
| ETF 괴리율 | NAV/iNAV 대비 시장가격 차이 |
| 총보수 | 장기 보유 비용 |
| 유동성 | 거래대금, 스프레드 |
| 레버리지 여부 | 장기 보유 부적합 패널티 |
| 섹터 집중도 | 상위 종목 쏠림 위험 |

레버리지 ETF는 다음 구조로만 평가합니다.

```text
기초지수 주가 수준 평가
+ 레버리지 구조 위험
+ 단기 변동성 위험
+ 보유 기간 패널티
```

---

## 6.4 최종 AI 서비스화 방향

향후 RedBot 서비스에서는 이 모델을 다음 형태로 제공할 수 있습니다.

### 6.4.1 사용자용 표현

투자자에게는 복잡한 모델 구조보다 직관적인 문장으로 표현합니다.

예시:

```text
현재 주가 수준: 적정 상단
성장성: 높음
밸류에이션 부담: 높음
단기 과열 위험: 있음
종합 판단: 신규 매수는 조정 후 접근이 유리
```

### 6.4.2 내부 관리용 표현

내부적으로는 점수와 근거를 상세히 저장합니다.

```json
{
  "ticker": "005930",
  "asof_date": "2026-05-06",
  "valuation_ai_score": 64,
  "valuation_state": "FAIR",
  "confidence_score": 0.71,
  "expected_return_score": 61,
  "valuation_safety_score": 54,
  "growth_quality_score": 78,
  "downside_safety_score": 59,
  "reason_codes": [
    "GROWTH_QUALITY_HIGH",
    "VALUATION_ABOVE_HISTORICAL_MEDIAN",
    "EARNINGS_REVISION_POSITIVE",
    "SHORT_TERM_OVERHEAT_MODERATE"
  ]
}
```

### 6.4.3 법적/표현상 주의

서비스 화면에서는 다음 표현을 피합니다.

| 피해야 할 표현 | 대체 표현 |
|---|---|
| 매수 추천 | 모델상 긍정 신호 |
| 목표주가 | 모델 추정 적정 범위 |
| 수익 보장 | 과거 데이터 기반 가능성 |
| 반드시 상승 | 상승 가능성 우위 |
| 투자자별 맞춤 조언 | 일반적 퀀트 모델 결과 |

---

# 7. Codex 개발 작업 지시사항

## 7.1 개발 목표

Codex는 본 문서를 기준으로 기존 `D:\Quant` 프로젝트에 `valuation_ai` 모듈을 추가해야 합니다.

1차 목표는 다음입니다.

1. 기존 DB에서 feature 생성
2. forward return label 생성
3. LightGBM 또는 scikit-learn 기반 baseline 모델 학습
4. 종목별 valuation score 생성
5. 기존 S2 백테스트에 필터 방식으로 적용
6. 성능 리포트 CSV 생성

---

## 7.2 개발 우선순위

### Step 1: DB 스키마 및 feature 생성

생성 파일:

```text
src/models/valuation_ai/config.py
src/models/valuation_ai/build_features.py
```

요구사항:

1. `price.db`, `fundamentals.db`, `market.db`, `regime.db`에서 데이터 로드
2. 월말 기준 feature 생성
3. 결측치 처리 로직 포함
4. `valuation_features_monthly` 테이블 저장
5. 모든 feature는 as-of 기준 준수

---

### Step 2: label 생성

생성 파일:

```text
src/models/valuation_ai/build_labels.py
```

요구사항:

1. 3/6/12개월 forward return 계산
2. 시장 또는 섹터 대비 excess return 계산
3. future MDD 계산
4. `valuation_labels_forward` 테이블 저장
5. feature 시점 이후 데이터만 사용

---

### Step 3: baseline 모델 학습

생성 파일:

```text
src/models/valuation_ai/train_model.py
```

요구사항:

1. 첫 버전은 scikit-learn `HistGradientBoostingRegressor` 또는 `RandomForestRegressor` 사용 가능
2. LightGBM이 설치되어 있으면 LightGBM 사용
3. walk-forward validation 구조 준비
4. 모델 파일 저장
5. feature importance 저장

---

### Step 4: 점수 생성

생성 파일:

```text
src/models/valuation_ai/predict_scores.py
src/models/valuation_ai/rule_score_engine.py
```

요구사항:

1. 모델 예측값을 0~100 점수로 변환
2. rule 기반 valuation safety score 추가
3. `valuation_state` 생성
4. `reason_codes` 생성
5. `valuation_ai_scores` 테이블과 CSV 저장

---

### Step 5: 평가 리포트

생성 파일:

```text
src/models/valuation_ai/evaluate_model.py
```

요구사항:

1. IC, Rank IC, Top-Decile Spread 계산
2. Top-N 포트폴리오 성과 계산
3. 1Y/2Y/3Y/5Y/FULL 성과표 생성
4. 기존 보고서 스타일과 호환되는 CSV 출력

---

### Step 6: 기존 S2 모델 통합

생성 또는 수정 파일:

```text
src/backtest/run_backtest_s2_plus_valuation_ai.py
```

요구사항:

1. 기존 S2 결과 후보에 valuation score 결합
2. `--valuation-ai-min-score` 옵션 추가
3. `--valuation-ai-weight` 옵션 추가
4. `OVERHEATED`, `AVOID` 종목 필터 옵션 추가
5. 기존 S2 결과와 S2_PLUS 결과 비교 리포트 생성

---

## 7.3 코드 작성 규칙

1. 모든 신규 파일 상단에 다음 형식의 버전 주석을 추가합니다.

```python
# 파일명 ver 2026-05-06_001
```

2. 동일 날짜 내 수정 시 `_002`, `_003`으로 순번을 증가시킵니다.
3. 기존 프로젝트의 import 구조를 유지합니다.
4. `sys.path` 임의 조작은 피합니다.
5. CLI 실행은 `python -m src...` 방식을 기준으로 합니다.
6. 기존 S2 결과를 훼손하지 말고, 별도 S2_PLUS 경로로 개발합니다.
7. 최초 개발은 안전하게 CSV 출력까지 확인한 뒤 DB/GSheet 연동을 확장합니다.

---

# 8. 성공 기준

1차 개발 성공 기준은 다음입니다.

| 기준 | 성공 조건 |
|---|---|
| feature 생성 | 월간 feature 테이블 정상 생성 |
| label 생성 | 3/6/12개월 forward return 정상 생성 |
| 모델 학습 | baseline 모델 저장 성공 |
| 점수 생성 | 전체 유니버스에 valuation score 생성 |
| 설명 가능성 | reason_codes 생성 |
| 백테스트 | 기존 S2와 S2_PLUS 성과 비교 가능 |
| 성능 | S2 대비 MDD 개선 또는 risk-adjusted return 개선 확인 |
| 안정성 | 특정 기간에만 성과가 집중되지 않아야 함 |

---

# 9. 현실적 기대수준

초기 모델이 바로 목표주가를 정확히 맞히기는 어렵습니다.

현실적인 1차 목표는 다음입니다.

1. 명백한 과열 성장주를 피한다.
2. 성장성 대비 가격 부담이 낮은 종목을 선별한다.
3. 기존 S2 모델의 MDD를 낮춘다.
4. Top-N 후보군의 품질을 개선한다.
5. RedBot 서비스에서 “주가 수준 판단” 설명 기능의 기반을 만든다.

따라서 1차 모델의 성공 기준은 **수익률 극대화**보다 **하방위험 감소와 종목선정 품질 개선**입니다.

---

# 10. 최종 결론

성장주의 주가 수준 판단 AI는 단순 예측모델이 아니라, 다음 5가지를 결합한 모델이어야 합니다.

```text
1. 성장성
2. 밸류에이션 부담
3. 수익성/ROIC 품질
4. 실적 전망 변화
5. 하방위험
```

가장 중요한 개발 철학은 다음입니다.

> “좋은 산업을 찾는 모델”이 아니라, “좋은 산업 안에서도 현재 가격이 합리적인 종목을 찾는 모델”이어야 한다.

기존 퀀트 모델에는 처음부터 핵심 엔진으로 넣기보다, **과열 종목 제외 필터 → 랭킹 보조 점수 → 비중 조정 엔진 → 서비스 설명 AI** 순서로 단계적으로 적용하는 것이 가장 안전합니다.

