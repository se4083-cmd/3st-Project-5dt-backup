# 4단계 분석 수신·검증·게시와 조회

Backend A 0.4.0 / migration 0004. Fabric이 지표·점수·순위를 계산하고 A는 제공 결과를 검증·게시합니다. A에는 운영 VOC 점수 계산기나 원장 집계 배치가 없습니다. 이번 출처는 LOCAL_SYNTHETIC이며 실제 Fabric·Azure·B 엔진 실행과 구분합니다. 공식 v4.1, schema_contract/config, 단계별 설계·검증·Fabric 계약과 실제 코드를 대조했습니다.

## 상태와 원자성

서비스 POST `/api/v1/analytics/batches` → `/{batch_id}/validate` → `/{batch_id}/publish`, GET `/{batch_id}`로 상태를 확인합니다. 성공 HTTP200이며 validate는 validation_result.passed까지 확인합니다. RECEIVED → VALIDATED → SUCCEEDED 또는 RECEIVED → FAILED입니다. 같은 ID·정규화 내용은 멱등, 다른 내용은409입니다. FAILED 수정은 새 ID를 사용합니다. 원본 fixture VALIDATED는 receipt가 없어 게시할 수 없으며 어댑터는 별도 deterministic UUID를 사용합니다.

수신은 head/receipt/감사, 검증은 네 mart/검증 결과/감사를 각각 한 트랜잭션으로 저장합니다. 검사 실패면 FAILED와 안전한 오류 코드만 남기며 mart는 적재하지 않습니다. 형식/금지 필드 오류는422이며 예외/감사 실패는 전체 rollback합니다. 업로드는 JSON 파싱 전에 실제 bytes를 세어 기본8MB, 네 테이블 합계20,000행으로 제한합니다. 파일 경로/URL을 서버가 읽지 않습니다.

게시는 singleton pointer → 후보 head를 잠급니다. validate는 head만 잠그므로 역행하지 않습니다. 저장된 네 mart의 행 수/해시를 재검사하고 이전 current 해제·새 성공/시각/current·pointer·감사를 원자 저장합니다. partial UNIQUE가 current1개를 보장합니다. window_end/source_as_of 각각 비감소이고 하나는 증가해야 합니다. 과거 성공 ID의 publish 재시도는 성공 상태만 반환하고 재승격하지 않습니다. 최초 미게시 조회는200 UNAVAILABLE/NO_PUBLISHED_BATCH/meta=null, 실패나 오래된 도착은 이전 성공 기준시각을 유지합니다.

PostgreSQL trigger는 게시된 head 내용(is_current 제외), receipt와 네 mart 변경/삭제/추가를 차단합니다. mart/receipt trigger도 head SHARE 잠금을 취해 게시와 직접 SQL 변경의 경합을 막습니다. 런타임 DB 계정에는 DDL/trigger 비활성화 권한을 주지 않아야 합니다. SQLite는 API 계약 개발 검증용이며 PG trigger/행 잠금의 대체가 아닙니다.

## wire와 검증

모델은 app/analytics_schemas.py, 기계 판독 계약은 openapi.json입니다. manifest에 batch/schema/rule/source, source_as_of/generated_at, history/operational/sales/prior/recent/window_end, calendar, 팀·상품 집합과 scope별 정확한 팀 집합, 테이블별 행 수/payload 해시, 별도 원천 입력 해시와 KPI/판매 분모 정의를 포함합니다. 원본 fixture head.checksums는 **원천 JSON 파일 해시**이므로 payload 해시로 복사하지 않습니다.

canonical JSON v1: 객체 키 정렬, UTF-8/ensure_ascii=false, separators=(comma,colon) 공백 없음, UTC Z datetime, ISO date/UUID, Decimal 고정 소수 문자열, 정수값 float 정수화, 유한수만 허용합니다. 행 배열은 PK 순, manifest 집합/scope도 정렬합니다. content_hash는 전체 정규화 submission, payload_checksums는 각 정규화 테이블이며 원천 파일 bytes 해시와 별개입니다. 구현은 app/analytics_canonical.py입니다.

허용 analytics-v1/voc_rule_v1, UTC 반열린 최근7일·직전7일·판매28일과 KST 자정 window_end, history_start≤operational_start<window_end≤source_as_of≤generated_at, generated_at≤서버현재+5분을 검사합니다. 행 날짜 범위, PK 중복, 실제 팀·상품 FK/manifest FK, scope 키/집합 중복, 상품×scope risk 전수, 행 수/해시, 카운터, 제공 추세의 C/U 합계, scope 공통 판매 S를 검사합니다.

C/P는 scope 최근/직전7일 complaint episode 수, S는 팀 공통 상품 유효 유료주문28일, N은 최근 episode 주문 중 판매 cohort에 포함되는 distinct 주문 수, M은 가장 큰 primary_issue episode 수, U는 미해결 episode 수, K는 distinct 고객 수입니다. M은 N의 부분집합이 아닙니다. A가 원장으로 이를 재계산하지 않습니다.

판매 누락→DATA_MISSING, 나머지 품질flag 실패→QUALITY_BLOCKED, S<30 또는 C<5 또는 K<3→LOW_SAMPLE, 나머지 ELIGIBLE입니다. 비대상 score/rank/band는 모두NULL입니다. 대상 score0–100/rank양수/band필수, band는 <40 NORMAL / <60 WATCH / 나머지 HIGH입니다. 제공 가중치·normalized/contribution 산술과 contribution합/score를 검사하며 운영 지표에서 normalized나 점수를 산출하지 않습니다. score DESC/C DESC/product UUID ASC의 제공 rank1..n을 검증하고 rank≤10을 반환합니다. 공동순위/새 순위 생성은 없습니다.

고객 ID/키·티켓 ID·원문·후속 메모·파일/URL 등 모델에 없는 필드는 중첩 위치에서도 거부합니다. 문장 없는 정형 allowlist이며 오류에 입력을 반사하지 않습니다. 검증 통과는 내부 정합성 통과이지 원천 사실·실제 Fabric 실행 증명이 아닙니다. FABRIC source도 인증 서비스 선언이며 origin_verification으로 이를 표시합니다.

## scope와 snapshot

ADMIN의 활성 user_team_scopes 전체 집합이 기본입니다. 반복 query team_ids로 부분집합만 선택합니다. 무권한/빈 범위는403, 중복422입니다. scope_key는 지원 입력이 아니며 제출해도 선택/권한에 사용하지 않습니다. 선택 팀 집합과 manifest scope의 정확한 동일성으로 찾고, 없으면 SCOPE_NOT_PROVIDED입니다. ALL4 fallback, 전체 TOP10 행 숨김, 팀별 점수 합산을 하지 않습니다.

원본 T1=863e9dc3-6c9f-5e86-b3b7-f639a91dbdd2(배송), T2=4a10ff03-d933-58aa-bfa2-e6c736275b70(반품환불), T3=6efbae37-4e53-59e9-b68c-9711bef485b1(상품결제), T4=6f797bdd-ec8f-5973-bb70-03d5a284d300(계정예외)입니다. 어댑터는 비어 있지 않은 조합15개 T1/T2/T3/T4, T1+T2/T1+T3/T1+T4/T2+T3/T2+T4/T3+T4, T1+T2+T3/T1+T2+T4/T1+T3+T4/T2+T3+T4, ALL4를 실제 UUID 집합으로 생성합니다.

GET `/api/v1/admin/analytics/voc/top`, `/voc/unavailable`, `/products/{product_id}`, `/kpi`는 인증부터 동일 REPEATABLE READ snapshot입니다. batch_id 선택은 managed 과거 성공만 허용하며 현재 권한을 매번 적용합니다. meta는 선택 팀만 포함하고 batch/asof/window/rule/schema/source/generated/published/current/stale/분모/cache_fingerprint를 제공합니다. 전체 manifest를 직원에게 반환하지 않습니다. 상품 상세의 표본·제외수·coverage/5요소 근거/제공 추세도 동일 scope입니다. 운영 티켓/고객360 이동은 각 리소스 권한을 다시 검사합니다.

HTTP no-store이며 서버 캐시는 없습니다. 향후 캐시는 principal/현재권한/batch/scope를 포함하고 hit 전 권한 검사해야 합니다. 점수는 관리 우선순위이며 실제 불량률·결함 확정이 아닙니다.

## KPI의 제공 한계와 팀 제안

제공 analytics_daily 행의 합만 계산합니다. ticket_count는 티켓 생성 cohort, 자동완료/이관 비율 분모는 그 ticket_count, 유형도 동일 행 집합입니다. 처리 평균은 Σduration_sum_seconds/Σduration_n이며 팀 평균을 평균내지 않습니다. message/cycle/VOC episode 수와 혼동하지 않습니다. full manifest scope는 미귀속 AUTO 포함, 부분 팀은 귀속 팀 행만 제공하고 coverage를 표시합니다. AUTO를 팀 자동 처리 성과로 배분하지 않습니다.

fixture-ticket-v1은 마지막 배정/상태의 합성 근사입니다. 재문의0·승인/검토 배정 proxy·SLA는 UNAVAILABLE/FIXTURE_PLACEHOLDER_OR_PROXY입니다. ticket-cohort-v1도 재문의/승인/검토/SLA 미합의 지표는 DEFINITION_NOT_AGREED입니다. raw rows의 해당 수치를 성과로 표시하지 않습니다. 처리시간도 제공 resolved-created 총시간이며 회차별 활성 처리/SLA 측정치가 아닙니다. product_daily는 팀 차원이 없으므로 full manifest scope만 tag grain 원본 행을 제공하고 부분 팀은 PRODUCT_KPI_HAS_NO_TEAM_SCOPE입니다. tag 중복 합계를 고유 티켓으로 만들거나 paid/inquiry/prior NULL을0으로 채우지 않습니다. 후속 내용·원문은 분석 응답에 없습니다.

**미확정 정책 제안:** 서비스 발급/회전/Managed Identity, source attestation, stale24시간/미래유예5분, byte/행 상한, wire버전, scope/첫 라우팅 팀 귀속/미귀속 AUTO, 생성 cohort·자동완료/이관 분모·처리시간 이벤트, 재문의의 티켓/cycle 단위, SLA/승인/검토 정의, 제품 KPI 팀차원/tag 중복 해소·NULL 분모를 팀과 확정해야 합니다.

## migration과 복구

0001–0003을 수정하지 않고0004를 추가했습니다. head의 검증/해시3필드, receipts와 singleton pointer, 강화 current CHECK와 PG 불변 trigger를 추가합니다. 기존 mart/운영 이력을 보존하며 증거 없는 과거 current만 내리고 pointer는NULL로 시작합니다. legacy SUCCEEDED 내용은 보존하고 새 wire로 별도 재수신/검증/게시합니다. SQLite는 parent rebuild 동안 자식 mart를 동일 트랜잭션 임시 테이블에 보존·복원하며 FK를 끄지 않습니다.

`python -m alembic upgrade head`와0004 readiness를 함께 적용합니다. receipt가 한 건이라도 있으면 downgrade를 거부합니다. 비어 있으면 legacy 데이터 보존 downgrade/re-upgrade가 가능하며 offline downgrade는 거부합니다. rollback은0004 호환 build를 사용합니다. 실제 운영 backup/restore·Azure 슬롯 전환은 미검증입니다. 실행 증거는 verification.md를 따릅니다.

SQLite migration 실행기는 transactional_ddl=True로 다중 revision 전체 rollback을 보장합니다. BEGIN IMMEDIATE를 실제 발행하는 이 저장소 엔진에 맞춘 설정이며, 이전 단계 이력 보호 검사 실패 때0004를 일부 내려버리지 않습니다.
