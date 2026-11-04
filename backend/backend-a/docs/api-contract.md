# API와 Frontend 계약

0.11.0/0011: GET `/staff/quality/automation-metrics`는 ADMIN+QUALITY_METRICS_READ와 현재 scope의 전향적 AUTO 회차 진단입니다. `/analytics/voc-effects/batches` 및 validate/publish는 별도 voc-effects 서비스 권한, GET `/staff/voc-improvements/{action_id}/effects`는 기존 VOC 관리 권한입니다. [정확한 wire/분모/상태/멱등/부분 기록 계약](monitoring-effects.md)을 따릅니다. 기존 analytics-v1 wire/게시 pointer는 변경하지 않았습니다.

0.10.0/0010 로컬: GET `/staff/assignment-recommendations`는 ADMIN+ASSIGNMENT_RECOMMEND+현재 route 팀 scope의 읽기 전용 힌트입니다. 팀/티켓 필터·페이지/후보 제한·버전/만료·불추천 사유는 [실제 계약](assignment-recommendations.md)을 따릅니다. 기존 workload·품질·VOC·analytics-v1 API는 유지합니다.


0.9.0/0009: `/staff/quality`의 후보·표본·목적별 자료·수동 평가/담당/VOID·이력·지표를 추가했습니다. [권한·정확한 요청/응답·집계 계약](quality-review.md)을 따릅니다. QUALITY_SAMPLE_MANAGE/REVIEW/METRICS_READ/UNATTRIBUTED_MANAGE는 역할과 현재 팀/지정 조건을 함께 적용하며 기본 미부여입니다. 과거 as_of·전체 AI 정답률·자동 처리율/안전한 완료율을 제공하지 않습니다.


0.8.0/head0008: [VOC 상품 개선 조치 등록·계획 이력](voc-improvements.md)을 추가했습니다. `/staff/voc-improvements`와 상세/plans/tickets는 ADMIN+명시 VOC_IMPROVEMENT_MANAGE+현재 팀 scope가 필요합니다. 담당·상태는 기존 followup API가 정본이며 Fabric 효과 availability는 UNAVAILABLE/EFFECT_INTEGRATION_NOT_IMPLEMENTED, metrics=null입니다. 기존 analytics-v1 wire는 변경하지 않았습니다.


0.7.1/head0007: workload의 unassigned는 ‘유효 상담사 배정 없음’이며 자동 경로도 포함합니다. 기존 필드를 유지하고 `by_handling_path={automatic_path,human_assignment_waiting,unknown}`를 추가했습니다. 세 분류 합은 total이며 실제 AI 실행 여부를 뜻하지 않습니다. [근거·표시명·권한 계약](workload.md)을 따릅니다. 이번 보완에 새 migration은 없습니다.

기본 경로 `/api/v1`, bearer JWT, JSON 요청/응답, UTC ISO 8601 시각입니다. JWT role/customer_id claim을 신뢰하지 않고 매 요청 사용자 활성·역할·DB scope를 다시 조회합니다. Refresh/logout/password reset은 이번 범위가 아니며 만료 기본값은 30분입니다. 브라우저 토큰은 가능하면 메모리에 보관하고 저장 전략은 Frontend와 별도 합의합니다.

| 메서드/경로 | 동작 |
|---|---|
| POST /auth/login | login_name/password → access_token, token_type, expires_in |
| GET /staff/workload | 0.7.0: AGENT 본인 또는 WORKLOAD_READ ADMIN의 현재 업무량·팀 미배정/후속 대기. [세부 계약](workload.md) |
| GET /auth/me | user_id, login_name, role만 반환 |
| GET /orders | 고객 본인 주문 목록 |
| GET /orders/{order_id} | 고객 본인 주문 상세 |
| POST /tickets | message, 선택 order_id와 Idempotency-Key → ticket_id, created_at |
| POST /tickets/{ticket_id}/reopen | expected_revision, message로 본인 티켓 새 회차 생성 |
| POST /tickets/{ticket_id}/request-agent | expected_revision, message, reason_code로 사람 연결 요청 |
| GET /tickets | 공통 권한 SQL로 제한한 목록 |
| GET /tickets/{ticket_id} | 공개 진행 상태·처리 방식·최근 공개 메시지 최대50건 |
| GET /tickets/{ticket_id}/messages | 전체 공개 메시지의 페이지 조회 |
| GET /health/live | 프로세스 응답 여부, DB 불필요 |
| GET /health/ready | DB 접속과 Alembic revision0007 확인. AUTO 가능 여부는 별도 control gate |

응답에서 주문의 customer_id, 티켓의 내부 status/version/오류/라벨, 메시지의 approval_id/멱등키/내부 role, AI 근거·승인 snapshot을 제외합니다. TicketDetail에는 공개 MessagePublic만 포함합니다. staff에도 이 버전에서는 같은 공개 스키마를 사용합니다. stage는 업무 UI 값이며 내부 enum을 직접 화면에 표시하지 않습니다.

2단계에서 TicketPublic(목록/상세)에 공개 동시성 토큰 `revision`과 업무 회차 `cycle_no`를 추가했습니다. revision은 내부 version에 대응하지만 권한 근거로 사용하지 않습니다. 내부 job ID/token/lease/reason/승인 정보는 여전히 고객 응답에서 제외합니다. 메시지 구조와 공개 stage 매핑은 유지합니다.

| 내부 상태 | stage | 처리 방식 |
|---|---|---|
| OPEN | RECEIVED | AUTOMATED 기본 |
| PROCESSING | PROCESSING | AUTOMATED 기본 |
| WAITING_CUSTOMER | NEEDS_INFORMATION | 요청/해결 mode 기준 |
| HANDOFF_PENDING | WAITING_FOR_SUPPORT | HUMAN |
| ASSIGNED / IN_PROGRESS | IN_SUPPORT | HUMAN |
| FOLLOWUP_PENDING | FOLLOWUP | HUMAN |
| RESOLVED | COMPLETED | resolution_mode=AUTO면 AUTOMATED, HUMAN이면 HUMAN |
| CANCELLED | CANCELLED | 요청/해결 mode 기준 |

requested_mode=HUMAN 또는 resolution_mode=HUMAN이면 HUMAN입니다. 자동 경로의 화면에 상담사 승인 대기 단계를 추가하지 않습니다. 안내 완료는 실제 환불/배송/반품 실행 완료를 의미하지 않습니다. 이 매핑은 이번 구현 제안으로 세부 문구·상태 전이는 팀 검토가 필요합니다.

목록은 `limit=1..100`(기본20), `cursor`를 받고 `items`, `next_cursor`를 반환합니다. 주문은 placed_at DESC, order_id DESC, 티켓은 created_at DESC, ticket_id DESC입니다. 메시지 목록은 created_at ASC, message_id ASC입니다. timestamp와 UUID를 함께 사용하는 keyset 정렬로 같은 시각도 안정적으로 처리합니다. cursor는 서명이 없는 불투명 위치값이며 권한을 포함하지 않습니다. 변조해도 매번 동일 scope가 적용됩니다. cursor는 같은 API에만 재사용하고 next_cursor=null에서 멈춥니다. 스냅샷 격리를 보장하는 페이지 계약은 아닙니다.

상세 messages는 최신50건을 시간순으로 반환합니다. `messages_has_more=true`이면 메시지 목록 API를 처음부터 순회해 전체 이력을 구성합니다. 페이지 cursor를 상세에 붙이는 계약은 아닙니다.

## 멱등과 오류

접수 key는 사용자별로 유일합니다. 공백을 trim한 메시지와 정규화 UUID/null을 정렬 JSON으로 해시하므로 의미가 같은 요청은 같은 결과입니다. 최초 201, 재시도 200이며 `Idempotency-Replayed` 헤더와 `Location`을 제공합니다. 동일 key에 다른 정규화 요청이면 409입니다. 성공한 key는 이번 버전에서 만료·재사용하지 않습니다. 화면은 접수 성공을 확인할 때까지 같은 key를 유지하고 새 문의에는 새 key를 만듭니다.

```json
{"error":{"code":"RESOURCE_NOT_FOUND","request_id":"correlation-uuid"}}
```

| HTTP | 기준 |
|---|---|
| 401 | 토큰 누락/손상/만료, 로그인 실패, 비활성 사용자. WWW-Authenticate: Bearer |
| 403 | 인증됐으나 고객 전용 기능에 staff 접근, 고객 프로필 사용 불가 |
| 404 | 없는 리소스 또는 본인/팀/배정 범위 밖 리소스. 존재 여부 숨김 |
| 409 | 멱등키 충돌, 주문 상품 매핑 불가, revision 경쟁, 금지 전이, 이미 사람 연결 진행 중 |
| 422 | UUID·길이·공백·추가필드·페이지/cursor·헤더 유효성 오류 |
| 503 | DB 접속/트랜잭션 오류, readiness 미준비 |
| 500 | 예상하지 못한 애플리케이션 실패, 원문 미포함 |

검증 오류에 제출 원문을 반사하지 않습니다. `X-Request-ID`는 서버가 생성하며 로그에는 ID와 상태코드만 기록합니다. TrustedHost/CORS 같은 프레임워크 middleware의 프로토콜 거부(400/사전요청)는 이 도메인 오류 envelope 적용 대상이 아닙니다. 요청 크기 제한·로그인 rate limit은 운영 ingress/WAF 설정 또는 후속 보안 작업으로 남깁니다.

권한 거부는 요청 세션 rollback/close 후 별도 트랜잭션으로 audit_events에 저장합니다. DB 자체 장애에서는 DB 감사 저장을 보장할 수 없어 고정 운영 신호 `audit_persistence_unavailable`을 남깁니다. 외부 내구 감사 sink·보존/삭제 주기·접근 통제는 운영 연동 후속 범위입니다.

## 재문의와 직접 연결 요청

두 API는 고객 전용입니다. 타인/없는 티켓은 404, staff 요청은 403입니다. `Idempotency-Key` 형식은 접수와 같으며 user별로 **접수·재문의·직접 연결 전체에서 공유하는 namespace**입니다. 다른 endpoint/티켓/reason/expected_revision/body에 같은 key를 사용하면 IDEMPOTENCY_CONFLICT입니다.

재문의 body는 `{"expected_revision": 1, "message": "추가 확인 요청"}`입니다. 직접 연결은 여기에 필수 reason_code를 추가합니다. reason_code는 CUSTOMER_REQUEST, DISSATISFIED, COMPLEX_ISSUE, OTHER 중 하나이며 message는 trim 후 1–10000자입니다. 고객이 role/customer_id/job_kind/lease를 제출하는 것은 422입니다.

성공 응답은 ticket_id, cycle_no, revision, stage(RECEIVED 또는 WAITING_FOR_SUPPORT), handling_mode, requested_at입니다. 201과 Location을 반환하고 같은 요청의 재시도는 200, Idempotency-Replayed=true와 **저장된 원래 응답**을 반환합니다. 이후 회차가 바뀌어도 replay 결과는 최신 상태로 바뀌지 않으므로 화면은 상세를 다시 조회합니다.

TICKET_REVISION_CONFLICT이면 GET으로 revision을 갱신하고 사용자의 의사를 확인해 새 key로 재요청합니다. 네트워크 실패 재시도는 body/revision/key를 그대로 유지합니다. 이미 HANDOFF_PENDING/ASSIGNED/IN_PROGRESS/FOLLOWUP_PENDING 또는 HUMAN WAITING_CUSTOMER이면 새 직접 연결은 HUMAN_REQUEST_ALREADY_ACTIVE(409)이며 새 메시지/배정 작업을 만들지 않습니다. 같은 성공 key 재시도는 이 검사보다 먼저 replay하므로 200입니다. 추가 요청 내용은 재문의로 제출합니다.

재문의는 CANCELLED 이외의 허용 상태에서 새 회차를 만들고 이전 미완료 작업을 취소합니다. 사람 경로의 재문의는 WAITING_FOR_SUPPORT/HUMAN으로 유지합니다. Frontend는 처리 방식을 임의로 AUTO로 덮어쓰지 않습니다. 상세 전이 표와 양쪽 경합 결과는 [2단계 설계](phase2-cycles.md)를 따릅니다.

## 3단계 후속과 고객360 Frontend 계약

세부 URI/필드/전이 표는 [3단계 설계](phase3-followups-customer360.md)를 따릅니다. 고객은 `/followups`의 공개 DTO만 사용하고 직원용 DTO/URI를 재사용하지 않습니다. 공개 메모가 없는 내부 후속과 상품 후속은 고객에게 표시하지 않습니다.

직원은 POST/GET `/staff/followups`, GET/PATCH/DELETE `/staff/followups/{action_id}`, POST `/staff/followups/{action_id}/status`를 사용합니다. 생성 응답은 action_id/revision/created_at이며 Location으로 상세를 조회합니다. 생성 Idempotency-Key는 기존 전역 사용자 namespace를 공유합니다. 변경 expected_revision은 **후속 revision**이며 ticket revision과 다릅니다. 충돌은 409 FOLLOWUP_REVISION_CONFLICT입니다. DONE/CANCELLED는 수정/재개하지 않습니다.

DELETE body는 `{"expected_revision":1,"cancellation_reason":"OTHER"}`이며 취소된 행도 이력에 남습니다. 상태 API는 expected_revision/status와 CANCELLED일 때만 cancellation_reason을 보냅니다. 완료시각/취소시각을 클라이언트가 지정하지 않습니다. BLOCKING 필드/소유자/원래 회차를 상태 값으로 추측하지 않습니다.

직원 목록의 needs_handover를 별도 표시하고 owner_user_id=NULL/비활성인 행을 화면에서 필터로 숨기지 않습니다. 티켓 재문의 후에도 후속 원래 cycle_no는 유지됩니다. 현재 유효 담당자는 PATCH의 owner_user_id를 자기 ID로 지정해 responsibility_cycle_no를 현재 회차로 인수합니다. 다른 팀 인수에는 양쪽 팀 scope의 관리자가 필요합니다. 인수 전 완료는 409 FOLLOWUP_TAKEOVER_REQUIRED입니다. 마지막 후속 완료만으로 티켓 화면을 COMPLETED로 바꾸지 않습니다.

고객360은 POST `/staff/customers/{customer_id}/360`와 목적 body를 사용합니다. ACTIVE_SUPPORT/FOLLOWUP_REVIEW, 관리자 QUALITY_REVIEW만 허용하며 고객 계정은 403입니다. 해당 직원에게 보이는 티켓이 0개이면 404입니다. 최근5건/미해결5건/후속20건은 일부 목록이므로 전체는 동일 prefix의 `/tickets`, `/followups` POST 페이지로 조회합니다. 티켓 이력에는 unresolved_only 필터가 있습니다. 집계 수치를 고객 전체 수치로 바꿔 표시하지 말고 ‘허용된 이력’이라고 표시합니다.

PostgreSQL은 인증부터 동일 REPEATABLE READ snapshot을 사용하고 as_of는 DB 트랜잭션 시작 시각입니다. 별도 상세 요청에서 배정 변경으로 404가 나면 목록/캐시를 새로 조회해야 합니다. summary_contract.status=NOT_GENERATED와 정형 사실 3줄을 생성형 AI 요약 성공으로 표시하지 않습니다. external_input은 숫자 사실만, sources는 별도 직원용 출처입니다.

## 4단계 관리자 분석 화면

GET `/admin/analytics/voc/top`, `/voc/unavailable`, `/products/{product_id}`, `/kpi`입니다. 실제 [OpenAPI](openapi.json)의 VocList/ProductDetail/KpiResponse를 사용합니다. 고객·상담사는403, 관리자는 매번 현재 활성 팀 scope를 검사합니다. 기본 범위는 허용 팀 전체이며 반복 query team_ids로 부분집합을 선택할 수 있습니다. scope_key를 보내도 선택/권한에 사용하지 않습니다. 정확한 집계 scope가 없으면 UNAVAILABLE/SCOPE_NOT_PROVIDED이며 ALL4로 대체하지 않습니다.

미게시200은 availability=UNAVAILABLE/reason=NO_PUBLISHED_BATCH/meta=null과 빈 items 또는 metrics=null입니다. 실패한 후보로 화면을 교체하지 않습니다. AVAILABLE meta에는 batch_id/source_as_of/window_end/rule/schema/source/선택scope/team_ids/published_at/generated_at/is_current/stale가 있습니다. stale 기본24시간을 기준으로 이전 결과임을 표시하고 실제 운영 시각으로 바꾸지 않습니다. LOCAL_SYNTHETIC은 합성 결과로 표시하며 FABRIC도 서비스 선언임을 origin_verification으로 구분합니다.

목록에서 받은 batch_id와 선택 team_ids를 상품 상세·추세 요청에도 전달해 화면 배치를 고정합니다. 과거 성공 배치에도 현재 권한을 검사하므로 권한 변경404/403 시 재조회합니다. 미게시 batch_id는404입니다. 서버는 한 응답에서 인증·포인터·집계·상세·메타데이터를 동일 REPEATABLE READ로 읽습니다. 응답은 no-store이며 향후 캐시도 사용자/현재권한/batch/scope를 포함하고 hit 전 권한을 검사해야 합니다. 운영 티켓·고객360 이동 시 해당 리소스 권한을 다시 확인합니다.

TOP10은 해당 scope의 제공 rank≤10이며 전체팀 TOP10에서 일부 행을 숨기거나 팀 점수를 합산하지 않습니다. unavailable 목록은 LOW_SAMPLE/DATA_MISSING/QUALITY_BLOCKED이며 score/rank/risk_band가NULL입니다. NULL을0으로 렌더링하지 않습니다. 표본 C/P/S/N/M/U/K, outside_cohort/excluded_count, coverage flags와 components를 함께 제공합니다. 제공된 trend도 같은scope이며 없는 날짜를 실제0으로 추정하지 않습니다. 판매분모는 팀 공통 상품28일 주문이며 점수는 관리 우선순위이지 불량률·결함 확정이 아닙니다.

KPI는 ticket 생성 cohort 기준 제공 행의 합이고 비율 분모 ticket_count, 평균은 duration_sum_seconds/duration_n입니다. 메시지·회차·episode로 바꾸어 표시하지 않습니다. 부분scope의 ATTRIBUTED_TEAM_ROWS_ONLY는 미귀속 AUTO를 제외합니다. SYNTHETIC_APPROXIMATION은 실제 성과가 아닙니다. reopened/approval/review/sla의 UNAVAILABLE와 reason을 그대로 표시하고 raw rows의 고정0/proxy를 성과 카드로 사용하지 않습니다. 제품 KPI는 팀차원 부재로 부분 팀 UNAVAILABLE이며 tag grain 합계를 고유 티켓으로 표시하지 않습니다. nullable 주문분모를0으로 채우지 않습니다. 분석 스키마는 후속 메모·원문을 포함하지 않습니다.

서비스 `/analytics/batches` 수신·검증·게시 API는 브라우저용이 아니며 관리자 JWT로도 사용할 수 없습니다. Frontend에 서비스 키/토큰을 전달하지 않습니다. 상세 검증·미정 정책은 [4단계 설계](phase4-analytics.md)를 따릅니다.

score는 소수 정밀도 보존을 위해 JSON 소수 문자열이고 rank는 정수입니다. 응답의 data_status/coverage flags와 C/S/K로 표본·제외 조건을 표시하며 outside_cohort는 판매 cohort 밖 문의 주문 수입니다. 원본의 excluded_count는0이며 별도의 상세 제외 사유코드는 제공하지 않습니다. 향후 추가 제외가 생기는 경우 코드별 집계 필드를 Fabric과 합의해야 하며 현재 수치만으로 미제공 원인을 만들어 표시하지 않습니다.

## 5단계 로컬 인수 확인

frontend-handoff.md와 examples/frontend-requests.json을 함께 전달합니다. scripts.check_handoff_contract가 실제 endpoint/요청 모델/공개 DTO whitelist와 생성 OpenAPI를 검사하고, scripts.http_integration은 실제 Uvicorn의 /openapi.json이 로컬 생성 파일과 완전히 같은지 확인합니다. 인증 없는 테스트/배정/확정 endpoint는 추가하지 않았습니다. GET /tickets는 상담사 현재 배정 목록이며 아직 미배정 예외 큐가 아닙니다. 직원 내부 티켓 근거 상세·긴급 중지 API도 아직 없어 Frontend가 임의 경로를 호출하면 안 됩니다. 전체 누락은 backend-a-handoff.md에 구분했습니다.

## 6단계 현재 계약

위5단계의 큐/내부 상세/중지 미구현 표기는 이 절로 대체합니다. GET /staff/capabilities, GET /staff/exception-queue와 /counts, POST /staff/tickets/{ticket_id}/internal, GET /staff/automation-control와 /history, POST /stop·/resume를 추가했습니다. 정확한 OpenAPI·요청 예시는 생성 파일/examples/frontend-requests.json과 [6단계 설계](phase6-staff-queues-control.md)를 따릅니다.

큐는 EXCEPTION_QUEUE_READ+명시적인 현재 회차 route+팀(상담사는 category) 조건입니다. UNROUTED는 관리자+UNROUTED_QUEUE_READ를 별도로 요구합니다. 기본 관리자/여러 팀/종료 배정/카테고리만으로 전사 열람하지 않습니다. 목록/건수/필터는 같은 권한 집합이며 고객 프로필/원문은 없습니다. 큐 열람은 내부 상세나 고객360 권한이 아닙니다. ROUTED/UNROUTED·reason·team_id·cursor/limit를 그대로 유지하고 전사 fallback하지 않습니다.

내부 상세는 현재 티켓 권한과 purpose_code를 다시 확인합니다. StaffTicketDetail/ProposalFact/GateFacts 등 중첩 allowlist는 공개 DTO와 분리되고 raw JSONB/초안/프롬프트/토큰/비밀번호/연결정보를 반환하지 않습니다. customer_ref는 권한 내 고객360 이동 키이며 그 API도 재검증합니다. 합성·과거·만료·불일치/미검증 근거를 표시하고 CURRENT_RECORDED도 실행 승인으로 사용하지 않습니다. usable_for_execution=false입니다.

전역 제어는 관리자+각 AUTOMATION_READ/STOP/RESUME의 명시 권한입니다. GET은 상태/history, stop은 expected_revision+SAFETY_INCIDENT/OPERATOR_PAUSE, resume은 expected_revision+stopped_revision+INCIDENT_RESOLVED/VERIFICATION_COMPLETE입니다. 역할만으로 제어하지 않으며 body의 team_id/generation/임의 권한은422입니다. 변경/이력/감사는 원자적이고409는 상태를 다시 읽어 처리합니다. 상태 부재503이며 자동 경로를 허용하지 않습니다.

PAUSED는 AUTO 대기, RECLAIM_REQUIRED는 새 token/generation 재claim 필요, HUMAN_REVIEW_REQUIRED는 실패 검토, CONTROL_UNAVAILABLE는 자동 실행 차단입니다. 사람 요청·HANDOFF·사람 해결/후속/조회는 유지합니다. 중지 전 이미 확정된 응답은 보존합니다. 실제 외부 발송 취소/중단까지 보장하는 API가 아닙니다. 새권한403/객체범위404/제어revision409/schema422/상태503에 기존 오류 envelope를 사용합니다.

## 7단계 보관 검토 (현재)

POST /staff/retention/dry-run은 [7단계 규범](phase7-retention-preview.md)을 따릅니다. ADMIN+RETENTION_TEAM_REVIEW 또는 별도 RETENTION_GLOBAL_REVIEW, purpose_code=RETENTION_REVIEW와 timezone 있는 as_of가 필요합니다. TEAM의 team_ids는 활성 허용 팀 부분집합, GLOBAL은 team filter 금지입니다. 기본 관리자는403이고 권한 grant는 자동화하지 않습니다.

DEV_RETENTION_V1의 raw_days30/aggregate_days90은 제안이며1–3650 정수로 검증합니다. 엄격한 UTC24시간 경과(<, 동일 시각 보존), 활동/저장 시계·cutoff·policy_hash를 반환합니다. past_retention_count(기간상 후보)/blocked/design/undetermined와 최종 후보를 혼동하지 않습니다. JSON 참조·hold 판정 부재로 최종 원문 후보0이며 삭제 승인이 아닙니다. 미지원 팀 저장소의 건수는NULL이고 숨겨진 타팀/미귀속 개수도 제공하지 않습니다.

응답은 dry_run=true/PREVIEW_ONLY_NOT_DELETION_AUTHORIZATION/고정 inventory/집계/미검사·판단 한계뿐입니다. 원문·메모·프로필·후보ID 목록이 없습니다. 추가 SQL/경로/URL/execute/force 필드는422, DB 장애503입니다. 업무 데이터 변경 없이 최소 감사1행만 추가합니다. 같은 REPEATABLE READ snapshot에서 권한·집계를 읽으며 fingerprint는 실행 토큰이 아닙니다. 실삭제 API·SQL·예약·외부 저장소 접속은 없습니다.

## 0.6.1 독립 검토 수정

숫자/객체/null 등 cursor JSON 원소는422 INVALID_CURSOR이며 날짜·UUID 두 문자열만 파싱합니다. tickets/orders/messages/후속/예외 큐/고객360 페이지에 같은 parser를 사용합니다. 유효 배정은 현재 회차·배정 시각/종료·활성 AGENT/팀·사용자 팀·정규화 scope/category·티켓 stage 공통 정책으로 판정하며 큐 노출이 내부 접근 권한을 늘리지 않습니다. HTTP413/422 description은 Content Too Large/Unprocessable Content로 명시하여 Python 버전 차이를 없앴고 필드·인증·스키마 전체 비교는 유지합니다. 자세한 재현/수정은 review-fixes.md를 따릅니다.


## 2026-11-03 Azure 이름 이전 후 현재 환경

API base는 https://csflow-backend-a.azurewebsites.net/api/v1, PG는 csflow-backend-a-pg.postgres.database.azure.com/backend_a, Plan은csflow-backend-a-plan이다. source0.6.1/head0006과 기존 모든행/계정/권한·자동중지를 보존했다. 구3개 삭제·공용잠금 복원과 실제검증/백업은[azure-migration.md](azure-migration.md)를 따른다. B·AI·Fabric·발송은미연결/미검증이고 실제 Frontend origin은추측해등록하지 않았다. 서비스 인증 비밀값이나 DBpassword는이문서에없다.
