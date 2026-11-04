# P1 AI 기반 VOC 개선 제안 — 구현 및 검증 (2026-11-04 KST)

기준/현재 HEAD `77cba3a4892160eb2f8a1afc8f51b28a0f1282bb`, 브랜치 feature/backend-plus. 미커밋 작업 트리이며 원격 push·다른 브랜치 수정·Azure 생성/배포는 하지 않았다. [API/설정/실행 명세](p1-voc-api.md), [기계 판독 요약](evidence/p1-voc-20261104/summary.json).

## 기존 기능 분석과 재사용

기존 VOC는 analytics_router의 top/unavailable/product detail 조회와 analytics_views의 게시 snapshot·scoped risk/daily mart 조회였다. 생성/사람 검토 기능은 없었다. analytics_product_risk, analytics_product_voc_daily, analytics_receipts/publication 및 기존 Metrics/Risk/VocDaily allowlist를 재사용했다. 전역 product_daily의 issue-tag grain을 더해 가짜 고유 문의 합계를 만들지 않았다.

기존 P0 approvals/AI suggestions는 티켓·cycle별 실행/답변 흐름이라 상품 개선 제안 승인에 재사용하면 업무 상태가 섞인다. 따라서 기존 원장을 유지하고 P1 별도 제안/검토 이력만 추가했다. Bearer/활성 사용자, ADMIN+명시 capability, user_team_scopes JOIN active teams, 감사 기록, 오류 봉투, p1_idempotency 및 기존 cursor를 재사용했다.

공급자 입력은 서버가 고정한 집계와 기간/출처뿐이다. 위험도/불만 집중(M/C)/문의 주문 비율(N/S)/upstream rate/기간 추세를 구분하고 표본·품질·freshness·추세 부족이면 AI를 호출하지 않는다. 근거 JSON+hash와 분석 windows를 남긴다. 공급자 추천은 인용 ID·닫힌 응답 스키마로 검증하지만 문구의 인과/효과를 사실로 승인하는 기능은 아니다. 제안은 PENDING_REVIEW이며 관리자 승인/반려를 받아도 실제 원장/정책/발송/worker가 바뀌지 않는다.

## 구현/API

신규 app/extensions/p1/voc_models.py, voc_schemas.py, voc_provider.py, voc_service.py, voc_router.py에 분리했다. app/main.py/schema.py에 최소 연결하고 seed의 공식 22테이블 fixture 제외 목록만 확장했다. 기존 P0와 monitoring route 코드는 변경하지 않았다.

| API | 권한 | 결과 |
|---|---|---|
| POST /api/v1/admin/p1/voc-proposals | P1_VOC_GENERATE | 서버 게시 근거로 동기 초안 생성/부족/실패 기록, 201 또는 멱등 replay 200 |
| GET /api/v1/admin/p1/voc-proposals | P1_VOC_READ | 상품 필터와 cursor/limit을 지원하는 요청 이력 |
| GET /api/v1/admin/p1/voc-proposals/{request_id} | P1_VOC_READ | 근거·기간·provider·상태·revision·검토 이력 |
| POST /api/v1/admin/p1/voc-proposals/{request_id}/reviews | P1_VOC_REVIEW | APPROVED/REJECTED, expected_revision·이유·멱등키, 충돌409 |

모든 요청은 기존 P1 flag와 별도 P1_VOC_ENABLED opt-in을 요구한다. `.env.example`에 설정 이름과 안전한 기본값만 추가했다. provider=MOCK 기본, AZURE_OPENAI 선택+AZURE_ENABLED=true일 때만 실제 전송이 가능하다. 키·배포명·endpoint·버전은 P1_VOC_AZURE_* 서버 환경변수다. Python 표준 HTTPS 전송으로 추가 SDK/의존성 변경 없이 구현했으며 TLS/CA/proxy를 유지하고 redirect/자동 retry를 막는다. bounded timeout/input/output 및 rate-limit/auth/timeout/unavailable/malformed/truncated/근거 인용 오류를 처리하고 Mock fallback을 하지 않는다.

생성 상태는 PENDING_REVIEW/INSUFFICIENT_DATA/FAILED이며 검토는 APPROVED 또는 REJECTED로 한 번만 전이한다. 201은 요청 이력 생성 성공이지 AI 성공을 뜻하지 않는다. 부족/실패 기록도 과거 이력으로 보존한다. 재시도는 새 멱등키이며 같은 키/body는 현재 권한·전체 팀 범위 검사 후 당시 snapshot으로 replay한다. 최신 상태는 GET으로 확인한다.

## DB 변경

신규 `0009_voc_proposals.py`: **0009 → 0008**, 단일 head. 기존 0001–0008과 기존 업무 테이블/권한 enum/잠금 파일은 수정하지 않았다. readiness와 head 기대 테스트는 0009로 맞췄다.

- p1_voc_requests: product/users/analytics_receipts FK, 상태/revision/provider, nullable model_deployment, 불변 evidence+hash, proposal 또는 reason, 생성/변경 시각. 결과/상태 CHECK와 이력 index.
- p1_voc_request_teams: request/team FK와 복합 PK. 현재 사용자에게 생성 당시 **모든 팀**이 허용될 때만 SQL 조회 가능.
- p1_voc_reviews: request/user FK, 요청당 검토 1회 UNIQUE, APPROVED/REJECTED 및 이유 길이 CHECK(API는 비공백 강제), 검토자/시각.

기존 p1_idempotency의 VOC_GENERATE/VOC_REVIEW operation을 사용하고 자동 grant는 없다. 동기 처리이므로 p1_tasks/lease/attempt writer를 생성하지 않는다. 기존 reserved task target FK는 변경하지 않았으며 향후 비동기 worker 작업에서 따로 이관해야 한다.

0008→0009 upgrade에서 기존 P0/P1 행·권한·task·멱등 기록 보존, 모델 drift 없음, 새 테이블이 비어 있을 때 왕복을 검증했다. VOC 요청/팀/검토 이력이 남으면 downgrade를 거부한다. offline downgrade도 거부하며 자동 데이터 삭제를 하지 않는다. PostgreSQL 동일 키 동시 생성은 provider 호출 1회, 동시 검토는 1개 성공/1개409로 검증했다.

## 최종 테스트

Python 3.12.14/Linux, 고정 requirements-dev.txt, 실제 로컬 PostgreSQL17.11과 테스트별 임시 schema 사용. 실제 Azure는 호출하지 않았다.

| 실행 | 수집 | 통과 | 실패/오류 | 건너뜀 |
|---|---:|---:|---:|---:|
| SQLite 전체 P0/P1/VOC | 501 | 449 | 0 | 52 |
| PostgreSQL 전체 P0/P1/VOC | 501 | 491 | 0 | 10 |
| 위에 포함된 신규 VOC SQLite | 44 | 42 | 0 | 2 |
| 위에 포함된 신규 VOC PostgreSQL | 44 | 44 | 0 | 0 |

소계와 전체·DB별 실행은 합산하지 않는다. SQLite skip은 PG 전용42 + 외부 전체 합성 fixture9 + Windows DPAPI1이다. PG skip은 fixture9+Windows1이며 PG 잠금/동시성 검증은 실행했다. 기존 Starlette/httpx deprecation warning은 각각1건이다. 외부 fixture 전체 적재/원본 Gold 검증 완료를 주장하지 않는다.

[SQLite JUnit](evidence/p1-voc-20261104/sqlite.xml), [PostgreSQL JUnit](evidence/p1-voc-20261104/postgres.xml). JUnit의 hostname만 제거하고 결과/사례는 보존했다. 부족 근거에서 공급자 미호출, Mock 표시, malformed/과대/잘린 출력·잘못된 근거 ID·Azure 미활성/endpoint/오류 매핑, 권한/역할/전체·일부 팀 회수, 비활성 계정, 멱등 replay/충돌, 검토 이유·revision·동시성, P0 원장 불변성, migration 보존/왕복/데이터 보호를 검증했다.

기존 P0 **37경로·41 operation 및 components/security 동일**, 기존 P1 monitoring **4개 GET과 참조 스키마/security 동일**, 최신 handoff/OpenAPI, Ruff check/format(130 Python files), git diff --check 통과. 기존 monitoring 계약은 77cba3a에서 추출한 docs/p1-monitoring-contract.json을 기준으로 검사한다.

실제 Uvicorn HTTP + 별도 임시 PG schema: 합성 analytics 수신/검증/게시 → 로그인 → Mock 제안201 → replay200 → 승인200 → 오래된 revision409 → 상세/이력200 → 비인증401 → 기존 monitoring200, no-store/request_id 확인. 검증 스크립트의 초기 service JWT nbf 누락은 기존 인증 계약에 맞춰 보완했고 애플리케이션 인증을 완화하지 않았다. [HTTP 증거](evidence/p1-voc-20261104/http-smoke.json).

임시 Uvicorn 및 PG는 종료했다. 테스트/smoke schema 잔존0, public table0을 확인했다. [정리 증거](evidence/p1-voc-20261104/cleanup.json).

## 미연동 및 남은 범위

실제 Azure 키/배포/JSON mode/API/network 인증 연결은 미검증이다. Mock/가짜 전송 응답으로만 실행했으며 실제 Azure 품질/비용/가용성을 검증하지 않았다. 실제 Fabric 연결/원천 reconciliation도 없고 FABRIC은 upstream 선언이다. LOCAL_SYNTHETIC과 provider MOCK은 독립적으로 표시한다.

P1 task/AI attempt 집계 writer는 없으므로 monitoring의 해당 coverage는 기존 미관측 계약이다. legacy task reason은 task-backed producer를 가리키고 이번 동기 요청의 상태 신호가 아니다. sync VOC 결과는 자체 API 상태/근거에서 확인한다. 공급자 호출 후 DB 장애 시 외부 비용의 exactly-once는 보장하지 않으며 자동 외부 재시도는 없다.

프론트엔드, 정책 변경 영향 분석, background worker/lease, 실제 provider/Fabric probe·운영 부하·Azure 생성/배포는 이번 범위 밖이다. 생성 문구는 가설이며 사람 검토가 필요하다. 외부 fixture9개/Windows1개 검사는 미완료다.

## Git/실제 변경 파일

브랜치 feature/backend-plus, HEAD 기준 커밋 그대로, 미커밋/unstaged **13개 수정 + 17개 신규 = 30개 파일**. 다른 브랜치나 원격 저장소는 수정하지 않았다. [파일 목록 JSON](evidence/p1-voc-20261104/changed-files.json).

| 구분 | 경로 |
|---|---|
| M | `backend/backend-a/.env.example` |
| M | `backend/backend-a/README.md` |
| M | `backend/backend-a/app/extensions/p1/models.py` |
| A | `backend/backend-a/app/extensions/p1/voc_models.py` |
| A | `backend/backend-a/app/extensions/p1/voc_provider.py` |
| A | `backend/backend-a/app/extensions/p1/voc_router.py` |
| A | `backend/backend-a/app/extensions/p1/voc_schemas.py` |
| A | `backend/backend-a/app/extensions/p1/voc_service.py` |
| M | `backend/backend-a/app/main.py` |
| M | `backend/backend-a/app/schema.py` |
| M | `backend/backend-a/app/seed.py` |
| A | `backend/backend-a/docs/evidence/p1-voc-20261104/changed-files.json` |
| A | `backend/backend-a/docs/evidence/p1-voc-20261104/cleanup.json` |
| A | `backend/backend-a/docs/evidence/p1-voc-20261104/http-smoke.json` |
| A | `backend/backend-a/docs/evidence/p1-voc-20261104/postgres.xml` |
| A | `backend/backend-a/docs/evidence/p1-voc-20261104/sqlite.xml` |
| A | `backend/backend-a/docs/evidence/p1-voc-20261104/summary.json` |
| M | `backend/backend-a/docs/openapi.json` |
| A | `backend/backend-a/docs/p1-monitoring-contract.json` |
| A | `backend/backend-a/docs/p1-voc-api.md` |
| A | `backend/backend-a/docs/p1-voc-implementation-20261104.md` |
| A | `backend/backend-a/migrations/versions/0009_voc_proposals.py` |
| M | `backend/backend-a/tests/p1/test_migrations.py` |
| A | `backend/backend-a/tests/p1/test_voc.py` |
| A | `backend/backend-a/tests/p1/test_voc_provider.py` |
| M | `backend/backend-a/tests/test_analytics_database.py` |
| M | `backend/backend-a/tests/test_phase3_database.py` |
| M | `backend/backend-a/tests/test_repository_layout.py` |
| M | `backend/backend-a/tests/test_workload_postgres.py` |
| M | `docs/P1_TEAM_AND_NEXT_STEP.md` |
