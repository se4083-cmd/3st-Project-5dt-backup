# React JWT / P1 통신 기반 검증 — 2026-11-04 KST

기준/HEAD `02242912ea7545a511296dc73531d4045afd8784`, feature/backend-plus. 미커밋 작업 트리이며 push/다른 브랜치 수정/배포는 하지 않았다. [인증 흐름·실행·미연결 API](p1-auth-foundation.md), [결과 JSON](evidence/p1-auth-20261104/summary.json).

## 구현과 기존 코드 경계

App.tsx는 기존 P0 내용을 LegacyApp으로 유지하면서 AuthProvider와 별도 P1 연결 화면을 붙였다. 기본 mock 모드의 기존 화면/프로필/29개 테스트는 유지했다. 실제 HTTP 모드와 `/p1` 경로에는 로그인→P1 세션 검증 게이트를 적용했다. 기존 메뉴/디자인 틀은 그대로 사용하고 P1 메뉴와 실제 서버 인증 toolbar를 별도 표시한다. 기능별 본 화면은 준비 화면만 제공한다.

신규 auth/store.ts는 JWT를 비공개 메모리 필드로 관리하고 상태 snapshot에는 토큰을 넣지 않는다. 로그아웃/만료/401에서 요청·토큰·보호 session을 제거한다. epoch/generation, AbortSignal 및 최종 결과 검사로 과거 응답이 새 계정·팀을 덮어쓰지 못하게 한다. 새 세션 확인 중에도 이전 보호 하위 트리를 표시하지 않는다. 외부 endpoint로 토큰을 보내거나 refresh/logout API를 만들어 호출하지 않는다.

P1 session parser는 활성 ADMIN·UUID 범위·capabilities를 검증한다. 기존 UI permission과 같은 이름으로 실제 부여된 capability만 기존 읽기 메뉴에 재사용하며 ADMIN이나 mock 프로필에서 권한을 추측하지 않는다. P1 기능 메뉴/직접 경로는 READ capability를 검사한다. 앞으로 기능별 쓰기 UI에는 각 WRITE/GENERATE/REVIEW 권한이 추가로 필요하다.

P1 client는 JSON/Bearer/POST/AbortSignal/명시적 Idempotency-Key와 상태·request ID/replay header를 제공한다. 서버 message/HTML은 노출하지 않고 기능 disabled를 network 오류와 구분한다. POST 자동 재시도는 없고 abort는 이미 완료된 서버 작업의 rollback 보장이 아니다. 기능별 DTO parser는 본 화면 구현 때 추가한다.

기존 api.ts/operations.ts에는 transport 주입만 추가하고 domain.ts에는 선택적 capabilities 및 cache key를 추가했다. useResource/Dashboard/Workspaces/fixtures/styles.css와 기존 테스트, package.json/package-lock은 그대로다. Vite의 기존 test/plugins 설정은 유지하고 loopback API proxy만 추가했다. 새 dependency는 없다.

## 검증 결과

| 실행 | 결과 |
|---|---|
| npm test -- --reporter=dot | **6개 파일·52개 passed**, 실패/skip0; 기존29+신규23 |
| npm run build | **PASS**, TypeScript + Vite8.3.5 |
| FastAPI check_p0_contract | **PASS**, 기존37경로·41 operation과 components/security 동일 |
| FastAPI check_handoff_contract | **PASS** |
| 기존 P1 OpenAPI 회귀2개 | **2 passed**, 모니터링/VOC 계약 유지 |
| backend/ 전체 및 OpenAPI 비교 | 기준 HEAD와 파일 동일; 정책 포함 59 operation 계약 파일 유지 |
| git diff --check | PASS |

FastAPI 전체530개를 다시 실행했다고 주장하지 않는다. 프론트 작업으로 백엔드 코드는 바뀌지 않았으며 계약 검사와 선택된2개 회귀를 실행했다. 기존 Starlette/httpx deprecation warning1건은 남아 있다.

신규23개는 메모리 로그인·Bearer 범위·저장소 미사용·만료·현재401·과거200/401/로그인 취소 응답 폐기·capability/팀 회수·403/503 blocked·잘못된 세션·JSON/멱등키/header·AbortSignal·namespace 탈출 거부·안전한 오류/request ID·HTML/잘못된 JSON·메뉴/직접URL·StrictMode 중복 로그인 방지·P0 KPI 보존·로그인 실패/세션401을 다룬다. 기존 테스트 assertion과 대기 시간을 완화하지 않았다. [최종 테스트 원문](evidence/p1-auth-20261104/react-tests.txt).

## 실제 로컬 HTTP 연결

실제 frontend AuthManager와 createP1Client 코드를 Vite 모듈 loader로 불러와 **Vite 개발 proxy→실제 로컬 Uvicorn/FastAPI→격리 PostgreSQL17.11**로 실행했다. 가짜 fetch 응답으로 대체한 검증이 아니다.

- POST /api/v1/auth/login:200
- GET /api/v1/admin/p1/session:200, 현재 SQL P1_MONITOR_READ와 허용 팀 확인
- frontend P1 client의 Bearer monitoring GET:200 및 실제 X-Request-ID 수신
- 잘못된 로컬 비밀번호:401, 인증/보호 상태 anonymous로 유지
- 로그아웃: 추가 HTTP 호출 없이 메모리 제거

[HTTP 결과](evidence/p1-auth-20261104/http-smoke.json). 서버/브라우저 비밀값은 결과에 저장하지 않았다. 전용 임시 schema로 migration/check/minimal seed를 실행했고 운영/원격 DB는 사용하지 않았다. Vite·Uvicorn 및 PG는 종료했으며 임시 schema 잔존0/public table0을 확인했다. [정리 결과](evidence/p1-auth-20261104/cleanup.json).

이는 브라우저 DOM을 실제로 자동 조작한 E2E는 아니다. React 화면은 jsdom 테스트로 검증했고 실제 네트워크는 프론트 인증/클라이언트 모듈을 통한 HTTP 검증이다. 실제 Azure OpenAI/Fabric/RAG/Search/Backend B 연결이나 배포를 검증한 것으로 표시하지 않는다.

## 남은 문제

기존 P0 Overview DTO의 실서버 adapter, `/staff/voc-improvements`, `/staff/quality/samples`, `/staff/quality/samples/{id}/material`은 현재 backend-plus API와 연결되지 않았다. 기존 참조를 임의의 P1 VOC 제안 API로 바꾸지 않았다. 목록/영향은 [별도 표](p1-auth-foundation.md)에 기록했다. Mock P0 화면이 동작하는 것과 해당 HTTP 연동은 구분한다.

실제 브라우저 E2E, production origin/reverse proxy·CORS/배포, P1 운영 모니터링/VOC/정책 본 화면·쓰기·동적 flags discovery·상품/팀 이름/source 문서 카탈로그는 남아 있다. 준비 메뉴는 capability를 확인하지만 서버 기능 flag=true를 보증하지 않는다. 기능 요청의 disabled 코드를 처리하는 기반까지만 제공했다.

## 변경 파일/Git

HEAD는 기준 병합 커밋 그대로다. 미커밋/unstaged **7개 수정 + 17개 신규 = 24개 파일**, 전부 frontend/ 내부다. 기존 feature/frontend와 다른 팀원 브랜치는 수정하지 않았다. [파일 목록 JSON](evidence/p1-auth-20261104/changed-files.json).

| 구분 | 경로 |
|---|---|
| M | `frontend/.env.example` |
| M | `frontend/README.md` |
| A | `frontend/docs/evidence/p1-auth-20261104/changed-files.json` |
| A | `frontend/docs/evidence/p1-auth-20261104/cleanup.json` |
| A | `frontend/docs/evidence/p1-auth-20261104/http-smoke.json` |
| A | `frontend/docs/evidence/p1-auth-20261104/react-tests.txt` |
| A | `frontend/docs/evidence/p1-auth-20261104/summary.json` |
| A | `frontend/docs/p1-auth-foundation.md` |
| A | `frontend/docs/p1-auth-verification.md` |
| M | `frontend/src/App.tsx` |
| M | `frontend/src/api.ts` |
| A | `frontend/src/auth/AuthProvider.tsx` |
| A | `frontend/src/auth/LoginPanel.tsx` |
| A | `frontend/src/auth/session.ts` |
| A | `frontend/src/auth/store.ts` |
| A | `frontend/src/auth/transport.ts` |
| M | `frontend/src/domain.ts` |
| A | `frontend/src/features/p1/Foundation.tsx` |
| A | `frontend/src/features/p1/client.ts` |
| A | `frontend/src/features/p1/foundation.css` |
| M | `frontend/src/operations.ts` |
| A | `frontend/src/test/auth-ui.test.tsx` |
| A | `frontend/src/test/auth.test.ts` |
| M | `frontend/vite.config.ts` |
