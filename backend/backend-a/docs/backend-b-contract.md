# Backend B와 내구 작업 계약

0.11.0의 전향적 기록은 [monitoring-effects.md](monitoring-effects.md)의 내부 Python 경계를 따릅니다. B의 재시도/HUMAN 전환/배정 엔진을 A에 추가하지 않았으며, 기존 성공 writer와 route/고객 명령의 같은 transaction에 사실만 연결했습니다. 최신 B 소스 검토와 실제 Worker 검증은 별개입니다.

0.10.0 로컬의 [배정 추천](assignment-recommendations.md)은 조회 전용입니다. 실제 `app.recommendations.view` 및 `repository.agent_eligibility`/`workload.ticket_facts`의 입력·인증·snapshot 책임은 해당 문서에 적었습니다. 후보/유효기간은 실행 허가가 아니며 B가 최신 ticket/cycle/route/직원 자격·부하·유효/물리 배정을 다시 검증해야 합니다. FAILED AUTO 보존 HUMAN 조회는 가능하지만 기존 미구현 실패/이관/배정 writer를 구현한 것은 아닙니다.


0.9.0 선택 확장: 내부 `AutomaticReply.provenance`에 실제 질문·suggestion id/revision/hash·approval·model/prompt·retrieval ref·당시 정책 id/version/hash/chunk를 전달할 수 있습니다. [실제 시그니처·예시·거부/원자 경계](quality-review.md)를 따릅니다. 미제공도 기존 성공 흐름을 유지하며 MISSING으로 기록합니다. 다른 회차/답변/근거는 거부합니다. 최신 제안/정책을 과거 응답에 추정 연결하지 않습니다. B 실패·HUMAN 전환·배정 writer는 추가하지 않았습니다.


Backend A 0.6.1 / migration0006 기준입니다. A의 예외 큐·직원 상세·전역 중지와 generation gate에 보관 dry-run을 추가했습니다. B의 AI/RAG·정책/승인·라우팅·배정·외부 부작용 엔진은 구현하지 않았습니다. [6단계 설계](phase6-staff-queues-control.md), [보관 계약](phase7-retention-preview.md)과 [B 인수](backend-b-handoff.md)를 함께 따릅니다. 실제 HTTP의 고정 응답/배정은 계약 검증이며 B 엔진 통합 성공이 아닙니다.

## 작업 필드와 종류

| 필드 | 의미 |
|---|---|
| job_id / ticket_id | UUID 작업/대상, ticket_id 필수 FK |
| cycle_no | 양수 업무 회차, ticket_id+cycle_no UNIQUE |
| expected_ticket_version | 작업 생성 당시 ticket.version. 확정 명령의 expected_revision과 일치해야 함 |
| job_kind | AUTO 또는 HANDOFF. 기존 행은 AUTO로 유지 |
| source_message_id | 이 명령의 고객 요청 메시지. 신규 HANDOFF에서 필수 |
| reason_code | HANDOFF의 CUSTOMER_REQUEST/DISSATISFIED/COMPLEX_ISSUE/OTHER/HUMAN_CONTINUATION |
| status | PENDING/RUNNING/RETRY/SUCCEEDED/FAILED/HANDED_OFF/CANCELLED |
| attempt / next_attempt_at | claim 횟수(초기0), UTC 처리/재시도 가능 시각 |
| lease_token / lease_owner / lease_until | claim마다 새 UUID, worker ID, UTC 만료시각 |
| automation_generation | AUTO claim 당시 전역 generation. 정지/재개 뒤 이전 claim 확정 금지. HANDOFF는 이 AUTO gate와 별개 |
| error_code | 원문 없는 내부 사유. 고객 응답 제외 |
| created_at / updated_at | 실제 UTC 시각. fixture 분석 고정시각과 구분 |

RUNNING일 때 lease 세 필드가 모두 있어야 하며 다른 상태에는 모두 NULL이어야 합니다. HANDOFF는 자동 답변 생성 작업이 아닌 사람 라우팅/배정 요청입니다. 일반 자동 worker가 이를 AUTO로 바꾸거나 자동 재처리하지 않습니다. 원본 종료 HANDED_OFF 작업은 과거 자동화의 결과이며 신규 HANDOFF 요청으로 활성화하지 않습니다.

## 예약 인터페이스

`claim_jobs(session, worker_id, limit=10, lease_seconds=60, job_kind="AUTO")`는 PostgreSQL 전용입니다. PENDING/RETRY 또는 만료 RUNNING, next_attempt_at 경과, 현재 cycle/version 일치를 검사합니다. AUTO는 requested_mode=AUTO와 OPEN/PROCESSING, HANDOFF는 HUMAN과 HANDOFF_PENDING만 예약합니다. SQLite에서는 명시적으로 거부합니다.

2단계부터 ticket을 SKIP LOCKED로 먼저 잠근 뒤 job을 잠급니다. 고객 명령·응답 확정과 동일한 ticket → job 순서를 지켜야 합니다. user 잠금이 필요한 고객 명령은 그 앞에 user를 잠급니다. B는 ticket을 잠근 상태에서 고객 user를 나중에 잠그는 코드를 추가하지 않습니다.

```python
with session_factory.begin() as session:
    auto_jobs = claim_jobs(session, "auto-worker", job_kind="AUTO")
# 여기서 DB commit 완료. 이후 외부 AI/HTTP 실행.

with session_factory.begin() as session:
    handoff_jobs = claim_jobs(session, "routing-worker", job_kind="HANDOFF")
# 실제 팀/상담사 선정 및 배정 엔진은 B의 후속 구현.
```

신호는 선택적이며 PostgreSQL polling으로 작업을 회수할 수 있습니다. API 프로세스는 worker daemon을 실행하지 않습니다. 별도 서비스 연결에는 전용 DB 최소 권한 또는 인증된 서비스 API가 필요합니다. 인증 없는 작업 HTTP endpoint는 없습니다. inspect_jobs는 kind·reason·ID·시각만 출력하고 원문/token은 출력하지 않습니다.

## 자동 응답 공통 저장 경계

B는 정책/근거/소유권/승인/안내 범위 등 자신의 gate를 먼저 검증한 뒤 다음 함수를 호출해야 합니다. 이 함수가 답변의 의미·정책 유효성을 판단해주는 것은 아닙니다. 고정 합성 답변을 넣은 계약 테스트를 실제 AI 엔진 검증으로 해석하지 않습니다.

```python
from app.finalization import AutomaticReply, WorkRejected, commit_automatic_reply

command = AutomaticReply(
    job_id=job["job_id"], lease_token=job["lease_token"], worker_id="auto-worker",
    cycle_no=job["cycle_no"], expected_revision=job["expected_ticket_version"],
    message=approved_public_reply,
)
try:
    with session_factory.begin() as session:
        receipt = commit_automatic_reply(session, command)
except WorkRejected as error:
    # 원문/token을 로그에 넣지 말고 reason code로 처리.
    pass
```

확정은 ticket → job 잠금을 얻은 뒤 현재시각 기준으로 검사합니다. 현재 cycle/version, job expected version/cycle, AUTO 모드·작업 종류·허용 상태, RUNNING, token/worker, lease 만료를 모두 확인합니다. 이미 해당 회차의 최종 OUT이 있거나 미완료 필수 후속이 있으면 거부합니다. 성공 시 PUBLIC SYSTEM/OUT final 메시지, ticket RESOLVED/AUTO/version+1, job SUCCEEDED/lease 해제, 최소 감사를 한 트랜잭션에 저장합니다. caller가 commit하고 네트워크는 이 트랜잭션 안에서 실행하지 않습니다.

WorkRejected.code는 WORK_NOT_FOUND, STALE_TICKET_REVISION, AUTOMATION_NOT_ALLOWED, INVALID_LEASE, FINAL_REPLY_ALREADY_EXISTS, BLOCKING_FOLLOWUP입니다. stale/사람 경로 결과를 새 회차로 복사해 자동 발송하지 않습니다. `fenced_job_predicate`는 하위 호환용 job 조건일 뿐이며 단독 사용으로 ticket 경쟁을 막을 수 없습니다.

0005는 여기에 AUTOMATION_PAUSED/AUTOMATION_GENERATION_CHANGED/AUTOMATION_CONTROL_UNAVAILABLE를 추가합니다. 최종 확정은 ticket→job 뒤 control SHARE를 잡아 paused/job generation을 다시 검사하고 최종 저장 commit까지 유지합니다. AutomaticReply.automation_generation에 claim 값을 전달합니다(하위호환 생략도 저장 job generation을 검사합니다). claim/확정이 전역 상태 조회에 실패하면 예외로 종료하며 허용으로 바꾸지 않습니다. 기존 predicate만으로는 전역 중지나 실제 발송을 승인할 수 없습니다.

B가 직접 SQL로 메시지를 저장하면 DB의 회차별 최종 응답 UNIQUE만 적용되고 최신 회차/lease는 자동 검증되지 않습니다. 반드시 공통 함수 또는 동등한 잠금/검증 경계를 통합해야 합니다. 외부 발송·금전/주문 부작용의 exactly-once를 보장하는 함수는 아닙니다. 별도 outbox·외부 멱등키는 B 책임입니다.

## 재문의와 직접 연결 이후 B 책임

수락된 고객 명령은 cycle/version을 올리고 이전 미완료 job을 CANCELLED, lease를 NULL로 바꿉니다. 이전 활성 배정을 종료하고 team_id를 비웁니다. 사람 경로를 요청한 최신 회차는 재문의해도 HUMAN/HANDOFF로 이어집니다. 이전 worker는 응답 저장 시 거부됩니다. 종료 작업/기존 최종 메시지/승인 이력은 보존합니다.

HANDOFF worker는 현재 회차·version·HUMAN·lease를 ticket/job 잠금 아래 재확인한 뒤 업무 category와 활성 팀·상담사 scope에 맞춰 실제 배정을 확정해야 합니다. 배정 행, ticket.team_id/status/version, job HANDED_OFF와 lease 해제, 감사를 원자 저장하는 것을 제안합니다. 이 배정 엔진과 사람 최종 응답 저장 엔진은 이번에 만들지 않았습니다. 사람이 이미 대기/처리 중인 직접 연결 API는 409로 중복 요청을 거부합니다.

heartbeat, backoff/jitter, 제한 횟수, 영구 실패/자동 이관, stale job 청소는 B의 후속 구현입니다. lease 변경만으로 ticket.version을 올리지 않습니다. B가 PROCESSING 전이 같은 업무 변경으로 version을 올린다면 같은 트랜잭션에서 작업 expected version과 caller command를 맞춰야 합니다.

## 검증 범위

실제 PostgreSQL 계약 테스트는 동시 claim, HANDOFF/AUTO 분리, 만료 lease 회수, 이전 token/version/cycle 거부, 최종 응답 중복, 재문의/확정의 양쪽 잠금 순서와 잠금 대기 중 만료를 검사합니다. 실제 B의 AI/RAG·gate·팀 선정/배정·외부 발송·장애 복구 E2E는 미검증입니다. 실행 결과는 [검증 보고서](verification.md)에 구분합니다.

## 3단계 후속 인수와 사람 해결 게이트

후속은 cycle_no=원래 회차, responsibility_cycle_no=인수 회차, origin_team_id=최초 책임 팀을 보존합니다. 재문의가 후속을 완료/취소하지 않습니다. 새 배정 전 옛 상담사의 접근은 차단되고 기존 책임 팀 관리자 큐에는 후속이 남습니다. 새 담당자는 현재 배정/업무 범위를 확인한 PATCH로 인수하며, 팀 이전에는 원래/새 팀 scope를 모두 검증합니다. B는 직원 API 또는 별도 서비스 principal의 권한 경계를 정한 뒤 같은 owner_valid/scope 정책을 재사용해야 합니다. 임의의 고객 JWT나 관리자 역할 문자열만으로 인수하지 않습니다.

모든 회차·담당 유무·팀의 미완료 필수 후속이 해결을 막습니다. AUTO 확정은 공통 assert_no_blocking_followups를 사용합니다. 사람 응답 엔진에는 다음 저장 전 게이트를 제공합니다.

```python
from app.resolution import lock_resolution_gate

with session_factory.begin() as session:
    ticket = lock_resolution_gate(
        session, ticket_id, expected_revision=revision, cycle_no=cycle,
        mode="HUMAN", human_user=authenticated_agent,
    )
    # 여기서 ticket lock 유지. B의 유효한 최종 메시지/해결/version/감사를 원자 저장해야 함.
```

이 함수는 DB에서 상담사 활성/역할을 다시 읽고 현재 배정/팀/category/cycle/HUMAN 경로와 필수 후속을 검증합니다. 사람 답변 생성/발송·승인·해결 저장 엔진이 아닙니다. 마지막 후속 완료도 티켓을 자동 해결하지 않습니다. caller가 이 트랜잭션에서 최종 상태를 저장해야 하고 cycle별 최종 OUT UNIQUE를 지켜야 합니다.

잠금은 후속 writer의 user(NO KEY UPDATE) → ticket/product → followup, B의 ticket → job → 후속 검사입니다. 후속을 먼저 잠근 뒤 ticket으로 역행하지 않습니다. 후속 생성이 먼저 commit하면 자동 해결은 BLOCKING_FOLLOWUP, 자동 해결이 먼저면 필수 후속 생성은 TICKET_ALREADY_FINISHED입니다. 원문 없는 감사만 기록합니다.

3단계 검증은 이 공통 게이트와 테스트용 배정·고정 답변의 계약 검증입니다. 실제 B 사람 응답/인수 엔진 통합 성공으로 보고하지 않습니다. 상세 정책은 [3단계 설계](phase3-followups-customer360.md)에 있습니다.

후속 변경은 후속 자체 version을 올리고 ticket.version을 자동 증가시키지 않습니다. parent ticket mutex와 해결 시 최신 blocker 재검사로 경합을 보호합니다. 고객360 요약 fingerprint는 후속 증거도 포함하므로 ticket.version 하나만으로 요약 캐시를 판정하지 않습니다.

6단계의 route는 record_queue_route/RouteCommand를 같은 ticket mutex transaction에서 기록합니다. expected_revision/cycle_no/expected_route_revision/명시팀만 사용하고 과거 배정·category로 귀속을 추정하지 않습니다. route 변경만으로 ticket.version을 바꾸지 않으며 실제 배정/버전/job 변경은 B가 원자 통합합니다. API 변경자(user)→control UPDATE와 worker(ticket→job→control SHARE) 사이에 역행하지 않습니다. 외부 모델/발송 동안 DB SHARE를 유지하지 않습니다. 실제 dispatch 전 재검증·outbox/멱등/이미 진행된 발송 중단은 B에서 별도 구현·검증해야 합니다.

## 4단계 분석 경계

A의 analytics-v1은 Fabric 계산 결과 수신·검증·게시·조회 계약입니다. B가 점수/순위를 계산하거나 mart/current를 직접 갱신하지 않습니다. 서비스 게시 토큰은 사용자/관리자 권한과 별개입니다. 운영 ticket→job→후속 검사 잠금과 분석 pointer→batch 잠금을 결합하지 않습니다. 분석 성공/실패는 ticket 해결 명령이 아니며 후속을 완료/삭제하지 않습니다.

Fabric 운영 추출을 위해 회차별 TICKET_REOPENED/AGENT_REQUESTED/AUTOMATIC_REPLY_COMMITTED, 유효 배정/종료, 최종 응답/승인, 후속 원래/책임 회차와 필수 blocker 의미를 유지해야 합니다. 현재 ticket snapshot만으로 재문의 횟수·사람 응답 처리시간을 복원하지 않습니다. 새 분석 KPI의 재문의/승인/검토/SLA는 정의 미합의로 unavailable이며 fixture0/proxy를 B 실제 성과로 해석하지 않습니다. 실제 B 배정/사람 응답/인수 엔진·Fabric 추출기 통합은 이번 검증에 없습니다.

## 7단계 보관 미리보기 경계

[보관 계약](phase7-retention-preview.md)의 A API는 읽기 집계+최소 감사만 수행합니다. 활성 작업/lease·현재 회차·모든 회차 필수 후속·멱등·승인/감사 참조를 보호하므로 B는 보관을 위해 이 상태를 임의 종료하지 않습니다. 기존 ticket→job→control SHARE/회차·버전·lease·generation fence는 그대로입니다. 실제 삭제·작업 취소·외부 발송/스토리지 호출은 없습니다. 향후 삭제를 합의한다면 실행 직전 현재 권한·참조·업무 상태를 다시 검증해야 하며 이 보고서는 실행 입력이 아닙니다.

## 0.6.1 lease·배정 보정

[독립 검토 수정](review-fixes.md)을 따른다. 자동 공통 확정은 모든 잠금 gate 후 첫 쓰기 직전에 wall-clock utcnow로 lease_until을 다시 검사한다. transaction_timestamp/SQL now의 고정 시각을 쓰지 않는다. 만료 시 INVALID_LEASE와 저장0이며 실제 발송에는 B의 별도 최종 재검사가 여전히 필요하다. 유효 상담사 배정은 repository.agent_assignment_exists의 회차·배정·활성 역할/팀·정규화 scope/category·stage 조건을 티켓 권한과 큐에서 공유한다. 라우팅/권한을 복원하거나 전사 공개하지 않는다.


## 2026-11-03 Azure 이름 이전 후 현재 환경

API base는 https://csflow-backend-a.azurewebsites.net/api/v1, PG는 csflow-backend-a-pg.postgres.database.azure.com/backend_a, Plan은csflow-backend-a-plan이다. source0.6.1/head0006과 기존 모든행/계정/권한·자동중지를 보존했다. 구3개 삭제·공용잠금 복원과 실제검증/백업은[azure-migration.md](azure-migration.md)를 따른다. B·AI·Fabric·발송은미연결/미검증이고 실제 Frontend origin은추측해등록하지 않았다. 서비스 인증 비밀값이나 DBpassword는이문서에없다.
