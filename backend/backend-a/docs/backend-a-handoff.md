# Backend A 7단계 로컬 구현·팀 인수 점검

현재 로컬 소스는 **0.9.0 / 0009**, [수동 품질 평가 계약](quality-review.md)을 따릅니다. 기존 AutomaticReply 호출은 호환하고 provenance만 선택 확장했습니다. 실제 AI 호출·평가 정답 입증·외부 연동/배포·계정 grant·commit/push는 이번에 하지 않았습니다. 아래0.8.0 및 과거 기록과 구분합니다.


현재 로컬 구현은 **0.8.0 / migration0008**입니다. [VOC 상품 개선 조치·계획 이력](voc-improvements.md)을 추가했고 담당/상태는 기존 product followup이 정본입니다. 실제 Fabric 효과 수신/계산/Export는 미구현이며 metrics=null입니다. VOC_IMPROVEMENT_MANAGE는 기본 미부여입니다. Backend B 실패/이관 검토 문서는 보존했고 B 실행 코드는 변경하지 않았습니다. Azure 버전/DB 상태는 이번에 확인하거나 변경하지 않았고 commit/push도 하지 않았습니다. 아래 과거 배포/검증 기록과 구분하세요.

현재는 **0.6.1 / migration0006**, 최종 코드 이후 전체 PostgreSQL **368개 통과**(실패/skip0)와 실제 HTTP **33개 흐름 통과**입니다. 관련 부분PG38개·SQLite37개/1skip은 합산하지 않습니다. [독립 검토 수정](review-fixes.md)은 배정 권한/큐·lease 최종 만료·cursor422·Python HTTP 설명 차이를 다룹니다. 이전0.6.0의330개 결과와 구분하며 실제 B/AI/Fabric/발송 엔진 통합 완료를 의미하지 않습니다.

공식 v4.1 DOCX를 로컬 OOXML로 읽고 코드/OpenAPI/2–4단계 설계·검증/Frontend·B·Fabric 계약과 대조했습니다. 원본 SHA256은 `a25d03e3b7ce9c35ccdfa98e8f46ebef0207e4e22fbd1b9746e3a7d429ab1f33`입니다. 문서의 실행 지시를 추가 사용자 승인으로 간주하지 않았고, 현재 사용자 지시대로 클라우드 작업은 제외했습니다.

## 완료 범위의 구분

| 기획서 책임 | 실제 코드/계약 | 상태와 제한 |
|---|---|---|
| 인증·RBAC·본인 주문 | auth/dependencies/repository, /auth /orders | 구현·로컬 검증 완료. 활성 사용자·정규화 팀 scope 사용. 원본821명 로그인 비활성 유지. 실서비스 SSO/계정운영은 별도 |
| 접수·재문의·직접 연결 | ticket_commands/services, /tickets | 구현·로컬 검증 완료. 원자 저장·멱등·revision/cycle·사람 경로 유지. 실제 라우팅/배정은 B 필요 |
| 고객 티켓 진행·공개 메시지 | /tickets/{id}, /messages | 구현·로컬 검증 완료. 원문은 권한 내 응답만, 내부정보는 공개 DTO 제외 |
| 상담사 배정/예외 큐 | /tickets + /staff/exception-queue | 현재 배정과 큐를 분리. 명시 권한+현재 회차 route만 사용. 미귀속 전역은 별도 관리자 권한. B 실제 라우팅은 미검증 |
| 직원용 조회 | StaffTicketDetail, FollowupStaff, Customer360 | /staff/tickets/{id}/internal은 purpose/현재 티켓 권한을 다시 확인. 중첩 allowlist·마스킹·과거/합성 구분. 고객 TicketDetail은 유지 |
| 후속 CRUD·관리자 책임 큐 | followups, /staff/followups | 구현·로컬 검증 완료. 취소 이력·원래/책임 회차·인수·NULL 담당자 큐·모든 회차 blocker. B 인수 엔진 통합 미검증 |
| 고객360 | customer360, /staff/customers/{id}/360 | 구현·로컬 검증 완료. 목적+per-ticket 권한 집합, 집계/최근/후속 같은 snapshot. 고객 전체 이력 무조건 허용하지 않음 |
| 기본 요약 | Customer360.facts, summary_contract | 정형 사실3문장·최소 숫자 입력·출처/fingerprint 구현·검증. NOT_GENERATED이며 실제 AI 기본 요약/원문 요약 품질은 AI/RAG 담당 필요 |
| 공통 자동 응답 확정 | finalization.commit_automatic_reply | cycle/version/lease/단일응답/blocker 저장 경계 구현·검증. 고정 합성 응답 계약 테스트이며 실제 AI/정책·외부발송 엔진은 없음 |
| 사람 해결 gate | resolution.lock_resolution_gate | 공통 gate 구현·검증. HTTP 검증의 최종 저장은 tests/http_scenario.py 대체물이며 B 사람 응답 엔진이 아님 |
| KPI | analytics_views, /admin/analytics/kpi | 제공 행의 안전한 합/합계÷건수 구현·검증. fixture 재문의0/proxy와 미합의 지표는 unavailable. 실제 성과 계산은 Fabric 필요 |
| VOC TOP10·상품 상세·추세 | analytics_views, 관리자 analytics | scope별 제공 순위/점수/근거/NULL·제공 추세 조회 구현·검증. A가 운영 점수를 계산하지 않음 |
| 분석 수신·검증·게시 | analytics_service/validation/auth, /analytics/batches | 서비스 인증·불변 receipt·원자 current·역전 방지·PG trigger 구현·로컬 검증. source=LOCAL_SYNTHETIC. 실제 Fabric/발급기/Managed Identity는 미검증 |
| 긴급 중지 제어 | /staff/automation-control + claim/확정 gate | DB 지속 revision/generation/이력·명시 권한 구현. AUTO claim/공통 DB 확정 차단. 실제 외부 발송 중단은 B 연결/검증 필요 |
| 감사·보관/삭제 | audit_events + 최소 감사 | 업무/조회/거부 감사 구현. 명시 TEAM/GLOBAL 권한·집계 중심 보관 dry-run 구현. 실제 삭제·외부 sink·백업 검사는 없음. 정책·Functions/Fabric 공동 합의 필요 |

## 남은 Backend A P0

**합의된 A 로컬 P0 경계에서 남은 미구현 항목은 없습니다.** 보관·삭제 dry-run까지 구현했습니다. 실제 삭제는 요청 범위 밖이고 구현·실행하지 않았습니다. 원문30일/집계90일은 DEV_RETENTION_V1 개발 제안이며 법적/운영 정책이 아닙니다. 법적 hold·비정형 JSON 참조·공유 batch 보관을 완전 판정할 수 없어 최종 후보 확정을 유보하는 것이 구현된 안전 동작입니다. P0 전체 제품/운영 통합이나 상용 준비 완료를 뜻하지 않습니다.

큐/상세/중지의 A 경계는 구현했지만 B worker/heartbeat/실패 이관/실제 발송·AI/RAG·Frontend 팀 화면 통합은 남습니다. 내부 상세는 검증된 metadata/근거만 표시하고 원시 draft는 노출하지 않는 제한적 기본값입니다. 안전한 초안 표시와 직원 텍스트 편집/승인 workflow는 B/AI 계약 없이 임의로 만들지 않았습니다.

## 실제 팀 연동이 필요한 것

- B: AUTO/HANDOFF 소비·배정·사람 응답 최종 저장·승인·실제 발송/외부 부작용, heartbeat/backoff/실패 이관·중지 연결. A의 gate와 테스트 대체물만으로 B 통합 성공을 주장하지 않습니다.
- AI/RAG: 분류·유효 정책·근거/승인·마스킹·기본 요약과 평가. 현재 사실3문장은 생성형 요약이 아닙니다.
- Fabric: 운영 추출/episode·KPI/VOC 계산·실제 emitter/파이프라인과 인증, 원천 품질·점수 계산 검증. 로컬 게시 성공은 외부 pipeline 성공이 아닙니다.
- Frontend: 역할별 화면, revision/멱등 재시도, 미게시/stale/unavailable/LOW_SAMPLE·batch 고정과 현재 권한 재조회. 이번에 실제 React 팀 화면을 실행하지 않았습니다.

## 확정이 필요한 정책

미배정 큐의 팀 귀속·열람 주체, 직원 내부 상세 whitelist, 긴급 중지 범위/재개 권한·in-flight 처리, SLA24시간 임시값·재문의 허용 전이, 모든 회차 필수 후속·인수/팀 이전 정책, per-ticket 고객360 범위, 기본 요약의 최소 입력/캐시, 보존/삭제와 외부 sink를 확정해야 합니다. 마지막 후속 완료만으로 자동 해결하지 않는 현재 동작을 유지합니다.

Fabric과는 생성 cohort/첫 팀·마지막 팀/미귀속 AUTO, 자동완료·이관 분모, ticket/cycle/message/episode 구분, 처리시간 합계/건수, 재문의/SLA/승인/검토 정의, 제품 KPI 팀차원/tag 중복/NULL 분모·세부 제외 사유코드, source attestation·JWT 발급/회전, stale24h/5분 시각 유예·업로드 상한을 합의해야 합니다. 현 기본값은 구현 제안입니다.

## 로컬 재현과 증거

현재 PC는 Windows, Python3.13.15와 별도 .venv-phase5를 사용했습니다. Docker 없음, WSL 배포판 없음으로 Linux는 미실행입니다. 시스템 기능 설치·재부팅·서비스 등록은 하지 않았습니다. 5단계에서 설치한 고정39개 패키지와 PostgreSQL16.15 binary를6–7단계에서 재사용했으며 이번 단계의 다운로드/외부 통신은 없습니다. 실제 bin 경로는 다음과 같습니다.

`<LOCAL_POSTGRES_BIN>`

README의 local_runtime init/start-api/test/verify/stop/start-db/clean으로 재현합니다. 실행마다 새 소유 클러스터/DB를 만들고 tests는 무작위 schema, HTTP는 별도 무작위 schema입니다. 기존 .env와 개발 DB는 건드리지 않습니다. API/DB는127.0.0.1만 사용하며 proxy·PG 서비스/클라우드 환경을 상속하지 않습니다. local.env는 로컬 비밀값이므로 공유 파일에서 제외합니다.

테스트 시나리오는 tests/http_scenario.py, 프로세스/schema 수명주기는 scripts/http_integration.py입니다. 내부 확정 함수는 테스트 코드에만 있고 무인증 endpoint를 추가하지 않았습니다. HTTP 결과는 DTO 필드명/합성 ID·집계·metadata만 남기고 토큰/비밀번호/문의·답변 원문·내부 메모를 포함하지 않습니다. 실제 API의 OpenAPI와 docs/openapi.json의 전체 동일성을 확인합니다.

실행 결과와 종료/정리 증거는 verification.md 및 .cache/local-phase7의 로컬 보고서에 기록합니다(이전 증거는 .cache/local-phase5·local-phase6·phase6-persistence에 보존). 원격 push·팀원 전송·GitHub Actions·클라우드 로그인/조회/리소스 작업·배포·외부 모델/발송 호출은 수행하지 않았습니다. 기존 클라우드 설정/배포 문서는 보존하며 이 문제를 해결하기 위해 실행하지 않았습니다.

## 전달 파일

Frontend는 frontend-handoff.md/api-contract.md/openapi.json/examples/frontend-requests.json, B는 backend-b-handoff.md/backend-b-contract.md/phase2/phase3 설계, Fabric은 fabric-handoff.md/fabric-contract.md/phase4 설계/examples/analytics-batch.json/examples/canonical-hashes.json을 읽습니다. 모두 로컬 파일이며 전송하지 않았습니다.

## 5단계 변경 파일

- app/local_guard.py와 app/db.py: CSFLOW_LOCAL_ONLY 연결 전 방어. app/config.py: CSFLOW_ENV_FILE 명시 선택. 기본 업무 API/DB revision은 유지했습니다.
- scripts/local_support.py, local_runtime.py, local_api.py: 별도 환경/소유 클러스터·서버 수명주기·정상 종료·재시작·정리.
- scripts/http_integration.py와 tests/http_scenario.py: 실제 HTTP/PG 흐름, 명시적인 고정 응답·배정·사람 writer 대체물. tests/test_local_safety.py와 conftest.py: 원격/환경 우회 방어 회귀.
- scripts/check_handoff_contract.py와 examples의 요청/응답/해시 JSON: 실제 OpenAPI/모델·정규화 계약 검사. 기존 export_openapi를 사용했습니다.
- README, 본 점검표, 담당자별 handoff/계약, verification/next-step-prompt/openapi, .gitignore의 별도 가상환경 제외를 갱신했습니다. 기존 migration·클라우드 설정/배포 문서는 이번 단계에서 변경하지 않았습니다.

## 6단계 추가 계약

명시 권한은 staff_permissions에 별도 저장하고 어떤 실제 계정/ADMIN에도 자동 부여하지 않습니다. queue_routes는 현재 cycle의 명시 팀만 사용하며 카테고리/이전 배정으로 귀속을 만들지 않습니다. 내부 상세는 현재 유효 배정 또는 관리자 팀 범위+목적을 다시 확인합니다. customer_ref는 이 권한 안의 고객360 이동 키이며 그 API에서도 범위를 다시 검증합니다.

전역 중지/재개는 별도 관리자 권한, expected_revision/재개 stopped_revision/사유·감사·history를 사용합니다. AUTO worker는 ticket→job→control SHARE, 제어는 user→control UPDATE 순서입니다. HANDOFF와 사람 업무를 유지하고 이전 claim은 재개 뒤 generation으로 차단합니다. 이미 확정된 응답은 보존합니다. 실제 외부 발송 취소는 보장하지 않습니다.

0001–0004는 수정하지 않고0005를 추가했습니다. route/grant/변경 control history/직원 상세 조회 이력이 있으면 downgrade를 거부합니다. 복구에는0005를 이해하는 API/worker가 필요합니다. 새 schema·fixture 재실행과 실제 PostgreSQL/HTTP/재시작 결과는 verification.md에 기록합니다. 소스는 app/staff_models.py, exception_queue.py, staff_detail.py, staff_router.py, automation_control.py와 jobs/finalization의 공통 gate입니다.

## 7단계 보관 검토와 범위 종료

[보관 미리보기 계약](phase7-retention-preview.md)은 실제 저장 inventory/UTC 경계/분류·제한을 정리합니다. messages뿐 아니라 AI draft/snapshot·승인·후속·멱등·감사 JSON·receipt/batch/mart와 글로벌 참조 저장 행을 집계합니다. JSON 내용 탐지나 클라우드 검사로 표현하지 않습니다. 팀 귀속이 불명확하면 숨기고, 공유 분석/프로필은 TEAM에서 건수NULL입니다. 전역은 ADMIN+RETENTION_GLOBAL_REVIEW로만 조회합니다. 어떤 계정에도 새 권한을 자동 부여하지 않습니다.

0006은 권한 CHECK만 확장하며0001–0005를 보존합니다. 새 권한/RETENTION_DRY_RUN 감사 후 downgrade는 거부합니다. 원문/운영·분석 내용은 수정하지 않고 purpose 코드/빈 payload 감사1행만 추가합니다. 실삭제 endpoint/실행 플래그/삭제 SQL/예약 작업은 없습니다. 향후 실제 삭제는 사용자 지정 범위/팀 정책과 실행 직전 재검증이 필요하고 이번 보고서가 승인이 되지 않습니다.

Frontend는 frontend-handoff/api-contract/OpenAPI/examples와 phase7 설계, B·AI는 backend-b-handoff의 보존 참조 계약, Fabric은 fabric-handoff의 receipt/불변 batch·외부 저장소 한계를 읽습니다. 모두 로컬 파일이며 전송하지 않았습니다. 새 단계를 임의로 확장하지 않고 현재 인수 범위에서 종료합니다.

## 0.6.1 독립 검토 수정

repo.agent_assignment_exists를 AGENT ticket_scope와 큐 assigned에서 공유해 실제 권한 없는 배정이 큐를 숨기지 않게 했습니다. control SHARE 대기 뒤 최종 쓰기 직전 wall-clock lease/저장 시각을 갱신하며 숫자 UUID 등 cursor는 모든 페이지422입니다. OpenAPI413/422 설명만 고정했고 계약 전체 비교·해시 벡터 검사는 유지합니다. migration은 추가하지 않았습니다.

최종 전체 회귀는 코드 변경 완료 뒤 실행했습니다. 실제 Linux/Python3.12 재실행·외부 worker/발송·클라우드 통합은 미검증입니다. 기존 검토 ZIP은0.6.0 원본 검토 자료이며 이번 수정 코드나 새 검증을 포함하지 않습니다. 체험 API를 다시 시작해도 DB/seed/권한·비밀번호는 초기화하지 않습니다.

## 2026-11-03 실제 Azure 배포 추가

이전 로컬 전용 문단은 당시 범위의 기록이다. 이번 명시 승인으로 A 전용 Korea Central App Service B1/PostgreSQL16 B1ms·32GiB에 배포했다. migration0006/PAUSED/별도 합성 계정과 실제 HTTPS18개 묶음61건을 확인했다. 새 관련 로컬 PostgreSQL92 passed이며 기존 전체368와 합산하지 않는다. 실제 Linux Python3.13.18 빌드·기동은 확인했지만 Linux 전체 pytest/B·AI/RAG·Fabric/Frontend/발송/PITR는 미검증이다. 원본 로컬 DB와 다른 팀 리소스는 변경하지 않았다. 비용·잠금·범위·작업 트리/패키지 해시는 azure-deployment.md와 evidence/azure-team-dev를 따른다.


## 2026-11-03 Azure 이름 이전 후 현재 환경

API base는 https://csflow-backend-a.azurewebsites.net/api/v1, PG는 csflow-backend-a-pg.postgres.database.azure.com/backend_a, Plan은csflow-backend-a-plan이다. source0.6.1/head0006과 기존 모든행/계정/권한·자동중지를 보존했다. 구3개 삭제·공용잠금 복원과 실제검증/백업은[azure-migration.md](azure-migration.md)를 따른다. B·AI·Fabric·발송은미연결/미검증이고 실제 Frontend origin은추측해등록하지 않았다. 서비스 인증 비밀값이나 DBpassword는이문서에없다.
