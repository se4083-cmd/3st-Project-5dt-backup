# 티켓·회차·감사·후속 계약

각 절의 상태 표시는 **구현 확인 / 팀 합의 필요 / 제안 / 미구현**이다. 아래는 앱 코드에서 확인한 경계이며 전체 B 처리 엔진이나 Fabric emitter를 구현했다는 뜻이 아니다.

## 티켓 상태와 전이

**구현 확인:** tickets.status는 PostgreSQL text + CHECK이며 `OPEN`, `PROCESSING`, `WAITING_CUSTOMER`, `HANDOFF_PENDING`, `ASSIGNED`, `IN_PROGRESS`, `FOLLOWUP_PENDING`, `RESOLVED`, `CANCELLED`만 허용한다. DB CHECK는 허용 값만 검사하며 모든 상태 전이를 자동 통제하는 trigger는 없다.

| 구현 경계 | 기존 상태 | 결과 | 참고 |
|---|---|---|---|
| POST /api/v1/tickets | 신규 | OPEN / AUTO, cycle_no=1, version=1 | 고객 본인 주문이 있으면 customer/product 복합 연결 검사 |
| POST /api/v1/tickets/{id}/reopen | 위 9개 중 CANCELLED를 제외한 8개 | AUTO 경로면 OPEN / AUTO, 사람 경로면 HANDOFF_PENDING / HUMAN | expected_revision, 소유권, 멱등키 검사 |
| POST /api/v1/tickets/{id}/request-agent | CANCELLED 제외. 이미 사람 경로 대기/활성은 아래 별도 거부 | HANDOFF_PENDING / HUMAN | 자동 재처리하지 않음 |
| commit_automatic_reply 공통 내부 함수 | OPEN 또는 PROCESSING / AUTO | RESOLVED / resolution_mode=AUTO | 현재 job/cycle/version/lease/중지 generation/필수 후속 검사 |
| lock_resolution_gate(mode=HUMAN) | 현재 유효 상담사 접근이 되는 상태 + HUMAN | 해결 쓰기 허용 경계만 반환 | 실제 사람 응답 writer는 B 책임; A에 완성된 사람 해결 HTTP API 없음 |

**구현 확인:** 사람 경로 판단은 requested_mode=HUMAN 또는 resolution_mode=HUMAN 또는 상태가 HANDOFF_PENDING/ASSIGNED/IN_PROGRESS/FOLLOWUP_PENDING인 경우다. request-agent는 해당 4상태와 HUMAN+WAITING_CUSTOMER에서 새 키로 반복해도 `409 HUMAN_REQUEST_ALREADY_ACTIVE`다. 동일 멱등키·같은 요청 재시도는 저장 receipt를 재반환하므로 신규 배정 작업이 생기지 않는다. 사람이 요청된 회차를 재문의해도 자동 경로로 되돌리지 않는다.

**미구현 / 팀 합의 필요:** OPEN→PROCESSING, HANDOFF_PENDING→ASSIGNED/IN_PROGRESS, 고객 대기·실패 이관·SLA·실제 취소의 전체 전이 엔진은 B가 연결해야 한다. 이 상태 이름이 존재한다는 이유로 해당 전이 API가 모두 있다고 해석하지 않는다. 과거 RESOLVED/CANCELLED 이력과 현재 진행 상태를 혼합해 처리시간을 추정하면 안 된다.

## cycle_no, revision, version

| 실제 위치 | 구현 확인한 의미 |
|---|---|
| tickets.cycle_no(bigint) | 재문의/사람 요청마다 +1인 처리 회차 |
| tickets.version(bigint) | 티켓 동시성 토큰. 재문의/사람 요청·자동 확정 등 쓰기에서 증가 |
| API ticket revision/expected_revision | DB tickets.version의 표현. tickets.revision 물리 컬럼은 없음 |
| followup_actions.version | 후속 자체 동시성 토큰. API followup revision/expected_revision에 대응 |
| followup cycle_no / responsibility_cycle_no | 처음 생성된 회차 / 현재 인수해 책임지는 회차. 인수해도 원래 cycle_no는 보존 |
| ai_suggestions.revision | 티켓/회차 안의 AI 제안 revision. 티켓 version과 별개 |
| approvals.ticket_version | 승인 때 대상 티켓 version |
| queue_routes.revision | 회차별 route 변경 토큰 |
| automation_control.revision / generation | 중지·재개 변경 토큰 / 오래된 AUTO 작업의 fencing 세대 |

**구현 확인:** ticket_commands.change_cycle은 사용자→ticket→job(정렬)→배정 순으로 잠근다. 같은 트랜잭션에서 기존 PENDING/RUNNING/RETRY 작업을 CANCELLED로 바꾸고 lease_token/until/owner를 NULL, error_code=SUPERSEDED_BY_CUSTOMER로 만든다. 종료되지 않은 배정은 ended_at을 채운다. cycle/version을 +1, team_id·resolution_mode·resolved_at·first_replied_at·last_error_code를 초기화하고 새 고객 PUBLIC/IN 메시지, AUTO 또는 HANDOFF/PENDING job, 멱등 receipt, 감사를 저장한다. HANDOFF에는 source_message_id와 reason_code가 남는다. 이전 route는 새 회차 route로 자동 복제되지 않는다. 이전 후속은 완료/삭제/이동하지 않는다.

**구현 확인:** AUTO 확정 잠금은 ticket→job→control SHARE이며 모든 잠금 gate 뒤 최종 쓰기 직전에 UTC wall clock으로 lease 만료를 다시 검사한다. transaction_timestamp()를 lease 만료 시각으로 쓰지 않는다. 현재 회차와 expected_ticket_version, worker/lease, AUTO 모드, 중지/세대와 blocker가 맞아야 한다. 최종 OUT 응답은 partial UNIQUE `(ticket_id,cycle_no) WHERE final_reply AND direction='OUT'`로 한 건만 가능하다. control 중지 전 claim을 재개 후 재사용할 수 없다. DB 확정 차단이 외부 발송 중단까지 보증하지는 않으며 B가 실제 발송 직전 재검사해야 한다.

## audit_events: 실제 식별자와 한계

2026-11-04 **0.11.0 소스 재검토:** 아래 감사 모델·공통 record의 설명은 여전히 유효하다. 첨부 합성 audit 8,820행의 CREATED/STATUS_CHANGED/CUSTOMER_CONTACT는 현재 A 업무 emitter와 다르다. [비교 및 최소 projection](audit-export-review.md)에 JSONB/문자열 차이와 접촉 시각 한계를 정리했다. 감사 시각·문구에서 접촉을 추정하지 않고, CUSTOMER_CONTACT producer나 messages Export는 이번에 구현하지 않았다. 이 문서의 다른 절은 기존0006 검토 기록이며 최신 전체 상태 전이·B 실행 계약으로 재검증한 것이 아니다.

**구현 확인:** `event_id uuid` PK가 **있다**. `event_key text`는 별도 UNIQUE다. ticket_id/cycle_no/actor_user_id/actor_service/target_id는 NULL 가능하고 target_type/action은 text다. created_at=timestamptz이며 A Python utcnow 기본값이다. `event_time`, `sequence`, `LSN`, `before`, `after`, `ticket_version` 물리 컬럼은 없다. `updated_at`도 없다. result=varchar(16)의 SUCCESS/DENIED/FAILURE CHECK, reason_code=varchar(64), payload=jsonb가 있다.

**구현 확인:** app/audit.py의 record는 호출마다 event_id와 event_key를 각각 새 UUID로 만든다. action/result/reason/연결 ID를 기록하고 payload는 `{}`로 고정한다. 예: TICKET_CREATED, TICKET_REOPENED, AGENT_REQUESTED, AUTOMATIC_REPLY_COMMITTED, FOLLOWUP_CREATED/UPDATED/STATE_CHANGED, ANALYTICS_RECEIVED/VALIDATED/REJECTED/PUBLISHED. 이 목록은 영구 Enum이 아니며 저장 action은 자유 text다. 접근·거부·목록·목적 조회 등의 감사도 섞여 있다. 실패 요청의 ACCESS_DENIED는 요청 rollback 뒤 독립 트랜잭션에서 저장될 수 있다.

**구현 확인:** `event_key`는 API 멱등키도, 모든 업무 변경의 결정적 ID도 아니다. 새 호출은 같은 업무 action에도 새 키를 만든다. fixture import는 과거 payload/키를 그대로 보존할 수 있어 앱의 `{}` 관례만으로 모든 과거 payload에 개인정보가 없다고 단정할 수 없다. 직접 DB writer/seed/일부 공통 gate는 row-level CDC before/after를 남기지 않는다. **audit_events는 전체 테이블 변경을 포괄하는 CDC 로그가 아니다.** 감사와 모든 회차 버전 이력을 동일시하면 안 된다.

| 중복/순서 영역 | 구현 확인 또는 제안 |
|---|---|
| API 생성·재문의·사람 요청·후속 생성 | 구현 확인: idempotency_keys PK=(user_id,key), operation/request_hash/response_snapshot. 같은 사용자 전역 namespace이며 다른 요청409 |
| 감사 저장 | 구현 확인: event_id PK + event_key UNIQUE. 재시도 자체가 같은 감사 event_key를 선택해 주는 기능은 아님 |
| Gold 수신 | 구현 확인: batch_id + 정규화 content_hash. 같은 ID 다른 내용409 |
| Export 재전송 | 미구현/제안: (source_system, export_schema_version, export_batch_id, table, projected_PK)로 snapshot 배치 내 dedupe. event 데이터는 원본 event_id를 별도 유지 |
| 변경 이벤트 순서 | 팀 합의 필요: created_at,event_id 정렬은 재현용 tie-break일 뿐 commit 순서나 전역 인과 순서가 아님. version/cycle도 row 간 전역 순서가 아님 |
| 증분·지연 이벤트 | 미구현/제안: CDC LSN/commit 순서 또는 outbox가 필요. updated_at watermark+overlap만으로 지연 commit·삭제를 완전히 포착한다고 주장하지 않음 |

**제안:** snapshot 재수신은 batch 단위 checksum 일치 후 교체 없이 멱등 처리한다. 지연 이벤트는 event 시각과 수신 시각을 구분하고 영향 기간을 Fabric에서 재계산한 새 Gold batch로 게시한다. 정정 horizon·tombstone·watermark/retention은 합의가 필요하며 늦게 온 이벤트 자체를 폐기하거나 새 배치를 과거 데이터라고 무조건 거부하는 정책을 가정하지 않는다.

## 후속 상태·인수·해결 gate

**구현 확인:** 상태는 OPEN/IN_PROGRESS/DONE/CANCELLED이다. OPEN→IN_PROGRESS/DONE/CANCELLED, IN_PROGRESS→DONE/CANCELLED만 허용한다. 동일 상태·OPEN으로의 역행, DONE/CANCELLED 이후 수정/재개는409다. DONE이면 completed_at 필수이며 그 외에는 NULL이다. CANCELLED이면 cancelled_at과 CUSTOMER_WITHDREW/NO_LONGER_NEEDED/DUPLICATE/OTHER 사유가 필수이고 그 외에는 둘 다 NULL이다. due_at은 NULL 또는 created_at 이후이며 API 신규/변경 due는 실제 now보다 미래여야 한다. 상세 CHECK와 API DTO는 [schema](schema.md)·[OpenAPI 원본](../openapi.json)을 따른다.

**구현 확인:** 담당 팀은 활성·허용 팀, 담당 사용자는 활성 직원/유효 scope여야 한다. 상담사는 현재 회차 배정/팀/category 범위에서 자기 인수를 한다. 담당 변경으로 책임 회차를 현재 회차로 갱신해도 origin_team_id/cycle_no는 유지한다. IN_PROGRESS/DONE 전환에는 유효 owner와 현재 책임 회차가 필요하다. CANCELLED도 기존 접근 scope·revision을 검사한다. 고객은 본인 티켓의 비어 있지 않은 public_note가 있는 공개 DTO만 보며 내부 메모/직원 정보는 제외한다. 삭제 HTTP 동작도 실제 행 삭제 대신 취소다.

**구현 확인:** 모든 회차의 `blocks_resolution=true AND status IN ('OPEN','IN_PROGRESS')`인 티켓 후속은 해결을 막는다. 현재 owner가 없어도, 이전 회차라도 막는다. 후속 쓰기와 해결은 같은 ticket 잠금을 먼저 사용해 생성/해결 경합을 막는다. 마지막 후속 DONE은 티켓을 자동 RESOLVED로 바꾸지 않는다. 자동 확정은 공통 gate를 호출하고 사람 writer도 lock_resolution_gate를 써야 하지만 실제 B writer 연결은 미검증이다. 팀 재배정 전 종료된 상담사의 권한을 되살리지 않는다.

근거: [ticket_commands](../../app/ticket_commands.py), [finalization](../../app/finalization.py), [resolution](../../app/resolution.py), [followups](../../app/followups.py), [audit](../../app/audit.py), [B 계약](../backend-b-contract.md).
