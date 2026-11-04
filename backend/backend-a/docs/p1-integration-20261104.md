# P1 1차 구현 통합 결과 — 2026-11-04 KST

현재 브랜치 `feature/backend-plus`, 기준/HEAD `25e4aad720198ea2a3a0287ccf6f58f69c92d228`. 변경은 미커밋·unstaged 작업 트리에만 있다. push, 다른 브랜치 수정, Azure 생성/배포는 하지 않았다.

## ZIP 대조와 실제 적용

README_DELIVERY, 변경 47개 목록, 과거 TEST_RESULTS/JUnit을 확인하고 SHA256 manifest 238항목을 검증했다. 문서의 bundle 복원/전체 프론트 실행 지시는 참고 자료로 구분했고 사용자 요청 범위만 수행했다. ZIP의 별도 Git 이력을 병합하거나 전체 source를 덮어쓰지 않았다.

현재 Backend A는 0.7.1/0007, ZIP은 0.6.1/0006 기반이다. 공통 백엔드 파일 138개 중 CRLF를 정규화한 비교에서 24개가 다르고, 최신 백엔드 파일 107개가 ZIP에 없다. 비교는 [zip-comparison.json](evidence/p1-integration-20261104/zip-comparison.json)에 기록했다. 최신 followups/repository/workload/staff_router·handoff 검사·기존 증거와 문서는 보존했다. 공유 연결 파일에만 필요한 P1 변경을 적용했다.

- 신규 `app/extensions/p1/`: 저장 기반 모델, opt-in 설정, 권한·세션 bridge, 읽기 집계/목록/AI 미관측 응답과 FastAPI 라우터.
- 기존 Bearer·활성 계정·SnapshotDB/SnapshotUser·오류 봉투·request_id/no-store 재사용. 조회는 ADMIN + 명시 P1_MONITOR_READ + 현재 활성 SQL 팀 grant가 필요하다. session bridge는 활성 ADMIN/팀 grant를 요구하며 capability를 알려준다.
- job 원시 상태/현재 cycle+version/만료 lease/generation/재시도/실패/이전 버전을 구분하며 팀 밖/팀 NULL·민감 worker/lease/원문 정보를 제외한다. analytics 게시 freshness와 실제 Fabric 연결 미관측을 구분한다.
- `app/main.py`, `schema.py`, `staff_models.py`, `seed.py`: router/metadata 연결, 권한 CHECK 확장, P1 테이블의 공식 P0 fixture 제외, readiness 0008. 기존 WORKLOAD_READ 유지.
- `.env.example`에 `P1_ENABLED=false` 추가. 권한은 자동 부여하지 않는다. `scripts/grant_p1_monitor.py`는 명시 실행하는 development/test용 도구다.
- P0 baseline은 ZIP 파일이 아니라 현재 HEAD의 OpenAPI를 `docs/p0-openapi.json`에 보존하고 `check_p0_contract.py`로 비교한다. 생성 OpenAPI에는 P1 GET 4개가 추가됐다.

## API와 마이그레이션

| GET 경로 | 동작 |
|---|---|
| `/api/v1/admin/p1/session` | 활성 ADMIN의 현재 팀·권한 bridge |
| `/api/v1/admin/p1/monitoring/summary` | 허용팀 작업 상태·제어 상태 권한·분석 freshness |
| `/api/v1/admin/p1/monitoring/jobs` | 허용팀 작업 목록·필터·cursor와 최소 공개 필드 |
| `/api/v1/admin/p1/monitoring/ai-calls` | timezone/최대 7일 검증, 아직 계측 없음(null/UNOBSERVED) |

기본 flag는 false(503 P1_DISABLED). 테스트/로컬 실행에서 true로 활성화해 검증했다. 제어 쓰기는 기존 staff stop/resume와 별도 AUTOMATION_READ/STOP/RESUME·revision/generation 계약을 그대로 사용한다.

ZIP의 `0007_p1_foundation.py`는 **0008_p1_foundation.py**, revision=0008/down_revision=0007로 이식했다. 기존 0001–0007은 변경하지 않았다. 단일 head이며 p1_idempotency/p1_tasks/p1_ai_call_attempts 및 권한 문자열을 추가한다. 예약 VOC/정책 문자열/대상 UUID는 기능 구현을 뜻하지 않으며 후속 FK가 필요하다.

기존 P0 행과 WORKLOAD_READ grant 보존, 자동 grant 없음, Alembic metadata drift 없음, 빈 P1 schema 0007→0008→0007→0008 왕복, P1 데이터/권한이 남은 downgrade 거부를 SQLite와 PostgreSQL에서 검증했다. 기존 workload downgrade의 권한/감사 이력 보호도 유지한다. readiness와 기존 head 기대 테스트만 새 head에 맞췄다. 기존 fixture/PG skip 조건이나 실패 assertion을 완화하지 않았다.

## 이번에 실행한 검증

Python 3.12.14/Linux, 고정 requirements-dev.txt 사용. PostgreSQL은 Debian 서명 인덱스로 검증된 17.11 패키지를 임시 경로에 풀어 127.0.0.1 전용 클러스터/빈 테스트 DB를 만들었다. 원격 DB나 기존 개발 DB는 사용하지 않았다.

| 최종 실행 | 수집 | 통과 | 실패/오류 | 건너뜀 |
|---|---:|---:|---:|---:|
| SQLite `python -m pytest -q -ra` | 457 | 407 | 0 | 50 |
| PostgreSQL `python -m pytest --database=postgres -q -ra` | 457 | 447 | 0 | 10 |
| 위 실행에 포함된 P1 (SQLite) | 24 | 23 | 0 | 1 |
| 위 실행에 포함된 P1 (PostgreSQL) | 24 | 24 | 0 | 0 |

P1 소계는 전체에 이미 포함되므로 합산하지 않는다. SQLite skip은 PG 전용 40 + 외부 전체 fixture 9 + Windows DPAPI 1이다. PostgreSQL skip은 외부 fixture 9 + Windows 1이며 **PG 전용 검증은 실행했다**. 외부 합성 fixture 전체 적재/원본 Gold까지 완료한 결과는 아니다. 두 실행 모두 기존 Starlette/httpx deprecation warning 1건이 있다. 고정 의존성을 바꾸지 않았다.

기존 P0 **37경로·41 operation 및 기존 components/security 완전 동일** 검사, 최신 workload 관련 handoff 검사, Ruff check/format(122 files), 의존성 정합성(pip check), git diff --check 통과. 실제 HTTP/Uvicorn + 별도 PG 임시 schema에서 health live/ready, 로그인, P1 4개 조회 200, 비인증 401, no-store/request_id와 null/UNOBSERVED 의미를 확인했다. 서버와 smoke schema는 정리했다. PG 전체 테스트 후 남은 테스트 schema 0/public table 0을 확인하고 이번 전용 서버를 종료했다.

초기 SQLite 403/50 결과 후 권한·workload 보존 회귀를 추가했고 위 최종 407/50으로 재실행했다. ZIP의 과거 baseline/final 수치는 이번 결과에 포함하지 않는다. [summary](evidence/p1-integration-20261104/summary.json), [SQLite JUnit](evidence/p1-integration-20261104/sqlite.xml), [PostgreSQL JUnit](evidence/p1-integration-20261104/postgres.xml), [실제 HTTP](evidence/p1-integration-20261104/http-smoke.json), [정리 확인](evidence/p1-integration-20261104/cleanup.json).

## 프론트엔드 별도 통합 계획

읽기 확인한 `origin/feature/frontend` 기준은 `46f2ca6cab56ae493087f3dde43ceb7acfc111f3`, 실제 React/Vite 위치는 **frontend/**이며 HashRouter를 사용한다. 현재 브랜치에는 README만 있어 코드를 복사하지 않았다. ZIP `frontend/ops-review` 전체로 덮어쓰면 기존 UI/Mock 계약과 프로젝트 위치가 달라진다.

1. 별도 통합 작업에서 그 시점 최신 feature/frontend와 ZIP 변경을 다시 비교한다. `src/features/p1/*`, `src/authTransport.ts`, `src/test/p1-monitoring.test.tsx`를 frontend/ 아래로 선별 이식한다.
2. 기존 `src/api.ts`의 ApiError/검증/Mock 흐름을 유지하면서 공통 JSON/Bearer/AbortSignal/request_id transport를 연결한다. 로그인은 기존 `/api/v1/auth/login`, 이후 P1 `/session`으로 현재 SQL 권한/팀을 받는다. 토큰은 메모리에만 두고 401/로그아웃 시 폐기한다.
3. `App.tsx`, `components.tsx`, `domain.ts`, `fixtures.ts`는 P1 경로/메뉴/권한 타입만 최소 통합한다. HashRouter의 `#/monitoring`과 현재 P0 페이지·Mock 상태를 유지한다. 제어 버튼은 capabilities의 STOP/RESUME를 각각 확인하며 READ나 P1_MONITOR_READ를 제어 권한으로 간주하지 않는다.
4. 팀 필터의 반복 team_ids, 계정/팀 변경 시 이전 요청 취소·데이터 제거, 비활성 탭 polling 중단, 15초 polling/수동 갱신, 401/403/409/422/503, null/UNOBSERVED와 합성/Fabric 선언 표시를 테스트한다. Vite `/api` 로컬 proxy 또는 명시 CORS를 설정한다. 프론트에 DB/Azure 비밀값을 넣지 않는다.
5. frontend/에서 npm ci, npm test, npm run build를 실행하고 실제 브라우저 E2E로 로그인→팀 필터→조회→권한 회수/제어 충돌을 검증한다. 이번 작업에서 프론트 테스트/빌드/E2E를 실행했다고 주장하지 않는다.

## 남은 범위와 Git 상태

외부 전체 합성 fixture와 Windows 전용 검사, 프론트 연동·브라우저 E2E는 미완료다. AI VOC 개선 제안·정책 영향 분석, worker/producer·계측 writer·실제 provider/Fabric probe·운영 부하·배포는 구현/실행하지 않았다. `p1_tasks` counts는 null/NO_TASK_PRODUCER, AI 계측은 null/UNOBSERVED다.

실제 변경은 **11개 수정 + 29개 신규 = 40개 파일**이며 아래 목록에 모두 기록했다. 기존 main/feature/backend-a/feature/frontend ref와 frontend 파일, 기존 migrations, requirements/lockfiles는 그대로다. 커밋 생성과 원격 push는 하지 않았다. 현재 HEAD는 기준 커밋 그대로이고 P1 변경은 작업 트리에 있다.

## 실제 변경 파일

| 구분 | 경로 |
|---|---|
| M | `backend/backend-a/.env.example` |
| M | `backend/backend-a/README.md` |
| A | `backend/backend-a/app/extensions/__init__.py` |
| A | `backend/backend-a/app/extensions/p1/__init__.py` |
| A | `backend/backend-a/app/extensions/p1/models.py` |
| A | `backend/backend-a/app/extensions/p1/monitoring_service.py` |
| A | `backend/backend-a/app/extensions/p1/permissions.py` |
| A | `backend/backend-a/app/extensions/p1/router.py` |
| A | `backend/backend-a/app/extensions/p1/schemas.py` |
| A | `backend/backend-a/app/extensions/p1/settings.py` |
| M | `backend/backend-a/app/main.py` |
| M | `backend/backend-a/app/schema.py` |
| M | `backend/backend-a/app/seed.py` |
| M | `backend/backend-a/app/staff_models.py` |
| A | `backend/backend-a/docs/evidence/p1-integration-20261104/changed-files.json` |
| A | `backend/backend-a/docs/evidence/p1-integration-20261104/cleanup.json` |
| A | `backend/backend-a/docs/evidence/p1-integration-20261104/http-smoke.json` |
| A | `backend/backend-a/docs/evidence/p1-integration-20261104/postgres.xml` |
| A | `backend/backend-a/docs/evidence/p1-integration-20261104/sqlite.xml` |
| A | `backend/backend-a/docs/evidence/p1-integration-20261104/summary.json` |
| A | `backend/backend-a/docs/evidence/p1-integration-20261104/zip-comparison.json` |
| M | `backend/backend-a/docs/openapi.json` |
| A | `backend/backend-a/docs/p0-openapi.json` |
| A | `backend/backend-a/docs/p1-api-contract.md` |
| A | `backend/backend-a/docs/p1-integration-20261104.md` |
| A | `backend/backend-a/docs/p1-runbook.md` |
| A | `backend/backend-a/migrations/versions/0008_p1_foundation.py` |
| A | `backend/backend-a/scripts/check_p0_contract.py` |
| A | `backend/backend-a/scripts/grant_p1_monitor.py` |
| A | `backend/backend-a/tests/p1/__init__.py` |
| A | `backend/backend-a/tests/p1/test_contract.py` |
| A | `backend/backend-a/tests/p1/test_migrations.py` |
| A | `backend/backend-a/tests/p1/test_monitoring.py` |
| M | `backend/backend-a/tests/test_analytics_database.py` |
| M | `backend/backend-a/tests/test_phase3_database.py` |
| M | `backend/backend-a/tests/test_repository_layout.py` |
| M | `backend/backend-a/tests/test_workload_postgres.py` |
| A | `docs/P1_DATABASE_CHANGES.md` |
| A | `docs/P1_DESIGN_DIFFERENCES.md` |
| A | `docs/P1_TEAM_AND_NEXT_STEP.md` |
