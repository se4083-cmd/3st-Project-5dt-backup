# 현재 상담사 업무량 조회 — 0.7.1 / migration 0007

`GET /api/v1/staff/workload`는 현재 유효한 문의 배정과 열린 후속의 업무량을 반환한다. 서버가 정한 단일 `as_of`와 PostgreSQL REPEATABLE READ snapshot에서 인증·scope·직원 목록·카운트를 계산한다. 과거 조회나 정식 SLA 준수율이 아니며 배정·추천·새 SLA 정책을 실행하지 않는다. 상담 원문·고객·주문·티켓 ID·직원 이름/로그인은 반환하지 않는다.

0.7.1은 0.7.0의 `unassigned` 집합·필드를 유지하면서 처리 경로별 분류만 추가한다. 이 합계의 화면 이름은 **‘유효 상담사 배정 없음’**이다. 자동 경로도 포함하므로 전체를 ‘상담사 배정 대기’라고 표시하지 않는다. DB 변경이 없어 migration은0007 그대로다.

## 권한과 요청

| 역할 | 조건·반환 범위 |
|---|---|
| CUSTOMER | 403 STAFF_ROLE_REQUIRED |
| AGENT | 별도 WORKLOAD_READ grant 없이 본인만. 현재 본인 소속의 활성 팀 및 normalized scope 안에서 조회. team_queue/unrouted는 null. 자기 ID만 agent_id로 선택 가능 |
| ADMIN | 명시적 WORKLOAD_READ + 현재 활성 user_team_scopes. 기본은 허용 팀 전체, team_id로 한 팀 선택 가능. 다른 팀 fallback 없음 |
| 미라우팅 포함 | ADMIN + WORKLOAD_READ + 기존 UNROUTED_QUEUE_READ. include_unrouted=true일 때 별도 전역 미라우팅 집계만 반환 |

`GET /staff/capabilities`는 ADMIN에게 실제 부여된 WORKLOAD_READ만 표시한다. AGENT에게 잘못 부여해도 이 capability로 타인/팀 조회를 할 수 없고 allowlist에도 노출하지 않는다. Frontend는 `/auth/me`의 역할로 AGENT 자기 보기를 열고, ADMIN 팀 보기는 capabilities의 WORKLOAD_READ를 확인한다. capability는 서버가 매 요청 재검사한다.

```http
GET /api/v1/staff/workload
Authorization: Bearer <user-access-token>
```

```http
GET /api/v1/staff/workload?team_id=<allowed-team-uuid>&limit=20
GET /api/v1/staff/workload?agent_id=<visible-agent-uuid>&limit=20
GET /api/v1/staff/workload?include_unrouted=true&limit=20
GET /api/v1/staff/workload?limit=20&cursor=<opaque-next-cursor>
```

| query | 기본/제약 | 의미 |
|---|---|---|
| team_id | UUID, 생략 가능 | ADMIN 허용 활성 팀 중 하나. AGENT는 본인 활성 scope·소속 팀만. 없는/권한 밖 팀 모두 동일403 |
| agent_id | UUID, 생략 가능 | **직원 목록에만** 적용. ADMIN의 선택 팀 안의 활성·scope 있는 AGENT, 없는/권한 밖 모두 동일404. AGENT의 타인 지정은 존재 여부와 무관하게403 |
| include_unrouted | false | 추가 권한이 있으면 전역 미라우팅 건수를 별도 반환. team_id/agent_id로 귀속시키지 않음 |
| limit | 20, 1–100 | 상담사 목록 페이지 크기 |
| cursor | 최대512자 | agent_id UUID ASC keyset. 사용자/역할/현재 팀 집합/agent 필터/미라우팅 선택에 묶임. 변경된 범위·변조된 구조는422 |

as_of 입력은 제공하지 않는다. 요청마다 서버 시각을 새로 정하며 모르는 as_of query로 과거 조회를 할 수 없다. 다음 페이지도 새 snapshot이다. cursor는 과거 상태를 고정하지 않으며 실시간 데이터 변동으로 이전 페이지와 합계가 달라질 수 있다. 화면의 총합은 해당 응답의 scope_totals를 사용하고 페이지들을 더해 총합을 만들지 않는다. scope/필터 변경 시 cursor를 버린다.

## 응답 읽는 법

기계 판독 전체 예시는 [workload-response.json](examples/workload-response.json), 스키마는 [OpenAPI](openapi.json)의 WorkloadPage다. 예시는 합성 값이며 실제 서버 상태가 아니다.

| 필드 | 의미 |
|---|---|
| as_of | 응답 전체의 서버 기준 UTC 시각. snapshot 인증 이전에 고정 |
| view/team_ids/agent_filter | SELF 또는 TEAM, 현재 선택된 활성 허용 팀 UUID, 목록 필터. 비활성/권한 밖 팀 ID는 반환하지 않음 |
| total_agents | 선택 scope의 활성·소속팀 scope 유효 AGENT 수. AGENT는 본인만 최대1 |
| matching_agents | agent_id 필터 적용 후 전체 직원 수. cursor/limit 적용 전 |
| items | 현재 페이지 상담사의 agent_id/team_id/tickets/followups만. 업무 0건인 유효 상담사도 표시 |
| scope_totals | 선택된 팀 전체 유효 AGENT의 tickets/followups. **agent_id·cursor·limit에 영향받지 않음**. SELF는 본인만 |
| page_totals | 현재 items의 tickets/followups 합계. team_queue/unrouted는 포함하지 않음 |
| team_queue | ADMIN만. unassigned, waiting_followups, admin_owned_followups를 각각 분리. agent_id·페이지와 무관한 선택 팀 전체 |
| unrouted | 요청+권한이 있을 때만 전역 미라우팅 UnassignedCounts. 아니면 null이며 숨겨진 건수를 0으로 표현하지 않음 |
| next_cursor | 다음 직원 페이지 또는 null |
| deadline_basis | STORED_DEADLINES_NOT_SLA_COMPLIANCE |
| ticket_deadline_policy/due_soon_seconds | LEGACY_24H_CONTINUOUS / 7200. 저장된 기한의 상태만 조회 |

TicketCounts는 `{total,overdue,due_soon,on_time,no_due_date,waiting_customer,by_category}`다. DeadlineCounts는 앞의 5개 기한 카운트만 가진다. UnassignedCounts는 TicketCounts에 `invalid_assignment_count`, `by_handling_path`를 추가한다. 각 집합에서 `overdue + due_soon + on_time + no_due_date = total`, `sum(by_category.values()) = total`, `sum(by_handling_path.values()) = total`이다. waiting_customer와 invalid_assignment_count는 부분집합이므로 total에 다시 더하지 않는다. 빈 집합은 total=0, by_category={}, 경로별 세 값은 모두0, 목록=[]다.

## 집계 규칙

### 문의

기존 `repository.agent_assignment_exists`를 재사용하며 이 조회만 동일 as_of를 주입한다. 현재 cycle·티켓팀/직원팀 일치·활성 AGENT/팀·정규화 scope·지원 category·미종료 배정·assigned_at<=as_of를 검사한다. 상태는 ASSIGNED/IN_PROGRESS/FOLLOWUP_PENDING/WAITING_CUSTOMER다. 종료/이전 회차 배정은 개인 업무량에서 제외한다. distinct(ticket_id,cycle_no)를 집계하므로 과거 배정 행 수·메시지·재시도는 문의 수를 늘리지 않는다.

by_category는 ACCOUNT/DELIVERY/PAYMENT/PRODUCT/REFUND/RETURN/FAQ/UNCLASSIFIED 중 정확히 하나다. 알 수 없는 DB category는 원문을 반사하지 않고 UNCLASSIFIED에 한 번 센다. WAITING_CUSTOMER는 전체에 포함하면서 waiting_customer에도 표시한다.

### 미배정·무효 배정

활성(RESOLVED/CANCELLED 제외)인데 현재 유효 배정이 없으면 미배정이다. job FAILED 여부로 미배정을 판정하지 않는다. FAILED여도 유효 배정이 있으면 제외한다. `invalid_assignment_count`는 이 미배정 집합 중 **ended_at=NULL인 물리 배정이 남아 있는 문의** 수다. 과거의 종료된 배정만 있는 문의는 이 부분집합에 넣지 않는다. 이전 cycle의 미종료 배정이 남아 있으면 무효 배정으로 센다.

따라서 자동 처리 대기·진행 경로, 실제 사람 배정 대기, 실패·재시도·PAUSED 상태의 자동 경로, 이전 cycle/무효 배정만 남은 활성 문의가 포함될 수 있다. 유효 배정 판단·route 권한은 아래와 같이 먼저 적용한다. 중지 상태 자체가 문의의 처리 경로나 사람 이관을 바꾸지는 않는다.

| by_handling_path | 현재 티켓의 정형 근거 | 권장 표시명 |
|---|---|---|
| automatic_path | requested_mode=AUTO, resolution_mode=NULL, status=OPEN/PROCESSING/WAITING_CUSTOMER | 자동 처리 경로 |
| human_assignment_waiting | requested_mode=HUMAN, resolution_mode=NULL, status=HANDOFF_PENDING | 사람 배정 대기 |
| unknown | 위 둘 외의 나머지. 예: 유효 배정 없는 HUMAN IN_PROGRESS, AUTO HANDOFF_PENDING, 활성인데 resolution_mode가 남은 경우 | 기타·판별 불가 |

세 분류는 상호 배타적이고 팀 미배정과 전역 미라우팅에 동일하게 적용한다. **현재 티켓이 선언한 경로**이며 job 실행 가능/실제 AI 실행 중/외부 발송 중이라는 의미가 아니다. 분류에 job 상태·lease·error/reason 문구·과거 기록·PAUSED를 사용하지 않는다. 이 때문에 job이 없거나 FAILED/RETRY/RUNNING이어도 현재 mode·상태가 명확하면 해당 선언 경로로 센다. HUMAN HANDOFF_PENDING도 그 상태로 선언된 대기라는 뜻이며 배정 worker 실행 가능성은 별도다. 원인 불명 무효 배정을 임의로 사람 대기 상태로 바꾸지 않는다.

코드 근거: `services.submit_ticket`는 AUTO/OPEN으로 접수하고, `ticket_commands.change_cycle`는 사람 요청 또는 사람 경로 재문의에서 현재 cycle을 올려 HUMAN/HANDOFF_PENDING과 HANDOFF job을 함께 만든다. `jobs.claim_jobs`는 AUTO와 HANDOFF를 구분하고 AUTO PAUSED이면 claim하지 않는다. 이 작업에서 해당 생성/전이/배정 코드를 바꾸지 않았다. 향후 ‘재배정 필요’나 ‘실제 실행 중’을 구분하려면 B가 현재 회차의 명시적 상태·일관된 job/lease·실행 사건을 제공하는 별도 계약이 필요하다.

미배정의 팀 귀속은 현재 cycle의 queue_routes에서 판단한다. 활성 route 팀이 선택 팀에 있을 때만 team_queue.unassigned에 센다. ticket.team_id·과거 배정·category로 route를 추정하지 않는다. route 없음/null/비활성 팀은 기존 예외 큐와 같이 미라우팅으로 분류하며 include_unrouted=true 및 전용 권한이 있어야 별도 전역 집계를 반환한다. 그 전역 값은 선택 팀 합계에 더하지 않는다.

### 기한

- `due_at < as_of`: overdue.
- `as_of <= due_at <= as_of + 2시간`: due_soon. 정확한 마감과 정확히 2시간 경계 포함.
- 그 이후: on_time. NULL: no_due_date.

문의는 저장된 sla_due_at, 후속은 저장된 due_at을 사용하고 재계산/갱신하지 않는다. 현재 tickets.sla_due_at은 DB NOT NULL이므로 정상 데이터의 문의 no_due_date는0이다. 공통 SQL 분류기는 NULL도 지원하며 선택 기한인 followup에는 실제로 사용할 수 있다. 이 구현 때문에 기존 NOT NULL 제약을 완화하지 않는다. 레거시 기한의 현재 상태이며 ‘정식 SLA 위반률’, 과거 처리 성과, 영업일/휴일 정책으로 표현하지 않는다.

### 후속

OPEN/IN_PROGRESS만 대상이다. 기존 followups.owner_valid와 같은 SQL 술어를 공유해 활성 소유자·활성 책임팀·현재 normalized scope를 검사한다. AGENT 소유는 해당 티켓의 유효한 현재 배정/팀/category가 있어야 하고 상품 후속의 AGENT 소유는 유효하지 않다. ADMIN 소유는 기존 정책처럼 해당 팀 scope를 요구한다. 티켓 후속은 responsibility_cycle_no가 현재 티켓 회차와 같아야 개인 업무에 포함한다.

유효한 AGENT 담당 후속은 items/scope_totals/page_totals.followups, 유효한 ADMIN 담당 후속은 ADMIN 팀 보기에만 team_queue.admin_owned_followups, 미지정/비활성/무효/미인수 담당은 team_queue.waiting_followups다. 책임팀이 현재 선택 scope 밖이면 그 건수도 노출하지 않는다. 일반 AGENT에게 팀 대기/타인 후속 수는 반환하지 않는다. 문의 수와 후속 수는 합산하지 않는다.

## 구현·운영 경계

업무량은0.7.0에서 도입했고, 현재 로컬 버전은0.7.1/head0007이다. [0007](../migrations/versions/0007_workload_read_permission.py)은 staff_permissions CHECK에 WORKLOAD_READ만 추가하고 grant·업무 테이블·기한·인덱스를 바꾸지 않는다. 이번 의미 보완으로 migration을 추가하지 않았다. 기존0001–0006은 그대로다. 권한 또는 READ_WORKLOAD 감사 이력이 있으면 downgrade를 거부한다. readiness는0007을 요구한다. 실제 운영 migration/ADMIN 권한 부여는 별도 작업이며 이번에는 수행하지 않았다.

기존 uq_assignments_current/ix_assignments_agent, 티켓 팀/후속 팀·티켓 인덱스를 우선 사용한다. 직원 페이지와 SQL 집계 쿼리 수는 페이지 크기에 비례하지 않는다. 페이지 밖 직원은 NULL bucket으로 집약해 결과 행 수도 제한한다. 조회 성공은 원문 없는 READ_WORKLOAD 감사와 함께 완료되며 감사 실패 시 응답도 실패한다. API의 no-store/RBAC/오류 envelope를 유지한다. 일반 필터 권한 오류는403, ADMIN 직원의 없음/범위 밖은 동일404, UUID/limit/cursor 오류는422다.

이 소스 변경은 Azure에 배포하지 않았다. Azure의 기존 0.6.1/0006 배포와 배포 도구의 고정 기록은 바꾸지 않았다. 기존 Azure 이전/배포 도구는 새0.7.x를 위한 배포 도구로 검증하지 않았으므로 이 변경을 자동 배포하는 용도로 사용하지 않는다. B의 배정·lease/generation·공용 업무 DB 계약도 바꾸지 않았다. 검증 범위는 [로컬 검증 기록](evidence/workload-local/README.md)을 따른다.

0.7.1의 이번 실행 결과와 공유 전 검토는 [미배정 의미 보완 검증](evidence/unassigned-paths-local/README.md)을 따른다. 위0.7.0 검증 건수는 이번 실행 수치에 합산하지 않는다. Azure 현재 버전은 재조회하지 않았다.
