# QUANTSERVICE_QUANT_MODEL_IDENTITY_UPDATE_HANDOFF_20260325.md

## 목적
Quant 쪽 public payload에 `퀀트투자 모델` 정체성을 명확하게 드러내는 `model_metadata` 및 관련 설명 필드가 추가되었다.
이번 작업의 목적은 QuantService가 기존 화면 구조를 크게 바꾸지 않으면서도, REDBOT이 단순 포트폴리오 나열 서비스가 아니라 `멀티애셋 데이터 기반 퀀트투자 모델 서비스`라는 점을 사용자가 자연스럽게 인식하도록 화면 문구와 표시 방식을 보정하는 것이다.

---

## 이번에 Quant에서 반영된 내용
사용 데이터는 기존 current snapshot 경로를 그대로 사용한다.

- `D:\Quant\service_platform\web\public_data\current\user_model_catalog.json`
- `D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json`
- `D:\Quant\service_platform\web\public_data\current\user_performance_summary.json`
- `D:\Quant\service_platform\web\public_data\current\user_recent_changes.json`
- `D:\Quant\service_platform\web\public_data\current\publish_manifest.json`

추가된 핵심 필드:
- `model_metadata`
- `performance_subject_name`
- `performance_subject_type`
- `portfolio_generation_basis`
- `change_subject_name`
- `change_basis_desc`
- `change_reason_desc`

핵심 문구 축:
- `멀티애셋 데이터 기반 퀀트투자 모델`
- `공개 기준 기반 퀀트투자 모델`
- `주간 브리핑용 퀀트투자 모델`
- `모델 포트폴리오를 산출하는 퀀트투자 모델`

---

## QuantService에서 수정해야 할 사항

### 1. 모델명 표시 보강
기존:
- `안정형`
- `균형형`
- `성장형`
- `자동전환형`

수정 권장:
- 카드 headline 또는 상세 headline에서 `model_metadata.model_display_name` 우선 사용
- 예:
  - `안정형 퀀트투자 모델`
  - `균형형 퀀트투자 모델`
  - `성장형 퀀트투자 모델`
  - `자동전환형 퀀트투자 모델`

단, 메뉴/탭처럼 짧아야 하는 곳은 기존 짧은 이름 유지 가능
- 예: 탭 = `안정형`
- 상세 제목 = `안정형 퀀트투자 모델`

### 2. 모델 소개 문구 교체
기존 summary/note를 그대로 쓰는 대신 아래 우선순위를 사용한다.

우선순위:
1. `model_metadata.model_one_line_desc`
2. `summary_text`
3. `note`

예시:
- `방어자산과 현금성 비중을 함께 활용하는 멀티애셋 데이터 기반 퀀트투자 모델`
- `주식과 ETF를 함께 사용하는 공개 기준 기반 퀀트투자 모델`

### 3. 모델 상세에서 정체성 문구 노출
상세 페이지 또는 카드 하단에 아래 정보 중 2~4개를 짧게 노출한다.

권장 필드:
- `model_metadata.model_family_name`
- `model_metadata.model_public_type`
- `model_metadata.model_brief_type`
- `model_metadata.model_portfolio_type`
- `model_metadata.model_scope_desc`

권장 UI 예:
- `멀티애셋 데이터 기반 퀀트투자 모델`
- `공개 기준 기반 퀀트투자 모델`
- `주간 브리핑용 퀀트투자 모델`
- `개별 맞춤형이 아닌 동일 기준의 공개형 모델 정보`

### 4. 성과 화면 문구 수정
성과 카드/표에 아래 필드를 반영한다.
- `performance_subject_name`
- `performance_subject_type`
- `portfolio_generation_basis`

권장 표현 예:
- `안정형 퀀트투자 모델의 백테스트 성과`
- `모델 포트폴리오를 산출하는 퀀트투자 모델 규칙 적용 결과`

기존 `전략 성과`, `추천 성과`, `오늘의 성과` 같은 표현이 남아 있으면 제거한다.

### 5. 변경내역 화면 문구 수정
변경내역에는 아래 필드를 사용한다.
- `change_subject_name`
- `change_basis_desc`
- `change_reason_desc`

권장 표현 예:
- `균형형 퀀트투자 모델 변경내역`
- `주간 기준일 기준으로 모델 포트폴리오 산출 결과가 변경되었습니다.`
- `시장 상태와 공개 규칙 변화에 따라 퀀트투자 모델의 자산 비중이 조정되었습니다.`

기존 `전략 변경`, `추천 변경`, `대응 변경` 같은 표현이 있으면 제거한다.

### 6. 용어 치환 가이드
외부 노출 화면에서 아래 치환을 적용한다.

권장:
- 전략 -> 모델
- 전략 결과 -> 모델 정보
- 전략 포트폴리오 -> 모델 포트폴리오
- allocation result -> 모델 포트폴리오
- 전략 성과 -> 모델 성과 설명
- rebalance output -> 주간 모델 기준안

지양:
- 오늘의 추천
- 추천 전략
- 추천 대응
- 대응 가이드
- 매수 전략
- 매도 전략

### 7. 기존 flat field는 계속 사용 가능
이번 변경은 breaking change가 아니다.
다음 flat field는 기존대로 사용 가능하다.
- `summary_text`
- `allocation_items`
- `rationale_items`
- `change_log`
- `performance_summary`

즉 QuantService는 기존 구조를 유지하되, `model_metadata`를 추가 활용해 표현만 보강하면 된다.

---

## 화면별 반영 권장

### Home
- 카드 제목: `model_metadata.model_display_name`
- 카드 설명: `model_metadata.model_one_line_desc`
- 작은 배지 1~2개:
  - `model_metadata.model_public_type`
  - `model_metadata.model_brief_type`

### Today
- 상단 제목: `현재 기준 모델 정보`
- 모델명: `model_metadata.model_display_name`
- 설명: `model_metadata.model_one_line_desc`
- 보조 설명: `model_metadata.model_scope_desc`

### Performance
- 제목: `{performance_subject_name} 성과 설명`
- 보조 설명: `performance_subject_type`
- 하단 주석: `portfolio_generation_basis`

### Changes
- 제목: `{change_subject_name} 변경내역`
- 본문 설명:
  - `change_basis_desc`
  - `change_reason_desc`

---

## 구현 원칙
1. QuantService는 Quant 계산 로직을 재구현하지 않는다.
2. raw DB 직접 조인하지 않는다.
3. current snapshot만 읽고 표현만 수정한다.
4. 새 표현은 `퀀트투자 모델`, `모델 포트폴리오`, `브리핑`, `기준안` 중심으로 유지한다.
5. 투자권유성 문구를 새로 생성하지 않는다.

---

## 최소 작업 체크리스트
- [ ] 카드/상세 제목을 `model_display_name` 기준으로 교체
- [ ] 설명 문구를 `model_one_line_desc` 우선으로 교체
- [ ] 성과 페이지에 `performance_subject_*` 반영
- [ ] 변경내역 페이지에 `change_*` 메타 반영
- [ ] `전략/추천/대응` 표현 제거 또는 축소
- [ ] `퀀트투자 모델` 정체성 문구를 최소 1회 이상 노출
