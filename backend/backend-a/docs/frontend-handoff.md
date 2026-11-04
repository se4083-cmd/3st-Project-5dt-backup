# Frontend 인수 — 추가 기능 연결 안내 (0.10.0 / migration0010)

2026-11-04 KST 문서 정리·공유 검토. 실제 체크아웃은 `<PROJECT_ROOT>/.cache/team-cs-flow-ai`(요청 경로의 `.cache` 앞 구분자 누락 보정), branch `feature/backend-a`, **구현 공유 기준 HEAD**는 `2cb07cfc0bcbf1a203b6d54c5ebb1bb905a7be93`다. 이번 문서 공유 전 원격 HEAD도 같은 기준임을 확인했고, 시작 변경은 이 문서 한 개뿐이었다. 적용 경로의 AGENTS.md는 발견되지 않았다. 앞선 초안 작성은 로컬 문서 작업이었으며, 이번에는 이 문서만 commit·일반 push 대상으로 검토한다. 앱·migration·업무 테스트·DB·Azure·실제 권한·다른 팀 코드·메시지 발송은 이번 범위 밖이다. **현재 Azure 상태는 조회하지 않았으며**, 아래 과거 배포 기록과 현재 소스 구현 상태를 구분한다.

## 1. 인수님 요청 3가지 상태

| 요청 | A 구현 완료(로컬·GitHub 소스) | 팀 연결 필요 | 추가 구현·합의 필요 |
|---|---|---|---|
| AI 상담 품질 평가·모니터링 | 확정 자동 응답의 전향적 근거 연결, 수동 표본·검토자 지정, 제한 자료·append-only 평가 이력, 표본 판정률/coverage | Frontend 화면, B의 실제 확정 writer와 AI/RAG의 실제 질문·버전·근거, 운영 평가자 연결 | 실제 AI 품질 검증·운영 rubric 합의는 미완료. 자동 처리율·이관율의 새 회차 분모/사유 이력과 **안전한 자동 완료율**은 별도 구현·관찰 기간/기준 합의 필요 |
| VOC 상품 개선 조치·효과 추적 | 상품 개선 등록, 기존 후속 등록, 계획/시행 사실 정정 이력, 관련 문의·발견 배치/scope 참조 | Frontend 등록/이력 화면, Fabric 주현님과 상품/기간/판매 분모/비교 scope 합의 | 실제 Fabric **전후 효과 수신·저장·조회/계산은 미구현**. DONE은 업무 완료이며 효과 입증 아님. 문의 감소만으로 인과효과 확정 불가 |
| 상담사 업무량·SLA 최적화 | 현재 업무량·미배정·기한 상태, HUMAN 대기의 읽기 전용 우선순위/적격 후보 추천 | Frontend 조회·상태 표시, B 준혁님의 최신 조건 재검사와 실제 배정 경계 연결 | B 실제 배정 통합·동시 부하 균형/운영 효과 미검증. 정식 SLA 시작/종료/재문의/일시정지·업무시간/휴일·최초 응답/해결 정의와 엔진은 별도 |

기존 `GET /api/v1/admin/analytics/kpi`는 게시 analytics-v1의 `Σauto_closed_count/Σticket_count`, `Σhandoff_count/Σticket_count`를 제공한다(분모0→null). 이는 upstream 티켓 생성 cohort 지표이며 AUTO 시작 회차율·사후 이관/안전한 완료율이 아니다. 실제 Fabric 연결/운영 성과를 확인한 것이 아니고, 없는 과거 회차/실패 사유를 snapshot이나 문구로 추정하지 않는다. [현재 A 전체 인수 현황](backend-a-handoff.md), [Fabric 계약](fabric-contract.md)을 따른다.

## 2. 연결 환경과 선행 확인

| 구분 | 확인된 기준 | 화면 연결 시 의미 |
|---|---|---|
| 로컬/GitHub | 소스0.10.0, migration 파일 head0010, 위 공유 커밋. 과거 로컬 PG 검증 기록 있음 | 현재 코드/OpenAPI 기준으로 연동 준비 가능. 실행 중인 로컬 API/DB 최신 head는 별도 확인 필요 |
| Azure 마지막 배포 기록 | [2026-11-03 이름 이전 보고](azure-migration.md): **0.6.1 / DB0006**, 당시 CORS 허용 origin=[] | **현재 최신 Azure 상태는 이번 미확인**. 기존 Azure 주소에 아래 신규 API가 있다고 안내하지 않는다 |
| 실제 화면/B/AI/Fabric | 실제 통합 미검증 | 합성 예시·로컬 PASS·Git push를 통합/배포 성공으로 표시하지 않는다 |

화면 연결 전에 **배포 담당+A**가 선택 환경의 빌드0.10.0·readiness·실제 DB head0010·대상 `/openapi.json` 경로를 확인해야 한다. Azure는 별도 승인 후 현재 DB head와 백업/호환성을 확인하고0007→0008→0009→0010 중 미적용 migration만 순서대로 처리하며, 새 테이블/trigger·권한 허용값까지 적용·검증해야 한다. 기존 데이터/권한을 seed로 덮어쓰거나0.6.1/0006 전용 도구를 새 버전에 바로 실행하지 않는다. 파일 head와 실제 배포 DB head는 다르다.

- **권한/운영 담당+A:** 아래 capability는 ADMIN 역할만으로 자동 부여되지 않는다. 실제 사용자 활성/팀·정규화 scope, 후보 지원 category, 검토자 지정/QUALITY_REVIEW와 필요 rubric을 확인한다. 승인된 별도 작업으로 최소 grant를 설정한다. 실제 계정·비밀번호·토큰·DB 접속 정보는 이 문서에 넣지 않는다.
- **Frontend 인수님+배포 담당:** 실제 HTTPS 화면 origin을 확정해 `CORS_ORIGINS`에 명시 허용하고 브라우저 preflight를 검증한다. 현재 코드의 허용 헤더는 Authorization/Content-Type/Idempotency-Key, 노출 헤더는 X-Request-ID/Location/Idempotency-Replayed, allow_credentials=false다. 이 설정이 실제 배포됐는지는 별도 확인한다. 임의 origin·`*`·브라우저의 DB 직접 접속/서비스 인증키 배포는 사용하지 않는다.
- Frontend의 `API_BASE`는 **연동 환경 확인 후 정한** `/api/v1`까지의 값으로 설정한다. 아래 경로에 `/api/v1`을 중복 붙이지 않는다. 실제 토큰은 기존 로그인 흐름에서 취급하고 문서·로그에 저장하지 않는다. 업무 자동 처리 재개는 화면 연동 선행 작업이 아니다.

## 3. 실제 API·역할·문서

아래 모든 경로의 공통 prefix는 `/api/v1`이다. CUSTOMER는 이 네 직원 기능에 접근하지 못한다. 화면의 capabilities 검사는 표시 제어이며 서버가 매번 현재 권한을 다시 검증한다.

| 기능 | 실제 HTTP 경로(prefix 제외) | 역할·capability·현재 scope | 상세/전체 예시 |
|---|---|---|---|
| 업무량 | GET `/staff/workload` | AGENT는 별도 grant 없이 본인/활성 소속 팀 scope만. ADMIN은 WORKLOAD_READ+허용 활성 팀. 전역 미라우팅 포함은 ADMIN+UNROUTED_QUEUE_READ 추가 | [workload.md](workload.md), [전체 응답](examples/workload-response.json) |
| VOC 개선 | GET/POST `/staff/voc-improvements`; GET `/staff/voc-improvements/{action_id}`; POST `/staff/voc-improvements/{action_id}/plans`, `/staff/voc-improvements/{action_id}/tickets` | ADMIN+VOC_IMPROVEMENT_MANAGE+현재 후속 담당 팀 scope. 과거 계획은 비교 팀 전부/과거 담당 팀 권한, 문의 연결은 양쪽 권한+상품 일치 | [voc-improvements.md](voc-improvements.md): 신규/기존 등록·계획·연결 요청/receipt |
| 품질 표본 관리 | GET `/staff/quality/rubrics`, `/staff/quality/candidates`, `/staff/quality/samples`; POST `/staff/quality/samples`, `/staff/quality/samples/{sample_id}/assignment`, `/staff/quality/samples/{sample_id}/void` | ADMIN+QUALITY_SAMPLE_MANAGE+현재 검토 팀. 미귀속 후보/표본 관리에는 QUALITY_UNATTRIBUTED_MANAGE 추가. 귀속된 응답의 검토 팀은 확정 시 귀속 팀과 일치 | [quality-review.md](quality-review.md) |
| 품질 검토/이력 | POST `/staff/quality/samples/{sample_id}/material`, `/staff/quality/samples/{sample_id}/reviews`; GET `/staff/quality/samples/{sample_id}/history` | 자료/평가는 AGENT/ADMIN 모두 QUALITY_REVIEW+**본인 지정**+현재 검토 팀 scope. ADMIN 관리 권한만으로 자료 열람 불가. 목록/이력은 관리 범위 또는 본인 지정 범위 | 같은 문서, [요청 모음](examples/frontend-requests.json) |
| 품질 지표 | GET `/staff/quality/metrics` | ADMIN+QUALITY_METRICS_READ+선택 팀 scope. 미귀속/legacy 불명 전역 건수는 추가 QUALITY_UNATTRIBUTED_MANAGE와 include_unattributed=true | [100건 합성 지표](examples/quality-metrics.json) |
| 배정 추천 | GET `/staff/assignment-recommendations` | ADMIN+ASSIGNMENT_RECOMMEND+현재 활성 route 팀 scope. 미라우팅 티켓 지정은 UNROUTED_QUEUE_READ 추가, 후보 없이 불추천 사유만 반환 | [assignment-recommendations.md](assignment-recommendations.md), [전체 응답](examples/assignment-recommendations.json) |

품질 `/rubrics`는 QUALITY_REVIEW 또는 ADMIN의 SAMPLE_MANAGE/METRICS_READ로 읽는다. 신규 상품 후속 담당자는 기존 규칙대로 활성 ADMIN 또는 팀 대기이며 AGENT에 상품 개선 권한을 확대하지 않는다. 담당/상태 변경은 기존 PATCH `/staff/followups/{action_id}`, POST `/staff/followups/{action_id}/status`를 사용한다. 표본 지정은 일반 티켓 상세/고객360 권한을 주지 않는다.

규범은 [API 계약](api-contract.md)과 [생성 OpenAPI](openapi.json)다. 후보/팀/상품/검토자 UUID는 권한 내 실제 응답·기존 참조 자료에서 선택해야 한다. `/auth/me`는 역할/본인 ID, `/staff/capabilities`는 권한명만 반환하며 팀/검토자 picker API로 오해하지 않는다. 필요한 선택 자료가 기존 화면/API에 없으면 A/Frontend와 제공 계약을 별도 협의한다. 없는 팀·직원 검색 endpoint를 추측해 만들지 않는다.

## 4. 권장 연결 순서와 최소 예시

모든 UUID/시각/결과는 **합성 설명용**이다. 아래 응답 중 ‘발췌’는 전체 DTO가 아니며, 실제 화면은 링크된 OpenAPI/전체 예시를 따른다. 이 절의 VOC/품질 변경 POST에는 매 업무 의도마다 생성한 `Idempotency-Key`(8–128자, 영문/숫자/`._:-`)를 보낸다. 자료 조회 POST만 멱등키 없이 purpose를 보낸다.

1. 기존 로그인 후 GET `/auth/me` → 직원이면 GET `/staff/capabilities`. AGENT 본인 업무량은 WORKLOAD_READ가 없어도 열고, ADMIN/품질 기능은 위 capability/지정 조건으로 구성한다.
2. **업무량부터:** GET `/staff/workload?limit=20`(ADMIN은 `team_id` 선택). 응답 발췌:

```json
{"as_of":"2026-11-04T03:00:00Z","view":"TEAM","items":[],"next_cursor":null}
```

`scope_totals`=선택 팀 전체, `page_totals`=현재 items만. agent_id 필터는 목록만 제한한다. 문의·WAITING_CUSTOMER·후속을 중복 합산하지 않는다. `unassigned.total`은 ‘유효 상담사 배정 없음’이며 자동 경로도 포함한다. `invalid_assignment_count`는 그 부분집합, by_handling_path 세 값의 합은 total이다. AGENT의 team_queue/unrouted=null은 미제공이지 팀 미배정0이 아니다. 기한은 저장값 기준 초과/2시간 임박이며 정식 SLA 준수율이 아니다.

3. **VOC:** TOP10의 상품 ID/게시 batch·scope를 출처로 쓸 수 있지만 수동 상품 선택도 가능하다. 신규 POST `/staff/voc-improvements`(예시 key `ui-voc-create-001`):

```json
{"followup":{"product_id":"11111111-1111-4111-8111-111111111111","owner_team_id":"22222222-2222-4222-8222-222222222222","owner_user_id":null,"kind":"PRODUCT_IMPROVEMENT","blocks_resolution":false},"plan":{"issue_code":"DAMAGED","improvement_text":"포장 점검 절차 개선","comparison_team_ids":["22222222-2222-4222-8222-222222222222"],"change_reason":"첫 개선 계획"}}
```

생성 receipt:

```json
{"action_id":"33333333-3333-4333-8333-333333333333","action_revision":1,"plan_revision":1,"ticket_id":null}
```

GET 목록/상세로 이어가고, 기존 후속 등록은 followup 대신 existing_action_id+expected_action_revision을 보내고 plan은 함께 보낸다. 계획/문의 연결에는 expected_action_revision과 expected_plan_revision 둘 다 필요하다. 계획은 PATCH가 아닌 **full snapshot** POST이며 생략 optional은null이므로 이전 값을 임의로 누락하지 않는다. 시행일/비교창은 미정이면 비울 수 있다. 창이 있으면 시행일+네 경계 모두, UTC aware `[start,end)`, 동일 길이/비중첩 검증이 필요하다. 14일은 편집 가능한 제안이다. DONE/CANCELLED 이후 사실 정정은 correction=true+사유의 제한 경로다. 상세 analysis는 현재 항상 아래와 같으며 기간이 지나도0/효과 성공으로 바꾸지 않는다.

```json
{"availability":"UNAVAILABLE","reason":"EFFECT_INTEGRATION_NOT_IMPLEMENTED","metrics":null}
```

4. **품질:** 관리자 rubrics→`candidates?origin=APPLICATION&limit=20`→POST `/staff/quality/samples`(key `ui-quality-select-001`):

```json
{"message_id":"11111111-1111-4111-8111-111111111111","rubric_version":"DEV_QUALITY_V1","review_team_id":"22222222-2222-4222-8222-222222222222","assigned_reviewer_id":"33333333-3333-4333-8333-333333333333"}
```

receipt는 `{"sample_id":"44444444-4444-4444-8444-444444444444","revision":1}`. 지정 reviewer가 목록에서 본인 표본을 골라 POST `/staff/quality/samples/{sample_id}/material`에 `{"purpose_code":"QUALITY_REVIEW"}`를 보낸다. 자료가 부족한 경우 평가 예시(POST 같은 sample의 `/reviews`, key `ui-quality-review-001`):

```json
{"expected_revision":1,"accuracy":"UNDETERMINABLE","policy_alignment":"UNDETERMINABLE","reason_codes":["INSUFFICIENT_CONTEXT"],"change_reason":"INITIAL_REVIEW"}
```

성공 receipt는 같은 sample_id의 revision2다. sample 목록의 current_revision 또는 마지막 receipt.revision을 사용하고 수정도 새 이력으로 POST한다. 담당 변경은 기존 평가를 지우지 않으며 VOID는 제외 이력을 남긴다. 지표 요청 예: GET `/staff/quality/metrics?response_start=2026-11-01T00:00:00Z&response_end=2026-11-04T00:00:00Z&rubric_version=DEV_QUALITY_V1&origin=APPLICATION`(team_ids는 반복 query). 평가일이 아닌 **응답 확정 기간** `[start,end)`의 현재 snapshot이다. 표본15정확/3오류/2판단불가라면 정확성15/18, 확인 가능한 전체100건이면 coverage20/100·미평가80이다. 정책 비적용/판단 불가/VOID와 미평가를 별도 표시한다. 분모0→null, 합성 원천은 SYNTHETIC 별도, 과거 as_of 조회는 미지원이다.

5. **추천:** GET `/staff/assignment-recommendations?limit=20&candidate_limit=3` 또는 `?ticket_id=<권한 내 티켓 UUID>`. 응답 발췌:

```json
{"as_of":"2026-11-04T03:00:00Z","expires_at":"2026-11-04T03:00:30Z","rule_version":"WORKLOAD_PRIORITY_V1","total":1,"items":[{"ticket_id":"11111111-1111-4111-8111-111111111111","cycle_no":1,"ticket_revision":2,"route_revision":2,"waiting_since":null,"recommendation_state":"AVAILABLE"}],"next_cursor":null}
```

HUMAN/HANDOFF_PENDING·현재 유효 배정 없음만 목록 대상이다. FAILED AUTO를 보존한 HUMAN도 가능하지만 AUTO 실행 중을 사람 대기로 추정하지 않는다. 업무는 초과→임박→나머지/기한/ID, 후보는 활성 AGENT/활성 route 소속 팀/정규화 scope/지원 category를 확인하고 유효 진행 문의 수→초과 문의 수→user_id로 정렬한다. 후보의 WAITING_CUSTOMER·후속은 분리 표시한다. waiting_since=null은 불명이며 route 기록으로 채우지 않는다. 만료/필터·scope 변경 시 재조회하고, CONDITIONAL의 물리 배정 정리 필요·UNAVAILABLE 이유를 표시한다. **실제 배정 버튼용 A 실행 API는 없고 30초는 예약/lease가 아니다.**

## 5. 공통 오류·revision·표시

- 문서의 HUMAN/HANDOFF_PENDING은 DB `requested_mode=HUMAN`, `status=HANDOFF_PENDING`이다. 고객용 공개 DTO에서는 `handling_mode=HUMAN`, `stage=WAITING_FOR_SUPPORT`로 표현한다. 티켓 DB 해결 상태는 RESOLVED이며 COMPLETED는 공개 stage다. 후속 DONE과 이 상태들을 혼용하지 않는다.
- ticket revision, 후속(action) revision, VOC plan revision, 품질 sample revision, route revision은 서로 다른 값이다. VOC 계획/문의 연결은 action revision을 올리지 않고, 담당/상태 변경은 후속 revision을 올린다. 품질 수정은 sample revision으로 경쟁을 확인한다.
- 멱등 namespace는 저장소별로 분리된다. 기존 접수/재문의/직접 연결/일반 후속 생성은 `idempotency_keys`, VOC CREATE/PLAN/LINK는 `voc_improvement_receipts`, 품질 SELECT/REVIEW/REASSIGN/VOID는 `quality_command_receipts`를 사용한다. 각 저장소 안에서는 사용자별 key가 작업/대상 전반에 공유되며, VOC/품질 key는 기존 저장소와 전역으로 공유되지 않는다. Frontend는 기능별·업무 의도별 새 key를 만들고 동일 재시도에는 유지한다.
- **동일 namespace 안에서** 같은 key+같은 경로/본문 재시도는 원래 결과(최초201/replay200). 다른 본문/경로에 같은 key를 쓰면409 IDEMPOTENCY_CONFLICT. 네트워크/503 후에는 같은 key/body로 제한 재시도하며, 성공을 못 봤다고 새 key로 중복 생성하지 않는다. 권한은 replay에도 현재 기준으로 재검사한다.
- 409 revision 충돌은 VOC 상세 또는 품질 **목록/이력**을 다시 읽고 사용자 의도 확인 후 최신 revision/새 key를 쓴다. 품질 GET `/samples/{sample_id}` 상세 API는 없다. 401 재인증, 403 권한/팀 확인, 404 없는/권한 밖을 동일 처리하며 다른 팀으로 우회하지 않는다. 422는 입력/시각/cursor를 수정하고 무한 재시도하지 않는다. X-Request-ID로 문의하되 원문/토큰은 로그에 남기지 않는다.
- no-store 응답과 reviewer 자료를 고객 캐시/분석 로그에 복제하지 않는다. 원문 패턴 마스킹은 개인정보 완전 제거 보장이 아니다. 자료 MISSING/UNKNOWN/REFERENCES_ONLY/INSUFFICIENT_MATERIAL/MATERIAL_CHANGED·truncated를 표시하고 누락 근거로 CORRECT/MATCH를 만들지 않는다.
- null은0이 아니다. 빈 items는 유효 조회 범위에 목록 없음, next_cursor=null은 끝, 계획 current_plan=null+plan_access는 권한/재확인 상태를 함께 표시한다. 숨긴 이력/문의 건수는 추정하지 않는다. 필터 변경 시 opaque cursor를 버리고 limit/후보 수 상한을 따른다. 각 페이지는 새 snapshot이므로 변경 중 페이지 전체를 하나의 고정 snapshot으로 설명하지 않는다.

## 6. 팀에서 받아야 할 것 / 아직 없는 것

| 담당 | 받을 데이터·다음 행동 | 아직 없는 것/합의 |
|---|---|---|
| B 준혁님 + A | 실제 commit_automatic_reply에 사용한 질문/message·job/ticket/cycle/revision, 선택 suggestion id/revision/hash·approval·model/prompt·retrieval 참조 전달. 추천 실행 직전 최신 route revision/팀·직원 자격·유효/물리 배정/lease·generation·PAUSED/CAS·멱등 재검사 | 내부 Python writer는 HTTP가 아니다. 실제 B 실패/HUMAN 전환/배정·서비스 인증 계약은 별도 검토이며 A 추천을 실행 권한으로 사용하지 않음. 구조화 회차/실패/사유 기록은 KPI 후속 합의 필요. [B 인수](backend-b-handoff.md) |
| AI/RAG + 운영 평가 책임자 | 실제 사용한 정책 문서 version/hash·검증 가능한 당시 본문/chunk·검색 snapshot, model/prompt 버전 제공. 운영 rubric·표본 추출/판정 기준 합의 | 누락은 MISSING/UNKNOWN, 과거 응답에 최신 정책을 추정 연결하지 않음. 실제 AI 품질/운영 정답률 미검증. [품질 계약](quality-review.md) |
| Fabric 주현님 + A | 게시 analytics-v1 배치/exact scope·상품 UUID/매핑·기간·판매량 분모·팀 귀속 합의, 실제 서비스 emitter→A 수신/검증/게시 확인 | 실제 VOC 전후 효과 모델/수신·조회·효과 계산·DB→Blob Export 미구현. 동일 길이 창·일별/UTC 경계·판매 없음·중첩/미성숙/자료 부족·인과 해석 별도 합의. 기존 `/analytics/batches`를 브라우저 사용자 토큰으로 호출하지 않음. [Fabric 인수](fabric-handoff.md) |
| 인수님 + A/배포·권한 담당 | 실제 target base/CORS·DB head/권한 확인 후 위 순서로 연결. 허용 팀/상품/검토자 선택 자료 경로 합의, 403/404/409/null/unavailable/만료 확인 | 실제 Frontend 화면/외부 연동·Azure 최신 배포 상태 미검증. 실제 배포·권한 부여는 별도 승인 작업 |

## 7. 인수님께 보낼 메시지 초안 (미발송)

```text
인수님, 요청하신 기능 중 A 쪽 업무량 조회·배정 추천, VOC 개선 등록/이력, AI 수동 평가 API를 구현하고 GitHub에 올렸습니다.
연결 방법과 권한·예시는 Frontend 인수 문서에 정리했습니다: https://github.com/InSSOOO/cs-flow-ai/blob/feature/backend-a/backend/backend-a/docs/frontend-handoff.md
새 API의 Azure 반영은 아직 확인되지 않았으며, 화면 연결 환경을 맞춰야 합니다.
VOC 전후 효과는 Fabric 연결, 실제 배정은 B 연결이 남아 있습니다.
```

이번 문서 점검: 실제 코드/OpenAPI의 경로·입출력 DTO·권한/CORS 설정과 예시·상대 링크·민감정보 패턴·diff를 확인했다. 업무/DB/외부 연동 테스트는 실행하지 않았고 과거 통과 수를 이번 결과로 재사용하지 않았다.

## 기존 화면 상세 계약 (이전 인수 내용 보존)

아래는 기존 고객/후속/분석/큐/보관 화면의 상세 참고다. 버전별 구현 당시 서술은 위 공유 기준과 구분하고, 배포 여부는2절의 선행 확인을 따른다.

규범 계약은 api-contract.md와 실제 코드에서 생성한 openapi.json입니다. 요청 모양은 examples/frontend-requests.json이며 `python -m scripts.check_handoff_contract`로 모델/endpoint/공개 DTO를 검사합니다. 예시 UUID는 실제 서버 상태가 아니므로 실행 중 응답 ID를 사용합니다. 토큰/비밀번호는 예시 파일에 넣지 않습니다.

0.7.0 업무량 화면은 `/auth/me`의 AGENT면 별도 grant 없이 `GET /staff/workload`로 본인만 조회합니다. ADMIN 팀 보기는 `/staff/capabilities`의 WORKLOAD_READ가 필요하고, 미라우팅은 추가 UNROUTED_QUEUE_READ가 있을 때만 include_unrouted=true로 요청합니다. `scope_totals`는 선택 팀 전체, `page_totals`는 현재 items뿐이며 agent_id도 목록만 제한합니다. team_queue/unrouted·invalid_assignment_count·waiting_customer를 총 문의 수에 다시 더하지 않습니다. [전체 응답 예시](examples/workload-response.json)는 합성 ADMIN의 agent_id 필터 사례입니다. 응답마다 as_of를 표시하고 scope/필터 변경 시 cursor를 버리세요. 실제 Frontend/Azure 연결은 이번에 검증하지 않았습니다.

| 역할 | endpoint와 조건 |
|---|---|
| 고객 | /auth/login, /auth/me, /orders, /tickets 및 reopen/request-agent, /followups. 본인 공개 정보만 |
| 업무량(0.7.0) | GET /staff/workload. AGENT는 별도 grant 없이 본인, ADMIN은 WORKLOAD_READ+현재 팀 scope. [요청/응답·카운트 계약](workload.md) |
| 상담사 | /tickets는 현재 유효 배정·팀·category·회차, /staff/followups CRUD와 고객360은 같은 권한 범위. 예외 큐는 별도 명시 권한/현재 route만 |
| 관리자 | 허용 팀 직원 후속/고객360, /admin/analytics의 KPI/VOC/상세. 전사 fallback 없음 |
| 게시 서비스 | /analytics/batches 별도 서비스 JWT. 브라우저에 키/토큰을 배포하지 않음 |

티켓 상세/목록의 revision을 티켓 expected_revision에 사용하고, FollowupStaff.revision은 후속 수정/상태 변경에 사용합니다. 서로 다른 토큰이며 후속 수정만으로 ticket revision이 올라가지 않습니다. create ticket 응답은 ticket_id/created_at이므로 상세를 다시 읽습니다. 이 문단의 Idempotency-Key 공통 namespace는 **기존 `idempotency_keys` 안의** 사용자별 접수/재문의/직접연결/일반 후속 생성만 뜻합니다. VOC와 품질은 위5절의 별도 receipt namespace를 사용하며 전체 API가 하나의 전역 namespace인 것은 아닙니다. 성공201, 같은 요청 재시도200/저장된 원래 결과, 다른 내용 같은키409입니다. revision409는 새 상세를 읽고 의도를 확인한 뒤 새 key/최신 token으로 요청합니다. 동일한 성공 재시도를 새 key로 바꾸지 않습니다.

FollowupPublic은 공개 메모/상태/기한/시각/원래 회차만 포함합니다. 직원 DTO에는 internal_note/책임 회차/담당/blocks_resolution/revision이 있습니다. 고객 캐시에 직원 DTO를 재사용하지 않습니다. needs_handover를 표시하며 담당자가 NULL이라고 큐에서 숨기지 않습니다. 후속 `status=DONE`이 티켓 DB `status=RESOLVED`(공개 DTO `stage=COMPLETED`)를 의미하지 않습니다. 서버의 명시적 해결 경로가 별도입니다. 사람 해결 엔진은 미구현이고 큐/내부 상세/중지 endpoint는6단계에 추가했습니다. 해당 권한과 DTO를 별도로 사용합니다.

고객360은 POST와 purpose_code가 필요합니다. 집계·최근5건·후속은 ‘허용된 이력’이며 고객 전체 이력이 아닙니다. facts3문장은 정형 사실이며 summary_contract.NOT_GENERATED를 AI 생성 성공으로 표시하지 않습니다.

분석의 미게시200은 UNAVAILABLE/NO_PUBLISHED_BATCH/meta=null, scope 없으면 SCOPE_NOT_PROVIDED입니다. LOW_SAMPLE/DATA_MISSING/QUALITY_BLOCKED의 점수·순위·밴드는NULL이며0으로 표시하지 않습니다. stale는 결과를 숨기는 명령이 아니라 기준시각/오래된 결과 표시입니다. LOCAL_SYNTHETIC은 합성 출처로 표시합니다. fixture 재문의0/proxy와 팀차원 없는 제품 KPI는 unavailable을 유지합니다.

TOP10의 batch_id와 선택 team_ids를 상세/추세에도 전달합니다. scope_key 자체를 제출해 권한을 얻을 수 없습니다. 과거 batch에도 현재 권한을 검사하므로403/404면 캐시를 폐기하고 새 scope로 조회합니다. API는 no-store이며 향후 캐시도 batch/scope/사용자·현재 권한을 포함해야 합니다. 점수는 관리 우선순위이지 불량률이나 결함 확정이 아닙니다. 판매 분모는 팀 공통입니다.

README의 로컬 체험과 verify를 사용합니다. 실제 React 화면·팀 Frontend와 연동한 결과는 미검증입니다. 그 화면이 없는 서버 기능을 호출하거나 테스트 배정을 실제 B 처리로 표시하면 안 됩니다.

### 기존 큐·내부 상세·중지 화면

GET /staff/capabilities의 권한명으로 버튼을 구성하되 모든 리소스 API가 다시 검증합니다. 기존 관리자 역할만 보고 미귀속/중지 버튼을 활성화하지 않습니다. ROUTED 큐는 EXCEPTION_QUEUE_READ+활성 팀(상담사는 category까지), UNROUTED는 관리자+UNROUTED_QUEUE_READ입니다. 큐/건수는 같은 reason/team/scope 필터를 사용하며 원문/고객 프로필이 없습니다. 큐에 보였다는 이유로 상세/고객360이 열릴 것으로 가정하지 않습니다. 상세404도 정상 권한 결과입니다.

POST /staff/tickets/{id}/internal은 purpose_code와 선택 include_history를 사용합니다. 기존 고객 TicketDetail 대신 StaffTicketDetail을 사용하고 직원 cache를 고객에게 재사용하지 않습니다. customer_ref로 고객360을 요청할 때도 purpose와 현재 범위를 다시 검사합니다. MISSING/SYNTHETIC_ONLY/과거·만료·버전 불일치/UNVERIFIED_LINKS·POLICY_INACTIVE를 구분합니다. CURRENT_RECORDED는 실행 승인 판정이 아니며 모든 usable_for_execution=false입니다. 초안 원문은 draft_exposed=false이고 중첩 JSONB·blob/정책 본문은 제공하지 않습니다.

GET /staff/automation-control와 /history는 AUTOMATION_READ, POST /stop은 AUTOMATION_STOP, /resume은 AUTOMATION_RESUME가 각각 필요하며 모두 ADMIN만 가능합니다. ticket/followup/route/control revision과 worker generation을 혼용하지 않습니다. 중지는 expected_revision+사유, 재개는 expected_revision+stopped_revision+재개 사유가 필요합니다.409면 상태를 다시 읽고 자동 재개하지 않습니다. 권한403, schema422, 상태 부재503을 처리합니다.

중지 중 큐의 PAUSED/RUNNING을 성공/숨김으로 표시하지 않습니다. 재개 뒤 RECLAIM_REQUIRED는 새 generation/token을 받은 재claim이 필요하다는 뜻입니다. HUMAN_REVIEW_REQUIRED/CONTROL_UNAVAILABLE도 명시적으로 표시합니다. 사람 요청·HANDOFF·후속·조회는 계속 사용할 수 있습니다. 중지 전에 이미 완료된 응답은 이력으로 남습니다. 외부 발송 중단 보장으로 표시하면 안 됩니다. 상세 상태·오류는 phase6-staff-queues-control.md/OpenAPI와 examples/frontend-requests.json을 따릅니다.

### 기존 보관 미리보기

POST /staff/retention/dry-run은 purpose/as_of/policy/scope를 사용합니다. ADMIN만 보고 버튼을 열지 말고 RETENTION_TEAM_REVIEW/GLOBAL_REVIEW를 각각 검사합니다. 실제 예시는 examples/frontend-requests.json, 상세는 phase7-retention-preview.md/OpenAPI입니다. 팀 보고에서 미지원 대상은 건수NULL(0 아님), 타팀/미귀속 숨김이며 글로벌 fallback하지 않습니다.

past_retention_count는 기간상 후보, candidate_count는 최종 판정 가능한 후보입니다. 현 모델에서는 법적 hold/JSON 참조 판정이 없어 최종 후보0이 정상이며 ‘데이터 없음/삭제 완료’로 표시하면 안 됩니다. BLOCKED/REQUIRES_DESIGN_CHANGE/undetermined/NOT_INSPECTED를 구분하고 UTC cutoff와 정책 제안 표시를 유지합니다. 결과는 PREVIEW_ONLY_NOT_DELETION_AUTHORIZATION이며 삭제 버튼/실행 승인으로 연결하지 않습니다. 원문/ID 목록은 없습니다. 실제 삭제 API는 없고 최소 감사만 추가됩니다.

### 과거 0.6.1 오류 수정 기록

scope/category/팀·배정 변경으로 상담사가 티켓에404를 받는 경우 처리 불가능한 배정이 예외 큐를 숨기지 않습니다. 관리자는 명시 route/허용 팀·capability 안에서만 해당 최소 큐 자료를 확인하며 그 사실로 상세/360 권한이 생기지 않습니다. 큐 목록/건수는 같은 조건입니다. 모든 페이지 cursor의 비정상 JSON 타입은422 INVALID_CURSOR이고500으로 재시도하지 않습니다. 날짜/UUID 두 문자열은 당시 해당 목록 cursor의 설명입니다. 신규 API에는 다른 cursor 형식이 있으므로 직접 구성/해석하지 말고 각 API의 서버 next_cursor를 그대로 사용합니다. 계약413/422 설명은 Python 범위에서 고정됐으며 에러코드/스키마는 유지됩니다.


## 과거 Azure 기록 (새 API 주소 안내 아님)

2026-11-03 배포/지정 이름 이전 기록은 [azure-deployment.md](azure-deployment.md)와 [azure-migration.md](azure-migration.md)에 보존돼 있다. 마지막 기록은0.6.1/0006이며 당시 CORS origin=[]·자동 처리 PAUSED·분석 NO_PUBLISHED_BATCH였다. 이 문서 작업에서는 실제 현재 값을 조회하지 않았다. 과거 주소/health/HTTPS 통과 수를0.10.0 신규 API 제공 증거로 사용하지 않는다. 계정·토큰·DB 접속 정보는 Frontend 인수 문서에 추가하지 않는다.
