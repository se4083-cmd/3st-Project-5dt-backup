# Backend B 로컬 인수

0.9.0 인수: `commit_automatic_reply(session, command)`의 반환값·호출자 commit 책임은 그대로입니다. 선택 `provenance` 및 새 PROVENANCE_* 거부 코드는 [품질 계약](quality-review.md)에 정리했습니다. policy body hash/원문과 실제 사용한 입력/근거를 제공하지 못하면 누락 상태로 남습니다. 이는 HTTP endpoint가 아니고 실제 AI/RAG/B Worker 연동 성공도 아닙니다. 기존 실패/이관 검토 제안은 그대로 미구현입니다.


규범은 backend-b-contract.md, phase2-cycles.md, phase3-followups-customer360.md입니다. 서버는 worker daemon/B 엔진을 실행하지 않습니다. 로컬 검증은 tests/http_scenario.py의 고정 응답·배정 fixture·gate 뒤 테스트 최종 writer이며 실제 승인/발송 엔진 성공이 아닙니다.

AUTO/HANDOFF는 claim_jobs의 job_kind로 분리합니다. PostgreSQL만 지원하며 caller가 claim transaction을 commit한 후 외부 작업을 수행합니다. ticket→job 잠금, cycle/version/expected_ticket_version, RUNNING token/worker/lease, requested_mode와 상태를 지킵니다. 고객 명령은 앞에 user 잠금이 있으므로 B가 ticket을 잡은 후 고객 user로 역행하지 않습니다.

자동 최종 저장은 app.finalization.AutomaticReply/commit_automatic_reply를 사용합니다. 재문의·사람 요청 뒤 이전 작업과 lease는 무효이며 최종 응답을 최신 회차로 복사하지 않습니다. 같은 회차 최종 OUT은 한 건입니다. 공통 함수는 B의 정책/AI/근거/승인 gate를 대신 검증하지 않습니다. 실제 외부 부작용/발송에는 별도 멱등/outbox가 필요합니다.

사람 응답은 lock_resolution_gate(mode=HUMAN) 뒤 같은 ticket 잠금 transaction에서 B가 유효한 최종 응답/해결/version/감사를 저장해야 합니다. 모든 회차 미완료 필수 후속이 막고 마지막 후속 완료는 자동 해결하지 않습니다. 후속의 cycle_no는 원래 회차, responsibility_cycle_no는 인수 회차입니다. 현재 배정·팀/category 확인 후 직원 PATCH로 인수하고, 팀 이전은 양쪽 scope가 필요합니다. admin 책임 큐에 미인수 후속을 보존합니다.

남은 연결: HANDOFF 팀 선정/배정의 내구 확정, 실제 사람 응답 저장/승인, lease heartbeat와 갱신 fencing, 재시도 상한/backoff/jitter·영구 실패의 원자 사람 이관, 외부 발송 중복 방지/장애 복구입니다. A의 지속 중지 상태/API와 AUTO claim/공통 확정 gate는6단계에서 구현했습니다. 실제 worker의 시작/재시도/heartbeat/발송 직전 연결은 B 공동 P0입니다. 현재 automation_rules.active=false를 중지 구현으로 해석하지 않습니다. 중지 시 HANDOFF/사람 큐 유지와 in-flight 취소·재개 정책을 합의해야 합니다.

로컬 verify는 실제 AUTO/HANDOFF claim과 공통 자동 확정·사람 gate만 호출합니다. 배정 선택과 사람 최종 writer는 테스트 코드라고 명시했습니다. 외부 모델/발송·클라우드 연결은 하지 않았습니다. B 엔진을 붙인 후 동일 경합/권한/이관/중지 회귀를 별도로 통과해야 합니다.

## 6단계 필수 연결

record_queue_route + RouteCommand는 현재 ticket revision/cycle과 expected_route_revision(최초0), 명시 team UUID 또는NULL을 받습니다. 서비스 ID는 감사 식별자일 뿐 인증이 아닙니다. B는 인증된 서비스/최소 DB 권한을 준비하고 team 선택은 자신이 수행합니다. ticket mutex 아래 route+배정/티켓·job 변경을 원자 처리하며 source category/종료 배정으로 queue 귀속을 추정하지 않습니다. 함수 자체가 ticket.version을 올리지 않으며 새 회차에는 새 route가 필요합니다. CAS409는 최신 상태를 읽고 충돌을 처리하고 무조건 덮어쓰지 않습니다.

AUTO claim 반환의 automation_generation을 보관하고 AutomaticReply에 전달합니다. claim/확정은 매번 paused/generation을 재검사하며 stop→resume 전후의 옛 claim은 재사용할 수 없습니다. 이전 generation RUNNING은 새 token/attempt로 재claim할 수 있습니다. HANDOFF에는 이 AUTO gate를 적용하지 않습니다. 정책/규칙 active는 재개가 변경하지 않으며 B의 기존 정책 gate가 계속 필요합니다.

잠금은 ticket→job→control SHARE입니다. 중지/재개는 actor user→control UPDATE만 사용합니다. B가 control을 먼저 잠그고 ticket으로 역행하거나 네트워크 호출 동안 SHARE를 유지하면 안 됩니다. assert_automatic_allowed(session, generation)는 ticket/job 잠금 뒤 사용할 공통 global gate입니다. 실제 시작/재시도/heartbeat/발송 직전에는 cycle/version/token/worker/lease도 함께 확인해야 합니다. legacy fenced_job_predicate만으로는 전체 fence가 되지 않습니다.

상태 부재는 AUTOMATION_CONTROL_UNAVAILABLE, 중지는 AUTOMATION_PAUSED, 이전 세대는 AUTOMATION_GENERATION_CHANGED로 거부하며 SQL 조회 실패도 허용으로 바꾸지 않습니다. 이미 공통 DB 확정이 먼저 commit된 응답은 이력으로 보존합니다. DB gate 후 외부 호출 사이 경합/이미 진행 중인 발송 취소·outbox/멱등·중단 보장은 실제 발송기 통합에서 별도 검증해야 합니다. 이 구현은 외부 발송 보장이 아닙니다.

0005와 호환되지 않는 구 worker는 이 중지를 모르므로 복구 때 함께 사용하지 않습니다. 실제 B/AI/발송 엔진은 이번에 실행하지 않았습니다. 로컬 고정 응답/배정 fixture·공통 DB 경합 검증과 구분합니다.

## 7단계 보관 참조

A의 retention/dry-run은 집계 미리보기이며 작업/배정/승인/후속을 완료·삭제하지 않습니다. 모든 회차 미완료 필수 후속, 활성 배정·작업/lease, 재문의/현재 회차, ticket/followup 멱등 응답·승인·감사·정책 버전/JSON 참조를 보존 영향으로 보고합니다. B의 기존 queue/lease/generation/해결 gate 계약은 유지됩니다. AI/RAG의 draft·order_snapshot·gate/evidence JSON은 원문 중복 저장 가능 위치로 inventoried이며 개인정보 탐지 성공으로 표현하지 않습니다. 마스킹/참조/hold·승인 보관 정책은 공동 확정이 필요합니다. dry-run을 미래 삭제 예약이나 worker 실행 명령으로 사용하지 않습니다. 실제 B·AI/발송 엔진 통합은 여전히 미검증입니다.

## 0.6.1 공통 경계 수정

repository.agent_assignment_exists는 AGENT 티켓 권한과 exception-queue assigned 공통 정책입니다. 현재 배정 행만 남아 있어도 scope/category·팀·활성 상태·처리 stage가 맞지 않으면 처리 가능한 배정으로 판정하지 않습니다. B는 정규화 scope/category와 현재 회차 route를 계속 원자 관리하며 권한을 임의 복원하지 않습니다.

commit_automatic_reply는 ticket→job→control SHARE 뒤 최종 INSERT 직전 실제 utcnow로 lease를 다시 검사하고 그 시각으로 메시지/해결/job 갱신을 저장합니다. INVALID_LEASE면 최종 저장/성공/감사를 남기지 않습니다. control 대기 중 lease가 만료될 수 있으므로 최초 검사만으로 실행/발송을 승인하지 않습니다. 기존 generation/회차/version/token/owner fence와 외부 발송 직전 재검사 계약은 그대로이며 실제 worker·외부 발송 보장은 미검증입니다.

## 2026-11-03 Azure A 개발 DB 경계

A API/DB를 실제 배포했으나 B worker/배정·사람 확정 엔진은 연결하지 않았다. 전용 DB backend_a, head0006, PostgreSQL16, verify-full 필수이다. 네트워크는 현재 A 앱 IP만 허용하므로 B의 실행 위치/고정 연결 경로/전용 최소 DB identity를 별도 합의해야 한다. owner 자격이나 A API 로그인 JWT를 DB 권한으로 공유하지 않는다. 비밀값은 이 문서에 없다.

AUTO는 최초 PAUSED이며 worker를 가동하지 않았다. 기존 ticket→job→control SHARE, cycle/version/lease/generation, heartbeat·작업 시작/재시도/실제 발송 직전 재검사 계약이 그대로 필요하다. 테스트용 배정 시각은 개발 PC가 아닌 DB의 clock_timestamp를 사용해 시계 차이를 회피했다. lease 최종 판단은 transaction_timestamp가 아니라 모든 gate 뒤 실제 wall-clock이며 worker 시간 동기화도 확인해야 한다. HANDOFF/사람 업무는 유지한다. 중지된 작업을 성공으로 처리하거나 재개 권한을 임의 부여하지 않는다. 실제 외부 발송 중단 보장은 여전히 미검증이다. 상세는 azure-deployment.md.


## 2026-11-03 Azure 이름 이전 후 현재 환경

API base는 https://csflow-backend-a.azurewebsites.net/api/v1, PG는 csflow-backend-a-pg.postgres.database.azure.com/backend_a, Plan은csflow-backend-a-plan이다. source0.6.1/head0006과 기존 모든행/계정/권한·자동중지를 보존했다. 구3개 삭제·공용잠금 복원과 실제검증/백업은[azure-migration.md](azure-migration.md)를 따른다. B·AI·Fabric·발송은미연결/미검증이고 실제 Frontend origin은추측해등록하지 않았다. 서비스 인증 비밀값이나 DBpassword는이문서에없다.
