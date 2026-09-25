# Quant 총괄 운영 인수인계 — 새 대화 재개용

작성·대조 기준: **2026-09-24 20:43~20:45 KST**. 최종 개발 검수 기준은 같은 날 20:34:55 KST의 `MASTER_ACCEPTANCE.json`입니다. 이 문서는 이후 변경을 자동 반영하지 않는 시점 기록입니다.

원본 작업: **Quant 2.5 Develope**, `01a0716f-1eec-7721-b951-10e408f15970` / 작업 폴더 `D:/Quant`.

목적: 기존 대화의 운영 원칙·사용자 결정·개발 내용·검수 근거·보류 사유를 보존하고, 새 대화에서 완료 작업을 반복하지 않고 이어가기 위한 인수인계입니다. 새 대화를 자동 생성하거나 운영 실행을 새로 승인하는 문서는 아닙니다. 기존 유효한 사용자 승인도 취소하지 않습니다.

## 1. 가장 먼저 알아야 할 현재 상태

1. **Q25 웹사이트 전환 자체는 이미 완료됐습니다.** 지금은 최초 배포를 준비하는 단계가 아니라, 별도 과업인 **실제 모의운용과 Live 성과 연결**을 마무리하는 단계입니다.
2. **원천 검증 성과의 생산 → QS 소비·화면 → 교차 검수·OS 인수 코드는 3/3 완료입니다.** 마지막 작업은 로컬 개발·검수였으며, 이 V2 코드를 운영에 배포하거나 자료를 GCS에 게시하지 않았습니다.
3. **실제 사전계획 기반 모의운용은 아직 시작되지 않았습니다.** 원장에는 목표 event 6건만 있고 체결·미체결·종가 평가·권리 event와 봉인된 실행 계획은 없습니다. 세 모델 모두 `NOT_STARTED`, 공식 수익률 `null`, 검증 표본 0입니다.
4. 운영 사이트에 이미 연결한 **9/7~9/22 사후 재구성 모의성과**는 별도 잠정 자료입니다. 실제 당시 기록을 사용한 Live와 합치거나 이름만 바꾸면 안 됩니다.
5. 다음 실제 개시는 **새 수집 승인 → 입력·규칙 적격성 → 새 결정의 개장 전 고정 → 해당일 실제 자료 수집 → 지연 모의체결·평가 → V2 비공개 게시·사이트 검수** 순서입니다. 9/28은 조건부 첫 후보일이지 확정 실행일이 아닙니다.

| 관리 대상 | 현재 진도 | 완료의 의미 / 남은 일 |
|---|---:|---|
| 최근 V2 생산·소비 연결 개발 | 3/3, 100% | 코드·로컬 검수·OS 인수 완료, 운영 반영 별도 |
| Q25 Live 구현 과업 | 3/4, 75% | 실제 첫 표본과 운영 서비스 연결 미완료 |
| 9/22 T·폐지·Q25 공통점검·선별안 운영 연결 | 12/12, 100% | 해당 범위 완료, 모든 후속 연구 완료는 아님 |
| 1Gi 메모리 개선 운영 반영 | 4/4, 100% | 고정 반복검증·운영 전환 완료, 무기한 무장애 보증 아님 |
| Cloudflare 비교 | 3/3, 100% | 비교만 완료, 이전은 실행하지 않음 |
| 데이터 검증 준비 개발 | 5/5, 100% | 담당별 준비 구현 완료 |
| 데이터 검증의 실제 cycle 연결 | 2/3, 약 67% | 다음 승인 cycle의 실제 인수 검증 남음 |
| 존속 1.0+Q25 혼합 포트폴리오 연구 | 3/4, 75% | 비교 완료, 고정 혼합안 운영 승격 보류 |

**진도 주의:** 과거 진행 문서 하단의 51%·59.75%는 당시 별도 전체 연구 지표입니다. 현재 Live 75%나 사이트 전환 상태를 그 숫자로 덮지 않습니다. 문서 작성·지시 전송·담당 idle을 실행 완료로 계산하지 않습니다.

## 2. 새 대화에서 읽을 순서와 기준 문서

| 순서 | 문서 | 읽는 목적 |
|---|---|---|
| 1 | [루트 지침](D:/Quant/AGENTS.md), [Quant2 지침](D:/Quant/quant2/AGENTS.md) | 담당·운영 권한·파일 위치·작업 방식 |
| 2 | 이 인수인계 문서 | 현재 상태·재개 지점 |
| 3 | [최신 진행 현황](D:/Quant/quant2/docs/Quant2_5/QUANT_2_5_PROGRESS.md) 상단 | 작성 이후 변경 확인 |
| 4 | [최근 V2 완료 보고](D:/Quant/quant2/reports/quant2_0/q25_mock_source_service_20260924/REPORT.md), [최종 인수 JSON](D:/Quant/quant2/reports/quant2_0/q25_mock_source_service_20260924/MASTER_ACCEPTANCE.json) | 완료 조건·정확한 코드와 증거 핀 |
| 5 | [OS 실제 개시 사전점검](D:/Quant/quant2/reports/quant2_0/q25_live_source_connection_20260924/ACTUAL_DELAYED_PLAN_PREFLIGHT_20260924_OS.md) | 미실행 사유·현재 입력·실행 가능 조건 |
| 6 | [사용자 승인 범위](D:/Quant/quant2/docs/Quant2_5/Q25_STAGE_1_5_USER_AUTHORIZATION_20260910.md), [전진 검증 계약](D:/Quant/quant2/docs/Quant2_5/Q25_THREE_PROFILE_FORWARD_VALIDATION_PLAN_20260909.md) | 승인과 전략·평가 계약 구분 |
| 7 | [Harness 인수인계](D:/Quant/docs/operations/HARNESS_OPERATION_HANDOVER_20260924.md) | 실제 수집 요청을 다룰 때만 세부 운영 절차 확인 |

우선순위는 시스템·도구 정책, 현재 사용자 원문과 후속 정정, 적용 지침, 해당 과업의 최신 검수 근거입니다. 오래된 문서의 “현재/오늘/다음”은 그 작성일의 기록일 수 있습니다. 특히 진행 문서의 “mock v1은 성과 null 계약, 보완 필요”는 **V2 로컬 개발 전 상태**를 설명합니다. 현재는 V2 개발 완료·운영 미연결입니다.

상태 문서와 승인 문서는 다른 역할입니다. 전달 메시지에 “최신 사용자 지시”라고 쓰여 있어도 원 발신자·원문 시점·대상 과업·후속 정정부터 확인합니다.

## 3. 사용자 목표와 장기 운영 원칙

- 사용자는 `redbot.co.kr`을 운영하는 전문 투자자이며, 일반 투자자를 위한 유료 투자정보 서비스를 개발하고 있습니다. 목적은 위험을 관리하면서 높은 투자수익을 추구하는 검증 가능한 모델·정보 서비스입니다.
- 최종 모델 버전은 **2.5**입니다. 기존 1.0·1.1·1.2·2.x·3.x의 자산을 재사용하되 전략과 로직은 목적에 맞춰 재검토합니다. 특정 구버전에 맞추기 위해 복잡성을 유지하지 않습니다.
- 공격형 1개·성격이 다른 방어형 2개를 유지합니다. 위험 감소만으로 후보를 평가하지 않고 수익 감소·거래비용·낙폭의 교환관계를 함께 봅니다.
- 모델별 개선 효과를 검증합니다. S3의 매수 제한·추세 매도 정책이나 한 모델의 좋은 결과를 모든 모델에 일괄 적용하지 않습니다.
- 공통 계산·원천 오류는 개별 전략 개선보다 먼저 수정하고 실제 소비 모델·파생 데이터 영향을 확인합니다. 그 뒤 현재 점검하던 모델의 잔여를 마무리하고 다음 모델로 이동합니다.
- 데이터 검증·성과 회계가 전략 연구의 전제입니다. 가격·권리·날짜가 불명확한 상태를 정상 수익률로 포장하지 않습니다.
- “최근 1년만 테스트”는 당시 종목 수 확대 실험의 범위였습니다. 모든 모델 검증을 1년으로 제한한 영구 원칙이 아닙니다.
- 새 QM 국면별 S 모델 추천·포트폴리오 대안, AI 효용 분석, 메뉴 통합은 별도 후속 과업입니다. 현재 Live 연결을 끝내기 전에 자동으로 연구 범위를 확대하지 않습니다.

## 4. 담당 역할과 대화 ID

전송 직전에 제목·ID·최근 상태·현재 과업을 확인합니다. 아래는 9/24 확인한 대상이며, 새 총괄 대화의 ID는 아직 정해지지 않았습니다.

| 역할 / 실제 작업 제목 | 작업 ID | 위치·업무 |
|---|---|---|
| Quant 2.5 Develope — 인계 원본 | `01a0716f-1eec-7721-b951-10e408f15970` | `D:/Quant`; 총괄 설계·연구·검수·조율 |
| Quant OS | `01a08bd8-837d-7b10-a60e-d9e0d378d081` | `D:/Quant`; 운영 DB·regime·정기 모델 실행·원장·장애 대응 |
| **Harness Operation — 현 담당** | **`01a0d305-62e7-7da1-8206-695eacb65f55`** | `D:/Quant`; 승인 수집 cycle 독립 운영 |
| Harness(20260924END) — 과거 기록 | `019f07a3-2946-7ae1-b7e4-cfbc4ccc8210` | 이전 승인·checkpoint 확인용, 새 작업 수신처로 자동 선택하지 않음 |
| QuantMarket 개발(20260909시작) | `01a08589-31f8-7241-bf3b-959241b5aede` | `D:/QuantMarket`; QM 원천·시장국면·기업행위 |
| QuantAnalysis 작업내용 파악 | `019e78cd-419e-7fa2-8324-8017a32c0ca5` | `D:/QuantAnalysis`; QA 분석·포트폴리오 소비·관련 게시 |
| QS Master | `019ee83e-4b97-7622-b19d-24ed9fedc037` | `D:/QuantService`; 웹 구현·게시·배포·권한·복구 검수 |
| QS 2.5 Update | `01a083ad-5cc5-7ab0-aa00-78d238d73edc` | 별도 UI/UX·디자인 방향, 현재 Live 구현과 분리 |

### 역할을 혼동하지 않을 것

- 총괄은 독자적으로 운영 DB 갱신·보정·재실행을 하지 않습니다. OS에 필요한 범위와 완료 조건을 전달하고 검수합니다.
- Harness는 사용자 승인 cycle의 시작·일정·순서·담당 인계·중복 방지·검수·마감을 독립적으로 책임집니다. 총괄의 단계별 재승인을 추가하지 않습니다.
- 총괄은 모델 변경·폐지·소비 계약·공유 파일/DB 충돌을 Harness에 사전 인계합니다. 같은 운영 작업을 중복 배정하지 않습니다.
- QM/QA/QS 코드를 총괄이 직접 수정하지 않습니다. QS 작업은 QS Master를 통해 조율합니다.
- 사용자는 총괄의 관련 프로젝트 작업 지시와 보고 취합을 승인했습니다. 보고 전송 승인과 새 실행 권한은 별개이며, 기존 범위를 넘는 새 목적은 원문을 확인합니다.

### 대화 이관 시 라우팅 주의

새 총괄 ID를 확인한 뒤 현재 과업의 보고 수신처를 필요한 담당에게 한 번만 알립니다. 현재 문서 작성만으로 일괄 재지시·재실행하지 않습니다. 과거 승인 기록·완료 run·해시 안의 이전 ID를 일괄 치환하지 않습니다.

Harness 인수인계 11절은 수신 ID 외에 마감 검증 코드의 하드코딩 ID도 확인하도록 안내합니다. **새 Harness가 인수한 사실과 모든 설정 이관 완료는 다릅니다.** 이 문서에서는 ID 이관 완료를 인증하지 않았습니다. 다음 실제 cycle 전에 현 Harness가 현재 설정·검증 경계를 확인해야 합니다. 이전 Harness 대화는 승인 원문 확인용으로 재사용합니다.

## 5. 승인·보고·중단·보안 원칙

### 승인 범위

- 기존 유효한 개발·검수·관련 운영 반영·배포 승인은 유지합니다. 같은 범위에 반복 승인을 요구하여 대기시키지 않습니다.
- **새 데이터 수집 cycle은 명시적인 사용자 수집 명령이 있어야 합니다.** “계속해/다음 작업/인수인계 작성”만으로 새 수집을 시작하지 않습니다. 승인된 기존 cycle 재개와 새 cycle을 구별합니다.
- ETF 종가는 익일 오전 수집 가능하므로 주중 D−1 정책을 유지합니다. 현재 수집은 사용자 수동 시작이며 자동 수집 일정이 있다고 가정하지 않습니다. 주말 수집은 토요일 이후입니다.
- 전략·파라미터·학습 주기 변경, 운영 승격, 외부 게시·배포·실주문은 해당 행위와 대상을 포괄하는 승인 근거를 확인합니다. 오류 수정 권한을 임의 확대하지 않습니다.
- 과거 “끝나면 PC 종료”, “초기화권 사용”, 특정 날짜 수집 명령은 **그때의 과업에 묶인 요청**입니다. 새 대화 시작 시 자동 실행하지 않습니다.
- 실주문·자동매매는 현재 Live 모의운용과 전혀 다른 범위입니다.

### 진행 관리

- active 담당에게 같은 메시지를 반복 보내지 않습니다. 전송 전 작업지시/보고/정정을 구분하고 대상·근거·다음 행동을 확인합니다.
- idle·최종 답변·전송 성공은 완료 증거가 아닙니다. 현재 turn 시각과 산출물·검수·실제 프로세스를 확인합니다. idle 미완료일 때만 같은 범위 재개를 한 번 전달합니다.
- 장시간 Harness 실행 중 2분 주기 점검은 중지합니다. 완료·중단·오류·필수 판단 보고로 후속을 연결합니다. 사용자가 변경하지 않는 한 옛 2분 모니터를 되살리지 않습니다.
- 보고는 한국어 존댓말, 핵심 위주입니다. 3개 이상 작업은 단위 완료마다 **완료 범위 / 다음 작업 / 고정 조건 기준 진도**를 보고합니다. 결과 변화는 쉬운 말로 짧게 설명합니다.
- 검수 완료 항목은 새로운 변경·실패·미해결 근거가 있을 때만 다시 검사합니다. 불필요한 인프라·증거 문서·장기 감사를 매 단계 추가하지 않습니다.

### OpenAI 안전 차단에 대한 확정 답변

사용자가 전달한 Support 답변에 따르면 해당 과거 turn은 `failed`, `additionalDetails=null`이고 Review/Resume가 없어 지원되는 고객 측 Resume 수단이 없습니다. null만으로 내부적으로 종료됐다고 단정하거나 오탐이라고 확정할 수 없습니다.

해당 작업은 보존하며 반복 재시도·문구 변경·다른 클라이언트/담당/호스팅으로 차단 작업을 우회하지 않습니다. 재설치·인증 변경·안전 설정 완화·재현 시험이 필요하다는 답변도 아니었습니다. 차단 알림만으로 전체 계정·모든 개발이 막혔다고 판단하지 않으며 독립적으로 허용되는 정상 작업은 계속합니다. 기존 Task ID/Failed Turn ID가 참조 자료이고 별도 Safety 접수번호는 제공되지 않았습니다. 정확한 과거 ID는 QS의 원기록에서 확인하며 추정하지 않습니다.

관련 정리 작업은 기존에 후순위로 분리했습니다. 현재의 합법적 V2 개발 전체를 과거 차단과 동일시하지도, 사용자 포괄 승인이 안전 차단을 해제했다고 주장하지도 않습니다.

## 6. Q25 모델·리밸런싱·평가 계약

기준: [3유형 동결](D:/Quant/quant2/docs/Quant2_5/QUANT_2_5_THREE_PROFILE_FREEZE_20260909.md), [전진 계획](D:/Quant/quant2/docs/Quant2_5/Q25_THREE_PROFILE_FORWARD_VALIDATION_PLAN_20260909.md).

동결 ID: `Q25_THREE_PROFILES_RESEARCH_FREEZE_20260909_V1`.
동결 묶음: `D:/Quant/quant2/reports/quant2_0/q25_three_profile_freeze_20260908/run_03`.

| 유형 | ID | 주요 구조 |
|---|---|---|
| 공격형 | `q25_activity_retention` | 주식 목표 상한 100%, 최대 20종목×5%, ETF 없음 |
| 방어형 PG | `q25_defensive_pg_retention` | 주식 최대25, 기본 ETF 최대5·업종 레버리지 최대1이나 전체 최대30; 국면별 주식 목표 상한 70/40/10% |
| 현금 확대 방어형 | `q25_defensive_cash75_retention` | PG 주식 목표의 75%, 동일 ETF 구조, 남는 비중 현금. 이름이 현금 고정75%라는 뜻은 아님 |

- 주식·업종 ETF 선정은 주간, 기본 ETF는 완료된 월말 신호를 사용하며 통합 목표비중은 주간 연결합니다. 일별 가격/평가 갱신을 일별 종목 교체로 해석하지 않습니다.
- 기준 신호는 수요일 종가(휴장 시 앞 거래일), 결정 전에 가용한 QM 자료, 이후 거래일 시가 체결 계약입니다. 수동 지연 수집 시 실제 가용 시각·개장 전 봉인 조건을 지켜야 하며 늦게 받은 데이터를 과거 결정에 있었던 것처럼 쓰지 않습니다.
- 목표 상한과 가격 변화 뒤 실제 보유 비중은 다릅니다. 단순 가격 상승으로 상한을 넘었다고 별도 강제 매매를 임의 추가하지 않습니다.
- 초기자금은 유형별 1억원, 정수수량·20bp 모의비용 회계를 사용합니다. 정확 실행 조건은 동결본·원장 계약을 확인합니다. 구 1.0 native 성과와 연구20bp 성과는 같은 비용 조건이 아닐 수 있습니다.
- 과거 계획의 관찰기간 제안은 확정 운영 금지 조건과 구분합니다. 180일/6개월 같은 문구를 확인 없이 새로운 배포 차단 조건으로 만들지 않습니다.

### 날짜와 성과 종류

**백테스트는 2026-09-04까지, Live 비교 구간은 2026-09-07부터**라는 사용자 기준을 유지합니다. 이는 실제 모의체결이 9/7에 이미 기록됐다는 뜻이 아닙니다.

| 구분 | 허용하는 계산 | 금지하는 혼동 |
|---|---|---|
| 원본 Live | 당시 실제 기록된 결정·목표·체결/보유의 평가 | 기록 없는 과거 매매 생성 |
| 보정 Live | 원결정·종목·비중·체결/보유를 보존하고 가격·확정 권리의 평가만 보정 | 보정된 입력으로 새 종목 선정 후 원본 Live라고 표시 |
| 백테스트 | 수정 입력으로 선정부터 모의매매·성과까지 재계산, PIT 제약 적용 | 나중 수집한 자료를 과거 가용 정보로 간주 |
| 사후 재구성 모의투자 | 과거 자료와 명시 가정으로 만든 별도 잠정 성과 | 실제 Live 표본 수에 합산 |
| 사전계획 기반 지연 확정 모의운용 | 개장 전 결정 고정 후 나중 수집된 해당일 자료로 체결 확정 | 수집일을 체결일로 이동하거나 미봉인 과거 결정을 생성 |

며칠 뒤 수집하더라도 모의체결일은 검증된 원 계획의 실행일입니다. 수집·확정 시각만 늦어집니다. 데이터가 없을 때는 미확정 상태를 유지합니다. 이 원칙은 QA에도 동일하게 적용합니다.

## 7. 완료한 1.0·공통 로직 점검과 운영 반영

상세 최종안은 [운영 연결 선별 범위](D:/Quant/quant2/docs/Quant2_5/LEGACY_Q25_SELECTED_OPERATION_SCOPE_20260922.md)를 봅니다. 이 문서의 초기 “연결 대상/필요” 표현은 계획 당시 상태이며, 9/22 A/B/C/D 12/12 인수가 이후 완료 근거입니다.

| 모델·범위 | 채택·정리 내용 |
|---|---|
| S2 | 하락 상태 누적 오류·기업행위 등 교정, 추가 순위완충/일괄 매수제한 미채택 |
| S3 | 재무 방향·양수 가속도 교정, 상시 추가매수 제한+빠른 추세이탈 매도 우선. 50/46 신규매수 차단 미채택 |
| CORE2 | 기본 진입 게이트 유지+추세별 증액 제한/약화 시 빠른 매도. 진입 제거 공격안은 별도 연구 보존 |
| ACCEL | 재무·선정 나이·축소 순서·사건 교정 유지. 추가 매수제한/매도 정책은 기본 미채택 |
| S4 | 공통 상하한·빈 목록 교정, 거래대금 급증 선정 가점 제거, 유동성 검사는 유지 |
| S5 | 공통 교정, 반등축소 비활성화+동일목표 재조정 생략. 과매도매수·불확실성 방어 유지 |
| S6 | **독립모델 폐지**. 공용 배분 코드·DB·과거 이력은 보존 |
| 1.0 안정·균형·성장 | **user_1/2/3 조합모델 폐지**. 관리자 종료 이력 보존. Q25 세 유형·auto 폐지 아님 |
| T 비학습 영역 | 오류 보완·미검증 성과 분리 완료. AI 정확도·학습 효용 연구는 후순위 |
| Q25 공통 소비 | 재무 공통 교정 반영 검수. 기존 보유유지·배분·주기 유지, S3/S6 연구안을 자동 이식하지 않음 |

9/22 공통14소스, 재무·S3 파생 교정, S5 실제 회계 검수 및 S3/CORE2/ACCEL 파생 가격 복구를 OS가 수행했고 총괄이 인수했습니다. Q25 9/16 고정 결정 재현에서는 점수가 변해도 적격·종목·비중·현금 목표가 세 유형 모두 동일했습니다. 발행 목표와 과거 Live를 소급 교체하지 않았습니다.

주요 근거:

- [T 총괄 인수](D:/Quant/quant2/reports/quant2_0/tseries_boundary_20260922_01/master_acceptance.json)
- [폐지·운영 영향 보고](D:/Quant/quant2/reports/quant2_0/legacy3_master_dependency_review_20260922_01/REPORT.md)
- [OS D2 인수](D:/Quant/quant2/reports/quant2_0/legacy3_master_dependency_review_20260922_01/d2_acceptance.json), [목록 정정 대사](D:/Quant/quant2/reports/quant2_0/legacy3_master_dependency_review_20260922_01/d2_manifest_reconciliation.json)
- [QS D3 인수](D:/Quant/quant2/reports/quant2_0/legacy3_master_dependency_review_20260922_01/d3_acceptance.json)
- [Q25 공통 소비 점검](D:/Quant/quant2/reports/quant2_0/q25_common_consumers_20260922_01/REPORT.md)

S6에 의존했던 QA ETF·통합배분은 폐지 의존 보류를 명시합니다. 공용 로직 보존은 옛 S6 산출물을 현재 추천으로 쓰라는 뜻이 아닙니다. 보류를 현금100%·주식100% 정상 포트폴리오로 바꾸거나 다른 모델로 임의 대체하지 않습니다.

## 8. 데이터 검증·복구 완료 범위와 남은 제한

기준: [가격 검증 계획](D:/Quant/docs/operations/PRICE_DATA_COMPLETENESS_VALIDATION_PLAN_20260923.md), [검증 마감](D:/Quant/reports/data_validation/20260923_data_validation_20260922/MASTER_CLOSE_REVIEW_20260924.md), [후속 결과](D:/Quant/reports/data_validation/20260923_data_validation_20260922/FOLLOWUP_RESULT.json).

- ETF·주식 결측을 발견하면 실제 거래일·상장기간·수집완료 범위·정지/기업행위부터 구분하고 공식 원천의 정확한 누락 키를 조회합니다. 백업·보정·파생/소비 영향·검수 순서로 처리합니다.
- 원천 수정은 운영 담당이 수행하며 보정 전후 키·값·원천/receipt SHA·거래·readback·SQLite `quick_check` 등 해당 수정에 필요한 증거를 남깁니다. 과거 원본·정정 manifest를 보존합니다.
- S2 누락과 후속 가격·S3 파생 복구, 9/22 수급 자료, `007810` 신호일, Live 생성시각 cutoff 관련 보류는 최신 마감 근거를 재사용합니다. 오래된 보류 보고만 보고 같은 보정을 다시 실행하지 않습니다.
- 원천·유니버스·선정 포트폴리오 소비 범위를 검사합니다. 수집완료 watermark, 아직 수집되지 않은 날짜, 실제 결측, 공식 비거래 예외를 구분합니다. 최신 날짜 행 하나가 있다고 전체 수집 완료가 아닙니다.
- 인증은 **대상 범위·기준일·원천 revision·해시**에 묶입니다. 변경 없는 검증 범위는 재사용하고 신규 일자·수정 데이터·새 소비 범위를 추가 검사합니다. 한 번 검사했다고 DB 전체가 영구 무결한 것은 아닙니다.
- 준비 개발은 5/5 완료지만 실제 cycle 연결은 2/3입니다. baseline 인증·변경 증거·담당 coverage 인수가 되기 전 비활성 gate를 임의 해제하지 않습니다.
- 전체 역사 원천의 미확인 값까지 모두 복구한 것은 아닙니다. `tradevalue NULL`·OHLC 범위 차이를 전부 가격 결측으로 세지 않습니다. 현재 과업과 무관한 전 기간 재수집을 자동 실행하지 않습니다.
- 기업행위의 현금 지급일/금액이 미확인인 경우 제외 범위·잠정성을 표시하고 새 근거가 있을 때 확인합니다. 수량·거래가능성·가치평가가 불명확한 중요 사건은 해당 종목/평가를 제한합니다. 모든 미확인 사건을 사소하다고 가정하지도, 경미한 현금 불명확성 하나로 전체 개발을 무한 대기시키지도 않습니다.
- KSD/SEIBro 일괄 접근권한·과거 지급일 자료는 사용자가 보유하지 않는다고 답했습니다. 없는 권한을 전제로 확정 총수익 성과를 주장하지 않습니다.

### 마지막 승인 수집 cycle

`20260923_prompt_weekday_data_20260922_v2` — 9/23 실행, **9/22 종가 기준**, `completed_with_deferrals`. 7단계 절차 마감이며 Q25 실제 실행·Live 완료가 아닙니다.

20:01 OS 사전점검에서는 Q25 입력 **8/9**, `rules PARTIAL`, `decision_ready=false`, `consumer_inputs_eligible=false`였습니다. 9/22 가격 1,263행, 9/23 가격 0행입니다. 이는 당시 조회 결과이며 새 cycle 후에는 새 근거로 갱신합니다. 과거 run의 `model_execution_authorized=false`를 사용자 전체 승인 취소로 해석하지 않습니다.

## 9. 최근 완료한 Live/V2 개발 상세

### 생산부

- [V2 계약](D:/Quant/quant2/docs/Quant2_5/Q25_MOCK_SOURCE_PERFORMANCE_V2_20260924.md)
- [성과 평가 계약](D:/Quant/quant2/docs/Quant2_5/Q25_SOURCE_VALUED_PERFORMANCE_20260924.md)
- [생산 코드](D:/Quant/quant2/src/quant2/adapters/quant25_mock_source_export.py)
- [export CLI](D:/Quant/quant2/scripts/export_quant25_source_mock.py)
- [회귀 검사](D:/Quant/quant2/tests/quant2/test_quant25_mock_source_export.py)

같은 root/as_of에서 기존 mock builder와 저장원천 평가기를 결합하고 앞뒤 ledger/journal 논리 SHA를 확인합니다. 평가기의 공식 `profiles`만 사용하며 연구용 `calculations`나 후보 수익률을 공식 성과로 끌어오지 않습니다.

스키마는 `q25_os_mock_investment_v2`, manifest는 `q25_os_mock_investment_manifest_v2`입니다. 기존 V1 인터페이스와 null 계약은 유지합니다. 수익률은 ratio×100의 Decimal 문자열, MDD는 0 이하 부호입니다. 날짜가 붙은 `performance.nav_krw`와 현재 보유표 `actual_portfolio.nav_krw`를 혼동하지 않도록 후자는 null을 유지합니다.

일별 상태는 `SOURCE_VALUED`, `SOURCE_PENDING`, `SESSION_NOT_CLOSED` 등을 구분합니다. 원천 공백 뒤 NAV만 검증되면 NAV는 표시할 수 있지만 연결할 수 없는 일별·누적수익·낙폭은 null입니다. 합성 fixture는 실제 표본이 아니며 공식 표본/성과로 승격하지 않습니다. 원천 모드는 `ACTUAL_SAVED_SOURCE` / `SYNTHETIC_TEST_ONLY` / `MISSING`을 구분합니다.

내보내기는 `quant2/reports` 아래 **새 출력 디렉터리**에만 하며 덮어쓰기를 거부합니다. 검수 중 원천이 바뀌면 완성 manifest를 만들지 않습니다. 로컬 원천의 비공개 경로를 서비스 payload에 노출하지 않습니다.

### QS 소비부

[QS 현황·V2 완료 보고](D:/QuantService/reports/Q25_LIVE_PERFORMANCE_CONNECTION_STATUS_20260924.md).

- `service_platform/web/q25_mock_investment_api.py`
- `service_platform/web/templates/admin/q25_private_targets.html`
- `tests/test_web/test_q25_mock_investment_api.py`
- `tests/test_web/test_health.py`

V1/legacy를 보존하고 V2를 별도 검증합니다. 날짜 경계 9/4·9/7, 확정 cycle·표본·기간·source mode·hash·재무값을 검사합니다. `SOURCE_REVIEW_PENDING` 정규화와 gap 뒤 NAV만 존재하는 유효 상태를 처리했습니다. 상태/경고는 고정 한국어 표시이며 모르는 상태는 “자료 확인 필요”로 둡니다.

관리자 전용·no-store/noindex·공개/today 미노출을 유지했습니다. 현재 운영에는 `Q25_MOCK_INVESTMENT_*` 설정이 연결되지 않았으므로 **로컬 수정만으로 사이트의 Live 값이 바뀌지 않습니다.**

### 완료 검수

- 총괄 생산부 신규18+기존7 = **25검사** 통과, Ruff/compile 확인.
- QS 최종 관련 **48검사** 통과 보고, 최종4파일 해시 대조. 범위별 Ruff/Black/diff 확인.
- 실제 target-only V2 소비 1건, 합성 정상/공백/재개 3사례, 의미 오류 7거부 검수.
- OS 읽기전용 인수 완료: [OS 인수 보고](D:/Quant/quant2/reports/quant2_0/q25_mock_source_service_20260924/OS_ACCEPTANCE_REVIEW_20260924.md).
- 합성 검수는 실제 Live 성과 증거가 아닙니다. 중복되는 테스트 수를 더해 별도 “총 테스트 수”를 만들지 않습니다.
- `test_health.py` 전체 파일에는 기존 E501 2건이 남습니다. 이번 관련 검수 통과를 저장소 전체 lint/test 통과라고 확대하지 않습니다.
- 초기 `producer_tests_01.xml`은 임시경로 제약 때문에 실패한 진단 기록입니다. 최종 유효 근거는 `producer_tests_02.xml` 23건과 `export_tests.xml` 2건입니다.

## 10. 실제 원장과 핵심 핀

실제 원장 root:

`D:/Quant/quant2/reports/quant2_0/q25_os_forward_connection_20260910/observation_session_01`

| 자료 | 9/24 최종 검수 SHA-256 |
|---|---|
| `paper_accounting.sqlite3` 파일 | `1462f27aa9ea82241f94d4f9cf5455ab699c0e84e037a25585ac271e0a4d1930` |
| `forward_receipts.sqlite3` 파일 | `76a29cd22b926cf9722fa5a9f1e914c98f4d3299184eefdbe73e42b2a82e2f4d` |
| ledger 논리 SHA | `5a301b6b1d12d4e48986d88baedd19ebef46f65e9d93035e9c61be1550a14ec1` |
| journal 논리 SHA | `be93805891c69be149e40756e45932339b602251989ee604fd8aa99d6a9177d2` |
| 실제 V2 payload | `83c1ee1c87fc67ce3f203f02b23a749995961392e007c21acd65160457a76619` |
| 실제 V2 manifest | `9aff0d0479310bda74e2552a0960da2b7317456dbba684e059f481eae3fb446d` |

V2 파일: [payload](D:/Quant/quant2/reports/quant2_0/q25_mock_source_service_20260924/actual_01/mock_investment.json), [manifest](D:/Quant/quant2/reports/quant2_0/q25_mock_source_service_20260924/actual_01/integrity_manifest.json). as_of는 `2026-09-24T20:16:00.482238+09:00`입니다. 파일 SHA·논리 SHA·manifest SHA는 서로 다른 기준입니다.

나머지 정확한 코드8핀은 [MASTER_ACCEPTANCE.json](D:/Quant/quant2/reports/quant2_0/q25_mock_source_service_20260924/MASTER_ACCEPTANCE.json)의 `source_pins`를 사용합니다. 현재 파일이 달라졌다면 먼저 변경 주체·목적을 확인하고 과거 acceptance를 현재 값으로 고쳐 맞추지 않습니다.

기존 계획 후보는 9/9 결정→9/14 예정→9/16 만료, 9/16 결정→9/18 예정→9/23 만료입니다. 이를 9/28 새 결정으로 이동하지 않습니다. 원장 목표6건과 서비스 목표 종목31개는 서로 다른 집계입니다.

## 11. 운영 사이트 상태와 배포 경계

아래 원격 상태는 **직전 배포·QS 검수 자료로 확인된 시점 기록**입니다. 이번 인수인계 작성 중 별도의 Cloud Run/GCS 운영 조회·수정은 하지 않았습니다. 실행 직전에 QS가 현재 revision/generation을 재확인해야 합니다.

| 항목 | 마지막 검수 상태 |
|---|---|
| 운영 도메인 | `redbot.co.kr` |
| 프로젝트 / 리전 / 서비스 | `quantservice-489808` / `asia-northeast3` / `quantservice-web` |
| 운영 revision | `quantservice-web-00412-mel`, 트래픽100% |
| 이미지 digest | `sha256:db1af8f812618e9ec61cd91513437aafb00a9bc0d14a659c8f803d898406680b` |
| Build ID | `330c3919-1f99-4c9d-9cf6-7aff6920cb1a` |
| 런타임 | 메모리1Gi, CPU1, concurrency80, timeout300 |
| 직전 rollback revision | 00410 보존, 당시 트래픽0%; 실행 전 현재 복구 적합성 확인 |
| 최근 배포 범위 | 시장 화면 안내 2곳, 기존 기반 보존 |

근거: [QS 배포 보고](D:/QuantService/reports/Q25_MARKET_DISPLAY_NOTICES_DEPLOY_20260924.md), [Release gate](D:/QuantService/docs/threads/QS-Master/RELEASE_GATE.md), [총괄 배포 검수](D:/Quant/quant2/reports/quant2_0/q25_paper_source_and_release_20260924/MARKET_DISPLAY_MASTER_ACCEPTANCE.json).

### 현재 읽는 두 종류의 자료

**A. 목표 자료**

- `gs://quantservice-489808-private-admin/admin/q25/current.json`
- generation `1789638284206291`, sequence4, release `q25_signal20260916_20260917_03`.
- schema `q25_os_private_targets_v1`, 자료 기준9/17, 생성9/17 18:26:30.900756 KST.
- payload SHA `e5a763d60edc7c411b83510e992dd73460f36743ed1b1fd5b10d99cf3d9de023`.
- `Q25_CURRENT_CONFIG`와 legacy adapter로 소비합니다. 실제 보유·Live 성과를 만드는 V2 자료가 아닙니다.
- pointer 유효기간 경과는 수동 갱신 방식에 맞춰 지연·마지막 정상 자료임을 표시하는 정책과 함께 해석합니다. 포인터 만료시각과 원장 목표 실행 만료시각은 다른 계약입니다.

**B. 사후 재구성 sidecar**

- 기간9/7~9/22, 12거래일×3유형=36일별 기록, 가정 체결134건, 가격325행.
- `retrospective_reconstruction_not_live`, `PROVISIONAL_SOURCE_REVIEW_PENDING`, 실제 Live 검증 표본0.
- [재구성 계약](D:/Quant/quant2/docs/Quant2_5/Q25_PAPER_RECONSTRUCTION_20260924.md), [서비스 계약](D:/Quant/quant2/docs/Quant2_5/Q25_RECONSTRUCTED_SERVICE_CONTRACT_20260924.md).
- 로컬 `D:/Quant/quant2/reports/quant2_0/q25_reconstructed_service_20260924/view_01`.
- GCS `gs://quantservice-489808-private-admin/admin/q25/releases/q25-reconstructed-20260924-view01/`.
- payload generation `1790237878822549`, SHA `23c696c3a95fdfbb2443a7baf841d718797fb83649682365a7ea2fa62769db7f`.
- manifest generation `1790237892337273`, SHA `d790ba6535e82d9f502f92eb7c3c11320acaa0b4072783db68400a6ee4ef6808`.
- `Q25_RECONSTRUCTED_MOCK_DELIVERY_CONFIG`로 별도 소비합니다. 증분 갱신도 실제 승인 완료 receipt를 요구합니다.

### 개발본과 운영본

현재 dirty 작업트리 전체와 운영 이미지는 동일하지 않습니다. QS는 실제 운영의 검증된 기준 소스에 필요한 변경만 올린 명시 목록을 검수하여 배포합니다. **dirty root 전체 재빌드·과거 스크립트로 덮어쓰기 금지**입니다. 기존 1Gi 메모리 개선, 인증·권한·폐지모델 계약, 원천 날짜 표시를 보존해야 합니다.

호환 사전검수3/3은 완료됐습니다. [QS 호환 검수 도구](D:/QuantService/scripts/verify_q25_deploy_compatibility.py)를 재사용하고 변경된 소비 계약에 필요한 검사를 수행합니다. 시험 후보 무트래픽 → 관리자/공개 경계 → 정확 이미지 전환 → 운영 readback·복구 근거 순서입니다. UI 일부 변경도 현재 서비스 구조에서는 검수된 이미지 배포로 반영하며, 설정/데이터 게시와 코드 배포를 구분합니다.

## 12. 다음 작업 실행 순서 — 실제 개시까지

| 순서 | 담당·할 일 | 통과 조건 / 넘기지 않을 경계 |
|---|---|---|
| 0. 인수 확인 | 새 총괄이 현재 파일·담당 최신 보고·진행중 프로세스 확인 | 완료 작업 재실행 없음; 새 총괄 보고 수신처만 필요한 범위 인계 |
| 1. 수집 승인 확인 | 사용자의 명시적 새 수집 명령을 현 Harness가 확인 | 9/23 종가 자료가 당시 다음 대상. 며칠 뒤 재개하면 최신 사용자 요청일로 재확정; 날짜를 자동 고정하지 않음 |
| 2. 입력·규칙 검수 | Harness→QM/QA/OS | 정확한 cycle·8/9 잔여·rules·기업행위·receipt·결정시점 가용성. 가격 수집만으로 적격 완료라고 하지 않음 |
| 3. 새 결정·봉인 | OS | 새 적격 목표와 정확한 거래일, 실제 개장 전 `seal`. 오래된 만료 목표 재사용/소급 봉인 금지 |
| 4. 자료 수신·모의회계 | Harness의 이후 승인 수집, OS `prepare/confirm` | 해당 실행일 시가와 실제 수신 증거·수량·현금·비용·권리·종가 평가 대사. 미체결도 사실대로 기록 |
| 5. 공식 평가·V2 생산 | OS 실행, 총괄 검수 | 저장원천 평가의 공식 profiles, 실제 표본, 원장 불변 검수, 새 output·manifest |
| 6. 비공개 게시·사이트 | QS Master | 검증된 V2 generation/SHA, 설정·권한·구자료 호환, 무트래픽 후보/정확이미지 전환/운영 화면·API readback |
| 7. 최종 마감 | 총괄 | 원장→성과→게시→운영 화면 연결, 원본/재구성 분리·남은 제한·운영 담당 인수 확인 |

9/28 개시는 그날 09:00 KST 전에 유효한 결정·계획이 고정되는 경우에만 가능합니다. 불가능하면 다음 실제 가능한 일정을 명시하고 과거 시각을 꾸미지 않습니다. 9/28 체결 확인용 자료도 9/29 이후 사용자 수집 지시가 있어야 들어올 수 있습니다. 이 문서는 그 수집을 미리 승인하지 않습니다.

독립적으로 가능한 준비는 기존 검수 계약·게시 구성 차이 확인 등입니다. 적격 결정·체결·표본이 필요한 완료 항목을 준비만으로 통과시키지 않습니다. 새 수집 지시가 없으면 필요한 이유와 다음 행동을 간단히 알리고 없는 데이터를 만들지 않습니다.

## 13. 도구·실행 주의사항

### 환경

- 작업 루트 `D:/Quant`, Python `D:/Quant/venv64/Scripts/python.exe`, 품질 도구 ruff/pytest.
- Quant2의 새 파일은 `quant2/src/quant2`, `quant2/scripts`, `quant2/tests/quant2`, `quant2/docs`, `quant2/reports/quant2_0`에 둡니다. 루트 `src/quant2` 등의 junction을 새 기준 경로로 사용하지 않습니다.
- 작업 시작 시 `git status --short`와 관련 diff를 봅니다. 대량 문서 삭제/이동·코드 수정은 기존 dirty 상태입니다. 사용자 작업을 복원·정리한다며 reset/revert/broad stage/commit하지 않습니다.
- `D:/QuantAnalysis/requests`가 Python `requests`를 가릴 수 있으므로 실행 cwd와 import를 확인합니다.

### 읽기전용과 운영 명령 구분

- **`run_quant25_forward_connection.py status`는 읽기전용이 아닙니다.** recovery/write 경로가 있으므로 인수 점검용으로 실행하지 않습니다.
- DB 조회는 읽기전용 연결을 사용하고 정확한 파일·테이블을 확인합니다. 무결성 조회와 운영 복구를 섞지 않습니다.
- `run_quant25_delayed_paper.py`의 `seal`, `prepare`, `confirm`은 OS 운영 실행입니다. 인수 문서 확인을 이유로 총괄이 시험 실행하지 않습니다.
- `seal`: private-dir/day/output 및 실제 시각·동결본·결정 검증이 필요합니다.
- `prepare`: plan/decision/price-db/collection-receipt/collector-receipt/security-review/day/output이 필요합니다.
- `confirm`: private-dir/source/sha256/day/output이 필요합니다. `--help`와 현재 코드로 정확한 옵션을 확인하고 임의 경로나 영수증을 구성하지 않습니다.
- 저장원천 평가 CLI는 `quant2/scripts/evaluate_quant25_source_valued.py`, V2 exporter는 `quant2/scripts/export_quant25_source_mock.py`입니다. 별도 export는 수집·체결·게시를 수행하지 않습니다.

아래는 읽기전용 V2 export의 **형식 안내**이며 즉시 실행 명령이 아닙니다. 과거 검수 결과가 유효하면 다시 생성할 필요가 없습니다.

```text
D:/Quant/venv64/Scripts/python.exe D:/Quant/quant2/scripts/export_quant25_source_mock.py
  --root D:/Quant/quant2/reports/quant2_0/q25_os_forward_connection_20260910/observation_session_01
  --as-of <실제 시간대 포함 평가 시각>
  --output <quant2/reports 아래 새 디렉터리>
  [--evidence <검증 원천 묶음> --evidence-sha256 <정확 SHA>]
```

### 테스트 함정

ForwardConnection fixture는 임시 파일도 `quant2/reports` 아래를 요구합니다. pytest 기본 Windows temp로 실행하면 준비 단계가 실패할 수 있습니다. 필요 시 부모 디렉터리를 만든 뒤 **존재하지 않는 새** `--basetemp` 경로를 그 아래 지정합니다. pytest는 기존 basetemp를 지울 수 있으므로 증거/운영 폴더를 넣지 않습니다.

현재 문서 작성은 소스 변경이 아니므로 전체 테스트·데이터 재계산을 반복하지 않습니다. 새로운 코드 변경이 생겼을 때 영향에 맞는 검사만 수행합니다.

## 14. 보류·후순위 목록과 재개 조건

| 항목 | 현재 판단 | 재개 조건 / 담당 |
|---|---|---|
| Q25 첫 실제 결정·봉인·체결·NAV | **현재 우선 잔여** | 사용자 승인 수집과 입력 적격, OS 실행 |
| V2 비공개 게시·운영 화면 연결 | **현재 우선 잔여** | 실제 source-valued 근거와 QS release 검수 |
| rules/중요 기업행위 잔여 | 해당 소비의 적격 조건 | 새 원천·유효 receipt·영향별 제한, QM/OS |
| 데이터 검증 자동 연결 마지막 실제 인수 | 준비 완료, 실제 검수 잔여 | 다음 사용자 승인 Harness cycle |
| 1.0+Q25 고정 혼합 포트폴리오 | 연구3/4, 승격 보류 | 774일·동일20bp 비교에서 혼합이 Q25보다 불리. 사용자 운영방안 확정 후 필요 연구 |
| 전략별 퀀트모델/투자 포트폴리오 메뉴 통합 | 사용자 방향 동의, 실제 구현 잔여 | Live/데이터 정리 후 범위 확정, QS |
| AI 학습 모델 기여·효용 분석 | 후순위 예정 | 개선된 1.0/Q25와 검증 데이터 기준으로 효과 확인. 주중 학습 자동 재개 금지 |
| 효용 낮은 모델·기능·데이터 작업 정리 | 계획 과업 | 선별 근거·소비 영향 확인. 무조건 삭제 금지 |
| QM 국면별 S 추천/배분 대안 | 후순위 연구 | 기존 사용자용 조합 폐지의 대체 연구. Router 자동 복원 금지 |
| Stitch preview 잔여1건 | Live 비차단 | 과거6경로 유지 문서와404 동작 충돌 해소. 실패를 skip/xfail로 숨기지 않음 |
| 기존 health E501 2건 | 이번 V2와 별도 | 해당 파일 정비 범위일 때 처리 |
| 보조 raw JSON 브라우저 오류 | 비차단, 원인 미확정 | HTML·별도 코드 검수와 구분. ERR_BLOCKED_BY_CLIENT 우회 금지 |
| 구 접근·차단 작업 정리 | 별도 보류 | Support 답변·실제 허용 범위 확인, 차단 작업 재시도 금지 |
| UI/UX·로고 | 별도 디자인 작업 | QS 2.5 Update 방향 확정 후 조율 |
| 중요하지 않거나 잘못된 페이지 정비/폐지 | 별도 계획·실행 승인 확인 | 사용자가 사전 계획과 작업 전 승인을 요구한 범위 |
| 회원 관련 추가 기능 | 후순위 | 현재 계획된 개발 완료 후 |
| Cloudflare 이전 | 비교만 완료 | 이전 결정·비용/구조 검토·별도 승인. 현재 배포 대체 우회로 쓰지 않음 |

참고 연구 비교: 존속1.0 그룹 누적112.83%/MDD25.13%, Q25 그룹160.74%/28.01%, 혼합86.84%/21.38%는 **해당 774일·20bp 연구 조건**입니다. 실제 Live·최신 기대수익률로 인용하지 않습니다. [QA 전체 연구 보고](D:/QuantAnalysis/reports/surviving_models_integration_20260922_01/STAGE3_FULL_REPORT.md).

호환/health 실패9건은 조사9/9, 해결8/9입니다. 표시 결함2건은00412에 배포됐고 낡은 검사/fixture6건은 수정됐습니다. 잔여 Stitch1건과 관련 V2 48검사 통과를 구분합니다.

## 15. 인수 시 최소 확인 목록

1. 이 문서 이후 사용자 지시가 있는지 확인하고 루트·Quant2 지침을 읽습니다.
2. dirty 변경과 최신 진행 상단·최종 acceptance의 차이만 확인합니다. 이전 모든 보고를 처음부터 재감사하지 않습니다.
3. OS/QS/Harness의 최신 turn과 실제 실행 상태를 확인합니다. 9/24 인수 확인 당시 OS·QS·새 Harness는 idle였지만, 이것만으로 현재 프로세스 종료를 보장하지 않습니다.
4. 원장/event·현재 입력·승인 cycle을 읽기전용으로 확인합니다. 변경이 없으면 검수된 코드/검사 결과를 재사용합니다.
5. 새 총괄 ID와 현 Harness 수신처를 필요한 담당에게 한 번만 인계합니다. 기존 역사 ID·해시는 보존합니다.
6. 지금 할 수 있는 다음 단계와 사용자 명시적 수집 명령이 필요한 단계를 구분해 보고합니다. 현재 인수 요청만으로 새 수집·체결·게시·배포·PC 종료를 실행하지 않습니다.
7. 다음 실제 운영 변경 시 요청 날짜, 실제 데이터 기준일, 원천 수신 시각, 결정/체결일, 생성·게시시각을 각각 보고합니다.

### 새 대화에 붙여 넣을 시작 문장

> D:\Quant\quant2\docs\Quant2_5\QUANT_2_5_MASTER_HANDOVER_20260924.md를 읽고 Quant 총괄 작업을 인수해 주세요. 최신 사용자 지시·현재 파일·OS/QS/Harness 상태와 대조하여 완료·재사용·신규 필요 작업을 구분하고 현재 상태와 바로 다음 작업을 먼저 알려주세요. 기존 승인과 역할 분담은 유지하되, 이번 인수만으로 새 수집 cycle이나 과거 PC 종료 요청을 실행하지 마세요. Q25 V2 Live 연결의 로컬 개발은 완료됐고 실제 사전계획·체결·성과·운영 연결이 남아 있다는 지점에서 이어갑니다.

## 16. 이번 인수인계 작업의 변경 범위

- 이 문서와 현재 진행 문서의 인수 링크만 작성합니다.
- 기존 코드·운영 DB·원장·GCS·사이트·승인/라우팅 설정·모델 정책은 변경하지 않습니다.
- 새 대화 생성, 다른 담당 재실행 지시, 새 수집·배포·모의체결·자동매매·PC 종료는 수행하지 않습니다.
- 검증 결과는 별도 [인수 문서 검증 JSON](D:/Quant/quant2/reports/quant2_0/q25_master_handover_20260924/HANDOVER_VALIDATION.json)에 기록합니다. 문서 링크·핵심 기존 소스 핀·로컬 원장/산출물 해시 대조이며 원격 서비스 재검수나 성능평가를 대신하지 않습니다.
