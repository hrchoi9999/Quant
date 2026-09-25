# Quant 1.0 AI 전면 폐지 사전 의존성 점검

기준일 2026-09-25. 사용자 지시: “지금 분석한 AI 학습모델은 전면 폐지하는 방향으로 수정…2.5 버전에서 AI…원점에서 재검토…의존성을 분석해서…먼저 점검…그후에 폐지”. 이전 선택적 유지 의견을 대체한다.

**점검 결론: 방향은 전면 폐지이며, 지금 파일·DB부터 삭제하면 안 된다.** 실제 서비스 검증기에 기존 T계열 등록과 AI 보류 상태가 필수값으로 남아 있다. 실행·생성·소비 계약을 함께 고친 뒤 기존 AI 실행 경로를 종료해야 한다. 이번 사전 점검에서 운영 소스·DB·게시자료를 변경하지 않았다.

## 1. 범위와 완료 기준

- 폐지 대상: 후보검증(공통·모델별·다기간), 주가수준평가/챌린저, 하락위험, 후보순위조정, 테마지속성, E계열 역할/비중템플릿/슬리브 AI, T-STOCK/T-ETF 학습기와 이 학습기에 의존한 현행 후보 공급. 해당 자동 학습·추론·재평가·실험 실행 및 현재 서비스 노출을 함께 종료 대상으로 한다. 이미 보관 중인 모델선택 AI도 재활성화하지 않는다.
- T계열은 학습기만 없애고 기존 예측 후보를 계속 최신으로 사용하는 방식으로 남기지 않는다. 별도 비AI 후보 모델이 필요하면 새 계약으로 설계하며 기존 T 성과·정체성을 자동 승계하지 않는다.
- 보존 대상: 가격·재무·수급·시장상태·ETF 분배금/분류·거래일 자료, 비AI S2/S3/CORE2/ACCEL/S4/S5와 Q25 기능, 과거 결정·보유·평가·실험 근거. AI 코드에 위치했다는 이유만으로 공유 함수·DB 전체·sklearn 패키지를 일괄 삭제하지 않는다.
- 이번에 평가하지 않은 QuantMarket 자체 시장예측·외부 LLM 설명 모델의 폐지로 범위를 확대하지 않는다. Quant가 더 이상 소비하지 않는 연결은 분리할 수 있지만 외부 소유 모델 자체 폐지는 별도 과업이다. Q25 AI 원점 재검토는 이 외부 입력의 필요성도 별도로 판단한다.
- 전체 단계: **①사전 의존성 점검 ②의존부 호환 수정·폐지·검증 ③Q25 AI 도입 원점 재검토**. 현재 ①의 고정 조건(범위/생성 경로, 소비/파손 영향, 제거 순서/검수조건)은 **3/3 완료**. 전체는 **1/3**, 실제 폐지 ②는 **미착수**다.

## 2. 의존성 지도와 선행 수정

| 영역 / 담당 | 확인한 경로 | 그대로 제거하면 생길 문제 | 폐지 전 조치 |
|---|---|---|---|
| 정기 실행 / OS·Harness | `src/quant_service/run_daily_quant_pipeline.py`의 T refresh, AI 생성·추적·E 연구 명령; `src/pipelines/rebuild_growth_valuation_ai_pipeline.py` 별도 가치평가 진입점 | 일시 skip만 쓰면 research_full/직접 명령에서 다시 학습·생성 가능 | 공통 폐지 목록으로 명령 구성과 직접 진입점을 차단. Harness 차기 승인 cycle의 범위·증거 기준 변경. 새 cycle은 시작하지 않음 |
| T 후보·C/I 연구 / Quant·OS | `run_t_stock_v01_operational_refresh.py`, `run_t_etf_v01_operational_refresh.py` → `tseries_operational.db`; `build_c_series_v01.py`는 ts_theme_labels/ts_candidates_latest/ts_rolling_watchlist_latest를 직접 읽음. I overlay 연구도 T DB 참조 | DB 삭제 시 SQL 오류; 파일만 보존하면 오래된 후보가 최신처럼 재사용될 수 있음 | T 현재 공급 종료와 소비 차단. C/I의 해당 입력 의존 분기 비활성·명시적 사용불가 처리. 비AI S 자료까지 중단하지 않음 |
| 공통 함수 / Quant | `build_e_series_etf_mart_v2.py` → `run_etf_ai_label_ablation.build_mart`; 여러 overlay가 `build_ai_overlay_v01`/valuation rule_score_engine의 함수를 import | 이름에 AI가 든 파일 일괄 삭제 시 남은 코드 import 실패 | 남길 비AI 데이터 함수는 공통 모듈로 분리하거나 함께 종료할 소비자를 확정한 뒤 제거 |
| 일별 검증 / OS | `validate_daily_pipeline_contract.py`는 기본 경로에서 T payload·DB·후보 최신성/존재 검사. `non_ai_scope.py`는 T/user 과거 부분의 해시 보존 | AI 파일 부재 실패, T 구역 삭제 시 preserved hash 검증 실패 | 임시 AI 보류와 영구 폐지를 구분한 계약. 비AI 6모델 최신성 검사는 유지; AI 항목만 명시적으로 검증 대상에서 제외 |
| 모델 범위 / Harness | `config/harness/model_scope_registry.yaml`에 T-STOCK 포함 8모델/고정 상태 계약 존재(승격 manifest 분기는 현재 inactive) | 현재 안 타는 분기라도 훗날 오래된 AI 모델 재활성화 가능 | 현행 폐지 목록과 범위 검증을 연결. 과거 승인 run·증거 자체는 수정하지 않음 |
| 포트폴리오 / QA | `D:/QuantAnalysis/portfolio_pipeline.py` ACTIVE_MODEL_IDS에 T-STOCK, reference에 T-ETF. `surviving_model_portfolio.py`도 T를 reference로 분류 | AI 폐지 후에도 활성 모델 메타데이터·참고 후보·기여 설명에 잔존 | 운영 모델 목록, 후보/랭킹/기여 집계, 과거 설명을 각각 조정. 현재 비AI 결정 경로를 유지하고 과거 성과는 보존 |
| 포트폴리오 검증 / QS | `private_portfolio_restore.py`가 정확한 ACTIVE_MODELS 및 reference T-ETF 목록·`ai_deferred` 상태를 요구 | QA만 변경하면 검증 거부로 포트폴리오 조회 실패 가능 | QA 새 payload 계약과 QS reader를 함께 전환. 무조건 허용하거나 검증을 삭제하는 방식은 금지 |
| 관리자/API / QS | `app.py`가 TSeriesOperationalApi/ValuationAiApi 생성; `internal_models_api.py`, `admin_new_entries_api.py`, valuation/tseries API와 nav/base/internal_models 화면 참조 | 초기 import 실패·깨진 링크·과거 점수 계속 노출·빈 자료를 정상 점수로 표시 | 신규 점수 소비 종료, 메뉴/API의 폐지 상태 처리, 일반 모델 페이지에서 AI 카드 제거. 과거 조회가 필요하면 명확한 역사 자료로 구분 |
| 게시 / Quant·OS·QS | `publish_public_current_to_gcs.py`, `scripts/harness/public_publish_guard.py`, `quant2/.../admin_publish_candidate.py`, QS `admin_private_gcs.py`의 객체 목록 | 필수 객체 부재 오류 또는 과거 AI 자료의 재게시 | 게시 목록·private allowlist·동기화·캐시 소비 변경. 클라우드 객체를 먼저 삭제하지 않음 |
| Q25 경계 / Master | quant2 storage의 shadow_json_contract/private_tseries_candidate/admin_publish_candidate에 과거 AI/T 호환 경로 존재 | 디렉터리 이름만 보고 Q25 핵심과 legacy 전달부를 혼동해 삭제할 위험 | legacy 전달 기능을 구분해 종료. Q25 기존 결정·모의성과 입력·회계와 비AI 기능 보존을 별도 검증 |

주요 소스 139개의 참조 위치와 SHA를 [사전 점검 근거](../../reports/quant2_0/ai_retirement_dependency_20260925/EVIDENCE.json)에 기록했다. 수치는 **참조가 발견된 파일 수**이며 활성 의존 개수나 139개 모두 수정 필요라는 뜻이 아니다. Quant src/scripts/config 및 quant2 src/config, QA 루트 Python, QS web Python/templates를 검색했다. 동적 전체 호출 그래프·클라우드 이미지·모든 수동 외부 작업까지 무의존이라고 인증하지 않는다.

## 3. 실제 파손 재현

기존 검수 완료 run112 자료를 SHA `59e5de1654a3c3b2c736937b167b84fe368206a0b9eb85cbbec91945ba0216d4`로 고정했다. QS 실제 `_legacy_structure` 함수에 메모리 사본만 전달했다.

| 입력 | 결과 |
|---|---|
| 기존 자료 그대로 | ACCEPTED |
| active_model_ids에서 T-STOCK 제거 | REJECTED: invalid_private_portfolio_current |
| reference_only_model_ids에서 T-ETF 제거 | REJECTED: invalid_private_portfolio_current |
| model_concentration_explanation 상태를 ai_deferred→retired로 변경 | REJECTED: invalid_private_portfolio_current |

마지막 사례는 외부 생성형 설명 모델까지 폐지하자는 뜻이 아니라 **공통 `ai_deferred` 문자열을 무작정 바꾸면 안 된다는 호환성 점검**이다. 이 함수 검증은 인증 HTTP·GCS 전환까지의 E2E를 뜻하지 않는다. 운영 자료와 소스 해시 불변, 검사 스크립트 Ruff/구문검사 통과를 확인했다. 재현 스크립트는 같은 폴더의 `audit.py`다.

## 4. 폐지 실행 순서와 완료조건

1. **정책 고정 및 복구 보존:** 현재 소유자별 변경 목록·폐지 모델/출력 목록 확정, 실제 변경 대상의 원본·SHA 보존. 역사 자료는 기존 위치 보존 또는 별도 보관으로 충분하며 대규모 삭제를 선행하지 않는다.
2. **소비 계약 선행 수정:** QA 모델목록/기여·QS 검증/화면/API·Quant 검증/게시의 영구 폐지 계약을 함께 만든다. 기존 운영 자료와 새 폐지 자료의 전환 조합을 검증한다. T/AI가 없는 상태를 현금100%, 점수0, 정상 최신값으로 대체하지 않는다.
3. **실행 연결 해제:** OS가 학습/추론/재평가/ablation·직접 실행 경로를 끊고 Harness가 차기 사용자가 승인한 cycle 범위를 갱신한다. 비AI 모델 및 공통 데이터 경로 유지. 이미 승인·진행 중인 실행이 있다면 실제 상태를 대조하고 조율하며 임의 종료하지 않는다.
4. **검증 후 반영:** AI 소스/모델/DB/현재 JSON 접근을 차단한 격리 조건에서 비AI 명령 구성·필수 입력 검증·QA 생성·QS API/화면·게시 후보 계획이 통과해야 한다. 동일 고정 입력의 비AI 후보/점수/보유·비중/기존 평가를 비교하고, 달라지면 숨은 의존으로 처리한다. 정확한 release 후보 검수 후 기존 배포 승인 범위와 담당 절차에 맞춰 반영한다.
5. **역사 자료와 코드 정리:** 실행·소비 참조가 제거된 것을 확인한 뒤 AI 전용 코드/모델을 보관 처리한다. 공유 DB 전체 삭제·원천 삭제·과거 성과 재작성은 하지 않는다. 폐지 대상 직접 실행도 명확한 종료 상태를 반환하도록 하고 오래된 설정으로 부활하지 않게 한다.

이 문서는 소유자별 실행 가능한 작업 경계를 제공한다. 아직 담당 코드 수정·새 운영 호환성 통과·게시/배포·실제 폐지를 완료한 상태가 아니다. 바로 삭제해도 안전하다는 결론이 아니라, 먼저 수정할 지점을 확인한 것이다.

## 5. Q25 AI 원점 재검토 기준

기존 학습모델·성과·모델명을 자동 이식하지 않는다. 먼저 비AI Q25에서 해결할 구체 문제를 정하고 AI가 필요한지부터 판단한다. 필요한 경우에만 사전 가용 입력·비AI 대조군·비용/낙폭·독립 검증 구간·실패 시 비AI 복귀 계약을 설계한다. AI를 도입하지 않는 결론도 허용한다. 현재 Q25 규칙·기업행위 작업은 보류 목록에 유지하며 이번 검토로 재개하지 않는다.
