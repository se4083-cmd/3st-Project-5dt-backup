# VOC 상품 개선 조치·계획 이력 (0.8.0 / 0008)

로컬 구현 계약이다. 개선 업무 완료와 효과 입증을 구분한다. 실제 Fabric 효과 수신·저장·조회, 계산, Export, 화면, 스케줄러는 구현하지 않았다. 기존 analytics-v1 wire·게시 및 Backend B 실행 계약은 변경하지 않았다.

## 저장 경계

- `followup_actions`가 상품·담당 팀/ADMIN 담당자·상태·기한·업무 revision의 정본이다. 기존 일반 상품 후속은 자동 분류하지 않는다. 상품 후속 담당은 활성 ADMIN 또는 팀 대기이며 AGENT로 확대하지 않는다.
- `voc_improvement_profiles`: action당 1개, 상품 FK, 현재 plan revision, 등록자/등록 시각. 티켓 후속·상품 불일치·blocks_resolution=true는 금지한다. PG trigger도 부모 대상 변경을 차단한다.
- `voc_improvement_plan_revisions`: 문제 유형·개선 내용·실제 시행일·비교창·발견 batch/scope·등록 당시 담당 팀·변경 사유·작성자. `(action_id,revision)` PK. 과거 계획은 수정/삭제하지 않는다.
- `voc_improvement_plan_teams`: 각 계획의 고정 비교 팀 집합. 팀 FK 및 계획 복합 FK. 변경은 새 계획으로만 수행한다.
- `voc_improvement_ticket_links`: action/ticket 복합 PK와 역방향 인덱스. 원문·고객·주문 정보를 복제하지 않는다.
- `voc_improvement_receipts`: 사용자/key PK, CREATE/PLAN/LINK CHECK, 요청 hash, profile·plan·선택 ticket FK, 최소 결과만 저장한다. 요청 본문·토큰·개선 텍스트는 receipt/감사 payload로 복제하지 않는다. 기존 고정 `idempotency_keys`는 변경하지 않는다.

새 후속의 검증·저장은 `followups.prepare_create` / `persist_create`를 재사용한다. 기존 API만 기존 FOLLOWUP_CREATE receipt를 생성한다. VOC wrapper는 VOC receipt만 생성하며 후속+profile+계획/비교팀+감사+receipt를 같은 외부 transaction에서 commit한다. 서비스 내부 savepoint 실패도 전체 명령을 rollback한다. HTTP API를 내부 호출하지 않는다.

## 권한·조회

모든 VOC 경로는 **현재 활성 ADMIN + 명시 VOC_IMPROVEMENT_MANAGE + 현재 활성 팀 scope**가 필요하다. CUSTOMER/AGENT와 grant 없는 ADMIN은403이다. capability는 `/api/v1/staff/capabilities`에서 확인한다. migration은 허용값만 추가하고 실제 계정에는 부여하지 않는다.

조치 접근은 현재 followup.owner_team_id로 판단한다. 범위 밖 객체는 존재 여부와 무관하게404이며, 목록에는 나타나지 않는다. 상품 전사 조회 권한이나 다른 팀의 티켓 접근 권한을 새로 만들지 않는다. 담당·상태·인수·취소는 기존 followup API의 권한과 규칙을 그대로 적용한다.

계획 내용은 비교 팀 **전부**와 owner_team_id_snapshot에 현재 권한이 있을 때만 노출한다. 담당 팀 변경으로 과거 팀 권한이 생기지 않는다. 현재 조치는 보이더라도 계획 권한이 없으면 `current_plan=null`, `plan_access=COMPARISON_SCOPE_DENIED`, `plan_refresh_required=true`이고 해당 이력·팀 ID·batch 참조·숨긴 이력 건수를 반환하지 않는다. 권한이 있어도 담당 팀 snapshot이 현재와 다르면 재확인을 표시한다. 새 허용 범위의 계획을 추가해 재확인할 수 있다. 이전 계획은 그대로 남는다.

문의 연결 시 조치/문의 각각의 현재 scope, 정확한 products UUID 일치, 현재 업무/계획 revision을 검사한다. product_id가 NULL이거나 다른 상품이면409다. 연결 조회도 현재 티켓 권한과 상품 일치를 재검사하며, 권한 밖 연결의 ID·건수를 반환하지 않는다. 권한 있는 연결만 제한된 페이지로 반환한다.

## API

기본 prefix는 `/api/v1/staff/voc-improvements`다. 세 POST 모두 `Authorization: Bearer <사용자 토큰>` 및 `Idempotency-Key`가 필요하다. key는8–128자 영문/숫자/`._:-`다. 실제 토큰은 문서에 저장하지 않는다.

| 메서드·경로 | 계약 |
|---|---|
| POST 기본 경로 | 신규 product followup+profile+첫 plan, 또는 existing_action_id 등록. 최초201/replay200 |
| GET 기본 경로 | product_id/status 선택 필터, limit 기본20/최대100, cursor. created_at DESC/action_id DESC 정렬. items/next_cursor |
| GET `/{action_id}` | 현재 후속·현재 계획·효과 availability 및 허용된 이력/문의 페이지 |
| POST `/{action_id}/plans` | full plan snapshot 추가. expected_action_revision/expected_plan_revision 및 사유 필수. 최초201/replay200 |
| POST `/{action_id}/tickets` | ticket_id와 두 expected revision. 같은 링크는 추가 복제하지 않음. 최초201/replay200 |

상세 이력은 `plan_limit`(1–100, 기본20), `plan_before_revision`(exclusive)와 `next_plan_before_revision`을 사용한다. 문의는 `ticket_limit`(1–100, 기본20), `ticket_cursor`, `next_ticket_cursor`이며 linked_at DESC/ticket_id DESC이다. 목록과 상세 인증·scope·데이터는 하나의 REPEATABLE READ snapshot에서 조회한다. 전체/숨긴 연결 수는 제공하지 않는다. 필터가 바뀌면 cursor를 버린다. 유효 범위에 데이터가 없으면 빈 목록이다.

### 신규 생성 예시

UUID는 설명용이며 실행 중 조회한 상품·팀·허용 ADMIN ID를 사용한다. 개인정보·상담 원문은 업무 텍스트에 넣지 않는다. 아래는 시행 전 계획이다.

```json
{
  "followup": {
    "product_id": "11111111-1111-4111-8111-111111111111",
    "owner_team_id": "22222222-2222-4222-8222-222222222222",
    "owner_user_id": null,
    "kind": "PRODUCT_IMPROVEMENT",
    "blocks_resolution": false
  },
  "plan": {
    "issue_code": "DAMAGED",
    "improvement_text": "포장 보강 및 출고 점검 절차 개선",
    "comparison_team_ids": ["22222222-2222-4222-8222-222222222222"],
    "change_reason": "위험 상품 검토 후 첫 계획"
  }
}
```

```json
{
  "action_id": "33333333-3333-4333-8333-333333333333",
  "action_revision": 1,
  "plan_revision": 1,
  "ticket_id": null
}
```

기존 등록은 followup 대신 `existing_action_id`, `expected_action_revision`, `plan`을 보낸다. 열려 있는 일반 상품 후속만 등록 가능하며, 기존 후속 필드/revision은 바꾸지 않는다. 이미 profile이 있으면409 VOC_PROFILE_ALREADY_EXISTS다. 종료 후 처음 등록은409 FOLLOWUP_TERMINAL이며 종료 후속을 되살리지 않는다.

### 시행 확인·계획 추가 예시

`POST /33333333-3333-4333-8333-333333333333/plans`:

```json
{
  "expected_action_revision": 1,
  "expected_plan_revision": 1,
  "issue_code": "DAMAGED",
  "improvement_text": "포장 보강 및 출고 점검 절차 개선",
  "implemented_at": "2026-11-01T00:00:00Z",
  "before_start": "2026-10-18T00:00:00Z",
  "before_end": "2026-11-01T00:00:00Z",
  "after_start": "2026-11-01T00:00:00Z",
  "after_end": "2026-11-15T00:00:00Z",
  "comparison_team_ids": ["22222222-2222-4222-8222-222222222222"],
  "change_reason": "실제 시행 시각 확인"
}
```

응답은 action_revision=1, plan_revision=2다. 계획 추가/연결은 followup revision을 올리지 않는다. 담당·상태 수정은 기존 후속이 revision을 올린다. 클라이언트는 상세에서 읽은 두 revision을 보낸다. 새 계획은 PATCH가 아니라 full snapshot이므로 생략한 optional 값은 NULL이다.

선택 출처는 `source_batch_id`/`source_scope_key`를 함께 보낸다. 기존 게시 resolver로 SUCCEEDED/검증된 수신 batch 및 비교 팀 **exact-set** scope와 정확한 scope_key를 검증한다. 해당 상품은 manifest.product_ids에 있어야 한다. 현재 pointer/현재 TOP10 포함 여부는 조건이 아니다. 게시가 교체돼도 원래 batch 참조는 유지한다. 게시된 Gold 자료를 참조했다는 사실은 이 조치의 효과 결과가 있다는 뜻이 아니다.

문제 유형은 현재 VOC allowlist: DELIVERY_DELAY, RETURN_PROCESS, REFUND_DELAY, DAMAGED, PAYMENT_ERROR, ACCOUNT_ERROR다. 미합의 자유 taxonomy를 추측해 추가하지 않았다. 개선 내용 최대4,000자, 변경 사유 최대1,000자이며 공백만 허용하지 않는다.

### 연결 예시

```json
{
  "ticket_id": "44444444-4444-4444-8444-444444444444",
  "expected_action_revision": 1,
  "expected_plan_revision": 2
}
```

응답 receipt에 해당 ticket_id가 들어가며 연결 중복 행은 만들지 않는다. 이 receipt도 재요청 때 현재 양쪽 권한을 검사한다.

## 시행일·기간·종료 후 정정

- 시행일과 비교창을 모두 비운 계획을 허용한다. 시행일만 저장하는 것도 가능하다. 실제 시행일은 미래일 수 없으며 completed_at/due_at으로 추정하지 않는다.
- 비교창 네 경계는 모두 NULL 또는 전부 값이다. 창이 있으면 시행일이 필요하다. aware 시각을 UTC로 정규화하고 `[start,end)`를 사용한다.
- `before_start < before_end <= implemented_at <= after_start < after_end`, 양쪽 길이가 같아야 한다. 중간 제외 구간은 명시한 경계 그대로 보존한다. 미래 after_end는 예정 관찰창이므로 가능하며 미래 implemented_at과 구분한다.
- 14×24시간은 **편집 가능한 입력 제안**일 뿐 서버 기본 생성/자정 반올림/팀 합의 정의가 아니다. 일별 원천으로 임의 시간 경계를 계산할 수 있는지는 Fabric 합의 전 미확인이다.
- 기존 due_at은 업무 기한이며 실제 시행일이나 비교창이 아니다. 예정 시행일 전용 필드는 이번에 추가하지 않았다. DONE은 업무 완료이고 효과 입증이 아니다.
- OPEN/IN_PROGRESS는 일반 새 계획(correction=false). DONE/CANCELLED는 `correction=true`와 비어 있지 않은 사유를 요구하는 ADMIN 정정만 허용한다. 동일 plans 경로의 이 명시적 분기만 사용한다. 종료 정정은 시행일/네 경계와 사유만 바꿀 수 있다. 문제 유형·개선 내용·비교 팀·출처를 바꾸는 업무 재계획은 거부한다. 과거 계획 권한도 필요하다. 후속 상태·담당·완료일·revision은 바꾸지 않는다.
- 이번 최소 정책에서 비교 팀은 현재 담당 팀을 포함해야 한다. 팀 변경 후 계획 재확인이 필요하다. 종료 후 담당 팀 변경은 기존 후속 정책상 허용되지 않는다.

## 멱등·동시성·오류

사용자별 VOC receipt namespace 안에서 같은 key/동일 검증 본문은 **원래 결과**(200, Idempotency-Replayed=true), 다른 본문/경로/operation은409 IDEMPOTENCY_CONFLICT다. 팀 집합 정렬과 계획 UTC 정규화 후 hash를 계산한다. 새로운 비교창이 미래 시행일인지 등의 검사는 새 명령에 적용하고, 이미 성공한 동일 재시도는 원래 결과를 반환한다. 재시도도 역할/capability/현재 조치·원래 계획·선택 티켓 권한을 재검사한다. 권한 회수 후 과거 receipt로 정보에 접근할 수 없다.

actor 잠금으로 같은 사용자의 요청/key를 직렬화하고 product→followup 잠금 및 두 expected revision으로 서로 다른 사용자의 변경도 검사한다. 연결은 actor→ticket→product→followup 순서다. 저장/감사/receipt 중 실패하면 외부 transaction 전체가 rollback한다. lock timeout 등 DB503은 같은 key·같은 body로 재시도하고409 revision 충돌은 상세를 새로 읽어 사용자의 변경 의도를 확인한다. 충돌 요청에 key를 재사용해 내용을 바꾸지 않는다.

| 응답 | 주요 코드 |
|---|---|
| 401/403 | INVALID_CREDENTIALS / EXPLICIT_PERMISSION_REQUIRED |
| 404 | 권한 밖/없는 action·ticket는 RESOURCE_NOT_FOUND, PUBLISHED_BATCH_NOT_FOUND |
| 409 | VOC_PROFILE_ALREADY_EXISTS, VOC_PRODUCT_FOLLOWUP_REQUIRED, VOC_TICKET_PRODUCT_MISMATCH, FOLLOWUP_REVISION_CONFLICT, VOC_PLAN_REVISION_CONFLICT, FOLLOWUP_TERMINAL, VOC_TERMINAL_CORRECTION_REQUIRED, VOC_NOT_TERMINAL, VOC_CORRECTION_FACTS_ONLY, IDEMPOTENCY_CONFLICT |
| 422 | VALIDATION_ERROR, VOC_IMPLEMENTED_AT_IN_FUTURE, VOC_OWNER_TEAM_OUTSIDE_COMPARISON, VOC_SOURCE_EXACT_SCOPE_REQUIRED, VOC_SOURCE_PRODUCT_NOT_PROVIDED, 기존 FOLLOWUP_DUE_IN_PAST |
| 503 | DATABASE_UNAVAILABLE. 부분 성공으로 처리하지 않음 |

각 요청의 X-Request-ID로 오류를 연결한다. 감사는 actor/action/target 등 최소 메타데이터만 남긴다. 입력 길이 제한을 개인정보 탐지 성공으로 표현하지 않는다.

## 분석 대기와 보관

상세/목록의 analysis는 항상 다음과 같다. after_end가 지나도 바뀌지 않으며 Fabric 결과가 없는 것을 관측0/효과 성공으로 바꾸지 않는다.

```json
{"availability":"UNAVAILABLE","reason":"EFFECT_INTEGRATION_NOT_IMPLEMENTED","metrics":null}
```

0008은5개 VOC 테이블과 FK/PK/CHECK/조회·역참조 인덱스, capability 허용값, PG 불변 이력/상품 대상 보호 trigger를 추가한다. 기존0001–0007과 업무/grant는 보존한다. history/grant/audit가 있으면 downgrade를 거부한다. readiness는0008을 요구한다. 실행 계정 grant나 Azure 적용은 이번에 수행하지 않았다.

retention dry-run은 연결 티켓·상품 후속·출처 batch의 새 참조를 보호 사유로 표시하고 VOC 테이블 자체를 workflow history로 보호한다. TEAM 검토는 다른 비교 팀/책임 범위가 섞인 티켓을 제외하며, 독립 VOC 이력 전체에 대해선 UNSUPPORTED_TEAM_SCOPE/null 건수를 사용한다. GLOBAL도 실삭제 후보로 승인하지 않는다. 계획/receipt 보존 정책·legal hold·외부 Fabric/Blob은 별도 합의 대상이다. 실삭제는 없다.

## Frontend·Fabric 인수

1. capabilities의 VOC_IMPROVEMENT_MANAGE로 ADMIN 진입을 제어한다. 현재 허용 팀과 기존 후속 담당자 규칙으로 입력한다. 일반 상품 후속 목록과 개선 목록을 구분한다.
2. 생성 receipt로 상세를 GET한다. followup과 plan revision을 따로 보관하고 재요청에는 같은 key/body를 유지한다. 담당/상태 변경 뒤 상세를 다시 읽는다.
3. plan_refresh_required와 plan_access를 표시하고 숨긴 이력/문의 수를 추측하지 않는다. DONE 표시는 ‘개선 업무 완료’다. analysis는 ‘효과 분석 연동 준비 중’으로 표시한다.
4. 주현님과 문의 단위(ticket/episode), cohort·분자/분모(주문/수량/판매 없음), 14일 등 동일 기간 및 지연/일별 경계, canonical 상품 UUID/매핑 버전, 고정 비교 팀과 역사 귀속, 전사 판매와 부분 팀 분모, coverage/저표본/중첩/인과 해석을 합의해야 한다.
5. 실제 효과 mart 수신·게시·조회 계약은 아직 없다. 기존 analytics-v1 wire에 새 효과 필드를 보내지 않는다. Export·Fabric 실행·실제 Frontend 화면 연결은 별도 작업이다.

실제 실행 기록은 [로컬 검증](evidence/voc-local/README.md)을 따른다.
