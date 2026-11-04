# Backend A 구현 검증 결과

## 2026-11-04 수동 품질 평가 — 로컬0.9.0/0009

[실제 실행 기록](evidence/quality-local/README.md): 신규33개 PG PASS, 영향 회귀222개 PG PASS, 마지막 지표 분리 후 관련6개·자료 제한 보완5개 PASS(중복 합산 금지). 초기 테스트 import1실패는 수정·재검증했다. 실제 AI 품질·B/AI/Fabric/Frontend/Azure 연동·계정 grant·commit/push는 이번에 하지 않았다.

## 2026-11-04 VOC 개선 조치 — 로컬0.8.0/0008

[실제 검증 기록](evidence/voc-local/README.md): 최신 VOC31개 PASS, 환경/seed 호환 보완 후 분석·fixture54개 PASS. 관련 최초 회귀248 PASS/1 FAIL/4 SKIP에서 실패·skip 원인을 수정하고 해당 사례를 재검증했다. 실행은 서로 겹치므로 합산하지 않는다. 기존 migration/미커밋 B 검토 문서를 보존했으며 Azure·실제 계정·Fabric·B Worker·Frontend 화면·commit/push는 변경/검증하지 않았다.

아래 기존 단계 결과는2026-11-02 KST의 원본 작업 폴더 실행 기록입니다. 원본 ZIP에 들어 있던 과거 70개 검증과 이번 서비스 검증을 합산하지 않습니다.

## 2026-11-03 지정 이름 이전 — 새 실행 결과

실제배포source0.6.1의동일ZIP으로이전했다. 새실행은전체32테이블내용/소유권/권한/138제약·인덱스/트리거/함수/sequence비교, 기존상태HTTPS16건, 핵심HTTPS18묶음61건, operator6tests이다. 원본 모든PK/rowhash가검증후에도일치했다. 초기2복원시도는target공개쓰기전 source자동복귀했고성공에포함하지않는다. 최종검증후 backup을추가확보하고구API/PG/Plan404·새ready200및공용DO_NOT_DELETE복원을확인했다. 기존전체PG368/HTTP33/관련PG92는반복/합산하지않는다. 상세[이전보고](azure-migration.md), evidence/azure-migration.

## 2026-11-03 Azure 팀 개발 배포 — 새 실행 결과

기존 아래368/로컬HTTP33은 이전 원본 검증이다. 이번에는 별도 로컬 PostgreSQL의 **관련92 passed(실패0/skip0),50.59초**, 초기 SQLite 보조26 passed, Ruff/엄격 계약 검사, 실제 Azure Linux Python3.13.18 빌드와 고정29개 dependency 설치를 확인했다. 새 전체 PostgreSQL/Linux 전체 pytest는 반복하지 않았다. 부분 결과를368에 합산하지 않는다.

배포 HTTPS는 **18개 검증 묶음·기대 상태 요청61건 PASS**이며 최종 검증 시각은2026-11-03 10:53:51 KST이다. 인증/소유권·scope/멱등/revision/재문의·직접연결/후속/고객360·내부 DTO/PAUSED·권한/보관 업무표 불변·감사/분석 미게시/429·413/실제 앱 restart 데이터·중지 보존을 확인했다. 고정 배정·사람 확정 writer는 공통 gate의 합성 검증이며 실제 B 엔진이 아니다. 실제 AI/Fabric/발송/Frontend는 미연결이다.

초기 환경 상속 테스트1건과 PC/클라우드 시계 차이로 중단된 HTTP 시도는 성공에 포함하지 않는다. 최종 코드의 API/lock/권한을 바꾸지 않고 격리 환경과 DB 시각 기반 검증 도구를 고쳤다. Windows CA 파일 경로와 팀 공유 삭제 잠금 문제도 인증서 검증/공유 잠금을 유지한 채 해결했다. 임시 operator 방화벽은 잠금 때문에 삭제 대신 loopback으로 비활성화했다. 배포/비용/복구와 증거는 [azure-deployment.md](azure-deployment.md), evidence/azure-team-dev에 있다.

## 0.6.1 독립 검토 결함 수정 — 최종 전체 회귀

유효하지 않은 배정의 큐 누락, control gate 대기 중 만료 lease 확정, 비문자열 cursor500과 Python별 OpenAPI413/422 설명 차이를 수정했습니다. 새 기능/endpoint/권한/migration은 추가하지 않았습니다. 현재 **Backend A0.6.1 / migration0006**이며 원인·변경 파일·정책은 [수정 내역](review-fixes.md)에 정리했습니다.

| 실제 실행 | 최종 결과 |
|---|---|
| **최종 코드 이후 전체 PostgreSQL** | **368 passed**, 실패0/skip0, JUnit398.277초(콘솔398.29초). 기존330개 + 신규38개 |
| 관련 PostgreSQL 부분 회귀 | **38 passed**, 실패0/skip0, 36.866초.368개에 합산하지 않음 |
| 관련 Windows SQLite 부분 회귀 | **37 passed / 1 skipped**, 실패0, 27.576초. 실제 PG control 잠금 대기1개만 skip. 전체 SQLite 결과가 아님 |
| 실제 로컬 Uvicorn/PostgreSQL HTTP | **33개 흐름 PASS**. 기존30개 + cursor8페이지/권한 회수 큐/만료 후 무저장3개 흐름 |
| OpenAPI/canonical vectors | PASS. 실제 HTTP 생성 계약 전체 동일.413/422 Python3.12 기본 문구 모사에서도 전체 동일. 필드/인증/응답/설명 변조4종은 엄격 거부 |
| Ruff check / format --check | PASS, Python92개 파일 |
| migration/원본 fixture 회귀 | PASS.0006 유지, 기존 migration 파일은0.6.0 검토 ZIP과 SHA256 동일. 기존 seed 적재/재실행 회귀 포함 |

모든 app/migrations/scripts/tests 실행 코드의 수정시각이 전체 pytest 시작 이전임을 확인하고 SHA256 snapshot을 남겼습니다. 전체 회귀 이후 실행 코드를 변경하지 않았으며 문서/보고서 갱신만 수행했습니다. 부분38개·SQLite37개·HTTP 흐름 수를 전체368개에 더하지 않습니다. 기존 Starlette/httpx deprecation warning1건은 유지됩니다.

배정 회귀는 scope 회수, category 변경/정규화 category 제거, 사용자·티켓·배정 팀 변경, 상담사 비활성, 배정 종료, 처리 불가 stage를 검사합니다. 정상 배정은 상담사 접근200/큐0이며, 처리 불가능해진 뒤 상담사는404(비활성 사용자401), 허용된 route 관리자 큐는 목록/필터/limit/counts가 일치합니다. 비활성 팀 route는 기존처럼 일반 관리자/ROUTED에 노출되지 않고 명시 UNROUTED_QUEUE_READ만 최소 정보로 봅니다. 권한을 복원하거나 전사 범위로 확대하지 않습니다.

lease 회귀는 RUNNING lease+0.4초 뒤 control SELECT+0.6초 지연을 주입해 INVALID_LEASE인지 검사했습니다. 실제 PostgreSQL control FOR UPDATE 보유→worker FOR SHARE 대기를 pg_blocking_pids로 확인한 뒤 만료시켜 같은 거부를 검사했습니다. 거부를 outer transaction 안에서 잡아 commit하더라도 ticket/job/messages/audit 행·내용 digest가 동일합니다. 성공 경로의 메시지/해결·갱신/job 저장 시각도 control gate 반환 이후의 새 wall-clock 시각인지 확인했습니다. 기존 중지/재개/generation·회차·lease·잠금 순서 전체 회귀가 포함됩니다.

cursor는 날짜와 UUID 위치 각각의 정수/bool/null/object/list/float12개를 검사했습니다. 실제 tickets/orders/messages/public followups/staff followups/queue/고객360 tickets·followups8개 페이지 경로에서 숫자 UUID cursor가422 INVALID_CURSOR로 처리됩니다. 권한·소유권 검사와 유효 cursor 형식은 유지합니다.

OpenAPI는 Python3.13.15가 사용하는 설명을 명시하고 http.client.responses를3.12 문구로 바꿔도 전체 동일함을 검사했습니다. schema/field/security를 지우거나 예상하지 않은 설명으로 바꾼 계약은 OPENAPI_NEEDS_REGENERATION으로 실패합니다. canonical hash vectors도 원래 값과 일치합니다. **이 PC에서 실제 Linux/Python3.12 전체 실행은 하지 않았습니다.** 사용자 독립 검토의 수정 전297 passed/33 skipped는 외부 보고이며 이 폴더에 해당 XML이 없으므로 새로 만들지 않았습니다.

환경은 기존 Windows/Python3.13.15/PostgreSQL16.15와 고정 의존성입니다. Docker/WSL 설치·실행이나 새 다운로드는 하지 않았습니다. SQLite 보조 실행의 초기 샌드박스 TEMP 권한 오류/파일 접근 정체는 성공으로 계산하지 않았고, 명령행·경로로 식별한 해당 테스트 자식만 종료한 뒤 native 로컬 임시 경로에서 최종37/1 결과를 얻었습니다. 체험 서버·DB는 그 프로세스 정리 대상이 아니었습니다.

증거는 `.cache/local-review-fixes/postgres-results.xml`, `pytest.log`, `focused-results.xml`, `focused.log`, `http-integration-report.json`, `final-verification-summary.json`, `openapi-compatibility-report.json`과 `.cache/review-fixes-sqlite-final.xml/log`입니다. 공유 HTTP 예시는 docs/examples/http-integration-result.json에 갱신했습니다. 고정 합성 답변·테스트 배정·공통 확정 테스트는 실제 B/AI/RAG/Fabric/발송 엔진 통합 성공이 아닙니다. 만료 확정은 내부 공통 함수로 검사하고 실제 HTTP로 미저장 상태를 확인했으며 무인증 확정 endpoint를 추가하지 않았습니다.

새 소유 `.cache/local-review-fixes` 클러스터/무작위 schema와 private HTTP 서버만 검증에 사용했습니다. 기존 demo-local DB·권한·seed·비밀번호를 검증에 사용하거나 초기화하지 않았습니다. 검증용 자원 정리와 체험 API 패치 재시작은 각 로컬 보고서로 구분합니다. 기존 CS_Flow_AI_Backend_A_review.zip은 수정 전0.6.0 자료로 유지했고 새 코드/결과가 들어 있다고 주장하지 않습니다. 클라우드 접속·외부 API/모델/Fabric/발송·원격 push/Actions는 실행하지 않았습니다.

검증 종료 후 새 클러스터·root/HTTP 자격파일·이번 SQLite scratch 디렉터리3개만 정리했습니다. `.cache/local-review-fixes/cleanup-report.json`에서 테스트 API/DB 포트 닫힘과 HTTP graceful 종료를 확인했습니다. 보고서/코드/기존 의존성은 보존했습니다.

기존 체험 API만 정상 재시작해0.6.1을 적용했고 http://127.0.0.1:8000/docs에서 계속 실행 중입니다. DB는127.0.0.1:65440 그대로이며 pg_postmaster_start_time·중지 상태·local.env SHA256이 재시작 전후 동일합니다. DB/seed/권한·비밀번호를 초기화하지 않았습니다. live/ready200과 실제 OpenAPI version0.6.1 확인은 `.cache/demo-local/hotfix-api-startup-report.json`에 저장했습니다. 기존 운영 로그도 API 재시작 전 로컬 복사본으로 보존했습니다.

## 7단계 보관·삭제 dry-run — 최종 전체 회귀

현재 **Backend A0.6.0 / migration0006**입니다. Windows/Python3.13.15/PostgreSQL16.15에서 기존 .venv-phase5/고정39개 의존성과 portable binary를 재사용했습니다. 새 `.cache/local-phase7` 소유 클러스터와 test_csflow_*/http_csflow_* 무작위 schema만 사용했습니다. 기존 개발 DB/.env를 사용하거나 덮어쓰지 않았습니다. API/DB는127.0.0.1 전용이며 Docker/WSL 설치·실행·재확인은 하지 않았습니다.

| 최종 실제 실행 | 결과 |
|---|---|
| 최종 코드 전체 PostgreSQL pytest | **330 passed**, 실패0/skip0, JUnit420.072초(콘솔420.08초). 기존283개 + 신규47개 |
| 최종 변경 대상 PostgreSQL 부분 검증 | **9 passed**, 실패0/skip0, 12.106초. 위330개에 합산하지 않음 |
| 실제 Uvicorn + PostgreSQL HTTP | **30개 흐름 PASS**, 기존25개 + 보관 검토5개. source=LOCAL_SYNTHETIC |
| minimal seed/원본22테이블 fixture 적재·재실행 | PASS. 새0006 DB 적재/재실행0행, 기존 이력 보존 |
| migration/readiness/복구 | PASS.0005→0006/check/빈 downgrade/re-upgrade, 새 권한·보관 감사 후 downgrade 거부 |
| 0001–0005 불변 | 실행 전후5개 파일 SHA256 동일.0006은 명시 권한 CHECK만 확장, auto grant0 |
| OpenAPI/요청 예시/공개 DTO/정규화 해시 | PASS. 실제 HTTP OpenAPI와 로컬 생성 파일 일치, retention 경로는 POST dry-run만 존재 |
| Ruff check / format --check | PASS, Python90개 파일 |
| Linux/클라우드/실제 B·AI·Fabric·외부 발송 | 미실행/미검증. 실제 삭제 기능도 구현·실행하지 않음 |

최종 전체 회귀는7단계 코드·migration·테스트와6단계 최종 DTO/단언 변경까지 모두 반영한 뒤 **한 번** 실행했습니다. 그 뒤 실행 코드는 변경하지 않았습니다. 초기 부분 검증 중 테스트 fixture의 필수 version/lease/분석 metadata 누락, 불필요한 SQL 개수 단언, 과거 fixture 시각 기대값을 정정했습니다. 중간 실패를 성공 수치에 포함하지 않습니다. 기존 Starlette/httpx deprecation warning1건이 있으며 실패가 아닙니다. 전체 SQLite 결과로 주장하지 않습니다.

새 API `POST /api/v1/staff/retention/dry-run`에서 ADMIN만으로 허용되지 않음, 잘못 부여된 고객/상담사 capability로도 허용되지 않음, RETENTION_TEAM_REVIEW/GLOBAL_REVIEW 분리, 활성 허용 팀 부분집합, 타팀/미귀속/과거 귀속 불명 자료의 존재·건수 숨김을 확인했습니다. 팀 보고의 공유 receipt/분석·프로필/참조는 UNSUPPORTED_TEAM_SCOPE/건수NULL이며 글로벌 fallback하지 않습니다. 숨겨진 자료 추가 전후 팀 결과 fingerprint 일치도 검사했습니다.

DEV_RETENTION_V1은30/90일 개발 제안이며 configurable1–3650일, timezone 정규화/미래 시각·잘못된 기간/SQL·경로·URL·execute·force 등 추가 필드422를 검사했습니다. UTC cutoff의 마이크로초 앞/동일/뒤를 원문30일·집계90일에 각각 검증했습니다. 최근 티켓 변경/현재 회차 보호와 과거 fixture 시각을 현재 만료로 오인하지 않는 기대값도 포함합니다. 분석 저장 시계(created_at/received_at)와 source_as_of/day를 구분합니다. 원안의 시연 종료시각 기준이나 법적 보존 정책 확정으로 표현하지 않습니다.

messages뿐 아니라 ai_suggestions의 draft/order_snapshot/evidence/gate JSON, approvals.gate_snapshot, 후속 공개/내부 메모, 멱등 response_snapshot, 감사 payload, tickets의 태그/메타데이터, receipt payload/validation_result, batch.manifest/4개 mart와 글로벌 프로필·주문·정책/규칙·인증/업무 참조 저장 행의 집계를 확인했습니다. 이것은 **고정 저장 위치·참조 영향 조사이며 JSON/본문 전체의 개인정보 탐지 검사가 아닙니다.** 현재 고객360/큐의 실시간 집계에는 별도 저장 테이블/생성형 cache가 없습니다. 미귀속 제품 후속/멱등·감사도 글로벌 별도 target으로 누락 없이 보고합니다.

미해결, 모든 회차 미완료 필수 후속, 활성 배정, PENDING/RETRY/RUNNING·유효 lease, 현재 회차, 멱등 재시도·승인/정책/감사·작업 source 참조를 보호합니다. 현재 분석 pointer/is_current뿐 아니라 과거 SUCCEEDED와 FAILED/미게시 receipt의 불변 trigger/FK를 차단·설계변경 사유로 보고합니다. 비현재 배치를 삭제 가능으로 단정하지 않습니다. hold/비정형 JSON 참조가 완전히 모델링되지 않았으므로 기간상 후보(past_retention_count)와 최종 후보(candidate_count=0)를 분리하고 판단 불가를 표시합니다.

실제 PostgreSQL REPEATABLE READ에서 API가 첫 대상 집계를 읽은 뒤 별도 연결로 티켓 추가/상태 변경을 commit해도 한 보고서의 메시지·티켓 수와 보호 조건이 섞이지 않는지 확인했습니다. 같은 snapshot/정책/as_of/권한의 반복 결과도 일치합니다. SQL 관측으로 원문/JSON/내부 메모 컬럼을 SELECT하지 않음을 검사했습니다. 업무·원문·분석·권한/제어 등 **audit_events를 제외한 전체 모델 테이블**의 행/내용 hash가 preview 전후 동일하며, 감사만1행 추가되고 payload={}, target_id=NULL/고정 목적임을 확인했습니다. 감사 실패는 성공 응답 없이 rollback합니다. 응답/감사·API/PostgreSQL 로그의 합성 원문/내부 표식·JWT·이번 로컬 비밀값 미포함을 확인했습니다.

Blob·외부 추출·Fabric Bronze/Silver/Gold·백업/replica/WAL·로그/파일/export/cache는 NOT_INSPECTED입니다. 로컬 보안/참조 metadata 중 내용 보관 대상 밖의 항목도 명시했습니다. 외부 저장소를 확인하러 접속하지 않았고 보존/삭제·법적 준수 달성을 주장하지 않습니다. 향후 실삭제는 별도 정책/권한/참조·상태의 실행 직전 재검증이 필요하며 이 결과는 실행 승인/예약/행 ID 목록이 아닙니다.

실제 HTTP는 새 역할/권한 분리·팀/전역 preview·숨김 자료 불변·공유 저장소NULL·업무 내용 불변·실행/임의 target 거부를 추가했습니다. 이전 고객/직원/후속/중지/분석30개 흐름은 실제 loopback Uvicorn/PostgreSQL이지만, 답변은 고정 합성/배정 fixture/사람 gate 뒤 테스트 writer/제공된 합성 분석입니다. 실제 B/AI/RAG/Fabric/발송 엔진 성공이 아닙니다. 분석 게시는 이 로컬 DB current pointer 교체뿐입니다.

주요 증거는 `.cache/local-phase7/postgres-results.xml`, `pytest.log`, `retention-pg-focused.xml`, `retention-pg-focused.log`, `seed-report.json`, `http-integration-report.json`, `log-safety-report.json`과 `.cache/phase7-original-migration-hashes.json`입니다. 중간 개발 실패는 retention-development-failed.*로 따로 구분합니다. 공유 가능한 요청·HTTP 결과는 docs/examples/frontend-requests.json·http-integration-result.json입니다. 코드와 계약은 phase7-retention-preview.md 및 A/Frontend/B/Fabric 인수 문서에 연결했습니다. 재현은 README의 local_runtime init/start-api/test/verify/stop/clean을 사용합니다.

검증 후 이번 소유 클러스터와 root/HTTP 임시 자격파일을 제거했습니다. `cleanup-report.json`에서 클러스터 삭제·API PID 해제·HTTP graceful 종료 표식·API/DB loopback 포트 닫힘을 확인했습니다. `postgres-server-summary.txt`는 정상 기동/정지 증거이며 `final-verification-summary.json`에330개/9개/HTTP30개를 구분했습니다. 기존 의존성/binary·fixture·검증 보고서는 보존했습니다. 테스트용 schema/임시 클러스터 정리는 보관 API의 실제 삭제 기능과 별개입니다.

이 단계에서 의존성 다운로드나 다른 외부 통신을 하지 않았습니다. 클라우드 로그인/접속/조회/리소스 작업/배포·외부 모델/Fabric/Storage/발송·원격 push/Actions/팀원 전송은 실행하지 않았습니다. 실제 업무 데이터 삭제 기능은 없고 실행하지 않았습니다. 합의된 A 로컬 P0 경계의 미구현 항목은 남지 않았으며 실제 팀/운영 통합과 보관·hold·기준 시계/권한·공유 batch/외부 복제본 정책은 확정이 필요합니다. 새로운 단계는 임의로 시작하지 않습니다.

## 6단계 예외 큐·직원 상세·전역 중지

Backend A **0.5.0 / migration0005**입니다. Windows/Python3.13.15/PostgreSQL16.15에서 기존 고정 의존성39개와 로컬 binary를 재사용했습니다. Docker/WSL/Linux는 실행하지 않았고 이번 단계의 외부 통신·다운로드는 없습니다. 기존 개발 DB와 .env 대신 새 소유 클러스터2개와 무작위 테스트/HTTP schema를 사용했습니다. API·DB는127.0.0.1에만 공개했습니다.

| 실제 실행 | 최종 결과 |
|---|---|
| 전체 PostgreSQL pytest | **283 passed**, 실패0/skip0, JUnit243.84초(콘솔243.85초). 기존235개 + 신규48개 |
| 최종 직원 상세 DTO·PG 경합 재검증 | **27 passed**, 실패0/skip0, 27.56초. 전체283개에 더해 합산하지 않음 |
| 실제 PostgreSQL + Uvicorn HTTP | **25개 흐름 PASS**, 기존17개 + 신규8개. 최종 DTO/OpenAPI와 일치 |
| 실제 API·PostgreSQL 중지/재시작 | PASS. paused·변경자·시각·revision/generation 보존, 재시작 전후 AUTO claim 차단, 명시 재개 후 비활성 규칙 유지 |
| 0004→0005·readiness·fixture 재적재 | PASS. 기존22테이블 보존/반복 삽입0, 자동 권한 부여0, route 자동 backfill0 |
| migration 복구 | 빈 상태 downgrade/re-upgrade PASS. 권한/route/변경 이력/직원 상세 감사가 있으면 downgrade 거부, history UPDATE/DELETE 거부 |
| SQLite 보조 검증 | 신규 큐·상세·제어 대상 **39 passed**. 전체 SQLite 실행이나 PostgreSQL 경합의 대체 결과가 아님 |
| Ruff check / format --check | PASS, Python84개 파일 |
| 실제 OpenAPI·역할 요청·공개 DTO·canonical hash 예시 | PASS, 로컬 생성/검사. 분석 wire 계약/점수 계산은 변경하지 않음 |

최종 전체 회귀 뒤 직원 상세의 닫힌 중첩 출력 스키마/customer_ref와 상태 조회 SQL 실패 시 HANDOFF 유지 단언을 추가했습니다. 해당 최종 변경은 위27개 PostgreSQL 재검증과25개 실제 HTTP로 확인했습니다. 중간 테스트의 잘못 배치된 fixture 변수 NameError는 수정했으며 실패한 실행을 통과 결과에 포함하지 않습니다. 기존 Starlette/httpx deprecation warning1건은 유지됩니다.

큐는 명시 EXCEPTION_QUEUE_READ/현재 회차 queue_routes와 팀·업무 범위를 사용합니다. 미귀속/비활성 팀은 관리자+UNROUTED_QUEUE_READ로만 최소 정보가 보이고 여러 팀 scope나 ADMIN만으로 열리지 않습니다. 목록/건수/필터/페이지 권한 일치, 종료/이전 회차 배정 배제, 큐로부터 직원 상세·고객360 권한이 생기지 않음을 검사했습니다. 실제 라우팅/배정은 B 대신 구현하지 않았고 record_queue_route와 테스트 fixture로 검증했습니다.

직원 상세는 목적/현재 유효 배정 또는 관리자 팀 범위를 검증하고 감사를 남깁니다. 정책·주문·제안·승인·회차 연결, 과거/합성/만료/이전 revision·정책 비활성 구분, 중첩 gate bool/버전 allowlist와 PRIVATE_* 독성 필드 제거를 검사했습니다. customer_ref는 허용된 직원에게만 이동 키로 제공하고 고객360에서 권한을 다시 검사합니다. 고객 DTO/OpenAPI에는 추가하지 않았습니다. 초안/원시 프롬프트/임의 JSONB는 노출하지 않으며 모든 승인 표시는 실행 권한이 아닙니다.

중지는 명시 권한·expected_revision·재개 stopped_revision·사유와 상태/이력/감사를 원자 저장합니다. AUTO claim/공통 확정 차단, 중지 전 in-flight와 재개 뒤 옛 generation fencing, 새 lease 재claim, HANDOFF/접수/사람 요청/후속/사람 해결 유지, 감사 실패 rollback을 검사했습니다. 실제 PostgreSQL pg_blocking_pids로 중지 선행·확정 선행 양쪽 잠금 순서와 동시 중지 revision 충돌을 검증했습니다. control 행 부재 및 SQL 조회 실패는 자동 처리를 허용하지 않고 같은 장애에서 HANDOFF는 유지됩니다. 이미 확정된 응답은 보존합니다.

HTTP는 고정 합성 답변·테스트 배정·공통 사람 해결 gate 뒤 테스트 writer·LOCAL_SYNTHETIC 분석을 사용합니다. 신규 큐/직원 상세/명시 권한/중지·재개·revision·이력/fencing/사람 업무 유지까지 실제 인증된 endpoint로 검사했습니다. 인증 없는 검증 endpoint를 추가하지 않았습니다. **실제 B worker·AI/RAG·Fabric·외부 발송 엔진의 통합 검증은 아닙니다.** DB claim/확정 차단은 검증했지만 이미 진행된 외부 호출의 취소/발송 중단은 B 연결이 필요합니다.

증거는 `.cache/local-phase6/postgres-results.xml`, `pytest.log`, `focused-results.xml`, `seed-report.json`, `http-integration-report.json`과 `.cache/phase6-persistence/control-restart-report.json`입니다. 실제 재시작 확인용 로컬 QA 코드는 `.cache/phase6_persistence.py`에 남겼으며 지정된 새 테스트 클러스터의 개발 계정에만 fixture 권한을 부여했습니다. 공유 가능한 HTTP 결과는 `docs/examples/http-integration-result.json`이고 비밀번호/토큰/문의·답변 원문/내부 메모를 포함하지 않습니다. 재현 명령은 README의 init/test/verify/stop/clean을 사용합니다.

두 소유 클러스터는 검증 후 정상 종료/삭제했습니다. 각 state의 `cleanup-report.json`과 `postgres-server-summary.txt`에서 클러스터·임시 자격파일 삭제, API PID 해제, API·DB loopback 포트 닫힘을 확인했습니다. HTTP schema도 제거했고 API/PostgreSQL 로그의 토큰·테스트 원문·내부 독성 값 미포함을 확인했습니다. 보고서·고정 의존성·기존 PostgreSQL binary는 보존했습니다.

0001–0004와 기존 클라우드 설정/배포 문서는 보존했습니다. Azure/다른 클라우드 로그인·접속·조회·리소스 작업·배포, 외부 모델/RAG/Fabric/발송, 원격 push/Actions/팀원 전송은 실행하지 않았습니다. 남은 A P0는 보관·삭제 dry_run이며 권한 부여 주체/큐 귀속 정책/안전 초안 표시/중지 재개 정책은 제한적인 구현 제안으로 팀 확정이 필요합니다.

## 5단계 로컬 실행·HTTP·인수

Backend A 버전0.4.0/migration0004를 유지했습니다. Windows/Python3.13.15의 **새 .venv-phase5**, PostgreSQL16.15의 새 소유 클러스터/DB를 사용했습니다. Docker 실행파일 없음, 설치된 WSL 배포판 없음으로 Linux/컨테이너는 미실행입니다. 시스템 기능 설치·재부팅·서비스 등록은 하지 않았습니다. 고정 requirements-dev.txt의39개 설치 버전 전체 일치를 확인했습니다. 필요한 패키지/EDB PostgreSQL binary 다운로드만 허용된 외부 통신으로 사용했고 프로젝트 데이터/자격정보를 전송하지 않았습니다.

| 실제 실행 | 최종 결과 |
|---|---|
| 전체 PostgreSQL pytest | **235 passed**, 실패0/skip0, 251.51초. 기존221개 + 로컬 안전 회귀14개 |
| PostgreSQL + 실제 Uvicorn HTTP | **17개 흐름 PASS**, 여러 새 schema로 재실행. source=LOCAL_SYNTHETIC |
| migration0004 + minimal/22테이블 fixture + 재실행 | PASS, 새 클러스터만 사용/fixture 반복 삽입0행 |
| 실제 HTTP /openapi.json ↔ 생성 파일 | 전체 동일 PASS. 인증 없는 검증 endpoint 추가0 |
| 역할 요청 예시/공개 DTO/해시 벡터 검사 | PASS, 실제 Pydantic/OpenAPI/canonical 함수에서 검증 |
| 고정39개 패키지 버전 확인 | PASS, 별도 가상환경 설치/원본 requirements 보존 |
| Ruff check / format --check | PASS, Python72개 파일 |
| 로컬 체험 API 시작·health·Swagger·정지/재시작 | 정상 종료/동일 fixture·revision 보존 확인. 수명주기 보고서 참조 |
| Linux/WSL/Docker/실제 B·AI·Fabric/CI/클라우드 | 미실행, 대체물 성공과 구분 |

전체 테스트에는 기존 Starlette/httpx deprecation warning1건이 있었습니다. 새 로컬 안전 회귀는 원격/암묵 host·host/service/hostaddr override·conninfo dbname·UNC 차단, cloud/libpq/proxy 환경 제거, 사용자 비밀번호의 #/공백/따옴표/개행 보존과 환경 삽입 방지, DB engine 생성 전 차단, 명시적 환경파일의 기본 .env 무시를 검사합니다. 원격 URL 문자열을 거부 테스트에 사용했을 뿐 DNS/원격 연결을 시도하지 않았습니다.

실제 HTTP는 고객 로그인/주문/접수, 같은키 재시도·다른내용409, 타고객404, 고정 자동 응답의 공통 확정, 재문의·사람 요청, HANDOFF claim/테스트 배정, 이전 회차 후속 보존·이전 상담사 차단·관리자 큐·새 담당자 인수/DONE, 필수 후속의 사람 해결 차단·완료 후 별도 명시적 해결을 확인했습니다. 두 번째 미배정 티켓을 만들어 고객360 집계/최근 목록의 권한 범위1건을 확인하고 고객 DTO 내부 메모 비노출을 검사했습니다.

같은 실제 HTTP 서버에서 로컬 서비스 토큰의 합성 분석 수신→검증→로컬 current 게시, 관리자 KPI·TOP10·상품 상세·제공 추세, T1 subset과 무권한 전체 scope403, LOW_SAMPLE 등 NULL, 잘못된 checksum 배치 FAILED/게시409/이전 성공 batch 유지도 검사했습니다. 이 게시에는 외부 업로드·배포가 없습니다. 기존 fixture의 source/checksum 의미를 바꾸거나 점수 엔진을 재실행하지 않았습니다.

고정 자동 답변은 tests/http_scenario.py에서 commit_automatic_reply를 호출했습니다. 배정은 test fixture이며 사람 최종 응답도 lock_resolution_gate 뒤의 테스트 writer입니다. **실제 B 배정/응답/승인·외부발송 엔진을 검증한 것이 아닙니다.** 실제 모델·RAG·Fabric emitter/파이프라인도 호출하지 않았습니다. AI 요약은 NOT_GENERATED이고 정형 사실3문장만 확인했습니다.

Windows venv launcher PID와 실제 Python PID가 다른 경우 준비 표식이 잘못 거부되는 새 실행 도구 결함을 발견해 수정했습니다. private 실행 경로/소유 ID와 실제 Uvicorn started 표식·health를 함께 검사하고, 종료는 private 파일 신호와 lifespan 완료를 기다립니다. 해당 중간 실패는 성공 횟수에 포함하지 않았으며 그때의 서버/schema/임시 자격파일도 정리했습니다. clean의 오래된 메타데이터가 종료 PID를 다시 기록하는 문제도 수정하고 별도 새 클러스터/API의 init→start→clean으로 재검증했습니다. 기존 SQLite 보조 smoke의 실제 PostgreSQL 검증 공백, 암묵 .env/상속 환경 대상 위험, README159개·B계약0.3의 오래된 표기도 수정했습니다.0001–0004 migration 파일과 클라우드 배포 파일은 이번 단계에서 수정하지 않았습니다.

주요 증거는 `.cache/local-phase5/postgres-results.xml`, `pytest.log`, `dependency-check.json`, `seed-report.json`, `http-integration-report.json`, `lifecycle-before.json`, `lifecycle-after.json`, `cleanup-report.json`, `postgres-server-summary.txt`입니다. 추가 정리 재검증은 `.cache/phase5-lifecycle-check/cleanup-report.json`입니다. 두 소유 클러스터/자격파일 삭제와 API·DB loopback 포트 닫힘을 확인했습니다. HTTP 별도 schema는 삭제하고 서버의 graceful 종료·API/PostgreSQL 로그의 비밀번호/토큰/원문/내부 메모 미포함을 확인했습니다. 생성 예시 `docs/examples/http-integration-result.json`은 원문 대신 공개 필드명/합성 ID/집계/metadata만 담습니다. `docs/examples/canonical-hashes.json`은 실제 함수의 오프라인 해시 벡터입니다. 별도 가상환경과 PostgreSQL binary는 로컬 재현을 위해 유지하고 다운로드 ZIP은 제거했습니다.

재현은 README의 `python -m scripts.local_runtime init/start-api/test/verify/stop/start-db/clean`을 사용합니다. 데이터/자격정보는 생성한 로컬 state와 소유 클러스터만 사용하고 기존 개발 DB/.env를 열거나 변경하지 않습니다. DB/API를127.0.0.1에만 바인딩하며 프록시·클라우드/libpq 서비스 설정은 상속하지 않습니다. 완료 후 체험 API/DB를 정상 종료하고 clean으로 이 작업의 임시 클러스터와 비밀값을 제거하며 보고서/로컬 의존성은 남깁니다.

실제 클라우드 로그인/접속/조회/리소스 작업/배포, Azure CLI·SDK·관리API·Cloud Shell·Terraform/Bicep, 외부 모델/AI Search/Fabric/Blob·실제 발송, GitHub Actions/원격 push/팀원 전송은 수행하지 않았습니다. 기존 클라우드 설정·배포 문서는 보존했습니다. 남은 Backend A P0와 타 담당/팀 정책은 backend-a-handoff.md에 구분했으며 이 로컬 검증을 전체 P0나 실제 팀 통합 완료로 표현하지 않습니다.

## 4단계 검증 범위

분석 수신/검증/게시와 KPI·VOC 조회,0004/readiness, 기존159개 회귀를 포함합니다. 최종 실행 수치와 시간은 아래 실행 결과 표에 기록합니다. 출처는 LOCAL_SYNTHETIC이며 원본 Gold 비교와 서비스 검증을 실제 Fabric 실행/점수 수식 재실행과 구분합니다. 실제 Fabric/Managed Identity·B 엔진·Azure 배포는 수행하지 않았습니다.

| 실제 실행 | 환경/범위 | 최종 결과 |
|---|---|---|
| 전체 pytest --database=postgres | Windows/Python3.13.15/PostgreSQL16.15, 원본 fixture 포함 | **221 passed**, 213.85초, 실패/skip0 |
| 전체 pytest SQLite | 같은 Python, PG 전용 검증은 명시적 skip | **201 passed, 20 skipped**, 144.40초 |
| Uvicorn loopback HTTP smoke | 격리 SQLite, 기존 운영 API | PASS |
| Ruff check / format --check | app/migrations/scripts/tests 64개 Python 파일 | PASS |
| Alembic check/upgrade/downgrade/re-upgrade | 실제 두 DB의 테스트 | PASS, 이력 보호/전체 rollback/legacy 보존 포함 |
| OpenAPI·예시 payload·전체 fixture 해시 | 실제 생성 산출물 직접 검사 | PASS, 별도 service/user scheme·413 포함 |
| PostgreSQL offline upgrade / 위험 offline downgrade | SQL 생성만 수행 | PASS / 명시적 거부, DB 실행과 구분 |

기존159개에 신규62개를 추가한 총221개입니다. 두 pytest 실행에는 기존 Starlette/httpx deprecation warning1건이 있었으며 실패가 아닙니다. 테스트용 PostgreSQL은 시스템 서비스 등록 없이127.0.0.1:55432에 실행했고 검증 후 fast stop 정상 종료와 전용 클러스터/무작위 비밀번호/다운로드 정리를 확인했습니다. 기동 버전·종료 증거는 `.cache/phase4-postgres-server-summary.txt`입니다. 운영 DB나 Azure 리소스에는 접속/변경하지 않았습니다.

- 실제 PostgreSQL에서 정상 수신→검증→게시→TOP10/상세/추세/KPI, 최초 미게시, 실패 후 이전 성공 유지, 동일 배치 재시도/다른 내용409, 후보·부분 적재 게시 거부를 검사합니다.
- 별도 서비스 키/issuer/audience/allowlist/permission, 고객·상담사·관리자 로그인 토큰 게시 거부, 관리자 전용 조회, 현재 팀 subset·무권한/정확한 scope 부재·과거 batch 현재 권한을 검사합니다.
- 행 수/해시/schema/rule/PK/FK/기간/scope/상태/NULL/밴드/순위·동점·설명 근거와 추세 합계를 검사합니다. 금지 식별자/원문/경로/URL 추가 필드422, 실제 upload bytes/행 상한413을 포함합니다.
- PostgreSQL 실제 pg_blocking_pids 대기로 동시 수신 동일/다른 내용, 양 순서의 동시 게시/오래된 역전, 게시와 직접 SQL mart 변경의 양 순서를 확인합니다. 게시 중 멈춘 조회가 동일 REPEATABLE READ의 이전 배치와 metadata를 반환하는지 검사합니다. 이 항목들은 SQLite 테스트 결과로 대체하지 않습니다.
- 수신/검증/게시 마지막 감사에 실패를 주입해 전체 rollback, 저장된 mart 삭제 후 게시409, 게시 후 DB trigger 변경 거부를 확인합니다.0003 원본 분석 행300개 보존 업그레이드/검증/빈 downgrade/re-upgrade, legacy current의 증거 없는 재게시 방지, receipt 이후 downgrade 거부·readiness를 검사합니다.
- SQLite의 실제 BEGIN IMMEDIATE에 맞춰 Alembic transactional_ddl을 명시했습니다.0004→0003이 끝난 후0003의 이력 보호가 실패하더라도0004까지 전체 rollback되어 readiness가 유지되는 기존 회귀를 포함합니다.0001–0003 migration 파일은 수정하지 않았습니다.
- 원본4팀 조합15개의 실제 UUID 집합에 대해 API TOP10 product/score/rank를 원본 gold_voc_top_n과 대조하고 상세/추세 같은scope, 비대상 NULL, 부분 팀 product KPI 미제공을 확인합니다. 전체 fixture를 다시 적재해 삽입0행·legacy VALIDATED/미게시·새 managed 성공 보존을 검사합니다. 어댑터는 제공된 점수/순위를 복사하며 score 함수/Notebook을 실행하지 않습니다.
- 별도 Uvicorn 실제 loopback HTTP smoke는 로그인/주문/접수/재문의/사람 요청/후속/고객360·내부 메모 차단을 검사했습니다. 이 smoke의 DB는 SQLite이며 PostgreSQL 증거와 구분합니다.

기계 판독 결과는 `.cache/phase4-postgres-results.xml`, `.cache/phase4-sqlite-results.xml`, offline SQL은 `.cache/phase4-postgres-upgrade.sql`입니다. OpenAPI service/user 인증 scheme 분리·413 응답과 전체 fixture/최소 예시의 canonical 해시도 직접 확인했습니다. 원본 팀 배열 순서에 의존하지 않는 고정 UUID 어댑터의 생성 결과 일치도 확인했습니다. Ruff check/format, PostgreSQL offline upgrade SQL 생성과 위험 offline downgrade 거부를 확인했습니다. offline SQL 생성 자체는 DB 실행 증거가 아닙니다.

재현에는 아래 공통 pytest 명령을 사용하고 결과 파일명을 phase4로 지정합니다. `python -m scripts.prepare_analytics_fixture reference/fixture .cache/analytics-payload.json`은 LOCAL_SYNTHETIC 파일만 만들고 네트워크/게시/Fabric을 실행하지 않습니다. `python -m scripts.export_openapi`는 실제 코드의 계약을 DB/네트워크 연결 없이 생성합니다.

미검증: 실제 Fabric source·emitter hash·발급/Managed Identity·파이프라인·원장 추출·점수 계산 정확성, 실제 B·LLM, CI/Linux/Azure, 운영 백업 복구/부하/장애 시험입니다. KPI fixture0/proxy와 scope 없는 제품 KPI를 지원 불가 성과로 명시하며 합의할 분모·귀속·재문의/SLA 정의와 원본에 없는 세부 제외 사유코드는 phase4-analytics.md/Fabric 계약에 남겼습니다.

## 3단계 최종 실행 결과

3단계 당시 후속 CRUD·관리자 책임 큐·공통 해결 차단·고객360·migration0003 코드의 기록입니다. **기존107개 포함159개**를 실제 PostgreSQL에서 실행했습니다. 현재4단계 결과와 혼동하지 않습니다.

| 검증 | 환경 | 실제 결과 |
|---|---|---|
| 전체 pytest --database=postgres | Windows, Python 3.13.15, PostgreSQL 16.15 | **159 passed**, 206.46초 |
| 전체 pytest | 동일 Python, SQLite | **150 passed, 9 skipped**, 131.40초 |
| 실제 Uvicorn loopback HTTP smoke | 격리 SQLite DB | PASS: 기존 흐름 + 후속 생성/완료·공개 메모 비노출·scoped 고객360·후속 완료 후 비자동 해결 |
| Ruff check / format --check | app, migrations, scripts, tests | PASS |
| Alembic upgrade/check/downgrade/re-upgrade | 위 두 DB의 테스트 | PASS. 0002→0003 원본 필드·회차 보존과 위험 downgrade 거부 포함 |
| 실제 B 사람 응답·배정/인수 엔진 / LLM / Azure / CI | 미실행 | 통합 성공으로 보고하지 않음 |

PostgreSQL 전용 9개는 기존 6개와 새 후속 생성/해결 양쪽 잠금 경합 2개, 고객360 REPEATABLE READ 권한 snapshot 1개입니다. SQLite 통과를 그 검증의 대체로 표현하지 않습니다. 각 pytest 실행에는 기존 TestClient/httpx deprecation warning 1건이 있습니다. Python 3.11/Linux CI는 구성만 유지했고 이번 결과는 Windows/Python 3.13.15 실행입니다.

이번 추가 검증은 다음과 같습니다.

- 고객/상담사/관리자의 후속 읽기·쓰기·상품 후속 권한, 타고객/타팀/종료 배정/이전 회차/다른 category 차단.
- 고객 DTO의 정확한 공개 필드 whitelist, 내부 전용 후속과 상품 후속 비노출. 직원 허용 범위 내 내부 메모는 유지.
- OPEN/IN_PROGRESS/DONE/CANCELLED 전이, 기한·timezone·소유자·필수값·원래/책임 회차·완료/취소 DB CHECK, terminal 불변성과 물리 삭제 없는 취소.
- 생성 멱등·동시 생성·다른 요청 충돌, 동시 수정의 revision 충돌, 생성/수정/상태 변경 중 감사 실패 시 데이터·멱등 기록 rollback.
- owner NULL/비활성 소유자 후속의 관리자 큐 잔존, 인수 전 완료 거부, 현재 담당자 인수, 양쪽 팀 scope가 필요한 팀 이전.
- 재문의 후 원래 cycle/최초 팀 보존, 이전 상담사 차단, 모든 회차의 미완료 필수 후속이 AUTO/HUMAN 공통 게이트를 차단함. 마지막 완료는 ticket을 자동 해결하지 않음.
- `pg_blocking_pids`로 실제 잠금 대기를 확인한 후 필수 후속 생성 선행/자동 해결 선행을 각각 검증. 한쪽만 성립하고 다른 쪽은 BLOCKING_FOLLOWUP/TICKET_ALREADY_FINISHED.
- 고객360의 집계·최근5건·유형·처리 방식·미해결·반복·현재 담당·후속·원본 페이지가 같은 per-ticket 권한 집합과 일치. 종료 배정/다른 팀/업무 범위의 이력은 집계에도 제외.
- PostgreSQL snapshot 조회 중 다른 트랜잭션에서 팀을 변경해도 같은 요청의 집계/현재 배정이 섞이지 않음. 다음 요청에는 새 권한 적용.
- 목적 값 검증·권한 독립성과 조회 감사, 최소 정수형 AI 입력·NOT_GENERATED·동일 snapshot fingerprint 안정성과 메모/실제 scope 변경 시 무효화.
- 0002의 후속 원문·상태·기한·version을 보존하는 0003 업그레이드, 기존 전체 fixture 적재/재실행·이력 보존과 기존 전체 회귀.

원시 결과는 `.cache/phase3-postgres-results.xml`, `.cache/phase3-sqlite-results.xml`입니다. 실제 PostgreSQL 16.15를 loopback 55432에 격리 실행했고 서버 로그는 terse/파라미터 비수집으로 구성했습니다. 시스템 서비스 등록·Azure 리소스 생성·실제 배포는 없습니다. smoke의 상담사 배정은 명시적인 로컬 테스트 fixture이며 B 엔진 실행이 아닙니다.

검증 후 임시 PostgreSQL을 정상 종료하고 다운로드·클러스터·비밀번호를 정리했습니다. 버전·기동·종료 증거는 `.cache/phase3-postgres-server-summary.txt`에 보존했습니다. 0003의 offline downgrade SQL 생성 거부도 별도로 확인했습니다.

초기 테스트 도우미의 이전 SQLite schema UUID/PK reflection 문제를 수정한 후 최종 전체 회귀를 다시 실행했습니다. 위 숫자는 부분 실행을 합산한 값이 아닙니다. B 사람 응답은 `lock_resolution_gate` 계약만 검사했고 실제 답변·승인·해결 저장/발송 엔진은 미검증입니다. 3줄은 정형 사실 문장이며 실제 생성형 LLM의 품질/출처 대응이나 캐시 운영은 검증하지 않았습니다.

## 2단계 실행 기록

재문의와 상담사 직접 연결 API, 공통 자동 응답 저장 경계, migration 0002를 추가한 최종 코드 기준입니다. 기존 46개를 포함한 총 107개 테스트를 실행했습니다.

| 검증 | 환경 | 실제 결과 |
|---|---|---|
| 전체 pytest --database=postgres | Windows, Python 3.13.15, PostgreSQL 16.15 | **107 passed**, 123.73초 |
| 전체 pytest | Windows, Python 3.13.15, SQLite | **101 passed, 6 skipped**, 76.07초 |
| Uvicorn 실제 loopback HTTP smoke | 별도 SQLite DB·무작위 자격정보 | PASS: 로그인/본인 주문/접수/재문의/직접 연결/동일 연결 재시도/내구 HANDOFF/타고객 차단 |
| Ruff check / format --check | app, migrations, scripts, tests | PASS |
| Alembic upgrade/check/downgrade/re-upgrade | 위 두 DB의 테스트 | PASS. 0001→0002 데이터 보존과 위험 downgrade 거부 포함 |
| CI, Azure Linux, Flexible Server, 실제 B 엔진 | 미실행 | 성공으로 간주하지 않음 |

각 pytest 실행에는 기존 Starlette TestClient/httpx deprecation warning 1건이 있으며 실패는 없습니다. 첫 PostgreSQL 시도는 새 테스트의 누락된 import로 실패했고 수정 후 **전체 107개를 재실행**해 위 결과를 얻었습니다. 부분 실행의 통과 건수를 최종 성공으로 합산하지 않았습니다.

실제 PostgreSQL 서버를 격리된 ASCII 임시 폴더에서 127.0.0.1:55432로 실행했습니다. 시스템 설치·서비스 등록·Azure 작업은 하지 않았습니다. 서버 로그는 terse, 파라미터/statement 수집 비활성으로 구성했습니다. 결과 XML은 `.cache/phase2-postgres-results.xml`, `.cache/phase2-sqlite-results.xml`에 남깁니다. PostgreSQL 전용 6개는 기존 lease 테스트 1개와 새 테스트 5개(양쪽 확정/재문의 순서 2건 포함)이며 SQLite에서 경합 성공으로 세지 않았습니다.

검증용 서버는 종료했고 버전·기동·정상 종료 증거를 `.cache/phase2-postgres-server-summary.txt`에 보존했습니다. 최종 migration의 offline downgrade SQL 생성 거부도 별도로 확인했습니다. DB 이력 검사를 생략하는 복구 SQL은 생성하지 않습니다.

추가한 검증 범위는 다음과 같습니다.

- 두 API의 본인 성공·비인증/타고객/없는 ID/staff 차단과 독립 권한 거부 감사, 필수 revision·메시지·추가 필드 검증.
- 허용 8개 재문의 상태, 직접 연결 허용 상태와 이미 사람 경로인 5개 상태의 중복 거부, CANCELLED/오래된 revision 거부.
- 새 회차·revision·공개 메시지·AUTO/HANDOFF·reason/source_message·감사·멱등 snapshot 저장. 실패 주입 시 이전 RUNNING lease, 활성 배정, ticket, 메시지, job, 멱등/감사 전부 원복.
- 동일 key의 재시도/동시 요청, 다른 key/다른 요청 경쟁, endpoint/대상/reason/revision 간 key 충돌과 사용자별 격리. 후속 회차 이후에도 원래 replay 응답 유지.
- 재문의와 직접 연결 경합은 한 명령만 수락. 수락된 HUMAN 경로는 이후 재문의에서도 유지하며 이전 배정 종료·team 범위 해제.
- 공통 저장 함수의 이전 cycle/version/token/worker/만료 거부, 최신 HUMAN/HANDOFF 자동 응답 차단, 필수 후속 차단, 확정 실패 시 rollback.
- 회차별 최종 OUT 중복 거부와 이전 유효 응답 보존. PostgreSQL 동시 최종 확정도 한 건만 저장.
- PostgreSQL `pg_blocking_pids`로 실제 잠금 대기를 확인한 후 재문의 선행/자동 응답 선행을 각각 검증. 잠금 대기 중 lease가 만료되는 경우도 재검증.
- AUTO/HANDOFF worker 예약 분리. 실제 HANDOFF 팀 선정/배정은 실행하지 않음.
- 0001의 기존 티켓·메시지·job·멱등 접수 결과를 보존한 0002 업그레이드와 위험 downgrade 거부.
- 기존 전체 합성 이력 적재·seed 반복·원본 티켓 재문의 후 과거 메시지/종료 job 보존·seed 재실행 후 새 cycle 보존. 원본 로그인 자격정보를 활성화하지 않고 테스트 전용 issuer로 소유권 API를 검증.

이 테스트는 **고정 합성 답변과 공통 저장 경계의 계약 테스트**입니다. 실제 B의 AI/RAG, 정책/승인 gate, 사람 이관/팀 선정·배정 엔진, 외부 발송·부작용, heartbeat/재시도/장애 복구 E2E를 검증한 것이 아닙니다. 직접 SQL writer는 최신 회차/lease guard를 우회할 수 있으므로 B는 공통 함수 또는 동등한 잠금·검증을 통합해야 합니다. DB 부분 UNIQUE는 회차별 최종 응답 중복을 독립적으로 차단합니다.

재현 명령은 아래 공통 명령을 사용하되 `--junitxml=.cache/phase2-postgres-results.xml`처럼 결과 파일을 구분할 수 있습니다. 외부 fixture가 없는 checkout은 전체 이력 관련 4개를 건너뛰므로 원본을 제공한 전체 회귀와 구분해야 합니다.

## 1단계 실행 기록

| 검증 | 환경 | 실제 결과 |
|---|---|---|
| 전체 pytest | Windows, Python 3.13.15, SQLite | 45 passed, 1 skipped, 22.83초 |
| 전체 pytest --database=postgres | Windows, Python 3.13.15, PostgreSQL 16.15 | 46 passed, 46.49초 |
| 실제 Uvicorn HTTP smoke | 격리 SQLite DB, loopback HTTP | PASS: 로그인/본인주문/티켓/내구작업/타고객차단 |
| Ruff check | app, migrations, scripts, tests | PASS |
| Ruff format --check | 동일 범위 | PASS |
| 최종 OpenAPI 확인 | 멱등 재시도 200 스키마 명시 후 해당 테스트 | 1 passed |
| PostgreSQL용 Alembic offline SQL 생성 | PostgreSQL dialect | PASS. 이 항목 자체는 DB 실행 증거가 아니며 위 PostgreSQL 테스트와 구분 |
| CI / Azure Linux / Flexible Server | 미실행 | 구성·절차만 준비 |

두 pytest 실행에 Starlette TestClient가 httpx 대신 httpx2로 전환을 권고하는 deprecation warning 1건이 있었습니다. 실패는 없으며 향후 테스트 의존성 갱신 시 반영할 항목입니다. Python 3.11/Linux 조합은 CI 구성으로 준비했으나 이번 로컬 결과를 그 환경의 성공으로 표현하지 않습니다.

의존성은 정확한 버전의 requirements.txt/requirements-dev.txt로 고정했습니다. Python 3.11 대상으로도 운영 의존성 메타데이터를 해석했으며 동일 버전으로 결정됐습니다. 이것은 Python 3.11에서 코드를 실행했다는 뜻은 아닙니다.

PostgreSQL 테스트를 위해 [PostgreSQL 공식 Windows 다운로드 페이지](https://www.postgresql.org/download/windows/)가 안내하는 EDB binary ZIP을 받아 시스템 설치·서비스 등록 없이 실행했습니다. 실행 버전은 서버 로그로 확인한 16.15입니다. 한글 경로에서 initdb가 실패하여 허용된 ASCII 작업 경로에 bin/lib/share만 복사하고 새 클러스터를 초기화했습니다. 접속은 127.0.0.1:55432, 무작위 로컬 비밀번호, 테스트 전용 DB와 무작위 스키마를 사용했습니다. 테스트 후 pg_ctl fast stop으로 종료한 로그를 확인했습니다. Azure 리소스/비용은 발생시키지 않았습니다. 검증용 PostgreSQL 다운로드/클러스터/비밀번호는 정리했고 저장소에 포함하지 않습니다.

Windows 제한 샌드박스는 asyncio의 내부 socketpair도 막아 처음 HTTP 테스트가 대기했습니다. 멈춘 해당 프로세스만 정리하고 검토된 실행 권한으로 다시 검증했습니다. 첫 setup 오류나 경로 초기화 실패를 통과 결과로 세지 않았습니다.

## 검증한 핵심 사례

- 로그인 성공/오류, 비활성 계정과 기존 토큰 차단, 만료/손상 토큰, 비활성 합성 해시 차단. 고정 dummy 검증값을 입력해도 합성 계정이 인증되지 않는 회귀 포함.
- 본인 주문 목록/상세, 주문 기반/주문 없는 티켓 접수, 실제 현재 UTC 시각과 주문 상품 매핑.
- 다른 고객 주문/티켓/메시지 조회 404, 타인 주문 접수 차단, body의 customer_id/role/product_id 거부.
- 티켓/첫 메시지/job/멱등 레코드/접수 감사가 함께 저장됨. 마지막 감사 직전 실패를 주입하면 모두 rollback.
- 동일 사용자/동일 key 재시도 동일 접수 결과, 다른 요청 409, 다른 사용자의 같은 key 독립성. 4개 동시 동일 요청이 1개 접수로 수렴하며 동시 다른 요청은 201/409.
- 내부 메모·오류·승인·고객 식별자/AI 내부 필드가 공개 스키마에 없음. 메시지 PUBLIC 형태 DB 제약.
- NOT NULL/양수 cycle·version/상태 enum, 주문 소유자·상품 FK, 작업 cycle 중복, lease 필수/해제 정합성, cycle별 최종 OUT 유일성.
- VOC ELIGIBLE 값의 NULL 허점 차단과 VALIDATED 배치의 current 전환 차단. 점수 계산기/게시 기능 테스트라는 뜻은 아님.
- 상담사 현재 배정+팀+업무 category+cycle+미종료 티켓, 관리자 팀 scope, 리스트·상세에 같은 제한 적용.
- 요청 rollback 이후 권한 거부 감사가 별도 commit으로 남음. 애플리케이션 로그에서 테스트 상담 원문·비밀번호·토큰 제외.
- Alembic 초기 적용/재적용/check/downgrade/upgrade. 최소 seed 재실행 시 비밀번호·활성 상태 보존.
- 22개 전체 fixture 적재, 재실행 삽입0행, 기존 티켓 변경 보존, 늦은 적재 실패 전체 rollback, 원본 1,000티켓 이후 신규 접수 성공.
- PostgreSQL 전용 SKIP LOCKED 동시 claim, 만료 lease 회수, token 교체, 이전 token 및 이전 version/cycle의 처리 배제.

실제 전체 적재 건수는 teams4, users821, customers800, products20, orders2000, shipments1898, returns76, tickets1000, messages4000, assignments820, knowledge_documents30, ai_suggestions1000, approvals1000, audit_events8820, automation_rules6, followup_actions168, automation_jobs1000, analytics_batches1, analytics_daily96, analytics_product_daily368, analytics_product_voc_daily840, analytics_product_risk300입니다. 최소 seed는 별도 UUID 영역이라 공존합니다. 전체 적재 테스트에서는 배치가 VALIDATED/미게시, 원본 로그인 표식이 비활성인 것도 확인했습니다.

## 재현 명령

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp=.cache/pytest-local --junitxml=.cache/sqlite-results.xml
$env:TEST_POSTGRES_URL='postgresql+psycopg://<test-user>:<test-password>@127.0.0.1:5432/<test-db>'
$env:CSFLOW_FIXTURE_DIR=(Resolve-Path reference/fixture).Path
.venv/Scripts/python.exe -m pytest -q --database=postgres --basetemp=.cache/pytest-postgres --junitxml=.cache/postgres-results.xml
.venv/Scripts/python.exe scripts/live_smoke.py
.venv/Scripts/python.exe -m ruff check app migrations scripts tests
.venv/Scripts/python.exe -m ruff format --check app migrations scripts tests
```

원시 JUnit 결과·smoke DB·임시 로그는 `.cache`에 저장하고 Git에서 제외했습니다. 일반적인 재현 환경은 README의 Docker Compose를 사용합니다. fixture가 없는 checkout에서는 원본 이력·분석 관련 테스트가 skip되므로 전체 검증에는 원본 ZIP을 별도로 추출해야 합니다.

## 미구현과 미검증

4단계에서 분석 수신·검증·게시/KPI·VOC TOP10·상세·추세를 구현했습니다. 점수 재계산·실제 Fabric emitter/실행·서비스 발급기/Managed Identity 통합은 포함하지 않습니다. 후속 CRUD·고객360은3단계 구현입니다. Backend B의 AI/RAG·정책/승인 판단·실제 사람 응답/배정/인수·외부 부작용·heartbeat/복구 daemon은 포함하지 않습니다. 생성형 요약도 최소 계약만 준비했고 LLM 호출/품질 검증은 없습니다.

Azure Linux 실행, App Service proxy/HTTPS/CORS 실기 검증, Flexible Server TLS/인증/네트워크, 실제 Fabric 연동, 실제 B와 E2E, 1,000상품 성능시험, 장애/부하시험, 감사 보존/삭제·외부 sink, 운영 rate limit은 미검증입니다. 이번 결과로 실운영 파이프라인 완성이나 분류/RAG 정확도를 주장하지 않습니다.
# 2026-11-04 업무량 조회 로컬 확장 검증

로컬0.7.0/head0007의 `GET /api/v1/staff/workload`를 추가했다. 기존 Azure0.6.1/0006 배포·계정·B/Fabric 연결은 바꾸지 않았다. [업무량 계약](workload.md), [이번 검증 상세](evidence/workload-local/README.md), [요약](evidence/workload-local/summary.json)을 기준으로 읽는다. 위 기존 검증 기록은 각 당시 범위 그대로이며 이번 결과에 합산하지 않는다.

격리 PostgreSQL16.15 선택 회귀164사례 중 초기163 passed/1 OpenAPI 비교 실패 후 실제 OpenAPI를 재생성하고 관련60사례를 재검증해60 passed/skip0/실패0을 확인했다. 사례 ID별 중복 제거 최종 상태는164개 모두PASS다. SQLite 관련59 passed/2 PG전용skip은 별도 결과다. Ruff·OpenAPI/DTO/예시·git diff --check PASS. 새 PG 임시스키마 잔존0 및 클러스터 종료를 확인했다. 실제 Uvicorn/브라우저·Azure·B·AI 품질·Fabric 전체 연동 성공을 뜻하지 않는다.

## 2026-11-04 미배정 의미 보완 — 0.7.1 / 0007

이번 격리 PostgreSQL 선택 검증113 passed, 추가 혼합 합계·계약 검증7 passed(중복 있어 합산하지 않음), 실패/skip0. 이전164 PASS는 이번 결과에 재사용하지 않았다. 기존 unassigned 집합을 유지하고 현재 처리 경로별 분류를 추가했으며 B/Azure 상태는 변경하지 않았다. [이번 검증과 공유 전 검토](evidence/unassigned-paths-local/README.md)를 따른다.
