# 업무량 기반 배정 우선순위 추천 — 로컬 0.10.0 / 0010

품질 평가0.9.0은 먼저 `30fbfff047f1d316b73cb33b6cc2b0fb4fe167db`로 일반 push했고 원격 HEAD 일치를 확인했다. **이 문서의 추천 구현은 그 이후 개발해 이번 공유 대상으로 검토한 변경**이다. Azure 배포는 포함하지 않는다. 실제 assignment·ticket/job/route 변경·예약·lease·B 실행기·ML·스케줄러·Export/Fabric 조율은 추가하지 않았다.

## API·권한

`GET /api/v1/staff/assignment-recommendations`

- 활성 ADMIN + 명시 ASSIGNMENT_RECOMMEND + 현재 정규화된 활성 팀 scope. CUSTOMER/AGENT는 차단하며 AGENT에 잘못 grant해도 ADMIN 역할을 대신하지 못한다. WORKLOAD_READ를 자동 부여하거나 기존 workload API 권한을 바꾸지 않는다.
- `team_id`: 허용 route 팀 필터. 범위 밖/없는 팀 필터 모두403. 미지정은 현재 허용 활성 팀들만 사용한다.
- `ticket_id`: 현재 route 기준으로 접근 가능한 티켓1개의 참고 정보. 팀 필터와 함께 쓰면 그 팀 안에서만 찾는다. 없는/권한 밖은404. AUTO/종료/이미 배정/기타 상태는 권한 안에서만 명시적 불추천 사유로 응답한다.
- `limit`: 기본20, 최대50. `candidate_limit`: 기본3, 최대10. `cursor`: 최대512자. ticket_id와 cursor는 함께 쓰지 않는다.
- 미라우팅 전체 추천 페이지는 제공하지 않는다. 미라우팅/현재 회차 route 부재/비활성 route의 **티켓 지정 조회**는 추가 UNROUTED_QUEUE_READ가 있을 때만 허용하며 후보 없이 UNROUTED_NO_RECOMMENDATION을 반환한다. 팀을 추정하지 않는다. 비활성 route의 팀 ID도 응답에 노출하지 않는다. 다른 활성 팀을 이 권한으로 우회하지 못한다.
- 원문·고객/프로필·주문·직원 이름/이메일을 반환하지 않는다. 후보 ID/집계는 허용 route 팀에 한정한다. Cache-Control:no-store, 최소 성공/거부 감사만 저장한다.

```http
GET /api/v1/staff/assignment-recommendations?team_id=22222222-2222-4222-8222-222222222222&limit=20&candidate_limit=3
Authorization: Bearer <사용자 토큰>
```

티켓 지정 예: `GET /api/v1/staff/assignment-recommendations?ticket_id=11111111-1111-4111-8111-111111111111`.
UUID는 설명용이다. 실제 응답 ID를 사용하고 토큰을 문서/로그에 저장하지 않는다. [완전한 합성 응답 예시](examples/assignment-recommendations.json)는 실제 DTO로 검증한다.

응답 골격은 `as_of/expires_at/rule_version/team_ids/total/items/next_cursor`다. 각 item은 ticket_id/cycle_no/ticket_revision, route_revision/team/recorded_at, category, due_at/deadline_state, waiting_since/basis, recommendation_state/reason_codes, invalid_active_assignment_present, eligible_candidate_count/candidates_truncated/candidates를 제공한다. 후보는 agent_id/team_id/rank, tickets 및 followups 집계와 reason_codes다. total은 선택 팀의 구조상 대상 HUMAN 대기 업무 수(티켓 지정 시1)이며 실제 배정 가능한 건수/후보 수를 뜻하지 않는다. 분류 부족·조건부 항목도 포함될 수 있다.

## 대상과 정렬

현재 코드의 확실한 배정 대기는 **requested_mode=HUMAN, status=HANDOFF_PENDING, resolution_mode=NULL, 현재 유효한 상담사 배정 없음**이다. current cycle의 활성 명시 route가 허용 팀에 있어야 목록 대상이다. A의 현재 HANDOFF claim/handling_path 상태와 맞춘 최소 기준이다.

현재 cycle의 AUTO Job이 FAILED인 HUMAN/HANDOFF_PENDING도 대상이다. reason=FAILED_AUTO_HISTORY_PRESERVED이며 job 종류·상태·expected version을 고치거나 재활성화하지 않는다. 이 조회는 그 상태를 만드는 HUMAN 전환/실제 배정 writer를 구현한 것이 아니다. AUTO 처리 중·FAILED/PAUSED/RETRY만으로 사람 대기로 바꾸지 않는다. HUMAN ASSIGNED/IN_PROGRESS 등의 무효 배정은 자동으로 HANDOFF_PENDING으로 해석하지 않고 STATE_NOT_ASSIGNABLE로 안내한다.

기존 `repository.agent_assignment_exists(as_of=...)`를 그대로 재사용해 종료/이전 회차/무효 배정을 유효 배정으로 세지 않는다. **물리적 ended_at=NULL 행은 별도 문제**다. 현재/이전 회차의 이 행이 남아 있으면 PHYSICAL_ASSIGNMENT_RECONCILIATION_REQUIRED와 CONDITIONAL을 표시한다. 후보는 참고로 제공하되 기존 uq_assignments_current 때문에 B가 새 배정 전에 명시적으로 정리/재검증해야 한다. A 조회가 행을 종료하지 않는다. 유효 배정된 FAILED 문의는 새 후보 대상으로 중복 표시하지 않는다.

업무 순서는:

1. 저장 due_at < as_of: overdue.
2. as_of <= due_at <= as_of+2시간: due_soon. 정확한 마감/2시간 경계 포함.
3. 이후 on_time 및 NULL no_due_date.
4. 같은 그룹에서 due_at ASC(NULL 마지막) → 확인 가능한 사람 대기 시작시각 → ticket_id ASC.

**현재는 사람 대기 시작시각을 입증하는 저장 이력이 없다.** waiting_since는 항상NULL/NOT_RECORDED_NOT_INFERRED, 이유는 WAITING_START_UNRECORDED다. 동일 기한이면 ID로 정렬한다. route_recorded_at은 마지막 route 기록 시각일 뿐 AUTO 때 기록됐거나 같은 팀 route 갱신일 수도 있다. 이를 사람 대기 시작·최초 접수·SLA 시작으로 사용하지 않는다. queue의 queued_at/job.created_at/ticket.created_at이나 감사 문구로 채우지 않는다. 향후 명시 이력이 생기면 규칙 버전을 새로 정의한다.

기한은 기존 저장된24시간 연속 기한의 상태다. 정식 SLA 준수율/과거 성과가 아니며 기한을 재계산·갱신하지 않는다. 현재 DB의 sla_due_at은 NOT NULL이다. NULL 분기는 과거/확장 자료를 위한 방어 동작이며 DB 제약을 변경하지 않았다.

## 후보·업무량

`repository.agent_eligibility(agent_table, team_id_expression, category_expression=None)`는 **배정이 없어도** 적용할 수 있는 공통 자격 SQL 술어다. 활성 AGENT, 소속 팀=route 팀, 활성 팀, 정규화된 agent 팀 grant, 팀의 category 지원을 확인한다. 기존 배정 유효성 함수도 이 자격을 재사용한다. 후보에게 일반 ticket_scope가 없다는 이유로 제외하지 않는다.

UNCLASSIFIED/알 수 없는 category는 CATEGORY_UNKNOWN, route 팀이 지원하지 않는 category는 ROUTE_CATEGORY_UNSUPPORTED, 나머지 적격 직원 부재는 NO_ELIGIBLE_AGENT다. 원문으로 category를 추측하지 않는다. 직원별 숙련도 대신 **현재 팀 category 계약**만 확인한다. 미추천 사유에 범위 밖 직원/팀의 ID·존재·건수를 끼워 넣지 않는다.

후보 정렬은 현재 유효한 distinct(ticket_id,cycle_no) 문의 수 ASC → 그중 overdue 문의 수 ASC → user_id ASC다. 동일 snapshot/as_of에서 `workload.ticket_facts`와 기존 `ticket_counts`/`followup_counts`를 재사용한다. WAITING_CUSTOMER는 유효 업무량에 포함하고 별도 필드로 표시한다. 후속 OPEN/IN_PROGRESS는 유효 인수/담당만 별도 집계하며 문의 수에 더하거나 가중치로 쓰지 않는다. 종료/이전 회차/비활성·scope 회수·업무 유형 불일치 배정은 현재 업무량에서 제외한다.

원천 없는 출근·휴가·온라인·개인 용량·개인 숙련도는 고려하지 않았다. reason_codes는 실제 자격과 정렬 기준을 설명하며 임의 최적화 점수가 아니다. 고정 UUID 동률 정렬은 반복적으로 같은 직원을 우선할 수 있다. 공정성 순환/최근 배정 이력을 구현했다고 표현하지 않는다.

**업무마다 독립적인 현재 부하 힌트**이므로 여러 문의의 첫 후보가 같을 수 있다. 페이지 안에서 부하를 가상 증가시키거나 예약하지 않는다. 자동화 PAUSED 여부로 추천을 실행 허가로 바꾸지 않는다. B의 자동/수동 실행 중지 정책은 별도 책임이다.

## 일관성·페이지·오류

인증·scope·목록/total·후보·문의/후속 집계는 기존 SnapshotDB/SnapshotUser의 한 PostgreSQL REPEATABLE READ와 서버 transaction_timestamp 기반 as_of를 사용한다. 내부 함수도 이 snapshot을 요구한다. expires_at=as_of+30초, rule_version=WORKLOAD_PRIORITY_V1이다. 유효시각은 신선도 표시이며 lease·예약·배정 권한이 아니다. 오래 걸린 응답이 이미 만료됐으면 새로 조회한다.

기한/ID keyset cursor는 사용자·선택 팀·규칙·필터에 묶는다. 기한 버킷은 기한 오름차순과 일관되므로 시간 경계 이동만으로 정렬이 뒤집히지 않는다. 각 페이지는 새로운 현재 snapshot이며 전체 페이지에 고정 DB snapshot을 보존하지 않는다. 업무 기한/route/대상이 바뀌면 재조회한다. 필터/candidate_limit 변경 시 cursor를 버린다. 변경 중인 데이터의 페이지 간 중복/누락이 없다고 보장하지 않는다.

후보 순위는 SQL window partition, 부하는 set-based facts/집계다. 페이지/후보 수만큼 개별 조회하지 않는다. 기존 route PK(ticket,cycle), ticket PK, normalized scope/category PK, assignments agent index와 현재 assignment partial UNIQUE를 사용하며 인덱스를 추가하지 않았다. 실제 운영 규모의 성능 보장은 이번 검증이 아니다.

403 EXPLICIT_PERMISSION_REQUIRED / RECOMMENDATION_TEAM_SCOPE_DENIED, 404 RESOURCE_NOT_FOUND, 422 RECOMMENDATION_FILTER_INVALID / INVALID_CURSOR, 503 RECOMMENDATION_SNAPSHOT_REQUIRED / DATABASE_UNAVAILABLE를 사용한다. 입력·원문·토큰을 오류에 반사하지 않는다.

## Frontend와 B 경계

Frontend는 `/staff/capabilities`에서 ASSIGNMENT_RECOMMEND를 확인하고 팀 목록/티켓 지정 GET을 연결한다. total과 표시 항목 수, 후보 total과 후보 페이지 제한을 구분한다. AVAILABLE/CONDITIONAL/UNAVAILABLE·이유·기한 상태·as_of/만료·문의/WAITING_CUSTOMER/후속을 따로 표시한다. 이 API로 실행하는 배정 버튼/POST는 없다.

B는 선택한 힌트를 사용하기 직전 **현재** cycle/ticket version/route revision·팀과 category, 직원 역할/활성/소속 팀·정규화 scope·지원 유형, 현재 유효/물리 배정과 부하를 다시 읽어야 한다. ticket→job→실제 배정 경계의 잠금·lease/generation/PAUSED·CAS·멱등 계약을 B의 실행 경로에서 적용한다. FAILED AUTO를 HUMAN으로 바꾸거나 그 FAILED를 실행용으로 되살리지 않는다. 유효기간 안이어도 최신 상태가 달라지면 거부/재추천해야 한다.

동일 티켓 중복 방지나 서로 다른 티켓의 동시 부하 균형은 이 조회만으로 보장하지 않는다. 팀 잠금/용량 실행기·새 서비스 HTTP는 만들지 않았다. 기존 B 실제 배정 엔진과의 통합도 미검증이다.

실제 import는 `app.recommendations.view(session, user, *, team_id=None, ticket_id=None, limit=20, candidate_limit=3, cursor=None)`다. HTTP가 아니다. caller가 실제 인증된 ADMIN identity를 확정하고, 첫 인증 SELECT **전** REPEATABLE READ 및 서버 snapshot_as_of를 설정해야 한다. 함수가 DB 사용자 활성·ADMIN/capability·scope를 다시 확인하며 caller가 최소 감사 commit을 담당한다. B 서비스 자격을 가짜 ADMIN dict로 바꾸는 우회 경계가 아니다. 서비스 identity만 가진 B를 위한 별도 인증 계약은 이번에 없다. `agent_eligibility`/`workload.ticket_facts(roster,as_of)`는 순수 SQL 재사용이며 caller의 권한 검사나 B 실행 guard를 대신하지 않는다.

0010은 permission CHECK/allowlist 추가뿐이다. 새 테이블·추천 저장·grant는 없다. readiness0010/source0.10.0을 요구한다. 기존0001–0009와 업무/grant를 보존하며 추천 grant/조회 감사가 있으면 downgrade를 거부한다. 실제 권한 부여·Azure 적용은 하지 않았다. [로컬 검증 기록](evidence/recommendation-local/README.md)을 참고한다.
