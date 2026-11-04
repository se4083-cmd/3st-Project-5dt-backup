# AUTO 최종 실패 → 사람 이관·배정 계약 검토

2026-11-04 KST 작성. **소스 검토 결과와 미구현 보완 제안**이다. 기존 [B 계약](backend-b-contract.md)·[B 인수](backend-b-handoff.md)를 대체하지 않는다. FAILED를 보존하는 방향과 필요한 필드 변경·공통 writer 구현은 별개의 계약이다. 이 검토는 아래 고정 소스 확인에 한정되며 앱·migration·DB·Azure·B 실행 경계를 변경하지 않았다.

## 1. 기준점·확인 범위

| 항목 | 확인 결과 |
|---|---|
| 실제 저장소/담당 폴더 | 팀 체크아웃의 `backend/backend-a/` |
| 브랜치/로컬 HEAD | `feature/backend-a` / `25e4aad720198ea2a3a0287ccf6f58f69c92d228` |
| 시작 Git 상태 | clean. 기존 파일을 변경하지 않고 새 검토 문서만 추가 |
| A 버전 | pyproject.toml 및 app/main.py: **0.7.1** |
| migration graph | 파일 AST 확인: base→0001→0002→0003→0004→0005→0006→**0007**, 단일 head. 실제 DB 적용 revision 조회 아님 |
| AGENTS.md | 담당 하위 경로와 저장소·프로젝트를 포함한 부모 경로에서 발견되지 않음 |
| A 원격 HEAD | 이번 읽기 조회에서 `25e4aad720198ea2a3a0287ccf6f58f69c92d228`로 로컬과 일치 |
| B 원격 HEAD/공유 기준 | `feature/backend-b`의 HEAD가 **d7a8dbd796dd554be0b4397bf9cc874093b88040**. 요청한 d7a8dbd와 같은 커밋 |
| B 검토 경로 | 해당 SHA의 `backend/app/automation/` Python 11파일 및 backend/README.md. 별도 ignored 사본으로 읽었고 A 체크아웃/브랜치를 바꾸지 않음 |
| GitHub 인증 작업 | 앞선 일반 push는 완료된 상태. 연결 앱 조회는 접근 오류였으나, 이미 복구된 실제 Git HTTPS 인증으로 원격 읽기는 성공. 이번에 인증 설정·커밋·push를 변경하지 않음 |
| 실행하지 않은 것 | pytest·업무 HTTP·B Worker·PostgreSQL·SQLite·Azure·Fabric. 아래 동작 판단은 코드/제약식 검토이며 새 실행 PASS가 아님 |

확인한 B 파일: automation_gate.py, dev_server.py, job_complete.py, job_create.py, job_fail.py, job_lease.py, job_recovery.py, job_store.py, mock_context.py, mock_jobs.py, worker.py. 자료에 없는 B 미커밋 PG 전환 코드는 확인하지 못했다. 따라서 **현재 B 실행 엔진과 A의 통합 호환성을 확정하지 않는다.**

## 2. 질문 1·2·3의 결론

| 질문 | 판정 | 현재 확정할 수 있는 것 / 부족한 것 |
|---|---|---|
| 1. AUTO Job을 FAILED로 보존하고 같은 회차 HUMAN으로 전환해도 되는가? | **코드 보완 필요** | DB 제약상 가능한 row 조합이고 FAILED 보존 방향은 타당하다. 그러나 실패 확정+같은 회차 HUMAN 전환을 안전하게 수행하는 A 공통 함수는 **현재 미구현**이다. raw SQL로 가능하다는 사실을 지원되는 명령으로 해석하지 않는다 |
| 2. requested_mode/status/version의 정확한 변경 규칙은? | **코드 보완 필요** | 기존 고객 명령은 cycle+1/version+1이다. 같은 회차 엔진 이관의 확정 규칙은 없다. 이 문서는 HUMAN/HANDOFF_PENDING/cycle 유지/version+1을 최소 **제안**하며 실제 호출 계약으로 확정하지 않는다 |
| 3. HANDOFF Job 없이 AUTO_FAILED 큐에서 실제 배정까지 할 수 있는가? | **코드 보완 필요** | FAILED AUTO의 큐 조회는 현재 지원(팀 route·권한 조건부). 하지만 큐는 배정 실행기/작업 예약기가 아니다. FAILED는 AUTO/HANDOFF claim 모두 불가하고, 이 경로의 배정 writer/예약·멱등 계약이 없다 |

요약하면 **‘같은 회차에 AUTO Job 1개를 FAILED로 남긴다’는 DB 구조를 유지하는 설계는 가능하지만, A가 이미 그 실패→HUMAN→배정 흐름을 제공하는 상태는 아니다.** 유효 배정을 마친 HUMAN 티켓은 기존 사람 해결 gate와 구조적으로 호환될 수 있다. 그 상태를 만드는 원자 writer와 회귀 검증이 먼저 필요하다.

### 근거가 되는 A 파일

- [models.py](../app/models.py): tickets, automation_jobs, assignments, audit_events.
- [model_constraints.py](../app/model_constraints.py): `uq_automation_jobs_ticket_id_cycle_no`, `ck_automation_jobs_state/kind/handoff_request/lease/counters`, `uq_assignments_current`, `uq_messages_final_cycle`.
- [jobs.py:claim_jobs](../app/jobs.py#L14), [finalization.py:commit_automatic_reply](../app/finalization.py#L28).
- [ticket_commands.py:change_cycle](../app/ticket_commands.py#L44), [exception_queue.py:queue_query](../app/exception_queue.py#L111), [record_queue_route](../app/exception_queue.py#L61).
- [repository.py:agent_assignment_exists](../app/repository.py#L31), [resolution.py:lock_resolution_gate](../app/resolution.py#L33), [automation_control.py](../app/automation_control.py).
- 원래 DDL은 migration0001, job kind/source/reason은0002, generation/control은0005. 0007은 WORKLOAD_READ 허용값 추가뿐이며 실패/배정 계약을 추가하지 않는다.

## 3. 최종 실패·재시도의 현재 구현

### 3.1 A에서 이미 있는 것

`claim_jobs(session, worker_id, *, limit=10, lease_seconds=60, job_kind="AUTO")`는 PostgreSQL 전용이다. caller가 transaction을 열고, ticket→job 순서로 잠근다. 현재 ticket/job cycle과 expected_ticket_version 일치, next_attempt_at 경과, 허용 mode/status, 작업 종류를 검사한다.

- AUTO: requested_mode=AUTO, status=OPEN/PROCESSING. HANDOFF: HUMAN/HANDOFF_PENDING.
- 대상 job: PENDING/RETRY, 또는 회수 가능한 RUNNING(lease 만료; AUTO는 이전 generation도 회수 대상).
- claim마다 attempt를 **+1**하고 새 token/owner/until을 기록한다. 실패 보고가 attempt를 올리는 구조가 아니다.
- AUTO PAUSED면 빈 목록, 상태 부재/조회 실패는 허용으로 바꾸지 않는다. AUTO의 control SHARE/generation 검사는 기존 helper를 따른다. HANDOFF claim은 AUTO control을 읽지 않는다.
- caller는 claim transaction을 commit한 다음 AI/외부 HTTP를 실행한다.
- **attempt<3 조건은 없다.** attempt>=0 DB CHECK도 상한을 강제하지 않는다. lease 회수·stop/resume 뒤 재claim도 attempt를 올리므로 attempt는 ‘AI가 실제로 실패한 횟수’와 같지 않을 수 있다.

**A에는 retry/fail/heartbeat/최대 횟수 소진/최종 실패 원자 확정 함수가 없다.** `commit_automatic_reply`는 성공 응답 확정이며 message final OUT, RESOLVED/AUTO, job SUCCEEDED를 저장한다. 실패를 기록하려고 이 함수를 호출하면 안 된다. `fenced_job_predicate`는 job 쪽 일부 조건일 뿐 ticket mutex·worker·종류·control/generation 검사를 대체하지 못한다.

FAILED는 기존 claim 대상이 아니고, resume도 FAILED를 PENDING으로 바꾸지 않는다. lease 3종이 NULL이어야 하는 CHECK와 별개로, **DB가 FAILED를 영구 불변 상태로 만드는 trigger는 없다.** 임의 SQL로 되살리지 않는 writer 계약이 필요하다. next_attempt_at은 NOT NULL이지만, FAILED에서는 그 시각이 지나도 claim되지 않는다.

### 3.2 B d7a8dbd에서 실제 확인한 것

다음 링크는 읽은 정확한 커밋의 소스다. B의 개발용 HTTP이며 A endpoint가 아니다.

| B 파일·함수 | 현재 소스 동작 | A 연동 차이 |
|---|---|---|
| [job_store.py](https://github.com/InSSOOO/cs-flow-ai/blob/d7a8dbd796dd554be0b4397bf9cc874093b88040/backend/app/automation/job_store.py) `get_connection/init_db` | 별도 로컬 SQLite. jobs/audit 생성 | job_kind, lease_owner, expected_ticket_version, automation_generation 없음. A ticket FK/권한·generation 관계가 없음 |
| [job_lease.py:claim_job](https://github.com/InSSOOO/cs-flow-ai/blob/d7a8dbd796dd554be0b4397bf9cc874093b88040/backend/app/automation/job_lease.py#L19) | PENDING/시각경과/attempt<3만, RUNNING 전환·attempt+1·300초 lease | ticket cycle/version/mode·worker owner·전역 중지 검사 없음. A 공통 claim으로 단순 교체하면 3회 상한이 자동 유지되지 않음 |
| [job_fail.py:fail_job](https://github.com/InSSOOO/cs-flow-ai/blob/d7a8dbd796dd554be0b4397bf9cc874093b88040/backend/app/automation/job_fail.py#L26) | FailJobRequest(lease_token,error_code,retryable). RUNNING/token/lease 검사. retryable이고 attempt<3이면 **PENDING**, 30×2^(attempt−1)초 후 재시도. 나머지는 **HANDED_OFF** | **현재 FAILED를 저장하지 않는다.** 사용자 설명의 FAILED 방향은 이 커밋에 아직 반영되지 않은 계획으로 구분 |
| [job_recovery.py:recover_expired_jobs](https://github.com/InSSOOO/cs-flow-ai/blob/d7a8dbd796dd554be0b4397bf9cc874093b88040/backend/app/automation/job_recovery.py#L19) | 만료 RUNNING을 attempt<3이면 PENDING, 아니면 HANDED_OFF. token/until 제거·감사 | ticket/generation/PAUSED 없음. 현재 SQLite 논리를 공유 PG에 그대로 실행하면 안 됨 |
| [job_complete.py:complete_job](https://github.com/InSSOOO/cs-flow-ai/blob/d7a8dbd796dd554be0b4397bf9cc874093b88040/backend/app/automation/job_complete.py#L22) | job SUCCEEDED+감사 | A의 message/ticket/job 원자 성공 확정이 아님. A 공통 성공 함수로 통합 필요 |
| [worker.py:run_once](https://github.com/InSSOOO/cs-flow-ai/blob/d7a8dbd796dd554be0b4397bf9cc874093b88040/backend/app/automation/worker.py#L8) | 만료 복구, PENDING·attempt<3 후보, fixture gate 조회/로그 | 이 경로에 실제 상담사 선정/배정 writer나 A 공통 함수 호출 없음 |

B fail/recovery는 자체 connection의 `BEGIN IMMEDIATE`와 context manager가 transaction/commit을 소유한다. A SQLAlchemy session의 caller-owned transaction에 바로 합칠 수 없다. fail의 now는 잠금 획득 **전**에 만들고 TEXT ISO 시각을 비교하며, 모든 대기 후 실제 wall-clock 재검사는 없다. PG 전환 시 native aware timestamp·ticket→job 잠금·최종 쓰기 직전 lease 재검사로 바꿔야 한다.

B fail은 감사 event_key를 `automation_job:{job_id}:attempt:{attempt}:failed`로 만들지만, 재요청은 이미 RUNNING이 아니므로409다. UNIQUE event_key만으로 ‘동일 요청이면 원래 성공 receipt 반환’이 구현된 것은 아니다. recovery도 event_key가 있으나 A 회차/버전 fence의 대체가 아니다. B dev_server의 조회/갱신은 개발 fixture/SQLite 맥락이고 공유 DB 서비스 인증이 연결됐다고 볼 수 없다.

**MAX_ATTEMPTS=3은 B 정책**이다. retryable=false면 3회 전에도 현재 B는 HANDED_OFF로 종결한다. 사용자 방향대로 FAILED를 쓰면 A AUTO_FAILED에 맞지만, 기존 B의 status·반환 handed_off·감사 action·recovery 결과 해석도 함께 변경해야 한다. 이름만 FAILED로 치환했다고 HUMAN 전환/실제 배정까지 완료되는 것은 아니다.

나머지 필드를 정상 매핑했다고 가정해도 현재 B의 HANDED_OFF 값을 그대로 저장하면 A의 AUTO_FAILED 조건에는 해당하지 않는다. 유효 배정이 없으면 일반 UNASSIGNED로 보일 수 있지만, 이것도 실제 사람 이관 완료를 뜻하지 않는다.

## 4. DB 제약과 같은 회차 전환의 호환성

| 항목 | 현재 제약/동작 | 이관 시 주의 |
|---|---|---|
| Job 유일성 | UNIQUE(ticket_id,cycle_no) | 같은 C에 AUTO+HANDOFF 두 행 불가. UNIQUE 삭제를 기본 해결책으로 삼지 않음 |
| Job 종류/사유 | AUTO/HANDOFF. AUTO면 reason_code=NULL. HANDOFF는 source_message_id와 허용 reason 필수 | AUTO FAILED에 `MAX_ATTEMPTS_EXHAUSTED`를 reason_code로 넣으면 CHECK 위반. 정형 error_code/감사 사유를 사용. job_kind 덮어쓰기 금지 |
| Job 상태/lease | PENDING/RUNNING/RETRY/SUCCEEDED/FAILED/HANDED_OFF/CANCELLED. RUNNING만 token/owner/until 모두 필수, 나머지는 모두NULL | FAILED/RETRY/PENDING 전환 시 3종을 같은 update로 제거. B SQLite의 두 필드 제거만으로는 A CHECK 충족 못함 |
| Ticket | requested_mode AUTO/HUMAN. status OPEN/PROCESSING/WAITING_CUSTOMER/HANDOFF_PENDING/ASSIGNED/IN_PROGRESS/FOLLOWUP_PENDING/RESOLVED/CANCELLED | ticket status에 FAILED나 HUMAN을 쓰는 구조가 아님. HUMAN은 requested_mode, 대기는 HANDOFF_PENDING |
| Ticket 종결 | RESOLVED면 resolved_at와 resolution_mode 필수 | 사람에게 넘기는 것은 해결이 아님. resolution_mode=HUMAN 또는 RESOLVED를 이관 표시로 사용하지 않음 |
| cycle/version | 양수 CHECK. job.expected_ticket_version도 양수 | mode/job 상태 간 관계·version+1을 DB가 자동 보장하지 않음. 새 writer에서 검증/증분 필요 |
| 활성 배정 | ticket당 ended_at=NULL 최대1개, 회차와 무관한 partial UNIQUE | 이전 회차·무효 배정도 물리적으로 남으면 신규 INSERT 충돌. 유효성=false라고 덮어쓰거나 무조건 새로 넣지 않음 |
| 최종 응답 | ticket+cycle당 final OUT 최대1개 | 이미 최종 응답이 있는 회차를 실패 이관으로 다시 해결하지 않음. 정상 AUTO 실패 회차에는 새 final을 만들지 않음 |

Job의 mode는 ticket에, 종류는 job에 있다. `AUTO FAILED + ticket HUMAN/HANDOFF_PENDING + 같은 cycle`을 금지하는 cross-table CHECK는 없다. 그러나 그 조합을 만드는 현재 A 명령도 없다. **‘DB가 허용’과 ‘지원되는 업무 전이’는 구분한다.**

기존 `request-agent`/`reopen`은 고객 소유권·고객 user 잠금·고객 메시지·멱등키를 전제로 한다. cycle+1, version+1, 이전 PENDING/RUNNING/RETRY 취소와 lease 제거, 배정 종료, team_id 비우기, 새 job을 만든다. 이미 FAILED인 이전 job은 이 취소 update에 포함되지 않아 과거 FAILED로 남지만, 큐는 현재 cycle의 새 job을 보게 된다. 엔진 실패를 고객 JWT/가짜 고객 메시지로 우회 입력하지 않는다.

## 5. AUTO_FAILED 조회와 실제 배정은 별개

### 5.1 현재 조회 predicate

`queue_query`는 현재 cycle의 route/job을 조인한다. 기본 대상은 `ticket.status NOT IN (RESOLVED,CANCELLED) AND (유효배정 없음 OR 현재 job.status=FAILED)`다. 그중 `job_kind=AUTO AND status=FAILED`이면 이유가 AUTO_FAILED다. ticket.requested_mode와 job.expected_ticket_version 일치를 큐 진입 조건으로 요구하지 않는다.

- ROUTED: 현재 cycle의 명시 route, 활성 팀, 조회자 user_team_scopes, EXCEPTION_QUEUE_READ 필요. AGENT는 소속 팀과 지원 category도 제한한다. ticket.team_id만으로 route를 추정하지 않는다.
- UNROUTED: route 없음/null/비활성 팀. ADMIN+UNROUTED_QUEUE_READ. 이 조회에 team_id 필터는 금지한다.
- route는 담당 배정/티켓 원문 권한을 주지 않는다. 큐를 봐도 ticket_scope 밖 상세는404일 수 있다. 조회 capability는 배정 쓰기 권한이 아니다.
- 정상 control 행이 있으면 FAILED AUTO의 automatic_state는 HUMAN_REVIEW_REQUIRED이며 PAUSED 표시보다 우선한다. control 부재는 CONTROL_UNAVAILABLE이다. 이 표시는 실행 허가가 아니다.

| row가 올바르게 저장돼 있다고 가정한 상태 | 현재 큐 | 현재 workload |
|---|---|---|
| AUTO FAILED + AUTO/OPEN·PROCESSING, 유효 배정 없음 | AUTO_FAILED | 미배정의 automatic_path |
| AUTO FAILED + HUMAN/HANDOFF_PENDING, 유효 배정 없음 | AUTO_FAILED | 미배정의 human_assignment_waiting |
| AUTO FAILED + HUMAN/ASSIGNED·IN_PROGRESS, 유효 배정 있음 | **여전히 AUTO_FAILED** | 미배정에서는 제외, 상담사 개인 업무량에는 포함 |
| 위 티켓이 RESOLVED/CANCELLED | 큐에서 제외 | 활성 업무량에서 제외. FAILED job 이력은 별도로 보존 가능 |

이는 source predicate의 논리적 결과이며 이번 DB에서 재현 실행한 결과가 아니다. **실패 이력 보존은 필요하지만, 배정 완료 뒤 실패 큐에 계속 보이는 현재 동작을 ‘배정 필요’로 해석하면 안 된다.**

### 5.2 현재 없는 실행 경계

FAILED는 `claim_jobs(...,job_kind="AUTO")`와 `job_kind="HANDOFF"` 모두 대상이 아니다. 전자는 FAILED와 HUMAN mode에서, 후자는 AUTO 종류에서 탈락한다. FAILED를 배정 목적으로 PENDING/RUNNING으로 되살리거나 job_kind를 HANDOFF로 바꾸지 않는다.

A에는 상담사 배정을 수행하는 공통 함수/HTTP API가 없다. `record_queue_route`는 route만 기록하고 `lock_resolution_gate`는 이미 배정된 상담사의 해결 전 gate다. tests/phase3_helpers.assign과 Azure 검증용 합성 writer는 실제 B 배정 엔진이 아니다. B d7a8dbd의 검토 경로에도 이 실패 경로의 실제 배정 writer는 없다.

현재 신규 HANDOFF claim에는 RUNNING lease가 생기지만, 실제 배정 저장 함수가 없으므로 A가 배정 시 job 종류·status·lease를 강제하는 완성 계약은 아직 없다. 기존 B 계약의 ‘HANDOFF worker가 최신 cycle/version/HUMAN/lease를 확인하고 원자 배정’은 연결해야 할 경계다. 이를 AUTO FAILED에 그대로 적용하면 terminal job에는 lease가 없어 진행할 수 없다. 새 FAILED 전용 배정 경계가 필요하다.

`repository.agent_assignment_exists`는 현재 cycle, 미종료/이미 시작된 배정, ticket/agent/team 일치, 활성 직원/팀, normalized scope/category, 처리 가능한 status를 검사한다. HUMAN 해결 gate는 여기에 requested_mode=HUMAN과 모든 회차 필수 후속 미완료 여부를 검사한다. **그 gate는 job이 HANDOFF/SUCCEEDED일 것을 요구하지 않는다.** 따라서 올바른 HUMAN 배정 후 AUTO FAILED를 남기는 row는 사람 해결 gate와 구조적으로 호환 가능하지만, 실제 사람 응답 writer 연결은 미구현/미검증이다.

### 5.3 PAUSED의 현재 범위

현재 A는 AUTO claim/자동 응답 확정을 막고, HANDOFF claim·고객 사람 요청·사람 해결 gate에는 그 AUTO gate를 적용하지 않는다. 이미 있는 함수가 모든 실제 자동 배정까지 통제한다고 보장하지 않는다. 실제 배정 엔진이 없고, B의 fixture gate도 전역 control을 읽지 않는다.

- 직원 수동 배정도 현재 실행 API는 없다. 향후 HUMAN 수동 명령은 직원 권한·팀 scope·cycle/version/중복 배정 검증을 해야 하며 AUTO PAUSED만으로 사람 업무 전체를 차단하는 설계는 기존 방향과 다르다.
- 사람 라우팅을 수행하는 B의 **무인 자동 배정**을 PAUSED 중 허용할지는 별도 실행 정책과 gate가 필요하다. HANDOFF claim이 허용된다는 사실만으로 새 FAILED 배정기를 허용하지 않는다. 미합의 상태에서는 해당 자동 실행을 시작하지 않는 것을 제안한다.
- Worker의 실패 확정/재시도에 PAUSED·generation을 어떻게 적용할지도 현재 미구현이다. 아래의 보완 기본안은 AUTO worker 명령에 기존 gate를 적용하는 fail-closed 방식이다. 중지 후 terminal 정리를 예외 허용하려면 ‘AI/발송 없는 안전한 퇴역’ 전용 명령을 별도로 합의한다.

## 6. 상태 전이표 — 현재와 제안 분리

C=실패 전 현재 회차, V=실패 전 ticket.version=job.expected_ticket_version, N=claim에 의해 증가한 attempt, G=claim generation, R=현재 cycle route revision(없으면0)이다. 아래 **보완안은 아직 구현·확정된 계약이 아니다.** 정상 AUTO 실행 회차(OPEN/PROCESSING, resolution_mode/resolved_at 없음, final OUT 없음, 미종료 물리 배정 없음)로 입력 범위를 좁힌다.

### 6.1 권고: 최종 실패와 HUMAN 전환을 한 번에 원자 저장

| 단계 | ticket | job | lease/재시도 | route·원자 범위 |
|---|---|---|---|---|
| 최종 실패 직전 — 현재 가능한 상태 | AUTO, OPEN/PROCESSING, cycle=C, version=V | AUTO/RUNNING, cycle=C, expected=V, attempt=N, generation=G | token/owner/until 유효 | 현재 R 또는 미라우팅 |
| 실패 확정 직후 — 논리 단계 | 단독 중간 commit 없음 | FAILED로 퇴역 | 3종NULL, attempt=N 유지 | 아래 HUMAN 전환과 **같은 transaction**, 외부에서 이 중간 상태를 관측하지 않음 |
| HUMAN 전환 후 — 제안 | HUMAN/HANDOFF_PENDING, cycle=C, version=V+1, team_id=NULL, resolution_mode/resolved_at=NULL. 기존 SLA/first_replied_at/created_at 보존 | **같은 AUTO FAILED 행**. expected=V를 실패 실행 근거로 보존, attempt=N·generation=G 보존, reason_code=NULL | token/owner/until=NULL, next_attempt_at 기존 값 유지(NN), 자동 재예약 없음 | route가 올바르면 R 유지. 명시 수정이면 CAS로 R+1. job+ticket+route+최소 감사/receipt 한 transaction |
| 상담사 배정 후 — 제안 | HUMAN/ASSIGNED, 같은 C, version=V+2, team_id=선택팀 | AUTO FAILED 그대로, expected=V 그대로 | lease 없음·재활성화 없음 | 새 유효 assignment+필요한 route+ticket+감사/receipt 한 별도 transaction. 중복/늦은 명령은 거부 |

최종 실패+HUMAN은 ticket의 한 업무 명령이므로 **version을 한 번만 +1**하는 제안이다. 배정은 다음 업무 명령이어서 다시 +1한다. route만 바꾸거나 lease/attempt만 바꾸는 것은 ticket.version을 올리지 않는 기존 원칙을 유지한다. 실제 현행 함수가 이 표를 수행하는 것은 아니다.

V+2는 사이에 다른 업무 변경이 없다는 예시다. category 정정 등 별도 업무 변경이 있었다면 그 최신 revision을 읽고 각 명령에서 +1해야 하며 과거 V로 계산해 덮어쓰지 않는다. UNCLASSIFIED 같은 업무 유형으로 배정 자격을 확인할 수 없으면 명시 분류/검토가 먼저 필요하고 category를 추측하지 않는다.

terminal FAILED의 expected_ticket_version을 V로 고정하는 것은 **보완안의 선택**이다. DB는 ticket 최신 version과의 동등성을 강제하지 않고, FAILED는 claim되지 않는다. 실패 실행 근거와 최신 티켓 revision을 구분한다. 새 FAILED 배정 명령은 현재 ticket의 V+1을 검사해야 하며 `job.expected=현재 ticket.version`인 RUNNING용 gate를 재사용하지 않는다. 기존 B PG 코드가 모든 상태에서 그 동등성을 가정한다면 수정·합의가 필요하다. claim 가능한 PENDING/RETRY/RUNNING에서는 기존 동등성 계약을 그대로 지킨다.

### 6.2 분리해야 한다면 — 복구 주체가 있는 경우에 한함

| transaction | 제안 상태 | 조건·복구 |
|---|---|---|
| F: 최종 실패 기록만 | ticket AUTO/OPEN·PROCESSING, C/V 그대로. job AUTO FAILED, expected=V, lease3종NULL | ticket을 정말 변경하지 않는 job-only 확정. AUTO_FAILED에는 보이고 재claim은 안 됨. 아직 HUMAN이 아니므로 배정 완료로 간주하지 않음 |
| H: 후속 사람 전환 | fresh ticket/job 잠금 아래 HUMAN/HANDOFF_PENDING, C 유지, V→V+1 | FAILED의 기록 근거와 현재 cycle/version/route를 다시 검사하는 **별도 인증 명령** 필요. 이미 HUMAN이면 동일 명령 receipt 확인 또는 충돌, 재문의면 stale 거부 |

이 방식도 DB/조회상 중간 상태는 유효하고 재실행이 차단된다. 그러나 H를 재시도/조정할 내구 복구 주체가 없으면 영구 대기한다. 실패한 Worker의 지워진 lease로 H를 계속 승인하면 안 된다. 최소 복잡도로는6.1 단일 transaction을 우선한다. F에서 ticket.last_error_code까지 바꾼다면 더 이상 job-only가 아니므로 version 정책을 다시 정해야 한다. 본 기본안은 그 값을 HUMAN 전환 transaction에서만 필요시 함께 기록한다.

## 7. B가 현재 호출할 수 있는 A 공통 함수

모두 **내부 Python 함수**다. A 설치/모듈 경로와 SQLAlchemy session을 공유해야 한다. B의 SQLite connection이나 `/api/automation/...` 개발 endpoint를 이 함수로 간주하지 않는다. 서비스 ID 문자열은 인증이 아니며 최소 DB identity/호출자 인증은 별도다.

| 실제 import·시그니처 | 반환·현재 거부 조건 | 실패 이관에서 할 수 있는 것 / 없는 것 |
|---|---|---|
| `from app.jobs import claim_jobs`; `claim_jobs(session, worker_id, *, limit=10, lease_seconds=60, job_kind="AUTO")` | claim된 job mapping 목록. PG 외 RuntimeError, 잘못된 worker/limit/lease/kind ValueError. AUTO PAUSED는[], control/generation 문제는 WorkRejected/DB 예외 | 실행 예약만. FAILED claim/3회 상한/실패 확정/배정 불가 |
| `from app.finalization import AutomaticReply, commit_automatic_reply`; `commit_automatic_reply(session, command)` | `{message_id,ticket_id,cycle_no,revision}`. WORK_NOT_FOUND, STALE_TICKET_REVISION, AUTOMATION_NOT_ALLOWED, INVALID_LEASE, FINAL_REPLY_ALREADY_EXISTS, BLOCKING_FOLLOWUP 및 control 오류 | 승인된 자동 **성공 응답**만. AutomaticReply는 expected_revision/message/job_id/lease_token/worker_id/cycle_no 필수, automation_generation 선택. 실패 writer로 호출 금지 |
| `from app.exception_queue import RouteCommand, record_queue_route`; `record_queue_route(session,ticket_id,body,*,service_id)` | `{ticket_id,cycle_no,team_id,revision,recorded_by_service,recorded_at}`. revision은 **route revision**. 잘못된 service ID ValueError, ROUTE_TICKET_REVISION_CONFLICT/ROUTE_TICKET_FINISHED/ROUTE_TEAM_UNAVAILABLE/ROUTE_REVISION_CONFLICT는APIError409 | RouteCommand(expected_revision,cycle_no,expected_route_revision,team_id 명시 UUID 또는None). 현재 ticket mutex 아래 route만 기록. HUMAN 전환·직원 선택·assignment·ticket.version 변경 안 함. 팀 활성만 검사하므로 B가 업무 유형/배정 자격도 별도 검증 |
| `from app.automation_control import read_control, assert_automatic_allowed`; `read_control(session,*,shared=False)`, `assert_automatic_allowed(session,generation)` | control row 반환. AUTOMATION_CONTROL_UNAVAILABLE / AUTOMATION_PAUSED / AUTOMATION_GENERATION_CHANGED의 WorkRejected; SQL 오류도 허용 아님 | AUTO gate 부품. ticket/job 잠금 뒤 control SHARE. 전체 lease/cycle 검증·실패 저장은 별도 |
| `from app.resolution import lock_resolution_gate`; `lock_resolution_gate(session,ticket_id,*,expected_revision,cycle_no,mode,human_user=None)` | 잠근 ticket row. TICKET_NOT_FOUND, STALE_TICKET_REVISION, HUMAN_RESOLUTION_NOT_ALLOWED, AUTOMATION_NOT_ALLOWED, BLOCKING_FOLLOWUP | 배정된 HUMAN의 해결 전 gate. 미배정 HANDOFF_PENDING을 배정하거나 HUMAN으로 바꾸는 함수 아님. job FAILED는 직접 검사하지 않음 |
| `from app.repository import agent_assignment_exists`; `agent_assignment_exists(agent_id=None,*,as_of=None)` | ticket에 상관된 SQL EXISTS 표현식 | 유효 배정/권한/중복 방지에 재사용. boolean 실행 결과나 배정 writer 아님. 배정 전 후보 자격 검증은 별도 필요 |
| `from app.audit import record`; `record(session,actor,action,target_type,target_id,*,result="SUCCESS",reason="AUTHORIZED",ticket=None,cycle=None,service="backend-a")` | 반환값없음. SQL 오류는 caller에 전파. event_id/event_key 무작위, payload={} | 최소 감사. deterministic failure receipt/동일 명령 멱등 응답은 현재 제공하지 않음 |

`assert_automatic_allowed`의 실제 code는 `AUTOMATION_PAUSED`, `AUTOMATION_GENERATION_CHANGED`, `AUTOMATION_CONTROL_UNAVAILABLE`이다. `WorkRejected`는 [app.resolution](../app/resolution.py#L13)에 정의되고 finalization에서도 import돼 있다.

모든 A 공통 writer는 caller의 외부 transaction/commit을 요구한다. 예를 들어 **현재 가능한 route 기록**만 보이면 다음과 같다(예시를 실행하지 않음).

```python
from app.db import session_factory
from app.exception_queue import RouteCommand, record_queue_route

factory = session_factory(existing_a_engine)
with factory.begin() as session:
    route_receipt = record_queue_route(
        session, ticket_id,
        RouteCommand(expected_revision=V, cycle_no=C,
                     expected_route_revision=R, team_id=chosen_team_id),
        service_id=authenticated_b_service_id,
    )
# context 정상 종료 시 commit. 이것만으로 HUMAN 전환/배정이 되지는 않는다.
```

동시성/DB 오류는 outer transaction을 rollback하고 최신 상태를 다시 읽는다. version/route 충돌을 무조건 덮어쓰지 않는다. 만료/이전 token·generation으로 같은 작업을 재사용하지 않는다. 외부 AI/HTTP·실제 발송은 잠금 transaction 밖에서 수행한다. 세션 내부 begin_nested는 외부 commit이나 서비스 인증의 대체가 아니다.

## 8. 최소 보완 제안 — 현재 import 불가, 구현하지 않음

### 8.1 실패 확정 명령

제안 이름 `commit_auto_failure(session, command)`는 **현재 존재하지 않는다**. 새로운 HTTP API라고 안내하지 않는다. 입력 후보:

`job_id, ticket_id, cycle_no, expected_revision, lease_token, worker_id, automation_generation, attempt, retryable, error_code, command_id` 및 필요 시 명시 `route_team_id, expected_route_revision`. attempt는 client 선언을 신뢰하지 않고 잠근 DB row와 일치시킨다. max_attempts=3은 합의한 B 정책 버전으로 관리하고 요청자가 임의 상향하지 못하게 한다.

검증·저장 순서의 최소안:

1. 호출자 인증 후 ticket→job 순으로 잠금. 같은 ticket/job/current cycle, ticket.version=command.expected_revision=job.expected_ticket_version, AUTO/OPEN·PROCESSING·미종결·최종 OUT 없음을 확인한다. 미종료 물리 배정이 남으면 임의 종료하지 않고 별도 인수/정리 명령을 요구한다.
2. RUNNING·token·worker(owner)·attempt·lease와 claim generation을 검증한다. ticket/job 뒤 기존 AUTO control SHARE/generation gate를 적용하는 것을 기본 제안으로 둔다. PAUSED/상태 조회 실패/이전 generation이면 **이번 worker 명령은 쓰기0으로 거부**한다. 중지 예외 퇴역 정책은 별도 합의 전 허용하지 않는다.
3. retryable이고 attempt<3이면 RETRY, next_attempt_at=합의한 backoff 시각, lease3종NULL, ticket/cycle/version 그대로, 최소 감사. A는 PENDING도 claim하지만 새 계약의 재시도 표시는 RETRY로 구분하는 제안이다. B 현재 PENDING 재시도와 매핑을 합의한다.
4. retryable=false 또는 attempt>=3이면6.1의 FAILED+HUMAN을 같은 transaction으로 저장한다. 세 번째 claim 이후 세 번째 실패에서 N=3을 사용하고 fail에서 attempt를 또 올리지 않는다. mode/status+version과 route/감사/receipt를 원자 저장한다.
5. 모든 blocking gate가 끝난 뒤 **첫 쓰기 직전 wall-clock UTC로 lease를 다시 검사**한다. transaction_timestamp/SQL now의 고정 시각을 대체로 사용하지 않는다. route를 먼저 썼다가 lease 만료를 발견하면 savepoint/outer transaction 전체를 rollback한다. writer가 내부 예외를 삼켜 부분 commit하지 않게 한다.

실패 전환은 해결 명령이 아니므로 미완료 필수 후속을 완료/삭제하지 않고 SLA를 새24시간으로 재설정하지 않는다. `lock_resolution_gate`나 `commit_automatic_reply`를 실패용으로 재사용하면 부적절한 해결/후속 gate가 섞인다.

**동시성·멱등:** 같은 명령 재전송은 이미 끝난 ticket을 다시 HUMAN/HANDOFF_PENDING으로 되돌리거나 version을 또 올리면 안 된다. 단순히 job.status=FAILED를 보면 성공이라고 반환하는 것도 원래 caller/token을 입증하지 못한다. 최소 write-once CAS+terminal 재요청 거부부터 구현할 수 있고, 원래 receipt 반환까지 필요하면 내구 명령 증거가 필요하다.

migration을 피하는 한 가지 **제안**은 기존 audit_events의 UNIQUE event_key와 허용된 정형 receipt payload를 새 전용 writer에서 사용하는 것이다. key는 job/attempt/operation 단위이고 command hash에는 cycle/revision/worker/lease 시도 identity를 묶되 token 원문은 저장하지 않는다. 같은 key/다른 hash는 충돌이다. 현재 audit.record는 무작위 key/payload={}라 이 기능을 제공하지 않는다. 임의 payload 허용으로 전역 audit 정책을 풀지 않고 새 이벤트 allowlist·receipt 읽기 권한·보존 규칙을 정의해야 한다. API idempotency_keys는 operation/target CHECK가 고정돼 있으므로 새 실패 명령을 임의로 넣지 않는다.

원래 성공했던 명령의 exact replay는 원래 receipt를 반환할 수 있어도 **현재 업무 실행 허가가 아니다.** 재문의/배정 이후 새 실패 명령은 current cycle/version에서 거부하고, 예전 receipt를 최신 회차 결과로 복사하지 않는다.

### 8.2 최대 횟수·lease 만료 복구

A claim에는 상한이 없어 B의 후보 prefilter만으로 모든 consumer의 최대3회를 강제할 수 없다. A 공통 claim에 선택적 정책 상한을 넣거나 B의 동일 transaction 예약 adapter에서 상한을 원자 검사하는 보완이 필요하다. 단순히3회 이상을 필터링해 영구 RUNNING/PENDING으로 방치하지 않는다.

마지막 시도의 lease가 만료된 경우 worker 실패 명령은 INVALID_LEASE로 거부해야 한다. 이를 처리할 **인증된 복구/소진 퇴역 명령은 별도**로 설계한다. 최신 ticket→job 잠금 아래 expired RUNNING·현재 cycle/version·새 lease로 이미 회수되지 않았음을 검사하고 attempt 소진이면 terminal로 기록한다. 살아 있는 lease를 가진 새 Worker를 이전 token으로 실패시키면 안 된다. PAUSED/generation 전환 뒤 이 퇴역을 허용할지와 소유권은 팀 합의가 필요하다. 현재 B recovery를 A DB에 그대로 연결하지 않는다.

### 8.3 FAILED 전용 배정 경계

제안 이름 `assign_failed_auto_ticket(session, command)`도 **현재 존재하지 않는다**. 실제 실행 책임은 B다. A가 재사용 가능한 자격/잠금 gate를 제공하고 B writer가 같은 session에서 assignment/ticket/route/감사를 원자 저장하는 방식이 최소다.

- 입력 후보: `ticket_id, cycle_no, expected_revision, failed_job_id, expected_route_revision, team_id, agent_id, authenticated_actor/service, command_id`. job 종류=AUTO/status=FAILED는 보존하고, terminal job에 RUNNING lease를 요구하지 않는다. 그렇다고 worker token 없이 임의 쓰기를 허용하는 것이 아니라 **별도 배정 권한**으로 승인한다.
- ticket→job→배정 등 기존 순서를 지킨다. 고객 user를 나중에 잠그지 않는다. 현재 HUMAN/HANDOFF_PENDING, 최신 cycle/revision, 미종결, route CAS, 실패 명령 근거를 확인한다.
- 활성 AGENT·소속/활성 팀·현재 scope/category 지원을 배정 전에 검증한다. assignment_exists는 이미 존재하는 배정을 검증하는 표현식이므로 신규 후보 검증을 그대로 대체하지 못한다. route와 ticket.team_id는 실제 책임 팀으로 일치시킨다.
- 이미 유효 배정되면 새로 만들지 않는다. exact replay는 원래 receipt, 다른 명령은 ALREADY_ASSIGNED/충돌로 처리하는 제안이다. 무효이지만 ended_at=NULL인 행은 별도 권한 있는 인수/종료 규칙 없이 덮어쓰지 않는다. 물리 UNIQUE가 마지막 방어선이며 충분한 업무 gate는 아니다.
- 새 assignment(C,team,agent,assigned_at) + ticket HUMAN/ASSIGNED/team/version+1 + 필요한 route + 감사/receipt를 원자 저장한다. job FAILED·leaseNULL·attempt/기존 오류는 유지한다. category·정책·scope를 임의 복원하지 않는다.
- 현재 큐의 FAILED 조건 때문에 배정 뒤에도 행이 남는다. 새 배정 소비자는 `~agent_assignment_exists()`와 최신 mode/status를 **쓰기 직전** 다시 검사해야 한다. 목록만 읽고 INSERT하면 중복 배정 위험이 있다.

큐를 운영상 ‘배정할 건만’ 보여줘야 한다면, 기존 실패 이력 큐는 유지하고 읽기 전용 assignment_state/action_required 필드·필터를 추가하는 보완을 제안한다. 현재 QueueItem에는 유효 배정 여부 필드가 없으므로 stage만으로 추측하지 않는다. 별도 acknowledgement가 필요하면 독립 사건/상태로 설계하고 FAILED를 지우거나 재활성화해서 큐를 숨기지 않는다. EXCEPTION_QUEUE_READ를 배정 쓰기 권한으로 승격하지 않는다.

### 8.4 route revision·version 연결

`record_queue_route` 자체는 route revision만 올리고 ticket.version을 올리지 않는다. 같은 transaction에서 이관 writer가 V→V+1을 수행한다면 route 호출을 ticket update **전**에 expected_revision=V로 하거나 update 후 새 V+1로 해야 한다. 증가 전 V를 update 후 넘기면409다. 명시 route 변경이 없으면 불필요하게 route revision을 올리지 않는다. 팀을 모르면 None/미라우팅으로 두고 이전 배정/category로 추정하지 않는다. route 변경 시 queued_at이 달라질 수 있지만 SLA 시작·기한을 재설정한 것은 아니다.

## 9. 같은 회차·새 회차 비교와 팀 결정 사항

| 방식 | 장점 | 호환성·추가 작업 |
|---|---|---|
| **같은 C, AUTO FAILED 보존** — 우선 제안 | UNIQUE 유지, 실패 실행 근거 보존, 고객 요청과 엔진 실패를 구분, 불필요한 고객 메시지/회차 증가 없음 | 새 실패/HUMAN 원자 writer·terminal 전용 배정 명령·예약/멱등·큐 action_required 구분 필요. 기존 HANDOFF claim으로 처리할 수 없음 |
| 새 C+1, 이전 C AUTO FAILED + 새 HANDOFF | 현재 HANDOFF 예약 구조와 맞고 이전 실패 행도 남음 | 엔진용 새 회차 명령은 여전히 미구현. +1 회차/버전·이전 lease/배정·followup 책임·SLA·source_message/reason·Fabric 회차 지표 의미를 별도 정의해야 함. 큐는 현재 HANDOFF를 조인해 이전 AUTO_FAILED가 더 이상 그 행의 이유가 아님 |
| 고객 request-agent/reopen 우회 호출 | 해당 고객 동작 자체는 기존 지원 | 엔진 실패 대체로 사용 금지. 고객 소유권·공개 IN 메시지·고객 의사·정해진 reason이 필요하며 회차도 증가함 |

새 회차 방식도 기존0002의 HANDOFF reason allowlist에 ENGINE_FAILURE 같은 새 값을 바로 넣을 수 없다. 원래 요청 source_message를 재사용할지, 시스템 요청 모델을 추가할지부터 합의해야 한다. 이유만 OTHER로 위장하지 않는다. UNIQUE 삭제나 동일 회차 두 job을 기본안으로 하지 않는다.

먼저 결정할 항목은 (1) attempt=claim 횟수와 최대3회 정책/비재시도 실패 (2) worker 실패의 PAUSED/generation gate와 별도 소진 복구 권한 (3) same-cycle terminal job.expected_version 보존 방식 (4) 실패/HUMAN 원자 명령의 멱등 receipt (5) 직원 수동/무인 배정의 권한·중지 정책 (6) 배정 후 큐 표시/acknowledgement다. 새 enum/제약이 필요하다고 단정하지 않으며, 위 same-cycle 기본안의 row 저장 자체는 기존 제약을 유지할 수 있다.

## 10. 향후 구현 검증 계획 — 이번에 실행하지 않음

- 실제 격리 PG에서 AUTO claim→재시도/3회 소진/비재시도 실패, retry에서 attempt 중복 증가 없음, 최종 FAILED lease3종NULL·NN next_attempt, FAILED 영구 재claim 차단을 확인한다.
- 재문의와 실패의 양쪽 잠금 순서, 늦은 worker/다른 worker/token/만료/다른 generation, PAUSED/없는 control/SQL 오류의 쓰기0을 확인한다. 모든 gate 대기 중 lease 만료도 포함한다.
- 실패+HUMAN+route+감사/receipt의 부분 실패 rollback, exact replay·다른 hash 충돌·배정/재문의 이후 replay 비파괴, 원자 V+1·후속 배정 추가+1을 확인한다.
- 현재 FAILED AUTO+HUMAN의 큐 노출, 유효 배정 후에도 실패 큐에는 남고 workload 미배정에서는 제외되는 차이를 확인한다. route 없음/비활성 팀·다른 팀 scope·AGENT category·read capability가 쓰기 허가가 아닌지 확인한다.
- FAILED 전용 배정 명령 두 개의 경합, physical old assignment 충돌, 현재 category/scope/팀 변경, 자동/수동 배정 중지 정책을 검증한다. 완료 후 사람 resolution gate·모든 회차 필수 후속·최종 OUT 유일성을 회귀한다.
- B의 SQLite→PG 필드/UUID/UTC/native datetime·같은 SQLAlchemy transaction·서비스 인증·오류 응답·실제 worker 연결을 검증한다. fixture gate 승인이나 큐 표시만으로 실제 이관/배정 완료를 보고하지 않는다.

이번 수행은 Git/버전/AST graph/파일·라우터·모델·migration·공통 함수·기존 테스트 **소스**와 지정 B 원격 SHA 확인뿐이다. 문서 링크/구문 및 기존 파일 보존 검사 외 업무 실행 검증은 없다. 기존 테스트 PASS 수치를 이번 결과로 재사용하지 않는다.

## 11. Backend B 연동 우선순위

1. 검토 기준 d7a8dbd의 최종 상태 HANDED_OFF와 제안하는 FAILED 보존 계약의 차이를 먼저 확정한다. 최대3회 정책은 B 책임이며, A claim의 상한 강제로 오해하지 않는다. PG 필드 매핑과 실패/재시도 검증을 준비한다.
2. 같은 회차에서 requested_mode=HUMAN, status=HANDOFF_PENDING, ticket.version+1을 원자 저장하는 방안은 **검토 당시 미구현 제안**이다. AUTO 종류·FAILED 이력을 유지하고 lease 3종을 NULL로 비우며 같은 회차에 별도 HANDOFF Job을 추가하지 않는 계약을 검토한다.
3. AUTO_FAILED 조회와 배정 실행을 분리한다. FAILED는 claim 대상이 아니고 유효 배정 후에도 실패 큐에 보일 수 있으므로 별도 배정 명령·멱등·중복 방지 경계를 합의한다.
4. 실패 확정·HUMAN 전환·FAILED 전용 배정의 transaction 계약이 구현되기 전에는 고객 request-agent를 엔진 실패 이관 대신 호출하거나 FAILED Job을 재활성화하지 않는다.
