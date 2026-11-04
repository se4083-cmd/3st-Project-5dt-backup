# 기존 합성 schema_contract.json과 실제 A DB 차이

**구현 확인:** 로컬 원본 reference/fixture/schema_contract.json은 27항목이며 [원본 메타데이터 사본](fixture-schema-contract.original.json)을 제공한다. 기존 docs/fixture-schema-contract.json은 그중 PK가 있는22항목만 뽑은 사본으로 내용이 같지만 전체 파일의 SHA256은 다르다. 입력 계약은 27항목: PK가 있는 fixture 22테이블 + PK가 없는 파생 5종이다. 실제 A는 이 fixture DDL을 실행하지 않고 자체 Alembic을 사용한다. 아래 비교는 실제 로컬 카탈로그 기준이다. fixture rows는 합성 파일의 건수 메타데이터이며 배포 A DB 건수가 아니다. 담당자가 언급한 5개 JSONL·12,008건은 이번에 파일/manifest를 받지 않아 검증 불가다.

| fixture 항목 | A에만 추가된 컬럼 | fixture에만 있는 컬럼 | 공통 컬럼의 타입·NULL 차이 |
|---|---|---|---|
| teams | 없음 | 없음 | 동일(타입 alias 정규화) |
| users | is_dev_account | 없음 | 동일(타입 alias 정규화) |
| customers | 없음 | 없음 | 동일(타입 alias 정규화) |
| products | 없음 | 없음 | 동일(타입 alias 정규화) |
| orders | 없음 | 없음 | 동일(타입 alias 정규화) |
| shipments | 없음 | 없음 | 동일(타입 alias 정규화) |
| returns | 없음 | 없음 | 동일(타입 alias 정규화) |
| tickets | team_id | 없음 | cycle_no: bigint/NULL=True → bigint/NULL=False |
| messages | visibility | 없음 | ticket_id: uuid/NULL=True → uuid/NULL=False; cycle_no: bigint/NULL=True → bigint/NULL=False |
| assignments | 없음 | 없음 | ticket_id: uuid/NULL=True → uuid/NULL=False; cycle_no: bigint/NULL=True → bigint/NULL=False |
| knowledge_documents | 없음 | 없음 | 동일(타입 alias 정규화) |
| ai_suggestions | 없음 | 없음 | 동일(타입 alias 정규화) |
| approvals | 없음 | 없음 | 동일(타입 alias 정규화) |
| audit_events | reason_code, result | 없음 | 동일(타입 alias 정규화) |
| automation_rules | 없음 | 없음 | 동일(타입 alias 정규화) |
| followup_actions | cancellation_reason, cancelled_at, origin_team_id, responsibility_cycle_no | 없음 | 동일(타입 alias 정규화) |
| automation_jobs | automation_generation, expected_ticket_version, job_kind, lease_owner, reason_code, source_message_id | 없음 | ticket_id: uuid/NULL=True → uuid/NULL=False; cycle_no: bigint/NULL=True → bigint/NULL=False |
| analytics_batches | content_hash, validated_at, validation_passed | 없음 | 동일(타입 alias 정규화) |
| analytics_daily | 없음 | 없음 | 동일(타입 alias 정규화) |
| analytics_product_daily | 없음 | 없음 | 동일(타입 alias 정규화) |
| analytics_product_voc_daily | 없음 | 없음 | 동일(타입 alias 정규화) |
| analytics_product_risk | 없음 | 없음 | 동일(타입 alias 정규화) |
| customer_contacts | A 물리 테이블 없음 | fixture/Silver/Gold 보조 자료 | 비교 대상 아님 |
| coverage | A 물리 테이블 없음 | fixture/Silver/Gold 보조 자료 | 비교 대상 아님 |
| silver_complaint_episodes | A 물리 테이블 없음 | fixture/Silver/Gold 보조 자료 | 비교 대상 아님 |
| silver_voc_metrics | A 물리 테이블 없음 | fixture/Silver/Gold 보조 자료 | 비교 대상 아님 |
| gold_voc_top_n | A 물리 테이블 없음 | fixture/Silver/Gold 보조 자료 | 비교 대상 아님 |

A에만 있는 테이블: `alembic_version`, `analytics_publication`, `analytics_receipts`, `automation_control`, `automation_control_history`, `idempotency_keys`, `queue_routes`, `staff_permissions`, `team_categories`, `user_team_scopes`

추가 PK/FK/CHECK/부분 UNIQUE·인덱스·불변 trigger는 [schema.md](schema.md)의 전체 목록이 규범이다. fixture 타입 파일에는 그 대부분이 표현돼 있지 않다. fixture의 order FK는 (order_id,customer_id)인 반면 A는 product까지 묶는다. fixture SQL의 inquiries/order_items 뷰도 A에는 없다.

**구현 확인:** fixture의 nested_json_encoded=true는 Spark 입력 JSONL에서 JSONB를 JSON 문자열로 한 번 더 인코딩하는 기존 관례다. DB의 JSONB 저장 타입과 Gold API의 중첩 JSON object를 문자열로 오해하면 안 된다. 신규 Export 제안은 typed nested JSON이며 기존 fixture와 다른 schema_version으로 합의해야 한다.

**비교 불가 / 팀 합의 필요:** 주현님이 실제 적재한 Bronze/Silver 스키마·5개 JSONL의 필드/행 수/manifest/완전성 근거는 받지 않았다. 현재 문서의 27항목 및 배포32테이블과 동일하다고 주장하지 않는다. 해당 schema_contract.json, 파일별 counts/checksum, Bronze CREATE TABLE/printSchema 결과, 사용 Notebook 버전이 필요하다.
