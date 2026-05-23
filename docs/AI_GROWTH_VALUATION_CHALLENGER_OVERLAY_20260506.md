# AI-GROWTH-VALUATION-V01 Challenger Overlay Analysis - 2026-05-06

## 목적

Feature ablation에서 유망했던 QuantMarket 기반 challenger를 실제 최신 운영 후보군에 적용해, 기존 기준 모델(`LOCAL_MARKET`) 대비 어떤 후보가 승격/강등되는지 확인했다.

평가 기준:

- 기준일: `2026-05-04`
- Champion/reference: `LOCAL_MARKET`
- Challenger:
  - `QM_MARKET_THEME`
  - `QM_MARKET_RISK`
  - `QM_FULL`
- 대상 후보: admin tracker 최신 weekly ranking 후보 `348`건
- 대상 scope:
  - user models
  - internal models
  - tseries models

## 전체 변화 요약

| challenger | same | upgrade | downgrade | 해석 |
|---|---:|---:|---:|---|
| QM_MARKET_THEME | 314 | 15 | 19 | 변화 폭은 중간. 테마 context가 일부 후보를 재평가 |
| QM_MARKET_RISK | 299 | 8 | 41 | 가장 보수적. risk context가 다수 후보를 강등 |
| QM_FULL | 331 | 9 | 8 | 변화는 작지만 일부 후보를 완만히 조정 |

## 주요 해석

1. `QM_MARKET_THEME`는 후보 선별 challenger로 가장 적합하다.
   - Ablation holdout에서 Top30 성과가 가장 좋았다.
   - 현재 후보 overlay에서도 변화가 과도하지 않다.
   - 테마 context가 강한 일부 후보를 `AVOID -> OVERHEATED`, `OVERHEATED -> FAIR` 등으로 재분류한다.

2. `QM_MARKET_RISK`는 매수 후보 발굴보다 caution filter 성격이 강하다.
   - downgrade가 41건으로 가장 많다.
   - `FAIR -> OVERHEATED`, `OVERHEATED -> AVOID` 형태가 많아 리스크 경고용 보조지표로 더 적합하다.

3. `QM_FULL`은 현재 후보군에서는 변화가 작다.
   - 전체 348건 중 same 331건.
   - 최근 1Y Top-N proxy 성과는 좋았지만, 현재 후보 overlay에서는 선별 변화가 제한적이다.

4. ETF 후보는 현재 주식용 valuation model에서 대부분 out-of-scope다.
   - `T-ETF-V01`은 별도 ETF valuation/price-level overlay가 필요하다.
   - 주식용 AI-GROWTH-VALUATION-V01을 ETF에 그대로 적용하지 않는 것이 맞다.

## 관찰된 주요 승격 후보

중복 모델 노출을 제거하지 않은 raw 기준이며, 같은 종목이 여러 모델에 중복 등장할 수 있다.

| challenger | 종목 | 변화 |
|---|---|---|
| QM_MARKET_THEME | LG이노텍 | AVOID -> OVERHEATED |
| QM_MARKET_THEME | 엘앤에프 | AVOID -> OVERHEATED |
| QM_MARKET_THEME | 서부T&D | OVERHEATED -> FAIR |
| QM_MARKET_THEME | 태광 | OVERHEATED -> FAIR |
| QM_MARKET_RISK | 동진쎄미켐 | OVERHEATED -> FAIR |
| QM_FULL | 서부T&D | OVERHEATED -> FAIR |
| QM_FULL | 비츠로셀 | AVOID -> OVERHEATED |

## 관찰된 주요 강등 후보

| challenger | 종목 | 변화 |
|---|---|---|
| QM_MARKET_THEME | DB하이텍 | OVERHEATED -> AVOID |
| QM_MARKET_THEME | 제주반도체 | OVERHEATED -> AVOID |
| QM_MARKET_THEME | 에코프로 | FAIR -> OVERHEATED |
| QM_MARKET_THEME | 대주전자재료 | FAIR -> OVERHEATED |
| QM_MARKET_RISK | SK텔레콤 | OVERHEATED -> AVOID |
| QM_MARKET_RISK | HD현대일렉트릭 | FAIR -> OVERHEATED |
| QM_MARKET_RISK | 한국전력 | UNDERVALUED -> FAIR |
| QM_FULL | 에코프로 | FAIR -> OVERHEATED |
| QM_FULL | 인텔리안테크 | OVERHEATED -> AVOID |

## 1차 결론

다음 단계 운영 후보는 다음과 같이 나누는 것이 좋다.

- `LOCAL_MARKET`: champion/reference 유지
- `QM_MARKET_THEME`: 주가수준 평가 challenger 1순위
- `QM_MARKET_RISK`: 리스크 경고/caution overlay
- `QM_FULL`: observation only

특히 `QM_MARKET_THEME`는 성과 ablation과 현재 후보 overlay 양쪽에서 모두 의미가 있으므로, shadow scoring 대상으로 올릴 가치가 있다.

## 권장 다음 작업

1. `QM_MARKET_THEME`를 `AI-GROWTH-VALUATION-V01-QM-THEME` challenger로 별도 저장한다.
2. `QM_MARKET_RISK`는 독립 모델보다는 risk overlay tag로 관리한다.
3. 최신 후보 화면에는 당장 교체 신호로 쓰지 말고 다음 3개 값을 추가 관찰한다.
   - champion_state
   - qm_theme_state
   - qm_risk_state
4. 4~8주 live shadow tracking 후 실제 수익률 기준으로 champion 대비 개선 여부를 판단한다.

## 산출물

- `D:\Quant\scripts\build_valuation_ai_challenger_overlay.py`
- `D:\Quant\reports\valuation_ai\valuation_ai_challenger_overlay_20260504.md`
- `D:\Quant\reports\valuation_ai\valuation_ai_challenger_overlay_detail_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_ai_challenger_overlay_summary_20260504.csv`
- `D:\Quant\reports\valuation_ai\valuation_ai_challenger_overlay_20260504.json`
