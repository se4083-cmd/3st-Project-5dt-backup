# 6단계 직원 큐·내부 상세·전역 중지

Backend A **0.5.0 / migration0005**입니다. 공식 v4.1과 5단계 인수에서 남긴 세 P0의 A 경계를 구현합니다. 보관·삭제 dry_run은 다음 단계입니다. 아래 권한/큐 범위/상태명/표시 정책은 구체 정책이 없던 부분을 채운 **제한적인 구현 제안**이며 팀 확정이 필요합니다. 실제 B·AI/RAG·발송 엔진은 구현하거나 호출하지 않았습니다.

## 명시적 권한

staff_permissions는 user_id/permission/granted_by/granted_at을 저장합니다. migration과 모든 seed는 **누구에게도 새 권한을 부여하지 않습니다**. 고객/직원 역할은 매 요청 DB에서 확인합니다. 기존 ADMIN, user.allowed_team_ids, 여러 팀 scope, JWT에 적은 임의 권한으로 global 권한을 얻지 않습니다. GET /api/v1/staff/capabilities는 현재 역할에서 유효한 명시적 권한만 반환하며 실제 리소스 권한 검사를 생략하는 근거가 아닙니다.

| 권한 | 추가 조건 |
|---|---|
| EXCEPTION_QUEUE_READ | AGENT 또는 ADMIN, 활성 user_team_scopes와 현재 명시 route 팀. AGENT는 자신의 팀+supported category도 필요 |
| UNROUTED_QUEUE_READ | ADMIN만. 요청에서 queue_scope=UNROUTED를 명시해야 함. 팀 수와 관계없이 별도 grant 필요 |
| AUTOMATION_READ | ADMIN만. 전역 상태·이력 조회 |
| AUTOMATION_STOP | ADMIN만. 전역 중지 명령 |
| AUTOMATION_RESUME | ADMIN만. 전역 재개 명령. STOP 권한에서 파생하지 않음 |

일반 운영 grant/revoke API는 추가하지 않았습니다. 실제 승인 주체/권한 부여·회수 절차는 팀 결정 후 별도로 운영해야 합니다. 로컬 검증의 INSERT grant는 새 격리 schema/개발 계정에 대한 명시적인 테스트 fixture입니다. 실제 계정에 전역 권한을 자동 부여하지 않습니다.

## 예외 큐와 귀속

GET /api/v1/staff/exception-queue, 같은 경로 /counts를 제공합니다. queue_scope는 기본 ROUTED, 별도 UNROUTED이고 reason(UNASSIGNED/AUTO_FAILED/ROUTING_FAILED/HUMAN_REQUEST), team_id, limit/cursor를 지원합니다. /counts는 같은 scope/reason/team_id predicate를 사용합니다. 목록의 total/counts는 cursor 적용 전 같은 허용 집합이며 한 요청의 인증·건수·목록은 REPEATABLE READ입니다.

queue_routes의 (ticket_id,cycle_no)별 명시 팀만 귀속으로 사용합니다. category/과거 배정/ticket.team_id fallback으로 귀속을 추측하지 않습니다. 현재 회차 route가 없거나 team=NULL이면 UNROUTED이며, 비활성 팀 route도 명시 전역 관리자용 quarantine으로 보입니다. 그 응답 route_team_id는NULL입니다. 전사 UNROUTED 열람도 최소 DTO만 허용하며 내부 상세/고객360 권한이 되지 않습니다. 재문의는 새 회차에 route가 없으므로 옛 route로 접근하지 않습니다. 과거 회차 route 행은 보존합니다.

종료 티켓은 제외하고 현재 유효 배정이 없거나 현재 job이FAILED인 티켓을 대상으로 합니다. FAILED는 종류에 따라 AUTO_FAILED/ROUTING_FAILED, source_message가 연결된 HANDOFF는 HUMAN_REQUEST, 나머지는 UNASSIGNED입니다. UNASSIGNED는 ‘아직 담당자가 없음’이지 자동으로 사람 처리로 전환하라는 명령이 아닙니다. 유효 배정 여부는 현재 cycle/미종료·시작된 assignment/활성 상담사·팀을 검사합니다. 상담사의 종료 배정은 큐나 상세 권한으로 되살리지 않습니다.

QueueItem에는 ticket_id/cycle_no/route_team_id/통제된 reason·stage/queued_at/waiting_seconds/job_state/automatic_state만 있습니다. 고객 ID·프로필·주문·메시지·내부 오류 문자열은 없습니다. 대기시간은 snapshot 기준0 이상이며 route 기록시각, 없으면 현재 job 생성시각으로 계산합니다. 페이지는 ticket.created_at DESC/UUID DESC이고 매 페이지에 권한을 다시 적용합니다.

AUTO의 PAUSED는 중지 중 대기, RECLAIM_REQUIRED는 이전 generation 또는 만료 lease의 재claim 필요, HUMAN_REVIEW_REQUIRED는 FAILED입니다. 상태 행 부재는 CONTROL_UNAVAILABLE로 표시하며 사람 큐를 숨기지 않습니다. 실제 DB 전체 장애에는 조회503이 발생할 수 있습니다. AUTO job을 중지 시 삭제/숨김/성공 처리하지 않습니다.

B의 최소 DB 인터페이스는 다음과 같습니다. service_id는 감사 식별자이며 인증을 대신하지 않습니다. 실제 B 서비스 인증/최소 DB 권한은 B 연결 시 필요하며 무인증 HTTP 라우팅 endpoint는 없습니다.

```python
from app.exception_queue import RouteCommand, record_queue_route
with factory.begin() as session:
    route = record_queue_route(session, ticket_id, RouteCommand(
        expected_revision=ticket_revision, cycle_no=cycle,
        expected_route_revision=0, team_id=explicit_team_id,
    ), service_id="authenticated-b-routing")
    # ticket 잠금 유지. B가 실제 배정/티켓 변경을 같은 transaction으로 이어감.
```

신규 route의 expected_route_revision=0, 변경에는 반환 revision을 사용합니다. ticket revision과 cycle, route revision, 활성 팀FK를 검증하고 route+감사를 savepoint/외부 transaction에 원자 저장합니다. 함수는 팀 선택·배정·사용자 권한 부여·ticket.version 변경을 하지 않습니다. B는 route→배정/팀/status/version/job 종료·lease 해제를 같은 ticket 잠금 transaction에 통합해야 합니다. 실제 B 대신 이 계약을 테스트 fixture가 호출했습니다.

## 직원 내부 상세

POST /api/v1/staff/tickets/{ticket_id}/internal, body는 purpose_code=ACTIVE_SUPPORT 또는 관리자 QUALITY_REVIEW, include_history=false가 기본입니다. 고객은403, 허용 범위 밖/종료·이전 배정 상담사는404입니다. 현재 유효 배정+팀/category 또는 활성 팀 scope의 관리자가 필요합니다. 큐 cap/route만으로 허용하지 않습니다. 성공/거부와 목적을 원문 없는 감사로 남기며 감사 실패에는 응답 전체를 rollback합니다.

StaffTicketDetail은 고객 TicketDetail과 별도 DTO입니다. current_proposals/historical_proposals, 현재 cycle/revision/as_of, MISSING/SYNTHETIC_ONLY/RECORDED_FACTS 상태를 제공합니다. 각 최대10개·승인 최대20개/참조 최대10개이며 truncated를 표시합니다. 과거 자료도 현재 티켓 권한이 있어야 하고 include_history로 명시 요청해야 합니다. 옛 담당자가 과거 회차 번호를 제시해 접근할 수 없습니다.

customer_ref는 권한 있는 직원이 고객360 경로를 구성할 최소 UUID이고 이름·연락처·프로필이 아닙니다. 큐/고객 DTO에는 포함하지 않습니다. 이를 받아도 고객360은 purpose와 현재 per-ticket 범위를 다시 검증하므로 전체 고객 이력 권한이 생기지 않습니다.

제안은 category/confidence, 제한된 template/prompt/model version 코드, rule version/활성 여부, 검증된 정책 참조(document_id/version/hash 일치·topic·기간·승인 상태), 명시적 bool gate, 연결 검증한 승인 metadata만 반환합니다. 원시 draft/프롬프트·정책 본문/제목·blob path·임의 URL/JSONB·토큰/비밀번호·연결정보는 노출하지 않습니다. version 문자열도 코드 형식/길이와 민감 표식을 제한합니다. 초안 텍스트는 기본 안전 정책상 draft_exposed=false이며 B/AI가 검증된 안전 텍스트 계약을 제공하기 전에는 원시 draft를 표시하지 않습니다.

gate는 ownership_valid/policy_valid/confidence_valid/pii_valid/risk_valid/no_money_execution/fixture_only/policy_valid_in_fixture만, 실제 bool만 허용합니다. 알려지지 않은 키/문자열/중첩 객체는 반환하지 않고 미제공 값은NULL입니다. JSONB 전체를 복사하지 않습니다.

주문 snapshot의 order_id/version을 실제 ticket.order_id/customer_id/product_id와 검증합니다. 반환은 ****마지막4자리 참조, 버전·수량·통제된 상태뿐이며 원래 주문 번호·고객키/주소/금액을 제외합니다. 상태/수량은 CURRENT_OPERATIONAL_DB에서 확인한 사실이라고 명시하고, AI snapshot 버전이 다르면 STALE_ORDER_SNAPSHOT으로 표시합니다. 잘못된 연결은 INVALID_LINK이고 값을 생성해 채우지 않습니다.

승인은 suggestion/ticket/cycle/content_hash를 모두 검사하고 틀린 연결은 제외·표시합니다. 합성/과거 회차/이전 ticket revision/만료·미발효/누락·불일치 근거/비활성 정책을 구분합니다. CURRENT_RECORDED도 ‘현재 기록’이지 실행 승인 판정이 아닙니다. **모든 usable_for_execution=false / execution_authority=DISPLAY_ONLY_NOT_AUTHORIZATION**입니다. 실제 정책/승인/AI gate를 대신 구현하지 않았으며 고객 endpoint/OpenAPI의 공개 DTO는 바꾸지 않습니다.

## 전역 중지·재개

가상 기업1곳의 singleton automation_control에 paused/revision/generation/reason/changed_by/changed_at을 저장하고 automation_control_history에 모든 초기/변경 기록을 남깁니다. PostgreSQL history는 UPDATE/DELETE trigger로 불변입니다. 새 migration의 초기 상태는 unpaused/revision1/generation1이며 기존235개 저장 계약을 유지합니다. 초기 허용은 실제 worker/정책 활성화가 아닙니다.

GET /staff/automation-control, GET /history(limit,before_revision), POST /stop, POST /resume을 제공합니다. 각각 명시 권한이 필요합니다. 중지 사유는 SAFETY_INCIDENT/OPERATOR_PAUSE, 재개 사유는 INCIDENT_RESOLVED/VERIFICATION_COMPLETE의 제한된 코드입니다.

```json
{"expected_revision":1,"reason_code":"SAFETY_INCIDENT"}
```

```json
{"expected_revision":2,"stopped_revision":2,"reason_code":"INCIDENT_RESOLVED"}
```

변경마다 revision/generation 모두+1, 상태·이력·감사는 원자 저장합니다. 재개에는 현재 paused 상태와 그 중지 revision이 정확히 필요합니다. revision 경쟁409, 이미 중지/중지 revision 불일치409, 권한403, 잘못된 필드/사유422입니다. 실패/timeout 시 성공을 추정하지 말고 권한 있는 GET으로 확인합니다. 재개는 정책/규칙 active나 job 성공 상태를 바꾸지 않습니다.

AUTO claim은 매번 상태를 읽고 이미paused면[]입니다. 최종 확정은 ticket/job 잠금 뒤 global SHARE gate를 다시 확인합니다. `automation_jobs.automation_generation`은 claim 당시 generation이고 AutomaticReply에도 전달할 수 있습니다. 기존 호출의 optional generation 생략도 **저장 job generation**을 검사하므로 우회할 수 없습니다. 중지 전 claim은 재개 후에도 이전 generation이어서 거부됩니다. 재claim은 이전 RUNNING generation을 만료 전에도 회수하며 새 token/generation/attempt를 저장합니다. 옛 token은 다시 사용할 수 없습니다.

WorkRejected는 AUTOMATION_PAUSED/AUTOMATION_GENERATION_CHANGED/AUTOMATION_CONTROL_UNAVAILABLE이며 SQL 조회 실패도 예외로 종료합니다. 상태 부재/실패를 허용으로 처리하지 않습니다. HANDOFF claim은 전역 AUTO gate를 읽지 않으며 고객 접수·사람 요청·사람 해결 gate·후속·조회는 유지합니다. 기존 최종 응답을 삭제하거나 취소하지 않습니다.

잠금 순서는 고객/후속의 user→ticket→job/후속, AUTO worker의 ticket→job→control SHARE입니다. 중지/재개는 actor user→control UPDATE만 잠그고 ticket/job으로 역행하지 않습니다. route는 ticket mutex 뒤 route를 기록하고 job을 함께 다룰 때는 ticket→route→job을 유지합니다. worker가 control을 잠근 뒤 새 ticket을 찾거나 user로 역행하면 안 됩니다.

최종 확정이 SHARE를 먼저 얻으면 그 응답이 commit된 다음 중지가 적용됩니다. 중지가 먼저면 worker는 기다린 뒤 paused/generation을 다시 보고 거부됩니다. stop 응답이 성공한 이후의 공통 DB 확정은 차단하지만 이미 확정된 과거 응답은 보존합니다. stop write 자체가 실패한 경우에는 중지 성공을 보장하지 않습니다.

## B와 외부 발송의 구분

작업 시작/재시도/heartbeat·실제 발송 직전에 현재 cycle/version/token/worker/lease와 global generation/paused를 재검사해야 합니다. app.automation_control.assert_automatic_allowed는 ticket/job 잠금 뒤 사용할 공통 global gate입니다. 직접 SQL이나 legacy fenced_job_predicate만으로 확정하면 이 경계를 우회하므로 지원하지 않습니다. B는 공통 함수 통합과 최소 DB 권한/발송 outbox·멱등/취소 정책이 필요합니다.

외부 네트워크 작업 동안 global SHARE/DB transaction을 유지하지 않습니다. DB 확인 후 외부 호출 직전에도 중지가 발생할 수 있고 이미 진행된 외부 호출은 이 코드가 취소하지 못합니다. **검증한 것은 공통 DB claim/확정의 차단이며 실제 외부 발송 중단 보장은 아닙니다.** 실제 B worker/발송기는 실행·검증하지 않았습니다.

## migration·복구·검증

0001–0004를 수정하지 않고0005를 추가했습니다. 기존 job에 generation1을 부여하고 이력/fixture를 보존합니다. route는 과거 배정에서 backfill하지 않고 권한도 auto grant하지 않습니다. readiness는0005를 요구합니다. READ_STAFF_TICKET 감사, route/capability 또는 변경 control history가 있으면 downgrade를 거부하고 offline downgrade도 거부합니다. 이력이 없는 빈 상태만0004 downgrade/re-upgrade를 허용합니다. rollback은0005 호환 build/worker를 사용해야 합니다.0004 worker는 중지를 모르는 구버전이므로 운영 복구 대상으로 무조건 사용하면 안 됩니다.

readiness는 DB/schema 준비 상태이고 AUTO 실행 가능 여부는 control gate가 별도로 확인합니다. 상태 장애를 이유로 사람 경로를 의도적으로 중지하지 않습니다. 실제 운영 백업·배포/외부연동은 미검증입니다. PostgreSQL 경합/rollback/fixture·재시작과 실제 HTTP의 실행 결과는 verification.md를 따릅니다. 모든 실행은 새 로컬 클러스터와127.0.0.1만 사용합니다.

## 0.6.1 정합성 보정

유효 배정 검사와 AGENT ticket_scope는 repository.agent_assignment_exists를 공유한다. 위 회차/배정·상담사/팀 조건에 더해 정규화 user_team_scopes/category, 사용자 실제 팀과 티켓 처리 stage를 함께 검사한다. 실제로 처리할 수 없는 배정은 허용 큐를 숨기지 않으며 비활성 route는 기존 quarantine 권한을 유지한다. 자동 확정의 control SHARE 대기 후에도 실제 wall clock으로 lease를 재확인하며 저장 시각을 갱신한다. 잠금 순서/generation·사람 경로·기존 이력 보존은 그대로다. 상세 회귀는 review-fixes.md/verification.md를 따른다.
