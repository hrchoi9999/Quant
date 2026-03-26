# MARKET_ANALYSIS_WEB_PAYLOAD_SPEC_20260323.md

## 1. 목적

이 문서는 시장 분석 기능의 웹서비스 전달 payload 구조를 정의한다.

## 2. 파일 / API 구조 제안

### snapshot 파일

- `market_analysis_summary.json`
- `market_analysis_detail.json`
- `market_analysis_manifest.json`

### API 제안

- `GET /api/v1/market-analysis/summary?market=KR`
- `GET /api/v1/market-analysis/detail?market=KR`
- `GET /api/v1/market-analysis/today-bridge?market=KR`

## 3. summary payload

용도:
- 메인페이지
- 오늘의 추천 페이지 상단 요약

예시 구조:

```json
{
  "market": "KR",
  "asof": "2026-03-23T14:00:00+09:00",
  "state_label": "약보합",
  "state_score": -0.6,
  "summary_line": "지수는 버티지만 시장 내부 확산은 약한 편입니다.",
  "change_vs_prev": "중립 -> 약보합",
  "top_signals": [
    "코스닥 약세",
    "달러 강세"
  ],
  "action_hint": "추격 매수보다 분할 접근이 적합합니다."
}
```

## 4. detail payload

용도:
- 시장 분석 상세 페이지

예시 구조:

```json
{
  "market": "KR",
  "asof": "2026-03-23T14:00:00+09:00",
  "state": {
    "label": "약보합",
    "score": -0.6,
    "prev_label": "중립",
    "change_direction": "weaker"
  },
  "components": {
    "trend": {
      "score": -0.2,
      "label": "시장 방향",
      "summary": "코스피는 버티지만 코스닥은 아직 약합니다."
    },
    "breadth": {
      "score": -0.7,
      "label": "시장 건강도",
      "summary": "상승 종목 확산이 충분하지 않습니다."
    },
    "risk": {
      "score": -0.5,
      "label": "시장 흔들림",
      "summary": "최근 변동성이 다소 높은 편입니다."
    },
    "defensive_flow": {
      "score": -0.9,
      "label": "방어자산 선호도",
      "summary": "달러와 금이 상대적으로 강한 흐름입니다."
    }
  },
  "metrics": {
    "kospi_1d_ret": 0.003,
    "kospi_20d_ret": 0.024,
    "kosdaq_20d_ret": -0.011,
    "above_20dma_ratio": 0.38,
    "above_60dma_ratio": 0.31,
    "realized_vol_20d": 0.019
  },
  "positive_points": [
    "대형주 추세 유지",
    "코스피 20일선 상회"
  ],
  "warning_points": [
    "코스닥 약세",
    "시장 확산도 저하",
    "달러 강세"
  ],
  "action_guide": "신규 매수는 분할 접근이 적합합니다.",
  "ai_note": {
    "enabled": false,
    "summary": null
  }
}
```

## 5. today_bridge payload

용도:
- 오늘의 추천 페이지에서 추천 모델과 연결

예시 구조:

```json
{
  "market": "KR",
  "asof": "2026-03-23T14:00:00+09:00",
  "state_label": "약보합",
  "state_score": -0.6,
  "recommended_tone": "균형 대응",
  "bridge_text": "시장 건강도가 약하고 방어자산 선호가 커 균형형 또는 자동전환형 접근이 유리합니다."
}
```

## 6. 40~60대 사용자용 표현 원칙

복잡한 기술 용어보다 아래 레이블을 우선한다.

- 시장 방향
- 시장 건강도
- 시장 흔들림
- 방어자산 선호도
- 오늘의 시장 판단
- 오늘의 대응 가이드

## 7. AI 해설 사용 원칙

- AI는 `detail payload`의 보조 필드로만 사용
- 시장 상태 판단 자체는 Quant 계산 결과 사용
- AI 실패 시 payload는 정상 생성되어야 함
- AI note는 선택 항목으로 처리
