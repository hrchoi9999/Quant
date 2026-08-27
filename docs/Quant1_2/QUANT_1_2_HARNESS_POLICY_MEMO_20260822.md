# Quant 1.2 Harness Policy Memo

- 작성일: `2026-08-22`
- 대상: `Harness / Update Pipeline / Quant weekday-weekend operation`
- 상태: `operating_policy_notice`

## 1. 목적

Quant 1.2 후보를 즉시 운영 반영하지 않고, Quant 1.0 운영과 Quant 1.2 병렬 성능 검증을 분리하기 위한 하네스 운영 원칙입니다.

## 2. 운영 범위

- `Quant 1.0`만 현재 운영 범위입니다.
- `Quant 1.2`는 운영 범위가 아니라 연구/shadow/live 검증 범위입니다.
- `Quant 1.1`, `Quant 2.x`도 별도 명시 승인 전까지 운영 범위에 포함하지 않습니다.

## 3. Quant 1.2 처리 원칙

- Quant 1.2 채택 후보(`S2, S3, S3_CORE2, S3_ACCEL_V01, S4, S5, S6`)는 즉시 운영 반영하지 않습니다.
- Quant 1.2 후보는 frozen/immutable 상태로 취급합니다.
- shadow 기간 중 모델 출력에 영향을 주는 로직, 파라미터, 유니버스, 점수화, 리밸런싱, 위험 규칙 변경은 Quant 1.2 범위에서 금지합니다.
- 이런 변경은 별도 신규 버전 후보(기본적으로 `Quant 1.3`)로 분리해야 합니다.
- 하네스는 freeze manifest의 후보 코드·선정 설정·shadow 실행 로직 fingerprint를 readiness의 `candidate_immutable_fingerprint_matches`로 검증합니다.
- fingerprint 불일치 시 해당 Quant 1.2 성능 비교는 무효 처리하고 `blocked_quant_1_2_immutable_fingerprint_mismatch`로 보고하며, 기존 1.2 shadow를 초기화하거나 덮어쓰지 않습니다.
- `2026-08-22` 동결 이후 최소 `180 calendar days`의 live shadow가 필수입니다.
- 주간형은 최소 `180일 + 약 26회 이상 주간 decision`이 필요합니다.
- 월간형은 최소 `180일 + 6회 monthly decision`이 필요합니다.
- 기간 조건 외에도 수익률 / MDD / 변동성 / turnover 위험 gate를 모두 통과해야 합니다.
- 가장 빠른 통합 재검토 가능일은 `2027-02-18`입니다.

## 4. 하네스 적용 원칙

- WD/WE 하네스 active scope는 계속 `Quant 1.0 only`로 유지합니다.
- Quant 1.2를 current payload, admin current, validation current, publish 범위에 자동 포함하지 않습니다.
- Quant 1.2는 `shadow/forward/live-evidence comparison` 대상으로만 추적합니다.
- 하네스 보고서에서는 가능하면 아래를 분리 표기합니다.
  - `Quant 1.0 운영 성과 / 운영 freshness`
  - `Quant 1.2 후보 성과 / live shadow gate 진행 상태`

## 5. 금지 사항

- Quant 1.2 canonical 운영 코드 전환
- Quant 1.2 DB current 전환
- Quant 1.2 registry active scope 전환
- Quant 1.2 current payload / public GCS publish
- `S2 1.2` 같은 신규 운영 모델 코드 생성

## 6. 허용 사항

- Quant 1.2 설계 문서
- canonical backport 매핑
- provenance / rollback 계약 정의
- 비활성 dry-run 검증
- 정기 입력 데이터 갱신
- 재현 실행
- 성능 기록
- 모니터링/하네스의 비의미적 수정
- frozen shadow/live 성능 추적
- Quant 1.0 대비 병렬 성능 비교 보고

## 7. 운영 반영 조건

아래가 모두 충족되기 전에는 하네스가 Quant 1.2를 운영 범위로 전환하지 않습니다.

1. 최소 `180일` live shadow 충족
2. decision 수 충족
3. 사전 정의된 위험 gate 통과
4. readiness `8/8 PASS`
5. 전 모델 최종 판정 완료
6. 사용자 최종 승인

## 8. 한 줄 요약

하네스는 당분간 `Quant 1.0 운영 유지 + Quant 1.2 병렬 성능 추적` 원칙으로 동작합니다.
