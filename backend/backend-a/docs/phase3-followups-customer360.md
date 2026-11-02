# 후속 조치와 고객360

Backend A 0.3.0 / migration 0003 기준입니다. 공식 v4.1의 후속 4상태, 고객360의 누적·최근5건·유형·처리 방식·미해결·반복·담당·후속을 현재 운영 DB에서 제공합니다. 문서와 코드의 2단계 미구현 표기를 갱신했습니다. 상세 기획서가 추가되지 않았으므로 아래 권한·전이·인수·기한 정책은 **이번 구현 제안**이며 팀 확정이 필요합니다. VOC/KPI·분석 게시와 B 엔진은 포함하지 않습니다.

## API와 응답 경계

| 경로 | 메서드 | 용도 |
|---|---|---|
| /api/v1/followups | GET | 고객 본인 공개 후속 목록 |
| /api/v1/followups/{action_id} | GET | 고객 본인 공개 후속 상세 |
| /api/v1/staff/followups | POST / GET | 직원 생성 / 허용 범위 목록·관리자 큐 |
| /api/v1/staff/followups/{action_id} | GET / PATCH / DELETE | 직원 상세 / 수정·인수 / 이력 보존 취소 |
| /api/v1/staff/followups/{action_id}/status | POST | 상태 전이 |
| /api/v1/staff/customers/{customer_id}/360 | POST | 목적을 받는 읽기 전용 snapshot |
| /api/v1/staff/customers/{customer_id}/360/tickets | POST | 같은 범위의 티켓 이력 페이지 |
| /api/v1/staff/customers/{customer_id}/360/followups | POST | 같은 범위의 후속 이력 페이지 |

모두 bearer 인증을 사용합니다. 고객용·직원용 schema와 URI를 분리했습니다. 고객은 public_note가 NULL/공백이 아닌 본인 **티켓** 후속만 봅니다. 공개 필드는 action_id, ticket_id, 원래 cycle_no, status, public_note, due_at, completed_at, updated_at입니다. internal_note·kind·담당 사용자/팀·origin_team_id·책임 회차·blocks_resolution·취소 사유·수정 revision은 제외합니다. 상품 후속과 내부 전용 행은 공개 목록/상세에 나타나지 않습니다. 직원은 자기 권한 안의 공개/내부 정보를 봅니다.

목록은 created_at DESC, action_id DESC keyset 페이지이며 limit 1–100, 기본20입니다. 직원 목록에는 ticket_id/product_id/status 필터를 사용할 수 있습니다. 담당자가 없거나 비활성이어도 책임 팀 scope에 맞는 관리자 목록에서 빠지지 않으며 needs_handover=true로 표시합니다. 물리 DELETE는 없습니다.

## 생성과 변경

생성은 Idempotency-Key가 필수입니다. 티켓·재문의·사람 연결과 같은 user_id+key namespace를 사용합니다. 같은 정규화 body는 200과 저장된 원래 접수 결과, 최초는 201과 action_id/revision/created_at을 반환합니다. 다른 body/operation이면 409입니다. 직원 수정과 상태 변경은 followup 자체의 expected_revision을 필수로 받아 409 FOLLOWUP_REVISION_CONFLICT로 경쟁을 처리합니다. ticket.revision과 혼용하지 않습니다.

```json
{
  "ticket_id": "<uuid>",
  "owner_team_id": "<uuid>",
  "owner_user_id": null,
  "kind": "INTERNAL_CHECK",
  "public_note": "확인 중입니다",
  "internal_note": "직원에게만 보이는 확인 내용",
  "blocks_resolution": true,
  "due_at": "2026-11-10T03:00:00Z"
}
```

ticket_id와 product_id는 정확히 하나입니다. 원래 cycle_no는 서버가 티켓에서 가져오고, 상품에는 두 회차 필드가 모두 NULL입니다. product 후속은 티켓 해결 대상이 없으므로 blocks_resolution=true를 거부합니다. 신규 상태는 OPEN입니다. origin_team_id는 최초 책임 팀으로 고정합니다.

owner_team_id는 활성 허용 팀이어야 합니다. 고객은 생성/변경할 수 없습니다. 상담사는 현재 회차 유효 배정·활성 팀·업무 category 범위의 티켓에서 자기 자신에게만 배정할 수 있습니다. 관리자 생성은 티켓 현재 팀 권한 또는 상품 후속의 담당 팀 권한이 필요합니다. 소유 사용자로는 활성 ADMIN(해당 팀 scope) 또는 해당 티켓의 현재 유효 AGENT만 허용하며 상품은 ADMIN 또는 팀 대기(NULL)만 허용합니다.

PATCH는 public_note/internal_note/kind/due_at/blocks_resolution/owner_team_id/owner_user_id만 변경합니다. target·원래 cycle·origin 팀·시각·status는 직접 수정할 수 없습니다. 필드를 생략하면 유지하고 nullable 필드의 명시적 null은 제거합니다. 기한은 UTC aware이며 생성/변경 시 지정했다면 미래여야 합니다. 과거 fixture의 원래 기한은 보존하고 재실행 때 현재시각으로 바꾸지 않습니다. 후속 기한은 선택값이며 필수 후속의 기한을 반드시 요구할지는 팀 정책 미정입니다.

| 현재 | 허용 전이 |
|---|---|
| OPEN | IN_PROGRESS / DONE / CANCELLED |
| IN_PROGRESS | DONE / CANCELLED |
| DONE / CANCELLED | 종료 상태로 고정, 수정/재개 금지 |

IN_PROGRESS/DONE에는 현재 유효한 소유 사용자와, 티켓 후속이면 현재 책임 회차의 인수가 필요합니다. CANCELLED는 CUSTOMER_WITHDREW/NO_LONGER_NEEDED/DUPLICATE/OTHER 중 취소 사유가 필수입니다. DELETE도 expected_revision과 cancellation_reason body를 받아 같은 취소 로직을 호출합니다. DONE에만 completed_at, CANCELLED에만 cancelled_at/취소 사유를 서버 UTC로 기록합니다. 같은 상태 전이는 409이며 상태 변경 자체의 멱등키는 이번 버전에 없습니다. 수정·상태·최소 감사는 원자 저장하며 원문을 감사 payload/로그로 복사하지 않습니다.

## 권한·인수와 관리자 큐

상담사 후속 접근은 기존 ticket_scope 전체와 후속 담당 팀=티켓 현재 팀을 요구합니다. 한 티켓의 유효 배정이 다른 티켓/고객 전체 권한을 부여하지 않습니다. 후속 owner_user_id에 옛 상담사 ID가 남았다고 그 사람의 접근을 허용하지 않습니다.

관리자 후속 큐는 **후속 owner_team_id의 활성 허용 팀**을 책임 범위로 사용합니다. 재문의가 ticket.team_id를 NULL로 만들어도 기존 후속은 이 책임 팀 큐에 남습니다. 현재 티켓이 다른 팀으로 이동한 뒤에도 기존 팀 관리자는 자신의 과거 책임 후속만 처리할 수 있습니다. 이것이 다른 팀의 현재 티켓·고객360 열람권을 부여하지는 않습니다. 팀 자체가 비활성이거나 scope를 회수하면 접근을 거부하므로 해당 팀의 책임 이전은 별도 관리 정책이 필요합니다.

재문의는 기존 후속을 완료/취소/삭제하지 않습니다. `cycle_no`는 원래 발생 회차, `responsibility_cycle_no`는 현재 인수 회차입니다. 모든 미완료 필수 후속은 원래 회차/팀/담당 유무와 무관하게 해당 티켓의 새 회차 해결도 막습니다. 새 배정 전에는 옛 상담사의 권한이 되살아나지 않습니다.

새 상담사가 같은 팀의 현재 유효 배정을 받으면 이전 회차 후속을 읽고 PATCH에서 owner_user_id를 자기 ID로 명시해 인수합니다. 이때 responsibility_cycle_no만 현재 회차로 갱신하고 원래 cycle_no/origin_team_id는 보존합니다. 인수 전 완료는 409 FOLLOWUP_TAKEOVER_REQUIRED입니다. 다른 팀으로 옮길 때는 원래 책임 팀과 새 팀을 모두 허용받은 관리자가 owner_team_id/owner_user_id를 변경해야 합니다. B의 실제 배정 엔진은 이 계약을 통합해야 하며 아직 구현하지 않았습니다.

## 해결 차단과 잠금 순서

후속 생성/변경은 user(NO KEY UPDATE) → ticket 또는 product → followup 순서입니다. 기존 고객 명령은 user → ticket → job → assignment, 자동 확정은 ticket → job 뒤 공통 후속 검사입니다. 후속 writer는 job을 잠그지 않으며 followup을 먼저 잡은 뒤 ticket을 잡지 않습니다. user의 NO KEY UPDATE는 감사 FK의 KEY SHARE와 충돌하는 불필요한 교착을 피하면서 동일 사용자의 멱등 명령을 직렬화합니다.

`app.resolution.assert_no_blocking_followups`가 모든 회차의 OPEN/IN_PROGRESS 필수 후속을 검사합니다. 자동 확정 함수는 ticket/job lock을 유지한 채 이를 호출합니다. B의 사람 응답에는 `lock_resolution_gate(... mode="HUMAN", human_user=...)`를 제공합니다. 현재 cycle/version·DB의 활성 상담사·유효 배정·HUMAN 경로와 같은 후속 검사를 하고 ticket lock을 caller 트랜잭션 끝까지 유지합니다. 이 함수는 사람 답변을 생성/발송하거나 해결 상태를 저장하지 않습니다.

후속 생성과 자동 해결이 경합하면 먼저 ticket lock을 얻어 commit한 명령만 성립합니다. 필수 후속 생성이 먼저면 자동 확정은 BLOCKING_FOLLOWUP, 자동 해결이 먼저면 새 필수 후속은 TICKET_ALREADY_FINISHED로 거부합니다. **마지막 후속 DONE/CANCELLED만으로 티켓을 자동 해결하지 않습니다.** 별도의 유효한 응답/해결 명령이 다시 공통 게이트를 통과해야 합니다. 임의 SQL writer까지 차단하는 DB trigger/RLS는 없으므로 B도 동일 잠금·검증 계약을 지켜야 합니다.

## 고객360 범위와 사실 정의

조회 목적은 ACTIVE_SUPPORT/FOLLOWUP_REVIEW, 관리자는 QUALITY_REVIEW도 허용합니다. 목적은 감사 사유이며 권한을 추가하지 않습니다. 고객 계정은 직원용 360을 사용할 수 없습니다. 고객이 없거나 허용 티켓이 0개이면 404입니다.

기준 집합은 기존 `ticket_scope`: 상담사는 **각 티켓마다** 현재 배정·팀·업무·회차·처리 중 상태를 모두 만족하는 티켓, 관리자는 현재 활성 허용 팀의 티켓입니다. 상담사가 예전에 맡았던 종료 티켓까지 자동 확장하지 않는 보수적인 제안입니다. 누적 건수·유형 분포·자동/사람 현황·미해결·반복·최근5건·현재 담당·후속과 원본 이력 페이지에 같은 집합을 적용합니다. 후속은 여기에 후속 자체 팀 scope까지 교집합을 취합니다. 관리자 책임 큐의 별도 권한으로 고객360을 확장하지 않습니다.

- 미해결은 RESOLVED/CANCELLED 이외 상태입니다. 최근5건과 미해결 최근5건을 반환하고 전체는 같은 범위의 페이지로 조회합니다.
- 반복은 `cycle_no>1`인 티켓 수와 `sum(cycle_no-1)` 추가 회차 수입니다. 메시지 수/문의 문장 중복을 반복 상담 수로 세지 않습니다.
- 자동/사람 수는 현재 공개 handling_mode 분포이며 성공률/KPI가 아닙니다.
- 현재 담당은 현재 회차·현재 팀·시작된 활성 배정이고 처리 중 상태일 때만 표시합니다. 종료 티켓에 남은 fixture 배정을 현재 담당으로 표시하지 않습니다.
- PostgreSQL은 인증 전부터 REPEATABLE READ를 설정합니다. 한 요청의 권한·집계·목록·후속은 같은 snapshot이며 as_of는 해당 DB 트랜잭션 시작 UTC입니다. 별도 요청 사이에는 권한 변경이 반영될 수 있습니다. SQLite는 개발용 쓰기 직렬화만 사용하며 PostgreSQL snapshot 검증으로 표현하지 않습니다.

## AI 담당 최소 계약

현재 반환하는 3줄은 허용된 건수·처리 방식·회차를 조합한 정형 사실 문장입니다. LLM 호출/생성 품질 평가나 요약 캐시 저장은 하지 않았습니다. `summary_contract.status=NOT_GENERATED`, version=customer360-v1입니다.

external_input은 허용 집합의 티켓/미해결/재문의/추가 회차/자동/사람 **정수 6개만** 포함합니다. 이름·이메일·고객/티켓 ID·원문·내부 메모·토큰은 넣지 않습니다. 최근5건의 ID/revision/cycle 출처는 별도 직원용 sources sidecar에 두며 외부 입력에 합치지 않습니다. 집계의 전체 출처는 같은 scope의 360/tickets 이력에서 확인합니다.

cache_fingerprint는 실제 principal/역할/정규화 팀 scope/목적/정책 버전과 허용된 티켓·후속·현재 배정의 증거를 해시합니다. 재문의·배정 종료/변경·허용 집합·후속 메모/상태/담당/버전이 바뀌면 무효화합니다. AI 담당은 캐시 hit 전에도 권한을 다시 확인하고 fingerprint가 같을 때만 재사용해야 합니다. 원시 내부 증거는 해시 입력으로만 사용하고 external_input으로 보내지 않습니다. 실제 LLM의 3줄 사실성·출처 대응·품질은 별도 통합 검증 대상입니다.

## migration과 복구

0001/0002는 수정하지 않고 0003을 추가했습니다. 원본 후속의 origin_team_id=owner_team_id, responsibility_cycle_no=cycle_no를 backfill하며 상태/원문/기한/승인/티켓 이력은 덮어쓰지 않습니다. seed는 신규 필드를 매핑하고 반복 시 기존 데이터/인수 결과를 보존합니다. 기존 잘못된 DONE/취소/기한 데이터가 있으면 CHECK 적용이 실패하므로 원본을 삭제하거나 임의 정상화하지 말고 검토해야 합니다.

3단계 당시 readiness는0003이었고 현재4단계 build는0004를 요구합니다. 3단계 생성/수정/상태 변경 감사나 멱등 기록이 있으면 이력을 잃는0002 downgrade를 거부하고 offline downgrade 생성도 거부합니다. 현재 release rollback은0004 호환 build를 사용합니다. Azure 생성·실제 배포·실제 B 통합은 실행하지 않았습니다.
