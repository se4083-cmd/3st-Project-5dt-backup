# 재문의와 상담사 직접 연결

2026-11-02의 Backend A 2단계 구현입니다. 기존 1단계 문서의 재문의/상담사 연결 관련 미구현 설명을 대체합니다. 상세 기획서가 추가로 없으므로 아래 상태 전이·중복 처리·24시간 SLA는 이번 구현 제안이며 팀 정책 확정이 필요합니다.

## 허용 상태와 전이

| 현재 내부 상태 | 재문의 /reopen | 직접 연결 /request-agent |
|---|---|---|
| OPEN / PROCESSING | 새 AUTO 회차, OPEN | 새 HUMAN 회차, HANDOFF_PENDING |
| WAITING_CUSTOMER, AUTO | 새 AUTO 회차, OPEN | 새 HUMAN 회차, HANDOFF_PENDING |
| WAITING_CUSTOMER, HUMAN | 새 HUMAN 회차, HANDOFF_PENDING | 409 HUMAN_REQUEST_ALREADY_ACTIVE |
| HANDOFF_PENDING / ASSIGNED / IN_PROGRESS / FOLLOWUP_PENDING | 새 HUMAN 회차, HANDOFF_PENDING | 409 HUMAN_REQUEST_ALREADY_ACTIVE |
| RESOLVED, AUTO | 새 AUTO 회차, OPEN | 새 HUMAN 회차, HANDOFF_PENDING |
| RESOLVED, HUMAN | 새 HUMAN 회차, HANDOFF_PENDING | 새 HUMAN 회차, HANDOFF_PENDING |
| CANCELLED | 409 TICKET_TRANSITION_NOT_ALLOWED | 동일 |

requested_mode=HUMAN, resolution_mode=HUMAN 또는 사람 업무 상태 중 하나이면 재문의도 HUMAN을 유지합니다. 회차가 바뀌었다고 자동 경로로 초기화하지 않습니다. 접수 후 처리 중에도 추가 문의를 새 회차로 받는 정책을 택했습니다. 일반 메시지 추가 API는 이번 범위가 아닙니다.

수락된 명령은 cycle_no+1, version+1을 적용합니다. 예전 최종 응답과 승인 이력은 삭제/덮어쓰기하지 않습니다. 기존 PENDING/RUNNING/RETRY 작업은 CANCELLED로 바꾸고 lease 세 필드를 NULL로 해제합니다. 종료된 SUCCEEDED/FAILED/HANDED_OFF/CANCELLED 이력은 보존합니다. 모든 이전 활성 배정을 종료하고 현재 team_id를 비웁니다. 신규 배정은 B가 수행하므로 그 전에는 이전 상담사·팀의 권한이 이어지지 않습니다.

resolved_at/resolution_mode/first_replied_at/last_error_code는 새 회차 기준으로 초기화합니다. sla_due_at은 현재 UTC+24시간으로 설정합니다. 기존 category·VOC 라벨과 과거 불만시각은 A가 재분류하지 않습니다. B/Fabric은 회차와 이벤트를 함께 해석하고 고정 분석 기준시각과 신규 생성시각을 구분해야 합니다.

고객 PUBLIC 메시지, 새 AUTO 또는 HANDOFF job, 최소 감사, 멱등 응답 snapshot을 같은 트랜잭션으로 저장합니다. HANDOFF에는 reason_code와 source_message_id로 직접 연결 사유·고객 요청을 연결합니다. 재문의가 사람 경로를 이어갈 때는 내부 사유 HUMAN_CONTINUATION을 사용합니다. 중복 사람 연결의 409는 새 요청을 수락한 것이 아니므로 메시지·사유·작업을 추가하지 않습니다. 추가 설명을 제출하려면 재문의 API를 사용합니다.

## 동시성과 멱등

목록/상세에 공개 `revision`과 `cycle_no`를 추가했습니다. revision은 version의 동시성 토큰이며 role/customer_id 같은 권한 정보가 아닙니다. 두 명령은 expected_revision을 필수로 받고 잠금 후 현재 version과 비교합니다. 오래된 UI의 요청은 409 TICKET_REVISION_CONFLICT입니다.

모든 고객 명령은 user 행 → ticket 행 → job 행(job_id 순) → assignment 순서로 잠급니다. user 잠금은 사용자별 전역 key namespace를 보장하며 사용자 한 명의 변경 명령을 직렬화하는 단순한 선택입니다. 서로 다른 고객은 독립적입니다. B의 claim/확정은 ticket → job 순서이며 고객 user를 잠그지 않습니다. B도 이 순서를 유지해야 교착 위험을 줄일 수 있습니다.

멱등 PK는 기존 user_id+key를 유지합니다. 새 operation과 response_snapshot을 추가하고 ticket_id UNIQUE를 제거해 한 티켓의 여러 성공 명령을 저장합니다. 신규 명령 해시에는 operation, 대상 ticket_id, 전체 정규화 body(expected_revision 포함)를 넣습니다. 1단계 CREATE_TICKET의 기존 해시와 접수 결과는 그대로 호환합니다. 같은 key를 다른 API/대상/body에 사용하면 409입니다. 최초 201, 동일 재시도 200이며 snapshot을 반환하므로 뒤에 다른 회차가 생겨도 원래 결과가 바뀌지 않습니다. 현재 티켓 상태는 GET으로 새로 조회합니다.

| 경합 | 결과 |
|---|---|
| 동일 key·동일 요청 | 1개 성공 명령, 201 + 200 |
| 다른 key, 같은 expected_revision | 1개 회차만 생성, 201 + 409 |
| 재문의와 사람 연결, 같은 revision | 먼저 잠금을 얻어 성공한 명령만 수락. 패자는 409 후 새 상태 확인 |
| 재문의가 자동 응답보다 먼저 commit | 이전 회차·version·lease 무효화, 공통 확정 함수가 오래된 응답 거부 |
| 자동 응답이 재문의보다 먼저 commit | 응답은 이전 회차의 유효한 이력. version 증가로 재문의는 409, 새 revision으로 재시도 시 새 회차 생성 |

사람 연결이 먼저 수락되면 늦은 재문의가 자동 모드를 되살릴 수 없습니다. 재문의가 먼저 수락되고 사람 연결이 409라면 아직 사람 연결이 수락된 상태는 아닙니다. Frontend는 새 revision으로 사용자의 연결 의사를 다시 제출해야 합니다. 단순 도착 순서를 전역 처리 순서로 보장하지 않습니다.

## 공통 응답 확정 경계와 한계

`app.finalization.commit_automatic_reply`는 B가 검증한 자동 답변의 저장 경계입니다. 외부 API/AI를 실행하지 않으며 공개 HTTP endpoint도 없습니다. ticket → job 잠금 뒤 실제 현재시각으로 lease 만료를 재검사하고 현재 회차·version·expected_ticket_version·AUTO 경로·job 종류·상태·worker·token을 모두 확인합니다. 미완료 필수 후속이 있으면 해결 확정을 거부합니다. 공개 최종 메시지·ticket RESOLVED/version 증가·job SUCCEEDED/lease 해제·감사를 원자 저장합니다.

최종 OUT 응답은 기존 부분 UNIQUE(ticket_id, cycle_no)로 회차당 한 건입니다. 이전 회차의 유효한 응답은 보존하며 새 회차에 하나를 더 저장할 수 있습니다. 공통 함수 없이 B가 직접 SQL로 삽입하면 DB UNIQUE는 중복만 막고 회차/lease의 최신성까지 보장하지 않습니다. 따라서 B는 이 함수를 사용하거나 동등한 ticket 잠금·검증을 갖춘 확정 경계로 통합해야 합니다. 임의 DB writer를 막는 PostgreSQL trigger나 RLS는 추가하지 않았습니다.

검증은 이 저장 함수와 고정 합성 답변으로 수행한 계약 테스트입니다. 실제 B의 AI/RAG·정책/승인 판단·라우팅·배정·외부 부작용·heartbeat/실패 복구까지 검증한 것은 아닙니다. 실제 결과는 verification.md에 기록합니다.

## 마이그레이션과 복구

0001은 수정하지 않고 0002를 추가했습니다. 기존 job은 AUTO, 기존 멱등 행은 CREATE_TICKET으로 backfill됩니다. fixture의 종료 HANDED_OFF는 과거 자동 처리 결과이므로 새 HANDOFF 요청으로 재해석하지 않습니다. 기존 ticket/message/job/승인·분석 이력을 보존합니다. 2단계 당시 readiness는 0002였으며 현재 4단계 build는 0004을 요구합니다. 후속/고객360 관련 정책은 phase3-followups-customer360.md를 함께 따릅니다.

2단계 명령 또는 HANDOFF 데이터가 생기면 0001로 downgrade하여 이력을 잃지 않도록 명시적으로 거부합니다. 데이터 검사를 생략하는 offline downgrade SQL 생성도 거부합니다. 삭제해서 강제 downgrade하지 않습니다. release rollback은 0002와 호환되는 build를 사용해야 하며, 0001만 요구하는 옛 readiness를 가진 build로 무조건 돌아가지 않습니다.
