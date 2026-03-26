# QUANTSERVICE_QUANT_MODEL_COPY_UPDATE_HANDOFF_20260325.md

## 목적
QuantService 요청에 따라 Quant current snapshot에 화면 표시용 단순 필드가 추가되었다.
이번 문서는 QuantService가 `model_metadata`를 깊게 파싱하지 않고도, 새 별칭 필드를 바로 사용해 모델 정체성과 변경 배지를 안정적으로 표시하도록 연결 기준을 정리한 것이다.

---

## 사용 데이터
- `D:\Quant\service_platform\web\public_data\current\user_model_catalog.json`
- `D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json`
- `D:\Quant\service_platform\web\public_data\current\user_performance_summary.json`
- `D:\Quant\service_platform\web\public_data\current\user_recent_changes.json`
- `D:\Quant\service_platform\web\public_data\current\publish_manifest.json`

---

## 이번에 Quant에서 추가된 필드

### 1. 공통 별칭 필드
아래 필드가 catalog / snapshot report / performance summary에 추가되었다.

- `quant_model_name`
  - 예: `안정형 퀀트투자 모델`
- `model_definition_line`
  - 예: `공개 기준 기반 퀀트투자 모델`
- `model_definition_detail`
  - 예: `변동성 완화와 자산 방어를 우선하는 모델 포트폴리오를 산출합니다.`

### 2. 변경내역 필드
아래 필드가 `user_recent_changes.json`의 `changes[]`에 추가되었다.

- `quant_model_name`
- `change_badge_label`
  - 현재 기본값: `주간 모델 조정`

---

## QuantService 반영 방법

### Home / 모델 카드
권장 사용 순서:
1. 제목: `quant_model_name`
2. 한 줄 정의: `model_definition_line`
3. 보조 설명: `model_definition_detail`

예시:
- 제목: `안정형 퀀트투자 모델`
- 배지/서브타이틀: `공개 기준 기반 퀀트투자 모델`
- 보조 문구: `변동성 완화와 자산 방어를 우선하는 모델 포트폴리오를 산출합니다.`

### Today / 상세 모델 정보
권장 사용 순서:
1. 제목: `quant_model_name`
2. 설명 1줄: `summary_text` 또는 `model_definition_line`
3. 상세 보조 설명: `model_definition_detail`

### Performance
권장 사용 순서:
1. 제목: `quant_model_name`
2. 보조 설명: `model_definition_line`
3. 모델 설명: `model_definition_detail`

기존 `performance_subject_name`, `performance_subject_type`, `portfolio_generation_basis`도 계속 함께 사용 가능하다.

### Changes
권장 사용 순서:
1. 제목: `quant_model_name`
2. 배지: `change_badge_label`
3. 설명: `change_basis_desc`, `change_reason_desc`

예시:
- `균형형 퀀트투자 모델`
- 배지: `주간 모델 조정`

---

## 구현 원칙
1. QuantService는 새 별칭 필드를 그대로 표시한다.
2. 문구를 프론트에서 다시 조합하거나 축약하지 않아도 된다.
3. 투자 권유형 표현은 새로 만들지 않는다.
4. 기존 `model_metadata`는 그대로 유지되므로, 필요 시 더 자세한 화면에서만 사용하면 된다.

---

## 최소 체크리스트
- [ ] 카드/상세 제목을 `quant_model_name` 우선으로 반영
- [ ] 모델 정의 한 줄로 `model_definition_line` 반영
- [ ] 모델 상세 보조 문구로 `model_definition_detail` 반영
- [ ] 변경내역 배지에 `change_badge_label` 반영
- [ ] 기존 `performance_subject_*`, `change_*` 메타와 충돌 없이 함께 사용
