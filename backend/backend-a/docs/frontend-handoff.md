# Frontend 로컬 인수

0.8.0: [VOC 상품 개선 API 계약·요청/응답](voc-improvements.md). capabilities의 VOC_IMPROVEMENT_MANAGE를 확인하고 상품 후속 신규 생성 또는 existing_action_id 등록을 연결합니다. 상세의 action/plan revision을 따로 보관하고 POST의 Idempotency-Key를 유지하세요. 담당/상태는 기존 followup API로 변경합니다. plan_refresh_required와 숨겨진 과거 scope, 효과 분석 미구현/null을 표시합니다. 화면은 이번에 구현하지 않았습니다.


0.7.1 미배정 표시: `team_queue.unassigned.total`은 **‘유효 상담사 배정 없음’**으로 표시합니다. 전체를 ‘사람 배정 대기’라고 부르지 마세요. 새 `by_handling_path.automatic_path`는 ‘자동 처리 경로’, `human_assignment_waiting`은 ‘사람 배정 대기’, `unknown`은 ‘기타·판별 불가’입니다. 세 값의 합이 total이며 invalid_assignment_count는 별도 부분집합입니다. 전역 unrouted에도 같은 분류가 있습니다. FAILED/RETRY/PAUSED만 보고 사람 대기로 바꾸거나 자동 경로를 ‘AI 실행 중’으로 표시하지 않습니다. 기존 권한·snapshot·scope/page 합계 계약은 유지합니다.

규범 계약은 api-contract.md와 실제 코드에서 생성한 openapi.json입니다. 요청 모양은 examples/frontend-requests.json이며 `python -m scripts.check_handoff_contract`로 모델/endpoint/공개 DTO를 검사합니다. 예시 UUID는 실제 서버 상태가 아니므로 실행 중 응답 ID를 사용합니다. 토큰/비밀번호는 예시 파일에 넣지 않습니다.

0.7.0 업무량 화면은 `/auth/me`의 AGENT면 별도 grant 없이 `GET /staff/workload`로 본인만 조회합니다. ADMIN 팀 보기는 `/staff/capabilities`의 WORKLOAD_READ가 필요하고, 미라우팅은 추가 UNROUTED_QUEUE_READ가 있을 때만 include_unrouted=true로 요청합니다. `scope_totals`는 선택 팀 전체, `page_totals`는 현재 items뿐이며 agent_id도 목록만 제한합니다. team_queue/unrouted·invalid_assignment_count·waiting_customer를 총 문의 수에 다시 더하지 않습니다. [전체 응답 예시](examples/workload-response.json)는 합성 ADMIN의 agent_id 필터 사례입니다. 응답마다 as_of를 표시하고 scope/필터 변경 시 cursor를 버리세요. 실제 Frontend/Azure 연결은 이번에 검증하지 않았습니다.

| 역할 | endpoint와 조건 |
|---|---|
| 고객 | /auth/login, /auth/me, /orders, /tickets 및 reopen/request-agent, /followups. 본인 공개 정보만 |
| 업무량(0.7.0) | GET /staff/workload. AGENT는 별도 grant 없이 본인, ADMIN은 WORKLOAD_READ+현재 팀 scope. [요청/응답·카운트 계약](workload.md) |
| 상담사 | /tickets는 현재 유효 배정·팀·category·회차, /staff/followups CRUD와 고객360은 같은 권한 범위. 예외 큐는 별도 명시 권한/현재 route만 |
| 관리자 | 허용 팀 직원 후속/고객360, /admin/analytics의 KPI/VOC/상세. 전사 fallback 없음 |
| 게시 서비스 | /analytics/batches 별도 서비스 JWT. 브라우저에 키/토큰을 배포하지 않음 |

티켓 상세/목록의 revision을 티켓 expected_revision에 사용하고, FollowupStaff.revision은 후속 수정/상태 변경에 사용합니다. 서로 다른 토큰이며 후속 수정만으로 ticket revision이 올라가지 않습니다. create ticket 응답은 ticket_id/created_at이므로 상세를 다시 읽습니다. Idempotency-Key는 사용자별 접수/재문의/직접연결/후속 생성의 전역 namespace입니다. 성공201, 같은 요청 재시도200/저장된 원래 결과, 다른 내용 같은키409입니다. revision409는 새 상세를 읽고 의도를 확인한 뒤 새 key/최신 token으로 요청합니다. 동일한 성공 재시도를 새 key로 바꾸지 않습니다.

FollowupPublic은 공개 메모/상태/기한/시각/원래 회차만 포함합니다. 직원 DTO에는 internal_note/책임 회차/담당/blocks_resolution/revision이 있습니다. 고객 캐시에 직원 DTO를 재사용하지 않습니다. needs_handover를 표시하며 담당자가 NULL이라고 큐에서 숨기지 않습니다. DONE이 티켓 COMPLETED를 의미하지 않습니다. 서버의 명시적 해결 경로가 별도입니다. 사람 해결 엔진은 미구현이고 큐/내부 상세/중지 endpoint는6단계에 추가했습니다. 해당 권한과 DTO를 별도로 사용합니다.

고객360은 POST와 purpose_code가 필요합니다. 집계·최근5건·후속은 ‘허용된 이력’이며 고객 전체 이력이 아닙니다. facts3문장은 정형 사실이며 summary_contract.NOT_GENERATED를 AI 생성 성공으로 표시하지 않습니다.

분석의 미게시200은 UNAVAILABLE/NO_PUBLISHED_BATCH/meta=null, scope 없으면 SCOPE_NOT_PROVIDED입니다. LOW_SAMPLE/DATA_MISSING/QUALITY_BLOCKED의 점수·순위·밴드는NULL이며0으로 표시하지 않습니다. stale는 결과를 숨기는 명령이 아니라 기준시각/오래된 결과 표시입니다. LOCAL_SYNTHETIC은 합성 출처로 표시합니다. fixture 재문의0/proxy와 팀차원 없는 제품 KPI는 unavailable을 유지합니다.

TOP10의 batch_id와 선택 team_ids를 상세/추세에도 전달합니다. scope_key 자체를 제출해 권한을 얻을 수 없습니다. 과거 batch에도 현재 권한을 검사하므로403/404면 캐시를 폐기하고 새 scope로 조회합니다. API는 no-store이며 향후 캐시도 batch/scope/사용자·현재 권한을 포함해야 합니다. 점수는 관리 우선순위이지 불량률이나 결함 확정이 아닙니다. 판매 분모는 팀 공통입니다.

README의 로컬 체험과 verify를 사용합니다. 실제 React 화면·팀 Frontend와 연동한 결과는 미검증입니다. 그 화면이 없는 서버 기능을 호출하거나 테스트 배정을 실제 B 처리로 표시하면 안 됩니다.

## 6단계 화면 연결

GET /staff/capabilities의 권한명으로 버튼을 구성하되 모든 리소스 API가 다시 검증합니다. 기존 관리자 역할만 보고 미귀속/중지 버튼을 활성화하지 않습니다. ROUTED 큐는 EXCEPTION_QUEUE_READ+활성 팀(상담사는 category까지), UNROUTED는 관리자+UNROUTED_QUEUE_READ입니다. 큐/건수는 같은 reason/team/scope 필터를 사용하며 원문/고객 프로필이 없습니다. 큐에 보였다는 이유로 상세/고객360이 열릴 것으로 가정하지 않습니다. 상세404도 정상 권한 결과입니다.

POST /staff/tickets/{id}/internal은 purpose_code와 선택 include_history를 사용합니다. 기존 고객 TicketDetail 대신 StaffTicketDetail을 사용하고 직원 cache를 고객에게 재사용하지 않습니다. customer_ref로 고객360을 요청할 때도 purpose와 현재 범위를 다시 검사합니다. MISSING/SYNTHETIC_ONLY/과거·만료·버전 불일치/UNVERIFIED_LINKS·POLICY_INACTIVE를 구분합니다. CURRENT_RECORDED는 실행 승인 판정이 아니며 모든 usable_for_execution=false입니다. 초안 원문은 draft_exposed=false이고 중첩 JSONB·blob/정책 본문은 제공하지 않습니다.

GET /staff/automation-control와 /history는 AUTOMATION_READ, POST /stop은 AUTOMATION_STOP, /resume은 AUTOMATION_RESUME가 각각 필요하며 모두 ADMIN만 가능합니다. ticket/followup/route/control revision과 worker generation을 혼용하지 않습니다. 중지는 expected_revision+사유, 재개는 expected_revision+stopped_revision+재개 사유가 필요합니다.409면 상태를 다시 읽고 자동 재개하지 않습니다. 권한403, schema422, 상태 부재503을 처리합니다.

중지 중 큐의 PAUSED/RUNNING을 성공/숨김으로 표시하지 않습니다. 재개 뒤 RECLAIM_REQUIRED는 새 generation/token을 받은 재claim이 필요하다는 뜻입니다. HUMAN_REVIEW_REQUIRED/CONTROL_UNAVAILABLE도 명시적으로 표시합니다. 사람 요청·HANDOFF·후속·조회는 계속 사용할 수 있습니다. 중지 전에 이미 완료된 응답은 이력으로 남습니다. 외부 발송 중단 보장으로 표시하면 안 됩니다. 상세 상태·오류는 phase6-staff-queues-control.md/OpenAPI와 examples/frontend-requests.json을 따릅니다.

## 7단계 보관 검토

POST /staff/retention/dry-run은 purpose/as_of/policy/scope를 사용합니다. ADMIN만 보고 버튼을 열지 말고 RETENTION_TEAM_REVIEW/GLOBAL_REVIEW를 각각 검사합니다. 실제 예시는 examples/frontend-requests.json, 상세는 phase7-retention-preview.md/OpenAPI입니다. 팀 보고에서 미지원 대상은 건수NULL(0 아님), 타팀/미귀속 숨김이며 글로벌 fallback하지 않습니다.

past_retention_count는 기간상 후보, candidate_count는 최종 판정 가능한 후보입니다. 현 모델에서는 법적 hold/JSON 참조 판정이 없어 최종 후보0이 정상이며 ‘데이터 없음/삭제 완료’로 표시하면 안 됩니다. BLOCKED/REQUIRES_DESIGN_CHANGE/undetermined/NOT_INSPECTED를 구분하고 UTC cutoff와 정책 제안 표시를 유지합니다. 결과는 PREVIEW_ONLY_NOT_DELETION_AUTHORIZATION이며 삭제 버튼/실행 승인으로 연결하지 않습니다. 원문/ID 목록은 없습니다. 실제 삭제 API는 없고 최소 감사만 추가됩니다.

## 0.6.1 오류 수정

scope/category/팀·배정 변경으로 상담사가 티켓에404를 받는 경우 처리 불가능한 배정이 예외 큐를 숨기지 않습니다. 관리자는 명시 route/허용 팀·capability 안에서만 해당 최소 큐 자료를 확인하며 그 사실로 상세/360 권한이 생기지 않습니다. 큐 목록/건수는 같은 조건입니다. 모든 페이지 cursor의 비정상 JSON 타입은422 INVALID_CURSOR이고500으로 재시도하지 않습니다. 날짜/UUID 두 문자열인 서버 next_cursor를 그대로 사용합니다. 계약413/422 설명은 Python 범위에서 고정됐으며 에러코드/스키마는 유지됩니다.

## 2026-11-03 Azure 팀 개발 주소

API base https://csflow-backend-a.azurewebsites.net/api/v1, Swagger /docs. 기존 JWT/RBAC/공개·직원 DTO/revision 계약을 유지한다. production 로그인429 LOGIN_RATE_LIMITED에는 Retry-After를 따르고 자동 무한 재시도를 하지 않는다. 일반 body128KiB413 REQUEST_TOO_LARGE, 분석8MB 제한이다. CORS는 아직빈 목록으로 실제 Frontend 브라우저 연동은 미검증이며 확정된 HTTPS origin만 배포 담당자에게 반영 요청해야 한다. 체험 계정/비밀번호 전달 방법과 상태는 azure-deployment.md를 따른다. 자동 처리는 PAUSED, 분석은200 UNAVAILABLE/NO_PUBLISHED_BATCH/meta=null이다. 합성 배정·고정 응답을 실제 B/AI로 표시하지 않는다.


## 2026-11-03 지정 이름 이전 완료

새 이름3개로 실제 이전·검증하고 구3개 삭제 및 공용잠금 복원을 완료했다. API https://csflow-backend-a.azurewebsites.net/api/v1, Swagger /docs, PG csflow-backend-a-pg, Plan csflow-backend-a-plan이다. 현재 state는 .cache/azure-backend-a이며 기존 DB를 seed로 대체하지 않았다. 원본32테이블·모든기존행 보존, 기존상태HTTP16건/핵심HTTPS61건/도구6개검증은[실제 이전 보고](azure-migration.md)를 따른다. 기존 전체368개 재실행이 아니다.
