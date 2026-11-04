# DB → Blob → Fabric Silver 계약 초안

2026-11-04 보완: [audit 상세/첨부 차이](audit-export-review.md), [projection 전용 schema](samples/export-proposal/schema_contract.json), [Manifest](samples/export-proposal/manifest.json). 현재 예시는 공통 products/orders/tickets/followup_actions + audit_events와 customers 참조 보조 파일, **6파일/6행**이다. 기존4개 계약·고객 참조 파일은 byte 그대로다. 아래 전체 원천 목록은 향후 제안이고 전부 파일로 구현한 것이 아니다. 물리 DDL의0006 보관본과 현재 소스 검토0.11.0/0011을 구분한다.

## 구현 상태와 책임

**미구현:** 운영 A PostgreSQL을 읽고 Blob에 파일/manifest를 업로드하는 API·예약 추출기·CDC·인증·실패 복구 파이프라인은 없다. 이번 작업에서도 만들거나 실행하지 않았다. `scripts/export_openapi.py`는 OpenAPI 파일 생성기일 뿐 데이터 Export가 아니다. 외부 합성 fixture의 `code/export_contract.py`는 합성 JSON을 Lakehouse용 JSONL/fixture DDL로 바꾸는 오프라인 도구이며 운영 A DB→Blob Export가 아니다. 해당 파일을 실행하지 않았다.

**구현 확인:** A는 Fabric이 계산한 Gold 4개 mart를 별도 서비스 API로 받는다. source_input_hashes와 payload_checksums가 이미 있지만 원장 snapshot 추출·파일 업로드의 성공을 검증하지 않는다. 입력 해시가 존재한다는 사실만으로 운영 Export가 구현됐다고 해석하지 않는다.

이하 모두 **제안**이며 실제 추출·업로드 실행 명령이 아니다. 확정해야 할 책임자는 A/B/Fabric/PM이고 [질문](open-questions.md)에 우선순위를 정리했다.

## Silver 최소 입력과 제외

| A 물리 원천 | 제안 projection | 목적/제외 기준 |
|---|---|---|
| products | product_id, sku, category, active, created_at, updated_at | 제품 차원. name은 필요성 합의 전 제외 |
| customers | HMAC customer_ref, deleted_at | 중복/반복 고객 K. user_id/customer_key/display_name/profile_masked 제외 |
| orders | HMAC order_ref/customer_ref, product_id, quantity, order_status, payment_status, amount, placed_at, paid_at, version | 유료 판매 cohort/분모. order_number 제외. amount 필요성도 최소화 검토 |
| tickets | HMAC ticket_ref/customer_ref/order_ref, product_id, team_id, cycle_no, version, status, requested_mode, resolution_mode, category, is_complaint, primary_issue, complaint_first_at, label_status, voc_label_version/source, human_verified, first_replied_at/resolved_at/created_at/updated_at | 라벨·현재 상태·cohort. 원문/last_error_code 자유문장/issue_tags 무검사 복사 제외. enum allowlist만 허용 |
| assignments | HMAC assignment_ref/ticket_ref, cycle_no, team_id, assigned_at, ended_at, reason_code allowlist | 회차별 팀 이력. agent_id는 필요한 경우만 별도 staff 가명. 현재 scope와 과거 귀속을 구분 |
| queue_routes | HMAC ticket_ref, cycle_no, team_id, revision, recorded_at | 명시적 라우팅. 현재 행만 있어서 같은 회차 route 변경 전체 이력은 복원 불가 |
| messages | HMAC message_ref/ticket_ref, cycle_no, role, direction, final_reply, visibility, created_at | 재문의/contact 유도에 필요한 메타데이터만. body/approval_id/idempotency_key/updated_at 원문 복사 불필요 |
| followup_actions | HMAC action_ref/ticket_ref, product_id, cycle_no, responsibility_cycle_no, origin_team_id, owner_team_id, status, blocks_resolution, due_at, completed_at, cancelled_at, cancellation_reason, version, created_at, updated_at | 미해결 필수 조치. public_note/internal_note/kind 자유문구/담당 user ID 제외 |
| teams / team_categories | team_id, active, 허용 category | 명시 팀 차원·범위 검증. name은 필요성 확인 후 |
| audit_events | HMAC event_ref/ticket_ref, cycle_no, action/result/reason_code allowlist, created_at | 선택된 상태 이벤트의 보조 근거. actor_user_id/target_id/전체 payload 제외. CDC 대체 불가 |
| approvals | 가명 approval/suggestion/ticket 참조와 cycle/ticket_version/mode/decision/reviewed_at/expires_at만 필요 시 추가 | 승인 KPI 합의 전 기본 입력에서 제외. gate_snapshot 제외 |
| users / user_team_scopes / staff_permissions | 기본 제외 | 분석에 계정·권한 전체 필요 없음. 로그인명·password_hash 절대 제외. 분석 집계 scope와 직원 권한 파일을 혼합하지 않음 |
| ai_suggestions / knowledge_documents / automation_rules | 기본 제외 | draft/body/order_snapshot/evidence_refs/gate_results/conditions에 원문·비밀·개인정보 포함 가능. 정책·모델 버전만 별도 allowlist 필요 시 합의 |
| automation_jobs / automation_control(_history) | 기본 제외, 중지/실패 운영 KPI 합의 때 메타데이터만 | lease_token/lease_owner/error 자유문구 등 제외. 현재 작업 상태로 이벤트 완료 시간을 추정하지 않음 |
| shipments / returns | 배송·반품 KPI가 정해진 경우만 메타데이터 추가 | reason/eta_if_known 자유텍스트 제외 |
| analytics_* / idempotency_keys / alembic_version | 원장 Silver 기본 제외 | 이미 계산된 Gold를 다시 원천으로 순환 입력하지 않음. receipt 전체 payload·멱등 snapshot·key는 제외. head는 manifest 메타데이터로만 전달 |

**팀 합의 필요:** 현재 공통5종(+customers 보조)만으로 모든 VOC episode·기간별 미해결·팀 재배정을 계산할 수 있는지 확인해야 한다. ticket snapshot만으로 과거 회차 전체 상태를 복원하지 않는다. 0.11.0에 추가된 전향적 cycle/event 기록도 모든 과거 이력을 backfill하지 않으며 이번 Export에는 포함하지 않았다. messages에 primary_issue/product/order 당시 snapshot이 없다. 파생 customer_contacts/coverage/episodes는 이 제안의 실제 A 원천 파일이 아니다. 누락 근거를 만들거나 완전하다고 표시하지 않는다.

**audit 최소 선택 제안:** target_type=TICKET, result=SUCCESS, 전달 허용 tickets에 속하는 non-NULL ticket_id만 선택한다. event_ref/ticket_ref는 HMAC, cycle_no는 원천 NULL도 그대로 유지한다. action별 reason 허용값은 새 schema의 audit_selection을 따른다. payload/event_key/actor/target_id는 전부 제외한다. CUSTOMER_CONTACT는 현재 A 업무 producer가 만들지 않아 생성·추정·다른 action 이름 변환을 하지 않는다. created_at은 감사 저장 시각이며 접촉 시각이 아니다. 고객 파일은 customer_ref FK 보조이므로 유지하며 별도 registry 방식은 추후 합의한다.

## Snapshot, batch, 기준시각

**제안:** 첫 버전은 full snapshot만 지원 대상으로 합의한다. 현재 제품에 구현된 지원 방식은 **없음**이며 snapshot 제안이 곧 지원 완료는 아니다. 삭제·지연 commit을 안전하게 처리할 기반 없이 updated_at 단순 증분을 시작하지 않는다.

- export_batch_id: 원천 전체 snapshot 전달 단위 UUID. 기존 Gold manifest.batch_id와는 **다른 namespace와 생명주기**다.
- source_as_of: 동일 DB snapshot을 획득할 때 기록한 UTC 관측 기준시각. 단순 `WHERE updated_at<=source_as_of`가 아니며 commit을 모두 포함하는 완전성 보증/LSN도 아니다. 첫 snapshot 질의의 clock_timestamp와 snapshot 획득이 정확히 동시에 일어난다는 과도한 주장도 하지 않는다.
- export_schema_version: allowlist projection/직렬화/가명화 명세의 버전. 수정 예시는 proposed-silver-v1-audit-v1. 과거 합성 fixture의 A migration head=0006, 현재 소스의 파일 head0011, 첨부 합성 물리 schema_contract, Gold schema_version=analytics-v1과 서로 다르다. Manifest의 source_migration_head=0006은 예시의 역사적 basis이며 실제 최신 DB 조회 결과가 아니다.
- source_migration_head, snapshot_consistency, key_version, join_domain, scope 정의, 테이블별 inventory, extraction_started/completed_at, data_origin을 manifest에 명시한다. DB 내부 snapshot token은 서버 내부 조정용이며 공개 URL/자격정보로 취급하지 않는다.
- Fabric은 후속 Gold manifest의 source_input_hashes를 실제 입력 bytes 해시와 대응시킨다. 현재 5필드(orders/tickets/customer_contacts/followup_actions/coverage)로는 다중 파일/많은 원천 테이블의 lineage가 부족하다. 기존 필드에 임의 새 필드를 넣으면422이므로 별도 lineage 확장 버전 합의가 필요하다.

**제안:** 한 연결에서 `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY` 후 최초 SELECT로 snapshot을 고정하고 모든 allowlist projection을 그 트랜잭션 안에서 streaming한다. 단일 장기 트랜잭션의 VACUUM/보관 영향과 시간 제한은 운영 합의가 필요하다. `READ COMMITTED`에서 테이블마다 별도 SELECT하면 다른 snapshot이 섞인다.

**제안:** 병렬 연결이면 coordinator의 같은 트랜잭션에서 `pg_export_snapshot()`을 만들고 열어 둔다. 각 worker는 REPEATABLE READ/READ ONLY로 BEGIN한 뒤 **첫 데이터 query 전에** `SET TRANSACTION SNAPSHOT`으로 그 token을 import한다. 각 worker의 snapshot 적용을 확인하기 전에 coordinator를 끝내지 않는다. 실패·재접속은 원래 snapshot을 보장하지 않으므로 새 export_batch_id로 전체 재시작한다. 임의 연결별 now()만 맞추는 것은 동일 snapshot이 아니다. 현재 코드에 이 추출 조정기는 없다. [Snapshot 동기화](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION), [SET TRANSACTION](https://www.postgresql.org/docs/16/sql-set-transaction.html).

## 파일 형식·정렬·manifest 게시

**제안:** UTF-8, BOM 없음, LF(0x0A), 각 행 compact JSON 객체 1개와 마지막 LF를 사용한다. 빈 파일은 0bytes/0행이다. 문자열 내부 개행은 JSON escape이며 원문을 허용하는 우회가 아니다. nested JSON은 object/array 그대로이며 합성 fixture의 double-encoded JSON 문자열과 다르다.

**제안:** JSON key는 Unicode codepoint 순 정렬, ensure_ascii=false, 공백 없음, NaN/Infinity 거부. timestamp는 UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`(6자리), date는 YYYY-MM-DD, NULL은 JSON null(빈 문자열/0/문자열 null 아님), UUID는 소문자 하이픈 문자열, bigint는 JSON 정수(소비자는64bit로 파싱), numeric(p,s)는 고정소수 문자열로 scale 유지, double은 finite JSON number로 한다. 이 Export wire 제안은 Gold의 Decimal trailing-zero 제거 canonical과 다르며 해시를 혼용하지 않는다.

**제안:** 테이블 PK별 안정 정렬, 복합 PK는 선언 컬럼 순 tuple. 문자열 참조는 codepoint 순, 원본 숫자 PK는 숫자 순을 사용한다. 파일 분할은 최대100,000행 또는64MiB 중 먼저 도달한 완전한 행 경계, 파일명 part-00001.jsonl부터 연속 번호. 이는 개발 기본 제안이며 실제 부하·소수집단 노출·전송 정책 합의 전 확정하지 않는다.

**제안:** manifest 파일별 relative object_key, row_count, byte_count, sha256, PK min/max(식별자 노출 허용 범위 내), projection/version을 기록한다. SHA256 대상은 **업로드할 정확한 UTF-8 파일 bytes 전체(최종 LF 포함), 비압축**다. gzip을 나중에 지원하면 압축 bytes 해시와 논리 bytes 해시를 따로 명시한다. Gold payload_checksums는 PK 정렬된 JSON 배열의 canonical hash여서 JSONL 파일 bytes 해시와 다르다. manifest 자체 hash는 외부 commit marker에 두거나 자기 해시 필드를 제외하는 명세를 별도 정하며 자기참조 해시를 만들지 않는다.

**제안:** 배치별 고유 prefix에 모든 part 업로드 → bytes/hash/count/목록 검증 → manifest를 **마지막** 조건부 신규 생성한다. manifest가 없거나 파일 일부가 없으면 소비하지 않는다. object listing만으로 완성 판단하지 않는다. 완성 manifest는 불변이며 임의 URL/서버 파일 경로를 읽게 하지 않는다. 소비자도 허용 container/prefix/파일명만 처리한다. Blob 업로드·조건부 쓰기·lease 구현/실행은 이번 범위 밖이다.

## 재시도·삭제·스키마 진화

**제안:** 같은 export_batch_id와 같은 exact bytes는 멱등 재시도, 같은 ID 다른 파일/manifest는 충돌이다. 미완성 prefix는 일정 후 정리 대상으로만 분류하며 현재 A dry-run이 해당 Blob을 검사/삭제한다고 주장하지 않는다. 전체 성공 확인 전 watermark를 전진시키지 않는다. part 실패 시 소비 batch를 완료로 표시하지 않는다.

**제안:** full snapshot의 부재를 삭제로 해석하려면 동일 source/scope·완전한 테이블 coverage·전체 성공 manifest가 전제다. 제한 팀 snapshot에서 사라진 행은 삭제가 아니라 scope 변화일 수 있다. customers.deleted_at은 존재하지만 모든 테이블에 soft-delete 시각이 있는 것은 아니다. incremental tombstone/commit LSN/operation envelope는 **미구현**이고 audit로 대체할 수 없다. 미래 삭제나 보관은 별도 승인·실행 직전 재검증이 필요하다.

**제안:** nullable 추가 등 호환 변경도 소비자 합의와 새 manifest 버전으로 명시한다. rename/type/Enum 의미 변경·HMAC 규격 변경은 breaking 버전이다. 모르는 버전/필드를 조용히 버리지 말고 quarantine 후 이전 성공을 유지한다. 기존 업무 migration을 Export 때문에 소급 수정하지 않는다.

## HMAC과 JSON 개인정보

**미구현 / 제안:** 분석 customer_ref는 HMAC-SHA256 가명이다. **익명화가 아니다.** 현 customers.customer_key는 기존 fixture/seed 값이며 A가 새 운영 HMAC을 계산·회전하는 구현은 없다. 값이64hex라는 이유로 검증된 HMAC이라고 주장하지 않는다. 이메일·이름으로 새로운 customer키를 추정하지 않는다.

**제안:** 원본 ID는 PostgreSQL UUID를 파싱한 canonical lowercase 하이픈 형식으로 정규화한다. customer 입력 bytes는 UTF-8 `csflow|customer|v1|<join_domain>|<canonical_uuid>`이며 HMAC key는 별도 비밀 저장소의 버전 있는 무작위256bit 이상 key다. 출력은 `key_version`과64자리 lowercase hex이다. order/ticket/followup/event는 domain label을 분리해 재사용 ID 충돌을 막는다. timestamp·공백·이메일 lowercasing을 고객키 규칙에 섞지 않는다. 샘플 키는 공개 합성 전용이며 운영에 사용하지 않는다.

**팀 합의 필요:** 가상 기업 전체의 restricted Silver에서 여러 팀 중복 K/episode를 합치려면 승인된 공통 join_domain/key가 필요하다. 팀 경계마다 다른 key면 팀 간 조인이 불가능하며 팀별 K를 합해 전체 K로 대체할 수 없다. 반대로 공통 key는 팀 간 연결 가능성을 만들므로 최소 접근·조인 목적·재식별 위험을 합의해야 한다. 팀 제한 전달본에는 별도 domain을 쓰고 전역 조인을 허용하지 않는 제안이다. key rotation 시 dual-key/bridge도 개인정보 처리이므로 기간·접근/삭제 정책을 합의한다. 키는 manifest·Git·로그에 넣지 않는다.

**제안:** 원문·이메일·login_name·password_hash·JWT/서비스 키·lease_token·주소/전화·profile_masked·order_number·raw prompt·internal/public note·blob_path·connection 문자열을 제외한다. public 또는 masked라는 이름만으로 분석 공개 가능 판정하지 않는다. JSONB는 재귀 allowlist projection만 허용하고 알려지지 않은 nested key를 폐기/격리한다. audit.payload 기본 `{}`와 과거 fixture payload를 구분한다. followup에는 JSONB 메모가 아니라 text 메모가 있고 두 메모 모두 제외한다. approval gate_snapshot/AI snapshot/receipt 전체를 그대로 전송하지 않는다. Gold에는 고객/주문/티켓/이벤트 가명키·상담 원문도 넣지 않는다. 제품·팀 범위·집계·정형 점수 근거만 반환하는 기존 Submission allowlist를 유지한다.

## 완전성 플래그

**구현 확인:** Gold metrics.sales_complete/quality_ok/complaints_complete/episode_state_complete는 bool 필수다. sales_complete=false면 DATA_MISSING, 나머지 품질flag가 false면 QUALITY_BLOCKED를 검증한다. S는 `GLOBAL_PRODUCT_PAID_28D`로 같은 상품은 모든 scope에 같은 판매 분모다. A는 원장으로 플래그 진위를 재검증하지 않는다. config의 고정 시각과 fixture coverage는 실제 현재 운영 완전성 증거가 아니다.

**제안:** Export manifest의 completeness는 제품·기간·원천별 `true/false/unknown`, 관측시각, 검사 규칙/근거와 누락 원천을 표현한다. unknown은 true가 아니다. 현재 Gold bool 모델은 unknown을 표현하지 못하므로 false+별도 원천 sidecar 또는 새 계약 버전을 합의한다. 허용되지 않은 completeness_reason 같은 필드를 기존 Submission에 임의 추가하지 않는다. 최근/직전/판매창과 history_start의 coverage, 지연 수신 grace·삭제·재문의 상태 재구성 가능성을 확인한 경우에만 true로 올린다.
