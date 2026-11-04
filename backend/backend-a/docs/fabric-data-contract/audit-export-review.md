# audit_events Export 계약 검토

2026-11-04 KST.

**제안 계약·합성 샘플만 보완했다. 실제 DB Export, Blob 업로드, Fabric 적재·Silver 승인이 아니다.** 앱·migration·DB·Azure는 변경하거나 실행하지 않았다. 검증은 로컬 파일과 소스에 한정했다.

## 확인 기준과 자료 구분

- 실제 저장소는 `.cache/team-cs-flow-ai`, 브랜치 `feature/backend-a`, HEAD `2af74b73eacb9e692e17b1ad166d35152085859d`다. 작업 시작 시 Git은 clean, 소스 버전은 **0.11.0**, migration 파일 graph head는 **0011**이었다. DB의 적용 head를 조회한 것은 아니다. 적용되는 부모/하위 AGENTS.md는 발견되지 않았다.
- 기존 이 폴더의 DDL·schema-catalog·source-basis·PostgreSQL 검증 기록은 **0.6.1/0006의 보관 자료**다. 덮어쓰거나 최신 DB 검증으로 재표시하지 않았다. 새 스키마는 Export projection 전용이며 전체 최신 물리 스키마가 아니다.
- Fabric 제공 ZIP은 실행·추출하지 않고 메모리에서 읽었다. 원본 데이터·개인정보 가능 필드·전체 합성 원문은 전달 ZIP에 복사하지 않았다.

| 자료 | 실제 확인 내용 | 해석 한계 |
|---|---|---|
| 첨부 blob 5개 | products 20, orders 2,000, tickets 1,000, followup_actions 168, audit_events 8,820 = **12,008행** | 모두 합성. 원본 Manifest 없음 |
| 첨부 schema/schema_contract.json | 합성 물리 테이블 계약의 목록. audit 15컬럼, payload는 nested_json_encoded string | layer=silver는 자료상의 선언이며 승인 증거가 아님 |
| 첨부 manifest/validation_20261104T071231Z.json | A의 기존 products/orders/tickets/followup_actions **각 1행**의 bytes/hash와 일치 | 첨부 전체 12,008행의 검증 결과가 아님. Silver gate=BLOCKED |
| 기존 A 제안 | 위 4파일 + customer_ref 검증용 customers 각 1행 | 5행. 원본 전체 데이터의 재현본 아님 |
| 수정 A 제안 | 위 5파일 **byte 그대로** + audit 1행 | **6파일/6행**, 그중 공통 5종 + 고객 참조 보조 1종 |

validation의 PASS는 선택한 4개 작은 샘플에 한정된다. SOURCE_COUNTS_NOT_SEPARATE, RULE_HASH_ABSENT, customers 미검증과 제안/합성/완전성 미확정에 따른 gate는 해소됐다고 주장하지 않는다. 원본 Manifest를 validation에서 재구성하지 않았다. 새 제안 Manifest는 내용이 바뀌어 별도 batch ID와 `proposed-silver-v1-audit-v1`을 사용한다.

## 실제 A 감사와 첨부의 차이

근거 소스: `app/models.py`의 audit_events, `app/model_constraints.py`, `app/audit.py:record`, `app/services.py:submit_ticket`, `app/ticket_commands.py:change_cycle`, `app/finalization.py:commit_automatic_reply`, `app/seed.py:seed`. 이번 확인은 **소스 검토**이며 DB 적용·B Worker 실행 확인이 아니다. 읽은 소스 hash는 [오프라인 검증 기록](audit-export-verification.json)에 있다.

| 항목 | 첨부 합성 audit | 실제 A 소스와 제안 처리 |
|---|---|---|
| 컬럼 | 15컬럼 | A는 17컬럼. result/reason_code가 추가됨. fixture 서버 기본 SUCCESS/FIXTURE_HISTORY는 실제 사건 의미의 검증이 아님 |
| event_id | UUID PK | A도 UUID PK. Export는 domain=event의 HMAC event_ref. 원본 ID는 제외 |
| event_key | UUID 모양 문자열, 8,820행 unique | A는 TEXT NOT NULL UNIQUE. record 호출마다 새 UUID라 논리 사건/접촉의 멱등키가 아님. Export 제외 |
| 연결/NULL | ticket_id·cycle_no 모두 있고 cycle=1. actor_user_id 전부 NULL | A ticket_id/cycle_no/actor_user_id/actor_service/target_id는 NULL 가능. ticket 생성 감사에는 cycle이 생략된다. 현재 ticket.cycle_no로 NULL을 채우지 않음 |
| action | CREATED 1,000 / STATUS_CHANGED 4,820 / CUSTOMER_CONTACT 3,000 | A action/target_type은 TEXT, action enum CHECK 없음. 문자열 저장 가능성과 해당 업무 producer 존재는 다름. 현재 업무 코드에 이 3개 emitter 없음 |
| 실제 업무 action | 위 합성 action | TICKET_CREATED, TICKET_REOPENED, AGENT_REQUESTED, AUTOMATIC_REPLY_COMMITTED 등. CREATED/STATUS_CHANGED와 자동 이름 변환하지 않음 |
| result/reason | 없음 | result는 VARCHAR(16), SUCCESS/DENIED/FAILURE CHECK. reason_code VARCHAR(64). 이 projection은 SUCCESS와 명시된 action별 reason만 허용 |
| payload | 모든 행 JSON 문자열. 내부 키는 CREATED:to_status, STATUS_CHANGED:from_status/to_status, CUSTOMER_CONTACT:message_id/primary_issue | A 컬럼은 JSONB, JSON scalar string도 저장 가능. 공통 record는 native object `{}`를 넣음. 파일을 JSON으로 한 번 읽으면 첨부 payload는 여전히 str이다. seed는 nested 문자열을 자동 object로 풀지 않으므로 fixture가 항상 object로 저장된다고 단정 못함 |
| 시각 | created_at UTC 문자열, 소수부 없음 | A UTCDateTime/timestamptz, record의 기본값은 저장 시 Python utcnow. Export 제안은 UTC 소수6자리. 정밀도 형식 통일이 사건 의미를 보완하지는 않음 |
| 생성 출처 | synthetic_generator / SYNTHETIC | 실제 record와 구분. 샘플·Manifest 전체가 SYNTHETIC. 운영 데이터와 섞거나 과거 완전 이력으로 backfill하지 않음 |

payload를 쓰는 별도 계약을 만들 경우 원천 JSONB 타입을 확인하고 허용 키만 native JSON object로 직렬화해야 한다. str을 다시 JSON 인코딩해 object처럼 전달하면 안 된다. **이번 projection에서는 payload 전체를 제외**하므로 자유문장·원문·message_id 등을 옮기지 않는다.

### 접촉 사건은 현재 호환 미확정

현재 A 업무 producer는 합성 `CUSTOMER_CONTACT`를 생성하지 않는다. TICKET_REOPENED/AGENT_REQUESTED는 해당 명시 명령의 근거일 뿐 모든 접촉을 나타내지 않는다. 감사 created_at은 고객 접촉 시각·외부 채널 발생 시각·commit 순서가 아니다. audit에는 별도 occurred_at/LSN/before/after가 없고, 감사 문구나 ticket snapshot으로 접촉을 추정하지 않는다.

최소 보완 **제안**: 고객 PUBLIC IN 메시지의 `message_ref, ticket_ref, cycle_no, role, direction, visibility, created_at` 메타데이터를 별도 버전 계약으로 검토한다. message.created_at도 외부 채널 실제 발생 시각을 보증하지 않는다. 채널 접촉 전체가 필요하면 담당 producer가 명시적으로 발생 시각·채널·안정적인 중복 방지 사건키를 제공하고, 포함 채널/전달 지연/재문의 집계 단위를 Fabric과 합의해야 한다. 이번에는 messages Export나 새 이벤트를 구현하지 않았다.

## 최소 audit Export projection — 전부 제안

[기계 판독 스키마](samples/export-proposal/schema_contract.json)의 audit_selection과 audit_events.fields가 정본이다. 기존 4종 및 customers의 필드·NULL·파일 bytes는 유지했다.

| 허용 필드 | wire 타입/NULL | 의미 |
|---|---|---|
| event_ref | HMAC-SHA256 lowercase hex64 / 필수 PK | 실제 event_id에서 가명화. 접촉 사건 논리키 아님 |
| ticket_ref | 동일 ticket domain HMAC / 필수 FK | 전달 허용 ticket 집합에 속하는 non-NULL ticket_id만 선택 |
| cycle_no | int64 또는 null | 원천 그대로. 이전 cycle도 지우거나 현재 회차로 대체하지 않음 |
| action | 아래 allowlist 문자열 / 필수 | 임의 일반 text는 전달하지 않음 |
| result | SUCCESS / 필수 | 접근·거부·조회 감사를 업무 접촉으로 섞지 않음 |
| reason_code | action별 allowlist / 필수 | 자유문장 제외 |
| created_at | UTC YYYY-MM-DDTHH:MM:SS.ffffffZ / 필수 | 감사 저장 시각 |

공통 선택: target_type=TICKET, result=SUCCESS, ticket_id가 있고 같은 scope의 전달 tickets에 연결 가능해야 한다. nullable 원천 ticket_id를 필수 wire ticket_ref로 바꾸는 것은 이 선택 조건이며 가짜 ID 생성이 아니다. 팀은 현재 전달 ticket 집합의 **접근 범위 필터**일 뿐 사건 당시 처리 팀 귀속의 증거가 아니다. 허용 tickets 밖의 이벤트는 누락/필터 수를 운영 Export에서 명시해야 하며 이번 1행으로 완전성을 주장하지 않는다.

| action | 허용 reason_code |
|---|---|
| TICKET_CREATED | CUSTOMER_SUBMITTED |
| TICKET_REOPENED | CUSTOMER_REOPENED, HUMAN_CONTINUATION |
| AGENT_REQUESTED | CUSTOMER_REQUEST, DISSATISFIED, COMPLEX_ISSUE, OTHER |
| AUTOMATIC_REPLY_COMMITTED | FENCED_COMMIT |

이 목록은 물리 DB CHECK를 추가한 것이 아니다. 그 밖의 action/result/reason은 이 최소 projection에서 제외하며, 임의 매핑·의미 추론을 하지 않는다. raw event_id/ticket_id/event_key, actor 식별자/service, target_id, payload, 고객 이름·원문·전화·주소·이메일·토큰을 포함하지 않는다. JSONB 직렬화 예시라는 이유로 payload를 재추가하지 않는다.

## customers 유지와 Manifest 해석

customers는 `customer_ref, deleted_at`만 유지해 orders/tickets의 customer_ref 참조를 검사한다. 첨부 ZIP에 customers가 없고 이전 validation이 범위 밖으로 두었다는 이유로 삭제하지 않는다. 별도 registry 전달로 바꿀지는 Fabric과 추후 합의한다. 현재 수정 Manifest에는 보조 파일도 명시되어 있다.

- Manifest 파일 항목 6개, 각 1행, 실제 UTF-8 LF bytes의 byte_count/SHA256을 사용한다. 샘플 audit는 297bytes다. 논리 파일명 audit_events.jsonl은 기존 분할 규칙에 따라 `export-proposal/audit_events/part-00001.jsonl`로 제공한다.
- `source_migration_head=0006`, 고정 source_as_of와 extraction 시각, full_snapshot=true는 **과거 합성 예시의 제안 값**이다. 실제 추출 사실이 아니다. fixture_basis와 별도 audit_source_review(0.11.0/0011, database_checked=false)를 함께 읽는다. 최신 DB head로 위장하지 않았다.
- `PROPOSED_NOT_IMPLEMENTED`, `EXAMPLE_ONLY_NO_SNAPSHOT_WAS_EXPORTED`, `data_origin=SYNTHETIC`, completeness=unknown, silver_approval=NOT_APPROVED를 유지한다. 기존 analytics-v1 Gold wire와 source_input_hashes는 바꾸지 않았다.
- hmac-vector의 bytes00..1f는 공개 합성 예시 키다. 운영 키·토큰·계정 정보가 아니다. 운영 재사용 금지. 해시 대상 JSONL의 줄바꿈을 변환하지 않는다.

## 이번에 실행한 검증

[A 제안 검증](audit-export-verification.json): 6 JSONL/6행, strict JSON·필수값·타입/NULL·PK·확인 가능한 FK·scope 소속·HMAC·Manifest bytes/count/hash 일치. 기존 공통4파일과 customers의 SHA256 기준값 동일. [첨부 검토](incoming-audit-review.json): ZIP CRC, 5 JSONL/12,008행, 첨부 schema의 키/필수값/주요 타입/PK, 포함 파일 사이 FK, audit event_key 유일성·action 건수·payload 구문, 기존 validation의 작은4파일 일치 확인. 파일 bytes/hash는 새로 계산했으며 원본 Manifest 검증은 아니다.

customers/users/teams/messages가 첨부에 없어 그 원천 FK는 미검증이다. 최신 PostgreSQL·운영 DB·실제 Export·Fabric/Silver·Azure 실행 검증은 하지 않았다. 과거 보관 PostgreSQL PASS와 이번 오프라인 파일 검증을 합산하지 않는다. 전체 업무 테스트도 반복하지 않았다.

```powershell
# backend/backend-a 기준. 표준 라이브러리만 사용; 앱/DB/환경파일 로드 없음
python docs/fabric-data-contract/tools/verify_export_proposal.py --write-report
# 전달받은 원본 ZIP이 로컬에 있을 때만 추가 비교; ZIP 내용 실행/추출 없음
python docs/fabric-data-contract/tools/verify_export_proposal.py --incoming-zip '<받은 ZIP 경로>' --write-report
```

Fabric 담당께 확인할 항목은 CUSTOMER_CONTACT 실제 producer/시각/중복 기준, 새 projection/version 수용, 고객 참조 registry 유지 방식, snapshot·완전성·규칙 hash·Silver 승인 조건이다. 이번 자료 추가로 어느 것도 자동 확정되지 않는다.
