# FILE: TASK_12_REDBOT_WEB_EXPOSURE_AND_USER_FACING_SCREEN_REFACTOR_20260318.md

# TASK 12. Redbot Web Exposure and User-Facing Screen Refactor
## (웹서비스 노출 화면 / 카피 / 비교표 / 사용자 리포트 연결)

---

# A. TASK 문서용

## 1. 작업 목적
TASK 12의 목적은 현재 구현된 `redbot.co.kr` 웹서비스를
**내부 모델 결과 게시형 구조**에서
**Redbot 사용자용 포트폴리오 추천 서비스 구조**로 개편하는 것입니다.

즉,
- 현재의 `home / today / performance / changes` 페이지와
- `public_data/current` 기반 snapshot 게시 구조를 유지하되,
- 노출 방식과 문구, 데이터 스키마를 사용자 중심으로 바꿔서

**안정형 / 균형형 / 성장형 / 자동전환형**
4개 사용자용 모델을 중심으로 서비스 화면을 재구성하는 것이 이번 TASK의 핵심입니다.

이번 단계가 완료되면,
Redbot는 “모델 결과를 게시하는 서비스”가 아니라
**사용자가 이해할 수 있는 포트폴리오 추천 서비스**로 보일 수 있습니다.

---

## 2. 현재 웹서비스 구조(확인 기준)
현재 업로드된 서비스 폴더 기준으로 웹서비스는 아래 구조를 가지고 있습니다.

### 2.1 웹 계층
- `service_platform/web/app.py`
- `service_platform/web/data_provider.py`
- `service_platform/web/templates/`
  - `home.html`
  - `today.html`
  - `performance.html`
  - `changes.html`
  - `pricing.html`
  - `status.html`
  - 로그인/회원가입/피드백 관련 템플릿

### 2.2 게시 데이터(snapshot) 계층
- `service_platform/web/public_data/current/`
- 현재 주요 snapshot:
  - `daily_recommendations.json`
  - `model_catalog.json`
  - `performance_summary.json`
  - `recent_changes.json`
  - `publish_manifest.json`

### 2.3 schema 계층
- `service_platform/schemas/`
  - `daily_recommendations.schema.json`
  - `model_catalog.schema.json`
  - `performance_summary.schema.json`
  - `recent_changes.schema.json`

### 2.4 현재 한계
현재 구조는 작동은 하지만,
노출 기준이 아직 사용자용 모델이 아니라
**내부 모델 / 추천 종목 / score / reason summary** 중심에 가깝습니다.

따라서 TASK 12에서는
이 기존 구조를 깨지 않으면서,
**사용자용 모델 4종 기준 서비스 화면**으로 번역하는 것이 필요합니다.

---

## 3. 핵심 원칙
1. 현재 Flask + snapshot 게시 구조는 유지합니다.
2. 현재 페이지 라우트(`home`, `today`, `performance`, `changes`)는 최대한 유지합니다.
3. 내부 모델명(`S2`, `S3`, `S4`, `S5`, `S6`, `Router`)은 사용자 기본 화면에서 직접 노출하지 않습니다.
4. 사용자에게는 **안정형 / 균형형 / 성장형 / 자동전환형** 4개 모델을 중심으로 보여줍니다.
5. 기존 내부 snapshot 구조는 가능한 한 호환을 유지하되, 사용자용 snapshot을 추가하거나 확장합니다.
6. A안 범위 내 서비스 완성이 목표이므로, B안 확장 요소는 넣지 않습니다.
7. 웹 카피는 기술 설명이 아니라 **포트폴리오 추천 서비스 언어**로 바꿉니다.

---

## 4. 이번 TASK의 핵심 목표
이번 TASK 12에서 달성해야 할 목표는 아래와 같습니다.

1. `home.html`를 Redbot 서비스 랜딩 구조로 개편한다.
2. `today.html`를 사용자용 포트폴리오 추천 리포트형 화면으로 개편한다.
3. `performance.html`를 사용자용 모델 비교형 화면으로 개편한다.
4. `changes.html`를 포트폴리오 변경/추천 변경 중심 화면으로 개편한다.
5. 기존 snapshot 구조 위에 사용자용 snapshot 구조를 추가 또는 확장한다.
6. 사용자용 모델 4종과 서비스 profile 구조를 웹에 반영한다.
7. 웹 카피/비교표/리포트 구조를 고정한다.

---

## 5. 페이지별 개편 방향

### 5.1 `home.html`
현재 역할:
- 서비스 소개 + 모델 카탈로그 성격

개편 목표:
- Redbot 랜딩 페이지 역할 강화
- 사용자용 모델 4종을 전면에 배치
- 각 모델의 성격/추천 대상/핵심 특징을 카드형으로 노출
- “오늘의 추천 보기”, “성과 비교 보기”, “플랜 보기” CTA 정리

필수 섹션:
1. Hero section
2. 사용자용 모델 4종 소개 카드
3. Redbot가 어떻게 추천하는지 간단 설명
4. 최근 성과/핵심 수치 요약
5. 플랜/가입 유도

---

### 5.2 `today.html`
현재 역할:
- 내부 모델별 추천 종목 나열

개편 목표:
- 사용자용 모델 기준의 **오늘의 추천 리포트** 화면으로 전환
- 모델명 / 시장 판단 / 추천 이유 / 포트폴리오 구성 / 최근 성과 / 변경사항 중심

필수 섹션:
1. 오늘의 추천 헤더
2. 현재 추천 모델 요약
3. 현재 시장 판단
4. 추천 포트폴리오 구성
5. 추천 이유
6. 리스크 수준
7. 직전 대비 변화
8. 유의사항

중요:
- 기본 노출은 사용자용 모델 기준
- 내부 모델 세부 정보는 숨김
- 필요 시 entitlements에 따라 상세 보기 수준 차등 제공 가능

---

### 5.3 `performance.html`
현재 역할:
- model_id 기준 CAGR / MDD / Sharpe 표시

개편 목표:
- 사용자용 모델 4종 비교 화면으로 전환
- 안정형 / 균형형 / 성장형 / 자동전환형 기준 비교표 제공
- 사용자가 “내게 맞는 모델이 무엇인지” 판단할 수 있게 구성

필수 섹션:
1. 사용자용 모델 비교표
2. 성과 요약 카드
3. 기간별 성과표 (A안 포맷)
4. 리스크 수준 비교
5. 모델별 설명/추천 대상

중요:
- 내부 모델 기준 비교는 숨김 또는 관리자 전용
- 사용자용 기본 화면은 4개 상품 비교 중심

---

### 5.4 `changes.html`
현재 역할:
- 추천 변경 이벤트 나열

개편 목표:
- 사용자 입장에서 “이번 추천이 왜 달라졌는지” 설명하는 화면으로 전환
- 포트폴리오 변경 내역과 변경 이유를 쉽게 보여줌

필수 섹션:
1. 오늘/최근 변경 요약
2. 비중 증가 자산
3. 비중 감소 자산
4. 모델 변경 발생 여부
5. 변경 이유 요약

중요:
- `new_entry/exit/rank_up/rank_down` 같은 이벤트 코드는 내부적으로 유지하되
- 사용자 노출 문구는 쉬운 설명으로 번역

---

## 6. snapshot 구조 개편 방향

## 6.1 현재 유지 대상
기존 snapshot 파일은 가능하면 유지합니다.
- `daily_recommendations.json`
- `model_catalog.json`
- `performance_summary.json`
- `recent_changes.json`

이유:
- 기존 publisher / validator / data_provider 호환성 유지

## 6.2 추가 또는 확장 권장 대상
아래 사용자용 snapshot을 추가하는 방식을 권장합니다.

### 권장 추가 파일
- `user_model_catalog.json`
- `user_recommendation_report.json`
- `user_performance_summary.json`
- `user_recent_changes.json`

또는 기존 파일 확장 방식도 가능하지만,
A안 서비스 완성을 빠르게 하려면
**기존 내부용 snapshot 유지 + 사용자용 snapshot 추가** 방식이 더 안전합니다.

---

## 7. 사용자용 snapshot 스키마 초안

### 7.1 `user_model_catalog.json`
목적:
- 사용자용 모델 4종의 메타데이터 제공

필드 예시:
- `user_model_id`
- `user_model_name`
- `service_profile`
- `summary`
- `risk_label`
- `target_user_type`
- `primary_asset_mix`
- `is_active`

### 7.2 `user_recommendation_report.json`
목적:
- `today.html`용 추천 리포트 데이터 제공

필드 예시:
- `as_of_date`
- `generated_at`
- `current_market_regime`
- `reports` (4개 사용자 모델 또는 현재 사용자에게 추천된 모델)
  - `user_model_name`
  - `service_profile`
  - `summary_text`
  - `market_view`
  - `allocation_items`
  - `rationale_items`
  - `risk_level`
  - `performance_summary`
  - `change_log`
  - `disclaimer_text`

### 7.3 `user_performance_summary.json`
목적:
- 사용자용 모델 4종 비교

필드 예시:
- `models`
  - `user_model_name`
  - `service_profile`
  - `risk_label`
  - `performance_cards`
  - `period_table`
  - `note`

### 7.4 `user_recent_changes.json`
목적:
- 사용자용 추천 변경 설명

필드 예시:
- `as_of_date`
- `changes`
  - `user_model_name`
  - `change_type`
  - `summary`
  - `increase_items`
  - `decrease_items`
  - `reason_text`

---

## 8. app / data_provider 변경 방향

### 8.1 `data_provider.py`
필요 작업:
- 기존 snapshot 로딩 유지
- 사용자용 snapshot 로딩 추가
- snapshot 누락 시 fallback 처리
- 내부용 / 사용자용 payload 동시 제공 가능 구조

### 8.2 `app.py`
필요 작업:
- `home`, `today`, `performance`, `changes` 라우트에서
  사용자용 payload를 우선 사용하도록 변경
- 내부 관리자/디버그 모드에서는 기존 내부 payload 확인 가능하도록 열어둘 수 있음
- entitlements에 따라
  - 미리보기
  - starter
  - premium
  노출 깊이 차등 가능

---

## 9. 템플릿 개편 범위

### 9.1 필수 수정 파일
- `service_platform/web/templates/home.html`
- `service_platform/web/templates/today.html`
- `service_platform/web/templates/performance.html`
- `service_platform/web/templates/changes.html`

### 9.2 선택 수정 파일
- `base.html`
- 스타일 파일 / static 리소스
- pricing 관련 카피 정리

---

## 10. 카피/문구 표준
아래 사용자용 모델 카피를 웹 화면 기준 표준으로 사용합니다.

### 안정형
- 제목: `안정형`
- 설명: `시장 하락에 대비해 채권, 달러, 금 등 방어 자산 비중을 높인 포트폴리오`

### 균형형
- 제목: `균형형`
- 설명: `주식과 ETF를 함께 활용해 수익과 안정의 균형을 추구하는 포트폴리오`

### 성장형
- 제목: `성장형`
- 설명: `상승 추세를 적극 활용해 장기 수익 확대를 추구하는 포트폴리오`

### 자동전환형
- 제목: `자동전환형`
- 설명: `시장 상황에 따라 포트폴리오 구성을 자동으로 전환하는 동적 운용형 포트폴리오`

---

## 11. 구현 범위

### 11.1 스키마
- 사용자용 snapshot schema 추가
- validator 연동

### 11.2 publisher
- 사용자용 report snapshot 생성
- current/published 구조에 반영

### 11.3 web
- data_provider 확장
- app route payload 교체
- 템플릿 개편

### 11.4 copy
- 사용자용 모델 설명
- 화면용 문구
- CTA / 비교표 문구

---

## 12. 권장 구현 파일
- `service_platform/schemas/user_model_catalog.schema.json`
- `service_platform/schemas/user_recommendation_report.schema.json`
- `service_platform/schemas/user_performance_summary.schema.json`
- `service_platform/schemas/user_recent_changes.schema.json`
- `service_platform/web/templates/home.html` (수정)
- `service_platform/web/templates/today.html` (수정)
- `service_platform/web/templates/performance.html` (수정)
- `service_platform/web/templates/changes.html` (수정)
- `service_platform/web/data_provider.py` (수정)
- `service_platform/web/app.py` (수정)
- `service_platform/publishers/` 하위 사용자용 snapshot 생성 로직 추가
- `docs/REDBOT_WEB_COPY_GUIDE.md`
- `docs/REDBOT_SCREEN_STRUCTURE.md`

---

## 13. 완료 기준 (Definition of Done)
아래를 모두 만족하면 완료입니다.

1. `home / today / performance / changes` 화면이 사용자용 모델 4종 기준으로 재구성된다.
2. 사용자용 snapshot 구조가 추가 또는 확장된다.
3. 기존 snapshot 구조와의 호환성이 유지된다.
4. 내부 모델명이 사용자 기본 화면에 직접 노출되지 않는다.
5. today 페이지가 사용자용 추천 리포트 구조를 반영한다.
6. performance 페이지가 사용자용 모델 비교 구조를 반영한다.
7. changes 페이지가 사용자 친화적 변경 설명 구조를 반영한다.
8. 향후 Redbot 서비스 운영에 바로 투입 가능한 수준의 카피와 화면 구조가 준비된다.

---

## 14. 이번 TASK에서 하지 않을 것
- 전체 프론트 프레임워크 교체
- 실시간 websocket 구조
- 결제 구조 변경
- 인증 구조 변경
- 새 모델 개발
- Router 로직 변경
- B안 멀티에셋 확장 작업

---

## 15. 다음 TASK
- TASK 13: Redbot 일일 추천 발행 구조 및 운영 플로우 정리
- TASK 14: 사용자용 추천 결과 API / 스냅샷 응답 표준화
- 이후: 웹 연동 고도화 / 알림 / PDF 발행 자동화

---

# B. Codex 실행지시문

## 작업명
Redbot Web Exposure and User-Facing Screen Refactor

## 현재 상태
현재 서비스는 Flask + snapshot 게시 구조로 운영된다.

핵심 구조:
- `service_platform/web/app.py`
- `service_platform/web/data_provider.py`
- `service_platform/web/templates/`
  - `home.html`
  - `today.html`
  - `performance.html`
  - `changes.html`
- `service_platform/web/public_data/current/`
  - `daily_recommendations.json`
  - `model_catalog.json`
  - `performance_summary.json`
  - `recent_changes.json`
- `service_platform/schemas/`
  - 기존 snapshot schema들

현재 한계:
- today/performance/changes 화면이 아직 내부 모델/추천종목 게시형에 가깝다
- 사용자용 모델 4종 기준 화면 구조가 부족하다

이제 TASK 12에서는
현재 웹서비스 구조를 유지하면서,
사용자용 모델 4종 기준의 Redbot 서비스 화면으로 개편한다.

## 중요 원칙
1. Flask 구조와 현재 라우트는 최대한 유지할 것
2. 기존 snapshot 파일은 가능하면 유지하고, 사용자용 snapshot을 추가하는 방향을 우선할 것
3. 내부 모델명(`S2/S3/S4/S5/S6/Router`)은 사용자 기본 화면에 직접 노출하지 말 것
4. 사용자용 모델 4종 중심으로 화면을 재구성할 것
5. A안 서비스 완성이 목표이며 B안 확장 요소는 넣지 말 것
6. 기존 publisher / validator / data_provider 호환성을 최대한 유지할 것

## 사용자용 모델 4종
- `안정형`
- `균형형`
- `성장형`
- `자동전환형`

## 화면별 구현 목표

### 1. `home.html`
- Redbot 서비스 랜딩 구조로 개편
- 사용자용 모델 4종 카드 노출
- 모델 설명/추천 대상/핵심 특징 표시
- CTA 정리:
  - 오늘의 추천 보기
  - 성과 비교 보기
  - 플랜 보기

### 2. `today.html`
- 내부 모델 추천 종목 나열형에서 사용자용 추천 리포트형으로 개편
- 필수 섹션:
  - 오늘의 추천 헤더
  - 현재 추천 모델 요약
  - 현재 시장 판단
  - 추천 포트폴리오 구성
  - 추천 이유
  - 리스크 수준
  - 직전 대비 변화
  - 유의사항

### 3. `performance.html`
- 내부 model_id 기준 성과표에서 사용자용 모델 4종 비교형으로 개편
- 필수 섹션:
  - 사용자용 모델 비교표
  - 성과 카드
  - 기간별 성과표
  - 리스크 수준 비교
  - 모델별 설명

### 4. `changes.html`
- 이벤트 나열형에서 사용자 친화적 포트폴리오 변경 설명형으로 개편
- 필수 섹션:
  - 최근 변경 요약
  - 비중 증가 자산
  - 비중 감소 자산
  - 변경 이유

## snapshot 개편 요구사항

### 기존 파일 유지
가능하면 아래는 유지할 것.
- `daily_recommendations.json`
- `model_catalog.json`
- `performance_summary.json`
- `recent_changes.json`

### 사용자용 파일 추가 권장
- `user_model_catalog.json`
- `user_recommendation_report.json`
- `user_performance_summary.json`
- `user_recent_changes.json`

### 사용자용 schema 추가 권장
- `service_platform/schemas/user_model_catalog.schema.json`
- `service_platform/schemas/user_recommendation_report.schema.json`
- `service_platform/schemas/user_performance_summary.schema.json`
- `service_platform/schemas/user_recent_changes.schema.json`

## data_provider / app 변경 요구사항
1. `data_provider.py`
- 기존 snapshot 로딩 유지
- 사용자용 snapshot 로딩 추가
- 누락 시 fallback 처리

2. `app.py`
- `home`, `today`, `performance`, `changes` 라우트에서
  사용자용 payload를 우선 사용하도록 변경
- 내부 관리자/디버그 용도는 기존 payload 열람 가능하게 해도 됨
- entitlements에 따라 노출 깊이 차등 가능

## 필수 수정 파일
- `service_platform/web/templates/home.html`
- `service_platform/web/templates/today.html`
- `service_platform/web/templates/performance.html`
- `service_platform/web/templates/changes.html`
- `service_platform/web/data_provider.py`
- `service_platform/web/app.py`

## 권장 추가 파일
- `service_platform/schemas/user_model_catalog.schema.json`
- `service_platform/schemas/user_recommendation_report.schema.json`
- `service_platform/schemas/user_performance_summary.schema.json`
- `service_platform/schemas/user_recent_changes.schema.json`
- 사용자용 snapshot 생성 publisher 코드
- `docs/REDBOT_WEB_COPY_GUIDE.md`
- `docs/REDBOT_SCREEN_STRUCTURE.md`

## 사용자용 카피 표준
### 안정형
- `시장 하락에 대비해 채권, 달러, 금 등 방어 자산 비중을 높인 포트폴리오`

### 균형형
- `주식과 ETF를 함께 활용해 수익과 안정의 균형을 추구하는 포트폴리오`

### 성장형
- `상승 추세를 적극 활용해 장기 수익 확대를 추구하는 포트폴리오`

### 자동전환형
- `시장 상황에 따라 포트폴리오 구성을 자동으로 전환하는 동적 운용형 포트폴리오`

## 완료 기준
1. `home / today / performance / changes`가 사용자용 모델 4종 기준으로 재구성된다
2. 사용자용 snapshot 구조가 추가 또는 확장된다
3. 기존 snapshot과 호환성이 유지된다
4. 내부 모델명이 사용자 기본 화면에 직접 노출되지 않는다
5. today 페이지가 사용자용 추천 리포트 구조를 반영한다
6. performance 페이지가 사용자용 모델 비교 구조를 반영한다
7. changes 페이지가 사용자 친화적 변경 설명 구조를 반영한다
8. 운영에 바로 투입 가능한 카피와 화면 구조가 준비된다

## 이번 TASK에서 하지 말 것
- 프론트 프레임워크 교체
- 실시간 websocket 구조
- 결제 구조 변경
- 인증 구조 변경
- 새 모델 개발
- Router 로직 변경
- B안 멀티에셋 확장 작업

## 완료 후 보고 형식
1. 수정/추가 파일 목록
2. 각 파일 역할
3. 화면별 변경 요약
4. snapshot/schema 변경 요약
5. 기존 구조와의 호환성 설명
6. 실행 방법
7. validate / smoke test 방법
8. 남은 리스크/주의사항
9. 다음 작업 제안
- TASK 13: Redbot 일일 추천 발행 구조 및 운영 플로우 정리
- TASK 14: 사용자용 추천 결과 API / 스냅샷 응답 표준화

---

# C. Codex 개발 기본방향

- 이번 TASK 12의 핵심은 새 웹서비스를 만드는 것이 아니라, 현재 Flask + snapshot 구조를 Redbot 사용자 서비스형으로 번역하는 것이다.
- 기존 라우트와 게시 구조는 최대한 유지하고, 사용자용 snapshot과 화면을 덧붙이는 방식으로 간다.
- 내부 모델 결과를 직접 보여주지 말고, 사용자용 모델 4종 기준의 추천 리포트와 비교 화면으로 재구성한다.
- `today.html`는 추천 종목 게시판이 아니라 추천 리포트 화면이어야 한다.
- `performance.html`는 내부 모델 성과판이 아니라 사용자용 모델 비교판이어야 한다.
- `changes.html`는 내부 이벤트 로그가 아니라 포트폴리오 변경 설명 화면이어야 한다.
- A안 서비스 완성이 목표이므로, 화면 구조와 카피는 단순하고 명확하게 유지한다.