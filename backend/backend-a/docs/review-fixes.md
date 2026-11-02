# 독립 검토 결함 수정 — Backend A0.6.1

새 기능이 아닌0.6.0의 결함 수정이다. DB schema/readiness는0006 그대로이며 migration 추가·기존 migration 수정·권한 복원·자동 전사 권한 부여를 하지 않는다. 기존 A P0/실제 팀 엔진의 책임 구분과 보관 dry-run 범위를 유지한다. 결과 수치는 verification.md의 최종0.6.1 항목을 따른다.

## 실제 처리할 수 없는 배정과 예외 큐

기존 exception_queue의 assigned는 회차/시각·종료 여부·활성 상담사/팀만 검사하고, repo.ticket_scope의 정규화 user_team_scopes/category/처리 stage 조건을 빠뜨렸다. 따라서 상담사의 scope를 회수하면 해당 상담사는404였지만 큐에서는 유효 배정처럼 숨겨졌다.

repository.agent_assignment_exists(agent_id=None)를 공통 SQL 정책으로 사용한다. AGENT 티켓 접근은 agent_id로 제한한 같은 정책, 큐의 assigned는 실제 사용 가능한 상담사가 있는지 같은 정책으로 판단한다. 조건은 현재 ticket/cycle/team 일치, 미종료/이미 시작된 배정, DB의 활성 AGENT, 사용자 실제 팀, 활성 팀, user_team_scopes의 명시 팀 권한, team_categories의 category, 티켓의 ASSIGNED/IN_PROGRESS/FOLLOWUP_PENDING/WAITING_CUSTOMER 상태다. 별칭으로 상위 followup/360/queue 쿼리의 correlation 충돌을 피한다.

scope 회수·category 변경/정규화 category 제거·사용자/티켓/배정 팀 변경·비활성 상담사·종료 배정·처리 불가 stage에서 상담사가 실제 접근할 수 없으면 배정으로 큐를 숨기지 않는다. 큐의 route/capability/현재 허용 팀 조건은 그대로이며 목록·counts에 같은 조건을 적용한다. 비활성 route 팀은 기존처럼 explicit UNROUTED_QUEUE_READ 관리자에게만 최소 정보로 보인다. 권한 복원·전사 공개·현재 티켓 팀/category로 route 추측은 하지 않는다. 실제 재배정은 B 책임이다.

## control 대기 후 lease 만료

기존 commit_automatic_reply는 ticket/job 잠금 뒤 now로 lease를 검사한 다음 blocker/control SHARE gate를 통과했지만 그 대기로 만료된 lease를 다시 검사하지 않았다. 초기 now를 최종 메시지·해결·job 성공 시각에도 재사용했다.

초기 fence와 ticket→job→control SHARE 순서를 유지하고, 모든 gate 뒤 savepoint 안의 첫 INSERT 직전에 utcnow()를 새로 읽어 lease_until<=now이면 INVALID_LEASE로 거부한다. utcnow는 datetime.now(timezone.utc)의 실제 wall clock이며 PostgreSQL transaction_timestamp()/now()처럼 트랜잭션 시작에 고정된 시간이 아니다. 메시지/티켓 해결·갱신/첫 응답(기존 값이 없을 때)/job 갱신 시각은 이 최종 시각을 사용한다. 이미 존재하는 first_replied_at 이력은 보존한다.

회귀는 lease+0.4초/control SELECT+0.6초 지연, 성공 경로의 gate 반환 이후 저장 시각, 실제 PostgreSQL control FOR UPDATE→worker FOR SHARE 대기→lease 만료를 검사한다. 거부를 outer transaction 안에서 잡아 commit하더라도 티켓/job/메시지/감사 행·내용 digest가 그대로인지 확인한다. 이미 확정된 응답·중지/재개 generation fencing·사람 경로는 기존 회귀로 보존한다. 이 검증은 공통 DB 경계이며 실제 B worker/외부 발송의 실행·취소 보장이 아니다.

## 비정상 cursor

decode_cursor는 JSON list 길이2 확인 뒤 두 값이 모두 문자열인지 먼저 검사한다. 정수/bool/null/object/list/float를 date나 UUID parser에 넘기지 않는다. 잘못된 cursor는422 INVALID_CURSOR이며 AttributeError가500으로 빠져나오지 않는다. UUID/시각/tz/base64/크기 등 기존 검증과 리소스 인증/소유권 우선순위는 유지한다.

실제 GET tickets/orders/messages/public followups/staff followups/exception-queue, POST customer360 tickets/followups의8개 페이지 경로에서 숫자 UUID cursor의422를 검사한다. 정상 페이지·권한·커서 형식 자체는 변경하지 않는다.

## Python HTTP 문구 차이

Python3.12의413 Request Entity Too Large/422 Unprocessable Entity와3.13의 Content Too Large/Unprocessable Content 차이는 FastAPI가 http.client.responses에서 가져오는 설명 기본값 차이였다. app.main의 공통 responses에서413=Content Too Large,422=Unprocessable Content만 명시한다. schema/field/security/response를 무시하는 정규화나 비교 예외를 추가하지 않는다.

scripts.check_handoff_contract는 여전히 실제 OpenAPI와 docs/openapi.json 전체를 엄격히 비교한다. Python3.12의 기본 문구 dictionary를 모사해도 전체 동일해야 하며, 필드/인증/응답/예상하지 않은 설명을 바꾼 계약은 OPENAPI_NEEDS_REGENERATION이어야 한다. canonical hash vector도 기존 그대로 비교한다. 실제 Linux/Python3.12 전체 재실행은 이 PC에서 하지 않았고 Windows/Python3.13.15에서 이 호환 조건을 검사한다. 사용자가 전달한 수정 전297 passed/33 skipped는 독립 검토자의 보고이며 이 작업의 로컬 XML 증거로 새로 생성하지 않는다.

## 변경/실행 범위

- app/repository.py, exception_queue.py: 공통 유효 배정·엄격 cursor 타입.
- app/finalization.py: 모든 gate 후 최종 lease 만료/시각 재검증.
- app/main.py, pyproject.toml, docs/openapi.json: 패치 버전0.6.1과413/422 설명 고정.
- tests/test_review_fixes.py: 직접 재현38개(그중 실제 PostgreSQL lock 대기1개).
- tests/http_review_fixes.py, http_scenario.py: 기존30개에 cursor8페이지/권한 회수 큐/만료 후 무저장3개 흐름 추가. 내부 확정은 기존처럼 테스트 코드에서만 호출한다.

검증은 .cache/local-review-fixes의 새 소유 PostgreSQL 클러스터와 무작위 schema·private Uvicorn을 사용한다. 기존 demo-local 데이터·비밀번호·seed는 검증에 사용하지 않는다. 코드 최종 확정 뒤 전체 PostgreSQL과 실제 HTTP를 실행하고 부분 수를 합산하지 않는다. 검증용 자원만 정리하며 기존 체험 서버에 패치를 적용할 경우 API만 정상 재시작하고 DB/seed/권한을 초기화하지 않는다.

기존 CS_Flow_AI_Backend_A_review.zip은 수정 전0.6.0 독립 검토본이다. 이번 요청에서 덮어쓰거나 재포장하지 않으며 새 코드/검증을 포함한다고 주장하지 않는다. 클라우드·외부 API/모델/RAG/Fabric/발송·원격 push/Actions를 실행하지 않는다.
