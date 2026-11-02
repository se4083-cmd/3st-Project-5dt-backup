# 7단계 보관·삭제 dry-run 계약

Backend A0.6.0 / migration0006. **정리 영향의 미리보기만** 제공한다. 실제 삭제 API/명령/삭제 SQL 생성/실행/예약 작업은 없다. dry-run 결과를 삭제 승인·예약·법적 준수 증거로 사용하지 않는다.

## 정책 제안과 시각

공식 v4.1의 시연 종료 후 원문·추출30일/집계90일은 제안이다. 운영 보존기간·법적 근거·시연 종료시각 필드가 확정되지 않았다. 현재 구현은 `DEV_RETENTION_V1` 개발용 활동/저장 시각 기준 정책이며 원안의 시연 종료일 기준을 구현했다고 주장하지 않는다. raw_days/aggregate_days는 각각1–3650의 정수로 변경 검증할 수 있다. 동일 version이라도 설정이 다르면 policy_hash가 달라진다. 버전·설정·시계 계약을 함께 비교한다.

as_of는 명시적 timezone이 있는 시각, UTC로 정규화한다. 2000–2100 범위, 읽은 DB snapshot 시각보다 미래이면422다. **as_of는 나이 계산 기준이며 과거 DB 상태로 되돌리는 기능이 아니다.** 보호 조건과 권한은 현재 읽은 snapshot에서 검사한다. 과거 fixture의 source_as_of를 실제 현재시각으로 취급하지 않는다.

기간 N일은 UTC24시간×N이다. `anchor < as_of - N days`인 경우만 기간 초과이며 정확히 같은 시각은 보존한다. 마이크로초 앞/동일/뒤와 timezone offset을 PostgreSQL에서 검증한다.

티켓 연결 원문은 row.created_at·있으면 row.updated_at·ticket.updated_at·coalesce(ticket.resolved_at,ticket.updated_at)가 **모두 cutoff 이전**이어야 한다. 최근 변경/재문의/해결 이후 다시 기간을 계산하는 보수적 제안이다. NULL resolved_at인 RESOLVED 자료는 별도 판단 불가로 표시한다. 현재 회차와 미래/불명 회차를 제외하며 이전 회차라고 자동 후보가 되지 않는다.

공유 분석은 analytics_batches.created_at, receipt.received_at, 각 mart.created_at의 **저장 시계**를 사용한다. 원천 source_as_of/day/window_end를 저장 기간과 혼동하지 않는다. receipt는 추출30일, batch/mart는 집계90일이다. 같은 payload가 receipt와 mart에 중복 저장될 수 있으므로 행 수를 합쳐 고유 원문/고객 수로 해석하지 않는다. 제품 후속·ticket 없는 감사/멱등 snapshot은 별도 `:without_ticket` 집계이고 created_at 기준의 나이만 검사한다. 운영/정책/인증 참조 객체에는 승인된 보존 시계가 없으므로 기간 초과로 단정하지 않는다.

## endpoint와 명시 권한

`POST /api/v1/staff/retention/dry-run`

```json
{
  "purpose_code": "RETENTION_REVIEW",
  "as_of": "2026-10-31T03:00:00Z",
  "policy": {"version":"DEV_RETENTION_V1","raw_days":30,"aggregate_days":90},
  "scope": "TEAM"
}
```

ADMIN+RETENTION_TEAM_REVIEW는 현재 활성 허용 팀 전체가 기본 범위이며 team_ids는 그 부분집합만 허용한다. GLOBAL은 ADMIN+별도 RETENTION_GLOBAL_REVIEW가 필요하고 team_ids를 함께 받지 않는다. 전역 권한만 있는 사용자가 TEAM을 요청해도 팀 권한을 별도로 요구한다. ADMIN·다수 팀·전역 큐/중지 권한에서 보관 권한을 파생하지 않는다. migration/seed는 실제/개발 계정 모두 자동 grant하지 않는다. capability 응답에서 유효한 권한을 확인할 수 있다. 부여 자체는 운영 계정 정책/팀 합의 대상이며 권한 부여 API는 추가하지 않았다.

팀 보고는 ticket.team_id가 선택 팀 안에 있고, 모든 과거 배정·route·후속의 origin/owner team이 알려져 있고 선택 팀 안인 자료만 센다. 여러 회차는1..현재 회차 각각에 명시 route가 있어야 한다. NULL·타팀·과거 귀속 불명은 결과뿐 아니라 검사/제외/이유 건수에서도 숨긴다. category나 끝난 배정만으로 추정하지 않는다. 이 보수적인 범위 때문에 기존 fixture 일부는 팀 보고에서 검사되지 않는다. GLOBAL 보고만 미귀속·공유 저장소를 검사한다.

공유 receipt/batch/분석 marts·프로필/주문/정책/인증 참조는 팀별 안전한 보관 단위를 확정할 수 없으므로 TEAM에서는 UNSUPPORTED_TEAM_SCOPE/모든 건수NULL/이유{}이다. 일부 mart에 팀 키가 있어도 receipt·공유 PK 전체의 보관 가능성과 같지 않으므로 글로벌 수치로 fallback하지 않는다. 지원하지 않는 대상 이름은 고정 inventory이며 데이터 존재를 의미하지 않는다.

401 인증,403 역할/명시 권한/범위,422 목적·시각·설정·중복 팀/추가 필드,503 DB 장애다. 미래 as_of는 RETENTION_AS_OF_IN_FUTURE, 범위 오류는 RETENTION_TEAM_SCOPE_DENIED이다. 임의 SQL·테이블명·경로·URL·execute·force는 extra=forbid로 거부하며 요청값을 오류/로그에 반사하지 않는다. Cache-Control:no-store다.

## 출력의 의미

모든 응답은 dry_run=true, PREVIEW_ONLY_NOT_DELETION_AUTHORIZATION, policy_status=DEVELOPMENT_PROPOSAL_NOT_LEGAL_POLICY, as_of/snapshot_at/UTC/경계/적용 팀/policy_hash/result_fingerprint를 포함한다. 후보 ID 목록·원문·내부 메모·고객 프로필·비밀값은 제공하지 않는다. 상세 ID API도 이번에 만들지 않았다.

대상별 inspected_count는 허용된 저장 행 수다. past_retention_count는 **기간상 후보 수**이며 삭제 가능 건수가 아니다. blocked_count는 명확한 업무 보호/참조가 있는 기간 초과 행, requires_design_change_count는 그 보호가 없는 행 중 구조/불변성 충돌, undetermined_count는 그 외 판단 불가다. candidate_count는 모두 판정 가능한 나머지만 허용하지만 **현 모델에는 법적 hold·JSON 참조의 완전한 판정이 없으므로 원문 최종 후보는0**이다. 분석도 현재/참조/불변성 때문에 최종 후보0이다. 이를 ‘정리할 데이터가 없다’고 표시하지 않는다.

excluded_count는 기간 이내+BLOCKED+REQUIRES_DESIGN_CHANGE다. `inspected_count = candidate_count + excluded_count + undetermined_count`이며 blocked/design은 excluded의 부분집합이다. 보존 시계 미정인 REFERENCE_OR_METADATA는 past_retention_count=0, 전부 undetermined_count로 보고한다. reason_counts는 겹치는 보호 조건을 모두 세므로 합계가 행 수보다 클 수 있다. 대상 간 동일 티켓·중복 snapshot도 있으므로 전체 고유 수로 합산하지 않는다.

## 실제 로컬 저장 위치와 영향

| 고정 대상 | 원문/중복 가능 필드·검사 범위 | 판단/제약 |
|---|---|---|
| messages | body | SQL 집계만. 현재 회차/업무·감사·재시도/작업 source_message FK 보호 |
| ai_suggestions | draft,order_snapshot,evidence_refs,gate_results | 승인 suggestion FK와 JSON 참조/마스킹 상태 판단 한계 |
| approvals | gate_snapshot | suggestion/ticket/cycle/hash·승인 이력 보존 설계 필요 |
| followup_actions | public_note,internal_note | 모든 회차 미완료 필수 후속 보호. 제품 후속은 글로벌 별도 집계 |
| idempotency_keys | response_snapshot | 원문/메모가 응답 snapshot으로 복제될 수 있음. ticket 또는 followup FK의 재시도 보장/TTL 미정 |
| audit_events | payload | 기존/합성 JSONB에 원문이 없다고 가정하지 않음. 감사 보존 시계 미정. ticket 없는 감사 별도 집계 |
| tickets | issue_tags,primary_issue,last_error_code | 운영 이력·FK 뿌리. 티켓 삭제 가능으로 판단하지 않음 |
| analytics_receipts | payload,validation_result | 실제 제출 JSON 복제. 실패/미게시도 receipt UPDATE/DELETE trigger 보호 |
| analytics_batches | manifest,row_counts,checksums | 현재 pointer/과거 게시·receipt FK. 비현재만으로 후보 확정 금지 |
| analytics_daily / product_daily / product_voc_daily / product_risk | 제공 KPI·metrics/components·점수/순위 | 현재 게시 보호; 과거 SUCCEEDED도 불변 trigger. 공유 보관 단위/Fabric 재게시 설계 필요 |
| customers/orders/shipments/returns | profile_masked/customer_key/display_name,order_number/amount,eta_if_known,reason | 글로벌 행 수만, 업무·프로필·재무 보존 정책 미정 |
| knowledge_documents/automation_rules | body/blob_path/version,conditions/version | 정책 버전/승인 JSON 참조와 활성 기간. 글로벌 행 수만, 보존 정책 미정 |
| users | login_name/password_hash/allowed_team_ids | 글로벌 행 수만, 값 조회 없음. 인증/비밀값 보관 정책은 별도 |
| assignments/jobs/queue_routes | cycle/team/source_message/lease/error metadata | 글로벌 참조 행 수만. 활성 배정·작업·유효 lease는 티켓 원문 보호 조건에도 사용 |

JSON 필드의 존재·중복 저장 가능성과 참조 구조를 조사한 것이며 JSON 내용 전체를 개인정보 탐지/분류한 검사는 아니다. allowlist 테이블/컬럼만 집계 SQL에 사용하고 본문/JSON payload를 SELECT하거나 대량으로 메모리에 복사하지 않는다. 인증의 기존 사용자 조회와 테스트의 내용 hash 비교는 production retention 집계와 별개다.

현재 고객360의 건수/정형 facts·예외 큐 건수는 운영 DB 실시간 SELECT 결과이고 별도 저장 테이블/생성형 요약 cache를 만들지 않았다. 운영 KPI 저장 위치는 analytics_daily, 제품/VOC는 나머지3개 mart다. 외부/향후 cache나 사용자 export의 부재를 보장하는 주장은 아니며 해당 복제본은 NOT_INSPECTED로 남긴다.

미해결 티켓, 모든 회차의 OPEN/IN_PROGRESS 필수 후속, 종료되지 않은 배정, PENDING/RETRY/RUNNING 작업/유효 lease, 현재 회차, 멱등 ticket/followup 참조, 승인·감사 참조를 제외 사유로 보고한다. 분석 현재는 is_current와 publication pointer를 모두 검사한다. 과거 게시·모든 receipt의 불변 trigger와 FK를 우회하지 않고 REQUIRES_DESIGN_CHANGE로 표시한다. 비게시 VALIDATED/FAILED 역시 FK/재수신/재게시/증거 보존 정책이 미정이므로 최종 후보가 아니다.

## 일관성·불변·미검사

인증부터 집계/참조/결과/최소 감사까지 하나의 PostgreSQL REPEATABLE READ snapshot이다. as_of는 그 snapshot 이전/동일이어야 한다. snapshot_at은 DB transaction_timestamp이며 모든 대상에 동일하다. fingerprint는 사용자/적용 범위/정규화 정책·시각/집계 결과를 묶고 snapshot_at·임의 감사 UUID는 제외한다. 동일 as_of·정책·권한·DB snapshot의 같은 결과를 재현한다. 별도 요청 사이 감사 추가 등 DB가 바뀌면 fingerprint도 바뀔 수 있다. fingerprint는 삭제 토큰·승인 서명이 아니다.

보호 잠금을 잡아 미래 삭제를 예약하지 않는다. 향후 실삭제 구현은 팀/법적 정책 확정과 별도 승인뿐 아니라 **실행 직전 현재 권한·상태·lease·참조·불변성·백업 범위를 다시 검증**해야 한다. 이번 보고서를 실행 입력/행 ID 승인으로 사용하지 않는다.

업무·원문·집계 변경 없이 RETENTION_DRY_RUN 감사1행만 추가한다. 목적은 RETENTION_REVIEW, payload={}, target_id/ticket_id=NULL이다. 원문/토큰/메모/후보ID/자유 입력 목적을 감사에 넣지 않는다. 감사 저장 실패면 성공 보고서 없이 rollback한다. 거부 감사는 기존 독립 경계를 유지한다.

Blob·외부 추출/Fabric Bronze/Silver/Gold·백업/replica/WAL·API/DB/외부 로그·파일/export/cache는 **NOT_INSPECTED**다. 로컬 팀/상품/scope/capability/제어 history/publication metadata도 내용 보관 정책 밖이며 이번 내용 검사가 아니다. 저장소 이름 목록이 실제 연결/존재 확인을 뜻하지 않는다. 클라우드/외부 서비스를 확인하러 접속하지 않는다.

## migration·인수·범위 종료

0006은 기존 staff_permissions CHECK에 RETENTION_TEAM_REVIEW/GLOBAL_REVIEW만 추가하기 위해 필요하다. 기존0001–0005는 수정하지 않았다. 업무 데이터/원문/분석 내용·기존 권한을 변경하지 않고 새 권한도 부여하지 않는다. readiness는0006이다. 새 권한 또는 RETENTION_DRY_RUN 감사가 있으면 downgrade를 거부하고 offline downgrade도 거부한다. 빈 신규 기능 상태의0005 downgrade/re-upgrade를 검증한다.0006 호환 build로 복구하고 보관 권한을 모르는 구 build를 권한 운영에 섞지 않는다.

Frontend는 후보0과 기간초과0을 구분하고 BLOCKED/설계변경/판단불가/미검사를 각각 표시한다. B는 기존 gate/queue/fencing 계약을 유지하며 보관을 이유로 작업/승인/후속을 끝내지 않는다. Fabric은 receipt·전체 batch의 보관 단위·과거 게시 불변성/재게시·원천/추출/Gold 보관 시계·외부 추출본 처리와 공통 정책을 합의해야 한다. AI/RAG는 원문 복제/마스킹/정책 버전·JSON 참조를 합의해야 한다.

보관 dry-run까지 Backend A의 합의된 로컬 P0 경계를 구현했지만 실제 삭제·법적 준수·상용 보존/백업 정책과 B/AI/Fabric/Frontend/외부 발송 통합은 완료 주장이 아니다. 새 단계를 자동 시작하지 않는다. 실제 실행 결과/회귀 수치는 verification.md를 따른다.

팀 확정 항목은30/90일 및 예외 기간, 시연 종료일/업무 종료·마지막 활동/저장 시계 중 기준, receipt 제출본의 추출/집계 분류(현재는 추출30일 제안), 현재 회차의 보존 해제 조건, 법적 hold/조사·분쟁 상태, JSON·정책 버전/승인·감사·멱등의 수명과 참조, 공유 batch/과거 게시·정정/재게시 단위, 전역 권한 부여/정기 검토, Blob·외부 추출·백업/replica/WAL·로그·사용자 export 범위다. 이 합의는 이번 로컬 개발의 실행 승인을 다시 요구하는 절차가 아니며, 향후 정책/실삭제 설계의 선행 조건이다.
