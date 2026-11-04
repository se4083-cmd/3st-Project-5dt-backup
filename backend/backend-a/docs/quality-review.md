# AI 상담 품질 수동 평가 (로컬 0.9.0 / migration 0009)

확정 답변의 근거 연결→수동 표본→지정 검토자 자료 조회→평가/수정 이력→현재 snapshot 지표를 구현했다. 실제 AI 호출·자기평가·재생성·Frontend 화면·Fabric 전송/집계·B 재시도/실패/이관/배정·ticket_cycles·새 SLA는 구현하지 않았다. 자동 완료·정답·안전한 완료는 다른 개념이며 신규 자동 처리율/이관율/안전한 완료율을 계산하지 않는다.

## 확정 기록과 B의 선택 데이터

내부 Python 함수 `app.finalization.commit_automatic_reply(session, command: AutomaticReply)`와 반환값 `{message_id,ticket_id,cycle_no,revision}`은 유지한다. 호출자가 `factory.begin()`으로 transaction을 열고 commit한다. HTTP API가 아니다.

`AutomaticReply.provenance: app.quality_schemas.ReplyProvenance | None = None`만 선택 추가했다. 미제공 호출도 성공하며, 새 PUBLIC OUT final SYSTEM 메시지에 실제 job/ticket/cycle, input_ticket_revision, result_ticket_revision=input+1, 답변 SHA256, 확정 시각, 당시 ticket.team_id를 같은 transaction으로 기록한다. 실제 외부 발송 성공을 뜻하지 않는다. 과거 메시지에는 임의 기록을 backfill하지 않는다.

```python
from app.finalization import AutomaticReply, commit_automatic_reply

with factory.begin() as session:
    result = commit_automatic_reply(session, AutomaticReply(
        job_id=claimed_job_id, lease_token=claimed_lease_token,
        worker_id=worker_id, cycle_no=current_cycle,
        expected_revision=current_ticket_revision, message=actual_final_answer,
        automation_generation=claimed_generation,
        provenance={
            "source_message_id": actual_question_id,
            "suggestion_id": actual_suggestion_id,
            "suggestion_revision": actual_suggestion_revision,
            "suggestion_content_hash": actual_suggestion_hash,
            "approval_id": actual_approval_id,
            "model_version": actual_model_version,
            "prompt_version": actual_prompt_version,
            "retrieval_ref": actual_retrieval_snapshot_ref,
            "evidence": [{"document_id": actual_policy_document_id,
                          "version": actual_policy_version,
                          "content_hash": actual_policy_sha256,
                          "chunk_ref": actual_chunk_ref}],
        },
    ))
```

위 변수는 B가 실제 사용한 값이다. 최신 suggestion/정책을 검색해 대신 넣지 않는다. suggestion 참조는 id/revision/hash를 함께 요구하며 명시된 행의 ticket/cycle/created_at, draft와 실제 최종 답변의 정확한 일치를 확인한다. 수정된 초안을 별도 연결 없이 원 suggestion의 확정 답변으로 표시하지 않는다. approval은 해당 suggestion/hash/ticket/cycle/input ticket revision/APPROVED 및 유효 시각을 확인한다. 전달한 model/prompt가 명시 suggestion과 다르면 거부한다.

질문은 명시한 PUBLIC IN 행의 ticket/cycle/hash만 고정한다. job.source_message_id가 있으면 일치해야 한다. suggestion에 공식 입력 message FK가 없으므로 **같은 회차라는 검사는 실제 AI 입력 사용을 독립 입증하지 않는다**. B가 실제 질문·retrieval snapshot을 전달해야 한다. 임의의 같은 회차 질문을 골라서는 안 된다. 없는 연결은 추측하지 않는다.

정책 참조는 document id/version/hash, 당시 active/APPROVED/effective 범위와 명시 suggestion의 evidence_refs 포함 여부를 확인한다. 검색 ref/chunk ref는128자 이내 식별 코드이며 URL/파일 경로를 열지 않는다. 정책 본문 SHA256까지 선언 hash와 일치할 때만 body_sha256을 기록한다. metadata hash만 있고 본문 hash를 검증할 수 없으면 REFERENCES_ONLY이며 본문을 복원했다고 표현하지 않는다. 정책 원문·raw prompt·주문 snapshot을 새 테이블로 복사하지 않는다.

- MISSING: AI/RAG 선택 자료 없음. PARTIAL: 일부만 있거나 본문 검증/전체 evidence가 부족함.
- COMPLETE: 명시 질문·suggestion·approval·버전·retrieval ref 및 suggestion의 전체 evidence와 검증 가능한 본문이 갖춰짐. **정답/AI 사용의 독립 증명/비트 단위 재현 보장 아님**.
- 관련 원천 중 SYNTHETIC이 있으면 origin=SYNTHETIC, 모두 APPLICATION이면 APPLICATION, 그 외 UNKNOWN이다. 조회는 origin별로 분리하고 기본은 APPLICATION이다.

기존 ticket→job→control SHARE 잠금과 lease/cycle/revision/mode/generation/PAUSED/필수 후속/최종 OUT 유일성 gate는 유지한다. 명시 provenance 원천을 SHARE로 확인한 **뒤**, 첫 쓰기 직전 wall-clock으로 lease 및 approval/정책 만료를 다시 확인한다. 불일치는 WorkRejected의 PROVENANCE_QUESTION_MISMATCH / SUGGESTION_MISMATCH / VERSION_MISMATCH / APPROVAL_MISMATCH / EVIDENCE_MISMATCH / SUGGESTION_EVIDENCE_MISMATCH(각 PROVENANCE_ 접두사), PROVENANCE_EXPIRED다. 기존 fencing 오류도 그대로다. 오류 후 전체 rollback하고 현재 job/ticket을 재확인하며, 기존 성공 답변을 재생성하거나 FAILED를 되살리지 않는다.

## 저장·권한

6개 additive 테이블: quality_rubrics, automatic_reply_records, automatic_reply_evidence, quality_samples, quality_review_revisions, quality_command_receipts. 기존0001–0008은 불변이며0009에 연결한다. profile·메시지·정책 본문을 복제하지 않는다. reply의 ticket/cycle 및 job/message 연결은 공통 writer와 PG trigger가 검증한다. job·ticket/cycle은 각각 UNIQUE다. evidence_count와 지연 제약으로 확정 후 근거 행 추가도 막는다.

표본은 `(message_id,rubric_version)` UNIQUE, selection_method는 MANUAL뿐이다. 표본 선택 revision1 SELECT, 이후 REVIEW/REASSIGN/VOID는 새 revision이다. 과거 revision·rubric·응답 기록·근거·receipt의 UPDATE/DELETE는 PG에서 거부한다. sample head 변경은 새 이력 revision을 요구한다. VOID는 최종 무효 상태이며 재선택으로 UNIQUE를 우회하지 않는다. rubric V2는 별도 버전의 검토된 정의로 추가해야 하고, 기존 정의를 수정하지 않는다. 현재 등록 UI/API는 없으며 GET catalog와 개발 기준 DEV_QUALITY_V1만 제공한다.

| 작업 | 필요 조건 |
|---|---|
| 후보/표본 생성·담당 변경·VOID | 활성 ADMIN + QUALITY_SAMPLE_MANAGE + 현재 책임 팀 scope |
| 자료/평가 | 활성 ADMIN/AGENT + QUALITY_REVIEW + 본인 지정 + 현재 검토 팀 scope |
| 지표 | ADMIN + QUALITY_METRICS_READ + 선택 팀이 현재 허용 팀의 부분집합 |
| 미귀속 후보·표본 관리 | 별도 QUALITY_UNATTRIBUTED_MANAGE 추가. 허용 팀 중 검토 책임 팀을 명시 |

새 capability는 CHECK·allowlist·capabilities에 일치하며 기본 grant0이다. 실제 계정 grant는 하지 않았다. CUSTOMER는 차단한다. 관리자가 자료를 보려면 본인을 지정하고 REVIEW도 가져야 한다. 관리 권한만으로 원문을 보지 못한다. reviewer 지정 시 활성 역할·명시 REVIEW·정규화 팀 scope를 확인하고 자료/평가 시 다시 검사한다. 담당 변경으로 이전 유효 REVIEW를 지우지 않는다.

처리 귀속은 확정 시점 ticket.team_id snapshot만 사용한다. route나 현재 ticket.team_id에서 과거 귀속을 추정하지 않는다. 미귀속 표본의 review_team_id는 QA 책임이며 ticket/team/처리 실적을 바꾸지 않는다. 미귀속 직접 선택도 별도 권한 없으면404로 숨긴다. 다른 권한 밖 객체 역시404이며, 범위 밖 목록/연결 개수를 반환하지 않는다. 일반 ticket_scope·고객360·배정은 확장하지 않는다.

## HTTP API와 요청 예시

prefix `/api/v1/staff/quality`, 사용자 bearer, Cache-Control:no-store. 모든 변경 POST에 기존 형식 Idempotency-Key(8–128자)가 필요하다. 자료 조회 POST는 멱등키 없이 purpose만 요구한다.

| 메서드·경로 | 계약 |
|---|---|
| GET /rubrics | 고정 rubric version·DEVELOPMENT_PROPOSAL·판정 기준. 운영 합의 아님 |
| GET /candidates | 검증된 자동 확정 응답 metadata. origin 기본 APPLICATION, unattributed=false. limit1–100 기본20/cursor. committed_at DESC/message_id DESC. 이미 표본인 응답도 포함하며 legacy 초안은 포함하지 않음 |
| POST /samples | message/rubric, 책임 팀, 지정 reviewer. 신규201/동일 replay200 |
| GET /samples | 관리자 허용 팀 또는 REVIEW 본인 지정 표본. selected_at DESC/sample_id DESC. limit/cursor |
| POST /samples/{sample_id}/material | purpose_code=QUALITY_REVIEW. 제한 답변·명시 질문·검증한 정책 본문/근거 상태·rubric |
| POST /samples/{sample_id}/reviews | expected_revision, 두 수동 판정, reason_codes, change_reason |
| POST /samples/{sample_id}/assignment | expected_revision, assigned_reviewer_id, REVIEWER_CHANGED/WORKLOAD_BALANCE/OTHER |
| POST /samples/{sample_id}/void | expected_revision, WRONG_TARGET/DUPLICATE/INVALID_SAMPLE/OTHER |
| GET /samples/{sample_id}/history | limit1–100, before_revision(exclusive), items/next_before_revision |
| GET /metrics | response_start/end aware UTC, rubric_version, origin, team_ids 반복 파라미터, include_unattributed=false. 과거 as_of 요청은422 |

다음 UUID는 설명용이고 실행 중 받은 ID를 사용한다. 실제 토큰을 문서에 저장하지 않는다.

```json
{"message_id":"11111111-1111-4111-8111-111111111111","rubric_version":"DEV_QUALITY_V1","review_team_id":"22222222-2222-4222-8222-222222222222","assigned_reviewer_id":"33333333-3333-4333-8333-333333333333"}
```

생성 응답: `{"sample_id":"44444444-4444-4444-8444-444444444444","revision":1}`. 자료 요청은 `{"purpose_code":"QUALITY_REVIEW"}`다. 자료 접근 성공/거부와 목적은 원문 없이 감사한다. 종료 티켓이어도 해당 표본 자료만 읽고, 일반 티켓 상세/고객360 탐색 권한은 생기지 않는다. 전체 이력·프로필·주문번호/주문 객체는 반환하지 않는다. 최소 원문 안의 이메일/연락처/URL/명시 주문번호 등은 마스킹한다. **패턴 마스킹은 완전한 개인정보 탐지가 아니다**. redaction_state는 PATTERN_MASKED_NOT_PII_FREE_GUARANTEE다. 미지의 개인정보가 자유 문장에 있을 수 있으므로 최소 자료/지정 목적 경계를 유지한다.

```json
{"expected_revision":1,"accuracy":"CORRECT","policy_alignment":"MATCH","reason_codes":["VERIFIED_AGAINST_MATERIAL"],"change_reason":"INITIAL_REVIEW"}
```

판정은 CORRECT/INCORRECT/UNDETERMINABLE, MATCH/MISMATCH/UNDETERMINABLE/NOT_APPLICABLE이다. 판정 사유는 VERIFIED_AGAINST_MATERIAL/FACT_ERROR/POLICY_CONTRADICTION/INSUFFICIENT_CONTEXT/POLICY_NOT_APPLICABLE/OTHER의 제한 코드다. 자유 원문·고객정보를 사유로 복제하지 않는다. 첫 REVIEW의 change_reason은 INITIAL_REVIEW, 수정은 CORRECTION/NEW_INFORMATION/OTHER를 명시한다. 질문이 없으면 정확성은 UNDETERMINABLE만, 정책 본문이 전부 검증되지 않으면 MATCH/MISMATCH는 거부한다. 각 자료 본문은10,000자 이내로 표시하고 원문이 더 길면 truncated_fields/정책별 truncated와 INSUFFICIENT_MATERIAL을 명시한다. 질문·답변이 잘리면 정확성 확정, 정책이 잘리면 MATCH/MISMATCH를 거부한다. NOT_APPLICABLE은 사람의 명시 판단이며 자료 누락의 자동 대체가 아니다.

현재 원본 답변/질문/정책의 hash·식별이 달라지면 MATERIAL_CHANGED, 본문 hash를 처음부터 확인하지 못했다면 REFERENCES_ONLY/INSUFFICIENT_MATERIAL이다. 새 현재 정책을 끼워 넣거나 blob_path/URL을 읽어 보충하지 않는다. 답변 자체가 바뀌면 평가 저장을 거부한다. 과거 판정을 새 본문으로 재해석하지 않는다. confidence·승인 여부로 정답을 생성하지 않는다. 원래 승인자가 알려진 경우 같은 평가자인지 independence=NO/YES, 아니면 UNKNOWN으로 이력에 표시한다.

같은 사용자/key/동일 검증 본문은 원래 sample/revision을 반환한다. 다른 operation/경로/본문은409 IDEMPOTENCY_CONFLICT다. 재요청도 현재 역할·scope·지정 reviewer를 검사하며 회수 후 옛 receipt로 읽지 못한다. actor→record(표본 생성) 또는 actor→sample 잠금으로 직렬화하고 expected_revision으로 경쟁을 거부한다. 표본/이력/head/감사/receipt는 한 transaction이며 부분 저장하지 않는다. 409 QUALITY_REVISION_CONFLICT면 최신 목록/이력을 다시 읽고 의도를 확인한다. DB503은 같은 key/body로 재시도한다.

## 지표 정의와 한계

**기준은 응답 확정 기간 `[response_start,response_end)`의 현재 repeatable-read snapshot**이다. 평가 시각 기간과 섞지 않는다. as_of는 서버 snapshot 시각이고 과거 평가 복원을 제공하지 않는다. REVIEW 중 sample head 이하의 마지막 유효 REVIEW만 사용한다. REASSIGN은 그 판정을 유지하고 VOID는 제외한다. 모든 지표는 rubric별·origin별로 분리한다.

| 필드/지표 | 분자·분모·제외 |
|---|---|
| attributed.confirmed_response_count | 기간·origin·확정 시 처리 팀 scope에 속하는 actual reply record 수. job 재시도 행/초안/legacy는 분모가 아님 |
| accuracy_rate | correct / (correct+incorrect). UNDETERMINABLE·미평가·VOID 제외. denominator0→null |
| policy_alignment_rate | policy_match / (policy_match+policy_mismatch). UNDETERMINABLE/NOT_APPLICABLE·미평가·VOID 제외. denominator0→null |
| evaluation_coverage | 비VOID 마지막 REVIEW가 있는 응답 수 / 같은 scope·기간·origin의 확인 가능한 **전체 자동 확정 응답 수**. 표본만을 분모로 쓰지 않음 |
| unreviewed_response_count | 확인 가능한 전체 응답 − 유효 평가 응답. 표본에 안 뽑힌 응답도 포함 |
| unreviewed_sample_count | 활성 표본 중 REVIEW 없음 |
| active_sample_count/void_count | 활성/무효 표본을 분리. 무효는 이력과 제외 건수 보존 |
| unselected_or_void_response_count | 전체 응답 − 활성 표본. void_count와 부분 중첩하므로 합산 금지 |
| review_team_sample_counts / review_team_evaluation | 허용 QA 팀의 표본 업무 수와 수동 표본 내 판정률. include_unattributed=true와 별도 권한이 있을 때 미귀속 표본도 이 QA 묶음에 포함한다. 처리 팀 실적/전체 coverage/전체 정답률이 아니다. 전체 응답 중 누가 어느 QA 팀에 속할지는 미정이므로 이 묶음의 population coverage는 제공하지 않는다 |
| unattributed_confirmed_response_count | 별도 권한+include_unattributed=true일 때만 전역 미귀속 확인 가능 응답 수. 특정 검토 팀 실적에 배분하지 않음 |
| legacy_auto_unknown_count | 같은 기간/원천 구분의 record 없는 PUBLIC OUT final 행. 당시 AUTO 자체/처리 귀속 불명이며 HUMAN이 포함될 수도 있음. 확인 가능한 AUTO 분모/정답으로 backfill하지 않음. 별도 전역 권한 없으면null |

미평가·판단 불가·비적용·VOID는 각각 개수다. 단위는 message(자동 writer의 ticket/cycle UNIQUE)이며 rubric이 다르면 별도 표다. 실제 원천 태그조차 불명인 자료는 UNKNOWN으로 분리한다. 조회하는 사용자의 현재 팀 scope만 적용한다. 표본 수동 선택은 대표 표본/전체 AI 정답률 추정이 아니다.

검산: 확인 가능한 응답100건 중20건 REVIEW(정확15/오류3/판단불가2), 나머지80건 미평가라면 accuracy=15/18, coverage=20/100, unreviewed_response_count=80이다. [전체 합성 응답 예시](examples/quality-metrics.json)를 제공한다. 관측0과 자료 없음/null을 혼동하지 않는다. 과거 provenance 누락·등록되지 않은 writer·원천 태그 누락이 있으므로 이 coverage도 전체 서비스 자동 응답의 완전 수집을 보장하지 않는다.

## 보관·회귀·연동

retention dry-run은 reply/source-question·정책 evidence·표본/평가/receipt 참조를 보호한다. TEAM preview는 미귀속/범위 밖 역사적 처리·검토 책임이 섞인 티켓을 제외하고, 전체 QA 이력 inventory는 null/UNSUPPORTED_TEAM_SCOPE다. GLOBAL도 workflow/정책 참조를 보호하며 실삭제는 없다. 원천 정책 본문 보존/immutable 버전 운영과 legal hold는 별도 합의가 필요하다.

기존 VOC·업무량·analytics-v1은 유지한다. 새 품질 결과를 Gold wire로 보내지 않는다. Frontend는 capabilities→rubric/candidate→표본/담당→본인 material→평가/이력→metrics 순서로 연결한다. 매 변경의 revision/key를 보관하고 충돌 시 새 이력을 확인한다. 미귀속 QA 책임과 처리 실적, origin, 부족한 자료, 수동 표본 한계를 화면에 표시한다. 실제 화면은 이번에 구현하지 않았다.

B/AI·RAG 합의 사항은 실제 입력 질문→suggestion FK, 실제 수정 답변의 provenance 계약, 모델 배포/생성 파라미터·검색 snapshot 보존, chunk 식별·당시 정책 SHA256/원문 불변 보존, 운영 rubric·표본 대표성·검토자 독립성이다. AI 자체 평가와 실패/HUMAN 전환 계약은 별개다. 실제 외부 AI 품질·발송·Fabric 연결은 미검증이다. [이번 로컬 검증](evidence/quality-local/README.md)을 따른다.
