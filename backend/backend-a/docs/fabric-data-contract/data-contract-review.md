# 데이터 계약 항목별 검토

Fabric 연동을 위한 Backend A 구현 및 제약 검토입니다. **이미 적용된 정의는 유지하고, 미라벨의 NULL 의미·불만 확정 제약·감사 맥락 보완은 별도 수정 대상으로 권고합니다.** 필수 후속에 따른 해결 차단과 티켓 상태 강제는 다른 규칙이므로 분리해서 결정해야 합니다.

**검증 범위는 소스·제약 검토입니다. 아래의 수정 권고·제안 제약은 구현하거나 적용하지 않았습니다.** 함께 전달하는 audit 샘플은 이 협의 항목 전체의 수정 완료본이 아닙니다.

## 확인 기준

- 2026-11-04 로컬 `feature/backend-a`, HEAD `2af74b73eacb9e692e17b1ad166d35152085859d`, 소스 **0.11.0**, migration 파일 graph의 단일 head **0011**을 기준으로 확인했습니다. 적용되는 AGENTS.md는 발견되지 않았습니다. 검토에 사용한 audit 자료는 합성 샘플과 제안 계약입니다.
- 아래 소스 경로는 저장소의 `backend/backend-a/` 기준입니다. 모델·migration·CHECK·trigger·업무 writer의 **정의**를 확인한 것이며 실제 Azure DB에 적용됐다는 확인은 아닙니다. 이번에는 Azure·실제 DB에 접속하지 않았습니다.
- `11.docx` 본문 전체를 확인했습니다. 로컬의 `CS_Flow_AI_공식_프로젝트_기획서.docx`, `CS_Flow_AI_공식프로젝트기획서_VOC개정판_v4.1.docx`와 관련 기획 문서를 찾아봤지만, p.19·p.25의 상세 스키마·규칙이 있는 **정확한 원본은 확인하지 못했습니다.** 그 페이지의 요구는 11.docx의 인용 내용만 확인한 것으로 취급합니다. 다른 기획서를 해당 페이지 원본으로 대체하지 않았습니다.
- 저장소에 보관된 과거 전체 DDL·카탈로그 검토 기준은 **0.6.1/0006**입니다. 최신 Export projection은 별도 제안 스키마이며 최신 전체 DB DDL이 아닙니다. 이 검토에서도 과거 DDL을 다시 추출하거나 전체 DDL을 ZIP에 추가하지 않았습니다.

## 먼저 볼 결론

| 협의 항목 | 현재 A | 권고 |
|---|---|---|
| orders로 적힌 cycle_no | tickets에 BIGINT NOT NULL, 양수 CHECK 있음 | **유지 권고** — orders에 추가하지 않음 |
| 미라벨 is_complaint | tickets BOOLEAN NOT NULL, 앱 기본 false | **수정 권고** — 미라벨 NULL 계약을 채택한다면 nullable·기본값·writer를 함께 변경. 아직 미수정 |
| primary_issue와 라벨 버전·출처 타입 | 세 컬럼 모두 TEXT NULL, 길이·값 CHECK 없음 | **유지 권고** — text 유지, 업무 값·길이 규칙은 별도 합의 |
| label_status / human_verified / team_id | 이미 존재. 상태 문자열 제한·라벨 writer는 없음 | **협의 필요** — 라벨 상태·검증 주체·사건 귀속 정의 |
| 불만 true일 때 필수 3값 | 해당 tickets CHECK·라벨 API 검증 없음 | **수정 권고** — 행 단위 명시적 CHECK와 검증 writer 추가 |
| 필수 후속 | A 공통 gate가 해결 차단. 상태 강제 trigger는 없음 | **협의 필요** — 해결 차단 유지가 기본. 항상 FOLLOWUP_PENDING은 별도 결정 |
| 감사 | 공통 writer payload={} 및 결과 CHECK 있음 | **수정 권고** — trace·버전 등 허용 맥락 구조화. DB 개인정보 차단 완성으로 해석하지 않음 |
| int/varchar와 bigint/text | 범위·길이 제한이 다름 | **유지 권고** — 일괄 축소하지 않고 Spark 타입·검증을 맞춤 |

## 1 orders로 적힌 항목

### 1.1 cycle_no NOT NULL

**협의 항목**: cycle_no를 NOT NULL로 처리.

**현재 A 구현**: `app/models.py`의 orders에는 cycle_no와 is_complaint가 없습니다. 해당 두 컬럼은 tickets에 있습니다. tickets.cycle_no는 `BigInteger, nullable=False, default=1`이고, `app/model_constraints.py` 및 `migrations/versions/0001_initial_application_schema_from_.py`에 다음 제약이 이미 있습니다.

```sql
-- 현재 migration에 존재하는 제약
CONSTRAINT ck_tickets_version_cycle CHECK (version >= 1 AND cycle_no >= 1)
-- 별도로 tickets.cycle_no BIGINT NOT NULL
```

`app/services.py:submit_ticket`은 첫 회차를 모델 기본값 1로 생성하고, `app/ticket_commands.py:change_cycle`은 재문의·사람 요청 시 현재 cycle_no를 1 증가시킵니다. 모델의 default는 SQLAlchemy 기본값입니다. 직접 SQL writer가 DB 서버 DEFAULT도 있다고 가정해서는 안 됩니다.

**판단: 유지 권고.**

**이유**: tickets에 대한 NOT NULL·양수 조건은 이미 구현돼 있어 같은 제약을 다시 개발할 필요가 없습니다. orders에 회차를 새로 넣으면 주문과 상담 회차의 의미가 섞입니다.

**Fabric 주의**: 첨부 합성 schema의 tickets.cycle_no nullable=true는 A 정의와 다릅니다. A tickets 입력은 LongType의 non-NULL·1 이상으로 검증하되, **audit_events.cycle_no는 NULL 가능하므로 일괄 NOT NULL로 바꾸지 마세요.** 누락된 회차를 현재 티켓 값이나 1로 채우지 않고 원천 불일치로 표시하는 것이 기본 권고입니다.

### 1.2 is_complaint NULL과 NOT NULL

**협의 항목**: bool NULL과 boolean NOT NULL 차이 확인. 별도 요구에서는 미라벨이면 is_complaint=NULL을 허용.

**현재 A 구현**: tickets.is_complaint는 `Boolean, nullable=False, default=False`입니다. `label_status`의 앱 기본값은 UNLABELED이므로 신규 A 티켓은 **UNLABELED + false**로 시작합니다. 0001 migration도 BOOLEAN NOT NULL입니다. bool과 boolean은 같은 PostgreSQL 타입의 표기 차이이고, 실질 차이는 NULL 허용 여부입니다.

**판단: 수정 권고. 단, NULL 의미에 대한 팀 합의를 먼저 확정해야 합니다.**

**이유**: “미라벨=NULL”을 채택하면 현재 NOT NULL 정의·false 기본값과 충돌합니다. false를 무조건 비불만으로 집계하면 아직 판단하지 않은 문의까지 비불만으로 처리하게 됩니다.

**기본 권고와 질문**: NULL=미판정, true=불만 확정, false=비불만 확정으로 구분하는 방향을 권고합니다. 이를 채택할지, 어떤 label_status·라벨 확정 절차와 묶을지 결정해주세요. 채택하면 후속 migration에서 nullable 변경과 앱 기본값 제거/NULL 설정, 모든 라벨 writer·DTO·분석 입력을 함께 수정해야 합니다. 이번에는 변경하지 않았습니다.

**Fabric 주의**: 현재 6행 제안의 `is_complaint=false, label_status=UNLABELED`는 **현행 A 한계가 남아 있는 예시**입니다. 이를 확정 비불만으로 읽지 마세요. 이런 legacy 행은 미라벨/불명으로 분리하고, SQL COALESCE로 NULL을 false로 바꾸거나 근거 없이 기존 false를 일괄 NULL로 재작성하지 않는 것이 권고입니다. 이전 첨부의 합성 티켓 1,000행에는 true 460/false 540만 있지만, 이것이 미래 운영 NULL 계약의 합의를 대신하지 않습니다.

## 2 tickets 타입과 추가 컬럼

### 2.1 primary_issue와 voc_label_version 및 voc_label_source

**협의 항목**: varchar(24/32/16)와 text의 차이 검토.

**현재 A 구현**: 세 컬럼은 `app/models.py:tickets` 및 0001 migration에서 모두 **TEXT NULL**입니다. 길이 제한·primary_issue 값 목록·세 컬럼 조합을 검사하는 tickets CHECK가 없고, tickets 라벨 변경 API도 없습니다. `TicketCreate`는 order_id와 message만 받아 extra 필드를 거부합니다. 업무 생성 writer는 세 컬럼을 설정하지 않아 NULL로 시작하고, 합성 fixture importer `app/seed.py:seed_fixture`는 계약 필드를 가져옵니다.

| 컬럼 | 현재 용도와 NULL 의미 | 실제 허용·검증 경계 |
|---|---|---|
| primary_issue | 대표 불만 유형. NULL은 미확정/없음 등을 구분할 별도 상태가 필요 | tickets DB는 임의 text 허용. Gold API의 Issue는 아래 6코드만 허용 |
| voc_label_version | 라벨을 만든 규칙/분류 체계 버전. NULL은 버전 미기록 | tickets DB·라벨 API에 길이/목록 검증 없음. 버전의 생산 주체·불변성 계약 미구현 |
| voc_label_source | 라벨 생성 출처. NULL은 출처 미기록 | tickets DB에 enum 없음. 합성 자료의 SYNTHETIC을 운영 출처로 해석하면 안 됨 |

현재 **Gold 입력**인 `app/analytics_schemas.py:Issue`와 **VOC 개선 계획**의 `app/voc_models.py` issue CHECK는 `DELIVERY_DELAY, RETURN_PROCESS, REFUND_DELAY, DAMAGED, PAYMENT_ERROR, ACCOUNT_ERROR`를 허용합니다. 이 다른 경계의 제한이 tickets 원천 라벨에도 이미 적용됐다는 뜻은 아닙니다. 화면 표시명 “배송지연”의 제안 저장 코드는 `DELIVERY_DELAY`이며, 한글 표시명을 그대로 저장하거나 미확정 자유문장을 자동 매핑하지 않는 것이 권고입니다.

**판단: 물리 text는 유지 권고. 업무 코드·버전·출처의 허용 범위는 협의 필요.**

**이유**: text와 varchar는 모두 문자열로 전달할 수 있고 현재 A에는 varchar와 같은 길이 제한이 없습니다. 표기만 맞추려고 축소하면 기존의 긴 버전·출처 값이 실패하거나 잘릴 수 있으므로, 실제 허용 값과 최대 길이를 먼저 합의해야 합니다.

**Fabric 주의**: 우선 StringType으로 읽고 NULL을 보존해주세요. varchar 최대 길이가 필수인 소비 단계라면 초과 값을 잘라 넣지 말고 검증 실패/격리로 표시해야 합니다. 24/32/16을 운영 상한으로 채택할 경우 A의 후속 CHECK·API 검증·Fabric 검증에 같은 기준을 적용해야 하며, 이번 샘플이나 스키마에 그 제한을 새로 적용하지 않았습니다.

### 2.2 label_status와 human_verified 및 team_id

**협의 항목**: 추가 컬럼의 용도·허용 값·NULL·생성/갱신 주체 설명.

**현재 A 구현**:

| 컬럼 | 타입·NULL·앱 초기값 | 현재 의미와 쓰기 경계 |
|---|---|---|
| label_status | TEXT NOT NULL / UNLABELED | 라벨 처리 상태용. DB enum CHECK 없음. 현재 A 업무 writer에서 확인한 초기 상태는 UNLABELED. fixture에는 SYNTHETIC_EXPECTED가 있음. 합의된 운영 상태 전체 목록이나 상태 전이 API는 없음 |
| human_verified | BOOLEAN NOT NULL / false | 원천 라벨의 사람 검증 여부를 표현하기 위한 별도 플래그. true를 만드는 검증 절차·검증자/시각 저장 writer는 A에 없음. fixture 입력은 가능. false는 불만이 아니라는 뜻도, 라벨 확정이라는 뜻도 아님 |
| team_id | UUID NULL / 미지정 | 현재 티켓 처리·권한 범위에 쓰는 팀 FK. `fk_tickets_team_id_teams`는 팀 존재만 보장하고 활성·권한·과거 사건 귀속까지 보장하지 않음 |

신규 티켓은 `submit_ticket`에서 team_id를 지정하지 않습니다. `change_cycle`은 새 회차에 team_id를 NULL로 초기화합니다. `app/seed.py:seed_fixture`는 합성 assignments에서 마지막 팀을 가져오는 fixture 보정 경로이며 운영 사건 이력의 증거가 아닙니다. `app/exception_queue.py:record_queue_route`는 **queue_routes만** 기록하고 tickets.team_id·version·assignment를 바꾸지 않습니다. 실제 배정·처리 팀 갱신은 B writer 연동 계약에서 확인해야 하며 이번에는 B 구현·실행을 검증하지 않았습니다.

**판단: 컬럼 유지 권고. 라벨 상태·사람 검증·집계 귀속은 협의 필요.**

**이유**: 세 컬럼은 서로 다른 정보를 담고 있어 한 값으로 다른 의미를 대체할 수 없습니다. 특히 사람이 확인했다는 플래그만으로 불만 확정이나 AI 응답 정확성을 증명할 수 없고, 현재 팀 값으로 과거 사건의 담당 팀을 복원할 수도 없습니다.

**기본 권고와 질문**: UNLABELED과 실제 라벨 확정 상태의 코드·전이를 정하고, A/B/AI·RAG 중 누가 라벨을 검증해 저장할지 정해주세요. human_verified=true에는 어떤 검토자·시각·라벨 버전을 연결해야 하는지도 합의가 필요합니다. 현행 AI 품질 평가의 응답 표본·평가 revision과 이 원천 라벨 플래그는 별개로 유지하는 것이 권고입니다.

**Fabric 주의**: label_status가 non-NULL이라고 라벨 완료로 집계하지 마세요. SYNTHETIC_EXPECTED도 실제 사람 검증 완료를 뜻하지 않습니다. team_id=NULL은 미귀속으로 보존하고 임의 팀에 나누지 마세요. 현행0.11의 전향적 cycle/event 기록에 일부 팀 사실이 있어도 전체 과거 접촉의 귀속을 보증하지 않으며, 이번 audit projection에는 그 원천을 추가하지 않았습니다.

## 3 불만 확정 시 필수값

**협의 항목**: is_complaint=true이면 허용 primary_issue·complaint_first_at·voc_label_version 필수. 미라벨이면 is_complaint=NULL, 나머지도 NULL 허용.

**현재 A 구현**: 이 조합을 보장하는 tickets DB CHECK는 **없습니다**. 0001의 `ck_tickets_version_cycle`, status/requested_mode/resolution_mode/order_product/resolved_at 등의 CHECK는 다른 규칙입니다. 0002–0011 migration·trigger에도 이 라벨 조합 제약은 없습니다. 일반 티켓 API는 라벨 입력을 받지 않고, seed도 이 조합의 의미를 검증하지 않습니다. Gold API에서 허용 코드를 검증하는 것으로 원천 tickets의 무결성을 대신할 수 없습니다.

**판단: 수정 권고.**

**이유**: 현재는 true인데 세 값이 빠진 행도 tickets 정의상 막지 못합니다. 필수값과 허용 코드를 DB와 라벨 writer에서 함께 검증해야 하지만, 접촉 시각·라벨 버전의 실제 근거를 먼저 공급받아야 합니다.

**최소 수정안 — 미구현 제안**:

1. 1.2의 nullable/기본값 변경과 운영 label_status 계약을 먼저 합의합니다. 미라벨 초기값은 is_complaint=NULL, 근거 미제공 필드=NULL로 두는 방향을 권고합니다. 미라벨 중간 초안의 일부 필드를 허용할지는 별도 결정입니다.
2. 미래 additive migration에 아래와 같은 **명시적 non-NULL 검사**를 추가하고, 권한·ticket revision을 검사하는 라벨 저장 writer에서 같은 규칙을 검증합니다. 제약명은 가칭이며 현재 존재하지 않습니다.

```sql
-- 제안 전용 예시. 이번에는 생성/실행하지 않음
CONSTRAINT ck_tickets_complaint_required CHECK (
  is_complaint IS DISTINCT FROM TRUE
  OR (
    primary_issue IS NOT NULL
    AND primary_issue IN ('DELIVERY_DELAY','RETURN_PROCESS','REFUND_DELAY',
                          'DAMAGED','PAYMENT_ERROR','ACCOUNT_ERROR')
    AND complaint_first_at IS NOT NULL
    AND voc_label_version IS NOT NULL
    AND length(btrim(voc_label_version)) > 0
  )
)
```

위 식은 실제 운영에 적용할 확정 migration이 아니라 제약 검토용 예시입니다. `IN (...)`만 쓰고 non-NULL 검사를 빼면 SQL CHECK의 NULL 통과 규칙 때문에 필수값을 보장하지 못합니다. [PostgreSQL CHECK 설명](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS).

3. 기존 데이터는 먼저 누락·불명 상태를 분리해 확인합니다. 임의 primary_issue, created_at/audit 시각, 최신 라벨 버전으로 채우지 않습니다. 위반 행 처리·NOT VALID 사용 여부·후속 VALIDATE 시점은 근거와 운영 영향 확인 후 별도 설계해야 합니다.

**보장 범위**: 제안 CHECK도 행에 값이 있고 코드가 맞는지만 보장합니다. complaint_first_at이 실제 고객 접촉인지, 그 라벨 버전으로 판정했는지는 원천 참조·writer 검증 없이는 입증하지 못합니다. voc_label_source/human_verified를 true의 필수로 추가하는 것은 원문 요청 밖의 별도 합의입니다.

**Fabric 주의와 질문**: “배송지연”은 표시명이고 저장 코드는 DELIVERY_DELAY를 권고합니다. complaint_first_at이 불만 유형의 최초 접촉인지·티켓 최초 접수인지·이전 회차를 포함하는지, 실제 원천 메시지/채널이 무엇인지 정해주세요. audit.created_at이나 ticket.created_at을 자동 대입하지 마세요. 현재 제안 티켓 JSONL에는 complaint_first_at·voc_label_version/source·human_verified가 포함되지 않았으므로 **필수값 충족 검증에는 부족**합니다. 이번에는 검증된 projection bytes를 보존했고, 해당 컬럼 추가는 다음 projection 버전 협의가 필요합니다.

## 4 필수 후속과 FOLLOWUP_PENDING

**협의 항목**: blocks_resolution=true인 미완료 후속이 있으면 티켓 상태를 FOLLOWUP_PENDING으로 유지하는 DB 규칙.

**현재 A 구현**: `app/resolution.py:assert_no_blocking_followups`가 아래 조건을 검사해 `BLOCKING_FOLLOWUP`으로 해결을 거부합니다. `lock_resolution_gate`와 `app/finalization.py:commit_automatic_reply`가 이를 사용합니다. HTTP API가 아닌 내부 Python gate이며, B의 사람 응답 writer도 같은 잠금/gate 계약을 지켜야 합니다. 실제 B 연결 성공은 이번 검토에서 확인하지 않았습니다.

```text
ticket_id = 대상 티켓
AND blocks_resolution = true
AND followup status IN ('OPEN', 'IN_PROGRESS')
```

| 적용 대상 | 현재 보장 |
|---|---|
| 현재/과거 회차 | 회차 필터 없음. 과거 회차의 열린 필수 후속도 해결 차단 |
| 미인수·무효 담당 | 담당자/인수 여부로 blocker를 제외하지 않음. 인수 대기여도 차단 |
| DONE / CANCELLED | blocker에서 제외. 취소를 미완료로 계속 세지 않음 |
| 상품 대상 후속 | `ck_followup_actions_product_block`: `product_id IS NULL OR NOT blocks_resolution`. 상품 후속은 해결 차단 불가 |
| 종료 티켓 | `followups.validate_values`가 RESOLVED/CANCELLED에 새 필수 후속을 만들거나 필수로 바꾸는 것을 거부. 기존 행·직접 SQL까지 자동 정리하는 규칙은 아님 |
| 후속 수정·인수 | `followups.prepare_create/persist_create/mutate`에서 부모 ticket 잠금 후 action 잠금/쓰기. IN_PROGRESS/DONE은 유효 담당·현재 책임 회차 검사. CANCELLED에는 별도 취소 규칙 |
| 티켓 상태 | 필수 후속을 만들었다고 FOLLOWUP_PENDING으로 강제하지 않음. 마지막 후속 완료도 티켓 자동 해결/원래 상태 복원을 하지 않음 |

DB에는 후속의 target/state/cycle/completed/cancelled/product_block 등의 **행 단위** CHECK가 이미 있습니다. 근거는 `app/model_constraints.py`, `migrations/versions/0003_followups_and_customer360.py`입니다. 0008의 `csflow_voc_product_guard`와 `voc_product_action` trigger는 상품 개선 후속의 연결/blocks_resolution 변경을 보호하는 것으로, 모든 티켓을 FOLLOWUP_PENDING으로 강제하는 trigger가 아닙니다.

**판단: 협의 필요. 기본은 현행 해결 차단을 유지 권고.**

**이유**: 해결을 막는 것과 상태를 항상 FOLLOWUP_PENDING으로 바꾸는 것은 다른 업무 규칙입니다. 후자를 강제하면 아직 배정되지 않았거나 고객 답변을 기다리는 티켓의 상태·자동 처리 gate·B 동작까지 바뀝니다.

**기본 권고와 질문**: 기획 의도가 “필수 후속이 남으면 해결 불가”인지, OPEN/PROCESSING/WAITING_CUSTOMER/HANDOFF_PENDING까지 모두 FOLLOWUP_PENDING으로 바꾸는 것인지 확인해주세요. 우선 현재 gate를 유지하고 직접 DB 우회를 막아야 한다면, **RESOLVED 전이와 열린 필수 후속의 상호 모순을 거부하는 DB guard**를 별도 보완안으로 검토하는 것이 권고입니다. 이것도 현재 DB에 적용된 보장은 아닙니다.

항상 FOLLOWUP_PENDING이 최종 합의라면 단순 CHECK로 다른 테이블을 조회하는 식으로 구현할 수 없습니다. ticket·followup 양쪽 변경을 검증하는 trigger/필요시 지연 constraint trigger, 모든 writer의 ticket→followup 잠금 순서, 동시 생성/해결 경합을 함께 설계해야 합니다. 자동 상태 변경 시 ticket.version을 누가 언제 증가시키는지, job.expected_ticket_version·AI 확정 gate와 B 재시도에 미치는 영향, 마지막 후속 종료 뒤 상태 복원·취소 예외도 결정해야 합니다. **이번에는 trigger·writer를 구현하지 않았습니다.** [PostgreSQL의 테이블 간 CHECK 제한](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS).

**Fabric 주의**: 현재 tickets.status만으로 필수 후속 유무를 단정하지 마세요. ticket_ref에 연결된 OPEN/IN_PROGRESS·blocks_resolution=true를 별도로 확인하고, 이전 회차도 누락하지 않는 것이 현재 A gate와 일치합니다. 고객 회차·후속 원래 회차·책임 회차를 같은 값으로 덮어쓰지 마세요.

## 5 audit_events 기록 정책과 Export

**협의 항목**: 원문·전화·주소·이메일·토큰 기록 금지. 조회 사유·허용/거부·batch·trace·버전·사유코드 중심으로 기록 가능한지 확인.

**현재 A 구현**:

| 경계 | 확인한 보장과 한계 |
|---|---|
| 공통 writer | `app/audit.py:record`는 payload 인자를 받지 않고 `{}`만 기록. actor/action/target/ticket/cycle/result/reason/service의 정형 참조만 넣으며 원문·request body·헤더·예외 문구를 복사하지 않음 |
| 조회 사유·허용/거부 | customer360은 PurposeInput의 ACTIVE_SUPPORT/FOLLOWUP_REVIEW/QUALITY_REVIEW를 reason_code로 기록. 품질 자료 조회는 QUALITY_REVIEW. record 기본 result=SUCCESS, `record_denial`은 ACCESS_DENIED/DENIED와 오류 코드를 요청 rollback 후 별도 transaction으로 기록 |
| batch | `app/analytics_service.py:event`는 target_type=ANALYTICS_BATCH, target_id=batch UUID, service=검증된 서비스 identity로 기록. 별도 batch_id 컬럼이 있는 것은 아님 |
| trace·버전 | `app/main.py`의 request_id는 응답 X-Request-ID와 최소 로그에 쓰임. audit.record 인자/컬럼에 request_id·trace_id·ticket_version·rule_version은 없고 payload={}여서 감사 DB에 자동 연결되지 않음. cycle_no는 ticket revision이나 라벨 버전의 대체가 아님 |
| DB 제약 | event_id UUID PK, event_key TEXT UNIQUE, payload JSONB NOT NULL, result VARCHAR(16)와 `ck_audit_events_result`의 SUCCESS/DENIED/FAILURE 제한. reason_code VARCHAR(64). action/target_type은 임의 TEXT, reason도 전역 enum CHECK 없음 |
| 직접 쓰기 | 공통 helper는 입력 payload를 제한하지만 JSONB 자체는 object뿐 아니라 scalar/string도 저장 가능. DB의 payload 허용 키·민감정보 검출·전체 문자열 정책 trigger는 없음. seed fixture import/직접 SQL writer가 helper를 우회할 수 있음 |

`record_denial`은 감사 DB 장애 때 고정 운영 신호만 로깅합니다. 모든 장애·모든 직접 쓰기의 감사가 무조건 남는다고 보장하지 않습니다. 직접 SQL·운영 audit 내용을 이번에 읽지 않았으므로 민감정보가 실제 기록됐거나 없다고 단정하지 않습니다.

**판단: 기존 최소 writer 유지 + 감사 맥락 보완 수정 권고.**

**이유**: 현재 공통 writer는 원문을 복사하지 않지만, 필요한 trace·버전까지 연결해주는 구조는 아닙니다. result/reason_code와 JSONB 컬럼의 존재만으로 개인정보 금지 정책이나 추적성 요구 전체가 충족되지는 않습니다.

**최소 수정안 — 미구현 제안**: 조회 목적·action별 reason 허용값을 명시하고, request_id/trace_id·batch_id·ticket_revision·필요한 규칙 버전처럼 정말 필요한 정형 맥락만 선택 인자로 받는 공통 writer를 검토합니다. UUID/숫자/제한된 코드와 길이를 검증하고, 요청 헤더·자유문구·전체 body를 전달하지 않아야 합니다. 컬럼 추가와 JSONB allowlist 중 선택은 팀 결정 사항입니다. JSONB 방식을 택해도 object 타입·허용 키·값 타입을 검증하고 직접 쓰기 역할/권한을 통제하는 보완이 필요합니다. 이 정도로도 모든 문자열 속 개인정보를 DB가 완전히 판별한다고 보장할 수는 없습니다.

**Fabric 주의**: 원천 DB 기록 정책과 **Export 제한**은 별개입니다. 기존 audit Export projection은 event_ref/ticket_ref/cycle_no/action/result/reason_code/created_at의 **7필드만** 담고 payload·원본 식별자·actor·event_key를 제외합니다. batch/trace/버전 전체를 전달하는 파일이 아니며 이번에도 이를 늘리지 않았습니다. event_ref는 원천 event_id의 HMAC 가명으로 행 중복 확인용이고, 논리 접촉의 멱등키가 아닙니다.

첨부 합성 CUSTOMER_CONTACT는 현재 A 업무 producer가 생성하지 않습니다. CREATED/STATUS_CHANGED도 실제 업무 action과 임의 이름 변환하지 않습니다. 감사 created_at은 저장 시각이며 실제 접촉 시각이나 전체 사건 순서가 아닙니다. 실제 접촉이 필요하면 원천 메시지/채널의 발생 시각·안정적인 사건키·포함 범위를 별도 계약으로 받아야 하며, 감사 시각·문구에서 만들어내지 않습니다. 상세는 기존 [audit 비교 문서](audit-export-review.md)를 참고해주세요.

## 6 int 및 varchar와 bigint 및 text

**협의 항목**: 기획서 int/varchar(n)과 A bigint/text 차이 수정 검토.

**현재 A 구현**: orders.quantity/version, tickets.cycle_no/version 등은 BigInteger이고, amount는 Numeric(12,2)입니다. 일반 문자열은 Text, 일부 reason·새 기능 코드 컬럼은 String(n)과 별도 CHECK를 사용합니다. 따라서 A 전체를 “길이 제한 없음” 또는 “전부 varchar”로 요약할 수 없습니다. 11.docx 인용과 실제 컬럼별 정의를 대조해야 합니다.

**판단: 일괄 축소 없이 유지 권고. 제한과 업무 의미는 항목별 협의.**

**이유**: bigint를 int로 줄이면 값 범위가 줄고, text를 varchar로 줄이면 이전에 저장되던 긴 값이 실패할 수 있습니다. 타입 표기를 같게 만드는 것보다 값 범위·길이·NULL·코드 의미를 손실 없이 맞추는 것이 우선입니다.

| 구분 | 기본 권고 | Fabric 주의 |
|---|---|---|
| 그대로 매핑 가능한 차이 | bool/boolean→BooleanType, text/varchar→StringType. NULL 여부는 별도 유지 | 문자열로 읽는다고 varchar 길이 검증까지 수행되는 것은 아님 |
| 값 제한을 맞출 차이 | PG int4는 32bit IntegerType, int8/bigint는 64bit LongType. 축소 전 실제 범위 검사 | int4: -2^31…2^31-1, bigint: -2^63…2^63-1. 넘는 값을 잘라 넣거나 null로 조용히 바꾸지 않음 |
| 정밀도 제한 | Numeric(12,2)→DecimalType(12,2). 현 Export의 고정소수 문자열을 검증 후 명시적으로 변환 | Float/Double로 금액을 바꿔 정밀도를 잃지 않음. scale/자리수 초과는 격리 |
| 문자열 상한 | 24/32/16이 업무 상한이면 A 검증과 Fabric 검증에 같은 기준을 명시 | 임의 substring 금지. 코드 allowlist는 길이 제한만으로 대체 불가 |
| 시각 | timestamptz는 UTC 소수6자리 Export 제안 유지 | Spark timestamp 종류·세션 timezone을 명시. NULL·시각 정밀도·접촉 사건 의미를 보존 |
| 의미·NULL 합의 | 미라벨/비불만, 라벨 확정·사람 검증, 현재 팀/사건 당시 팀을 구분 | 타입 cast로 이 의미 차이가 해결되지 않음 |

첨부 합성 schema도 bigint→spark long, text→string, boolean→boolean, numeric(12,2)→decimal(12,2)로 선언돼 있습니다. **실제 Fabric runtime에 적용된 스키마나 옵션은 이번에 확인하지 않았습니다.** 위 Spark 기본 타입은 [Apache Spark 공식 자료](https://spark.apache.org/docs/latest/sql-ref-datatypes.html)로 확인했으며, 그 문서의 최신 버전이 Fabric 담당 Fabric runtime 버전과 같다는 뜻은 아닙니다.

## 계약 결정 사항과 담당 범위

| 결정할 내용 | 기본 권고 | 확인할 담당 |
|---|---|---|
| 미라벨 NULL·라벨 확정 상태·비불만의 의미 | NULL/true/false 분리. UNLABELED=false를 확정 비불만으로 집계하지 않음 | Fabric 담당·A·라벨 생산 담당·기획 책임자 |
| primary_issue 코드·버전/출처 상한·사람 검증 근거 | 현 6코드 기반 합의. text 유지 후 검증 규칙을 명시 | Fabric 담당·A·AI/RAG·필요시 B |
| complaint_first_at의 사건·회차·시각 원천 | 실제 접촉 근거 제공. ticket/audit 시각 대입 금지 | Fabric 담당·B·AI/RAG·A |
| 필수 후속 상태 강제 여부 | 우선 해결 차단 유지. DB 보완과 상태 강제를 분리 | 기획 책임자·A·B·Frontend |
| 감사 최소 맥락과 직접 DB writer 정책 | 공통 writer 확장·allowlist 검증. Export 기본7필드는 그대로 | A·B·보안/운영 담당·Fabric 담당 |
| 다음 Export projection과 Silver 승인 | 라벨 필수값을 담을 별도 버전·원본 Manifest·완전성 기준 합의 | A·Fabric 담당 |

**이미 충족**: tickets.cycle_no NOT NULL/양수, 후속의 행 단위 상태·회차·취소·상품 blocker 제약, A 공통 해결 gate, 공통 audit writer의 payload 미복사, 제한된 audit Export projection.

**실제 수정 권고**: 미라벨 NULL 계약 채택 시 nullable·기본값·writer 변경, true 라벨 필수값 CHECK·검증 writer, 정형 trace/버전 등 필요한 감사 맥락 보완. 모두 **이번에는 미구현**입니다.

**Fabric 담당과 결정할 것**: 라벨 상태/확정 주체·최초 접촉 시각·문자열 상한·항상 FOLLOWUP_PENDING인지·팀 귀속·차기 Export 컬럼과 Silver 승인 기준입니다. 이번 전달본은 기존 audit6행 제안을 보존한 계약 검토 자료이며, 실제 Export·운영 DB 변경·전체 기획 수정 완료본이 아닙니다.

## 보관 자료와 검증 범위

최초 계약 검토본은 기존 audit ZIP에 검토 문서와 README 읽는 순서를 추가한 자료입니다. 후속 문서 중립화에서는 원본 ZIP을 팀 체크아웃 밖의 별도 로컬 백업에 보존한 뒤 현재 전달 파일을 갱신했습니다. 기존 6개 JSONL·schema_contract.json·manifest.json bytes는 유지하며, 문서 변경에 따른 패키지 SHA256·건수·bytes는 별도 갱신 기록으로 구분합니다. 이전 검증 결과를 새로운 업무 검증으로 재표시하지 않습니다.

보관 ZIP 검증은 문서 참조·CRC/목록·원본과의 멤버별 bytes·Manifest 건수/bytes/SHA256 보존을 확인한 기록입니다. 이 기록에는 PostgreSQL·전체 업무 테스트·B Worker·Fabric·Azure·실제 Export 검증이 포함되지 않습니다.
